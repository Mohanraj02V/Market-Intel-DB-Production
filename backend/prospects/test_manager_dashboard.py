import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

import utils.encryption as encryption
from accounts.models import (
    GoogleCalendarCredentials,
    GoogleMailCredentials,
    ZoomCredentials,
)
from companies.models import Company
from prospects.manager_views import _get_report_tz
from prospects.models import (
    AuditReverificationRequest,
    CallActivity,
    CommunicationActivity,
    EmailCampaign,
    EmailCampaignRecipient,
    EmailThread,
    EmailThreadMessage,
    LeadQualification,
    Meeting,
    OutreachEmail,
    PreTask,
    Prospect,
    ProspectContact,
)
from whatsapp.models import (
    WhatsAppConfiguration,
    WhatsAppConversation,
    WhatsAppMessage,
    WhatsAppSession,
)
from whatsapp_ai.models import (
    WhatsAppAIAutoReplyConfig,
    WhatsAppAIReplyLog,
    WhatsAppMeetingRequest,
)

User = get_user_model()


class ManagerDashboardAndAuditTestCase(APITestCase):
    """
    Verifies the redesigned Manager Role:
      - RBAC enforcement (401 unauthenticated, 403 PRE/DM, 200 MANAGER/Superuser)
      - Strict company-level isolation
      - Unified PRE real-time metrics across Prospects, Calls, Emails, WhatsApp/AI,
        Meetings, PreTasks, Campaigns, Funnel, Live Feed, and Daily Audit
      - Zero double-counting between linked OutreachEmail and EmailThreadMessage
    """

    def setUp(self):
        self.company_a = Company.objects.create(name="Alpha Analytics", code="ALPHA", slug="alpha")
        self.company_b = Company.objects.create(name="Beta Systems", code="BETA", slug="beta")

        self.superuser = User.objects.create_superuser(
            username="superadmin", email="super@example.com", password="p"
        )

        self.manager_a = User.objects.create_user(
            username="mgr_a", password="p", email="mgra@alpha.com", first_name="Maya", last_name="Manager"
        )
        self.manager_a.profile.role = "MANAGER"
        self.manager_a.profile.company = self.company_a
        self.manager_a.profile.save()

        self.pre_a1 = User.objects.create_user(
            username="pre_a1", password="p", email="pre1@alpha.com", first_name="Arun", last_name="PRE"
        )
        self.pre_a1.profile.role = "PRE"
        self.pre_a1.profile.company = self.company_a
        self.pre_a1.profile.save()

        self.pre_a2 = User.objects.create_user(
            username="pre_a2", password="p", email="pre2@alpha.com", first_name="Bala", last_name="PRE"
        )
        self.pre_a2.profile.role = "PRE"
        self.pre_a2.profile.company = self.company_a
        self.pre_a2.profile.save()

        self.dm_a = User.objects.create_user(username="dm_a", password="p", email="dm@alpha.com")
        self.dm_a.profile.role = "DM"
        self.dm_a.profile.company = self.company_a
        self.dm_a.profile.save()

        self.pre_b1 = User.objects.create_user(
            username="pre_b1", password="p", email="pre1@beta.com", first_name="Beta", last_name="User"
        )
        self.pre_b1.profile.role = "PRE"
        self.pre_b1.profile.company = self.company_b
        self.pre_b1.profile.save()

        now = timezone.now()
        self.today_str = now.astimezone(_get_report_tz()).date().isoformat()

        # Credentials for pre_a1 only
        GoogleMailCredentials.objects.create(
            user=self.pre_a1,
            email="pre1@alpha.com",
            access_token_encrypted=encryption.encrypt_password("tok"),
            refresh_token_encrypted=encryption.encrypt_password("ref"),
            is_active=True,
        )
        GoogleCalendarCredentials.objects.create(
            user=self.pre_a1,
            email="pre1@alpha.com",
            access_token_encrypted=encryption.encrypt_password("tok"),
            refresh_token_encrypted=encryption.encrypt_password("ref"),
            is_active=True,
        )
        ZoomCredentials.objects.create(
            user=self.pre_a1,
            email="pre1@alpha.com",
            access_token_encrypted=encryption.encrypt_password("tok"),
            refresh_token_encrypted=encryption.encrypt_password("ref"),
            is_active=True,
        )

        # Prospects in Company A (p1 qualified today, p2 nurture today) + Company B (p_b1)
        self.p1 = Prospect.objects.create(
            company_name="Acme Energy",
            country_head_office="UAE",
            complete_address="Dubai",
            primary_industries="Energy",
            company_structure=Prospect.Structure.PARENT,
            operational_status=Prospect.Status.ACTIVE,
            primary_offering_type=Prospect.OfferingType.SOLUTIONS,
            created_by=self.pre_a1.username,
        )
        self.c1 = ProspectContact.objects.create(
            prospect=self.p1,
            contact_name="John CEO",
            official_email="john@acme.com",
            phone_number="+971501112233",
        )
        lq1 = self.p1.lead_qualification
        lq1.verification_status = LeadQualification.VerificationStatus.VERIFIED
        lq1.qualification_status = LeadQualification.QualificationStatus.LEAD_QUALIFIED
        lq1.attended_meeting = True
        lq1.attended_at = now
        lq1.decision_by = self.pre_a1
        lq1.decision_at = now
        lq1.save()

        self.p2 = Prospect.objects.create(
            company_name="Horizon Robotics",
            country_head_office="Singapore",
            complete_address="Marina",
            primary_industries="Robotics",
            company_structure=Prospect.Structure.PARENT,
            operational_status=Prospect.Status.ACTIVE,
            primary_offering_type=Prospect.OfferingType.PRODUCTS,
            created_by=self.pre_a2.username,
        )
        lq2 = self.p2.lead_qualification
        lq2.qualification_status = LeadQualification.QualificationStatus.LEAD_FREEZE
        lq2.decision_by = self.pre_a2
        lq2.decision_at = now
        lq2.save()

        self.p_b1 = Prospect.objects.create(
            company_name="Secret Beta Corp",
            country_head_office="USA",
            complete_address="NYC",
            primary_industries="Defense",
            company_structure=Prospect.Structure.PARENT,
            operational_status=Prospect.Status.ACTIVE,
            primary_offering_type=Prospect.OfferingType.SERVICES,
            created_by=self.pre_b1.username,
        )
        lq_b = self.p_b1.lead_qualification
        lq_b.qualification_status = LeadQualification.QualificationStatus.LEAD_QUALIFIED
        lq_b.decision_by = self.pre_b1
        lq_b.decision_at = now
        lq_b.save()

        # Call & Communication activity in Company A and Company B
        CallActivity.objects.create(
            prospect=self.p1,
            prospect_contact=self.c1,
            created_by=self.pre_a1,
            call_status="Connected",
            communication_outcome="Interested",
        )
        CommunicationActivity.objects.create(
            prospect=self.p1,
            prospect_contact=self.c1,
            activity_type="CALL",
            direction="OUTBOUND",
            status="Connected",
            performed_by=self.pre_a1,
        )
        CallActivity.objects.create(
            prospect=self.p_b1,
            created_by=self.pre_b1,
            call_status="Connected",
        )

        # Emails: 1 linked OutreachEmail + EmailThreadMessage (must count as 1, not 2)
        # + 1 inbound reply in thread + 1 standalone opened OutreachEmail
        thread_a = EmailThread.objects.create(
            owner=self.pre_a1,
            prospect=self.p1,
            prospect_contact=self.c1,
            mailbox_email="pre1@alpha.com",
            correspondent_email="john@acme.com",
            subject="Partnership Intro",
            status=EmailThread.Status.REPLIED,
            last_direction=EmailThread.Direction.INBOUND,
            last_message_at=now,
            message_count=2,
        )
        oe_linked = OutreachEmail.objects.create(
            prospect=self.p1,
            created_by=self.pre_a1,
            from_email="pre1@alpha.com",
            subject="Partnership Intro",
            status="RECEIVED RESPONSE",
            sent_at=now,
            is_opened=True,
        )
        EmailThreadMessage.objects.create(
            thread=thread_a,
            owner=self.pre_a1,
            outreach_email=oe_linked,
            direction=EmailThreadMessage.Direction.OUTBOUND,
            source=EmailThreadMessage.Source.OUTREACH,
            status=EmailThreadMessage.Status.SENT,
            dedup_key=f"out-{uuid.uuid4()}",
            sender_email="pre1@alpha.com",
            to_emails=["john@acme.com"],
            subject="Partnership Intro",
            sent_at=now,
        )
        EmailThreadMessage.objects.create(
            thread=thread_a,
            owner=self.pre_a1,
            direction=EmailThreadMessage.Direction.INBOUND,
            source=EmailThreadMessage.Source.SYNC,
            status=EmailThreadMessage.Status.RECEIVED,
            dedup_key=f"in-{uuid.uuid4()}",
            sender_email="john@acme.com",
            to_emails=["pre1@alpha.com"],
            subject="Re: Partnership Intro",
            sent_at=now,
        )
        OutreachEmail.objects.create(
            prospect=self.p2,
            created_by=self.pre_a2,
            from_email="pre2@alpha.com",
            subject="Follow-up Deck",
            status="WAITING FOR RESPONSE",
            sent_at=now,
            is_opened=True,
        )
        EmailThread.objects.create(
            owner=self.pre_a2,
            prospect=self.p2,
            mailbox_email="pre2@alpha.com",
            correspondent_email="lead@horizon.io",
            subject="Follow-up Deck",
            status=EmailThread.Status.WAITING_REPLY,
            last_direction=EmailThread.Direction.OUTBOUND,
            last_message_at=now,
            message_count=1,
        )
        # Company B email (must not count for manager_a)
        OutreachEmail.objects.create(
            prospect=self.p_b1,
            created_by=self.pre_b1,
            from_email="pre1@beta.com",
            subject="Beta Secret Pitch",
            status="SENT",
            sent_at=now,
        )

        # WhatsApp config, session, AI config, messages (1 out, 1 in, 1 soft-deleted), AI log, AI meeting request
        WhatsAppConfiguration.objects.create(outbound_enabled=True, safety_stop_active=False)
        wa_sess_a = WhatsAppSession.objects.create(
            owner=self.pre_a1,
            session_name="alpha_pre1_wa",
            status=WhatsAppSession.Status.READY,
            phone_number="+971500000001",
            is_active=True,
            last_used_at=now,
        )
        WhatsAppAIAutoReplyConfig.objects.create(
            session=wa_sess_a,
            enabled=True,
            model_name="gemini-2.5-flash",
        )
        wa_conv = WhatsAppConversation.objects.create(
            chat_id="971501112233@c.us",
            whatsapp_name="John CEO",
            prospect=self.p1,
            prospect_contact=self.c1,
            session=wa_sess_a,
            is_matched=True,
        )
        wa_in = WhatsAppMessage.objects.create(
            idempotency_key=f"wa-in-{uuid.uuid4().hex[:20]}",
            conversation=wa_conv,
            direction=WhatsAppMessage.Direction.INBOUND,
            status=WhatsAppMessage.Status.DELIVERED,
            body_preview="Hi, tell me about your enterprise plan",
        )
        wa_out = WhatsAppMessage.objects.create(
            idempotency_key=f"wa-out-{uuid.uuid4().hex[:20]}",
            conversation=wa_conv,
            performed_by=self.pre_a1,
            direction=WhatsAppMessage.Direction.OUTBOUND,
            status=WhatsAppMessage.Status.SENT,
            body_preview="Sure, sharing our enterprise solution overview!",
        )
        # Deleted message must not count
        WhatsAppMessage.objects.create(
            idempotency_key=f"wa-del-{uuid.uuid4().hex[:20]}",
            conversation=wa_conv,
            direction=WhatsAppMessage.Direction.OUTBOUND,
            status=WhatsAppMessage.Status.SENT,
            body_preview="Should be hidden",
            is_deleted=True,
        )
        WhatsAppAIReplyLog.objects.create(
            session=wa_sess_a,
            conversation=wa_conv,
            incoming_message=wa_in,
            reply_message=wa_out,
            sender_identifier="971501112233",
            reply_text="AI reply sent",
            status=WhatsAppAIReplyLog.Status.SENT,
            replied_at=now,
        )
        WhatsAppMeetingRequest.objects.create(
            user=self.pre_a1,
            session=wa_sess_a,
            conversation=wa_conv,
            idempotency_key=f"wa-mtg-{uuid.uuid4().hex[:20]}",
            state=WhatsAppMeetingRequest.State.SCHEDULED,
        )

        # Meetings (1 scheduled today/upcoming in Company A, 1 in Company B)
        Meeting.objects.create(
            prospect=self.p1,
            prospect_contact=self.c1,
            created_by=self.pre_a1,
            scheduled_datetime=now + timedelta(hours=2),
            meeting_provider="GOOGLE_MEET",
            meeting_link="https://meet.google.com/abc-defg-hij",
            recording_status="COMPLETED",
            transcription_status="COMPLETED",
        )
        Meeting.objects.create(
            prospect=self.p_b1,
            created_by=self.pre_b1,
            scheduled_datetime=now + timedelta(hours=3),
            meeting_provider="ZOOM",
        )

        # PRE Tasks & Audit Reverification Requests
        PreTask.objects.create(
            task_type=PreTask.TaskType.EMAIL_REPLY,
            status=PreTask.Status.PENDING,
            title="Reply from John CEO",
            assigned_pre=self.pre_a1,
            assigned_pre_username=self.pre_a1.username,
            prospect=self.p1,
            company_name=self.p1.company_name,
            source_key=f"pt-1-{uuid.uuid4()}",
        )
        PreTask.objects.create(
            task_type=PreTask.TaskType.WHATSAPP_ESCALATION,
            status=PreTask.Status.PENDING,
            title="Custom pricing query",
            assigned_pre=self.pre_a2,
            assigned_pre_username=self.pre_a2.username,
            prospect=self.p2,
            company_name=self.p2.company_name,
            source_key=f"pt-2-{uuid.uuid4()}",
        )
        PreTask.objects.create(
            task_type=PreTask.TaskType.EMAIL_REPLY,
            status=PreTask.Status.COMPLETED,
            title="Resolved task",
            assigned_pre=self.pre_a1,
            assigned_pre_username=self.pre_a1.username,
            prospect=self.p1,
            completed_at=now,
            completed_by=self.pre_a1,
            source_key=f"pt-3-{uuid.uuid4()}",
        )
        PreTask.objects.create(
            task_type=PreTask.TaskType.EMAIL_REPLY,
            status=PreTask.Status.PENDING,
            title="Beta task",
            assigned_pre=self.pre_b1,
            assigned_pre_username=self.pre_b1.username,
            prospect=self.p_b1,
            source_key=f"pt-b-{uuid.uuid4()}",
        )

        AuditReverificationRequest.objects.create(
            prospect=self.p1,
            manager=self.manager_a,
            pre_user=self.pre_a1,
            highlighted_fields=["official_email_address"],
            manager_notes="Confirm primary domain",
            status=AuditReverificationRequest.Status.PENDING,
        )
        AuditReverificationRequest.objects.create(
            prospect=self.p_b1,
            pre_user=self.pre_b1,
            highlighted_fields=["complete_address"],
            status=AuditReverificationRequest.Status.PENDING,
        )

        # Campaign
        camp = EmailCampaign.objects.create(
            name="Q4 Energy Outreach",
            created_by=self.pre_a1,
            sender_email="pre1@alpha.com",
            subject="Hello",
            body="World",
            status=EmailCampaign.Status.RUNNING,
        )
        EmailCampaignRecipient.objects.create(
            campaign=camp,
            email_address="john@acme.com",
            status=EmailCampaignRecipient.Status.SENT,
        )
        EmailCampaignRecipient.objects.create(
            campaign=camp,
            email_address="ops@acme.com",
            status=EmailCampaignRecipient.Status.PENDING,
        )

    def test_rbac_permissions(self):
        # Unauthenticated -> 401
        self.assertEqual(self.client.get("/api/manager-dashboard/").status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.get("/api/manager-dashboard/audit/").status_code, status.HTTP_401_UNAUTHORIZED)

        # PRE and DM -> 403
        for denied_user in (self.pre_a1, self.dm_a):
            self.client.force_authenticate(user=denied_user)
            self.assertEqual(self.client.get("/api/manager-dashboard/").status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(self.client.get("/api/manager-dashboard/audit/").status_code, status.HTTP_403_FORBIDDEN)

        # Manager and Superuser -> 200
        for allowed_user in (self.manager_a, self.superuser):
            self.client.force_authenticate(user=allowed_user)
            self.assertEqual(self.client.get("/api/manager-dashboard/").status_code, status.HTTP_200_OK)
            self.assertEqual(self.client.get("/api/manager-dashboard/audit/").status_code, status.HTTP_200_OK)

    def test_invalid_date_returns_400(self):
        self.client.force_authenticate(user=self.manager_a)
        res1 = self.client.get("/api/manager-dashboard/?date=invalid-date")
        res2 = self.client.get("/api/manager-dashboard/audit/?date=2026-99-99")
        self.assertEqual(res1.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_company_isolation_and_true_metrics(self):
        self.client.force_authenticate(user=self.manager_a)
        res = self.client.get(f"/api/manager-dashboard/?date={self.today_str}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data

        # Obsolete split PRE/LQ structures must be removed
        self.assertNotIn("lq_users", data)
        self.assertNotIn("lq_pre_distribution", data)
        self.assertNotIn("pre_users", data)

        # Meta
        self.assertEqual(data["meta"]["team_size"], 2)

        # Summary (strictly Company A: 2 prospects, 1 lead_qualified, 1 non-LQ, 1 call, 2 emails_sent, etc.)
        s = data["summary"]
        self.assertEqual(s["prospects_entered"], 2)
        self.assertEqual(s["active_pre_users"], 2)
        self.assertEqual(s["lead_qualified"], 1)
        self.assertEqual(s["not_lead_qualified"], 1)
        self.assertEqual(s["meetings_attended"], 1)
        self.assertEqual(s["calls_logged"], 1)
        self.assertEqual(s["emails_sent"], 2)  # 1 EmailThreadMessage OUTBOUND + 1 unlinked OutreachEmail (no double count)
        self.assertEqual(s["emails_received"], 1)
        self.assertEqual(s["emails_opened"], 2)
        self.assertEqual(s["whatsapp_outbound"], 1)  # deleted message excluded
        self.assertEqual(s["whatsapp_inbound"], 1)
        self.assertEqual(s["whatsapp_ai_replies"], 1)
        self.assertEqual(s["meetings_created_today"], 1)
        self.assertEqual(s["upcoming_meetings_7d"], 1)
        self.assertEqual(s["pending_tasks_total"], 2)
        self.assertEqual(s["email_reply_pending"], 1)
        self.assertEqual(s["whatsapp_escalation_pending"], 1)
        self.assertEqual(s["tasks_completed_today"], 1)
        self.assertEqual(s["pending_audit_reverifications"], 1)
        self.assertEqual(s["active_campaigns"], 1)
        self.assertEqual(s["whatsapp_sessions_ready"], 1)
        self.assertEqual(s["whatsapp_ai_enabled_sessions"], 1)
        self.assertEqual(s["waiting_email_replies"], 1)
        self.assertEqual(s["replied_email_threads"], 1)

        # Funnel (real Outreach stages only, no unused Hot Lead / Nurture / Disqualified)
        funnel = data["pipeline_funnel"]
        self.assertEqual(funnel["total"], 2)
        self.assertEqual(funnel["lead_qualified"], 1)
        self.assertEqual(funnel["lead_freeze"], 1)
        self.assertEqual(funnel["received_response"], 0)
        self.assertEqual(funnel["waiting_for_response"], 0)
        self.assertEqual(funnel["call_follow_up"], 0)
        self.assertEqual(funnel["ready_for_outreach"], 0)
        self.assertNotIn("hot_lead", funnel)
        self.assertNotIn("nurture", funnel)
        self.assertNotIn("disqualified", funnel)
        self.assertEqual(funnel["conversion_rate"], 50.0)

        # Unified team_performance with integration health
        team_map = {m["user_id"]: m for m in data["team_performance"]}
        self.assertEqual(set(team_map.keys()), {self.pre_a1.id, self.pre_a2.id})
        self.assertNotIn(self.pre_b1.id, team_map)

        m1 = team_map[self.pre_a1.id]
        self.assertEqual(m1["prospects_entered"], 1)
        self.assertEqual(m1["lead_qualified"], 1)
        self.assertEqual(m1["emails_sent"], 1)
        self.assertTrue(m1["integrations"]["gmail_connected"])
        self.assertTrue(m1["integrations"]["google_calendar_connected"])
        self.assertTrue(m1["integrations"]["zoom_connected"])
        self.assertEqual(m1["integrations"]["whatsapp_status"], "READY")
        self.assertTrue(m1["integrations"]["whatsapp_ai_enabled"])

        m2 = team_map[self.pre_a2.id]
        self.assertFalse(m2["integrations"]["gmail_connected"])
        self.assertEqual(m2["integrations"]["whatsapp_status"], "NOT_LINKED")
        self.assertEqual(m2["emails_sent"], 1)

        # WhatsApp overview
        self.assertEqual(len(data["whatsapp_overview"]["sessions"]), 1)
        self.assertEqual(data["whatsapp_overview"]["ai_metrics"]["ai_meetings_scheduled_today"], 1)

        # Meetings overview
        self.assertEqual(data["meetings_overview"]["recordings_completed"], 1)
        self.assertEqual(data["meetings_overview"]["transcriptions_completed"], 1)
        self.assertEqual(len(data["meetings_overview"]["upcoming"]), 1)
        self.assertEqual(data["meetings_overview"]["upcoming"][0]["company_name"], "Acme Energy")

        # Campaigns overview
        self.assertEqual(len(data["campaigns_overview"]["recent_campaigns"]), 1)
        self.assertEqual(data["campaigns_overview"]["recent_campaigns"][0]["sent_count"], 1)
        self.assertEqual(data["campaigns_overview"]["recent_campaigns"][0]["total_count"], 2)

        # Live feed must not leak Company B prospects
        feed_titles = " ".join(item["title"] for item in data["live_feed"])
        self.assertIn("Acme Energy", feed_titles)
        self.assertNotIn("Secret Beta Corp", feed_titles)

    def test_superuser_sees_all_companies(self):
        self.client.force_authenticate(user=self.superuser)
        res = self.client.get(f"/api/manager-dashboard/?date={self.today_str}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["summary"]["prospects_entered"], 3)
        self.assertEqual(res.data["summary"]["pending_audit_reverifications"], 2)

    def test_manager_audit_unified_samples_and_tracker(self):
        self.client.force_authenticate(user=self.manager_a)
        res = self.client.get(f"/api/manager-dashboard/audit/?date={self.today_str}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data

        self.assertNotIn("audit_samples", data)
        self.assertEqual(data["summary"]["total_entered"], 2)
        self.assertEqual(data["summary"]["total_sampled"], 2)
        self.assertEqual(data["summary"]["pending_reverifications"], 1)

        samples_by_uid = {g["pre_user_id"]: g for g in data["pre_audit_samples"]}
        self.assertEqual(set(samples_by_uid.keys()), {self.pre_a1.id, self.pre_a2.id})
        p1_sample = samples_by_uid[self.pre_a1.id]["sample"][0]
        self.assertEqual(p1_sample["company_name"], "Acme Energy")
        self.assertEqual(p1_sample["qualification_status"], "Lead Qualified")
        self.assertTrue(p1_sample["attended_meeting"])
        self.assertGreaterEqual(len(p1_sample["daily_activities"]), 2)

        # Re-verification tracker scoped to Company A
        self.assertEqual(len(data["reverification_requests"]), 1)
        self.assertEqual(data["reverification_requests"][0]["prospect_company_name"], "Acme Energy")

        # Optional ?include_audit=1 on manager-dashboard
        res_with_audit = self.client.get(f"/api/manager-dashboard/?date={self.today_str}&include_audit=1")
        self.assertEqual(res_with_audit.status_code, status.HTTP_200_OK)
        self.assertIn("audit_samples", res_with_audit.data)
        self.assertEqual(len(res_with_audit.data["audit_samples"]), 2)

    def test_real_outreach_pipeline_funnel_stages(self):
        # Create one prospect for each remaining real Outreach stage:
        # received_response, waiting_for_response, call_follow_up, ready_for_outreach
        p_replied = Prospect.objects.create(
            company_name="Replied Co",
            country_head_office="UK",
            complete_address="London",
            primary_industries="FinTech",
            company_structure=Prospect.Structure.PARENT,
            operational_status=Prospect.Status.ACTIVE,
            primary_offering_type=Prospect.OfferingType.SOLUTIONS,
            created_by=self.pre_a1.username,
        )
        p_replied.lead_qualification.email_status = "Received Response"
        p_replied.lead_qualification.save(update_fields=["email_status"])

        p_waiting = Prospect.objects.create(
            company_name="Waiting Co",
            country_head_office="UK",
            complete_address="London",
            primary_industries="FinTech",
            company_structure=Prospect.Structure.PARENT,
            operational_status=Prospect.Status.ACTIVE,
            primary_offering_type=Prospect.OfferingType.SOLUTIONS,
            created_by=self.pre_a1.username,
        )
        p_waiting.lead_qualification.email_status = "Waiting for Response"
        p_waiting.lead_qualification.save(update_fields=["email_status"])

        p_called = Prospect.objects.create(
            company_name="Called Co",
            country_head_office="UK",
            complete_address="London",
            primary_industries="FinTech",
            company_structure=Prospect.Structure.PARENT,
            operational_status=Prospect.Status.ACTIVE,
            primary_offering_type=Prospect.OfferingType.SOLUTIONS,
            created_by=self.pre_a2.username,
        )
        CallActivity.objects.create(
            prospect=p_called,
            created_by=self.pre_a2,
            call_status="Connected",
            communication_outcome="Call Back Later",
        )

        Prospect.objects.create(
            company_name="Fresh Ready Co",
            country_head_office="UK",
            complete_address="London",
            primary_industries="FinTech",
            company_structure=Prospect.Structure.PARENT,
            operational_status=Prospect.Status.ACTIVE,
            primary_offering_type=Prospect.OfferingType.SOLUTIONS,
            created_by=self.pre_a2.username,
        )

        self.client.force_authenticate(user=self.manager_a)
        res = self.client.get(f"/api/manager-dashboard/?date={self.today_str}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        funnel = res.data["pipeline_funnel"]
        self.assertEqual(funnel["total"], 6)
        self.assertEqual(funnel["lead_qualified"], 1)
        self.assertEqual(funnel["lead_freeze"], 1)
        self.assertEqual(funnel["received_response"], 1)
        self.assertEqual(funnel["waiting_for_response"], 1)
        self.assertEqual(funnel["call_follow_up"], 1)
        self.assertEqual(funnel["ready_for_outreach"], 1)
