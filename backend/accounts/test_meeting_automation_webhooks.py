import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.meeting_automation_service import (
    process_due_scheduled_meetings,
    sign_cbe_headers,
)
from accounts.models import (
    CalendarEventRecording,
    GoogleCalendarCredentials,
    MeetingAutomationJob,
)
from prospects.models import EmailThread, EmailThreadMessage, Meeting, Prospect

User = get_user_model()


class _FakeUrllibResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._raw = json.dumps(payload).encode("utf-8")
        self.status = status_code

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class CustomBrowserEngineWebhookIntegrationTests(APITestCase):
    """
    Verifies end-to-end automated meeting processing across multiple users:
      1. Discovers scheduled meetings across all users' calendars and CRM Meeting records.
      2. Resolves missing meeting links from emails cleanly.
      3. Dispatches due meetings to the configured trigger webhook with canonical HMAC-SHA256.
      4. Trigger webhook invokes CBE POST /v1/meetings with transcription_enabled=True.
      5. Completion webhook verifies CBE canonical HMAC-SHA256 headers and stores
         diarization + transcription back into Meeting, CalendarEventRecording, and
         MeetingAutomationJob records.
    """

    def setUp(self):
        self.user1 = User.objects.create_user(username="host_alice", email="alice@example.com", password="p")
        self.user1.profile.role = "LQ"
        self.user1.profile.save()

        self.user2 = User.objects.create_user(username="host_bob", email="bob@example.com", password="p")
        self.user2.profile.role = "PRE"
        self.user2.profile.save()

        self.gcal1 = GoogleCalendarCredentials.objects.create(
            user=self.user1,
            email="alice@example.com",
            access_token_encrypted="enc-tok-1",
            is_active=True,
        )
        self.gcal2 = GoogleCalendarCredentials.objects.create(
            user=self.user2,
            email="bob@example.com",
            access_token_encrypted="enc-tok-2",
            is_active=True,
        )

        self.prospect = Prospect.objects.create(
            company_name="Acme Robotics",
            created_by=self.user1.username,
        )

    def test_multi_user_calendar_and_email_link_dispatch_to_webhook(self):
        now = timezone.now()
        # Event 1 for user1: Calendar event HAS meet_url and is due right now
        cal_events_user1 = [{
            "id": "gcal_evt_alice_1",
            "summary": "Acme Robotics Demo",
            "description": "Quarterly walkthrough",
            "start": (now + timedelta(seconds=15)).isoformat(),
            "end": (now + timedelta(minutes=30)).isoformat(),
            "meet_url": "https://meet.google.com/abc-defg-hij",
            "attendees": [{"email": "buyer@acmerobotics.com", "name": "Buyer"}],
        }]
        # Event 2 for user2: Calendar event has NO meet_url, so link must come from user2's email
        cal_events_user2 = [{
            "id": "gcal_evt_bob_2",
            "summary": "Bob Sync Call",
            "description": "Join via email link",
            "start": (now + timedelta(seconds=20)).isoformat(),
            "end": (now + timedelta(minutes=30)).isoformat(),
            "meet_url": "",
            "location": "",
            "attendees": [{"email": "client@globex.com", "name": "Client"}],
        }]

        # Email for user2 containing the meeting URL for "Bob Sync Call"
        th_bob = EmailThread.objects.create(
            owner=self.user2,
            correspondent_email="client@globex.com",
            subject="Bob Sync Call - Link Inside",
            last_message_at=now,
            message_count=1,
        )
        EmailThreadMessage.objects.create(
            thread=th_bob,
            owner=self.user2,
            direction=EmailThreadMessage.Direction.INBOUND,
            source=EmailThreadMessage.Source.SYNC,
            status=EmailThreadMessage.Status.RECEIVED,
            dedup_key="bob-email-link-1",
            sender_email="client@globex.com",
            to_emails=["bob@example.com"],
            subject="Bob Sync Call - Link Inside",
            body_text="Please join using https://meet.google.com/xyz-mnop-qrs at scheduled time.",
            sent_at=now - timedelta(hours=1),
        )

        # Future CRM Meeting for user1 (should be discovered as PENDING, NOT dispatched yet)
        future_meeting = Meeting.objects.create(
            prospect=self.prospect,
            created_by=self.user1,
            google_calendar_owner=self.user1,
            scheduled_datetime=now + timedelta(hours=4),
            meeting_link="https://meet.google.com/fut-uree-mtg",
            agenda="Future Executive Review",
        )

        def _fake_list_events(creds, time_min=None, time_max=None, max_results=250):
            return cal_events_user1 if creds.user_id == self.user1.id else cal_events_user2

        captured_requests = []

        def _fake_urlopen(req, timeout=15):
            captured_requests.append({
                "url": req.full_url,
                "headers": dict(req.header_items()),
                "body": json.loads(req.data.decode("utf-8")),
            })
            return _FakeUrllibResponse({"job_id": f"cbe_job_{len(captured_requests)}", "state": "pending"})

        with patch("accounts.calendar_services.list_events", side_effect=_fake_list_events), \
             patch.dict("os.environ", {
                 "MEETING_TRIGGER_WEBHOOK_URL": "https://hooks.local.test/api/auth/webhooks/meeting-trigger/",
                 "CBE_TRIGGER_WEBHOOK_SECRET": "test-trigger-secret",
                 "CBE_SERVICE_ID": "market-intel-db",
                 "CBE_KEY_ID": "k1",
             }), \
             patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            res = process_due_scheduled_meetings(now=now)

        self.assertEqual(res["discovered"], 3)
        self.assertEqual(res["dispatched"], 2)
        self.assertEqual(len(captured_requests), 2)

        # Both Alice (calendar link) and Bob (email-extracted link) dispatched cleanly with X-CBE HMAC headers
        urls_dispatched = {r["body"]["meeting_link"] for r in captured_requests}
        self.assertEqual(
            urls_dispatched,
            {"https://meet.google.com/abc-defg-hij", "https://meet.google.com/xyz-mnop-qrs"},
        )
        for req_info in captured_requests:
            self.assertEqual(req_info["body"]["transcription_enabled"], True)
            self.assertIn("X-cbe-signature", req_info["headers"])

        # Future meeting stays PENDING
        future_job = MeetingAutomationJob.objects.get(meeting=future_meeting)
        self.assertEqual(future_job.status, MeetingAutomationJob.Status.PENDING)

    def test_trigger_webhook_invokes_cbe_and_completion_webhook_stores_diarization_and_transcript(self):
        now = timezone.now()
        meeting = Meeting.objects.create(
            prospect=self.prospect,
            created_by=self.user1,
            google_calendar_owner=self.user1,
            scheduled_datetime=now,
            google_event_id="gcal_evt_trigger_99",
            meeting_link="https://meet.google.com/tri-gger-099",
            agenda="Diarization Integration Test",
        )
        job = MeetingAutomationJob.objects.create(
            user=self.user1,
            meeting=meeting,
            source_type=MeetingAutomationJob.SourceType.MEETING_RECORD,
            external_event_id="gcal_evt_trigger_99",
            idempotency_key="idem-trigger-99",
            title="Diarization Integration Test",
            meeting_link="https://meet.google.com/tri-gger-099",
            platform="GOOGLE_MEET",
            scheduled_start=now,
            status=MeetingAutomationJob.Status.PENDING,
        )

        # 1. Signed trigger webhook POSTs to CBE /v1/meetings with transcription_enabled=True
        trigger_payload = json.dumps({
            "automation_job_id": str(job.id),
            "meeting_link": meeting.meeting_link,
            "title": job.title,
            "scheduled_start_epoch_ms": int(now.timestamp() * 1000),
            "scheduled_end_epoch_ms": int((now + timedelta(minutes=30)).timestamp() * 1000),
        }).encode("utf-8")
        trigger_secret = "shared-trigger-secret"
        trig_headers = sign_cbe_headers(
            method="POST",
            path_with_query="/api/auth/webhooks/meeting-trigger/",
            body_bytes=trigger_payload,
            service_id="market-intel-db",
            key_id="k1",
            secret=trigger_secret,
        )
        meta_trig = {f"HTTP_{k.upper().replace('-', '_')}": v for k, v in trig_headers.items()}

        cbe_calls = []

        def _fake_cbe_urlopen(req, timeout=15):
            cbe_calls.append({"url": req.full_url, "body": json.loads(req.data.decode("utf-8"))})
            return _FakeUrllibResponse({"job_id": "cbe_job_99", "meeting_id": "cbe_mtg_99", "state": "pending"})

        with patch.dict("os.environ", {
            "CBE_TRIGGER_WEBHOOK_SECRET": trigger_secret,
            "CBE_SERVICE_URL": "http://127.0.0.1:8443",
            "CBE_SERVICE_ID": "market-intel-db",
            "CBE_KEY_ID": "k1",
            "CBE_HMAC_SECRET": "cbe-api-secret",
        }), patch("urllib.request.urlopen", side_effect=_fake_cbe_urlopen):
            trig_resp = self.client.post(
                "/api/auth/webhooks/meeting-trigger/",
                data=trigger_payload,
                content_type="application/json",
                **meta_trig,
            )

        self.assertEqual(trig_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(cbe_calls), 1)
        self.assertEqual(cbe_calls[0]["url"], "http://127.0.0.1:8443/v1/meetings")
        self.assertEqual(cbe_calls[0]["body"]["meet_url"], meeting.meeting_link)
        self.assertTrue(cbe_calls[0]["body"]["transcription_enabled"])

        job.refresh_from_db()
        meeting.refresh_from_db()
        self.assertEqual(job.status, MeetingAutomationJob.Status.PROCESSING)
        self.assertEqual(job.cbe_job_id, "cbe_job_99")
        self.assertEqual(meeting.transcription_status, "PROCESSING")

        # 2. Completion webhook rejects bad/missing signature and stores completed transcript + diarization on valid HMAC
        cbe_completed_body = json.dumps({
            "schema_version": "1.0",
            "event_type": "meeting.completed",
            "delivery_id": "deliv_99",
            "idempotency_key": "idem-trigger-99",
            "meeting": {
                "meeting_id": "cbe_mtg_99",
                "session_id": "sess_99",
                "meeting_url": meeting.meeting_link,
                "calendar_event_id": "gcal_evt_trigger_99",
                "platform": "google_meet",
            },
            "recording": {
                "recording_id": "rec_99",
                "status": "finalized",
                "duration_ms": 120000,
                "output_wav_path": "/tmp/recordings/rec_99/audio.wav",
            },
            "participants": [
                {"participant_id": "p1", "display_name": "Alice Host", "is_self": True},
                {"participant_id": "p2", "display_name": "Bob Prospect", "is_self": False},
            ],
            "speaker_segments": [
                {"participant_id": "p1", "speaker_name": "Alice Host", "start_ms": 0, "end_ms": 5000},
                {"participant_id": "p2", "speaker_name": "Bob Prospect", "start_ms": 5100, "end_ms": 12000},
            ],
            "transcription": {
                "enabled": True,
                "status": "completed",
                "backend_used": "gemini",
                "utterance_count": 2,
                "segments": [
                    {"speaker_name": "Alice Host", "start_ms": 0, "end_ms": 5000, "text": "Welcome to the Acme demo."},
                    {"speaker_name": "Bob Prospect", "start_ms": 5100, "end_ms": 12000, "text": "Thanks, excited to see the pricing."},
                ],
            },
        }).encode("utf-8")

        comp_secret = "cbe-outbound-webhook-secret"
        with patch.dict("os.environ", {"CBE_WEBHOOK_SECRET": comp_secret}):
            bad_resp = self.client.post(
                "/api/auth/webhooks/cbe/meeting-completed/",
                data=cbe_completed_body,
                content_type="application/json",
            )
            self.assertEqual(bad_resp.status_code, status.HTTP_401_UNAUTHORIZED)

            comp_headers = sign_cbe_headers(
                method="POST",
                path_with_query="/api/auth/webhooks/cbe/meeting-completed/",
                body_bytes=cbe_completed_body,
                service_id="market-intel-db",
                key_id="k1",
                secret=comp_secret,
            )
            meta_comp = {f"HTTP_{k.upper().replace('-', '_')}": v for k, v in comp_headers.items()}
            meta_comp["HTTP_X_CBE_DELIVERY_ID"] = "deliv_99"
            meta_comp["HTTP_IDEMPOTENCY_KEY"] = "idem-trigger-99"

            ok_resp = self.client.post(
                "/api/auth/webhooks/cbe/meeting-completed/",
                data=cbe_completed_body,
                content_type="application/json",
                **meta_comp,
            )

        self.assertEqual(ok_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(ok_resp.data["transcription_status"], "COMPLETED")
        self.assertEqual(ok_resp.data["utterance_count"], 2)

        meeting.refresh_from_db()
        job.refresh_from_db()
        self.assertTrue(meeting.is_completed)
        self.assertEqual(meeting.status, "COMPLETED")
        self.assertEqual(meeting.transcription_status, "COMPLETED")
        self.assertEqual(meeting.transcription_backend, "gemini")
        self.assertIn("[00:00:00] Alice Host: Welcome to the Acme demo.", meeting.transcript_text)
        self.assertIn("[00:00:05] Bob Prospect: Thanks, excited to see the pricing.", meeting.transcript_text)
        self.assertEqual(len(meeting.speaker_segments), 2)
        self.assertEqual(len(meeting.diarization_participants), 2)
        self.assertEqual(job.status, MeetingAutomationJob.Status.COMPLETED)
        self.assertEqual(job.cbe_delivery_id, "deliv_99")

        # Also verifies calendar-only event without a CRM Meeting stores transcript into CalendarEventRecording
        cal_only_body = json.dumps({
            "event_type": "meeting.completed",
            "delivery_id": "deliv_cal_only",
            "idempotency_key": "idem-cal-only",
            "meeting": {
                "meeting_id": "cbe_cal_22",
                "meeting_url": "https://meet.google.com/cal-only-022",
                "calendar_event_id": "gcal_evt_bob_2",
            },
            "recording": {"recording_id": "rec_cal_22", "status": "finalized"},
            "participants": [{"participant_id": "p1", "display_name": "Bob"}],
            "speaker_segments": [{"speaker_name": "Bob", "start_ms": 0, "end_ms": 3000}],
            "transcription": {
                "enabled": True,
                "status": "completed",
                "backend_used": "local-whisper",
                "segments": [{"speaker_name": "Bob", "start_ms": 0, "end_ms": 3000, "text": "Calendar only summary."}],
            },
        }).encode("utf-8")
        MeetingAutomationJob.objects.create(
            user=self.user2,
            source_type=MeetingAutomationJob.SourceType.GOOGLE_CALENDAR,
            external_event_id="gcal_evt_bob_2",
            idempotency_key="idem-cal-only",
            title="Bob Sync Call",
            meeting_link="https://meet.google.com/cal-only-022",
            scheduled_start=now,
        )
        comp_headers_2 = sign_cbe_headers(
            method="POST",
            path_with_query="/api/auth/webhooks/cbe/meeting-completed/",
            body_bytes=cal_only_body,
            service_id="market-intel-db",
            key_id="k1",
            secret=comp_secret,
        )
        meta_comp_2 = {f"HTTP_{k.upper().replace('-', '_')}": v for k, v in comp_headers_2.items()}
        with patch.dict("os.environ", {"CBE_WEBHOOK_SECRET": comp_secret}):
            resp2 = self.client.post(
                "/api/auth/webhooks/cbe/meeting-completed/",
                data=cal_only_body,
                content_type="application/json",
                **meta_comp_2,
            )
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        cal_rec = CalendarEventRecording.objects.get(user=self.user2, event_id="gcal_evt_bob_2")
        self.assertEqual(cal_rec.transcription_status, "COMPLETED")
        self.assertIn("Calendar only summary.", cal_rec.transcript_text)

        # Management command sanity check
        with patch("accounts.calendar_services.list_events", return_value=[]):
            call_command("process_scheduled_meetings", "--once")
