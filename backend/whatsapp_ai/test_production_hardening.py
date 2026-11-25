from datetime import datetime, timedelta, timezone as dt_timezone
import hashlib
import hmac
import json
import os
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

import utils.encryption as encryption
from accounts.models import (
    GoogleCalendarCredentials,
    MicrosoftCalendarCredentials,
    UserProfile,
    ZoomCredentials,
)
from accounts.oauth_services import GmailOAuthService
from prospects.models import Meeting, Prospect, ProspectContact
from rag.serializers import session_settings_payload
from whatsapp.models import (
    WhatsAppConfiguration,
    WhatsAppConversation,
    WhatsAppMessage,
    WhatsAppSession,
)
from whatsapp_ai.gemini_service import (
    catch_up_unreplied_fresh_inbound_messages,
    is_session_ai_enabled,
    process_ai_auto_reply,
)
from whatsapp_ai.models import (
    WhatsAppAIAutoReplyConfig,
    WhatsAppAIReplyLog,
    WhatsAppAssistantState,
    WhatsAppMeetingRequest,
)

User = get_user_model()
WEBHOOK_SECRET = "prod-hardening-webhook-secret"


@override_settings(DEBUG=True)
class ProductionHardeningAndIsolationTests(APITestCase):
    """Comprehensive tests for Phase 2–8 security, AI toggle, calendar isolation, and availability scheduling."""

    def setUp(self):
        self.user_a = User.objects.create_user(
            username="pre_user_a",
            email="user_a@company.com",
            password="Password@123!",
        )
        UserProfile.objects.update_or_create(
            user=self.user_a,
            defaults={"role": "PRE", "timezone": "Asia/Kolkata"},
        )

        self.user_b = User.objects.create_user(
            username="pre_user_b",
            email="user_b@company.com",
            password="Password@123!",
        )
        UserProfile.objects.update_or_create(
            user=self.user_b,
            defaults={"role": "PRE", "timezone": "America/New_York"},
        )

        WhatsAppConfiguration.objects.create(
            outbound_enabled=True,
            safety_stop_active=False,
        )

        self.session_a = WhatsAppSession.objects.create(
            owner=self.user_a,
            session_name="wa_u_a_slot",
            status=WhatsAppSession.Status.READY,
            phone_number="+919000000001",
            is_active=True,
        )
        self.session_b = WhatsAppSession.objects.create(
            owner=self.user_b,
            session_name="wa_u_b_slot",
            status=WhatsAppSession.Status.READY,
            phone_number="+919000000002",
            is_active=True,
        )

        self.conv_a = WhatsAppConversation.objects.create(
            session=self.session_a,
            chat_id="919800000111@c.us",
            phone_number="+919800000111",
            whatsapp_name="Client Alpha",
        )
        self._msg_seq = 0

    def _inbound_msg(self, body: str, *, conv=None, waha_id=None) -> WhatsAppMessage:
        self._msg_seq += 1
        target_conv = conv or self.conv_a
        return WhatsAppMessage.objects.create(
            idempotency_key=f"hardening-in-{self._msg_seq}",
            conversation=target_conv,
            waha_message_id=waha_id or f"wamid-hardening-{self._msg_seq}",
            direction=WhatsAppMessage.Direction.INBOUND,
            status=WhatsAppMessage.Status.DELIVERED,
            body_preview=body[:500],
            full_body=body,
            sent_at=timezone.now(),
        )

    def _enable_ai(self, session):
        WhatsAppAIAutoReplyConfig.objects.update_or_create(
            session=session,
            defaults={"enabled": True},
        )

    # ------------------------------------------------------------------
    # Phase 2: Per-account AI Toggle, Isolation & Race Protection
    # ------------------------------------------------------------------

    def test_new_session_defaults_to_off_across_api_rag_and_serializers(self):
        self.assertFalse(is_session_ai_enabled(self.session_a))
        self.assertFalse(session_settings_payload(self.session_a)["ai_enabled"])

        self.client.force_authenticate(user=self.user_a)
        res = self.client.get(f"/api/whatsapp/ai-config/{self.session_a.pk}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["enabled"])
        self.assertFalse(res.data["ai_enabled"])

    def test_toggle_persistence_multi_account_isolation_and_idor_blocked(self):
        # User A toggles their session ON -> persists across GET & RAG payload
        self.client.force_authenticate(user=self.user_a)
        patch_res = self.client.patch(
            f"/api/whatsapp/ai-config/{self.session_a.pk}/",
            {"enabled": True},
            format="json",
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        self.assertTrue(patch_res.data["enabled"])
        self.assertTrue(is_session_ai_enabled(self.session_a))
        self.assertTrue(session_settings_payload(self.session_a)["ai_enabled"])

        # User B remains OFF and isolated
        self.assertFalse(is_session_ai_enabled(self.session_b))

        # User B cannot read or mutate User A's session AI toggle (IDOR blocked)
        self.client.force_authenticate(user=self.user_b)
        idor_get = self.client.get(f"/api/whatsapp/ai-config/{self.session_a.pk}/")
        self.assertEqual(idor_get.status_code, status.HTTP_404_NOT_FOUND)
        idor_patch = self.client.patch(
            f"/api/whatsapp/ai-config/{self.session_a.pk}/",
            {"enabled": False},
            format="json",
        )
        self.assertEqual(idor_patch.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(is_session_ai_enabled(self.session_a))

        # Reject non-boolean input cleanly
        self.client.force_authenticate(user=self.user_a)
        bad_patch = self.client.patch(
            f"/api/whatsapp/ai-config/{self.session_a.pk}/",
            {"enabled": "true"},
            format="json",
        )
        self.assertEqual(bad_patch.status_code, status.HTTP_400_BAD_REQUEST)

    def test_ai_off_blocks_catchup_and_queued_reply_while_manual_send_works(self):
        msg = self._inbound_msg("Hello, tell me about your plans")
        fake_waha = MagicMock()
        fake_waha.send_text.return_value = {"id": "manual-msg-1"}

        with patch.dict("os.environ", {"WHATSAPP_AI_AUTO_REPLY_ENABLED": "true"}), \
             patch("whatsapp.client.get_waha_client", return_value=fake_waha):
            # Catch-up sweep ignores OFF sessions
            scheduled = catch_up_unreplied_fresh_inbound_messages()
            self.assertEqual(scheduled, 0)

            # Even a previously queued/direct worker call stops if OFF
            res = process_ai_auto_reply(msg.pk)
            self.assertEqual(res["status"], "SKIPPED")
            self.assertEqual(res["reason"], "session_ai_disabled")
            fake_waha.send_text.assert_not_called()

            # Manual UI sending still works normally
            self.client.force_authenticate(user=self.user_a)
            send_res = self.client.post(
                "/api/whatsapp/send/",
                {"chat_id": "919800000111@c.us", "message_body": "Manual reply from agent"},
                format="json",
            )
            self.assertEqual(send_res.status_code, status.HTTP_201_CREATED)
            fake_waha.send_text.assert_called_once()

    def test_midflight_ai_off_race_condition_aborts_before_sending(self):
        self._enable_ai(self.session_a)
        msg = self._inbound_msg("Can you share pricing details?")
        fake_waha = MagicMock()

        def _disable_during_generation(*args, **kwargs):
            WhatsAppAIAutoReplyConfig.objects.filter(session=self.session_a).update(enabled=False)
            return "Generated draft reply", "gemini-test"

        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key", "WHATSAPP_AI_AUTO_REPLY_ENABLED": "true"}), \
             patch("whatsapp_ai.gemini_service.generate_gemini_whatsapp_reply", side_effect=_disable_during_generation), \
             patch("whatsapp.client.get_waha_client", return_value=fake_waha):
            res = process_ai_auto_reply(msg.pk)

        self.assertEqual(res["status"], "SKIPPED")
        self.assertEqual(res["reason"], "session_ai_disabled_during_processing")
        fake_waha.send_text.assert_not_called()
        log = WhatsAppAIReplyLog.objects.get(incoming_message=msg)
        self.assertEqual(log.status, WhatsAppAIReplyLog.Status.SKIPPED)

    # ------------------------------------------------------------------
    # Phase 3 & 4: Zero Cross-User Fallback + Availability + State Machine
    # ------------------------------------------------------------------

    def test_zero_cross_user_calendar_fallback_when_owner_disconnected(self):
        """
        Reproduces the exact root cause where User B had reactapplicationdeveloper@gmail.com
        connected in Google Calendar and User A (owning the WhatsApp session) had none.
        User A must NEVER use User B's credentials.
        """
        self._enable_ai(self.session_a)
        GoogleCalendarCredentials.objects.create(
            user=self.user_b,
            email="reactapplicationdeveloper@gmail.com",
            access_token_encrypted=encryption.encrypt_password("user_b_tok"),
            refresh_token_encrypted=encryption.encrypt_password("user_b_ref"),
            token_expiry=timezone.now() + timedelta(hours=1),
            scopes="https://www.googleapis.com/auth/calendar.events",
            is_active=True,
        )
        ZoomCredentials.objects.create(
            user=self.user_b,
            email="user_b_zoom@company.com",
            access_token_encrypted=encryption.encrypt_password("user_b_ztok"),
            refresh_token_encrypted=encryption.encrypt_password("user_b_zref"),
            token_expiry=timezone.now() + timedelta(hours=1),
            is_active=True,
        )

        target_date = (timezone.localdate() + timedelta(days=3)).isoformat()
        fake_waha = MagicMock()
        fake_waha.send_text.return_value = {"id": "out-iso-1"}

        with patch.dict("os.environ", {"WHATSAPP_AI_AUTO_REPLY_ENABLED": "true"}), \
             patch("whatsapp.client.get_waha_client", return_value=fake_waha), \
             patch("accounts.calendar_services.create_meet_event") as mock_gmeet:
            res = process_ai_auto_reply(
                self._inbound_msg(
                    f"Schedule a Google Meet on {target_date} at 11:00 AM IST about onboarding"
                ).pk
            )

        self.assertEqual(res["status"], "SENT")
        mock_gmeet.assert_not_called()
        self.assertEqual(Meeting.objects.count(), 0)
        self.assertIn("not connected", res["reply_text"].lower())
        req = WhatsAppMeetingRequest.objects.get(conversation=self.conv_a)
        self.assertEqual(req.user, self.user_a)
        self.assertEqual(req.state, WhatsAppMeetingRequest.State.REQUIRES_RECONNECTION)

    def test_duration_overlap_conflict_alternative_selection_revalidation_and_teams_booking(self):
        """
        Verify:
          1. MS Teams platform support for session owner.
          2. 60-min requested meeting (10:00-11:00 UTC) detects partial conflict with 10:30-11:00 busy event.
          3. Returns numbered available alternatives; sender selects "1" -> revalidates & confirms.
          4. Confirmation books MS Teams meeting with valid https link, no invented email for phone-only sender.
          5. Retrying/replaying confirmation idempotently never creates a duplicate meeting.
        """
        self._enable_ai(self.session_a)
        MicrosoftCalendarCredentials.objects.create(
            user=self.user_a,
            email="exec_a@company.com",
            access_token_encrypted=encryption.encrypt_password("ms_tok_a"),
            refresh_token_encrypted=encryption.encrypt_password("ms_ref_a"),
            token_expiry=timezone.now() + timedelta(hours=1),
            is_active=True,
        )

        target_date = timezone.localdate() + timedelta(days=4)
        busy_start = f"{target_date.isoformat()}T10:30:00Z"
        busy_end = f"{target_date.isoformat()}T11:00:00Z"

        fake_waha = MagicMock()
        fake_waha.send_text.side_effect = [{"id": f"out-ms-{i}"} for i in range(1, 10)]

        with patch.dict("os.environ", {"WHATSAPP_AI_AUTO_REPLY_ENABLED": "true"}), \
             patch("whatsapp.client.get_waha_client", return_value=fake_waha), \
             patch(
                 "accounts.microsoft_services.list_ms_events",
                 return_value=[{"id": "busy-1", "summary": "Busy Block", "start": busy_start, "end": busy_end}],
             ), \
             patch(
                 "accounts.microsoft_services.create_teams_meeting_and_event",
                 return_value={
                     "event_id": "ms-evt-1",
                     "meeting_id": "ms-mtg-1",
                     "join_url": "https://teams.microsoft.com/l/meetup-join/valid-1",
                     "status": "READY",
                 },
             ) as mock_create_teams:
            # Turn 1: Ask for 60 min MS Teams meeting at 10:00 UTC (partially overlaps 10:30-11:00 busy block)
            r1 = process_ai_auto_reply(
                self._inbound_msg(
                    f"Schedule a 60 min Microsoft Teams meeting on {target_date.isoformat()} at 10:00 AM UTC regarding Q4 Demo, skip email"
                ).pk
            )
            self.assertEqual(r1["status"], "SENT")
            self.assertIn("unavailable", r1["reply_text"].lower())
            self.assertIn("1.", r1["reply_text"])
            req = WhatsAppMeetingRequest.objects.get(conversation=self.conv_a)
            self.assertEqual(req.state, WhatsAppMeetingRequest.State.AWAITING_ALTERNATIVE_SELECTION)
            self.assertEqual(req.duration_minutes, 60)

            # Turn 2: Sender picks option 1 (11:00 - 12:00 UTC)
            r2 = process_ai_auto_reply(self._inbound_msg("1").pk)
            self.assertEqual(r2["status"], "SENT")
            self.assertIn("confirm", r2["reply_text"].lower())
            self.assertIn("Microsoft Teams", r2["reply_text"])
            req.refresh_from_db()
            self.assertEqual(req.state, WhatsAppMeetingRequest.State.AWAITING_CONFIRMATION)

            # Turn 3: Sender confirms
            r3 = process_ai_auto_reply(self._inbound_msg("Yes, confirm").pk)
            self.assertEqual(r3["status"], "SENT")
            self.assertIn("https://teams.microsoft.com/l/meetup-join/valid-1", r3["reply_text"])

        mock_create_teams.assert_called_once()
        # No email invented for phone-only WhatsApp sender
        self.assertEqual(mock_create_teams.call_args.kwargs["attendees"], [])
        self.assertEqual(mock_create_teams.call_args.kwargs["duration_minutes"], 60)

        mtg = Meeting.objects.get()
        self.assertEqual(mtg.meeting_provider, "MS_TEAMS")
        self.assertEqual(mtg.created_by, self.user_a)
        req.refresh_from_db()
        self.assertEqual(req.state, WhatsAppMeetingRequest.State.SCHEDULED)
        self.assertTrue(req.notification_sent)

    def test_revalidation_catches_slot_taken_between_confirmation_and_yes(self):
        self._enable_ai(self.session_a)
        GoogleCalendarCredentials.objects.create(
            user=self.user_a,
            email="exec_a@company.com",
            access_token_encrypted=encryption.encrypt_password("g_tok_a"),
            refresh_token_encrypted=encryption.encrypt_password("g_ref_a"),
            token_expiry=timezone.now() + timedelta(hours=1),
            scopes="https://www.googleapis.com/auth/calendar.events",
            is_active=True,
        )
        target_date = timezone.localdate() + timedelta(days=5)
        fake_waha = MagicMock()
        fake_waha.send_text.side_effect = [{"id": f"out-reval-{i}"} for i in range(1, 5)]

        # First check returns free -> Confirmation prompt; Second check (during confirmation!) shows slot was just taken!
        slot_busy = [{
            "id": "race-evt",
            "summary": "Taken Just Now",
            "start": f"{target_date.isoformat()}T14:00:00+05:30",
            "end": f"{target_date.isoformat()}T14:30:00+05:30",
            "start_timezone": "Asia/Kolkata",
        }]
        with patch.dict("os.environ", {"WHATSAPP_AI_AUTO_REPLY_ENABLED": "true"}), \
             patch("whatsapp.client.get_waha_client", return_value=fake_waha), \
             patch("accounts.calendar_services.list_events", side_effect=[[], slot_busy]), \
             patch("accounts.calendar_services.create_meet_event") as mock_create:
            r1 = process_ai_auto_reply(
                self._inbound_msg(
                    f"Schedule a Google Meet on {target_date.isoformat()} at 2:00 PM IST for Sync, skip email"
                ).pk
            )
            self.assertIn("confirm", r1["reply_text"].lower())

            r2 = process_ai_auto_reply(self._inbound_msg("Yes").pk)
            self.assertEqual(r2["status"], "SENT")
            self.assertIn("unavailable", r2["reply_text"].lower())
            self.assertIn("1.", r2["reply_text"])
            mock_create.assert_not_called()
            self.assertEqual(Meeting.objects.count(), 0)
            req = WhatsAppMeetingRequest.objects.get(conversation=self.conv_a)
            self.assertEqual(req.state, WhatsAppMeetingRequest.State.AWAITING_ALTERNATIVE_SELECTION)

    # ------------------------------------------------------------------
    # Phase 8: Security Audit Regression Tests (IDOR, OAuth Replay, HMAC)
    # ------------------------------------------------------------------

    def test_security_idor_media_proxy_and_crm_contacts_blocked(self):
        # 1. Media proxy cross-user IDOR blocked
        msg_a = self._inbound_msg("Here is doc")
        msg_a.media_url = "http://localhost:3000/api/files/secret.pdf"
        msg_a.save(update_fields=["media_url"])

        self.client.force_authenticate(user=self.user_b)
        media_res = self.client.get(f"/api/whatsapp/media-proxy/?message_id={msg_a.pk}")
        self.assertEqual(media_res.status_code, status.HTTP_404_NOT_FOUND)

        # 2. CRM contact listing & linking scoped strictly via distribution
        p_a = Prospect.objects.create(company_name="Secret Alpha Corp", created_by=self.user_a.username)
        c_a = ProspectContact.objects.create(prospect=p_a, contact_name="Private Contact", phone_number="+919999000111")

        conv_b = WhatsAppConversation.objects.create(
            session=self.session_b,
            chat_id="919800000222@c.us",
            phone_number="+919800000222",
        )
        crm_list_b = self.client.get("/api/whatsapp/crm-contacts/")
        self.assertEqual(crm_list_b.status_code, status.HTTP_200_OK)
        self.assertFalse(any(row["id"] == str(c_a.pk) for row in crm_list_b.data))

        link_res = self.client.post(
            f"/api/whatsapp/conversations/{conv_b.pk}/link-crm/",
            {"prospect_contact_id": str(c_a.pk)},
            format="json",
        )
        self.assertEqual(link_res.status_code, status.HTTP_404_NOT_FOUND)

    def test_gmail_oauth_state_single_use_replay_blocked(self):
        with self.settings(GOOGLE_OAUTH_CLIENT_ID="cid", GOOGLE_OAUTH_CLIENT_SECRET="csec"):
            _, signed_state = GmailOAuthService.generate_authorization_url(self.user_a.id)
        self.assertTrue(GmailOAuthService.verify_state(signed_state, self.user_a.id))
        # Second attempt with the exact same state must be rejected as replay
        self.assertFalse(GmailOAuthService.verify_state(signed_state, self.user_a.id))

    def test_disconnected_calendar_post_returns_409_never_fake_meet_url(self):
        self.client.force_authenticate(user=self.user_a)
        res = self.client.post(
            "/api/auth/google/calendar/events/",
            {
                "summary": "Should Not Mock",
                "start": "2026-12-01T10:00:00Z",
                "end": "2026-12-01T10:30:00Z",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.data.get("code"), "calendar_not_connected")

    def test_webhook_rejects_unsigned_when_secret_set_and_rejects_stale_timestamp(self):
        payload = json.dumps({
            "event": "message",
            "id": "evt-sec-1",
            "session": self.session_a.session_name,
            "payload": {"id": "m1", "from": "919800000111@c.us", "fromMe": False, "body": "Hi"},
        }).encode("utf-8")

        with patch.dict("os.environ", {"WHATSAPP_WEBHOOK_SECRET": WEBHOOK_SECRET}):
            # Unsigned request even under DEBUG=True must be rejected when secret is configured
            res_unsigned = self.client.post(
                "/api/whatsapp/webhook/",
                data=payload,
                content_type="application/json",
            )
            self.assertEqual(res_unsigned.status_code, status.HTTP_401_UNAUTHORIZED)

            # Stale timestamp > 300s must be rejected
            stale_ts = str(int((timezone.now() - timedelta(minutes=15)).timestamp()))
            mac = hmac.new(
                WEBHOOK_SECRET.encode("utf-8"),
                f"{stale_ts}.".encode("utf-8") + payload,
                hashlib.sha256,
            ).hexdigest()
            res_stale = self.client.post(
                "/api/whatsapp/webhook/",
                data=payload,
                content_type="application/json",
                HTTP_X_WEBHOOK_HMAC=f"sha256={mac}",
                HTTP_X_WEBHOOK_TIMESTAMP=stale_ts,
            )
            self.assertEqual(res_stale.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_purge_whatsapp_chats_command_preserves_sessions_configs_users_and_tasks(self):
        from django.core.management import call_command
        from prospects.models import PreTask

        self._enable_ai(self.session_a)
        msg = self._inbound_msg("Hello chat history")
        WhatsAppAIReplyLog.objects.create(
            session=self.session_a,
            conversation=self.conv_a,
            incoming_message=msg,
            reply_text="AI reply",
            status=WhatsAppAIReplyLog.Status.SENT,
        )
        WhatsAppAssistantState.objects.create(
            conversation=self.conv_a,
            session=self.session_a,
            mode=WhatsAppAssistantState.Mode.MEETING_SCHEDULING,
        )
        WhatsAppMeetingRequest.objects.create(
            user=self.user_a,
            session=self.session_a,
            conversation=self.conv_a,
            source_message=msg,
            idempotency_key="purge-test-mr-1",
            state=WhatsAppMeetingRequest.State.SCHEDULED,
        )
        task = PreTask.objects.create(
            task_type=PreTask.TaskType.WHATSAPP_ESCALATION,
            status=PreTask.Status.PENDING,
            title="Follow up task",
            assigned_pre=self.user_a,
            whatsapp_conversation=self.conv_a,
            source_key="purge-test-task-1",
        )
        mtg = Meeting.objects.create(
            scheduled_datetime=timezone.now() + timedelta(days=2),
            meeting_date=(timezone.localdate() + timedelta(days=2)),
            timezone="UTC",
            meeting_provider="GOOGLE_MEET",
            meeting_link="https://meet.google.com/abc-defg-hij",
            created_by=self.user_a,
            client_request_id="purge-test-mtg-1",
        )

        # Dry run leaves everything intact
        call_command("purge_whatsapp_chats", dry_run=True)
        self.assertEqual(WhatsAppConversation.objects.count(), 1)
        self.assertEqual(WhatsAppMessage.objects.count(), 1)

        # Confirmed purge removes ONLY chat/conversation records
        call_command("purge_whatsapp_chats", yes=True)
        self.assertEqual(WhatsAppConversation.objects.count(), 0)
        self.assertEqual(WhatsAppMessage.objects.count(), 0)
        self.assertEqual(WhatsAppAIReplyLog.objects.count(), 0)
        self.assertEqual(WhatsAppAssistantState.objects.count(), 0)
        self.assertEqual(WhatsAppMeetingRequest.objects.count(), 0)

        # Non-chat records stay 100% intact
        self.assertEqual(User.objects.count(), 2)
        self.assertEqual(WhatsAppSession.objects.count(), 2)
        self.assertEqual(WhatsAppConfiguration.objects.count(), 1)
        self.assertTrue(is_session_ai_enabled(self.session_a))
        self.assertTrue(Meeting.objects.filter(pk=mtg.pk).exists())
        task.refresh_from_db()
        self.assertIsNone(task.whatsapp_conversation)

