from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, BasePermission

from rest_framework import viewsets
from django.contrib.auth.models import User
from .serializers import UserSerializer
from .permissions import IsPRE, IsLQ as IsLQPerm

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

class IsSuperUser(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_superuser)

class UserMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        profile = getattr(user, 'profile', None)
        mail_account_id = None
        if profile and profile.mail_account_id:
            mail_account_id = profile.mail_account_id
        return Response({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'role': profile.role if profile else 'PRE',
            'is_superuser': user.is_superuser,
            'mail_account_id': mail_account_id,
        })

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = UserSerializer
    permission_classes = [IsSuperUser]

from .models import MailAccount
from .serializers import MailAccountSerializer
from rest_framework.decorators import action
from rest_framework import status
import smtplib
import imaplib
import email
from email.header import decode_header
import utils.encryption as encryption
import re
import time

class IsLQ(IsLQPerm):
    """Local alias so the rest of this module can reference IsLQ directly."""
    pass

class MailAccountViewSet(viewsets.ModelViewSet):

    @action(detail=False, methods=['get'], url_path='fetch-emails')
    def fetch_emails(self, request):
        """
        Fetch email metadata for the authenticated user's mail account using IMAP UIDs.

        Returns a list of messages with stable UID identifiers instead of sequence numbers.
        Also returns the mailbox UIDVALIDITY so the client can detect mailbox resets.

        Query params:
            folder (str): IMAP folder name, default 'INBOX'
            limit (int): maximum messages to return (newest first), default 20
        """
        user = request.user
        if not hasattr(user, 'profile'):
            return Response({'error': 'No profile found.'}, status=status.HTTP_400_BAD_REQUEST)

        mail_account = MailAccount.objects.filter(
            id=user.profile.mail_account_id, is_active=True
        ).first()
        if not mail_account:
            return Response(
                {'error': 'No active mail account configured.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        folder = request.query_params.get('folder', 'INBOX')
        limit = int(request.query_params.get('limit', 20))

        mail = None
        try:
            password = encryption.decrypt_password(mail_account.imap_app_password_encrypted)
            if mail_account.imap_security == 'SSL':
                mail = imaplib.IMAP4_SSL(mail_account.imap_host, mail_account.imap_port)
            else:
                mail = imaplib.IMAP4(mail_account.imap_host, mail_account.imap_port)
                mail.starttls()

            mail.login(mail_account.imap_username, password)
            select_status, select_data = mail.select(folder)

            if select_status != 'OK':
                return Response(
                    {'error': f'Failed to select folder {folder}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Extract UIDVALIDITY from the SELECT response
            uidvalidity = None
            for item in select_data:
                if item and isinstance(item, bytes) and b'UIDVALIDITY' in item:
                    try:
                        parts = item.decode().split()
                        idx = parts.index('UIDVALIDITY')
                        uidvalidity = int(parts[idx + 1])
                    except (ValueError, IndexError):
                        pass

            # Use STATUS to get UIDVALIDITY if not found in SELECT response
            if uidvalidity is None:
                status_res, status_data = mail.status(folder, '(UIDVALIDITY)')
                if status_res == 'OK' and status_data:
                    try:
                        status_str = status_data[0].decode()
                        parts = status_str.replace(')', '').split()
                        idx = parts.index('UIDVALIDITY')
                        uidvalidity = int(parts[idx + 1])
                    except (ValueError, IndexError, AttributeError):
                        pass

            # Search using UIDs instead of sequence numbers
            uid_status, uid_data = mail.uid('SEARCH', None, 'ALL')
            if uid_status != 'OK':
                return Response(
                    {'error': 'Failed to search emails'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            all_uids = uid_data[0].split()
            # Fetch up to 100 recent emails to allow for filtering, we will break when we hit `limit` owned emails
            recent_uids = all_uids[-100:]
            recent_uids.reverse()  # newest first

            emails_list = []
            from prospects.models import OutreachEmail, ProspectContact, Prospect

            for uid_bytes in recent_uids:
                if len(emails_list) >= limit:
                    break
                    
                uid_str = uid_bytes.decode()
                # Fetch headers using UID command — PEEK avoids marking as read
                res_status, hdr_data = mail.uid(
                    'FETCH', uid_bytes, '(FLAGS BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE MESSAGE-ID IN-REPLY-TO REFERENCES)])'
                )
                if res_status != 'OK':
                    continue

                subject = ''
                from_hdr = ''
                date_hdr = ''
                message_id = ''
                is_unread = True  # default; corrected from FLAGS below

                for part in hdr_data:
                    if isinstance(part, tuple):
                        # part[0] contains FLAGS info, part[1] is the header bytes
                        part_info = part[0].decode() if isinstance(part[0], bytes) else ''
                        flags_str = part_info.upper()
                        is_unread = '\\SEEN' not in flags_str

                        hdr_msg = email.message_from_bytes(part[1])

                        raw_subject = hdr_msg.get('Subject', '')
                        decoded_subject = decode_header(raw_subject)
                        subject_parts = []
                        for s_bytes, enc in decoded_subject:
                            if isinstance(s_bytes, bytes):
                                subject_parts.append(s_bytes.decode(enc or 'utf-8', errors='ignore'))
                            else:
                                subject_parts.append(s_bytes or '')
                        subject = ''.join(subject_parts)

                        from_hdr = hdr_msg.get('From', '')
                        to_hdr = hdr_msg.get('To', '')
                        date_hdr = hdr_msg.get('Date', '')
                        message_id = hdr_msg.get('Message-ID', '')
                        in_reply_to = str(hdr_msg.get('In-Reply-To', ''))
                        references = str(hdr_msg.get('References', ''))

                # Attempt to match prospect company
                prospect_company_name = None
                email_pattern = re.compile(r'[\w\.-]+@[\w\.-]+\.\w+')
                all_emails = email_pattern.findall(from_hdr) + email_pattern.findall(to_hdr)
                if all_emails:
                    from prospects.models import ProspectContact, Prospect
                    contact = ProspectContact.objects.filter(official_email__in=all_emails).select_related('prospect').first()
                    if contact and contact.prospect:
                        prospect_company_name = contact.prospect.company_name
                    else:
                        prospect = Prospect.objects.filter(official_email_address__in=all_emails).first()
                        if prospect:
                            prospect_company_name = prospect.company_name

                if not prospect_company_name and (in_reply_to or references):
                    refs = (in_reply_to + ' ' + references).replace('<', ' ').replace('>', ' ').split()
                    for ref in refs:
                        ref = ref.strip()
                        if not ref:
                            continue
                        oe = OutreachEmail.objects.filter(message_id__icontains=ref).select_related('prospect').first()
                        if oe and oe.prospect:
                            prospect_company_name = oe.prospect.company_name
                            break

                # --- OWNERSHIP FILTERING ---
                is_owned = False
                # 1. If it's a sent email, did this user send it?
                if 'sent' in folder.lower():
                    clean_msg_id = message_id.strip('<>')
                    if clean_msg_id and OutreachEmail.objects.filter(message_id__icontains=clean_msg_id, created_by=user).exists():
                        is_owned = True
                else:
                    # 2. If it's an inbox/received email, is it a reply to this user?
                    if in_reply_to or references:
                        refs = (in_reply_to + ' ' + references).replace('<', ' ').replace('>', ' ').split()
                        for ref in refs:
                            ref = ref.strip()
                            if ref and OutreachEmail.objects.filter(message_id__icontains=ref, created_by=user).exists():
                                is_owned = True
                                break
                    # 3. Or if it's from a prospect the user has interacted with
                    if not is_owned and prospect_company_name:
                        if OutreachEmail.objects.filter(prospect__company_name=prospect_company_name, created_by=user).exists():
                            is_owned = True
                            
                # If they don't own it, skip it
                if not is_owned:
                    continue

                emails_list.append({
                    'uid': uid_str,
                    'id': uid_str,  # backward-compatible field
                    'message_id': message_id,
                    'subject': subject,
                    'from': from_hdr,
                    'to': to_hdr,
                    'date': date_hdr,
                    'is_unread': is_unread,
                    'folder': folder,
                    'prospect_company_name': prospect_company_name,
                })

            return Response({
                'uidvalidity': uidvalidity,
                'messages': emails_list,
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            if mail is not None:
                try:
                    mail.logout()
                except Exception:
                    pass

    @action(detail=False, methods=['post'], url_path='send-email')
    def send_email_action(self, request):
        user = request.user
        profile = getattr(user, 'profile', None)
        mail_account = MailAccount.objects.filter(id=profile.mail_account_id if profile else None, is_active=True).first()
        if not mail_account:
            return Response({'error': 'No active mail account.'}, status=status.HTTP_400_BAD_REQUEST)
            
        to_address = request.data.get('to')
        subject = request.data.get('subject', '')
        body = request.data.get('body', '')
        
        if not to_address:
            return Response({'error': 'To address is required.'}, status=status.HTTP_400_BAD_REQUEST)
            
        from email.message import EmailMessage
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = f"{mail_account.display_name} <{mail_account.email_address}>" if mail_account.display_name else mail_account.email_address
        msg['To'] = to_address
        msg.set_content(body)
        
        def send_smtp_and_imap():
            import time
            import imaplib
            try:
                password = encryption.decrypt_password(mail_account.smtp_app_password_encrypted)
                if mail_account.smtp_security == 'SSL':
                    server = smtplib.SMTP_SSL(mail_account.smtp_host, mail_account.smtp_port, timeout=30)
                else:
                    server = smtplib.SMTP(mail_account.smtp_host, mail_account.smtp_port, timeout=30)
                    server.starttls()
                server.login(mail_account.smtp_username, password)
                server.send_message(msg)
                server.quit()
                
                try:
                    if mail_account.imap_security == 'SSL':
                        imap = imaplib.IMAP4_SSL(mail_account.imap_host, mail_account.imap_port)
                    else:
                        imap = imaplib.IMAP4(mail_account.imap_host, mail_account.imap_port)
                        imap.starttls()
                    imap.login(mail_account.imap_username, password)
                    # Attempt to save to Sent folder
                    sent_folder = '"[Gmail]/Sent Mail"' if 'gmail' in mail_account.imap_host.lower() else 'Sent'
                    imap.append(sent_folder, '\\Seen', imaplib.Time2Internaldate(time.time()), msg.as_bytes())
                    imap.logout()
                except Exception as e:
                    print(f"Background IMAP append failed: {e}")
            except Exception as e:
                print(f"Background SMTP send failed: {e}")

        import threading
        t = threading.Thread(target=send_smtp_and_imap)
        t.start()
        
        return Response({'success': True})

    @action(detail=False, methods=['get'], url_path='fetch-email-body')
    def fetch_email_body(self, request):
        """
        Fetch the full body of a single email by UID.

        Query params:
            folder (str): IMAP folder name, default 'INBOX'
            uid (str): IMAP UID of the email (stable; preferred)
            email_id (str): legacy alias for uid
        """
        user = request.user
        if not hasattr(user, 'profile'):
            return Response({'error': 'No profile found.'}, status=status.HTTP_400_BAD_REQUEST)

        mail_account = MailAccount.objects.filter(
            id=user.profile.mail_account_id, is_active=True
        ).first()
        if not mail_account:
            return Response(
                {'error': 'No active mail account configured.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        folder = request.query_params.get('folder', 'INBOX')
        # Accept 'uid' (preferred) or legacy 'email_id'
        uid = request.query_params.get('uid') or request.query_params.get('email_id')
        if not uid:
            return Response({'error': 'uid is required.'}, status=status.HTTP_400_BAD_REQUEST)

        mail_conn = None
        try:
            password = encryption.decrypt_password(mail_account.imap_app_password_encrypted)
            if mail_account.imap_security == 'SSL':
                mail_conn = imaplib.IMAP4_SSL(mail_account.imap_host, mail_account.imap_port)
            else:
                mail_conn = imaplib.IMAP4(mail_account.imap_host, mail_account.imap_port)
                mail_conn.starttls()

            mail_conn.login(mail_account.imap_username, password)
            mail_conn.select(folder)

            # Fetch full RFC822 message by UID
            res_status, msg_data = mail_conn.uid('FETCH', uid.encode(), '(RFC822)')

            if res_status != 'OK':
                return Response(
                    {'error': 'Failed to fetch email body.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            html_body = ''
            text_body = ''
            attachments = []
            import base64

            def process_attachment(part):
                filename = part.get_filename()
                if not filename:
                    filename = 'unknown_attachment'
                else:
                    decoded_headers = email.header.decode_header(filename)
                    filename = ''.join([str(t[0], t[1] or 'utf-8') if isinstance(t[0], bytes) else t[0] for t in decoded_headers])
                payload = part.get_payload(decode=True)
                if payload:
                    b64_data = base64.b64encode(payload).decode('utf-8')
                    attachments.append({
                        'filename': filename,
                        'content_type': part.get_content_type(),
                        'data': b64_data,
                        'size': len(payload)
                    })

            for part in msg_data:
                if isinstance(part, tuple):
                    msg = email.message_from_bytes(part[1])
                    if msg.is_multipart():
                        for mp in msg.walk():
                            content_type = mp.get_content_type()
                            disposition = str(mp.get('Content-Disposition', ''))
                            if 'attachment' in disposition or mp.get_filename():
                                process_attachment(mp)
                                continue
                            payload = mp.get_payload(decode=True)
                            if payload is None:
                                continue
                            charset = mp.get_content_charset() or 'utf-8'
                            decoded = payload.decode(charset, errors='ignore')
                            if content_type == 'text/html' and not html_body:
                                html_body = decoded
                            elif content_type == 'text/plain' and not text_body:
                                text_body = decoded
                    else:
                        disposition = str(msg.get('Content-Disposition', ''))
                        if 'attachment' in disposition or msg.get_filename():
                            process_attachment(msg)
                        else:
                            payload = msg.get_payload(decode=True)
                            if payload:
                                charset = msg.get_content_charset() or 'utf-8'
                                decoded = payload.decode(charset, errors='ignore')
                                if msg.get_content_type() == 'text/html':
                                    html_body = decoded
                                else:
                                    text_body = decoded

            return Response({
                'html_body': html_body,
                'text_body': text_body,
                'attachments': attachments,
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            if mail_conn is not None:
                try:
                    mail_conn.logout()
                except Exception:
                    pass

    @action(detail=False, methods=['get'], url_path='check-new-mail')
    def check_new_mail(self, request):
        """
        Lightweight mailbox delta check.

        Instead of fetching all headers, this uses IMAP STATUS to compare the
        current mailbox state against the client's known state.  When new UIDs
        are present, only the missing message metadata is fetched.

        Query params:
            folder (str): IMAP folder name, default 'INBOX'
            uidvalidity (int): client's known UIDVALIDITY (0 if unknown)
            highest_uid (int): client's highest known UID (0 if unknown)

        Returns:
            {
              "uidvalidity": int,
              "uidvalidity_changed": bool,   # True if client must rebuild cache
              "unseen_count": int,
              "highest_uid": int,
              "new_messages": [...]           # only when new UIDs were found
            }
        """
        user = request.user
        if not hasattr(user, 'profile'):
            return Response({'error': 'No profile found.'}, status=status.HTTP_400_BAD_REQUEST)

        mail_account = MailAccount.objects.filter(
            id=user.profile.mail_account_id, is_active=True
        ).first()
        if not mail_account:
            return Response(
                {'error': 'No active mail account configured.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        folder = request.query_params.get('folder', 'INBOX')
        try:
            client_uidvalidity = int(request.query_params.get('uidvalidity', 0))
        except (TypeError, ValueError):
            client_uidvalidity = 0
        try:
            client_highest_uid = int(request.query_params.get('highest_uid', 0))
        except (TypeError, ValueError):
            client_highest_uid = 0

        mail = None
        try:
            password = encryption.decrypt_password(mail_account.imap_app_password_encrypted)
            if mail_account.imap_security == 'SSL':
                mail = imaplib.IMAP4_SSL(mail_account.imap_host, mail_account.imap_port)
            else:
                mail = imaplib.IMAP4(mail_account.imap_host, mail_account.imap_port)
                mail.starttls()

            mail.login(mail_account.imap_username, password)

            # Use STATUS to get mailbox state without fully selecting it
            status_res, status_data = mail.status(folder, '(UIDVALIDITY UIDNEXT UNSEEN)')
            if status_res != 'OK' or not status_data:
                return Response(
                    {'error': f'Failed to get status for folder {folder}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            status_str = status_data[0].decode() if isinstance(status_data[0], bytes) else str(status_data[0])
            # Parse: '... (UIDVALIDITY 123 UIDNEXT 456 UNSEEN 7)'
            status_str = status_str.replace(')', '').replace('(', '')
            parts = status_str.split()

            def extract(key, default=0):
                try:
                    idx = parts.index(key)
                    return int(parts[idx + 1])
                except (ValueError, IndexError):
                    return default

            server_uidvalidity = extract('UIDVALIDITY')
            server_uidnext = extract('UIDNEXT')
            unseen_count = extract('UNSEEN')

            # UIDNEXT is the next UID to be assigned, so current highest = UIDNEXT - 1
            server_highest_uid = max(0, server_uidnext - 1)

            uidvalidity_changed = (
                client_uidvalidity != 0 and server_uidvalidity != client_uidvalidity
            )

            response_data = {
                'uidvalidity': server_uidvalidity,
                'uidvalidity_changed': uidvalidity_changed,
                'unseen_count': unseen_count,
                'highest_uid': server_highest_uid,
                'new_messages': [],
            }

            if uidvalidity_changed:
                # Client must rebuild the cache; don't mix old UIDs with new ones
                return Response(response_data, status=status.HTTP_200_OK)

            # Check if there are new UIDs the client doesn't have yet
            new_uids_exist = server_highest_uid > client_highest_uid

            if not new_uids_exist:
                return Response(response_data, status=status.HTTP_200_OK)

            # Select the folder to run UID SEARCH
            select_res, _ = mail.select(folder)
            if select_res != 'OK':
                return Response(response_data, status=status.HTTP_200_OK)

            # Search for UIDs the client doesn't know about
            search_criteria = f'{client_highest_uid + 1}:*'
            uid_res, uid_data = mail.uid('SEARCH', None, f'UID {search_criteria}')
            if uid_res != 'OK' or not uid_data or not uid_data[0]:
                return Response(response_data, status=status.HTTP_200_OK)

            new_uid_list = uid_data[0].split()
            new_messages = []

            for uid_bytes in new_uid_list:
                uid_str = uid_bytes.decode()
                try:
                    uid_int = int(uid_str)
                except ValueError:
                    continue

                if uid_int <= client_highest_uid:
                    continue

                fetch_res, hdr_data = mail.uid(
                    'FETCH', uid_bytes,
                    '(FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])'
                )
                if fetch_res != 'OK':
                    continue

                subject = ''
                from_hdr = ''
                date_hdr = ''
                message_id = ''
                is_unread = True

                for part in hdr_data:
                    if isinstance(part, tuple):
                        part_info = part[0].decode() if isinstance(part[0], bytes) else ''
                        is_unread = '\\SEEN' not in part_info.upper()

                        hdr_msg = email.message_from_bytes(part[1])

                        raw_subject = hdr_msg.get('Subject', '')
                        decoded_subject = decode_header(raw_subject)
                        subject_parts = []
                        for s_bytes, enc in decoded_subject:
                            if isinstance(s_bytes, bytes):
                                subject_parts.append(s_bytes.decode(enc or 'utf-8', errors='ignore'))
                            else:
                                subject_parts.append(s_bytes or '')
                        subject = ''.join(subject_parts)

                        from_hdr = hdr_msg.get('From', '')
                        date_hdr = hdr_msg.get('Date', '')
                        message_id = hdr_msg.get('Message-ID', '')

                new_messages.append({
                    'uid': uid_str,
                    'id': uid_str,
                    'message_id': message_id,
                    'subject': subject,
                    'from': from_hdr,
                    'date': date_hdr,
                    'is_unread': is_unread,
                    'folder': folder,
                })

            response_data['new_messages'] = new_messages
            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            if mail is not None:
                try:
                    mail.logout()
                except Exception:
                    pass

    # Legacy endpoint kept for backward compatibility with old fetch_emails URL
    @action(detail=False, methods=['get'], url_path='fetch_emails')
    def fetch_emails_legacy(self, request):
        """Legacy underscore URL — delegates to fetch_emails."""
        return self.fetch_emails(request)

    # Legacy endpoint kept for backward compatibility with old fetch_email_body URL
    @action(detail=False, methods=['get'], url_path='fetch_email_body')
    def fetch_email_body_legacy(self, request):
        """Legacy underscore URL — delegates to fetch_email_body."""
        return self.fetch_email_body(request)

    serializer_class = MailAccountSerializer
    permission_classes = [IsLQ]

    def get_queryset(self):
        return MailAccount.objects.all()

    def perform_create(self, serializer):
        mail_account = serializer.save()
        profile = self.request.user.profile
        profile.mail_account = mail_account
        profile.save()

    @action(detail=True, methods=['post'], url_path='set-default')
    def set_default(self, request, pk=None):
        mail_account = self.get_object()
        profile = request.user.profile
        profile.mail_account = mail_account
        profile.save()
        return Response({'status': 'default set'})

    @action(detail=True, methods=['post'], url_path='test-smtp')
    def test_smtp(self, request, pk=None):
        mail_account = self.get_object()
        server = None
        try:
            password = encryption.decrypt_password(mail_account.smtp_app_password_encrypted)
            if mail_account.smtp_security == 'SSL':
                server = smtplib.SMTP_SSL(mail_account.smtp_host, mail_account.smtp_port, timeout=30)
            else:
                server = smtplib.SMTP(mail_account.smtp_host, mail_account.smtp_port, timeout=30)
                server.starttls()
            server.login(mail_account.smtp_username, password)
            mail_account.smtp_status = 'VERIFIED'
            mail_account.save()
            return Response({'message': 'SMTP connection successful.'})
        except Exception as e:
            mail_account.smtp_status = 'FAILED'
            mail_account.save()
            return Response({'error': 'Unable to connect to SMTP server. Please verify the configuration.'}, status=status.HTTP_400_BAD_REQUEST)
        finally:
            if server is not None:
                try:
                    server.quit()
                except Exception:
                    pass

    @action(detail=True, methods=['post'], url_path='test-imap')
    def test_imap(self, request, pk=None):
        mail_account = self.get_object()
        server = None
        try:
            password = encryption.decrypt_password(mail_account.imap_app_password_encrypted)
            if mail_account.imap_security == 'SSL':
                server = imaplib.IMAP4_SSL(mail_account.imap_host, mail_account.imap_port)
            else:
                server = imaplib.IMAP4(mail_account.imap_host, mail_account.imap_port)
                server.starttls()
            server.login(mail_account.imap_username, password)
            mail_account.imap_status = 'CONNECTED'
            mail_account.save()
            return Response({'message': 'IMAP connection successful.'})
        except Exception as e:
            mail_account.imap_status = 'FAILED'
            mail_account.save()
            return Response({'error': 'Unable to connect to IMAP server. Please verify the configuration.'}, status=status.HTTP_400_BAD_REQUEST)
        finally:
            if server is not None:
                try:
                    server.logout()
                except Exception:
                    pass
