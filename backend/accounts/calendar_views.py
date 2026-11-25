"""Optional Google Calendar connection endpoints (separate from Gmail/login)."""
import uuid
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .calendar_services import (
    CalendarAuthError,
    CalendarError,
    GoogleCalendarOAuthService,
    create_meet_event,
    get_calendar_credentials,
    list_events,
    delete_event,
    _api_request,
    extract_conference,
)
from .models import GoogleCalendarCredentials
from .oauth_services import GoogleOAuthService
from .serializers import GmailOAuthCallbackSerializer  # plain {code, state} serializer


def _can_use_calendar(user):
    """PRE, LQ and MANAGER users (and superusers) may use Calendar."""
    if user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    return bool(profile and profile.role in ('PRE', 'LQ', 'MANAGER'))


class _CalendarBase(APIView):
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not _can_use_calendar(request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only PRE, Lead Qualifiers and Managers can use Google Calendar.")


class CalendarOAuthURLView(_CalendarBase):
    def get(self, request):
        try:
            url, state = GoogleCalendarOAuthService.generate_authorization_url(request.user.id)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"url": url, "authorization_url": url, "state": state}, status=status.HTTP_200_OK)


class CalendarOAuthCallbackView(_CalendarBase):
    def post(self, request):
        serializer = GmailOAuthCallbackSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        code = serializer.validated_data['code']
        state = serializer.validated_data['state']

        if not GoogleCalendarOAuthService.verify_state(state, request.user.id):
            return Response({"detail": "Invalid or expired Google Calendar authorization state."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            tokens = GoogleCalendarOAuthService.exchange_code_for_tokens(code)
            creds = GoogleCalendarOAuthService.store_tokens(request.user, tokens)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Google Calendar connected successfully.", "email": creds.email},
                        status=status.HTTP_200_OK)


class CalendarOAuthStatusView(_CalendarBase):
    """Connection state only; tokens/secrets are never returned."""
    def get(self, request):
        configured = GoogleOAuthService.is_configured()
        creds = get_calendar_credentials(request.user)
        if not creds:
            return Response({"is_connected": False, "is_configured": configured}, status=status.HTTP_200_OK)
        return Response({"is_connected": True, "is_configured": configured, "email": creds.email,
                         "updated_at": creds.updated_at}, status=status.HTTP_200_OK)


class CalendarOAuthDisconnectView(_CalendarBase):
    def post(self, request):
        creds = GoogleCalendarCredentials.objects.filter(user=request.user).first()
        if creds:
            GoogleCalendarOAuthService.revoke(creds)
            creds.delete()
        try:
            from .models import GoogleMailCredentials
            from .oauth_services import GmailOAuthService
            mail_creds = GoogleMailCredentials.objects.filter(user=request.user).first()
            if mail_creds:
                GmailOAuthService.revoke_tokens(mail_creds)
                mail_creds.delete()
        except Exception as e:
            pass
        return Response({"detail": "Google account disconnected."}, status=status.HTTP_200_OK)


class MeetingProvidersStatusView(_CalendarBase):
    """Returns connected & configured status for Google Meet, Zoom, and Microsoft Teams."""
    def get(self, request):
        from .zoom_services import ZoomOAuthService, get_zoom_credentials, has_zoom_recording_scope
        from .microsoft_services import MicrosoftOAuthService, get_microsoft_credentials

        g_conf = GoogleOAuthService.is_configured()
        g_creds = get_calendar_credentials(request.user)

        z_conf = ZoomOAuthService.is_configured()
        z_creds = get_zoom_credentials(request.user)
        z_has_rec = has_zoom_recording_scope(z_creds.scopes) if z_creds else False

        ms_conf = MicrosoftOAuthService.is_configured()
        ms_creds = get_microsoft_credentials(request.user)

        return Response({
            'google_meet': {
                'is_connected': bool(g_creds),
                'is_configured': g_conf,
                'email': g_creds.email if g_creds else '',
            },
            'zoom': {
                'is_connected': bool(z_creds),
                'is_configured': z_conf,
                'email': z_creds.email if z_creds else '',
                'has_recording_scope': z_has_rec,
                'needs_reconnect_for_transcriptions': bool(z_creds) and not z_has_rec,
            },
            'ms_teams': {
                'is_connected': bool(ms_creds),
                'is_configured': ms_conf,
                'email': ms_creds.email if ms_creds else '',
            },
        }, status=status.HTTP_200_OK)



def _crm_meetings_as_events(user, existing_ids=None, existing_links=None, time_min=None, time_max=None):
    """
    Serialize accessible CRM Meeting records (e.g. WhatsApp-scheduled Google Meet or Zoom
    meetings) into CalendarEventsView event dictionaries, skipping any already represented
    in Google Calendar so they appear cleanly without duplicates.
    """
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    from django.db.models import Q
    from django.utils.dateparse import parse_datetime
    from prospects.models import Meeting

    existing_ids = set(existing_ids or ())
    existing_links = set(existing_links or ())

    qs = Meeting.objects.select_related('prospect', 'prospect_contact', 'created_by').filter(is_completed=False)
    role = getattr(getattr(user, 'profile', None), 'role', None)
    if not user.is_superuser and role in ('PRE', 'LQ'):
        qs = qs.filter(
            Q(created_by=user)
            | Q(google_calendar_owner=user)
            | Q(prospect__created_by=user.username)
            | Q(prospect__lead_qualification__assigned_lq=user)
        )

    if time_min:
        dt_min = parse_datetime(time_min)
        if dt_min:
            qs = qs.filter(scheduled_datetime__gte=dt_min)
    if time_max:
        dt_max = parse_datetime(time_max)
        if dt_max:
            qs = qs.filter(scheduled_datetime__lte=dt_max)

    added = []
    for m in qs.order_by('scheduled_datetime'):
        if m.google_event_id and m.google_event_id in existing_ids:
            continue
        if m.meeting_link and m.meeting_link in existing_links:
            continue

        try:
            tz = ZoneInfo(m.timezone or 'UTC')
        except Exception:
            tz = ZoneInfo('UTC')
        start_local = m.scheduled_datetime.astimezone(tz)
        end_local = start_local + timedelta(minutes=30)

        company = m.prospect.company_name if m.prospect else ''
        contact_name = m.prospect_contact.contact_name if m.prospect_contact else ''
        summary = company or contact_name or 'Scheduled Meeting'
        if m.meeting_provider == 'ZOOM' and 'zoom' not in summary.lower():
            summary = f"{summary} (Zoom)"

        attendees = []
        if m.prospect_contact and m.prospect_contact.official_email:
            attendees.append({'email': m.prospect_contact.official_email})

        added.append({
            'id': m.google_event_id or m.calendar_event_id or f"crm_meeting_{m.id}",
            'meeting_id': m.id,
            'summary': summary,
            'description': m.agenda or '',
            'start': start_local.isoformat(),
            'end': end_local.isoformat(),
            'meet_url': m.meeting_link or '',
            'html_link': m.meeting_link or '',
            'meeting_provider': m.meeting_provider,
            'timezone': m.timezone or 'UTC',
            'company_name': company,
            'contact_name': contact_name,
            'attendees': attendees,
            'recording_file': m.recording_file.url if m.recording_file else None,
            'recording_status': m.recording_status,
        })
    return added


class CalendarEventsView(_CalendarBase):
    """
    Fetch events directly from Google Calendar primary calendar for the authenticated user,
    merged with any CRM-scheduled meetings (Zoom, WhatsApp Meet/Zoom).
    """
    def get(self, request):
        time_min = request.query_params.get('time_min')
        time_max = request.query_params.get('time_max')
        creds = get_calendar_credentials(request.user)
        if not creds:
            crm_events = _crm_meetings_as_events(
                request.user,
                time_min=time_min,
                time_max=time_max,
            )
            return Response({
                "is_connected": False,
                "email": None,
                "events": crm_events,
                "detail": "Google Calendar is not connected."
            }, status=status.HTTP_200_OK)

        try:
            events = list_events(creds, time_min=time_min, time_max=time_max)
            # Annotate events with Market Intel DB Meeting recording information
            from django.db.models import Q
            from prospects.models import Meeting
            meet_urls = [e['meet_url'] for e in events if e.get('meet_url')]
            event_ids = [e['id'] for e in events if e.get('id')]
            meeting_scope = Meeting.objects.filter(
                Q(created_by=request.user) | Q(google_calendar_owner=request.user)
            )
            if request.user.is_superuser:
                meeting_scope = Meeting.objects.all()
            meetings_by_link = {m.meeting_link: m for m in meeting_scope.filter(meeting_link__in=meet_urls)}
            meetings_by_event = {m.google_event_id: m for m in meeting_scope.filter(google_event_id__in=event_ids)}
            from .models import CalendarEventRecording, MeetingAutomationJob
            standalone_by_event = {
                r.event_id: r for r in CalendarEventRecording.objects.filter(user=request.user, event_id__in=event_ids)
            }
            jobs_by_event = {
                j.external_event_id: j
                for j in MeetingAutomationJob.objects.filter(user=request.user, external_event_id__in=event_ids).order_by('created_at')
            }
            jobs_by_link = {
                j.meeting_link: j
                for j in MeetingAutomationJob.objects.filter(user=request.user, meeting_link__in=meet_urls).order_by('created_at')
            }

            for e in events:
                m = meetings_by_event.get(e.get('id')) or meetings_by_link.get(e.get('meet_url'))
                if not (m and m.recording_file):
                    standalone = standalone_by_event.get(e.get('id'))
                    if standalone:
                        m = standalone
                job = jobs_by_event.get(e.get('id')) or jobs_by_link.get(e.get('meet_url'))
                if m:
                    if isinstance(m, Meeting):
                        e['meeting_id'] = m.id
                    e['recording_file'] = m.recording_file.url if m.recording_file else None
                    e['recording_status'] = m.recording_status
                    e['recording_file_size'] = m.recording_file_size
                    e['recording_downloaded_at'] = m.recording_downloaded_at.isoformat() if m.recording_downloaded_at else None
                    e['transcription_status'] = getattr(m, 'transcription_status', 'NONE') or 'NONE'
                    e['transcription_backend'] = getattr(m, 'transcription_backend', '') or ''
                    e['transcript_text'] = getattr(m, 'transcript_text', '') or ''
                    e['speaker_segments'] = getattr(m, 'speaker_segments', []) or []
                    e['transcript_segments'] = getattr(m, 'transcript_segments', []) or []
                if job:
                    e['automation_job_id'] = str(job.id)
                    e['automation_status'] = job.status
                    e['cbe_job_id'] = job.cbe_job_id
                    if job.transcript_text and not e.get('transcript_text'):
                        e['transcript_text'] = job.transcript_text
                        e['transcription_status'] = 'COMPLETED'
                        e['speaker_segments'] = job.speaker_segments or []
                        e['transcript_segments'] = job.transcript_segments or []

            extra_crm = _crm_meetings_as_events(
                request.user,
                existing_ids=event_ids,
                existing_links=meet_urls,
                time_min=time_min,
                time_max=time_max,
            )
            if extra_crm:
                events.extend(extra_crm)
                events.sort(key=lambda ev: str(ev.get('start') or ''))

            return Response({
                "is_connected": True,
                "email": creds.email,
                "events": events,
            }, status=status.HTTP_200_OK)
        except CalendarAuthError as exc:
            return Response({
                "is_connected": False,
                "email": creds.email,
                "events": [],
                "detail": str(exc),
                "reauth_required": True,
            }, status=status.HTTP_200_OK)
        except CalendarError as exc:
            return Response({
                "is_connected": True,
                "email": creds.email,
                "events": [],
                "error": str(exc),
            }, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response({
                "is_connected": True,
                "email": creds.email,
                "events": [],
                "error": str(exc),
            }, status=status.HTTP_200_OK)

    def post(self, request):
        """Create a calendar event with genuine Google Meet, Zoom, or no online meeting."""
        from django.core.cache import cache
        from django.utils import timezone as dj_tz
        from django.utils.dateparse import parse_datetime
        from .models import CalendarEventRecording
        from .zoom_services import (
            ZoomError,
            create_zoom_meeting,
            delete_zoom_meeting,
            get_zoom_credentials,
        )
        from transcriptions.models import MeetingTranscription
        from transcriptions.services import create_or_update_pending_transcription

        summary = (request.data.get('summary') or '').strip() or 'New Event'
        description = (request.data.get('description') or '').strip()
        start = request.data.get('start')
        end = request.data.get('end')
        meet_url = (request.data.get('meet_url') or '').strip()
        attendees = request.data.get('attendees') or []
        color_id = request.data.get('color_id')
        client_request_id = str(request.data.get('client_request_id') or '').strip()[:120]

        profile = getattr(request.user, 'profile', None)
        tz_name = (
            (request.data.get('timezone') or '').strip()
            or getattr(profile, 'timezone', '')
            or 'UTC'
        )

        # Normalize meeting_provider while remaining backward compatible with legacy meet_url callers
        raw_provider = str(request.data.get('meeting_provider') or '').strip().upper()
        if raw_provider in ('GOOGLE_MEET', 'MEET', 'GOOGLE'):
            meeting_provider = 'GOOGLE_MEET'
        elif raw_provider == 'ZOOM':
            meeting_provider = 'ZOOM'
        elif raw_provider in ('NONE', 'NO_MEETING', 'MANUAL'):
            meeting_provider = 'NONE'
        elif meet_url and 'meet.google.com' in meet_url.lower():
            meeting_provider = 'GOOGLE_MEET'
        else:
            meeting_provider = 'NONE'

        if not start or not end:
            return Response(
                {'error': 'Start and end times are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_dt = parse_datetime(str(start)) if 'T' in str(start) else None
        end_dt = parse_datetime(str(end)) if 'T' in str(end) else None
        if start_dt and not dj_tz.is_aware(start_dt):
            start_dt = dj_tz.make_aware(start_dt, dj_tz.utc)
        if end_dt and not dj_tz.is_aware(end_dt):
            end_dt = dj_tz.make_aware(end_dt, dj_tz.utc)
        if start_dt and end_dt and end_dt <= start_dt:
            return Response(
                {'error': 'End time must be after start time.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Idempotency guard for rapid double-clicks / retries
        idemp_cache_key = None
        if client_request_id:
            idemp_cache_key = f'calendar-event-create:{request.user.id}:{client_request_id}'
            cached_payload = cache.get(idemp_cache_key)
            if cached_payload:
                return Response(cached_payload, status=status.HTTP_200_OK)

        # Clean attendees list
        clean_att_emails = []
        clean_att_objects = []
        for a in attendees:
            if isinstance(a, str) and a.strip():
                clean_att_emails.append(a.strip())
                clean_att_objects.append({'email': a.strip()})
            elif isinstance(a, dict) and a.get('email'):
                email_str = str(a['email']).strip()
                if email_str:
                    clean_att_emails.append(email_str)
                    clean_att_objects.append({'email': email_str})

        # Google Calendar connection is required for calendar schedule creation
        creds = get_calendar_credentials(request.user)
        if not creds:
            return Response({
                'error': 'Google Calendar is not connected for your account. Please connect Google Calendar first.',
                'code': 'calendar_not_connected',
            }, status=status.HTTP_409_CONFLICT)

        # ── GOOGLE MEET ───────────────────────────────────────────────────
        if meeting_provider == 'GOOGLE_MEET':
            if not start_dt or not end_dt:
                return Response(
                    {'error': 'Valid ISO start and end datetimes are required for Google Meet events.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            duration_minutes = max(5, int((end_dt - start_dt).total_seconds() // 60))
            req_id = f'cal-{client_request_id}' if client_request_id else f'cal-{uuid.uuid4().hex}'
            try:
                created_meet = create_meet_event(
                    creds,
                    summary=summary,
                    description=description,
                    start_dt=start_dt,
                    tz_name=tz_name,
                    attendees=clean_att_emails,
                    request_id=req_id,
                    duration_minutes=duration_minutes,
                )
            except (CalendarAuthError, CalendarError) as exc:
                return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as exc:
                return Response({'error': f'Failed to create Google Meet event: {exc}'}, status=status.HTTP_400_BAD_REQUEST)

            real_meet_url = created_meet.get('meet_url') or ''
            google_event_id = created_meet.get('google_event_id') or ''
            if not real_meet_url:
                return Response(
                    {'error': 'Google Calendar created the event, but did not return a Google Meet link.'},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            # Register CalendarEventRecording + pending MeetingTranscription for CBE
            cal_rec, _ = CalendarEventRecording.objects.get_or_create(
                user=request.user,
                event_id=google_event_id,
                defaults={
                    'meeting_link': real_meet_url,
                },
            )
            if not cal_rec.meeting_link and real_meet_url:
                cal_rec.meeting_link = real_meet_url
                cal_rec.save(update_fields=['meeting_link', 'updated_at'])
            transcription = create_or_update_pending_transcription(
                user=request.user,
                provider=MeetingTranscription.Provider.GOOGLE_MEET,
                source=MeetingTranscription.Source.CBE,
                title=summary,
                meeting_url=real_meet_url,
                calendar_event_id=google_event_id,
                calendar_recording=cal_rec,
                scheduled_start=start_dt,
                scheduled_end=end_dt,
                status=MeetingTranscription.Status.PENDING,
                status_message='Scheduled Google Meet. Transcript will appear after CBE completes.',
            )

            resp_payload = {
                'success': True,
                'event': {
                    'id': google_event_id,
                    'summary': summary,
                    'description': description,
                    'start': start_dt.isoformat(),
                    'end': end_dt.isoformat(),
                    'meet_url': real_meet_url,
                    'meeting_url': real_meet_url,
                    'meeting_provider': 'GOOGLE_MEET',
                    'provider_meeting_id': '',
                    'html_link': created_meet.get('html_link') or '',
                    'attendees': clean_att_objects,
                    'color_id': color_id,
                    'transcription_id': str(transcription.id),
                },
            }
            if idemp_cache_key:
                cache.set(idemp_cache_key, resp_payload, 600)
            return Response(resp_payload, status=status.HTTP_201_CREATED)

        # ── ZOOM ──────────────────────────────────────────────────────────
        if meeting_provider == 'ZOOM':
            if not start_dt or not end_dt:
                return Response(
                    {'error': 'Valid ISO start and end datetimes are required for Zoom meetings.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            zoom_creds = get_zoom_credentials(request.user)
            if not zoom_creds:
                return Response({
                    'error': 'Zoom is not connected for your account. Please connect Zoom first.',
                    'code': 'zoom_not_connected',
                }, status=status.HTTP_409_CONFLICT)

            duration_minutes = max(5, int((end_dt - start_dt).total_seconds() // 60))
            try:
                zoom_result = create_zoom_meeting(
                    zoom_creds,
                    summary=summary,
                    description=description,
                    start_dt=start_dt,
                    tz_name=tz_name,
                    duration_minutes=duration_minutes,
                    enable_cloud_recording=True,
                )
            except ZoomError as exc:
                return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as exc:
                return Response({'error': f'Failed to create Zoom meeting: {exc}'}, status=status.HTTP_400_BAD_REQUEST)

            zoom_join_url = zoom_result['join_url']
            zoom_meeting_id = zoom_result['meeting_id']
            zoom_password = zoom_result.get('password', '')
            auto_rec_enabled = zoom_result.get('auto_recording_enabled', False)
            auto_rec_warning = zoom_result.get('auto_recording_warning', '')

            zoom_block = f"Join Zoom Meeting: {zoom_join_url}"
            if zoom_meeting_id:
                zoom_block += f"\nMeeting ID: {zoom_meeting_id}"
            if zoom_password:
                zoom_block += f"\nPasscode: {zoom_password}"
            cal_description = f"{description}\n\n{zoom_block}".strip() if description else zoom_block

            body = {
                'summary': summary,
                'description': cal_description,
                'location': zoom_join_url,
                'start': {'dateTime': start_dt.isoformat(), 'timeZone': tz_name},
                'end': {'dateTime': end_dt.isoformat(), 'timeZone': tz_name},
            }
            if color_id:
                body['colorId'] = str(color_id)
            if clean_att_objects:
                body['attendees'] = clean_att_objects

            params = {'sendUpdates': 'all' if clean_att_objects else 'none'}
            try:
                created = _api_request(creds, 'POST', '/calendars/primary/events', body=body, params=params)
            except Exception as exc:
                # Roll back orphaned Zoom meeting so user doesn't end up with dangling Zoom links
                delete_zoom_meeting(zoom_creds, zoom_meeting_id)
                return Response(
                    {'error': f'Zoom meeting was rolled back because Google Calendar sync failed: {exc}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            google_event_id = created.get('id') or ''
            tr_status = (
                MeetingTranscription.Status.PENDING
                if auto_rec_enabled
                else MeetingTranscription.Status.UNAVAILABLE
            )
            tr_msg = (
                'Scheduled Zoom meeting with cloud recording. Transcript will be fetched after the meeting ends.'
                if auto_rec_enabled
                else (auto_rec_warning or 'Cloud recording was not enabled for this Zoom meeting.')
            )
            transcription = create_or_update_pending_transcription(
                user=request.user,
                provider=MeetingTranscription.Provider.ZOOM,
                source=MeetingTranscription.Source.ZOOM_CLOUD_RECORDING,
                title=summary,
                meeting_url=zoom_join_url,
                provider_meeting_id=zoom_meeting_id,
                calendar_event_id=google_event_id,
                scheduled_start=start_dt,
                scheduled_end=end_dt,
                status=tr_status,
                status_message=tr_msg,
                source_metadata={
                    'auto_recording_enabled': auto_rec_enabled,
                    'auto_recording_warning': auto_rec_warning,
                },
            )

            resp_payload = {
                'success': True,
                'event': {
                    'id': google_event_id,
                    'summary': created.get('summary') or summary,
                    'description': created.get('description') or cal_description,
                    'start': created.get('start', {}).get('dateTime') or start_dt.isoformat(),
                    'end': created.get('end', {}).get('dateTime') or end_dt.isoformat(),
                    'meet_url': zoom_join_url,
                    'meeting_url': zoom_join_url,
                    'meeting_provider': 'ZOOM',
                    'provider_meeting_id': zoom_meeting_id,
                    'zoom_password': zoom_password,
                    'auto_recording_enabled': auto_rec_enabled,
                    'auto_recording_warning': auto_rec_warning,
                    'html_link': created.get('htmlLink') or '',
                    'attendees': created.get('attendees', clean_att_objects),
                    'color_id': color_id,
                    'transcription_id': str(transcription.id),
                },
            }
            if idemp_cache_key:
                cache.set(idemp_cache_key, resp_payload, 600)
            return Response(resp_payload, status=status.HTTP_201_CREATED)

        # ── NO ONLINE MEETING (optional manual link) ──────────────────────
        try:
            body = {
                'summary': summary,
                'description': description,
                'start': {'dateTime': start} if 'T' in str(start) else {'date': start},
                'end': {'dateTime': end} if 'T' in str(end) else {'date': end},
            }
            if meet_url:
                body['location'] = meet_url
            if color_id:
                body['colorId'] = str(color_id)
            if clean_att_objects:
                body['attendees'] = clean_att_objects

            params = {'sendUpdates': 'all' if clean_att_objects else 'none'}
            created = _api_request(creds, 'POST', '/calendars/primary/events', body=body, params=params)
            _, extracted_url = extract_conference(created)
            final_url = extracted_url or meet_url
            resp_payload = {
                'success': True,
                'event': {
                    'id': created.get('id'),
                    'summary': created.get('summary'),
                    'description': created.get('description'),
                    'start': created.get('start', {}).get('dateTime') or created.get('start', {}).get('date'),
                    'end': created.get('end', {}).get('dateTime') or created.get('end', {}).get('date'),
                    'meet_url': final_url,
                    'meeting_url': final_url,
                    'meeting_provider': 'NONE',
                    'provider_meeting_id': '',
                    'html_link': created.get('htmlLink'),
                    'attendees': created.get('attendees', []),
                    'color_id': color_id,
                },
            }
            if idemp_cache_key:
                cache.set(idemp_cache_key, resp_payload, 600)
            return Response(resp_payload, status=status.HTTP_201_CREATED)
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request):
        """Delete an event by event_id."""
        event_id = request.query_params.get('event_id') or request.data.get('event_id')
        if not event_id:
            return Response({'error': 'event_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        creds = get_calendar_credentials(request.user)
        if creds and not event_id.startswith('evt_') and not event_id.startswith('mock_') and not event_id.startswith('sample_'):
            try:
                delete_event(creds, event_id)
            except Exception as exc:
                return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'success': True, 'deleted': event_id}, status=status.HTTP_200_OK)


class GoogleCalendarSyncRecordingView(_CalendarBase):
    """Sync Google Meet audio recording for a calendar event or meet URL."""

    def post(self, request):
        from accounts.google_meet_service import GoogleMeetRestService, extract_meeting_code
        from prospects.models import Meeting, Prospect
        from django.utils import timezone

        meeting_id = request.data.get('meeting_id')
        event_id = request.data.get('event_id')
        meet_url = request.data.get('meet_url')

        meeting = None
        if meeting_id:
            meeting = Meeting.objects.filter(id=meeting_id).first()
        if not meeting and event_id:
            meeting = Meeting.objects.filter(google_event_id=event_id).first()
        if not meeting and meet_url:
            code = extract_meeting_code(meet_url)
            if code:
                meeting = Meeting.objects.filter(meeting_link__icontains=code).first()

        if not meeting:
            if not (event_id and meet_url):
                return Response({'error': 'No meeting found for this event or URL.'}, status=status.HTTP_404_NOT_FOUND)
            from .models import CalendarEventRecording
            meeting, _ = CalendarEventRecording.objects.get_or_create(
                user=request.user, event_id=event_id,
                defaults={'meeting_link': meet_url},
            )
            if not meeting.meeting_link:
                meeting.meeting_link = meet_url
                meeting.save(update_fields=['meeting_link', 'updated_at'])
        elif meeting.google_calendar_owner_id not in (None, request.user.id) and meeting.created_by_id != request.user.id \
                and not request.user.is_superuser:
            return Response({'error': 'Only the meeting host can sync this recording.'}, status=status.HTTP_403_FORBIDDEN)

        res = GoogleMeetRestService.sync_meeting_recording(meeting)
        return Response({
            'success': res.get('success', False),
            'status': res.get('status'),
            'recording_url': meeting.recording_file.url if meeting.recording_file else None,
            'meeting_id': meeting.id if isinstance(meeting, Meeting) else None,
            'detail': res.get('detail') or res.get('error'),
            'file_size': meeting.recording_file_size,
        }, status=status.HTTP_200_OK if res.get('success') else (status.HTTP_202_ACCEPTED if res.get('status') == 'PROCESSING' else status.HTTP_200_OK))


class MeetingTriggerWebhookView(APIView):
    """
    POST /api/auth/webhooks/meeting-trigger/
    Receives scheduled meeting details & meeting link when a meeting's start time arrives
    and triggers the Custom Browser Engine (CBE) meeting-processing workflow
    (/v1/meetings with transcription + speaker diarization enabled).
    """
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        import json as _json
        from django.conf import settings as _settings
        from .meeting_automation_service import (
            _get_env,
            trigger_cbe_meeting_processing,
            verify_cbe_hmac_headers,
        )

        raw_body = request.body or b""
        secret = _get_env("CBE_TRIGGER_WEBHOOK_SECRET", "") or _get_env("CBE_HMAC_SECRET", "")
        has_sig = bool(request.headers.get("X-CBE-Signature"))
        if secret or has_sig:
            path_q = request.get_full_path()
            ok, reason = verify_cbe_hmac_headers(
                method=request.method,
                path_with_query=path_q,
                headers=dict(request.headers),
                raw_body=raw_body,
                secret=secret,
            )
            if not ok:
                return Response({"detail": reason}, status=status.HTTP_401_UNAUTHORIZED)
        elif not getattr(_settings, "DEBUG", False):
            return Response({"detail": "Webhook secret not configured."}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            payload = _json.loads(raw_body.decode("utf-8") or "{}")
        except Exception:
            return Response({"detail": "Invalid JSON body."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = trigger_cbe_meeting_processing(payload)
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)


class CBECompletionWebhookView(APIView):
    """
    POST /api/auth/webhooks/cbe/meeting-completed/
    Receives HMAC-SHA256 signed `meeting.completed` webhooks from the Custom Browser
    Engine (`WebhookOutbox`) containing finalized speaker diarization and audio
    transcription, and stores them into Market Intel DB records.
    """
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        import json as _json
        from django.conf import settings as _settings
        from .meeting_automation_service import (
            _get_env,
            ingest_cbe_completed_webhook,
            verify_cbe_hmac_headers,
        )

        raw_body = request.body or b""
        secret = _get_env("CBE_WEBHOOK_SECRET", "") or _get_env("CBE_HMAC_SECRET", "")
        has_sig = bool(request.headers.get("X-CBE-Signature"))
        if secret or has_sig:
            path_q = request.get_full_path()
            ok, reason = verify_cbe_hmac_headers(
                method=request.method,
                path_with_query=path_q,
                headers=dict(request.headers),
                raw_body=raw_body,
                secret=secret,
            )
            if not ok:
                return Response({"detail": reason}, status=status.HTTP_401_UNAUTHORIZED)
        elif not getattr(_settings, "DEBUG", False):
            return Response({"detail": "CBE webhook secret not configured."}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            payload = _json.loads(raw_body.decode("utf-8") or "{}")
        except Exception:
            return Response({"detail": "Invalid JSON payload."}, status=status.HTTP_400_BAD_REQUEST)

        delivery_id = request.headers.get("X-CBE-Delivery-Id", "")
        idem_key = request.headers.get("Idempotency-Key", "")
        result = ingest_cbe_completed_webhook(
            payload,
            delivery_id=delivery_id,
            idempotency_key=idem_key,
        )
        return Response({"status": "ok", **result}, status=status.HTTP_200_OK)


class MeetingAutomationPollView(_CalendarBase):
    """
    POST /api/auth/calendar/automation/poll/
    Trigger dynamic multi-user calendar discovery & due meeting webhook dispatch.
    """

    def post(self, request):
        from .meeting_automation_service import process_due_scheduled_meetings
        res = process_due_scheduled_meetings()
        return Response(res, status=status.HTTP_200_OK)


class MeetingAutomationJobsView(_CalendarBase):
    """
    GET /api/auth/calendar/automation/jobs/
    List discovered/processed MeetingAutomationJob records (own user, or all for Manager/Superuser).
    """

    def get(self, request):
        from .models import MeetingAutomationJob

        qs = MeetingAutomationJob.objects.select_related("user", "meeting", "calendar_recording")
        profile = getattr(request.user, "profile", None)
        is_mgr_or_admin = request.user.is_superuser or (profile and profile.role == "MANAGER")
        if not is_mgr_or_admin:
            qs = qs.filter(user=request.user)
        elif not request.user.is_superuser:
            comp_id = getattr(profile, "company_id", None)
            if comp_id is not None:
                qs = qs.filter(user__profile__company_id=comp_id)

        jobs = list(qs.order_by("-scheduled_start")[:100])
        return Response([
            {
                "id": str(j.id),
                "user_id": j.user_id,
                "username": j.user.username,
                "source_type": j.source_type,
                "external_event_id": j.external_event_id,
                "meeting_id": j.meeting_id,
                "title": j.title,
                "meeting_link": j.meeting_link,
                "platform": j.platform,
                "scheduled_start": j.scheduled_start.isoformat() if j.scheduled_start else None,
                "scheduled_end": j.scheduled_end.isoformat() if j.scheduled_end else None,
                "status": j.status,
                "cbe_job_id": j.cbe_job_id,
                "cbe_meeting_id": j.cbe_meeting_id,
                "transcript_text": j.transcript_text,
                "transcript_segments": j.transcript_segments,
                "speaker_segments": j.speaker_segments,
                "participants": j.participants,
                "last_error": j.last_error,
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            }
            for j in jobs
        ], status=status.HTTP_200_OK)


