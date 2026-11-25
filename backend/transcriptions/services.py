import hashlib
import hmac
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from transcriptions.models import MeetingTranscription, compute_transcription_dedup_key

logger = logging.getLogger(__name__)

MAX_ZOOM_RETRIES = 12
ZOOM_RETRY_BACKOFF_MINUTES = [2, 5, 10, 15, 30, 45, 60, 60, 120, 120, 180, 180]
ZOOM_WEBHOOK_TOLERANCE_SECONDS = 300

_VTT_TIMESTAMP_RE = re.compile(
    r'^(?:(?P<sh>\d{1,2}):)?(?P<sm>\d{2}):(?P<ss>\d{2})(?:[.,](?P<sms>\d{1,3}))?'
    r'\s*-->\s*'
    r'(?:(?P<eh>\d{1,2}):)?(?P<em>\d{2}):(?P<es>\d{2})(?:[.,](?P<ems>\d{1,3}))?'
)
_VTT_VOICE_TAG_RE = re.compile(r'^<v(?:\.[^>\s]+)?\s+([^>]+)>(.*?)(?:</v>)?$', re.DOTALL)
_VTT_SPEAKER_PREFIX_RE = re.compile(r'^([A-Za-z0-9][A-Za-z0-9 ._\-\(\)]{0,60}):\s+(.+)$', re.DOTALL)
_HTML_TAG_RE = re.compile(r'<[^>]+>')


def _hms_to_seconds(hours: Optional[str], minutes: str, seconds: str, millis: Optional[str]) -> float:
    h = int(hours or 0)
    m = int(minutes or 0)
    s = int(seconds or 0)
    ms_str = (millis or '0').ljust(3, '0')[:3]
    ms = int(ms_str)
    return round(h * 3600 + m * 60 + s + ms / 1000.0, 3)


def format_seconds_hms(seconds: Optional[float]) -> str:
    if seconds is None:
        return '00:00:00'
    total = max(0, int(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f'{h:02d}:{m:02d}:{s:02d}'


def parse_vtt_transcript(vtt_text: str) -> Dict[str, Any]:
    """
    Parse a WebVTT (.vtt) transcript into normalized readable text,
    timestamped segments, speaker segments, and unique participant names.
    """
    if not vtt_text or not isinstance(vtt_text, str):
        return {
            'transcript_text': '',
            'transcript_segments': [],
            'speaker_segments': [],
            'participants': [],
        }

    cleaned = vtt_text.lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n')
    blocks = re.split(r'\n\s*\n', cleaned)

    segments: List[Dict[str, Any]] = []
    participants: List[str] = []
    seen_participants = set()

    for raw_block in blocks:
        lines = [line.strip() for line in raw_block.split('\n') if line.strip()]
        if not lines:
            continue
        upper_first = lines[0].upper()
        if upper_first.startswith('WEBVTT') or upper_first.startswith('NOTE') or upper_first.startswith('STYLE'):
            continue

        ts_idx = None
        ts_match = None
        for idx, line in enumerate(lines[:2]):
            m = _VTT_TIMESTAMP_RE.match(line)
            if m:
                ts_idx = idx
                ts_match = m
                break

        if ts_match is None or ts_idx is None:
            continue

        text_lines = lines[ts_idx + 1:]
        if not text_lines:
            continue

        raw_cue_text = ' '.join(text_lines).strip()
        speaker = ''
        cue_text = raw_cue_text

        voice_match = _VTT_VOICE_TAG_RE.match(raw_cue_text)
        if voice_match:
            speaker = voice_match.group(1).strip()
            cue_text = _HTML_TAG_RE.sub('', voice_match.group(2)).strip()
        else:
            cue_text = _HTML_TAG_RE.sub('', raw_cue_text).strip()
            speaker_match = _VTT_SPEAKER_PREFIX_RE.match(cue_text)
            if speaker_match:
                candidate = speaker_match.group(1).strip()
                if not candidate.lower().startswith(('http', 'https', 'mailto')):
                    speaker = candidate
                    cue_text = speaker_match.group(2).strip()

        if not cue_text:
            continue

        start_sec = _hms_to_seconds(
            ts_match.group('sh'), ts_match.group('sm'), ts_match.group('ss'), ts_match.group('sms')
        )
        end_sec = _hms_to_seconds(
            ts_match.group('eh'), ts_match.group('em'), ts_match.group('es'), ts_match.group('ems')
        )

        seg = {
            'start': format_seconds_hms(start_sec),
            'end': format_seconds_hms(end_sec),
            'start_seconds': start_sec,
            'end_seconds': end_sec,
            'speaker': speaker,
            'text': cue_text,
        }
        segments.append(seg)

        if speaker and speaker.lower() not in seen_participants:
            seen_participants.add(speaker.lower())
            participants.append(speaker)

    formatted_lines = []
    for seg in segments:
        prefix = f"[{seg['start']}]"
        if seg['speaker']:
            formatted_lines.append(f"{prefix} {seg['speaker']}: {seg['text']}")
        else:
            formatted_lines.append(f"{prefix} {seg['text']}")

    return {
        'transcript_text': '\n'.join(formatted_lines).strip(),
        'transcript_segments': segments,
        'speaker_segments': segments,
        'participants': participants,
    }


def _parse_dt(val: Any) -> Optional[datetime]:
    if not val:
        return None
    if isinstance(val, datetime):
        return val if timezone.is_aware(val) else timezone.make_aware(val, timezone.utc)
    if isinstance(val, str):
        parsed = parse_datetime(val.strip())
        if parsed is None:
            return None
        return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed, timezone.utc)
    return None


def _normalize_segments(raw_segments: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_segments, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in raw_segments:
        if isinstance(item, dict):
            text = str(item.get('text') or item.get('content') or '').strip()
            if not text:
                continue
            speaker = str(item.get('speaker') or item.get('speaker_name') or '').strip()
            start_val = item.get('start') or item.get('timestamp') or ''
            start_sec = item.get('start_seconds')
            if start_sec is None and isinstance(start_val, (int, float)):
                start_sec = float(start_val)
                start_val = format_seconds_hms(start_sec)
            elif not start_val and start_sec is not None:
                try:
                    start_val = format_seconds_hms(float(start_sec))
                except (TypeError, ValueError):
                    start_val = ''
            out.append({
                'start': str(start_val or ''),
                'end': str(item.get('end') or ''),
                'start_seconds': start_sec,
                'end_seconds': item.get('end_seconds'),
                'speaker': speaker,
                'text': text,
            })
        elif isinstance(item, str) and item.strip():
            out.append({
                'start': '',
                'end': '',
                'start_seconds': None,
                'end_seconds': None,
                'speaker': '',
                'text': item.strip(),
            })
    return out


def _segments_to_text(segments: List[Dict[str, Any]]) -> str:
    lines = []
    for seg in segments:
        ts = seg.get('start') or ''
        speaker = seg.get('speaker') or ''
        text = (seg.get('text') or '').strip()
        if not text:
            continue
        parts = []
        if ts:
            parts.append(f"[{ts}]")
        if speaker:
            parts.append(f"{speaker}:")
        parts.append(text)
        lines.append(' '.join(parts))
    return '\n'.join(lines).strip()


def _extract_participants(raw_participants: Any, segments: List[Dict[str, Any]]) -> List[str]:
    names: List[str] = []
    seen = set()
    if isinstance(raw_participants, list):
        for p in raw_participants:
            if isinstance(p, dict):
                name = str(p.get('name') or p.get('display_name') or p.get('email') or '').strip()
            else:
                name = str(p or '').strip()
            if name and name.lower() not in seen:
                seen.add(name.lower())
                names.append(name)
    for seg in segments:
        speaker = str(seg.get('speaker') or '').strip()
        if speaker and speaker.lower() not in seen:
            seen.add(speaker.lower())
            names.append(speaker)
    return names


def find_existing_transcription(
    *,
    user_id: int,
    provider: str,
    provider_meeting_id: str = '',
    calendar_event_id: str = '',
    meeting_id=None,
    automation_job_id=None,
    calendar_recording_id=None,
    meeting_url: str = '',
) -> Optional[MeetingTranscription]:
    """Locate an existing MeetingTranscription using stable external or relational keys."""
    qs = MeetingTranscription.objects.filter(user_id=user_id, provider=provider)

    if provider_meeting_id:
        match = qs.filter(provider_meeting_id=str(provider_meeting_id).strip()).first()
        if match:
            return match

    if calendar_event_id:
        match = qs.filter(calendar_event_id=str(calendar_event_id).strip()).first()
        if match:
            return match

    if meeting_id:
        match = qs.filter(meeting_id=meeting_id).first()
        if match:
            return match

    if automation_job_id:
        match = qs.filter(automation_job_id=automation_job_id).first()
        if match:
            return match

    if calendar_recording_id:
        match = qs.filter(calendar_recording_id=calendar_recording_id).first()
        if match:
            return match

    dedup_key = compute_transcription_dedup_key(
        user_id=user_id,
        provider=provider,
        provider_meeting_id=provider_meeting_id,
        calendar_event_id=calendar_event_id,
        meeting_id=meeting_id,
        automation_job_id=automation_job_id,
        calendar_recording_id=calendar_recording_id,
        meeting_url=meeting_url,
    )
    return MeetingTranscription.objects.filter(dedup_key=dedup_key).first()


def create_or_update_pending_transcription(
    *,
    user,
    provider: str,
    source: str,
    title: str = '',
    meeting_url: str = '',
    provider_meeting_id: str = '',
    calendar_event_id: str = '',
    meeting=None,
    calendar_recording=None,
    automation_job=None,
    scheduled_start=None,
    scheduled_end=None,
    status: str = MeetingTranscription.Status.PENDING,
    status_message: str = '',
    source_metadata: Optional[Dict[str, Any]] = None,
) -> MeetingTranscription:
    """
    Create or update a pending/tracking MeetingTranscription record idempotently.
    Never overwrites an already-COMPLETED transcript with pending/empty state.
    """
    pmid = str(provider_meeting_id or '').strip()
    ceid = str(calendar_event_id or '').strip()
    start_dt = _parse_dt(scheduled_start)
    end_dt = _parse_dt(scheduled_end)

    existing = find_existing_transcription(
        user_id=user.id,
        provider=provider,
        provider_meeting_id=pmid,
        calendar_event_id=ceid,
        meeting_id=getattr(meeting, 'id', None),
        automation_job_id=getattr(automation_job, 'id', None),
        calendar_recording_id=getattr(calendar_recording, 'id', None),
        meeting_url=meeting_url,
    )

    if existing:
        changed = False
        if title and not existing.title:
            existing.title = title[:500]
            changed = True
        if meeting_url and not existing.meeting_url:
            existing.meeting_url = meeting_url[:512]
            changed = True
        if pmid and not existing.provider_meeting_id:
            existing.provider_meeting_id = pmid[:255]
            changed = True
        if ceid and not existing.calendar_event_id:
            existing.calendar_event_id = ceid[:255]
            changed = True
        if meeting and not existing.meeting_id:
            existing.meeting = meeting
            changed = True
        if calendar_recording and not existing.calendar_recording_id:
            existing.calendar_recording = calendar_recording
            changed = True
        if automation_job and not existing.automation_job_id:
            existing.automation_job = automation_job
            changed = True
        if start_dt and not existing.scheduled_start:
            existing.scheduled_start = start_dt
            changed = True
        if end_dt and not existing.scheduled_end:
            existing.scheduled_end = end_dt
            changed = True
        if existing.status != MeetingTranscription.Status.COMPLETED and status_message:
            existing.status = status
            existing.status_message = status_message
            changed = True
        if source_metadata:
            merged = dict(existing.source_metadata or {})
            merged.update(source_metadata)
            existing.source_metadata = merged
            changed = True
        if changed:
            existing.save()
        return existing

    dedup_key = compute_transcription_dedup_key(
        user_id=user.id,
        provider=provider,
        provider_meeting_id=pmid,
        calendar_event_id=ceid,
        meeting_id=getattr(meeting, 'id', None),
        automation_job_id=getattr(automation_job, 'id', None),
        calendar_recording_id=getattr(calendar_recording, 'id', None),
        meeting_url=meeting_url,
    )

    defaults = {
        'user': user,
        'provider': provider,
        'source': source,
        'title': (title or '')[:500],
        'meeting_url': (meeting_url or '')[:512],
        'provider_meeting_id': pmid[:255],
        'calendar_event_id': ceid[:255],
        'meeting': meeting,
        'calendar_recording': calendar_recording,
        'automation_job': automation_job,
        'scheduled_start': start_dt,
        'scheduled_end': end_dt,
        'status': status,
        'status_message': status_message,
        'next_retry_at': end_dt or start_dt,
        'source_metadata': source_metadata or {},
    }

    try:
        with transaction.atomic():
            obj, _ = MeetingTranscription.objects.get_or_create(
                dedup_key=dedup_key,
                defaults=defaults,
            )
            return obj
    except IntegrityError:
        existing = find_existing_transcription(
            user_id=user.id,
            provider=provider,
            provider_meeting_id=pmid,
            calendar_event_id=ceid,
            meeting_id=getattr(meeting, 'id', None),
            automation_job_id=getattr(automation_job, 'id', None),
            calendar_recording_id=getattr(calendar_recording, 'id', None),
            meeting_url=meeting_url,
        )
        if existing:
            return existing
        raise


def upsert_from_cbe(
    payload: Dict[str, Any],
    *,
    job=None,
    meeting_obj=None,
    cal_rec=None,
    delivery_id: str = '',
) -> Optional[MeetingTranscription]:
    """
    Store or update a normalized MeetingTranscription from an incoming
    CBE (Custom Browser Engine) completion webhook without disturbing
    existing Meeting / CalendarEventRecording / MeetingAutomationJob records.
    """
    user = (
        getattr(job, 'user', None)
        or getattr(cal_rec, 'user', None)
        or getattr(meeting_obj, 'created_by', None)
    )
    if user is None:
        logger.warning('upsert_from_cbe: unable to resolve owner user for delivery_id=%s', delivery_id)
        return None

    meeting_info = payload.get('meeting') if isinstance(payload.get('meeting'), dict) else {}
    tr_info = payload.get('transcription') if isinstance(payload.get('transcription'), dict) else {}

    raw_status = str(
        tr_info.get('status')
        or payload.get('status')
        or 'completed'
    ).strip().lower()

    raw_text = str(
        payload.get('transcript_text')
        or tr_info.get('text')
        or getattr(job, 'transcript_text', '')
        or getattr(cal_rec, 'transcript_text', '')
        or getattr(meeting_obj, 'transcript_text', '')
        or ''
    ).strip()

    raw_segments = (
        tr_info.get('segments')
        or payload.get('transcript_segments')
        or getattr(job, 'transcript_segments', None)
    )
    raw_speaker_segments = (
        payload.get('speaker_segments')
        or getattr(job, 'speaker_segments', None)
    )

    segments = _normalize_segments(raw_segments)
    speaker_segments = _normalize_segments(raw_speaker_segments)
    if not segments and speaker_segments:
        segments = speaker_segments
    if not speaker_segments and segments:
        speaker_segments = segments

    if not raw_text and segments:
        raw_text = _segments_to_text(segments)

    participants = _extract_participants(
        payload.get('participants') or getattr(job, 'participants', None),
        speaker_segments or segments,
    )

    calendar_event_id = str(
        meeting_info.get('calendar_event_id')
        or payload.get('calendar_event_id')
        or getattr(job, 'external_event_id', '')
        or getattr(cal_rec, 'event_id', '')
        or getattr(meeting_obj, 'google_event_id', '')
        or ''
    ).strip()

    meeting_url = str(
        meeting_info.get('meeting_url')
        or payload.get('meeting_url')
        or getattr(job, 'meeting_link', '')
        or getattr(cal_rec, 'meeting_link', '')
        or getattr(meeting_obj, 'meeting_link', '')
        or ''
    ).strip()

    provider_meeting_id = str(
        meeting_info.get('meeting_id')
        or payload.get('provider_meeting_id')
        or payload.get('meeting_code')
        or payload.get('cbe_session_id')
        or getattr(job, 'cbe_meeting_id', '')
        or getattr(meeting_obj, 'provider_meeting_id', '')
        or ''
    ).strip()

    title = str(
        meeting_info.get('title')
        or payload.get('meeting_title')
        or payload.get('title')
        or getattr(job, 'title', '')
        or getattr(meeting_obj, 'agenda', '')
        or 'Google Meet'
    ).strip()

    scheduled_start = (
        _parse_dt(payload.get('scheduled_start'))
        or getattr(job, 'scheduled_start', None)
        or getattr(meeting_obj, 'scheduled_start', None)
    )
    scheduled_end = (
        _parse_dt(payload.get('scheduled_end'))
        or getattr(job, 'scheduled_end', None)
        or getattr(meeting_obj, 'scheduled_end', None)
    )
    ended_at = (
        _parse_dt(payload.get('ended_at'))
        or _parse_dt(payload.get('meeting_ended_at'))
        or timezone.now()
    )

    is_success = raw_status in ('completed', 'success', 'succeeded', 'done', 'ready')
    has_content = bool(raw_text or segments or speaker_segments)

    if is_success and has_content:
        norm_status = MeetingTranscription.Status.COMPLETED
        status_message = ''
    elif is_success and not has_content:
        norm_status = MeetingTranscription.Status.UNAVAILABLE
        status_message = 'CBE completed without capturing spoken transcript text.'
    else:
        norm_status = MeetingTranscription.Status.FAILED
        status_message = str(payload.get('error') or payload.get('error_message') or f'CBE reported status: {raw_status}')

    existing = find_existing_transcription(
        user_id=user.id,
        provider=MeetingTranscription.Provider.GOOGLE_MEET,
        provider_meeting_id=provider_meeting_id,
        calendar_event_id=calendar_event_id,
        meeting_id=getattr(meeting_obj, 'id', None),
        automation_job_id=getattr(job, 'id', None),
        calendar_recording_id=getattr(cal_rec, 'id', None),
        meeting_url=meeting_url,
    )

    meta = {
        'delivery_id': delivery_id,
        'cbe_status': raw_status,
        'duration_seconds': payload.get('duration_seconds'),
        'cbe_session_id': payload.get('cbe_session_id') or '',
    }

    if existing:
        # Preserve an already completed transcript against empty/failed retries
        if (
            existing.status == MeetingTranscription.Status.COMPLETED
            and existing.transcript_text
            and norm_status != MeetingTranscription.Status.COMPLETED
        ):
            return existing

        existing.title = title[:500] or existing.title
        if meeting_url:
            existing.meeting_url = meeting_url[:512]
        if provider_meeting_id and not existing.provider_meeting_id:
            existing.provider_meeting_id = provider_meeting_id[:255]
        if calendar_event_id and not existing.calendar_event_id:
            existing.calendar_event_id = calendar_event_id[:255]
        if meeting_obj and not existing.meeting_id:
            existing.meeting = meeting_obj
        if cal_rec and not existing.calendar_recording_id:
            existing.calendar_recording = cal_rec
        if job and not existing.automation_job_id:
            existing.automation_job = job
        if scheduled_start and not existing.scheduled_start:
            existing.scheduled_start = scheduled_start
        if scheduled_end and not existing.scheduled_end:
            existing.scheduled_end = scheduled_end
        existing.ended_at = ended_at or existing.ended_at
        if has_content:
            existing.transcript_text = raw_text
            existing.transcript_segments = segments
            existing.speaker_segments = speaker_segments
            existing.participants = participants
        existing.status = norm_status
        existing.status_message = status_message
        if norm_status == MeetingTranscription.Status.COMPLETED:
            existing.completed_at = timezone.now()
            existing.next_retry_at = None
        merged_meta = dict(existing.source_metadata or {})
        merged_meta.update({k: v for k, v in meta.items() if v not in (None, '')})
        existing.source_metadata = merged_meta
        existing.save()
        return existing

    obj = create_or_update_pending_transcription(
        user=user,
        provider=MeetingTranscription.Provider.GOOGLE_MEET,
        source=MeetingTranscription.Source.CBE,
        title=title,
        meeting_url=meeting_url,
        provider_meeting_id=provider_meeting_id,
        calendar_event_id=calendar_event_id,
        meeting=meeting_obj,
        calendar_recording=cal_rec,
        automation_job=job,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        status=norm_status,
        status_message=status_message,
        source_metadata={k: v for k, v in meta.items() if v not in (None, '')},
    )
    if has_content:
        obj.transcript_text = raw_text
        obj.transcript_segments = segments
        obj.speaker_segments = speaker_segments
        obj.participants = participants
    obj.ended_at = ended_at
    obj.status = norm_status
    obj.status_message = status_message
    if norm_status == MeetingTranscription.Status.COMPLETED:
        obj.completed_at = timezone.now()
        obj.next_retry_at = None
    obj.save()
    return obj


def _schedule_next_retry(transcription: MeetingTranscription, reason: str, now: Optional[datetime] = None) -> None:
    now = now or timezone.now()
    retry_num = transcription.retry_count + 1
    if retry_num > MAX_ZOOM_RETRIES:
        transcription.status = MeetingTranscription.Status.UNAVAILABLE
        transcription.status_message = (
            f"{reason} Stopped retrying after {MAX_ZOOM_RETRIES} attempts."
        )
        transcription.next_retry_at = None
        transcription.retry_count = retry_num
        transcription.save(update_fields=['status', 'status_message', 'next_retry_at', 'retry_count', 'updated_at'])
        return

    delay_min = ZOOM_RETRY_BACKOFF_MINUTES[min(retry_num - 1, len(ZOOM_RETRY_BACKOFF_MINUTES) - 1)]
    transcription.status = MeetingTranscription.Status.WAITING_FOR_PROVIDER
    transcription.status_message = reason
    transcription.retry_count = retry_num
    transcription.next_retry_at = now + timedelta(minutes=delay_min)
    transcription.save(update_fields=['status', 'status_message', 'retry_count', 'next_retry_at', 'updated_at'])


def _pick_zoom_transcript_file(recording_files: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(recording_files, list):
        return None
    for rf in recording_files:
        if not isinstance(rf, dict):
            continue
        ftype = str(rf.get('file_type') or '').upper()
        rtype = str(rf.get('recording_type') or '').lower()
        fext = str(rf.get('file_extension') or '').upper()
        if ftype == 'TRANSCRIPT' or rtype == 'audio_transcript' or fext == 'VTT':
            return rf
    return None


def fetch_and_store_zoom_transcript(
    transcription: MeetingTranscription,
    *,
    force: bool = False,
    webhook_recording_data: Optional[Dict[str, Any]] = None,
    download_token: Optional[str] = None,
) -> MeetingTranscription:
    """
    Fetch a Zoom cloud recording VTT transcript for a MeetingTranscription,
    parse it, store the raw VTT file and normalized fields, and update status.
    """
    from accounts.models import ZoomCredentials
    from accounts.zoom_services import (
        ZoomAuthError,
        ZoomRecordingNotFoundError,
        ZoomScopeError,
        download_zoom_recording_file,
        get_zoom_meeting_recordings,
    )

    if transcription.provider != MeetingTranscription.Provider.ZOOM:
        return transcription

    if (
        not force
        and transcription.status == MeetingTranscription.Status.COMPLETED
        and transcription.transcript_text
    ):
        return transcription

    if not transcription.provider_meeting_id:
        transcription.status = MeetingTranscription.Status.UNAVAILABLE
        transcription.status_message = 'Zoom meeting ID is missing; cannot fetch cloud transcript.'
        transcription.next_retry_at = None
        transcription.save(update_fields=['status', 'status_message', 'next_retry_at', 'updated_at'])
        return transcription

    try:
        creds = ZoomCredentials.objects.get(user=transcription.user, is_active=True)
    except ZoomCredentials.DoesNotExist:
        transcription.status = MeetingTranscription.Status.FAILED
        transcription.status_message = 'Zoom account is not connected. Reconnect Zoom in Settings.'
        transcription.next_retry_at = None
        transcription.save(update_fields=['status', 'status_message', 'next_retry_at', 'updated_at'])
        return transcription

    recording_data = webhook_recording_data
    if recording_data is None:
        try:
            recording_data = get_zoom_meeting_recordings(creds, transcription.provider_meeting_id)
        except ZoomScopeError as exc:
            transcription.status = MeetingTranscription.Status.FAILED
            transcription.status_message = str(exc)
            transcription.next_retry_at = None
            transcription.save(update_fields=['status', 'status_message', 'next_retry_at', 'updated_at'])
            return transcription
        except ZoomRecordingNotFoundError:
            _schedule_next_retry(
                transcription,
                'Waiting for Zoom cloud recording to become available.',
            )
            return transcription
        except ZoomAuthError as exc:
            transcription.status = MeetingTranscription.Status.FAILED
            transcription.status_message = f'Zoom authentication error: {exc}'
            transcription.next_retry_at = None
            transcription.save(update_fields=['status', 'status_message', 'next_retry_at', 'updated_at'])
            return transcription
        except Exception as exc:
            logger.exception('Zoom recording fetch error for transcription %s', transcription.id)
            _schedule_next_retry(
                transcription,
                f'Temporary error while checking Zoom recordings: {exc}',
            )
            return transcription

    recording_files = recording_data.get('recording_files') or []
    transcript_rf = _pick_zoom_transcript_file(recording_files)

    if not transcript_rf:
        any_processing = any(
            str(rf.get('status') or '').lower() == 'processing'
            for rf in recording_files
            if isinstance(rf, dict)
        )
        if any_processing or not recording_files:
            _schedule_next_retry(
                transcription,
                'Zoom cloud recording is still processing.',
            )
        else:
            _schedule_next_retry(
                transcription,
                'Zoom cloud recording found, waiting for audio transcript (VTT) file. Ensure Audio Transcript is enabled in Zoom Cloud Recording settings.',
            )
        return transcription

    rf_status = str(transcript_rf.get('status') or 'completed').lower()
    if rf_status == 'processing':
        _schedule_next_retry(
            transcription,
            'Zoom audio transcript file is still processing.',
        )
        return transcription

    download_url = str(transcript_rf.get('download_url') or '').strip()
    if not download_url:
        _schedule_next_retry(
            transcription,
            'Zoom transcript file has no download URL yet.',
        )
        return transcription

    try:
        vtt_bytes = download_zoom_recording_file(
            creds,
            download_url,
            download_token=download_token,
        )
    except ZoomScopeError as exc:
        transcription.status = MeetingTranscription.Status.FAILED
        transcription.status_message = str(exc)
        transcription.next_retry_at = None
        transcription.save(update_fields=['status', 'status_message', 'next_retry_at', 'updated_at'])
        return transcription
    except Exception as exc:
        logger.exception('Zoom VTT download error for transcription %s', transcription.id)
        _schedule_next_retry(
            transcription,
            f'Failed to download Zoom transcript file: {exc}',
        )
        return transcription

    vtt_text = vtt_bytes.decode('utf-8', errors='replace')
    parsed = parse_vtt_transcript(vtt_text)

    if not parsed['transcript_text'] and not parsed['transcript_segments']:
        transcription.status = MeetingTranscription.Status.UNAVAILABLE
        transcription.status_message = 'Zoom VTT transcript file was empty.'
        transcription.next_retry_at = None
        transcription.save(update_fields=['status', 'status_message', 'next_retry_at', 'updated_at'])
        return transcription

    recording_id = str(transcript_rf.get('id') or recording_data.get('uuid') or '').strip()
    topic = str(recording_data.get('topic') or '').strip()
    rec_start = _parse_dt(recording_data.get('start_time') or transcript_rf.get('recording_start'))
    rec_end = _parse_dt(transcript_rf.get('recording_end'))

    filename = f"zoom_{transcription.provider_meeting_id}_{recording_id or transcription.id}.vtt"
    filename = re.sub(r'[^A-Za-z0-9._-]', '_', filename)[:120]

    transcription.transcript_file.save(filename, ContentFile(vtt_bytes), save=False)
    if topic and not transcription.title:
        transcription.title = topic[:500]
    if recording_id:
        transcription.provider_recording_id = recording_id[:255]
    if rec_start and not transcription.scheduled_start:
        transcription.scheduled_start = rec_start
    if rec_end:
        transcription.ended_at = rec_end

    transcription.transcript_text = parsed['transcript_text']
    transcription.transcript_segments = parsed['transcript_segments']
    transcription.speaker_segments = parsed['speaker_segments']
    transcription.participants = parsed['participants']
    transcription.status = MeetingTranscription.Status.COMPLETED
    transcription.status_message = ''
    transcription.completed_at = timezone.now()
    transcription.next_retry_at = None

    meta = dict(transcription.source_metadata or {})
    meta.update({
        'zoom_uuid': recording_data.get('uuid') or '',
        'zoom_recording_count': len(recording_files),
        'zoom_transcript_file_id': recording_id,
        'zoom_file_size': transcript_rf.get('file_size'),
    })
    transcription.source_metadata = meta
    transcription.save()

    # Keep linked prospects.Meeting in sync without overwriting existing data
    if transcription.meeting_id:
        meeting_obj = transcription.meeting
        update_fields = []
        if not meeting_obj.transcript_text:
            meeting_obj.transcript_text = parsed['transcript_text']
            update_fields.append('transcript_text')
        if not meeting_obj.transcript_segments:
            meeting_obj.transcript_segments = parsed['transcript_segments']
            update_fields.append('transcript_segments')
        if not meeting_obj.speaker_segments:
            meeting_obj.speaker_segments = parsed['speaker_segments']
            update_fields.append('speaker_segments')
        if not meeting_obj.diarization_participants and parsed['participants']:
            meeting_obj.diarization_participants = parsed['participants']
            update_fields.append('diarization_participants')
        if meeting_obj.transcription_status != 'COMPLETED':
            meeting_obj.transcription_status = 'COMPLETED'
            update_fields.append('transcription_status')
        if not meeting_obj.transcription_completed_at:
            meeting_obj.transcription_completed_at = timezone.now()
            update_fields.append('transcription_completed_at')
        if update_fields:
            meeting_obj.save(update_fields=update_fields + ['updated_at'])

    return transcription


def compute_zoom_url_validation_response(plain_token: str, secret_token: str) -> Dict[str, str]:
    """Compute Zoom's endpoint.url_validation CRC HMAC-SHA256 response."""
    encrypted = hmac.new(
        secret_token.encode('utf-8'),
        plain_token.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
    return {
        'plainToken': plain_token,
        'encryptedToken': encrypted,
    }


def verify_zoom_webhook_signature(
    headers: Dict[str, Any],
    raw_body: bytes,
    secret_token: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Verify Zoom webhook x-zm-signature and x-zm-request-timestamp headers.
    Per Zoom docs:
      message = f"v0:{timestamp}:{raw_body_str}"
      expected = f"v0={hmac_sha256_hex(secret, message)}"
    """
    secret = (secret_token if secret_token is not None else getattr(settings, 'ZOOM_WEBHOOK_SECRET_TOKEN', '')).strip()
    if not secret:
        return False, 'ZOOM_WEBHOOK_SECRET_TOKEN is not configured.'

    signature = (
        headers.get('x-zm-signature')
        or headers.get('X-Zm-Signature')
        or headers.get('HTTP_X_ZM_SIGNATURE')
        or ''
    ).strip()
    timestamp = (
        headers.get('x-zm-request-timestamp')
        or headers.get('X-Zm-Request-Timestamp')
        or headers.get('HTTP_X_ZM_REQUEST_TIMESTAMP')
        or ''
    ).strip()

    if not signature or not timestamp:
        return False, 'Missing Zoom webhook signature headers.'

    try:
        ts_int = int(timestamp)
    except ValueError:
        return False, 'Invalid Zoom webhook timestamp header.'

    if abs(int(time.time()) - ts_int) > ZOOM_WEBHOOK_TOLERANCE_SECONDS:
        return False, 'Zoom webhook timestamp outside tolerance window.'

    body_str = raw_body.decode('utf-8') if isinstance(raw_body, (bytes, bytearray)) else str(raw_body)
    message = f'v0:{timestamp}:{body_str}'
    expected = 'v0=' + hmac.new(
        secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        return False, 'Invalid Zoom webhook signature.'

    return True, ''


def handle_zoom_webhook_payload(payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    """
    Handle verified Zoom webhook events:
    - endpoint.url_validation -> returns CRC challenge response
    - recording.completed / recording.transcript_completed -> upserts & fetches transcript
    """
    event = str(payload.get('event') or '').strip()

    if event == 'endpoint.url_validation':
        plain_token = str((payload.get('payload') or {}).get('plainToken') or '').strip()
        secret = getattr(settings, 'ZOOM_WEBHOOK_SECRET_TOKEN', '').strip()
        if not plain_token or not secret:
            return 400, {'error': 'Missing plainToken or ZOOM_WEBHOOK_SECRET_TOKEN.'}
        return 200, compute_zoom_url_validation_response(plain_token, secret)

    if event not in ('recording.completed', 'recording.transcript_completed'):
        return 200, {'status': 'ignored', 'event': event}

    inner = payload.get('payload') or {}
    obj = inner.get('object') or {}
    download_token = payload.get('download_token') or inner.get('download_token')

    meeting_id = str(obj.get('id') or '').strip()
    meeting_uuid = str(obj.get('uuid') or '').strip()
    host_id = str(obj.get('host_id') or '').strip()
    host_email = str(obj.get('host_email') or '').strip()
    topic = str(obj.get('topic') or 'Zoom Meeting').strip()
    start_time = _parse_dt(obj.get('start_time'))
    duration_min = obj.get('duration')
    scheduled_end = None
    if start_time and duration_min:
        try:
            scheduled_end = start_time + timedelta(minutes=int(duration_min))
        except (TypeError, ValueError):
            scheduled_end = None

    if not meeting_id and not meeting_uuid:
        return 200, {'status': 'ignored', 'reason': 'No meeting id in payload.'}

    # 1. Try matching existing MeetingTranscription
    transcription = None
    id_candidates = [c for c in (meeting_id, meeting_uuid) if c]
    if id_candidates:
        transcription = (
            MeetingTranscription.objects
            .filter(provider=MeetingTranscription.Provider.ZOOM, provider_meeting_id__in=id_candidates)
            .select_related('user', 'meeting')
            .first()
        )

    # 2. Try matching prospects.Meeting
    meeting_obj = None
    if transcription is None and id_candidates:
        from prospects.models import Meeting
        meeting_obj = (
            Meeting.objects
            .filter(provider_meeting_id__in=id_candidates)
            .select_related('created_by', 'prospect')
            .first()
        )

    # 3. Resolve owner user
    owner = getattr(transcription, 'user', None) or getattr(meeting_obj, 'created_by', None)
    if owner is None:
        from accounts.models import ZoomCredentials
        creds_qs = ZoomCredentials.objects.filter(is_active=True).select_related('user')
        creds = None
        if host_id:
            creds = creds_qs.filter(zoom_user_id=host_id).first()
        if creds is None and host_email:
            creds = creds_qs.filter(email__iexact=host_email).first()
        owner = getattr(creds, 'user', None)

    if owner is None:
        logger.info('Zoom webhook %s for meeting %s did not match any connected user.', event, meeting_id)
        return 200, {'status': 'ignored', 'reason': 'No matching user or meeting found.'}

    if transcription is None:
        meeting_title = topic
        if meeting_obj is not None:
            meeting_title = (
                (meeting_obj.agenda or '').strip()[:120]
                or (meeting_obj.prospect.company_name if meeting_obj.prospect_id else '')
                or topic
            )
        m_start = getattr(meeting_obj, 'scheduled_datetime', None) or start_time
        m_end = scheduled_end
        if not m_end and m_start:
            default_dur = getattr(settings, 'MEETING_DEFAULT_DURATION_MINUTES', 30)
            m_end = m_start + timedelta(minutes=default_dur)
        transcription = create_or_update_pending_transcription(
            user=owner,
            provider=MeetingTranscription.Provider.ZOOM,
            source=MeetingTranscription.Source.ZOOM_CLOUD_RECORDING,
            title=meeting_title,
            meeting_url=getattr(meeting_obj, 'meeting_link', '') or '',
            provider_meeting_id=meeting_id or meeting_uuid,
            calendar_event_id=getattr(meeting_obj, 'calendar_event_id', '') or getattr(meeting_obj, 'google_event_id', '') or '',
            meeting=meeting_obj,
            scheduled_start=m_start,
            scheduled_end=m_end,
            status=MeetingTranscription.Status.PROCESSING,
            status_message='Received Zoom recording.completed webhook.',
            source_metadata={'zoom_event': event, 'zoom_uuid': meeting_uuid},
        )

    # If webhook includes recording_files with a TRANSCRIPT file, use it directly;
    # otherwise fall back to fetching from Zoom REST API.
    webhook_files = obj.get('recording_files') or []
    use_webhook_data = obj if _pick_zoom_transcript_file(webhook_files) else None

    result = fetch_and_store_zoom_transcript(
        transcription,
        force=False,
        webhook_recording_data=use_webhook_data,
        download_token=download_token,
    )
    return 200, {
        'status': 'processed',
        'transcription_id': str(result.id),
        'transcription_status': result.status,
    }


def process_pending_transcriptions(
    *,
    max_items: int = 50,
    now: Optional[datetime] = None,
    user=None,
) -> Dict[str, int]:
    """
    Periodic recovery worker for pending Zoom transcriptions.
    Also discovers ended Zoom prospects.Meeting rows that do not yet have a
    MeetingTranscription record.
    """
    now = now or timezone.now()
    summary = {
        'discovered': 0,
        'checked': 0,
        'completed': 0,
        'waiting': 0,
        'unavailable': 0,
        'failed': 0,
    }

    # Step 1: Discover ended Zoom prospects.Meeting rows without a MeetingTranscription
    from prospects.models import Meeting

    default_dur = getattr(settings, 'MEETING_DEFAULT_DURATION_MINUTES', 30)
    cutoff = now - timedelta(minutes=default_dur)

    ended_meetings_qs = Meeting.objects.filter(
        meeting_provider='ZOOM',
        scheduled_datetime__lt=cutoff,
    ).exclude(
        provider_meeting_id=''
    ).select_related('created_by', 'prospect')

    if user is not None:
        ended_meetings_qs = ended_meetings_qs.filter(created_by=user)

    for m in ended_meetings_qs[:max_items]:
        if not m.created_by_id:
            continue
        pmid = (m.provider_meeting_id or '').strip()
        if not pmid:
            continue
        ceid = (m.calendar_event_id or m.google_event_id or '').strip()
        existing = find_existing_transcription(
            user_id=m.created_by_id,
            provider=MeetingTranscription.Provider.ZOOM,
            provider_meeting_id=pmid,
            calendar_event_id=ceid,
            meeting_id=m.id,
        )
        if existing is None:
            m_title = (
                (m.agenda or '').strip()[:120]
                or (f"Meeting with {m.prospect.company_name}" if m.prospect_id else 'Zoom Meeting')
            )
            create_or_update_pending_transcription(
                user=m.created_by,
                provider=MeetingTranscription.Provider.ZOOM,
                source=MeetingTranscription.Source.ZOOM_CLOUD_RECORDING,
                title=m_title,
                meeting_url=m.meeting_link or '',
                provider_meeting_id=pmid,
                calendar_event_id=ceid,
                meeting=m,
                scheduled_start=m.scheduled_datetime,
                scheduled_end=m.scheduled_datetime + timedelta(minutes=default_dur),
                status=MeetingTranscription.Status.PENDING,
                status_message='Queued for Zoom cloud transcript retrieval.',
            )
            summary['discovered'] += 1

    # Step 2: Process due pending / waiting Zoom transcriptions
    due_qs = MeetingTranscription.objects.filter(
        provider=MeetingTranscription.Provider.ZOOM,
        status__in=[
            MeetingTranscription.Status.PENDING,
            MeetingTranscription.Status.WAITING_FOR_PROVIDER,
        ],
    ).filter(
        Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now)
    ).filter(
        Q(scheduled_end__isnull=True) | Q(scheduled_end__lte=now)
    ).select_related('user', 'meeting').order_by('next_retry_at', 'created_at')

    if user is not None:
        due_qs = due_qs.filter(user=user)

    for item in due_qs[:max_items]:
        summary['checked'] += 1
        updated = fetch_and_store_zoom_transcript(item, force=False)
        if updated.status == MeetingTranscription.Status.COMPLETED:
            summary['completed'] += 1
        elif updated.status == MeetingTranscription.Status.WAITING_FOR_PROVIDER:
            summary['waiting'] += 1
        elif updated.status == MeetingTranscription.Status.UNAVAILABLE:
            summary['unavailable'] += 1
        elif updated.status == MeetingTranscription.Status.FAILED:
            summary['failed'] += 1

    return summary


def _infer_provider_and_source(meeting_url: str, provider_hint: str = '') -> Tuple[str, str]:
    hint = (provider_hint or '').strip().upper()
    url_lower = (meeting_url or '').strip().lower()
    if hint == 'ZOOM' or 'zoom.us' in url_lower:
        return (
            MeetingTranscription.Provider.ZOOM,
            MeetingTranscription.Source.ZOOM_CLOUD_RECORDING,
        )
    return (
        MeetingTranscription.Provider.GOOGLE_MEET,
        MeetingTranscription.Source.CBE,
    )


def backfill_historical_transcriptions(*, dry_run: bool = False) -> Dict[str, Any]:
    """
    Safely and idempotently import historical non-empty transcripts from:
    - prospects.Meeting
    - accounts.CalendarEventRecording
    - accounts.MeetingAutomationJob

    Never deletes historical records and never overwrites a newer completed
    MeetingTranscription.
    """
    from accounts.models import CalendarEventRecording, MeetingAutomationJob
    from prospects.models import Meeting

    stats = {'created': 0, 'updated': 0, 'skipped': 0, 'dry_run': dry_run}

    def _import_record(
        *,
        user,
        provider: str,
        source: str,
        title: str,
        meeting_url: str,
        provider_meeting_id: str,
        calendar_event_id: str,
        meeting=None,
        calendar_recording=None,
        automation_job=None,
        scheduled_start=None,
        scheduled_end=None,
        ended_at=None,
        raw_text: str = '',
        raw_segments=None,
        raw_speaker_segments=None,
        raw_participants=None,
        origin_label: str = '',
    ):
        segments = _normalize_segments(raw_segments)
        speaker_segments = _normalize_segments(raw_speaker_segments)
        if not segments and speaker_segments:
            segments = speaker_segments
        if not speaker_segments and segments:
            speaker_segments = segments
        text = (raw_text or '').strip()
        if not text and segments:
            text = _segments_to_text(segments)
        if not text and not segments:
            stats['skipped'] += 1
            return

        participants = _extract_participants(raw_participants, speaker_segments or segments)
        existing = find_existing_transcription(
            user_id=user.id,
            provider=provider,
            provider_meeting_id=provider_meeting_id,
            calendar_event_id=calendar_event_id,
            meeting_id=getattr(meeting, 'id', None),
            automation_job_id=getattr(automation_job, 'id', None),
            calendar_recording_id=getattr(calendar_recording, 'id', None),
            meeting_url=meeting_url,
        )

        if existing:
            if existing.status == MeetingTranscription.Status.COMPLETED and existing.transcript_text:
                stats['skipped'] += 1
                return
            if not dry_run:
                existing.title = existing.title or (title or '')[:500]
                existing.meeting_url = existing.meeting_url or (meeting_url or '')[:512]
                if provider_meeting_id and not existing.provider_meeting_id:
                    existing.provider_meeting_id = provider_meeting_id[:255]
                if calendar_event_id and not existing.calendar_event_id:
                    existing.calendar_event_id = calendar_event_id[:255]
                if meeting and not existing.meeting_id:
                    existing.meeting = meeting
                if calendar_recording and not existing.calendar_recording_id:
                    existing.calendar_recording = calendar_recording
                if automation_job and not existing.automation_job_id:
                    existing.automation_job = automation_job
                existing.transcript_text = text
                existing.transcript_segments = segments
                existing.speaker_segments = speaker_segments
                existing.participants = participants
                existing.status = MeetingTranscription.Status.COMPLETED
                existing.status_message = ''
                existing.completed_at = existing.completed_at or ended_at or timezone.now()
                existing.save()
            stats['updated'] += 1
            return

        if not dry_run:
            obj = create_or_update_pending_transcription(
                user=user,
                provider=provider,
                source=source,
                title=title,
                meeting_url=meeting_url,
                provider_meeting_id=provider_meeting_id,
                calendar_event_id=calendar_event_id,
                meeting=meeting,
                calendar_recording=calendar_recording,
                automation_job=automation_job,
                scheduled_start=scheduled_start,
                scheduled_end=scheduled_end,
                status=MeetingTranscription.Status.COMPLETED,
                status_message='',
                source_metadata={'backfilled_from': origin_label},
            )
            obj.transcript_text = text
            obj.transcript_segments = segments
            obj.speaker_segments = speaker_segments
            obj.participants = participants
            obj.ended_at = ended_at or scheduled_end
            obj.completed_at = ended_at or scheduled_end or timezone.now()
            obj.next_retry_at = None
            obj.save()
        stats['created'] += 1

    # 1. prospects.Meeting
    meetings_qs = Meeting.objects.filter(
        Q(transcript_text__gt='')
        | ~Q(transcript_segments=[])
        | ~Q(speaker_segments=[])
    ).select_related('created_by', 'prospect')
    for m in meetings_qs.iterator():
        if not m.created_by_id:
            stats['skipped'] += 1
            continue
        url = m.meeting_link or ''
        provider, source = _infer_provider_and_source(url, m.meeting_provider)
        m_title = (
            (m.agenda or '').strip()[:120]
            or (f"Meeting with {m.prospect.company_name}" if m.prospect_id else 'Meeting')
        )
        _import_record(
            user=m.created_by,
            provider=provider,
            source=source,
            title=m_title,
            meeting_url=url,
            provider_meeting_id=(m.provider_meeting_id or '').strip(),
            calendar_event_id=(m.calendar_event_id or m.google_event_id or '').strip(),
            meeting=m,
            scheduled_start=m.scheduled_datetime,
            scheduled_end=m.transcription_completed_at,
            ended_at=m.transcription_completed_at,
            raw_text=m.transcript_text or '',
            raw_segments=m.transcript_segments,
            raw_speaker_segments=m.speaker_segments,
            raw_participants=m.diarization_participants,
            origin_label='prospects.Meeting',
        )

    # 2. accounts.CalendarEventRecording
    cal_recs_qs = CalendarEventRecording.objects.filter(
        Q(transcript_text__gt='')
        | ~Q(transcript_segments=[])
        | ~Q(speaker_segments=[])
    ).select_related('user')
    for cr in cal_recs_qs.iterator():
        url = cr.meeting_link or ''
        provider, source = _infer_provider_and_source(url)
        _import_record(
            user=cr.user,
            provider=provider,
            source=source,
            title=f'Calendar Meeting ({cr.event_id[:16]})' if cr.event_id else 'Calendar Meeting',
            meeting_url=url,
            provider_meeting_id='',
            calendar_event_id=(cr.event_id or '').strip(),
            calendar_recording=cr,
            scheduled_start=cr.created_at,
            scheduled_end=cr.transcription_completed_at,
            ended_at=cr.transcription_completed_at,
            raw_text=cr.transcript_text or '',
            raw_segments=cr.transcript_segments,
            raw_speaker_segments=cr.speaker_segments,
            raw_participants=cr.diarization_participants,
            origin_label='accounts.CalendarEventRecording',
        )

    # 3. accounts.MeetingAutomationJob
    jobs_qs = MeetingAutomationJob.objects.filter(
        Q(transcript_text__gt='')
        | ~Q(transcript_segments=[])
        | ~Q(speaker_segments=[])
    ).select_related('user', 'meeting', 'calendar_recording')
    for job in jobs_qs.iterator():
        url = job.meeting_link or ''
        provider, source = _infer_provider_and_source(url)
        _import_record(
            user=job.user,
            provider=provider,
            source=source,
            title=job.title or 'Automated Meeting',
            meeting_url=url,
            provider_meeting_id=(job.cbe_meeting_id or '').strip(),
            calendar_event_id=(job.external_event_id or '').strip(),
            meeting=job.meeting,
            calendar_recording=job.calendar_recording,
            automation_job=job,
            scheduled_start=job.scheduled_start,
            scheduled_end=job.scheduled_end,
            ended_at=job.completed_at or job.scheduled_end,
            raw_text=job.transcript_text or '',
            raw_segments=job.transcript_segments,
            raw_speaker_segments=job.speaker_segments,
            raw_participants=job.participants,
            origin_label='accounts.MeetingAutomationJob',
        )

    return stats
