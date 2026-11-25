import test from 'node:test';
import assert from 'node:assert/strict';
import {
  formatDuration,
  formatTranscriptSegmentLine,
  getDisplaySegments,
  filterTranscriptSegments,
  buildDownloadableTranscriptText,
  inferCalendarMeetingProvider,
} from './transcriptionHelpers.js';

test('formatDuration formats seconds cleanly', () => {
  assert.equal(formatDuration(null), '—');
  assert.equal(formatDuration(0), '—');
  assert.equal(formatDuration(45), '45s');
  assert.equal(formatDuration(1800), '30m');
  assert.equal(formatDuration(4320), '1h 12m');
});

test('formatTranscriptSegmentLine renders [timestamp] Speaker: text', () => {
  assert.equal(
    formatTranscriptSegmentLine({ start: '00:01:25', speaker: 'Speaker 1', text: 'Hello team.' }),
    '[00:01:25] Speaker 1: Hello team.'
  );
  assert.equal(
    formatTranscriptSegmentLine({ start: '00:00:05', speaker: '', text: 'Welcome.' }),
    '[00:00:05] Welcome.'
  );
  assert.equal(formatTranscriptSegmentLine({ start: '00:00:05', speaker: 'A', text: '  ' }), '');
});

test('filterTranscriptSegments matches speaker, text, or timestamp case-insensitively', () => {
  const segs = [
    { start: '00:00:01', speaker: 'Alice', text: 'Review Q4 budget' },
    { start: '00:01:25', speaker: 'Bob', text: 'Approved pricing' },
  ];
  assert.equal(filterTranscriptSegments(segs, '').length, 2);
  assert.equal(filterTranscriptSegments(segs, 'alice').length, 1);
  assert.equal(filterTranscriptSegments(segs, 'pricing').length, 1);
  assert.equal(filterTranscriptSegments(segs, '00:01:25').length, 1);
  assert.equal(filterTranscriptSegments(segs, 'nonexistent').length, 0);
});

test('buildDownloadableTranscriptText includes metadata header and formatted segments', () => {
  const txt = buildDownloadableTranscriptText({
    title: 'Weekly Sync',
    provider: 'ZOOM',
    status: 'COMPLETED',
    scheduled_start: '2026-11-25T10:00:00Z',
    meeting_url: 'https://us02web.zoom.us/j/123456',
    participants: ['Alice', 'Bob'],
    speaker_segments: [
      { start: '00:00:02', speaker: 'Alice', text: 'Let us begin.' },
    ],
  });
  assert.match(txt, /Title: Weekly Sync/);
  assert.match(txt, /Provider: Zoom/);
  assert.match(txt, /Participants: Alice, Bob/);
  assert.match(txt, /\[00:00:02\] Alice: Let us begin\./);
});

test('getDisplaySegments prefers speaker_segments then transcript_segments', () => {
  assert.equal(getDisplaySegments(null).length, 0);
  assert.equal(
    getDisplaySegments({ speaker_segments: [{ text: 'a' }], transcript_segments: [{ text: 'b' }, { text: 'c' }] }).length,
    1
  );
  assert.equal(
    getDisplaySegments({ speaker_segments: [], transcript_segments: [{ text: 'b' }] }).length,
    1
  );
});

test('inferCalendarMeetingProvider identifies Zoom, Google Meet, and None', () => {
  assert.equal(inferCalendarMeetingProvider('https://us02web.zoom.us/j/123'), 'ZOOM');
  assert.equal(inferCalendarMeetingProvider('https://meet.google.com/abc-defg-hij'), 'GOOGLE_MEET');
  assert.equal(inferCalendarMeetingProvider('https://example.com/room'), 'NONE');
  assert.equal(inferCalendarMeetingProvider('', 'ZOOM'), 'ZOOM');
});
