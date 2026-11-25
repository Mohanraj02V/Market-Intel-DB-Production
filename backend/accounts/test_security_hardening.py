import hashlib
import hmac
import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import UserProfile
from accounts.template_utils import convert_base64_images_to_cid
from companies.models import Company
from digital_marketing.models import SocialAccountConnection
from digital_marketing.serializers import SocialAccountConnectionSerializer
from prospects.models import CallbackReminder, LeadQualification, Meeting, OutreachEmail, PreTask, Prospect
from utils.url_security import is_ip_publicly_routable, validate_safe_external_url


def _create_user(username, role='PRE', company=None, is_superuser=False):
    user = User.objects.create_user(
        username=username,
        email=f'{username}@example.com',
        password='StrongPassword123!',
        is_superuser=is_superuser,
        is_staff=is_superuser,
    )
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.role = role
    profile.company = company
    profile.timezone = 'UTC'
    profile.save()
    user.profile = profile
    return user


class EnterpriseSecurityHardeningTests(TestCase):
    def setUp(self):
        self.co_a = Company.objects.create(name='Alpha Co', code='ALPHA')
        self.co_b = Company.objects.create(name='Beta Co', code='BETA')
        self.pre_a = _create_user('pre_alpha', role='PRE', company=self.co_a)
        self.pre_b = _create_user('pre_beta', role='PRE', company=self.co_b)
        self.mgr_a = _create_user('mgr_alpha', role='MANAGER', company=self.co_a)
        self.dm_a = _create_user('dm_alpha', role='DM', company=self.co_a)

    # ── 1. Health & CSRF endpoints ──────────────────────────────────────────
    def test_health_endpoint_returns_ok_without_leaking_secrets(self):
        client = APIClient()
        res = client.get('/api/health/')
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body, {'status': 'ok', 'database': 'ok'})

    def test_cookie_jwt_enforces_csrf_on_unsafe_methods_and_allows_with_token(self):
        csrf_client = APIClient(enforce_csrf_checks=True)
        refresh = RefreshToken.for_user(self.pre_a)
        access = str(refresh.access_token)

        # Fetch CSRF cookie & token
        csrf_res = csrf_client.get('/api/auth/csrf/')
        self.assertEqual(csrf_res.status_code, 200)
        csrf_token = csrf_res.data['csrfToken']
        self.assertTrue(bool(csrf_token))

        # Authenticate purely via HttpOnly cookie
        csrf_client.cookies['access_token'] = access

        # Safe GET works with cookie
        me_res = csrf_client.get('/api/auth/me/')
        self.assertEqual(me_res.status_code, 200)

        # Unsafe PATCH without X-CSRFToken MUST be rejected (403)
        blocked = csrf_client.patch('/api/auth/me/', {'timezone': 'UTC'}, format='json')
        self.assertEqual(blocked.status_code, 403)

        # Unsafe PATCH WITH X-CSRFToken MUST succeed (200)
        allowed = csrf_client.patch(
            '/api/auth/me/',
            {'timezone': 'UTC'},
            format='json',
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(allowed.status_code, 200)

        # Bearer header auth works on unsafe PATCH without CSRF token
        bearer_client = APIClient(enforce_csrf_checks=True)
        bearer_res = bearer_client.patch(
            '/api/auth/me/',
            {'timezone': 'UTC'},
            format='json',
            HTTP_AUTHORIZATION=f'Bearer {access}',
        )
        self.assertEqual(bearer_res.status_code, 200)

    # ── 2. CID Local File Read / Path Traversal & SVG Upload ────────────────
    def test_cid_inliner_blocks_path_traversal_and_rag_private(self):
        html_traversal = '<img src="/media/../../backend/.env">'
        out1, imgs1 = convert_base64_images_to_cid(html_traversal)
        self.assertEqual(imgs1, [])
        self.assertEqual(out1, html_traversal)

        html_rag = '<img src="/media/rag_private/secret.png">'
        out2, imgs2 = convert_base64_images_to_cid(html_rag)
        self.assertEqual(imgs2, [])
        self.assertEqual(out2, html_rag)

    def test_template_image_upload_blocks_svg_xss(self):
        client = APIClient()
        client.force_authenticate(user=self.pre_a)
        svg_file = SimpleUploadedFile(
            'evil.svg',
            b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"></svg>',
            content_type='image/svg+xml',
        )
        res = client.post('/api/auth/email-templates/upload-image/', {'file': svg_file}, format='multipart')
        self.assertEqual(res.status_code, 400)

    # ── 3. SSRF Protection (IPv4, IPv6, Cloud Metadata, Mapped IPv6) ────────
    def test_ssrf_validator_blocks_private_ipv4_ipv6_and_metadata(self):
        self.assertFalse(is_ip_publicly_routable('127.0.0.1'))
        self.assertFalse(is_ip_publicly_routable('10.0.0.5'))
        self.assertFalse(is_ip_publicly_routable('169.254.169.254'))
        self.assertFalse(is_ip_publicly_routable('100.64.0.1'))
        self.assertFalse(is_ip_publicly_routable('0.0.0.0'))
        self.assertFalse(is_ip_publicly_routable('::1'))
        self.assertFalse(is_ip_publicly_routable('fe80::1'))
        self.assertFalse(is_ip_publicly_routable('fc00::1'))
        self.assertFalse(is_ip_publicly_routable('::ffff:127.0.0.1'))
        self.assertFalse(is_ip_publicly_routable('::ffff:169.254.169.254'))
        self.assertTrue(is_ip_publicly_routable('8.8.8.8'))

        ok_meta, _ = validate_safe_external_url('http://169.254.169.254/latest/meta-data/')
        self.assertFalse(ok_meta)
        ok_scheme, _ = validate_safe_external_url('file:///etc/passwd')
        self.assertFalse(ok_scheme)

    def test_search_console_inspect_blocks_ssrf_metadata_url(self):
        client = APIClient()
        client.force_authenticate(user=self.dm_a)
        res = client.post(
            '/api/digital-marketing/cms/search-console/indexing/',
            {'action': 'INSPECT', 'page_url': 'http://169.254.169.254/latest/meta-data/'},
            format='json',
        )
        self.assertEqual(res.status_code, 400)

    # ── 4. Meta Webhook HMAC & Plaintext Token Stripping ────────────────────
    @patch.dict('os.environ', {'META_APP_SECRET': 'meta-secret-xyz'})
    def test_meta_webhook_rejects_unsigned_and_invalid_signature(self):
        client = APIClient()
        body = json.dumps({'object': 'instagram', 'entry': []}).encode('utf-8')

        # Missing signature -> 403
        res_no_sig = client.post('/api/digital-marketing/webhooks/meta/', data=body, content_type='application/json')
        self.assertEqual(res_no_sig.status_code, 403)

        # Bad signature -> 403
        res_bad = client.post(
            '/api/digital-marketing/webhooks/meta/',
            data=body,
            content_type='application/json',
            HTTP_X_HUB_SIGNATURE_256='sha256=deadbeef',
        )
        self.assertEqual(res_bad.status_code, 403)

        # Valid signature -> 200
        good_sig = 'sha256=' + hmac.new(b'meta-secret-xyz', body, hashlib.sha256).hexdigest()
        res_ok = client.post(
            '/api/digital-marketing/webhooks/meta/',
            data=body,
            content_type='application/json',
            HTTP_X_HUB_SIGNATURE_256=good_sig,
        )
        self.assertEqual(res_ok.status_code, 200)

    def test_social_connection_serializer_strips_token_keys_from_metadata(self):
        conn = SocialAccountConnection.objects.create(
            user=self.dm_a,
            platform='INSTAGRAM',
            account_id='ig_12345',
            account_name='Brand',
            metadata={'page_id': 'p1', 'page_access_token': 'SECRET_TOKEN', 'followers_count': 42},
        )
        data = SocialAccountConnectionSerializer(conn).data
        self.assertEqual(data['metadata'].get('page_id'), 'p1')
        self.assertEqual(data['metadata'].get('followers_count'), 42)
        self.assertNotIn('page_access_token', data['metadata'])

    # ── 5. Multi-Tenant & Role IDOR Regression Tests ────────────────────────
    def test_idor_fixes_across_prospects_tasks_reminders_meetings_and_users(self):
        prospect_b = Prospect.objects.create(
            company_name='Beta Secret Corp',
            country_head_office='US',
            company_structure='Parent',
            operational_status='Active',
            created_by=self.pre_b.username,
        )
        lq_b, _ = LeadQualification.objects.get_or_create(prospect=prospect_b)
        email_b = OutreachEmail.objects.create(
            prospect=prospect_b,
            created_by=self.pre_b,
            from_email='pre_b@beta.test',
            subject='Confidential Offer',
            body='<p>Secret</p>',
            open_tracking_enabled=True,
        )
        task_b = PreTask.objects.create(
            assigned_pre=self.pre_b,
            prospect=prospect_b,
            title='Follow up Beta',
        )
        CallbackReminder.objects.create(
            prospect=prospect_b,
            scheduled_datetime=timezone.now() + timezone.timedelta(hours=2),
        )
        Meeting.objects.create(
            prospect=prospect_b,
            created_by=self.pre_b,
            scheduled_datetime=timezone.now() + timezone.timedelta(hours=3),
            meeting_provider='GOOGLE_MEET',
        )

        # PRE A cannot access PRE B's LQ record via Prospect UUID fallback
        client_a = APIClient()
        client_a.force_authenticate(user=self.pre_a)
        self.assertEqual(client_a.get(f'/api/lq-pipeline/{prospect_b.id}/').status_code, 404)

        # PRE A cannot read PRE B's OutreachEmail tracking-stats
        self.assertEqual(client_a.get(f'/api/outreach/emails/{email_b.id}/tracking-stats/').status_code, 404)

        # PRE A cannot access PRE B's PreTask
        self.assertEqual(client_a.get(f'/api/pre-tasks/{task_b.id}/').status_code, 404)

        # PRE A cannot trigger global meeting automation poll
        self.assertEqual(client_a.post('/api/auth/calendar/automation/poll/', {}).status_code, 403)

        # DM cannot access PreTask, CallbackReminder, Meeting, OutreachEmail, or email_ai
        client_dm = APIClient()
        client_dm.force_authenticate(user=self.dm_a)
        self.assertEqual(client_dm.get('/api/pre-tasks/').status_code, 403)
        self.assertEqual(client_dm.get('/api/outreach/emails/').status_code, 403)
        self.assertEqual(client_dm.get('/api/meetings/').status_code, 403)
        self.assertEqual(client_dm.get('/api/reminders/').status_code, 403)
        self.assertEqual(
            client_dm.post('/api/email-ai/generate/', {'prompt': 'hi', 'prospect_id': str(prospect_b.id)}).status_code,
            403,
        )

        # Manager of Company A only sees Company A users in UserViewSet (not Company B)
        client_mgr = APIClient()
        client_mgr.force_authenticate(user=self.mgr_a)
        res_users = client_mgr.get('/api/auth/users/')
        self.assertEqual(res_users.status_code, 200)
        results = res_users.data['results'] if isinstance(res_users.data, dict) else res_users.data
        usernames = {u['username'] for u in results}
        self.assertIn(self.pre_a.username, usernames)
        self.assertNotIn(self.pre_b.username, usernames)
