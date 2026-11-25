import hashlib
import hmac
import json
import time
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import (
    CalendarEventRecording,
    GoogleCalendarCredentials,
    MeetingAutomationJob,
    UserProfile,
    ZoomCredentials,
)
from accounts.meeting_automation_service import ingest_cbe_completed_webhook
from accounts.zoom_services import (
    ZoomAPIError,
    ZoomRecordingNotFoundError,
    ZoomScopeError,
    create_zoom_meeting,
    has_zoom_recording_scope,
)
from companies.models import Company
from prospects.models import Meeting
from transcriptions.models import MeetingTranscription
from transcriptions.services import (
    MAX_ZOOM_RETRIES,
    backfill_historical_transcriptions,
    create_or_update_pending_transcription,
    fetch_and_store_zoom_transcript,
    parse_vtt_transcript,
    process_pending_transcriptions,
)
from utils import encryption


SAMPLE_VTT = """WEBVTT

1
00:00:01.000 --> 00:00:05.500
Alice Smith: Welcome everyone to the quarterly market review.

2
00:00:06.000 --> 00:00:11.200
<v Bob Jones>Thanks Alice, let's walk through the APAC pipeline.</v>

3
00:01:25.000 --> 00:01:30.000
Alice Smith: Great, the deal closes next Tuesday.
"""


def _make_user(username, role='PRE', company=None, is_superuser=False):
    user = User.objects.create_user(
        username=username,
        email=f'{username}@example.com',
        password='TestPassword123!',
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


def _make_zoom_creds(user, scopes='meeting:write meeting:read user:read cloud_recording:read:list_recording_files'):
    return ZoomCredentials.objects.create(
        user=user,
        email=user.email,
        zoom_user_id=f'zoom_{user.id}',
        access_token_encrypted=encryption.encrypt_password('zoom-access-token'),
        refresh_token_encrypted=encryption.encrypt_password('zoom-refresh-token'),
        token_expiry=timezone.now() + timedelta(hours=1),
        scopes=scopes,
        is_active=True,
    )


def _make_calendar_creds(user):
    return GoogleCalendarCredentials.objects.create(
        user=user,
        email=user.email,
        access_token_encrypted=encryption.encrypt_password('gcal-access-token'),
        refresh_token_encrypted=encryption.encrypt_password('gcal-refresh-token'),
        token_expiry=timezone.now() + timedelta(hours=1),
        scopes='https://www.googleapis.com/auth/calendar.events',
        is_active=True,
    )


def _sign_zoom_webhook(secret, body_bytes, ts=None):
    ts_str = str(ts if ts is not None else int(time.time()))
    msg = f'v0:{ts_str}:{body_bytes.decode("utf-8")}'
    sig = 'v0=' + hmac.new(secret.encode('utf-8'), msg.encode('utf-8'), hashlib.sha256).hexdigest()
    return {
        'HTTP_X_ZM_REQUEST_TIMESTAMP': ts_str,
        'HTTP_X_ZM_SIGNATURE': sig,
    }


class VttParserTests(TestCase):
    def test_parse_vtt_extracts_speakers_timestamps_and_text(self):
        parsed = parse_vtt_transcript(SAMPLE_VTT)
        self.assertEqual(len(parsed['transcript_segments']), 3)
        self.assertEqual(parsed['participants'], ['Alice Smith', 'Bob Jones'])
        self.assertEqual(parsed['transcript_segments'][0]['start'], '00:00:01')
        self.assertEqual(parsed['transcript_segments'][0]['speaker'], 'Alice Smith')
        self.assertEqual(parsed['transcript_segments'][1]['speaker'], 'Bob Jones')
        self.assertIn('[00:01:25] Alice Smith: Great, the deal closes next Tuesday.', parsed['transcript_text'])

    def test_parse_empty_vtt(self):
        parsed = parse_vtt_transcript('WEBVTT\n\n')
        self.assertEqual(parsed['transcript_text'], '')
        self.assertEqual(parsed['transcript_segments'], [])
        self.assertEqual(parsed['participants'], [])


class ZoomTranscriptionTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Acme Corp')
        self.user = _make_user('pre_zoom', role='PRE', company=self.company)
        self.zoom_creds = _make_zoom_creds(self.user)

    def test_has_zoom_recording_scope_variants(self):
        self.assertTrue(has_zoom_recording_scope('meeting:write cloud_recording:read:list_recording_files'))
        self.assertTrue(has_zoom_recording_scope('cloud_recording:read:recording'))
        self.assertTrue(has_zoom_recording_scope('meeting:read recording:read'))
        self.assertFalse(has_zoom_recording_scope('meeting:write meeting:read user:read'))
        self.assertFalse(has_zoom_recording_scope(''))

    @patch('accounts.zoom_services.zoom_api_request')
    def test_create_zoom_meeting_falls_back_when_cloud_recording_unsupported(self, mock_req):
        mock_req.side_effect = [
            ZoomAPIError('Cloud recording is not enabled on this plan', status=400),
            {'id': 987654321, 'join_url': 'https://us02web.zoom.us/j/987654321', 'password': 'abc'},
        ]
        res = create_zoom_meeting(
            self.zoom_creds,
            summary='Demo Call',
            description='Agenda',
            start_dt=timezone.now() + timedelta(hours=1),
            tz_name='UTC',
            duration_minutes=30,
            enable_cloud_recording=True,
        )
        self.assertEqual(res['meeting_id'], '987654321')
        self.assertEqual(res['join_url'], 'https://us02web.zoom.us/j/987654321')
        self.assertFalse(res['auto_recording_enabled'])
        self.assertTrue(bool(res['auto_recording_warning']))
        self.assertEqual(mock_req.call_count, 2)

    @patch('accounts.zoom_services.download_zoom_recording_file')
    @patch('accounts.zoom_services.get_zoom_meeting_recordings')
    def test_fetch_zoom_transcript_success_and_updates_meeting(self, mock_get_rec, mock_dl):
        meeting = Meeting.objects.create(
            created_by=self.user,
            scheduled_datetime=timezone.now() - timedelta(hours=2),
            meeting_provider='ZOOM',
            provider_meeting_id='888111222',
            meeting_link='https://us02web.zoom.us/j/888111222',
            agenda='Q4 Strategy',
        )
        tr = create_or_update_pending_transcription(
            user=self.user,
            provider=MeetingTranscription.Provider.ZOOM,
            source=MeetingTranscription.Source.ZOOM_CLOUD_RECORDING,
            title='Q4 Strategy',
            meeting_url=meeting.meeting_link,
            provider_meeting_id='888111222',
            meeting=meeting,
        )
        mock_get_rec.return_value = {
            'uuid': 'uuid-abc-123',
            'topic': 'Q4 Strategy',
            'recording_files': [
                {'id': 'rec-vid', 'file_type': 'MP4', 'status': 'completed'},
                {
                    'id': 'rec-vtt-1',
                    'file_type': 'TRANSCRIPT',
                    'file_extension': 'VTT',
                    'status': 'completed',
                    'download_url': 'https://zoom.us/rec/download/vtt1',
                    'recording_end': timezone.now().isoformat(),
                },
            ],
        }
        mock_dl.return_value = SAMPLE_VTT.encode('utf-8')

        updated = fetch_and_store_zoom_transcript(tr)
        self.assertEqual(updated.status, MeetingTranscription.Status.COMPLETED)
        self.assertEqual(updated.provider_recording_id, 'rec-vtt-1')
        self.assertIn('quarterly market review', updated.transcript_text)
        self.assertEqual(len(updated.transcript_segments), 3)
        self.assertEqual(updated.participants, ['Alice Smith', 'Bob Jones'])
        self.assertTrue(bool(updated.transcript_file.name))

        meeting.refresh_from_db()
        self.assertEqual(meeting.transcription_status, 'COMPLETED')
        self.assertIn('quarterly market review', meeting.transcript_text)

    @patch('accounts.zoom_services.get_zoom_meeting_recordings')
    def test_fetch_zoom_transcript_delayed_processing_and_max_retries(self, mock_get_rec):
        tr = create_or_update_pending_transcription(
            user=self.user,
            provider=MeetingTranscription.Provider.ZOOM,
            source=MeetingTranscription.Source.ZOOM_CLOUD_RECORDING,
            title='Delayed Zoom',
            provider_meeting_id='777000111',
        )
        mock_get_rec.side_effect = ZoomRecordingNotFoundError('Not ready')

        updated = fetch_and_store_zoom_transcript(tr)
        self.assertEqual(updated.status, MeetingTranscription.Status.WAITING_FOR_PROVIDER)
        self.assertEqual(updated.retry_count, 1)
        self.assertIsNotNone(updated.next_retry_at)

        # Exhaust retries -> UNAVAILABLE
        updated.retry_count = MAX_ZOOM_RETRIES
        updated.save(update_fields=['retry_count'])
        final = fetch_and_store_zoom_transcript(updated)
        self.assertEqual(final.status, MeetingTranscription.Status.UNAVAILABLE)
        self.assertIsNone(final.next_retry_at)

    @patch('accounts.zoom_services.get_zoom_meeting_recordings')
    def test_fetch_zoom_transcript_missing_scope_marks_failed_without_deactivating_creds(self, mock_get_rec):
        tr = create_or_update_pending_transcription(
            user=self.user,
            provider=MeetingTranscription.Provider.ZOOM,
            source=MeetingTranscription.Source.ZOOM_CLOUD_RECORDING,
            title='Scope Test',
            provider_meeting_id='555444333',
        )
        mock_get_rec.side_effect = ZoomScopeError('Missing cloud_recording:read scope')

        updated = fetch_and_store_zoom_transcript(tr)
        self.assertEqual(updated.status, MeetingTranscription.Status.FAILED)
        self.assertIn('scope', updated.status_message.lower())
        self.zoom_creds.refresh_from_db()
        self.assertTrue(self.zoom_creds.is_active)

    @override_settings(ZOOM_WEBHOOK_SECRET_TOKEN='super-secret-zoom-token')
    def test_zoom_webhook_crc_validation_and_invalid_signature(self):
        client = APIClient()
        payload = {'event': 'endpoint.url_validation', 'payload': {'plainToken': 'abc123plain'}}
        raw = json.dumps(payload).encode('utf-8')

        # Missing signature -> 401
        bad_resp = client.post('/api/transcriptions/webhooks/zoom/', data=raw, content_type='application/json')
        self.assertEqual(bad_resp.status_code, 401)

        # Valid signature -> 200 with encryptedToken
        headers = _sign_zoom_webhook('super-secret-zoom-token', raw)
        ok_resp = client.post(
            '/api/transcriptions/webhooks/zoom/',
            data=raw,
            content_type='application/json',
            **headers,
        )
        self.assertEqual(ok_resp.status_code, 200)
        self.assertEqual(ok_resp.data['plainToken'], 'abc123plain')
        expected_enc = hmac.new(b'super-secret-zoom-token', b'abc123plain', hashlib.sha256).hexdigest()
        self.assertEqual(ok_resp.data['encryptedToken'], expected_enc)

    @override_settings(ZOOM_WEBHOOK_SECRET_TOKEN='super-secret-zoom-token')
    @patch('accounts.zoom_services.download_zoom_recording_file')
    def test_zoom_webhook_recording_completed_is_idempotent(self, mock_dl):
        mock_dl.return_value = SAMPLE_VTT.encode('utf-8')
        client = APIClient()
        payload = {
            'event': 'recording.completed',
            'download_token': 'webhook-dl-token',
            'payload': {
                'object': {
                    'id': 1234567890,
                    'uuid': 'uuid-zoom-99',
                    'host_id': self.zoom_creds.zoom_user_id,
                    'host_email': self.user.email,
                    'topic': 'Webhook Synced Zoom',
                    'start_time': (timezone.now() - timedelta(hours=1)).isoformat(),
                    'duration': 30,
                    'recording_files': [
                        {
                            'id': 'vtt-file-1',
                            'file_type': 'TRANSCRIPT',
                            'file_extension': 'VTT',
                            'status': 'completed',
                            'download_url': 'https://zoom.us/rec/download/vtt-file-1',
                        }
                    ],
                }
            },
        }
        raw = json.dumps(payload).encode('utf-8')
        headers = _sign_zoom_webhook('super-secret-zoom-token', raw)

        resp1 = client.post('/api/transcriptions/webhooks/zoom/', data=raw, content_type='application/json', **headers)
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp1.data['transcription_status'], 'COMPLETED')
        self.assertEqual(MeetingTranscription.objects.count(), 1)

        # Replay exact same webhook -> no duplicate record, no second download
        resp2 = client.post('/api/transcriptions/webhooks/zoom/', data=raw, content_type='application/json', **headers)
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(MeetingTranscription.objects.count(), 1)
        self.assertEqual(mock_dl.call_count, 1)

    @patch('accounts.zoom_services.download_zoom_recording_file')
    @patch('accounts.zoom_services.get_zoom_meeting_recordings')
    def test_process_pending_discovers_ended_zoom_meeting(self, mock_get_rec, mock_dl):
        Meeting.objects.create(
            created_by=self.user,
            scheduled_datetime=timezone.now() - timedelta(hours=2),
            meeting_provider='ZOOM',
            provider_meeting_id='444555666',
            meeting_link='https://us02web.zoom.us/j/444555666',
            agenda='Recovered Zoom Call',
        )
        mock_get_rec.return_value = {
            'uuid': 'uuid-rec',
            'topic': 'Recovered Zoom Call',
            'recording_files': [
                {
                    'id': 'vtt-rec',
                    'file_type': 'TRANSCRIPT',
                    'status': 'completed',
                    'download_url': 'https://zoom.us/rec/download/vtt-rec',
                }
            ],
        }
        mock_dl.return_value = SAMPLE_VTT.encode('utf-8')

        summary = process_pending_transcriptions(max_items=20)
        self.assertEqual(summary['discovered'], 1)
        self.assertEqual(summary['completed'], 1)
        tr = MeetingTranscription.objects.get(provider_meeting_id='444555666')
        self.assertEqual(tr.status, MeetingTranscription.Status.COMPLETED)


class CbeAndBackfillTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Beta Ltd')
        self.user = _make_user('pre_cbe', role='PRE', company=self.company)

    def test_cbe_completed_webhook_upserts_meeting_transcription_and_preserves_existing(self):
        cal_rec = CalendarEventRecording.objects.create(
            user=self.user,
            event_id='gcal_evt_100',
            meeting_link='https://meet.google.com/abc-defg-hij',
        )
        job = MeetingAutomationJob.objects.create(
            user=self.user,
            source_type=MeetingAutomationJob.SourceType.GOOGLE_CALENDAR,
            external_event_id='gcal_evt_100',
            calendar_recording=cal_rec,
            title='CBE Synced Google Meet',
            meeting_link='https://meet.google.com/abc-defg-hij',
            scheduled_start=timezone.now() - timedelta(hours=1),
            scheduled_end=timezone.now() - timedelta(minutes=30),
            idempotency_key='cbe-job-dedup-100',
        )
        payload = {
            'event': 'meeting.completed',
            'status': 'completed',
            'delivery_id': 'deliv-100',
            'meeting': {
                'meeting_id': 'cbe-meet-100',
                'calendar_event_id': 'gcal_evt_100',
                'meeting_url': 'https://meet.google.com/abc-defg-hij',
                'title': 'CBE Synced Google Meet',
            },
            'transcription': {
                'status': 'completed',
                'backend': 'whisper',
                'segments': [
                    {'start_ms': 5000, 'speaker_name': 'Speaker 1', 'text': 'Hello from Google Meet.'}
                ],
            },
            'speaker_segments': [
                {'start_ms': 5000, 'speaker_name': 'Speaker 1', 'text': 'Hello from Google Meet.'}
            ],
            'participants': ['Speaker 1'],
        }

        res = ingest_cbe_completed_webhook(payload, delivery_id='deliv-100', idempotency_key='cbe-job-dedup-100')
        self.assertFalse(res['duplicate'])
        cal_rec.refresh_from_db()
        self.assertIn('Hello from Google Meet', cal_rec.transcript_text)

        tr = MeetingTranscription.objects.get(calendar_event_id='gcal_evt_100')
        self.assertEqual(tr.provider, MeetingTranscription.Provider.GOOGLE_MEET)
        self.assertEqual(tr.source, MeetingTranscription.Source.CBE)
        self.assertEqual(tr.status, MeetingTranscription.Status.COMPLETED)
        self.assertIn('Hello from Google Meet', tr.transcript_text)
        self.assertEqual(tr.participants, ['Speaker 1'])

        # Duplicate delivery does not create a second MeetingTranscription
        res2 = ingest_cbe_completed_webhook(payload, delivery_id='deliv-100')
        self.assertTrue(res2['duplicate'])
        self.assertEqual(MeetingTranscription.objects.count(), 1)

    def test_backfill_historical_transcriptions_idempotent_and_dry_run(self):
        Meeting.objects.create(
            created_by=self.user,
            scheduled_datetime=timezone.now() - timedelta(days=2),
            meeting_provider='GOOGLE_MEET',
            google_event_id='hist_evt_1',
            meeting_link='https://meet.google.com/aaa-bbbb-ccc',
            agenda='Historical Meet',
            transcript_text='Historical meeting transcript text.',
        )
        CalendarEventRecording.objects.create(
            user=self.user,
            event_id='hist_cal_2',
            meeting_link='https://meet.google.com/ddd-eeee-fff',
            transcript_text='Historical calendar recording transcript.',
        )
        # Empty record should be skipped
        CalendarEventRecording.objects.create(
            user=self.user,
            event_id='hist_cal_empty',
            meeting_link='https://meet.google.com/ggg-hhhh-iii',
            transcript_text='',
        )

        dry = backfill_historical_transcriptions(dry_run=True)
        self.assertEqual(dry['created'], 2)
        self.assertEqual(MeetingTranscription.objects.count(), 0)

        first = backfill_historical_transcriptions(dry_run=False)
        self.assertEqual(first['created'], 2)
        self.assertEqual(MeetingTranscription.objects.count(), 2)

        # Second run is completely idempotent
        second = backfill_historical_transcriptions(dry_run=False)
        self.assertEqual(second['created'], 0)
        self.assertEqual(second['updated'], 0)
        self.assertEqual(MeetingTranscription.objects.count(), 2)


class TranscriptionApiAndIsolationTests(TestCase):
    def setUp(self):
        self.co_a = Company.objects.create(name='Company A', code='CO_A')
        self.co_b = Company.objects.create(name='Company B', code='CO_B')
        self.pre_a1 = _make_user('pre_a1', role='PRE', company=self.co_a)
        self.pre_a2 = _make_user('pre_a2', role='PRE', company=self.co_a)
        self.mgr_a = _make_user('mgr_a', role='MANAGER', company=self.co_a)
        self.pre_b1 = _make_user('pre_b1', role='PRE', company=self.co_b)
        self.dm_a = _make_user('dm_a', role='DM', company=self.co_a)

        self.tr_a1 = MeetingTranscription.objects.create(
            user=self.pre_a1,
            provider=MeetingTranscription.Provider.ZOOM,
            source=MeetingTranscription.Source.ZOOM_CLOUD_RECORDING,
            title='Acme Renewal Call',
            provider_meeting_id='1001',
            scheduled_start=timezone.now() - timedelta(days=1),
            transcript_text='Discussed enterprise pricing and renewal timeline.',
            status=MeetingTranscription.Status.COMPLETED,
            source_metadata={'zoom_uuid': 'u1', 'access_token': 'MUST_NOT_LEAK'},
        )
        self.tr_a2 = MeetingTranscription.objects.create(
            user=self.pre_a2,
            provider=MeetingTranscription.Provider.GOOGLE_MEET,
            source=MeetingTranscription.Source.CBE,
            title='Product Demo',
            calendar_event_id='ev2',
            scheduled_start=timezone.now() - timedelta(days=3),
            transcript_text='Walked through dashboard analytics.',
            status=MeetingTranscription.Status.PENDING,
        )
        self.tr_b1 = MeetingTranscription.objects.create(
            user=self.pre_b1,
            provider=MeetingTranscription.Provider.ZOOM,
            source=MeetingTranscription.Source.ZOOM_CLOUD_RECORDING,
            title='Competitor Secret Call',
            provider_meeting_id='2002',
            scheduled_start=timezone.now(),
            transcript_text='Confidential Company B discussion.',
            status=MeetingTranscription.Status.COMPLETED,
        )

    def test_role_and_company_isolation(self):
        client = APIClient()

        # PRE sees only their own
        client.force_authenticate(user=self.pre_a1)
        res = client.get('/api/transcriptions/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['count'], 1)
        self.assertEqual(res.data['results'][0]['id'], str(self.tr_a1.id))

        # PRE cannot retrieve another user's record
        res_other = client.get(f'/api/transcriptions/{self.tr_a2.id}/')
        self.assertEqual(res_other.status_code, 404)

        # Detail response strips secret keys from safe_metadata
        res_detail = client.get(f'/api/transcriptions/{self.tr_a1.id}/')
        self.assertEqual(res_detail.status_code, 200)
        self.assertNotIn('access_token', res_detail.data['safe_metadata'])
        self.assertEqual(res_detail.data['safe_metadata'].get('zoom_uuid'), 'u1')

        # Manager sees all Company A records, NOT Company B
        client.force_authenticate(user=self.mgr_a)
        res_mgr = client.get('/api/transcriptions/')
        self.assertEqual(res_mgr.status_code, 200)
        self.assertEqual(res_mgr.data['count'], 2)
        ids = {r['id'] for r in res_mgr.data['results']}
        self.assertIn(str(self.tr_a1.id), ids)
        self.assertIn(str(self.tr_a2.id), ids)
        self.assertNotIn(str(self.tr_b1.id), ids)

        # DM role is forbidden
        client.force_authenticate(user=self.dm_a)
        res_dm = client.get('/api/transcriptions/')
        self.assertEqual(res_dm.status_code, 403)

    def test_search_filters_and_process_pending_permissions(self):
        client = APIClient()
        client.force_authenticate(user=self.mgr_a)

        # Search in transcript text
        res = client.get('/api/transcriptions/', {'search': 'enterprise pricing'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['count'], 1)

        # Filter by provider
        res_prov = client.get('/api/transcriptions/', {'provider': 'GOOGLE_MEET'})
        self.assertEqual(res_prov.data['count'], 1)

        # Filter by status
        res_st = client.get('/api/transcriptions/', {'status': 'COMPLETED'})
        self.assertEqual(res_st.data['count'], 1)

        # Manager can call process-pending
        res_proc = client.post('/api/transcriptions/process-pending/', {})
        self.assertEqual(res_proc.status_code, 200)
        self.assertIn('checked', res_proc.data)

        # PRE cannot call process-pending
        client.force_authenticate(user=self.pre_a1)
        res_pre_proc = client.post('/api/transcriptions/process-pending/', {})
        self.assertEqual(res_pre_proc.status_code, 403)


class CalendarMeetingLinkGenerationTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Cal Corp')
        self.user = _make_user('pre_cal', role='PRE', company=self.company)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.start = (timezone.now() + timedelta(hours=2)).replace(microsecond=0)
        self.end = self.start + timedelta(minutes=30)

    def test_calendar_requires_google_calendar_connection(self):
        res = self.client.post('/api/auth/google/calendar/events/', {
            'summary': 'Test Meet',
            'start': self.start.isoformat(),
            'end': self.end.isoformat(),
            'meeting_provider': 'GOOGLE_MEET',
        }, format='json')
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data['code'], 'calendar_not_connected')

    @patch('accounts.calendar_views.create_meet_event')
    def test_calendar_google_meet_creates_real_link_and_is_idempotent(self, mock_create_meet):
        _make_calendar_creds(self.user)
        mock_create_meet.return_value = {
            'google_event_id': 'gcal_real_1',
            'meet_url': 'https://meet.google.com/xyz-abcd-efg',
            'html_link': 'https://calendar.google.com/event?eid=1',
            'status': 'READY',
        }
        payload = {
            'summary': 'Real Meet Schedule',
            'description': 'Sync agenda',
            'start': self.start.isoformat(),
            'end': self.end.isoformat(),
            'meeting_provider': 'GOOGLE_MEET',
            'timezone': 'UTC',
            'client_request_id': 'idemp-meet-1',
        }
        res1 = self.client.post('/api/auth/google/calendar/events/', payload, format='json')
        self.assertEqual(res1.status_code, 201)
        self.assertEqual(res1.data['event']['meet_url'], 'https://meet.google.com/xyz-abcd-efg')
        self.assertEqual(res1.data['event']['meeting_provider'], 'GOOGLE_MEET')
        self.assertEqual(MeetingTranscription.objects.filter(calendar_event_id='gcal_real_1').count(), 1)
        self.assertEqual(CalendarEventRecording.objects.filter(event_id='gcal_real_1').count(), 1)

        # Duplicate click with same client_request_id returns cached response without calling Google again
        res2 = self.client.post('/api/auth/google/calendar/events/', payload, format='json')
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(mock_create_meet.call_count, 1)

    def test_calendar_zoom_requires_zoom_connection(self):
        _make_calendar_creds(self.user)
        res = self.client.post('/api/auth/google/calendar/events/', {
            'summary': 'Zoom Without Connection',
            'start': self.start.isoformat(),
            'end': self.end.isoformat(),
            'meeting_provider': 'ZOOM',
        }, format='json')
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data['code'], 'zoom_not_connected')

    @patch('accounts.calendar_views._api_request')
    @patch('accounts.zoom_services.create_zoom_meeting')
    def test_calendar_zoom_creates_zoom_and_syncs_google_calendar_without_meet(self, mock_zoom, mock_gcal):
        _make_calendar_creds(self.user)
        _make_zoom_creds(self.user)
        mock_zoom.return_value = {
            'meeting_id': '999888777',
            'join_url': 'https://us02web.zoom.us/j/999888777',
            'password': 'pass',
            'start_url': 'https://us02web.zoom.us/s/999888777',
            'status': 'READY',
            'auto_recording_enabled': True,
            'auto_recording_warning': '',
        }
        mock_gcal.return_value = {
            'id': 'gcal_zoom_1',
            'summary': 'Zoom Sync Event',
            'description': 'Join Zoom Meeting: https://us02web.zoom.us/j/999888777',
            'start': {'dateTime': self.start.isoformat()},
            'end': {'dateTime': self.end.isoformat()},
            'htmlLink': 'https://calendar.google.com/event?eid=zoom1',
        }

        res = self.client.post('/api/auth/google/calendar/events/', {
            'summary': 'Zoom Sync Event',
            'start': self.start.isoformat(),
            'end': self.end.isoformat(),
            'meeting_provider': 'ZOOM',
            'timezone': 'UTC',
        }, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['event']['meet_url'], 'https://us02web.zoom.us/j/999888777')
        self.assertEqual(res.data['event']['meeting_provider'], 'ZOOM')
        self.assertEqual(res.data['event']['provider_meeting_id'], '999888777')

        # Ensure Google Calendar body did NOT attach a Google Meet conference
        gcal_body = mock_gcal.call_args.kwargs['body']
        self.assertNotIn('conferenceData', gcal_body)
        self.assertEqual(gcal_body['location'], 'https://us02web.zoom.us/j/999888777')

        tr = MeetingTranscription.objects.get(provider_meeting_id='999888777')
        self.assertEqual(tr.provider, MeetingTranscription.Provider.ZOOM)
        self.assertEqual(tr.status, MeetingTranscription.Status.PENDING)

    @patch('accounts.zoom_services.delete_zoom_meeting')
    @patch('accounts.calendar_views._api_request')
    @patch('accounts.zoom_services.create_zoom_meeting')
    def test_calendar_zoom_rolls_back_zoom_if_google_calendar_fails(self, mock_zoom, mock_gcal, mock_del_zoom):
        _make_calendar_creds(self.user)
        _make_zoom_creds(self.user)
        mock_zoom.return_value = {
            'meeting_id': '111222333',
            'join_url': 'https://us02web.zoom.us/j/111222333',
            'password': '',
            'start_url': '',
            'status': 'READY',
            'auto_recording_enabled': True,
            'auto_recording_warning': '',
        }
        mock_gcal.side_effect = RuntimeError('Google Calendar 500')

        res = self.client.post('/api/auth/google/calendar/events/', {
            'summary': 'Rollback Zoom',
            'start': self.start.isoformat(),
            'end': self.end.isoformat(),
            'meeting_provider': 'ZOOM',
        }, format='json')
        self.assertEqual(res.status_code, 400)
        mock_del_zoom.assert_called_once()
        self.assertEqual(MeetingTranscription.objects.count(), 0)
