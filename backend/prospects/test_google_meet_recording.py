"""Unit tests for Google Meet REST API v2 Audio Recording Download into Market Intel DB."""
import io
import json
import os
from unittest import mock
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

import utils.encryption as encryption

if not os.environ.get('MAIL_CREDENTIALS_ENCRYPTION_KEY'):
    os.environ['MAIL_CREDENTIALS_ENCRYPTION_KEY'] = encryption.Fernet.generate_key().decode('utf-8')

from accounts.google_meet_service import GoogleMeetRestService, extract_meeting_code
from accounts.models import GoogleCalendarCredentials
from prospects.models import Meeting, Prospect, ProspectContact

TEST_SETTINGS = dict(
    GOOGLE_OAUTH_CLIENT_ID='test-client-id',
    GOOGLE_OAUTH_CLIENT_SECRET='test-client-secret',
    CALENDAR_OAUTH_REDIRECT_URI='http://localhost:5173/auth/calendar/callback',
)


@override_settings(**TEST_SETTINGS)
class GoogleMeetRecordingTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='host_user', password='password123', email='host@test.com')
        self.other_user = User.objects.create_user(username='other_user', password='password123', email='other@test.com')

        self.cal_creds = GoogleCalendarCredentials.objects.create(
            user=self.user,
            email='host@test.com',
            access_token_encrypted=encryption.encrypt_password('test-access-token'),
            refresh_token_encrypted=encryption.encrypt_password('test-refresh-token'),
            token_expiry=timezone.now() + timedelta(hours=1),
            scopes='https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/meetings.space.readonly https://www.googleapis.com/auth/drive.readonly',
            is_active=True
        )

        self.prospect = Prospect.objects.create(
            company_name='Acme Corp',
            country_head_office='US',
            created_by=self.user.username
        )

        self.meeting = Meeting.objects.create(
            prospect=self.prospect,
            scheduled_datetime=timezone.now() - timedelta(hours=2),
            meeting_link='https://meet.google.com/abc-mnop-xyz',
            meeting_provider='GOOGLE_MEET',
            google_calendar_owner=self.user,
            created_by=self.user,
            conference_status='READY',
            status='SCHEDULED',
            client_request_id='meet-rec-req-123'
        )

    def test_extract_meeting_code(self):
        self.assertEqual(extract_meeting_code('https://meet.google.com/abc-mnop-xyz'), 'abc-mnop-xyz')
        self.assertEqual(extract_meeting_code('http://meet.google.com/abc-mnop-xyz?authuser=0'), 'abc-mnop-xyz')
        self.assertEqual(extract_meeting_code('abc-mnop-xyz'), 'abc-mnop-xyz')

    @mock.patch.object(GoogleMeetRestService, 'download_drive_file_content')
    @mock.patch.object(GoogleMeetRestService, 'get_drive_file_metadata')
    @mock.patch.object(GoogleMeetRestService, 'list_recordings_for_conference')
    @mock.patch.object(GoogleMeetRestService, 'list_conference_records')
    def test_sync_meeting_recording_success(self, mock_conf, mock_rec, mock_meta, mock_download):
        mock_conf.return_value = [{'name': 'conferenceRecords/C_test_123'}]
        mock_rec.return_value = [{
            'name': 'conferenceRecords/C_test_123/recordings/R_test_456',
            'state': 'FILE_GENERATED',
            'driveDestination': {
                'file': 'drive-file-id-789',
                'exportUri': 'https://drive.google.com/file/d/drive-file-id-789/view'
            }
        }]
        mock_meta.return_value = {
            'id': 'drive-file-id-789',
            'name': 'Acme_Meeting_Audio.mp4',
            'mimeType': 'audio/mp4',
            'size': '2048000'
        }
        mock_download.return_value = b"FAKE_AUDIO_RECORDING_BYTES"

        result = GoogleMeetRestService.sync_meeting_recording(self.meeting)

        self.assertTrue(result['success'])
        self.assertEqual(result['status'], 'COMPLETED')
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.recording_status, 'COMPLETED')
        self.assertEqual(self.meeting.recording_drive_file_id, 'drive-file-id-789')
        self.assertEqual(self.meeting.google_conference_record_id, 'conferenceRecords/C_test_123')
        self.assertEqual(self.meeting.google_recording_id, 'conferenceRecords/C_test_123/recordings/R_test_456')
        self.assertTrue(bool(self.meeting.recording_file))
        self.assertIsNotNone(self.meeting.recording_downloaded_at)
        self.meeting.recording_file.delete(save=False)

    @mock.patch.object(GoogleMeetRestService, 'list_recordings_for_conference')
    @mock.patch.object(GoogleMeetRestService, 'list_conference_records')
    def test_sync_meeting_recording_processing(self, mock_conf, mock_rec):
        mock_conf.return_value = [{'name': 'conferenceRecords/C_test_123'}]
        mock_rec.return_value = [{
            'name': 'conferenceRecords/C_test_123/recordings/R_test_456',
            'state': 'STARTED',
            'driveDestination': {}
        }]

        result = GoogleMeetRestService.sync_meeting_recording(self.meeting)

        self.assertFalse(result['success'])
        self.assertEqual(result['status'], 'PROCESSING')
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.recording_status, 'PROCESSING')

    @mock.patch.object(GoogleMeetRestService, 'list_conference_records')
    def test_sync_meeting_recording_not_found(self, mock_conf):
        mock_conf.return_value = []

        result = GoogleMeetRestService.sync_meeting_recording(self.meeting)

        self.assertFalse(result['success'])
        self.assertEqual(result['status'], 'NOT_FOUND')
        self.meeting.refresh_from_db()
        self.assertEqual(self.meeting.recording_status, 'NOT_FOUND')

    @mock.patch.object(GoogleMeetRestService, 'sync_meeting_recording')
    def test_api_sync_recording_endpoint_authorized(self, mock_sync):
        mock_sync.return_value = {
            'success': True,
            'status': 'COMPLETED',
            'recording_url': '/media/meeting_recordings/test.mp4'
        }

        self.client.force_authenticate(user=self.user)
        res = self.client.post(f'/api/meetings/{self.meeting.id}/sync-recording/')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('sync_result', res.data)
        self.assertTrue(res.data['sync_result']['success'])

    @mock.patch.object(GoogleMeetRestService, 'download_drive_file_content')
    @mock.patch.object(GoogleMeetRestService, 'get_drive_file_metadata')
    @mock.patch.object(GoogleMeetRestService, 'list_recordings_for_conference')
    @mock.patch.object(GoogleMeetRestService, 'list_conference_records')
    def test_calendar_event_without_meeting_row(self, mock_conf, mock_rec, mock_meta, mock_dl):
        """An event created directly in Google Calendar (no prospect Meeting) can still sync audio."""
        from accounts.models import CalendarEventRecording
        mock_conf.return_value = [{'name': 'conferenceRecords/C_1'}]
        mock_rec.return_value = [{'name': 'conferenceRecords/C_1/recordings/R_1',
                                  'driveDestination': {'file': 'fid'}}]
        mock_meta.return_value = {'name': 'rec.mp4', 'mimeType': 'video/mp4', 'size': '10'}
        mock_dl.return_value = b'BYTES'

        self.client.force_authenticate(user=self.user)
        res = self.client.post('/api/auth/google/calendar/sync-recording/', {
            'event_id': 'evt_standalone_1',
            'meet_url': 'https://meet.google.com/qqq-wwww-eee',
        }, format='json')

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['success'])
        self.assertIsNone(res.data['meeting_id'])
        rec = CalendarEventRecording.objects.get(user=self.user, event_id='evt_standalone_1')
        self.assertEqual(rec.recording_status, 'COMPLETED')
        self.assertTrue(bool(rec.recording_file))
        rec.recording_file.delete(save=False)

    def test_calendar_sync_requires_event_or_meeting(self):
        self.client.force_authenticate(user=self.user)
        res = self.client.post('/api/auth/google/calendar/sync-recording/', {}, format='json')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_api_sync_recording_endpoint_unauthorized_user(self):
        self.client.force_authenticate(user=self.other_user)
        res = self.client.post(f'/api/meetings/{self.meeting.id}/sync-recording/')

        self.assertIn(res.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])
