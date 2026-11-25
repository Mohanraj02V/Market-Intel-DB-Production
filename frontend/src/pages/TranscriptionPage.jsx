import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { toast } from 'react-toastify';
import {
  AlertTriangle,
  Calendar,
  Check,
  ChevronLeft,
  ChevronRight,
  Clock,
  Copy,
  Download,
  ExternalLink,
  FileText,
  RefreshCw,
  Search,
  Users,
  Video,
  X,
} from 'lucide-react';
import api from '../services/api';
import { formatDateTimeForUser } from '../utils/timezone';
import {
  ACTIVE_POLL_STATUSES,
  PROVIDER_META,
  SOURCE_META,
  STATUS_META,
  buildDownloadableTranscriptText,
  filterTranscriptSegments,
  formatDuration,
  getDisplaySegments,
} from './transcriptionHelpers';

const PAGE_SIZE = 20;

function highlightText(text, query) {
  const str = String(text || '');
  const q = String(query || '').trim();
  if (!q) return str;
  const escaped = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const parts = str.split(new RegExp(`(${escaped})`, 'gi'));
  return parts.map((part, idx) =>
    part.toLowerCase() === q.toLowerCase() ? (
      <mark key={idx} className="bg-amber-200/80 text-slate-900 rounded px-0.5">
        {part}
      </mark>
    ) : (
      part
    )
  );
}

export default function TranscriptionPage() {
  const { user } = useSelector((state) => state.auth);
  const canProcessPending = Boolean(user?.is_superuser || user?.role === 'MANAGER');

  // Filters & pagination
  const [searchInput, setSearchInput] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [providerFilter, setProviderFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [ordering, setOrdering] = useState('-scheduled_start');
  const [page, setPage] = useState(1);

  // Data state
  const [items, setItems] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loadingList, setLoadingList] = useState(true);
  const [listError, setListError] = useState('');

  // Detail state
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [refreshingDetail, setRefreshingDetail] = useState(false);
  const [processingPending, setProcessingPending] = useState(false);

  // Transcript viewer controls
  const [innerSearch, setInnerSearch] = useState('');
  const [copiedTranscript, setCopiedTranscript] = useState(false);
  const [copiedUrl, setCopiedUrl] = useState(false);

  // Zoom scope status banner
  const [zoomNeedsReconnect, setZoomNeedsReconnect] = useState(false);

  // Debounce search input
  useEffect(() => {
    const t = setTimeout(() => {
      setSearchQuery(searchInput.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [searchInput]);

  // Check Zoom scope status once on mount
  useEffect(() => {
    let active = true;
    api
      .get('/auth/meeting-providers/status/')
      .then((res) => {
        if (!active) return;
        setZoomNeedsReconnect(Boolean(res.data?.zoom?.needs_reconnect_for_transcriptions));
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  const fetchList = useCallback(
    async ({ silent = false } = {}) => {
      if (!silent) setLoadingList(true);
      setListError('');
      try {
        const params = {
          page,
          page_size: PAGE_SIZE,
          ordering,
        };
        if (searchQuery) params.search = searchQuery;
        if (providerFilter) params.provider = providerFilter;
        if (statusFilter) params.status = statusFilter;
        if (dateFrom) params.date_from = dateFrom;
        if (dateTo) params.date_to = dateTo;

        const res = await api.get('/transcriptions/', { params });
        const data = res.data || {};
        const results = Array.isArray(data.results) ? data.results : Array.isArray(data) ? data : [];
        const count = typeof data.count === 'number' ? data.count : results.length;
        setItems(results);
        setTotalCount(count);

        // Keep selection valid or auto-select first row on desktop
        setSelectedId((prev) => {
          if (prev && results.some((r) => r.id === prev)) return prev;
          return results.length > 0 ? results[0].id : null;
        });
      } catch (err) {
        const msg =
          err?.response?.data?.detail ||
          err?.response?.data?.error ||
          'Failed to load meeting transcriptions.';
        setListError(msg);
      } finally {
        if (!silent) setLoadingList(false);
      }
    },
    [page, ordering, searchQuery, providerFilter, statusFilter, dateFrom, dateTo]
  );

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  const fetchDetail = useCallback(async (id, { silent = false } = {}) => {
    if (!id) {
      setDetail(null);
      return;
    }
    if (!silent) setLoadingDetail(true);
    try {
      const res = await api.get(`/transcriptions/${id}/`);
      setDetail(res.data);
    } catch (err) {
      if (!silent) {
        toast.error(err?.response?.data?.detail || 'Failed to load transcription details.');
      }
    } finally {
      if (!silent) setLoadingDetail(false);
    }
  }, []);

  useEffect(() => {
    setInnerSearch('');
    fetchDetail(selectedId);
  }, [selectedId, fetchDetail]);

  // Non-intrusive visibility-aware polling only when active pending items exist
  const hasActivePending = useMemo(
    () =>
      items.some((i) => ACTIVE_POLL_STATUSES.has(i.status)) ||
      (detail && ACTIVE_POLL_STATUSES.has(detail.status)),
    [items, detail]
  );

  const selectedIdRef = useRef(selectedId);
  selectedIdRef.current = selectedId;

  useEffect(() => {
    if (!hasActivePending) return undefined;
    const interval = setInterval(() => {
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') {
        return;
      }
      fetchList({ silent: true });
      if (selectedIdRef.current) {
        fetchDetail(selectedIdRef.current, { silent: true });
      }
    }, 20000);
    return () => clearInterval(interval);
  }, [hasActivePending, fetchList, fetchDetail]);

  const handleRefreshOne = async () => {
    if (!detail?.id) return;
    setRefreshingDetail(true);
    try {
      const res = await api.post(`/transcriptions/${detail.id}/refresh/`);
      setDetail(res.data);
      setItems((prev) =>
        prev.map((item) =>
          item.id === res.data.id
            ? {
                ...item,
                status: res.data.status,
                status_message: res.data.status_message,
                completed_at: res.data.completed_at,
                has_transcript: Boolean(res.data.transcript_text),
              }
            : item
        )
      );
      if (res.data.status === 'COMPLETED') {
        toast.success('Transcript synced and ready.');
      } else {
        toast.info(res.data.status_message || `Status: ${STATUS_META[res.data.status]?.label || res.data.status}`);
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Could not refresh transcription.');
    } finally {
      setRefreshingDetail(false);
    }
  };

  const handleProcessPending = async () => {
    setProcessingPending(true);
    try {
      const res = await api.post('/transcriptions/process-pending/', { max_items: 50 });
      const s = res.data || {};
      toast.success(
        `Checked ${s.checked || 0} pending Zoom meetings (${s.completed || 0} completed, ${s.waiting || 0} waiting).`
      );
      await fetchList({ silent: true });
      if (selectedId) await fetchDetail(selectedId, { silent: true });
    } catch (err) {
      toast.error(err?.response?.data?.detail || 'Failed to process pending transcriptions.');
    } finally {
      setProcessingPending(false);
    }
  };

  const handleCopyTranscript = async () => {
    if (!detail) return;
    const text = buildDownloadableTranscriptText(detail);
    try {
      await navigator.clipboard.writeText(text);
      setCopiedTranscript(true);
      toast.success('Transcript copied to clipboard.');
      setTimeout(() => setCopiedTranscript(false), 2000);
    } catch {
      toast.error('Failed to copy transcript.');
    }
  };

  const handleCopyUrl = async (url) => {
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      setCopiedUrl(true);
      toast.success('Meeting link copied.');
      setTimeout(() => setCopiedUrl(false), 2000);
    } catch {
      toast.error('Failed to copy link.');
    }
  };

  const handleDownloadTxt = () => {
    if (!detail) return;
    const content = buildDownloadableTranscriptText(detail);
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const safeName = String(detail.title || 'meeting-transcript')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '')
      .slice(0, 60);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${safeName || 'transcript'}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const displaySegments = useMemo(() => getDisplaySegments(detail), [detail]);
  const filteredSegments = useMemo(
    () => filterTranscriptSegments(displaySegments, innerSearch),
    [displaySegments, innerSearch]
  );

  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
  const hasFilters = Boolean(searchQuery || providerFilter || statusFilter || dateFrom || dateTo);

  const clearFilters = () => {
    setSearchInput('');
    setSearchQuery('');
    setProviderFilter('');
    setStatusFilter('');
    setDateFrom('');
    setDateTo('');
    setPage(1);
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] bg-slate-50/70 p-4 sm:p-6 space-y-5">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <FileText className="w-5 h-5 text-indigo-600" />
            <span>Meeting Transcriptions</span>
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Completed and pending transcripts from Google Meet (CBE) and Zoom Cloud Recordings.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {canProcessPending && (
            <button
              type="button"
              onClick={handleProcessPending}
              disabled={processingPending}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold text-indigo-700 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 rounded-xl transition disabled:opacity-50 cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${processingPending ? 'animate-spin' : ''}`} />
              <span>{processingPending ? 'Checking Pending...' : 'Check Pending Zoom'}</span>
            </button>
          )}
          <button
            type="button"
            onClick={() => fetchList()}
            disabled={loadingList}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 border border-slate-200 rounded-xl shadow-2xs transition disabled:opacity-50 cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loadingList ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Zoom Reconnect Notice */}
      {zoomNeedsReconnect && (
        <div className="flex items-start gap-3 p-3.5 rounded-2xl bg-amber-50 border border-amber-200 text-amber-900 text-xs">
          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="font-semibold">Zoom needs to be reconnected to fetch cloud transcripts.</p>
            <p className="text-amber-800/90 mt-0.5">
              Your existing Zoom connection does not include cloud recording read permissions. Reconnect Zoom in Settings to enable automatic post-meeting transcripts.
            </p>
          </div>
          <Link
            to="/settings"
            className="shrink-0 px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white font-semibold transition"
          >
            Open Settings
          </Link>
        </div>
      )}

      {/* Search & Filter Bar */}
      <div className="bg-white rounded-2xl border border-slate-200/90 p-3.5 shadow-2xs space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-2.5">
          {/* Search */}
          <div className="lg:col-span-2 relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search title or transcript text..."
              className="w-full pl-9 pr-8 py-2 text-xs rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-400"
            />
            {searchInput && (
              <button
                type="button"
                onClick={() => setSearchInput('')}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Provider filter */}
          <select
            value={providerFilter}
            onChange={(e) => {
              setProviderFilter(e.target.value);
              setPage(1);
            }}
            className="px-3 py-2 text-xs rounded-xl border border-slate-200 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
          >
            <option value="">All Providers</option>
            <option value="GOOGLE_MEET">Google Meet (CBE)</option>
            <option value="ZOOM">Zoom</option>
          </select>

          {/* Status filter */}
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            className="px-3 py-2 text-xs rounded-xl border border-slate-200 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
          >
            <option value="">All Statuses</option>
            <option value="COMPLETED">Completed</option>
            <option value="PENDING">Pending</option>
            <option value="WAITING_FOR_PROVIDER">Waiting for Zoom</option>
            <option value="PROCESSING">Processing</option>
            <option value="UNAVAILABLE">Unavailable</option>
            <option value="FAILED">Failed</option>
          </select>

          {/* Date range */}
          <div className="flex items-center gap-1.5">
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => {
                setDateFrom(e.target.value);
                setPage(1);
              }}
              title="From date"
              className="w-full px-2.5 py-2 text-xs rounded-xl border border-slate-200 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
            />
            <input
              type="date"
              value={dateTo}
              onChange={(e) => {
                setDateTo(e.target.value);
                setPage(1);
              }}
              title="To date"
              className="w-full px-2.5 py-2 text-xs rounded-xl border border-slate-200 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
            />
          </div>

          {/* Sort */}
          <select
            value={ordering}
            onChange={(e) => {
              setOrdering(e.target.value);
              setPage(1);
            }}
            className="px-3 py-2 text-xs rounded-xl border border-slate-200 bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
          >
            <option value="-scheduled_start">Newest First</option>
            <option value="scheduled_start">Oldest First</option>
          </select>
        </div>

        <div className="flex items-center justify-between text-[11px] text-slate-500">
          <span>
            Showing <strong className="text-slate-700">{items.length}</strong> of{' '}
            <strong className="text-slate-700">{totalCount}</strong> transcriptions
          </span>
          {hasFilters && (
            <button
              type="button"
              onClick={clearFilters}
              className="text-indigo-600 hover:text-indigo-800 font-semibold cursor-pointer"
            >
              Clear filters
            </button>
          )}
        </div>
      </div>

      {/* Main Split Content */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* Left: Paginated List */}
        <div className="lg:col-span-5 bg-white rounded-2xl border border-slate-200/90 shadow-2xs overflow-hidden flex flex-col">
          {loadingList ? (
            <div className="p-10 flex flex-col items-center justify-center text-slate-400 text-xs gap-2">
              <RefreshCw className="w-5 h-5 animate-spin text-indigo-500" />
              <span>Loading transcriptions...</span>
            </div>
          ) : listError ? (
            <div className="p-8 text-center space-y-2">
              <p className="text-xs font-semibold text-rose-600">{listError}</p>
              <button
                type="button"
                onClick={() => fetchList()}
                className="px-3 py-1.5 text-xs font-semibold bg-slate-900 text-white rounded-lg"
              >
                Retry
              </button>
            </div>
          ) : items.length === 0 ? (
            <div className="p-10 text-center space-y-2">
              <FileText className="w-8 h-8 text-slate-300 mx-auto" />
              <p className="text-sm font-semibold text-slate-700">No transcriptions found</p>
              <p className="text-xs text-slate-500 max-w-xs mx-auto">
                {hasFilters
                  ? 'Try adjusting your search or filter criteria.'
                  : 'Completed Google Meet (CBE) and Zoom Cloud Recording transcripts will appear here automatically.'}
              </p>
            </div>
          ) : (
            <div className="divide-y divide-slate-100 max-h-[68vh] overflow-y-auto">
              {items.map((item) => {
                const prov = PROVIDER_META[item.provider] || {
                  label: item.provider,
                  badgeClass: 'bg-slate-100 text-slate-700 border-slate-200',
                };
                const st = STATUS_META[item.status] || {
                  label: item.status,
                  badgeClass: 'bg-slate-100 text-slate-700 border-slate-200',
                };
                const isSelected = item.id === selectedId;

                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setSelectedId(item.id)}
                    className={`w-full text-left p-4 transition cursor-pointer ${
                      isSelected ? 'bg-indigo-50/60 border-l-4 border-l-indigo-600' : 'hover:bg-slate-50/80'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <h3 className="text-xs font-bold text-slate-900 line-clamp-1">
                        {item.title || 'Untitled Meeting'}
                      </h3>
                      <span
                        className={`shrink-0 px-2 py-0.5 rounded-full text-[10px] font-semibold border ${st.badgeClass}`}
                      >
                        {st.label}
                      </span>
                    </div>

                    <div className="flex flex-wrap items-center gap-2 mt-1.5 text-[11px] text-slate-500">
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold border ${prov.badgeClass}`}
                      >
                        <Video className="w-2.5 h-2.5" />
                        {prov.label}
                      </span>
                      <span className="text-[10px] text-slate-400">
                        {SOURCE_META[item.source] || item.source}
                      </span>
                      {item.scheduled_start && (
                        <span className="inline-flex items-center gap-1">
                          <Calendar className="w-3 h-3 text-slate-400" />
                          {formatDateTimeForUser(item.scheduled_start, user?.timezone)}
                        </span>
                      )}
                      {item.duration_seconds ? (
                        <span className="inline-flex items-center gap-1">
                          <Clock className="w-3 h-3 text-slate-400" />
                          {formatDuration(item.duration_seconds)}
                        </span>
                      ) : null}
                    </div>

                    {item.transcript_preview ? (
                      <p className="mt-2 text-[11px] text-slate-600 line-clamp-2 leading-relaxed">
                        {item.transcript_preview}
                      </p>
                    ) : item.status_message ? (
                      <p className="mt-2 text-[11px] text-slate-400 italic line-clamp-1">
                        {item.status_message}
                      </p>
                    ) : null}
                  </button>
                );
              })}
            </div>
          )}

          {/* Pagination Footer */}
          {totalCount > PAGE_SIZE && (
            <div className="px-4 py-3 border-t border-slate-100 bg-slate-50/70 flex items-center justify-between text-xs">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-slate-200 bg-white text-slate-700 font-semibold disabled:opacity-40 cursor-pointer"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
                Prev
              </button>
              <span className="text-slate-500 font-medium">
                Page {page} of {totalPages}
              </span>
              <button
                type="button"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-slate-200 bg-white text-slate-700 font-semibold disabled:opacity-40 cursor-pointer"
              >
                Next
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
        </div>

        {/* Right: Transcription Detail Viewer */}
        <div className="lg:col-span-7 bg-white rounded-2xl border border-slate-200/90 shadow-2xs overflow-hidden min-h-[420px] flex flex-col">
          {!selectedId ? (
            <div className="flex-1 flex flex-col items-center justify-center p-12 text-center text-slate-400">
              <FileText className="w-10 h-10 text-slate-200 mb-2" />
              <p className="text-sm font-semibold text-slate-600">Select a meeting transcription</p>
              <p className="text-xs text-slate-400 mt-1">
                Choose any meeting on the left to inspect its full transcript, speakers, and metadata.
              </p>
            </div>
          ) : loadingDetail ? (
            <div className="flex-1 flex items-center justify-center p-12 text-xs text-slate-400 gap-2">
              <RefreshCw className="w-4 h-4 animate-spin text-indigo-500" />
              <span>Loading transcript...</span>
            </div>
          ) : detail ? (
            <>
              {/* Detail Header */}
              <div className="p-5 border-b border-slate-100 space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="text-base font-bold text-slate-900 break-words">
                      {detail.title || 'Untitled Meeting'}
                    </h2>
                    <div className="flex flex-wrap items-center gap-2 mt-1.5 text-xs text-slate-500">
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-semibold border ${
                          (PROVIDER_META[detail.provider] || {}).badgeClass || 'bg-slate-100 text-slate-700'
                        }`}
                      >
                        <Video className="w-3 h-3" />
                        {(PROVIDER_META[detail.provider] || {}).label || detail.provider}
                      </span>
                      <span
                        className={`px-2 py-0.5 rounded-full text-[11px] font-semibold border ${
                          (STATUS_META[detail.status] || {}).badgeClass || 'bg-slate-100 text-slate-700'
                        }`}
                      >
                        {(STATUS_META[detail.status] || {}).label || detail.status}
                      </span>
                      {detail.scheduled_start && (
                        <span className="inline-flex items-center gap-1">
                          <Calendar className="w-3.5 h-3.5 text-slate-400" />
                          {formatDateTimeForUser(detail.scheduled_start, user?.timezone)}
                        </span>
                      )}
                      {detail.duration_seconds ? (
                        <span className="inline-flex items-center gap-1">
                          <Clock className="w-3.5 h-3.5 text-slate-400" />
                          {formatDuration(detail.duration_seconds)}
                        </span>
                      ) : null}
                    </div>
                  </div>

                  {detail.provider === 'ZOOM' && (
                    <button
                      type="button"
                      onClick={handleRefreshOne}
                      disabled={refreshingDetail}
                      className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-sky-700 bg-sky-50 hover:bg-sky-100 border border-sky-200 rounded-xl transition disabled:opacity-50 cursor-pointer"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 ${refreshingDetail ? 'animate-spin' : ''}`} />
                      <span>{refreshingDetail ? 'Syncing...' : 'Refresh from Zoom'}</span>
                    </button>
                  )}
                </div>

                {/* Meeting URL & Participants */}
                <div className="flex flex-wrap items-center gap-3 text-xs">
                  {detail.meeting_url && (
                    <div className="inline-flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1">
                      <a
                        href={detail.meeting_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-indigo-600 hover:text-indigo-800 font-medium inline-flex items-center gap-1 max-w-[260px] truncate"
                      >
                        <ExternalLink className="w-3 h-3 shrink-0" />
                        <span className="truncate">{detail.meeting_url}</span>
                      </a>
                      <button
                        type="button"
                        onClick={() => handleCopyUrl(detail.meeting_url)}
                        className="text-slate-400 hover:text-slate-700 ml-1"
                        title="Copy meeting link"
                      >
                        {copiedUrl ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
                      </button>
                    </div>
                  )}

                  {Array.isArray(detail.participants) && detail.participants.length > 0 && (
                    <div className="inline-flex items-center gap-1.5 flex-wrap">
                      <Users className="w-3.5 h-3.5 text-slate-400" />
                      {detail.participants.map((p, idx) => (
                        <span
                          key={idx}
                          className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[11px] font-medium"
                        >
                          {p}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Status message banner when not completed */}
                {detail.status !== 'COMPLETED' && detail.status_message && (
                  <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-600">
                    {detail.status_message}
                  </div>
                )}
              </div>

              {/* Transcript Actions Toolbar */}
              {(detail.transcript_text || displaySegments.length > 0) && (
                <div className="px-5 py-3 bg-slate-50/70 border-b border-slate-100 flex flex-wrap items-center justify-between gap-2">
                  <div className="relative flex-1 min-w-[180px] max-w-xs">
                    <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
                    <input
                      type="text"
                      value={innerSearch}
                      onChange={(e) => setInnerSearch(e.target.value)}
                      placeholder="Search within transcript..."
                      className="w-full pl-8 pr-7 py-1.5 text-xs rounded-lg border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
                    />
                    {innerSearch && (
                      <button
                        type="button"
                        onClick={() => setInnerSearch('')}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    {innerSearch && displaySegments.length > 0 && (
                      <span className="text-[11px] text-slate-500">
                        {filteredSegments.length} / {displaySegments.length} lines
                      </span>
                    )}
                    <button
                      type="button"
                      onClick={handleCopyTranscript}
                      className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-100 border border-slate-200 rounded-lg transition cursor-pointer"
                    >
                      {copiedTranscript ? (
                        <Check className="w-3.5 h-3.5 text-emerald-600" />
                      ) : (
                        <Copy className="w-3.5 h-3.5" />
                      )}
                      <span>{copiedTranscript ? 'Copied' : 'Copy'}</span>
                    </button>
                    <button
                      type="button"
                      onClick={handleDownloadTxt}
                      className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-semibold text-white bg-slate-900 hover:bg-black rounded-lg transition cursor-pointer"
                    >
                      <Download className="w-3.5 h-3.5" />
                      <span>Download TXT</span>
                    </button>
                  </div>
                </div>
              )}

              {/* Transcript Body */}
              <div className="p-5 flex-1 overflow-y-auto max-h-[58vh]">
                {displaySegments.length > 0 ? (
                  filteredSegments.length > 0 ? (
                    <div className="space-y-2.5">
                      {filteredSegments.map((seg, idx) => (
                        <div
                          key={idx}
                          className="flex items-start gap-3 text-xs leading-relaxed p-2 rounded-xl hover:bg-slate-50 transition"
                        >
                          {seg.start ? (
                            <span className="shrink-0 font-mono text-[11px] text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded">
                              [{seg.start}]
                            </span>
                          ) : null}
                          <div className="min-w-0 flex-1 text-slate-800">
                            {seg.speaker ? (
                              <span className="font-bold text-indigo-700 mr-1.5">
                                {highlightText(seg.speaker, innerSearch)}:
                              </span>
                            ) : null}
                            <span>{highlightText(seg.text, innerSearch)}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-slate-500 text-center py-8">
                      No transcript lines matched &ldquo;{innerSearch}&rdquo;.
                    </p>
                  )
                ) : detail.transcript_text ? (
                  <pre className="whitespace-pre-wrap font-sans text-xs text-slate-800 leading-relaxed">
                    {highlightText(detail.transcript_text, innerSearch)}
                  </pre>
                ) : (
                  <div className="py-12 text-center space-y-2">
                    <Clock className="w-7 h-7 text-slate-300 mx-auto" />
                    <p className="text-xs font-semibold text-slate-600">
                      Transcript not available yet
                    </p>
                    <p className="text-[11px] text-slate-400 max-w-sm mx-auto">
                      {detail.status_message ||
                        'Once the meeting finishes and transcription processing completes, the full transcript will appear here.'}
                    </p>
                  </div>
                )}
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
