"""Comprehensive tests for Meeting Providers & Calendar Integrations:
1. Google Meet
2. Zoom Meetings
3. Microsoft Teams Meetings

Tests all OAuth flows, meeting creation, calendar sync, credential encryption,
idempotency / duplicate prevention, cross-user isolation, and error handling.
"""
import io
import json
import os
import urllib.error
from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

import utils.encryption as encryption

if not os.environ.get('MAIL_CREDENTIALS_ENCRYPTION_KEY'):
    os.environ['MAIL_CREDENTIALS_ENCRYPTION_KEY'] = encryption.Fernet.generate_key().decode('utf-8')

from accounts import calendar_services as cal
from accounts import zoom_services as zoom
from accounts import microsoft_services as ms
from accounts.models import (
    GoogleCalendarCredentials,
    ZoomCredentials,
    MicrosoftCalendarCredentials,
)
from prospects.models import LeadQualification, Meeting, Prospect, ProspectContact

MEET_URL = 'https://meet.google.com/abc-defg-hij'
ZOOM_JOIN_URL = 'https://us05web.zoom.us/j/1234567890?pwd=xyz'
TEAMS_JOIN_URL = 'https://teams.microsoft.com/l/meetup-join/19%3ameeting_xyz%40thread.v2/0'

TEST_SETTINGS = dict(
    GOOGLE_OAUTH_CLIENT_ID='google-client-id',
    GOOGLE_OAUTH_CLIENT_SECRET='google-client-secret',
    CALENDAR_OAUTH_REDIRECT_URI='http://localhost:5173/auth/calendar/callback',
    ZOOM_CLIENT_ID='zoom-client-id',
    ZOOM_CLIENT_SECRET='zoom-client-secret',
    ZOOM_OAUTH_REDIRECT_URI='http://localhost:5173/auth/zoom/callback',
    MICROSOFT_CLIENT_ID='ms-client-id',
    MICROSOFT_CLIENT_SECRET='ms-client-secret',
    MICROSOFT_OAUTH_REDIRECT_URI='http://localhost:5173/auth/microsoft/callback',
)


def _user(name, role, tz='UTC'):
    u = User.objects.create_user(username=f'{name}@example.com', email=f'{name}@example.com', password='Password123!')
    u.profile.role = role
    u.profile.timezone = tz
    u.profile.save()
    return u


def make_prospect(user, name='Acme Global'):
    p = Prospect.objects.create(
        company_name=name,
        country_head_office='IN',
        primary_industries='IT',
        company_structure='Parent',
        operational_status='Active',
        primary_offering_type='Products',
        official_website_url='https://acme.test',
        created_by=user.username,
    )
    lqual, _ = LeadQualification.objects.get_or_create(prospect=p)
    lqual.assigned_lq = user
    lqual.save()
    return p


class FakeResp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode('utf-8')

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def close(self):
        pass


def http_error(code, payload):
    return urllib.error.HTTPError('http://test', code, 'err', {}, io.BytesIO(json.dumps(payload).encode('utf-8')))


class FakeHttp:
    """Queued urlopen simulator recording calls and returning responses."""
    def __init__(self, *queue):
        self.queue = list(queue)
        self.calls = []

    def __call__(self, req, timeout=None):
        body = None
        if req.data:
            try:
                body = json.loads(req.data.decode('utf-8'))
            except Exception:
                body = req.data.decode('utf-8', errors='ignore')
        self.calls.append({
            'method': req.get_method(),
            'url': req.full_url,
            'body': body,
            'auth': req.headers.get('Authorization'),
        })
        if not self.queue:
            return FakeResp({})
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResp(item)


@override_settings(**TEST_SETTINGS)
class MeetingProvidersOAuthTests(APITestCase):
    def setUp(self):
        self.lq = _user('lq_tester', 'LQ')
        self.lq2 = _user('lq_other', 'LQ')
        self.client.force_authenticate(user=self.lq)

    # ── Status endpoint ────────────────────────────────────────────────────────
    def test_unified_providers_status_endpoint(self):
        r = self.client.get('/api/auth/meeting-providers/status/')
        self.assertEqual(r.status_code, 200)
        data = r.data
        self.assertIn('google_meet', data)
        self.assertIn('zoom', data)
        self.assertIn('ms_teams', data)
        self.assertFalse(data['google_meet']['is_connected'])
        self.assertFalse(data['zoom']['is_connected'])
        self.assertFalse(data['ms_teams']['is_connected'])

    # ── Zoom OAuth Flow ───────────────────────────────────────────────────────
    def test_zoom_oauth_url_and_state(self):
        r = self.client.get('/api/auth/zoom/url/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('https://zoom.us/oauth/authorize', r.data['url'])
        self.assertIn('client_id=zoom-client-id', r.data['url'])
        state = r.data['state']
        self.assertTrue(zoom.ZoomOAuthService.verify_state(state, self.lq.id, consume=False))
        # Tampered or mismatched user is rejected
        self.assertFalse(zoom.ZoomOAuthService.verify_state(state, self.lq2.id, consume=False))

    def test_zoom_callback_and_storage(self):
        state = self.client.get('/api/auth/zoom/url/').data['state']
        fake = FakeHttp(
            {'access_token': 'zoom-token-123', 'refresh_token': 'zoom-ref-123', 'expires_in': 3600, 'scope': 'meeting:write'},
            {'id': 'zoom-usr-1', 'email': 'zoom_user@example.com'}
        )
        with mock.patch('accounts.zoom_services.urllib.request.urlopen', fake):
            r = self.client.post('/api/auth/zoom/callback/', {'code': 'code123', 'state': state}, format='json')
        self.assertEqual(r.status_code, 200)
        creds = ZoomCredentials.objects.get(user=self.lq)
        self.assertTrue(creds.is_active)
        self.assertEqual(encryption.decrypt_password(creds.access_token_encrypted), 'zoom-token-123')
        self.assertEqual(encryption.decrypt_password(creds.refresh_token_encrypted), 'zoom-ref-123')
        self.assertNotIn('zoom-token-123', json.dumps(r.data))

    def test_zoom_disconnect(self):
        ZoomCredentials.objects.create(
            user=self.lq,
            email=self.lq.email,
            access_token_encrypted=encryption.encrypt_password('z-tok'),
            refresh_token_encrypted=encryption.encrypt_password('z-ref'),
            is_active=True,
        )
        with mock.patch.object(zoom.ZoomOAuthService, 'revoke'):
            r = self.client.post('/api/auth/zoom/disconnect/')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(ZoomCredentials.objects.filter(user=self.lq).exists())

    # ── Microsoft OAuth Flow ──────────────────────────────────────────────────
    def test_microsoft_oauth_url_and_state(self):
        r = self.client.get('/api/auth/microsoft/url/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('https://login.microsoftonline.com', r.data['url'])
        self.assertIn('client_id=ms-client-id', r.data['url'])
        state = r.data['state']
        self.assertTrue(ms.MicrosoftOAuthService.verify_state(state, self.lq.id, consume=False))
        self.assertFalse(ms.MicrosoftOAuthService.verify_state(state, self.lq2.id, consume=False))

    def test_microsoft_callback_and_storage(self):
        state = self.client.get('/api/auth/microsoft/url/').data['state']
        fake = FakeHttp(
            {'access_token': 'ms-token-123', 'refresh_token': 'ms-ref-123', 'expires_in': 3600, 'scope': 'Calendars.ReadWrite'},
            {'id': 'ms-usr-1', 'mail': 'ms_user@example.com', 'userPrincipalName': 'ms_user@example.com'}
        )
        with mock.patch('accounts.microsoft_services.urllib.request.urlopen', fake):
            r = self.client.post('/api/auth/microsoft/callback/', {'code': 'code123', 'state': state}, format='json')
        self.assertEqual(r.status_code, 200)
        creds = MicrosoftCalendarCredentials.objects.get(user=self.lq)
        self.assertTrue(creds.is_active)
        self.assertEqual(encryption.decrypt_password(creds.access_token_encrypted), 'ms-token-123')
        self.assertEqual(encryption.decrypt_password(creds.refresh_token_encrypted), 'ms-ref-123')


@override_settings(**TEST_SETTINGS)
class MeetingCreationMultiProviderTests(APITestCase):
    def setUp(self):
        self.lq = _user('lq_scheduler', 'LQ', tz='UTC')
        self.lq2 = _user('lq_other', 'LQ')
        self.client.force_authenticate(user=self.lq)
        self.prospect = make_prospect(self.lq, name='Stark Industries')
        self.contact = ProspectContact.objects.create(
            prospect=self.prospect, contact_name='Pepper Potts', designation='CEO', official_email='pepper@stark.test'
        )

    def payload(self, provider, req_id='req-test-12345'):
        return {
            'prospect': self.prospect.id,
            'prospect_contact': self.contact.id,
            'scheduled_datetime': '2026-11-20T10:00:00Z',
            'agenda': 'Strategic Partnership Discussion',
            'meeting_provider': provider,
            'client_request_id': req_id,
        }

    # ── Rejection of MANUAL provider ──────────────────────────────────────────
    def test_manual_provider_rejected(self):
        r = self.client.post('/api/meetings/', self.payload('MANUAL'), format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data.get('code'), 'manual_calendar_removed')

    def test_invalid_provider_rejected(self):
        r = self.client.post('/api/meetings/', self.payload('UNKNOWN_PLATFORM'), format='json')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data.get('code'), 'invalid_provider')

    # ── Google Meet Creation ──────────────────────────────────────────────────
    def test_google_meet_creation_success(self):
        GoogleCalendarCredentials.objects.create(
            user=self.lq, email=self.lq.email,
            access_token_encrypted=encryption.encrypt_password('g-access'),
            refresh_token_encrypted=encryption.encrypt_password('g-refresh'),
            token_expiry=timezone.now() + timedelta(hours=1),
            scopes='https://www.googleapis.com/auth/calendar.events',
            is_active=True,
        )
        fake_google_event = {
            'id': 'g_evt_123',
            'conferenceData': {
                'createRequest': {'status': {'statusCode': 'success'}},
                'entryPoints': [{'entryPointType': 'video', 'uri': MEET_URL}]
            },
            'hangoutLink': MEET_URL,
        }
        fake = FakeHttp(fake_google_event)
        with mock.patch('accounts.calendar_services.urllib.request.urlopen', fake):
            r = self.client.post('/api/meetings/', self.payload('GOOGLE_MEET', 'req-gmeet-001'), format='json')

        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['meeting_provider'], 'GOOGLE_MEET')
        self.assertEqual(r.data['meeting_link'], MEET_URL)

        meeting = Meeting.objects.get(client_request_id='req-gmeet-001')
        self.assertEqual(meeting.meeting_link, MEET_URL)
        self.assertEqual(meeting.meeting_provider, 'GOOGLE_MEET')
        self.assertEqual(meeting.calendar_event_id, 'g_evt_123')
        self.assertEqual(meeting.created_by, self.lq)
        self.assertEqual(meeting.prospect_contact, self.contact)

    def test_include_all_contacts_invites_all_key_persons_with_email(self):
        contact2 = ProspectContact.objects.create(
            prospect=self.prospect, contact_name='Happy Hogan', designation='Head of Security', official_email='happy@stark.test'
        )
        GoogleCalendarCredentials.objects.create(
            user=self.lq, email=self.lq.email,
            access_token_encrypted=encryption.encrypt_password('g-access'),
            refresh_token_encrypted=encryption.encrypt_password('g-refresh'),
            token_expiry=timezone.now() + timedelta(hours=1),
            scopes='https://www.googleapis.com/auth/calendar.events',
            is_active=True,
        )
        fake_google_event = {
            'id': 'g_evt_multi_1',
            'conferenceData': {'createRequest': {'status': {'statusCode': 'success'}}, 'entryPoints': [{'entryPointType': 'video', 'uri': MEET_URL}]},
            'hangoutLink': MEET_URL,
        }
        fake = FakeHttp(fake_google_event)
        payload = self.payload('GOOGLE_MEET', 'req-gmeet-multi-01')
        payload['include_all_contacts'] = True

        with mock.patch('accounts.calendar_services.urllib.request.urlopen', fake):
            r = self.client.post('/api/meetings/', payload, format='json')

        self.assertEqual(r.status_code, 201, r.data)
        call_body = fake.calls[0]['body']
        attendee_emails = [a['email'] for a in call_body.get('attendees', [])]
        self.assertIn('pepper@stark.test', attendee_emails)
        self.assertIn('happy@stark.test', attendee_emails)

    # ── Zoom Meeting Creation ─────────────────────────────────────────────────
    def test_zoom_not_connected_returns_actionable_error(self):
        r = self.client.post('/api/meetings/', self.payload('ZOOM', 'req-zoom-001'), format='json')
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data.get('code'), 'zoom_not_connected')

    def test_zoom_creation_success_with_google_calendar_sync(self):
        ZoomCredentials.objects.create(
            user=self.lq, email='host@zoom.test',
            access_token_encrypted=encryption.encrypt_password('zoom-tok'),
            refresh_token_encrypted=encryption.encrypt_password('zoom-ref'),
            token_expiry=timezone.now() + timedelta(hours=1),
            is_active=True,
        )
        GoogleCalendarCredentials.objects.create(
            user=self.lq, email=self.lq.email,
            access_token_encrypted=encryption.encrypt_password('g-access'),
            refresh_token_encrypted=encryption.encrypt_password('g-refresh'),
            token_expiry=timezone.now() + timedelta(hours=1),
            scopes='https://www.googleapis.com/auth/calendar.events',
            is_active=True,
        )

        zoom_resp = {
            'id': 9876543210,
            'join_url': ZOOM_JOIN_URL,
            'start_url': 'https://us05web.zoom.us/s/9876543210',
            'password': 'secretpassword',
        }
        cal_resp = {'id': 'cal_evt_zoom_123'}

        fake_zoom = FakeHttp(zoom_resp)
        fake_cal = FakeHttp(cal_resp)

        def dispatch_urlopen(req, timeout=None):
            if 'zoom.us' in req.full_url:
                return fake_zoom(req, timeout=timeout)
            return fake_cal(req, timeout=timeout)

        with mock.patch('urllib.request.urlopen', side_effect=dispatch_urlopen):
            r = self.client.post('/api/meetings/', self.payload('ZOOM', 'req-zoom-002'), format='json')

        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['meeting_provider'], 'ZOOM')
        self.assertEqual(r.data['meeting_link'], ZOOM_JOIN_URL)

        meeting = Meeting.objects.get(client_request_id='req-zoom-002')
        self.assertEqual(meeting.meeting_link, ZOOM_JOIN_URL)
        self.assertEqual(meeting.provider_meeting_id, '9876543210')
        self.assertEqual(meeting.meeting_provider, 'ZOOM')
        self.assertEqual(meeting.calendar_type, 'GOOGLE_CALENDAR')
        self.assertEqual(meeting.created_by, self.lq)

    # ── Microsoft Teams Meeting Creation ──────────────────────────────────────
    def test_ms_teams_not_connected_returns_actionable_error(self):
        r = self.client.post('/api/meetings/', self.payload('MS_TEAMS', 'req-teams-001'), format='json')
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data.get('code'), 'microsoft_not_connected')

    def test_ms_teams_creation_success(self):
        MicrosoftCalendarCredentials.objects.create(
            user=self.lq, email='host@office.test',
            access_token_encrypted=encryption.encrypt_password('ms-access'),
            refresh_token_encrypted=encryption.encrypt_password('ms-refresh'),
            token_expiry=timezone.now() + timedelta(hours=1),
            is_active=True,
        )

        teams_event_resp = {
            'id': 'ms_event_999',
            'onlineMeeting': {
                'joinUrl': TEAMS_JOIN_URL,
                'conferenceId': 'conf-teams-123',
            },
            'onlineMeetingUrl': TEAMS_JOIN_URL,
        }
        fake = FakeHttp(teams_event_resp)
        with mock.patch('accounts.microsoft_services.urllib.request.urlopen', fake):
            r = self.client.post('/api/meetings/', self.payload('MS_TEAMS', 'req-teams-002'), format='json')

        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['meeting_provider'], 'MS_TEAMS')
        self.assertEqual(r.data['meeting_link'], TEAMS_JOIN_URL)

        meeting = Meeting.objects.get(client_request_id='req-teams-002')
        self.assertEqual(meeting.meeting_link, TEAMS_JOIN_URL)
        self.assertEqual(meeting.calendar_event_id, 'ms_event_999')
        self.assertEqual(meeting.meeting_provider, 'MS_TEAMS')
        self.assertEqual(meeting.calendar_type, 'OUTLOOK_CALENDAR')
        self.assertEqual(meeting.created_by, self.lq)

    # ── Idempotency / Duplicate Prevention ────────────────────────────────────
    def test_duplicate_submission_returns_existing_meeting(self):
        MicrosoftCalendarCredentials.objects.create(
            user=self.lq, email='host@office.test',
            access_token_encrypted=encryption.encrypt_password('ms-access'),
            refresh_token_encrypted=encryption.encrypt_password('ms-refresh'),
            token_expiry=timezone.now() + timedelta(hours=1),
            is_active=True,
        )
        fake = FakeHttp({'id': 'evt_single', 'onlineMeeting': {'joinUrl': TEAMS_JOIN_URL}})
        with mock.patch('accounts.microsoft_services.urllib.request.urlopen', fake):
            r1 = self.client.post('/api/meetings/', self.payload('MS_TEAMS', 'req-idemp-001'), format='json')
            self.assertEqual(r1.status_code, 201)

            # Second call with same client_request_id returns original meeting (200 OK)
            r2 = self.client.post('/api/meetings/', self.payload('MS_TEAMS', 'req-idemp-001'), format='json')
            self.assertEqual(r2.status_code, 200)
            self.assertEqual(r1.data['id'], r2.data['id'])
            self.assertEqual(Meeting.objects.filter(client_request_id='req-idemp-001').count(), 1)

    # ── Cross-User Credential Isolation ───────────────────────────────────────
    def test_user_cannot_use_another_users_zoom_or_microsoft_credentials(self):
        # lq2 has credentials, but authenticated lq has none
        ZoomCredentials.objects.create(
            user=self.lq2, email='lq2@zoom.test',
            access_token_encrypted=encryption.encrypt_password('lq2-tok'),
            refresh_token_encrypted=encryption.encrypt_password('lq2-ref'),
            token_expiry=timezone.now() + timedelta(hours=1),
            is_active=True,
        )
        r = self.client.post('/api/meetings/', self.payload('ZOOM', 'req-iso-001'), format='json')
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data.get('code'), 'zoom_not_connected')

    def test_participant_contact_ids_invites_selected_key_persons(self):
        c2 = ProspectContact.objects.create(
            prospect=self.prospect, contact_name='Happy Hogan', designation='Head of Security', official_email='happy@stark.test'
        )
        c3 = ProspectContact.objects.create(
            prospect=self.prospect, contact_name='Rhodey', designation='VP', official_email='rhodey@stark.test'
        )
        GoogleCalendarCredentials.objects.create(
            user=self.lq, email='lq_cal@example.com',
            access_token_encrypted=encryption.encrypt_password('tok'),
            refresh_token_encrypted=encryption.encrypt_password('ref'),
            token_expiry=timezone.now() + timedelta(hours=1),
            scopes='https://www.googleapis.com/auth/calendar.events',
            is_active=True,
        )
        fake = FakeHttp({
            'id': 'evt_google',
            'conferenceData': {
                'createRequest': {'status': {'statusCode': 'success'}},
                'entryPoints': [{'entryPointType': 'video', 'uri': MEET_URL}]
            },
            'hangoutLink': MEET_URL,
        })
        with mock.patch('accounts.calendar_services.urllib.request.urlopen', fake):
            pl = self.payload('GOOGLE_MEET', 'req-part-sel-01')
            pl['participant_contact_ids'] = [c2.id]
            r = self.client.post('/api/meetings/', pl, format='json')
            self.assertEqual(r.status_code, 201)
            created_call = fake.calls[0]['body']
            attendees = [a['email'] for a in created_call.get('attendees', [])]
            self.assertIn('pepper@stark.test', attendees)
            self.assertIn('happy@stark.test', attendees)
            self.assertNotIn('rhodey@stark.test', attendees)


