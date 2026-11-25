export const PROVIDER_META = {
  GOOGLE_MEET: {
    label: 'Google Meet',
    shortLabel: 'Meet',
    badgeClass: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    dotClass: 'bg-emerald-500',
  },
  ZOOM: {
    label: 'Zoom',
    shortLabel: 'Zoom',
    badgeClass: 'bg-sky-50 text-sky-700 border-sky-200',
    dotClass: 'bg-sky-500',
  },
};

export const SOURCE_META = {
  CBE: 'CBE Bot',
  ZOOM_CLOUD_RECORDING: 'Zoom Cloud',
};

export const STATUS_META = {
  COMPLETED: {
    label: 'Completed',
    badgeClass: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  },
  PENDING: {
    label: 'Pending',
    badgeClass: 'bg-amber-50 text-amber-700 border-amber-200',
  },
  WAITING_FOR_PROVIDER: {
    label: 'Waiting for Zoom',
    badgeClass: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  },
  PROCESSING: {
    label: 'Processing',
    badgeClass: 'bg-blue-50 text-blue-700 border-blue-200',
  },
  FAILED: {
    label: 'Failed',
    badgeClass: 'bg-rose-50 text-rose-700 border-rose-200',
  },
  UNAVAILABLE: {
    label: 'Unavailable',
    badgeClass: 'bg-slate-100 text-slate-600 border-slate-200',
  },
};

export const ACTIVE_POLL_STATUSES = new Set([
  'PENDING',
  'WAITING_FOR_PROVIDER',
  'PROCESSING',
]);

export function formatDuration(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) {
    return '—';
  }
  const total = Math.max(0, Math.round(Number(seconds)));
  if (total === 0) return '—';
  if (total < 60) return `${total}s`;
  const hours = Math.floor(total / 3600);
  const mins = Math.floor((total % 3600) / 60);
  if (hours > 0) {
    return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
  }
  return `${mins}m`;
}

export function formatTranscriptSegmentLine(seg) {
  if (!seg || typeof seg !== 'object') return '';
  const text = String(seg.text || '').trim();
  if (!text) return '';
  const start = String(seg.start || '').trim();
  const speaker = String(seg.speaker || '').trim();
  const parts = [];
  if (start) parts.push(`[${start}]`);
  if (speaker) parts.push(`${speaker}:`);
  parts.push(text);
  return parts.join(' ');
}

export function getDisplaySegments(detail) {
  if (!detail) return [];
  if (Array.isArray(detail.speaker_segments) && detail.speaker_segments.length > 0) {
    return detail.speaker_segments;
  }
  if (Array.isArray(detail.transcript_segments) && detail.transcript_segments.length > 0) {
    return detail.transcript_segments;
  }
  return [];
}

export function filterTranscriptSegments(segments, query) {
  if (!Array.isArray(segments)) return [];
  const q = String(query || '').trim().toLowerCase();
  if (!q) return segments;
  return segments.filter((seg) => {
    const speaker = String(seg?.speaker || '').toLowerCase();
    const text = String(seg?.text || '').toLowerCase();
    const start = String(seg?.start || '').toLowerCase();
    return speaker.includes(q) || text.includes(q) || start.includes(q);
  });
}

export function buildDownloadableTranscriptText(detail) {
  if (!detail) return '';
  const providerLabel = PROVIDER_META[detail.provider]?.label || detail.provider || 'Meeting';
  const headerLines = [
    `Title: ${detail.title || 'Untitled Meeting'}`,
    `Provider: ${providerLabel}`,
    `Status: ${STATUS_META[detail.status]?.label || detail.status || ''}`,
  ];
  if (detail.scheduled_start) {
    headerLines.push(`Scheduled: ${detail.scheduled_start}`);
  }
  if (detail.meeting_url) {
    headerLines.push(`Meeting Link: ${detail.meeting_url}`);
  }
  if (Array.isArray(detail.participants) && detail.participants.length > 0) {
    headerLines.push(`Participants: ${detail.participants.join(', ')}`);
  }
  headerLines.push('---', '');

  const segments = getDisplaySegments(detail);
  const body =
    segments.length > 0
      ? segments.map(formatTranscriptSegmentLine).filter(Boolean).join('\n')
      : String(detail.transcript_text || '').trim();

  return `${headerLines.join('\n')}${body}\n`;
}

export function inferCalendarMeetingProvider(url, explicitProvider = '') {
  const norm = String(explicitProvider || '').trim().toUpperCase();
  if (norm === 'ZOOM' || norm === 'GOOGLE_MEET' || norm === 'NONE') {
    return norm;
  }
  const lower = String(url || '').trim().toLowerCase();
  if (lower.includes('zoom.us')) return 'ZOOM';
  if (lower.includes('meet.google.com')) return 'GOOGLE_MEET';
  return 'NONE';
}
