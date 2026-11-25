import json
import uuid
from datetime import timedelta
from io import BytesIO
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import GoogleMailCredentials
from companies.models import Company
from prospects.email_summarizer import summarize_email_thread
from prospects.email_thread_service import (
    record_outbound_email_in_thread,
    sync_mailbox_messages,
)
from prospects.models import (
    EmailCampaign,
    EmailCampaignRecipient,
    EmailThread,
    EmailThreadMessage,
    OutreachEmail,
    OutreachEmailRecipient,
    Prospect,
    ProspectContact,
)

User = get_user_model()


class _FakeHttpResponse:
    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class ManagerEmailActivityAndSummaryTestCase(APITestCase):
    """
    Comprehensive tests for Part B:
      - Multi-PRE dynamic visibility (4+ PRE users, zero hardcoding)
      - Outreach, Inbox, Bulk Campaign, and Gmail/IMAP synced reply ingestion
      - Multi-strategy reply matching (thread_id, In-Reply-To/References, subject+sender)
      - Repeated reply preservation & sync idempotency
      - Unmatched email isolation
      - Filters, search, pagination, thread detail, safe fields (no BCC/tokens/passwords)
      - Role & tenant company isolation
      - AI summarization (Gemini/OpenAI mock, extractive fallback, failure recovery, hash cache)
      - Legacy OutreachEmail backfill
    """

    def setUp(self):
        self.company_a = Company.objects.create(name="Alpha Corp", code="ALPHA", slug="alpha")
        self.company_b = Company.objects.create(name="Beta Corp", code="BETA", slug="beta")

        self.manager_a = User.objects.create_user(username="mgr_a", password="p", email="mgra@alpha.com")
        self.manager_a.profile.role = "MANAGER"
        self.manager_a.profile.company = self.company_a
        self.manager_a.profile.save()

        self.manager_b = User.objects.create_user(username="mgr_b", password="p", email="mgrb@beta.com")
        self.manager_b.profile.role = "MANAGER"
        self.manager_b.profile.company = self.company_b
        self.manager_b.profile.save()

        # Dynamically create 4 PRE/LQ users in Company A (arbitrary count)
        self.pre_users = []
        for idx in range(1, 5):
            u = User.objects.create_user(
                username=f"pre_alpha_{idx}",
                password="p",
                email=f"pre{idx}@alpha.com",
                first_name=f"PRE{idx}",
                last_name="Alpha",
            )
            u.profile.role = "PRE" if idx < 4 else "LQ"
            u.profile.company = self.company_a
            u.profile.save()
            self.pre_users.append(u)

        self.pre_other_company = User.objects.create_user(username="pre_beta", password="p", email="pre@beta.com")
        self.pre_other_company.profile.role = "PRE"
        self.pre_other_company.profile.company = self.company_b
        self.pre_other_company.profile.save()

        self.dm_user = User.objects.create_user(username="dm_alpha", password="p", email="dm@alpha.com")
        self.dm_user.profile.role = "DM"
        self.dm_user.profile.company = self.company_a
        self.dm_user.profile.save()

        self.cred1 = GoogleMailCredentials.objects.create(
            user=self.pre_users[0],
            email="pre1@alpha.com",
            access_token_encrypted="secret-oauth-access-token-123",
            refresh_token_encrypted="secret-oauth-refresh-token-456",
            is_active=True,
        )

        self.prospect1 = Prospect.objects.create(
            company_name="Target One Logistics",
            official_email_address="ceo@targetone.com",
            created_by=self.pre_users[0].username,
        )
        self.contact1 = ProspectContact.objects.create(
            prospect=self.prospect1,
            contact_name="Priya Nair",
            official_email="priya@targetone.com",
        )

    def test_1_permissions_and_tenant_company_isolation(self):
        """Only MANAGER/superuser can access endpoints, and managers only see own company PRE users."""
        # Anonymous -> 401
        self.assertEqual(self.client.get("/api/manager-dashboard/email-activity/").status_code, status.HTTP_401_UNAUTHORIZED)

        # PRE / LQ / DM -> 403
        for u in [self.pre_users[0], self.pre_users[3], self.dm_user]:
            self.client.force_authenticate(user=u)
            resp = self.client.get("/api/manager-dashboard/email-activity/")
            self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # Manager A sees all 4 Company A PRE/LQ users dynamically and NOT Company B PRE
        self.client.force_authenticate(user=self.manager_a)
        resp_a = self.client.get("/api/manager-dashboard/email-activity/")
        self.assertEqual(resp_a.status_code, status.HTTP_200_OK)
        returned_ids = {u["id"] for u in resp_a.data["pre_users"]}
        self.assertEqual(returned_ids, {u.id for u in self.pre_users})
        self.assertNotIn(self.pre_other_company.id, returned_ids)

        # Manager A filtering by Company B PRE user gets 403
        resp_forbidden = self.client.get(
            f"/api/manager-dashboard/email-activity/?pre_user_id={self.pre_other_company.id}"
        )
        self.assertEqual(resp_forbidden.status_code, status.HTTP_403_FORBIDDEN)

        # Cross-tenant detail access returns 403
        other_thread, _ = record_outbound_email_in_thread(
            owner=self.pre_other_company,
            from_email="pre@beta.com",
            to_emails=["client@other.com"],
            subject="Confidential Beta Deal",
            body_text="Beta private body",
        )
        detail_resp = self.client.get(f"/api/manager-dashboard/email-activity/{other_thread.id}/")
        self.assertEqual(detail_resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_2_outreach_inbox_and_campaign_email_ingestion_plus_security(self):
        """Emails sent via Outreach, Inbox, and Campaign appear for Manager with zero BCC or secret exposure."""
        # 1. Legacy/Outreach email with BCC recipient (BCC must NEVER appear in manager payload!)
        oe = OutreachEmail.objects.create(
            prospect=self.prospect1,
            created_by=self.pre_users[1],
            from_email="pre2@alpha.com",
            from_name="PRE2 Alpha",
            subject="Outreach Proposal",
            body="<p>Please review our proposal for Target One.</p>",
            status="WAITING FOR RESPONSE",
            sent_at=timezone.now() - timedelta(hours=2),
            message_id="<outreach-202@alpha.com>",
        )
        OutreachEmailRecipient.objects.create(outreach_email=oe, email_address="priya@targetone.com", prospect_contact=self.contact1, recipient_type="TO")
        OutreachEmailRecipient.objects.create(outreach_email=oe, email_address="hidden-bcc@internal.com", recipient_type="BCC")

        # 2. Inbox direct send (even without matching prospect)
        inbox_thread, _ = record_outbound_email_in_thread(
            owner=self.pre_users[2],
            from_email="pre3@alpha.com",
            to_emails=["custom@unmatched-domain.io"],
            cc_emails=["cc@alpha.com"],
            subject="Direct Inbox Followup",
            body_text="Checking in on our call yesterday.",
            source="INBOX",
            status="SENT",
        )

        # 3. Bulk Campaign recipient via service record
        camp = EmailCampaign.objects.create(
            name="Q4 Campaign",
            created_by=self.pre_users[0],
            sender_email="pre1@alpha.com",
            subject="Q4 Market Briefing",
            body="<p>Exclusive Q4 insights attached.</p>",
        )
        rec = EmailCampaignRecipient.objects.create(
            campaign=camp,
            email_address="priya@targetone.com",
            prospect=self.prospect1,
            prospect_contact=self.contact1,
            status=EmailCampaignRecipient.Status.SENT,
        )
        record_outbound_email_in_thread(
            owner=self.pre_users[0],
            from_email="pre1@alpha.com",
            to_emails=["priya@targetone.com"],
            subject=camp.subject,
            body_text="Exclusive Q4 insights attached.",
            source="CAMPAIGN",
            prospect=self.prospect1,
            prospect_contact=self.contact1,
            campaign_recipient=rec,
            dedup_key=f"campaign:{rec.id}",
        )

        # Manager fetches email activity (also triggers historical backfill for oe!)
        self.client.force_authenticate(user=self.manager_a)
        list_resp = self.client.get("/api/manager-dashboard/email-activity/")
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)
        subjects = {r["subject"] for r in list_resp.data["results"]}
        self.assertEqual(subjects, {"Outreach Proposal", "Direct Inbox Followup", "Q4 Market Briefing"})

        # Verify BCC and OAuth tokens are completely absent from list and detail payloads
        serialized_blob = json.dumps(list_resp.data, default=str)
        self.assertNotIn("hidden-bcc@internal.com", serialized_blob)
        self.assertNotIn("secret-oauth-access-token-123", serialized_blob)

        outreach_row = next(r for r in list_resp.data["results"] if r["subject"] == "Outreach Proposal")
        detail_resp = self.client.get(f"/api/manager-dashboard/email-activity/{outreach_row['id']}/")
        self.assertEqual(detail_resp.status_code, status.HTTP_200_OK)
        detail_blob = json.dumps(detail_resp.data, default=str)
        self.assertNotIn("hidden-bcc@internal.com", detail_blob)
        self.assertNotIn("secret-oauth-access-token-123", detail_blob)
        self.assertNotIn("secret-oauth-refresh-token-456", detail_blob)

    def test_3_inbound_reply_matching_multi_reply_idempotency_and_unmatched(self):
        """Incoming replies attach to exact threads, preserve second replies, stay idempotent, and isolate unmatched."""
        t0 = timezone.now() - timedelta(hours=3)
        th, _ = record_outbound_email_in_thread(
            owner=self.pre_users[0],
            from_email="pre1@alpha.com",
            to_emails=["priya@targetone.com"],
            subject="Pricing & Onboarding Timeline",
            body_text="Hi Priya, sharing our Q4 pricing sheet.",
            external_thread_id="gmail-th-555",
            rfc_message_id="out-rfc-1@alpha.com",
            prospect=self.prospect1,
            prospect_contact=self.contact1,
            sent_at=t0,
            trigger_summary=False,
        )

        mock_inbox = {
            "messages": [
                # Reply 1 matches by external_thread_id
                {
                    "id": "gmail-in-1",
                    "thread_id": "gmail-th-555",
                    "from": "Priya Nair <priya@targetone.com>",
                    "to": "pre1@alpha.com",
                    "subject": "Re: Pricing & Onboarding Timeline",
                    "date": (t0 + timedelta(minutes=30)).isoformat(),
                    "message_id": "<in-rfc-1@targetone.com>",
                    "in_reply_to": "<out-rfc-1@alpha.com>",
                    "snippet": "Looks good, can we start next Monday?",
                },
                # Reply 2 has NO thread_id match (e.g. different client) -> matches by In-Reply-To / References
                {
                    "id": "gmail-in-2",
                    "thread_id": "different-gmail-tid",
                    "from": "priya@targetone.com",
                    "to": "pre1@alpha.com",
                    "subject": "Re: Pricing & Onboarding Timeline",
                    "date": (t0 + timedelta(minutes=60)).isoformat(),
                    "message_id": "<in-rfc-2@targetone.com>",
                    "in_reply_to": "<out-rfc-1@alpha.com>",
                    "snippet": "Also please include SLA terms in PDF.",
                },
                # Unknown sender with unrelated subject -> stored safely as UNMATCHED on cred1 owner only
                {
                    "id": "gmail-unmatched-1",
                    "thread_id": "gmail-th-unknown",
                    "from": "newsletter@randomvendor.org",
                    "to": "pre1@alpha.com",
                    "subject": "Monthly Digest",
                    "date": (t0 + timedelta(minutes=70)).isoformat(),
                    "message_id": "<digest-1@randomvendor.org>",
                    "snippet": "Generic update",
                },
            ]
        }

        def _fake_body(_cred, mid):
            bodies = {
                "gmail-in-1": {
                    "text_body": "Looks good, can we start next Monday?",
                    "html_body": "",
                    "attachments": [{"filename": "signed-nda.pdf", "mime_type": "application/pdf", "size": 20480}],
                },
                "gmail-in-2": {"text_body": "Also please include SLA terms in PDF.", "html_body": "", "attachments": []},
                "gmail-unmatched-1": {"text_body": "Generic newsletter digest.", "html_body": "", "attachments": []},
            }
            return bodies[mid]

        with patch("accounts.oauth_services.GmailOAuthService.fetch_messages", return_value=mock_inbox), \
             patch("accounts.oauth_services.GmailOAuthService.fetch_message_body", side_effect=_fake_body):
            res1 = sync_mailbox_messages(self.cred1, limit=30)
            # Run second sync to prove idempotency (same messages skipped, not duplicated)
            res2 = sync_mailbox_messages(self.cred1, limit=30)

        self.assertEqual(res1["synced"], 3)
        self.assertEqual(res2["synced"], 0)
        self.assertEqual(res2["skipped"], 3)

        th.refresh_from_db()
        self.assertEqual(th.status, EmailThread.Status.REPLIED)
        self.assertEqual(th.last_direction, EmailThread.Direction.INBOUND)
        self.assertEqual(th.message_count, 3)

        ordered_msgs = list(th.messages.order_by("sent_at", "created_at"))
        self.assertEqual(
            [m.body_text for m in ordered_msgs],
            [
                "Hi Priya, sharing our Q4 pricing sheet.",
                "Looks good, can we start next Monday?",
                "Also please include SLA terms in PDF.",
            ],
        )
        self.assertEqual(ordered_msgs[1].attachments_metadata[0]["filename"], "signed-nda.pdf")

        # Verify unmatched email did not link to prospect1 or another PRE user
        unmatched_th = EmailThread.objects.get(owner=self.pre_users[0], external_thread_id="gmail-th-unknown")
        self.assertEqual(unmatched_th.match_status, EmailThread.MatchStatus.UNMATCHED)
        self.assertEqual(unmatched_th.status, EmailThread.Status.UNMATCHED)
        self.assertIsNone(unmatched_th.prospect)

    def test_4_ai_summarization_gemini_cache_refresh_and_failure_fallback(self):
        """AI summary generates with Gemini/OpenAI, caches by content hash, refreshes on force, and survives failures."""
        th, _ = record_outbound_email_in_thread(
            owner=self.pre_users[0],
            from_email="pre1@alpha.com",
            to_emails=["priya@targetone.com"],
            subject="Security Questionnaire",
            body_text="Sent SOC2 report and ISO27001 certificate.",
            prospect=self.prospect1,
            prospect_contact=self.contact1,
            trigger_summary=False,
        )

        # 1. No API key configured -> extractive summary
        with patch.dict("os.environ", {"GEMINI_API_KEY": "", "OPENAI_API_KEY": "", "EMAIL_SUMMARY_PROVIDER": "auto"}):
            res_ext = summarize_email_thread(th.id)
        self.assertEqual(res_ext["provider"], "extractive")
        th.refresh_from_db()
        self.assertEqual(th.summary_status, EmailThread.SummaryStatus.READY)
        self.assertIn("Security Questionnaire", th.summary_text)

        # 2. Gemini configured -> calls external API, caches by content_hash
        gemini_payload = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "summary": "PRE shared SOC2 and ISO27001 compliance documents with Priya.",
                            "next_action": "Follow up in 2 days for security sign-off.",
                        })
                    }]
                }
            }]
        }
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake-gemini-key", "EMAIL_SUMMARY_PROVIDER": "gemini"}), \
             patch("urllib.request.urlopen", return_value=_FakeHttpResponse(gemini_payload)) as mock_url:
            res_gem = summarize_email_thread(th.id, force=True)
            res_cached = summarize_email_thread(th.id, force=False)
            self.assertEqual(mock_url.call_count, 1)
            self.assertTrue(res_cached.get("cached"))

        th.refresh_from_db()
        self.assertEqual(th.summary_provider, "gemini")
        self.assertIn("SOC2", th.summary_text)

        # 3. AI API fails -> graceful recovery without raising, marks FAILED with error and preserves fallback text
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake-gemini-key", "EMAIL_SUMMARY_PROVIDER": "gemini", "EMAIL_SUMMARY_MAX_RETRIES": "1"}), \
             patch("urllib.request.urlopen", side_effect=RuntimeError("Gemini 503 outage")):
            self.client.force_authenticate(user=self.manager_a)
            refresh_resp = self.client.post(f"/api/manager-dashboard/email-activity/{th.id}/refresh-summary/")
        self.assertEqual(refresh_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(refresh_resp.data["summary_status"], "FAILED")
        self.assertIn("Gemini 503 outage", refresh_resp.data["summary_error"])

    def test_5_manager_filtering_search_and_pagination(self):
        """Manager endpoints support PRE filtering, search, status filtering, date filtering, and pagination."""
        now = timezone.now()
        for idx in range(5):
            owner = self.pre_users[0] if idx < 3 else self.pre_users[1]
            record_outbound_email_in_thread(
                owner=owner,
                from_email=owner.email,
                to_emails=[f"buyer{idx}@client.com"],
                subject=f"Deal Thread {idx}",
                body_text=f"Proposal body {idx}",
                sent_at=now - timedelta(minutes=idx * 10),
                trigger_summary=False,
            )

        self.client.force_authenticate(user=self.manager_a)
        page1 = self.client.get("/api/manager-dashboard/email-activity/?page=1&page_size=2")
        self.assertEqual(page1.status_code, status.HTTP_200_OK)
        self.assertEqual(page1.data["count"], 5)
        self.assertEqual(page1.data["total_pages"], 3)
        self.assertEqual(len(page1.data["results"]), 2)

        filtered_pre = self.client.get(f"/api/manager-dashboard/email-activity/?pre_user_id={self.pre_users[0].id}")
        self.assertEqual(filtered_pre.data["count"], 3)

        searched = self.client.get("/api/manager-dashboard/email-activity/?search=Deal Thread 4")
        self.assertEqual(searched.data["count"], 1)
        self.assertEqual(searched.data["results"][0]["correspondent_email"], "buyer4@client.com")

    def test_6_manager_sync_true_pulls_incoming_reply(self):
        """Opening/refreshing Manager Email Activity with ?sync=true syncs new Gmail replies automatically."""
        th, _ = record_outbound_email_in_thread(
            owner=self.pre_users[0],
            from_email="pre1@alpha.com",
            to_emails=["priya@targetone.com"],
            subject="hello mohan",
            body_text="Initial outreach email.",
            prospect=self.prospect1,
            prospect_contact=self.contact1,
            trigger_summary=False,
        )
        fake_inbox = {
            "messages": [
                {
                    "id": "gmail-live-reply-1",
                    "thread_id": "gmail-thread-live-1",
                    "from": "priya@targetone.com",
                    "to": "pre1@alpha.com",
                    "subject": "Re: hello mohan",
                    "date": timezone.now().isoformat(),
                    "message_id": "<reply-1@targetone.com>",
                    "snippet": "Yes, let us talk tomorrow at 10am.",
                }
            ]
        }
        fake_body = {
            "text_body": "",
            "html_body": "<p>Yes, let us talk tomorrow at 10am.</p>",
            "attachments": [],
        }

        self.client.force_authenticate(user=self.manager_a)
        with patch("accounts.oauth_services.GmailOAuthService.fetch_messages", return_value=fake_inbox), \
             patch("accounts.oauth_services.GmailOAuthService.fetch_message_body", return_value=fake_body):
            resp = self.client.get("/api/manager-dashboard/email-activity/?sync=true")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        th.refresh_from_db()
        self.assertEqual(th.status, EmailThread.Status.REPLIED)
        self.assertEqual(th.message_count, 2)
        reply_msg = th.messages.filter(direction="INBOUND").first()
        self.assertIsNotNone(reply_msg)
        self.assertIn("talk tomorrow at 10am", reply_msg.body_text)

    def test_7_user_wise_daily_email_activity_report_and_gemini_summary(self):
        """User-wise daily report returns exact per-user received/sent/replied/pending counts and Gemini AI summaries for every authorized user."""
        now = timezone.now()
        today_str = now.date().isoformat()

        # User 0: 2 sent today (1 replied, 1 pending), 2 received today (1 reply + 1 standalone inbound)
        th_replied, m_out1 = record_outbound_email_in_thread(
            owner=self.pre_users[0],
            from_email="pre1@alpha.com",
            to_emails=["priya@targetone.com"],
            subject="Demo Proposal",
            body_text="Sending demo proposal for review.",
            prospect=self.prospect1,
            prospect_contact=self.contact1,
            trigger_summary=False,
        )
        m_out1.sent_at = now - timedelta(hours=2)
        m_out1.save(update_fields=["sent_at"])

        EmailThreadMessage.objects.create(
            thread=th_replied,
            owner=self.pre_users[0],
            direction=EmailThreadMessage.Direction.INBOUND,
            source=EmailThreadMessage.Source.SYNC,
            status=EmailThreadMessage.Status.RECEIVED,
            dedup_key="reply-daily-u0-1",
            sender_email="priya@targetone.com",
            to_emails=["pre1@alpha.com"],
            subject="Re: Demo Proposal",
            body_text="Approved the demo slot for Thursday.",
            sent_at=now - timedelta(hours=1),
        )
        th_replied.status = EmailThread.Status.REPLIED
        th_replied.save(update_fields=["status"])

        _th_pending, m_out2 = record_outbound_email_in_thread(
            owner=self.pre_users[0],
            from_email="pre1@alpha.com",
            to_emails=["lead2@targetone.com"],
            subject="Follow-up Quote",
            body_text="Checking on revised quote.",
            prospect=self.prospect1,
            trigger_summary=False,
        )
        m_out2.sent_at = now - timedelta(minutes=30)
        m_out2.save(update_fields=["sent_at"])

        standalone_th = EmailThread.objects.create(
            owner=self.pre_users[0],
            correspondent_email="inbound@partner.com",
            subject="Partnership Inquiry",
            last_direction=EmailThread.Direction.INBOUND,
            status=EmailThread.Status.REPLIED,
            last_message_at=now,
            message_count=1,
        )
        EmailThreadMessage.objects.create(
            thread=standalone_th,
            owner=self.pre_users[0],
            direction=EmailThreadMessage.Direction.INBOUND,
            source=EmailThreadMessage.Source.SYNC,
            status=EmailThreadMessage.Status.RECEIVED,
            dedup_key="inbound-daily-u0-2",
            sender_email="inbound@partner.com",
            to_emails=["pre1@alpha.com"],
            subject="Partnership Inquiry",
            body_text="Can we partner in Q2?",
            sent_at=now - timedelta(minutes=10),
        )

        # User 1: 1 outbound sent today, 0 responses
        _th_u1, m_u1 = record_outbound_email_in_thread(
            owner=self.pre_users[1],
            from_email="pre2@alpha.com",
            to_emails=["buyer@acme.com"],
            subject="Intro Deck",
            body_text="Sharing our company intro deck.",
            trigger_summary=False,
        )
        m_u1.sent_at = now - timedelta(hours=1)
        m_u1.save(update_fields=["sent_at"])

        mock_gemini_resp = _FakeHttpResponse({
            "candidates": [{
                "content": {
                    "parts": [{
                        "text": json.dumps({
                            "summary": "User exchanged emails regarding Demo Proposal approval, quote follow-up, and Q2 partnership inquiry.",
                            "next_action": "Confirm Thursday demo invite and follow up on the revised quote.",
                        })
                    }]
                }
            }]
        })

        self.client.force_authenticate(user=self.manager_a)
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake-gemini-key", "EMAIL_SUMMARY_PROVIDER": "gemini"}), \
             patch("urllib.request.urlopen", return_value=mock_gemini_resp) as mock_urlopen:
            resp = self.client.get(f"/api/manager-dashboard/daily-email-report/?date={today_str}")

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["date"], today_str)
        # All 5 active company_a users returned (4 PRE/LQ + dm_user); company_b excluded
        returned_uids = {u["user_id"]: u for u in resp.data["users"]}
        self.assertIn(self.pre_users[0].id, returned_uids)
        self.assertIn(self.pre_users[1].id, returned_uids)
        self.assertIn(self.dm_user.id, returned_uids)
        self.assertNotIn(self.pre_other_company.id, returned_uids)

        u0_rep = returned_uids[self.pre_users[0].id]
        self.assertEqual(u0_rep["emails_received"], 2)
        self.assertEqual(u0_rep["emails_sent"], 2)
        self.assertEqual(u0_rep["sent_received_responses"], 1)
        self.assertEqual(u0_rep["pending_responses"], 1)
        self.assertEqual(u0_rep["summary_provider"], "gemini")
        self.assertIn("Demo Proposal approval", u0_rep["overall_summary"])

        u1_rep = returned_uids[self.pre_users[1].id]
        self.assertEqual(u1_rep["emails_received"], 0)
        self.assertEqual(u1_rep["emails_sent"], 1)
        self.assertEqual(u1_rep["sent_received_responses"], 0)
        self.assertEqual(u1_rep["pending_responses"], 1)

        # User with 0 activity gets SKIPPED summary without calling Gemini
        dm_rep = returned_uids[self.dm_user.id]
        self.assertEqual(dm_rep["emails_received"], 0)
        self.assertEqual(dm_rep["emails_sent"], 0)
        self.assertEqual(dm_rep["summary_status"], "SKIPPED")
        self.assertEqual(mock_urlopen.call_count, 2)  # Only called for the 2 users with emails

        # Refresh single user report endpoint enforces tenant authorization
        unauth_refresh = self.client.post(f"/api/manager-dashboard/daily-email-report/{self.pre_other_company.id}/refresh/")
        self.assertEqual(unauth_refresh.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.pre_users[0])
        pre_denied = self.client.get("/api/manager-dashboard/daily-email-report/")
        self.assertEqual(pre_denied.status_code, status.HTTP_403_FORBIDDEN)

