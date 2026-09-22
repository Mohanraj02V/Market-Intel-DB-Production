"""
Management command: check_mail_configuration

Diagnoses database, SMTP, and IMAP connectivity without sending email
or exposing credentials.

Usage:
    python manage.py check_mail_configuration

Output:
    DATABASE
    connection = PASS

    SMTP (MailAccount ID=1, username=user@example.com)
    credential_decryption = PASS
    connection = PASS
    starttls = PASS
    authentication = PASS

    IMAP (MailAccount ID=1, username=user@example.com)
    credential_decryption = PASS
    connection = PASS
    authentication = PASS
    inbox_select = PASS
"""

import smtplib
import imaplib
import socket
from django.core.management.base import BaseCommand
from django.db import connection as db_connection


class Command(BaseCommand):
    help = "Diagnose database, SMTP, and IMAP connectivity. Never prints secrets."

    def _result(self, label, passed, detail=""):
        icon = "PASS" if passed else "FAIL"
        line = f"  {label} = {icon}"
        if detail and not passed:
            line += f"  [{detail}]"
        self.stdout.write(line)
        return passed

    def handle(self, *args, **options):
        overall_ok = True

        # ── DATABASE ────────────────────────────────────────────────────────────
        self.stdout.write("\nDATABASE")
        try:
            with db_connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            self._result("connection", True)
        except Exception as exc:
            self._result("connection", False, type(exc).__name__)
            overall_ok = False

        # ── MAIL ACCOUNTS ───────────────────────────────────────────────────────
        try:
            from accounts.models import MailAccount
            import utils.encryption as encryption
        except ImportError as exc:
            self.stdout.write(f"\nFATAL: could not import required modules: {exc}")
            return

        accounts = MailAccount.objects.filter(is_active=True)
        if not accounts.exists():
            self.stdout.write("\nNo active MailAccounts found in database - SMTP/IMAP checks skipped.")
            return

        for account in accounts:
            self.stdout.write(
                f"\n{'-' * 60}\n"
                f"MailAccount ID={account.id}  email={account.email_address}"
            )

            # -- SMTP ----------------------------------------------------------
            self.stdout.write("\nSMTP")
            self.stdout.write(f"  host={account.smtp_host}  port={account.smtp_port}  "
                              f"security={account.smtp_security}  username={account.smtp_username}")

            smtp_password = None
            smtp_ok = True

            # Decryption
            try:
                smtp_password = encryption.decrypt_password(account.smtp_app_password_encrypted)
                decryption_ok = smtp_password is not None and len(smtp_password) > 0
                self._result("credential_decryption", decryption_ok)
                if not decryption_ok:
                    smtp_ok = False
            except Exception as exc:
                self._result("credential_decryption", False, type(exc).__name__)
                smtp_ok = False

            if smtp_ok:
                server = None
                try:
                    # TCP connection
                    if account.smtp_security == 'SSL':
                        server = smtplib.SMTP_SSL(account.smtp_host, account.smtp_port, timeout=15)
                        self._result("connection", True)
                        self._result("starttls", True, "N/A — using SSL directly")
                    else:
                        server = smtplib.SMTP(account.smtp_host, account.smtp_port, timeout=15)
                        self._result("connection", True)
                        # STARTTLS
                        try:
                            server.starttls()
                            self._result("starttls", True)
                        except Exception as exc:
                            self._result("starttls", False, type(exc).__name__)
                            smtp_ok = False

                    if smtp_ok:
                        # Authentication — only login, never send
                        try:
                            server.login(account.smtp_username, smtp_password)
                            self._result("authentication", True)
                        except smtplib.SMTPAuthenticationError:
                            self._result("authentication", False, "SMTPAuthenticationError")
                        except Exception as exc:
                            self._result("authentication", False, type(exc).__name__)

                except (socket.timeout, ConnectionRefusedError, OSError) as exc:
                    self._result("connection", False, type(exc).__name__)
                except Exception as exc:
                    self._result("connection", False, type(exc).__name__)
                finally:
                    if server is not None:
                        try:
                            server.quit()
                        except Exception:
                            pass

            # ── IMAP ──────────────────────────────────────────────────────────
            self.stdout.write("\nIMAP")
            self.stdout.write(f"  host={account.imap_host}  port={account.imap_port}  "
                              f"security={account.imap_security}  username={account.imap_username}")

            imap_password = None
            imap_ok = True

            # Decryption
            try:
                imap_password = encryption.decrypt_password(account.imap_app_password_encrypted)
                decryption_ok = imap_password is not None and len(imap_password) > 0
                self._result("credential_decryption", decryption_ok)
                if not decryption_ok:
                    imap_ok = False
            except Exception as exc:
                self._result("credential_decryption", False, type(exc).__name__)
                imap_ok = False

            if imap_ok:
                mail = None
                try:
                    # SSL connection
                    if account.imap_security == 'SSL':
                        mail = imaplib.IMAP4_SSL(account.imap_host, account.imap_port)
                    else:
                        mail = imaplib.IMAP4(account.imap_host, account.imap_port)
                        mail.starttls()
                    self._result("connection", True)

                    # Authentication
                    try:
                        mail.login(account.imap_username, imap_password)
                        self._result("authentication", True)
                    except imaplib.IMAP4.error as exc:
                        self._result("authentication", False, "IMAP4.error")
                        imap_ok = False
                    except Exception as exc:
                        self._result("authentication", False, type(exc).__name__)
                        imap_ok = False

                    # INBOX select (no download)
                    if imap_ok:
                        try:
                            status_code, _ = mail.select("INBOX")
                            self._result("inbox_select", status_code == "OK",
                                         "" if status_code == "OK" else f"status={status_code}")
                        except Exception as exc:
                            self._result("inbox_select", False, type(exc).__name__)

                except (socket.timeout, ConnectionRefusedError, OSError) as exc:
                    self._result("connection", False, type(exc).__name__)
                except Exception as exc:
                    self._result("connection", False, type(exc).__name__)
                finally:
                    if mail is not None:
                        try:
                            mail.logout()
                        except Exception:
                            pass

        self.stdout.write(f"\n{'-' * 60}")
        self.stdout.write("Diagnostic complete. See PASS/FAIL above.")
        self.stdout.write("Never share this output with secrets visible.")
