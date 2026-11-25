import hashlib
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


def compute_transcription_dedup_key(
    *,
    user_id: int,
    provider: str,
    provider_meeting_id: str = '',
    calendar_event_id: str = '',
    meeting_id=None,
    automation_job_id=None,
    calendar_recording_id=None,
    meeting_url: str = '',
) -> str:
    """Build a deterministic SHA-256 deduplication key for a MeetingTranscription."""
    prov = (provider or '').strip().upper()
    if provider_meeting_id:
        anchor = f"pmid:{str(provider_meeting_id).strip()}"
    elif calendar_event_id:
        anchor = f"ceid:{str(calendar_event_id).strip()}"
    elif meeting_id:
        anchor = f"meeting:{meeting_id}"
    elif automation_job_id:
        anchor = f"job:{automation_job_id}"
    elif calendar_recording_id:
        anchor = f"calrec:{calendar_recording_id}"
    elif meeting_url:
        anchor = f"url:{str(meeting_url).strip().lower()}"
    else:
        anchor = f"rand:{uuid.uuid4().hex}"
    raw = f"{user_id}|{prov}|{anchor}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


class MeetingTranscription(models.Model):
    """Normalized meeting transcription storage across Google Meet (CBE) and Zoom."""

    class Provider(models.TextChoices):
        GOOGLE_MEET = 'GOOGLE_MEET', 'Google Meet'
        ZOOM = 'ZOOM', 'Zoom'

    class Source(models.TextChoices):
        CBE = 'CBE', 'Custom Browser Engine (CBE)'
        ZOOM_CLOUD_RECORDING = 'ZOOM_CLOUD_RECORDING', 'Zoom Cloud Recording'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        WAITING_FOR_PROVIDER = 'WAITING_FOR_PROVIDER', 'Waiting for Provider Processing'
        PROCESSING = 'PROCESSING', 'Processing'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'
        UNAVAILABLE = 'UNAVAILABLE', 'Transcript Unavailable'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='meeting_transcriptions',
        db_index=True,
    )
    provider = models.CharField(
        max_length=24,
        choices=Provider.choices,
        db_index=True,
    )
    source = models.CharField(
        max_length=32,
        choices=Source.choices,
        db_index=True,
    )
    title = models.CharField(max_length=500, blank=True, default='')
    meeting_url = models.CharField(max_length=512, blank=True, default='')
    provider_meeting_id = models.CharField(max_length=255, blank=True, default='', db_index=True)
    provider_recording_id = models.CharField(max_length=255, blank=True, default='')
    calendar_event_id = models.CharField(max_length=255, blank=True, default='', db_index=True)

    meeting = models.ForeignKey(
        'prospects.Meeting',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transcriptions',
    )
    calendar_recording = models.ForeignKey(
        'accounts.CalendarEventRecording',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transcriptions',
    )
    automation_job = models.ForeignKey(
        'accounts.MeetingAutomationJob',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transcriptions',
    )

    scheduled_start = models.DateTimeField(null=True, blank=True, db_index=True)
    scheduled_end = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    transcript_text = models.TextField(blank=True, default='')
    transcript_segments = models.JSONField(default=list, blank=True)
    speaker_segments = models.JSONField(default=list, blank=True)
    participants = models.JSONField(default=list, blank=True)
    transcript_file = models.FileField(
        upload_to='meeting_transcriptions/%Y/%m/',
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    status_message = models.TextField(blank=True, default='')
    completed_at = models.DateTimeField(null=True, blank=True)

    retry_count = models.PositiveIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True, db_index=True)
    dedup_key = models.CharField(max_length=128, unique=True, editable=False)

    source_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-scheduled_start', '-created_at']
        indexes = [
            models.Index(fields=['user', 'provider', 'status']),
            models.Index(fields=['user', 'scheduled_start']),
            models.Index(fields=['provider', 'status', 'next_retry_at']),
            models.Index(fields=['calendar_event_id']),
            models.Index(fields=['provider_meeting_id']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'provider', 'provider_meeting_id'],
                condition=~Q(provider_meeting_id=''),
                name='uniq_transcription_user_provider_meeting_id',
            ),
            models.UniqueConstraint(
                fields=['user', 'provider', 'calendar_event_id'],
                condition=~Q(calendar_event_id=''),
                name='uniq_transcription_user_provider_calendar_event',
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.dedup_key:
            self.dedup_key = compute_transcription_dedup_key(
                user_id=self.user_id,
                provider=self.provider,
                provider_meeting_id=self.provider_meeting_id,
                calendar_event_id=self.calendar_event_id,
                meeting_id=self.meeting_id,
                automation_job_id=self.automation_job_id,
                calendar_recording_id=self.calendar_recording_id,
                meeting_url=self.meeting_url,
            )
        super().save(*args, **kwargs)

    @property
    def duration_seconds(self):
        start = self.scheduled_start
        end = self.ended_at or self.scheduled_end
        if start and end and end > start:
            return int((end - start).total_seconds())
        return None

    def __str__(self):
        return f"MeetingTranscription({self.provider}, {self.title or self.provider_meeting_id}, {self.status})"
