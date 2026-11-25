from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import GoogleCalendarCredentials, MailAccount, ZoomCredentials
from accounts.oauth_services import encryption
from accounts.timezone_utils import extract_timezone_from_text, list_all_timezones, normalize_timezone
from prospects.email_thread_service import ingest_fetched_messages
from prospects.models import (
    EmailCampaign,
    EmailThread,
    EmailThreadMessage,
    LeadQualification,
    Meeting,
    OutreachEmail,
    OutreachEmailRecipient,
    PreTask,
    Prospect,
    ProspectContact,
)
from rag.models import KnowledgeBase, KnowledgeBaseSessionAssignment, SessionRAGConfig
from rag.services import document_upload_service
from rag.workers.ingestion_worker import process_document
from rag.tests.helpers import patched_Subsystems
from whatsapp.models import WhatsAppConfiguration, WhatsAppConversation, WhatsAppMessage, WhatsAppSession
from whatsapp_ai.assistant_workflows import ESCALATION_OFFER_MESSAGE
from whatsapp_ai.gemini_service import process_ai_auto_reply
from whatsapp_ai.models import WhatsAppAIAutoReplyConfig, WhatsAppAssistantState

User = get_user_model()


@override_settings(RAG_ENABLED=True, RAG_STRICT_MODE_DEFAULT=True, WHATSAPP_AI_AUTO_REPLY_ENABLED=True)
class AdditionalAIAssistantFeaturesTests(APITestCase):
    def setUp(self):
        self.pre_user = User.objects.create_user(username="pre_owner", password="pw", email="pre@company.com")
        self.pre_user.profile.role = "PRE"
        self.pre_user.profile.save()

        self.other_pre = User.objects.create_user(username="other_pre", password="pw", email="other@company.com")
        self.other_pre.profile.role = "PRE"
        self.other_pre.profile.save()

        self.superadmin = User.objects.create_superuser(username="admin_u", password="pw", email="admin@company.com")

        self.prospect = Prospect.objects.create(
            company_name="Acme Robotics",
            country_head_office="India",
            complete_address="123 Industrial Park",
            official_phone_number="+919876543210",
            official_email_address="contact@acmerobotics.com",
            primary_industries="Robotics",
            company_structure="Parent",
            operational_status="Active",
            primary_offering_type="Products",
            created_by=self.pre_user.username,
        )
        LeadQualification.objects.get_or_create(prospect=self.prospect)
        self.contact = ProspectContact.objects.create(
            prospect=self.prospect,
            contact_name="Riya Sharma",
            designation="VP Procurement",
            official_email="riya@acmerobotics.com",
            phone_number="+919876543210",
        )

        WhatsAppConfiguration.objects.create(outbound_enabled=True, safety_stop_active=False)
        self.wa_session = WhatsAppSession.objects.create(
            owner=self.pre_user,
            session_name="user_pre_1",
            phone_number="919000011111",
            status=WhatsAppSession.Status.READY,
            is_active=True,
        )
        WhatsAppAIAutoReplyConfig.objects.create(
            session=self.wa_session,
            enabled=True,
            reply_to_groups=False,
            model_name="gemini-2.5-flash",
        )
        self.wa_conv = WhatsAppConversation.objects.create(
            session=self.wa_session,
            chat_id="919876543210@c.us",
            phone_number="+919876543210",
            whatsapp_name="Riya Sharma",
            prospect=self.prospect,
            prospect_contact=self.contact,
            is_matched=True,
        )

        # Connect Google Calendar & Zoom OAuth credentials for pre_user
        self.g_creds = GoogleCalendarCredentials.objects.create(
            user=self.pre_user,
            email="pre@company.com",
            access_token_encrypted=encryption.encrypt_password("fake-g-token"),
            refresh_token_encrypted=encryption.encrypt_password("fake-g-refresh"),
            token_expiry=timezone.now() + timezone.timedelta(hours=1),
            scopes="https://www.googleapis.com/auth/calendar",
            is_active=True,
        )
        self.z_creds = ZoomCredentials.objects.create(
            user=self.pre_user,
            email="pre@company.com",
            access_token_encrypted=encryption.encrypt_password("fake-z-token"),
            refresh_token_encrypted=encryption.encrypt_password("fake-z-refresh"),
            token_expiry=timezone.now() + timezone.timedelta(hours=1),
            is_active=True,
        )
        self._msg_seq = 0

    def _inbound_wa(self, body: str) -> WhatsAppMessage:
        self._msg_seq += 1
        return WhatsAppMessage.objects.create(
            idempotency_key=f"test-wa-{self._msg_seq}",
            conversation=self.wa_conv,
            waha_message_id=f"wamid-{self._msg_seq}",
            direction=WhatsAppMessage.Direction.INBOUND,
            status=WhatsAppMessage.Status.DELIVERED,
            body_preview=body[:500],
            full_body=body,
        )

    def _fake_waha(self):
        fake = MagicMock()
        fake.send_text.return_value = {"id": "out-wamid-1"}
        return fake

    # ── Feature 1: WhatsApp AI Meeting Scheduling (Zoom & Google Meet + Calendar) ──

    @patch("accounts.zoom_services.list_zoom_meetings", return_value=[])
    @patch("accounts.calendar_services.list_events", return_value=[])
    @patch("accounts.calendar_services._api_request")
    @patch("accounts.zoom_services.create_zoom_meeting")
    @patch("whatsapp.client.get_waha_client")
    def test_whatsapp_meeting_scheduling_zoom_multi_turn_and_calendar_display(
        self, mock_waha, mock_zoom, mock_gcal_req, _mock_list_events, _mock_list_zoom
    ):
        mock_waha.return_value = self._fake_waha()
        mock_zoom.return_value = {
            "meeting_id": "99887766",
            "join_url": "https://zoom.us/j/99887766",
            "password": "123",
            "start_url": "https://zoom.us/s/99887766",
            "status": "READY",
        }
        mock_gcal_req.return_value = {"id": "gcal_zoom_1"}

        # 1. Sender expresses scheduling interest -> asks date & time
        r1 = process_ai_auto_reply(self._inbound_wa("Hi, I would like to schedule a meeting with your team.").pk)
        self.assertEqual(r1["status"], "SENT")
        self.assertIn("date", r1["reply_text"].lower())
        self.assertIn("time", r1["reply_text"].lower())

        # 2. Sender provides date & time -> asks timezone
        r2 = process_ai_auto_reply(self._inbound_wa("2026-11-25 at 3:30 PM").pk)
        self.assertEqual(r2["status"], "SENT")
        self.assertIn("time zone", r2["reply_text"].lower())

        # 3. Sender provides timezone -> asks details/agenda (since contact already has email, asks topic)
        r3 = process_ai_auto_reply(self._inbound_wa("IST").pk)
        self.assertEqual(r3["status"], "SENT")
        self.assertIn("topic", r3["reply_text"].lower())

        # 4. Sender provides topic -> asks platform (Zoom or Google Meet)
        r4 = process_ai_auto_reply(self._inbound_wa("Product pricing and deployment timeline").pk)
        self.assertEqual(r4["status"], "SENT")
        self.assertIn("Zoom", r4["reply_text"])
        self.assertIn("Google Meet", r4["reply_text"])

        # 5. Sender chooses Zoom -> asks confirmation summary
        r5 = process_ai_auto_reply(self._inbound_wa("Zoom please").pk)
        self.assertEqual(r5["status"], "SENT")
        self.assertIn("Confirm", r5["reply_text"])
        self.assertIn("2026-11-25", r5["reply_text"])
        self.assertIn("15:30", r5["reply_text"])
        self.assertIn("Asia/Kolkata", r5["reply_text"])
        self.assertEqual(Meeting.objects.count(), 0)  # Not created before confirmation!

        # 6. Sender confirms -> generates Zoom link + creates CRM Meeting + displays in Calendar API
        r6 = process_ai_auto_reply(self._inbound_wa("Yes, confirm").pk)
        self.assertEqual(r6["status"], "SENT")
        self.assertIn("https://zoom.us/j/99887766", r6["reply_text"])

        mock_zoom.assert_called_once()
        meeting = Meeting.objects.get()
        self.assertEqual(meeting.prospect, self.prospect)
        self.assertEqual(meeting.prospect_contact, self.contact)
        self.assertEqual(meeting.meeting_provider, "ZOOM")
        self.assertEqual(meeting.meeting_link, "https://zoom.us/j/99887766")
        self.assertEqual(meeting.timezone, "Asia/Kolkata")
        self.assertEqual(meeting.meeting_date.isoformat(), "2026-11-25")
        self.assertEqual(meeting.meeting_time.strftime("%H:%M"), "15:30")

        state = WhatsAppAssistantState.objects.get(conversation=self.wa_conv)
        self.assertEqual(state.mode, WhatsAppAssistantState.Mode.IDLE)

        # Verify Calendar endpoint shows the Zoom meeting even if not in Google Calendar list_events result
        self.client.force_authenticate(user=self.pre_user)
        with patch("accounts.calendar_views.list_events", return_value=[]):
            cal_res = self.client.get("/api/auth/google/calendar/events/")
        self.assertEqual(cal_res.status_code, 200)
        events = cal_res.data["events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["meet_url"], "https://zoom.us/j/99887766")
        self.assertEqual(events[0]["company_name"], "Acme Robotics")
        self.assertEqual(events[0]["contact_name"], "Riya Sharma")
        self.assertEqual(events[0]["timezone"], "Asia/Kolkata")

    @patch("accounts.calendar_services.list_events", return_value=[])
    @patch("accounts.calendar_services.create_meet_event")
    @patch("whatsapp.client.get_waha_client")
    def test_whatsapp_meeting_scheduling_google_meet_single_message_slots(self, mock_waha, mock_gmeet, _mock_list_events):
        mock_waha.return_value = self._fake_waha()
        mock_gmeet.return_value = {
            "event_id": "gmeet_evt_123",
            "status": "READY",
            "meet_url": "https://meet.google.com/abc-defg-hij",
        }

        # Sender gives all details in initial request
        r1 = process_ai_auto_reply(
            self._inbound_wa("Can we schedule a Google Meet on 2026-12-02 at 10:00 AM EST about annual contract?").pk
        )
        self.assertEqual(r1["status"], "SENT")
        self.assertIn("Google Meet", r1["reply_text"])
        self.assertIn("America/New_York", r1["reply_text"])
        self.assertIn("Confirm", r1["reply_text"])

        r2 = process_ai_auto_reply(self._inbound_wa("Confirmed").pk)
        self.assertEqual(r2["status"], "SENT")
        self.assertIn("https://meet.google.com/abc-defg-hij", r2["reply_text"])

        meeting = Meeting.objects.get()
        self.assertEqual(meeting.meeting_provider, "GOOGLE_MEET")
        self.assertEqual(meeting.meeting_link, "https://meet.google.com/abc-defg-hij")
        self.assertEqual(meeting.timezone, "America/New_York")
        self.assertEqual(meeting.prospect, self.prospect)
        self.assertEqual(meeting.prospect_contact, self.contact)

    # ── Feature 2: WhatsApp Vector DB Unanswered Query -> Confirmation -> PRE Task ──

    @patch("whatsapp.client.get_waha_client")
    def test_whatsapp_unknown_query_asks_confirmation_then_creates_pre_task(self, mock_waha):
        mock_waha.return_value = self._fake_waha()
        kb = KnowledgeBase.objects.create(owner=self.superadmin, name="Product Docs")
        KnowledgeBaseSessionAssignment.objects.create(session=self.wa_session, knowledge_base=kb, is_active=True)
        SessionRAGConfig.objects.create(session=self.wa_session, strict_rag_enabled=True)

        def mock_rag_gemini(model, payload, **kwargs):
            return {
                "candidates": [{"content": {"parts": [{"text": "NOT AVAILABLE IN KNOWLEDGE BASE"}]}}]
            }

        with patched_Subsystems(gemini_transport=mock_rag_gemini):
            doc = document_upload_service.upload_document(
                kb,
                self.superadmin,
                SimpleUploadedFile("catalog.csv", b"Item,Cost\nBolt,10\n", content_type="text/csv"),
            )
            process_document(doc.pk)

            # 1. Sender asks something NOT in KB
            res1 = process_ai_auto_reply(
                self._inbound_wa("Do you offer custom 10-year SLA guarantees for offshore rigs?").pk
            )
            self.assertEqual(res1["status"], "SENT")
            self.assertEqual(res1["reply_text"], ESCALATION_OFFER_MESSAGE)
            # Must NOT create PRE task before sender confirms
            self.assertEqual(PreTask.objects.count(), 0)

            # 2. Sender declines first -> no task created
            res2 = process_ai_auto_reply(self._inbound_wa("No thanks").pk)
            self.assertEqual(res2["status"], "SENT")
            self.assertEqual(PreTask.objects.count(), 0)

            # 3. Sender asks another unavailable query and then confirms
            res3 = process_ai_auto_reply(
                self._inbound_wa("What is your dedicated enterprise discount tier for 500 units?").pk
            )
            self.assertEqual(res3["reply_text"], ESCALATION_OFFER_MESSAGE)
            res4 = process_ai_auto_reply(self._inbound_wa("Yes, please forward my details").pk)
            self.assertEqual(res4["status"], "SENT")
            self.assertIn(self.pre_user.username, res4["reply_text"])

        task = PreTask.objects.get()
        self.assertEqual(task.task_type, PreTask.TaskType.WHATSAPP_ESCALATION)
        self.assertEqual(task.status, PreTask.Status.PENDING)
        self.assertEqual(task.assigned_pre, self.pre_user)
        self.assertEqual(task.prospect, self.prospect)
        self.assertEqual(task.prospect_contact, self.contact)
        self.assertEqual(task.sender_email, "riya@acmerobotics.com")
        self.assertEqual(task.sender_phone, "+919876543210")
        self.assertIn("500 units", task.description)
        self.assertGreaterEqual(len(task.conversation_history), 4)

    # ── Feature 3: Automatically Create PRE Tasks for Incoming Email Replies ──

    @patch("accounts.oauth_services.GmailOAuthService.fetch_message_body")
    @patch("email_ai.services.schedule_thread_summary")
    def test_incoming_email_reply_creates_assigned_pre_task_and_api_completion(self, mock_sched, mock_fetch_body):
        mock_fetch_body.return_value = {
            "text_body": "Thanks! Can you send the updated CAD specs before Friday?",
            "html_body": "",
            "attachments": [],
        }
        mail_acc = MailAccount.objects.create(
            name="PRE Outreach",
            email_address="outreach@company.com",
            display_name="PRE Outreach",
            smtp_host="smtp.example.com",
            smtp_username="outreach@company.com",
            smtp_app_password_encrypted="enc",
            imap_host="imap.example.com",
            imap_username="outreach@company.com",
            imap_app_password_encrypted="enc",
        )
        oe = OutreachEmail.objects.create(
            prospect=self.prospect,
            created_by=self.pre_user,
            sender_mail_account=mail_acc,
            from_email="outreach@company.com",
            from_name="PRE Owner",
            subject="Robotics Partnership Proposal",
            body="Hello Riya, sharing our Robotics catalog.",
            status="SENT",
            sent_at=timezone.now(),
            message_id="<sent-msg-100@company.com>",
        )
        OutreachEmailRecipient.objects.create(
            outreach_email=oe,
            email_address="riya@acmerobotics.com",
            prospect_contact=self.contact,
            recipient_type="TO",
        )

        # Ingest matching inbound reply
        cred = SimpleNamespace(user=self.pre_user, email="outreach@company.com")
        payload = [
            {
                "id": "gmail-msg-200",
                "message_id": "<reply-200@acmerobotics.com>",
                "in_reply_to": "<sent-msg-100@company.com>",
                "subject": "Re: Robotics Partnership Proposal",
                "from": "Riya Sharma <riya@acmerobotics.com>",
                "to": "outreach@company.com",
                "snippet": "Thanks! Can you send the updated CAD specs",
                "sent_at": timezone.now().isoformat(),
            }
        ]
        res = ingest_fetched_messages(cred, payload)
        self.assertEqual(res["synced"], 1)

        task = PreTask.objects.get()
        self.assertEqual(task.task_type, PreTask.TaskType.EMAIL_REPLY)
        self.assertEqual(task.status, PreTask.Status.PENDING)
        self.assertEqual(task.assigned_pre, self.pre_user)
        self.assertEqual(task.prospect, self.prospect)
        self.assertEqual(task.prospect_contact, self.contact)
        self.assertEqual(task.outreach_email, oe)
        self.assertEqual(task.sender_email, "riya@acmerobotics.com")
        self.assertIn("updated CAD specs", task.description)
        self.assertTrue(any("Robotics Partnership Proposal" in (m.get("subject") or "") for m in task.conversation_history))

        # Re-ingesting duplicate message must NOT create duplicate PreTask
        ingest_fetched_messages(cred, payload)
        self.assertEqual(PreTask.objects.count(), 1)

        # Authorization + complete workflow on /api/pre-tasks/
        self.client.force_authenticate(user=self.other_pre)
        other_list = self.client.get("/api/pre-tasks/?status=PENDING")
        self.assertEqual(other_list.status_code, 200)
        other_items = other_list.data["results"] if isinstance(other_list.data, dict) else other_list.data
        self.assertEqual(len(other_items), 0)

        self.client.force_authenticate(user=self.pre_user)
        own_list = self.client.get("/api/pre-tasks/?status=PENDING")
        self.assertEqual(own_list.status_code, 200)
        own_items = own_list.data["results"] if isinstance(own_list.data, dict) else own_list.data
        self.assertEqual(len(own_items), 1)
        self.assertEqual(own_items[0]["id"], str(task.id))

        comp = self.client.post(f"/api/pre-tasks/{task.id}/complete/", {"resolution_notes": "Sent CAD specs"})
        self.assertEqual(comp.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, PreTask.Status.COMPLETED)
        self.assertEqual(task.completed_by, self.pre_user)

    @patch("whatsapp.client.get_waha_client")
    def test_whatsapp_case_insensitive_and_all_network_timezones_no_repeat(self, mock_waha):
        mock_waha.return_value = self._fake_waha()

        # Exact screenshot reproduction: "Asia/kolkata" lowercase 'k' must advance immediately!
        r1 = process_ai_auto_reply(self._inbound_wa("Can you schedule a meeting").pk)
        self.assertIn("date", r1["reply_text"].lower())

        r2 = process_ai_auto_reply(self._inbound_wa("I want to schedule meeting on 5 pm today").pk)
        self.assertIn("time zone", r2["reply_text"].lower())

        r3 = process_ai_auto_reply(self._inbound_wa("Asia/kolkata").pk)
        self.assertIn("Asia/Kolkata", r3["reply_text"])
        self.assertNotIn("Which *time zone*", r3["reply_text"])

        state = WhatsAppAssistantState.objects.get(conversation=self.wa_conv)
        self.assertEqual(state.state_data["timezone"], "Asia/Kolkata")
        state.reset()

        # Verify broad IANA / network timezones (multi-level, lowercase, offsets, cities)
        self.assertGreater(len(list_all_timezones()), 400)
        self.assertEqual(normalize_timezone("america/argentina/buenos_aires"), "America/Argentina/Buenos_Aires")
        self.assertEqual(normalize_timezone("europe/london"), "Europe/London")
        self.assertEqual(normalize_timezone("UTC+4"), "Asia/Dubai")
        self.assertEqual(normalize_timezone("GMT+05:30"), "Asia/Kolkata")
        self.assertEqual(extract_timezone_from_text("I preferred Asia/kolkata time zone"), "Asia/Kolkata")
        self.assertEqual(extract_timezone_from_text("riyadh", expecting_timezone=True), "Asia/Riyadh")

        # Profile timezone endpoint normalizes any network timezone
        self.client.force_authenticate(user=self.pre_user)
        resp = self.client.patch("/api/auth/me/", {"timezone": "america/argentina/buenos_aires"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["timezone"], "America/Argentina/Buenos_Aires")
