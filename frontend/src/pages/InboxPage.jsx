import React, { useState, useEffect, useCallback } from 'react';
import { Mail, Send, AlertTriangle, RefreshCw, ChevronLeft, Loader2, Paperclip, Building2, Reply, Edit3, X } from 'lucide-react';
import { toast } from 'react-toastify';
import { useDispatch, useSelector } from 'react-redux';
import api from '../services/api';
import {
  setEmails,
  setInboxLoading,
  setSyncError,
  setActiveFolder,
  mergeEmails,
} from '../features/inbox/inboxSlice';
import {
  getMailboxMessages,
  setMailboxMessages,
  getMailboxState,
  setMailboxState,
  getEmailBody,
  setEmailBody,
  resetMailboxCache,
} from '../services/cache/inboxCacheService';

const FOLDERS = [
  { id: 'INBOX', label: 'Inbox', icon: Mail },
  { id: '"[Gmail]/Sent Mail"', label: 'Sent', icon: Send },
  { id: '"[Gmail]/Spam"', label: 'Spam', icon: AlertTriangle },
];

const InboxPage = () => {
  const dispatch = useDispatch();
  const { user } = useSelector((state) => state.auth);
  const { emails, loading, activeFolder } = useSelector((state) => state.inbox);

  const [selectedEmail, setSelectedEmail] = useState(null);
  const [bodyLoading, setBodyLoading] = useState(false);
  const [emailBody, setEmailBodyState] = useState({ html_body: '', text_body: '', attachments: [] });

  const [showCompose, setShowCompose] = useState(false);
  const [composeData, setComposeData] = useState({ to: '', subject: '', body: '' });
  const [sendingEmail, setSendingEmail] = useState(false);
  
  const [searchQuery, setSearchQuery] = useState('');

  const handleCompose = () => {
    setComposeData({ to: '', subject: '', body: '' });
    setShowCompose(true);
  };

  const handleReply = () => {
    if (!selectedEmail) return;
    const toAddress = selectedEmail.from.match(/<([^>]+)>/)?.[1] || selectedEmail.from;
    setComposeData({
      to: toAddress,
      subject: selectedEmail.subject?.startsWith('Re:') ? selectedEmail.subject : `Re: ${selectedEmail.subject || ''}`,
      body: `\n\n\n--- Original Message ---\nFrom: ${selectedEmail.from}\nDate: ${selectedEmail.date}\nSubject: ${selectedEmail.subject}\n`
    });
    setShowCompose(true);
  };

  const sendEmail = () => {
    if (!composeData.to) return toast.error('To address is required');
    
    // Close modal immediately for better UX
    setShowCompose(false);
    
    // Use toast promise or loading state
    const toastId = toast.loading('Sending email in the background...');
    
    api.post('/auth/mail-account/send-email/', composeData)
      .then(() => {
        toast.dismiss(toastId);
        toast.success('Email sent successfully');
      })
      .catch((e) => {
        toast.dismiss(toastId);
        toast.error('Failed to send email');
      });
  };

  // Derived: user's mail account ID comes from user.profile via /auth/me/
  // The backend resolves mail account from user.profile.mail_account_id
  // We use user.id as the user-scope key for the cache
  const userId = user?.id;
  // mailAccountId is used as part of the cache key; we don't have it directly
  // on the Redux user object, but we use a stable placeholder since all
  // IMAP calls are scoped by the authenticated session on the backend.
  // If the user has multiple accounts in future, extend this.
  const mailAccountId = user?.mail_account_id || 'default';

  // ─── Folder fetch ─────────────────────────────────────────────────────────

  /**
   * Load messages for a folder.
   * Normal path: IndexedDB cache → render immediately, no backend call.
   * Cache-miss path: backend fetch → store in IndexedDB → render.
   */
  const loadFolder = useCallback(async (folder, bypassCache = false) => {
    dispatch(setInboxLoading(true));
    dispatch(setSyncError(null));

    // Step 1: Try IndexedDB cache
    if (!bypassCache && userId) {
      const cached = await getMailboxMessages(userId, mailAccountId, folder);
      if (cached && cached.length > 0) {
        dispatch(setEmails(cached));
        dispatch(setInboxLoading(false));
        return; // Cache hit — no backend call
      }
    }

    // Step 2: Cache miss — fetch from backend
    try {
      const res = await api.get(
        `/auth/mail-account/fetch-emails/?folder=${encodeURIComponent(folder)}&limit=20`
      );
      const { messages = [], uidvalidity = null } = res.data;

      if (userId) {
        // Compute highest UID from fetched messages
        const highestUid = messages.reduce((max, m) => {
          const uid = parseInt(m.uid, 10);
          return uid > max ? uid : max;
        }, 0);

        await setMailboxMessages(userId, mailAccountId, folder, messages, uidvalidity);
        if (uidvalidity !== null) {
          await setMailboxState(userId, mailAccountId, folder, uidvalidity, highestUid);
        }
      }

      dispatch(setEmails(messages));
    } catch (err) {
      const message = err.response?.data?.error || 'Failed to fetch emails.';
      toast.error(message);
      dispatch(setSyncError(message));
      dispatch(setEmails([]));
    } finally {
      dispatch(setInboxLoading(false));
    }
  }, [userId, mailAccountId, dispatch]);

  // ─── Load on folder change ────────────────────────────────────────────────

  useEffect(() => {
    setSelectedEmail(null);
    setEmailBodyState({ html_body: '', text_body: '', attachments: [] });
    loadFolder(activeFolder);
  }, [activeFolder]); // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Folder switch ────────────────────────────────────────────────────────

  const handleFolderSwitch = (folderId) => {
    if (folderId === activeFolder) return;
    dispatch(setActiveFolder(folderId));
    setSelectedEmail(null);
    setEmailBodyState({ html_body: '', text_body: '', attachments: [] });
  };

  // ─── Explicit Sync (bypass cache) ────────────────────────────────────────

  const handleRefresh = () => {
    setSelectedEmail(null);
    setEmailBodyState({ html_body: '', text_body: '', attachments: [] });
    loadFolder(activeFolder, true /* bypassCache */);
  };

  // ─── Open email (body cache-first) ────────────────────────────────────────

  const openEmail = async (email) => {
    setSelectedEmail(email);
    setEmailBodyState({ html_body: '', text_body: '', attachments: [] });

    const uid = email.uid || email.id;

    // Step 1: Check body cache using stable UID
    if (userId && uid) {
      const cached = await getEmailBody(userId, mailAccountId, activeFolder, uid);
      if (cached) {
        setEmailBodyState(cached);
        return; // Cache hit — no backend call
      }
    }

    // Step 2: Cache miss — fetch body from backend
    setBodyLoading(true);
    try {
      const res = await api.get(
        `/auth/mail-account/fetch-email-body/?folder=${encodeURIComponent(activeFolder)}&uid=${encodeURIComponent(uid)}`
      );
      const body = res.data;

      if (userId && uid) {
        await setEmailBody(userId, mailAccountId, activeFolder, uid, body);
      }

      setEmailBodyState(body);
    } catch (err) {
      toast.error('Failed to load email body.');
    } finally {
      setBodyLoading(false);
    }
  };

  // ─── UIDVALIDITY change handler ───────────────────────────────────────────

  const handleUidvalidityChange = useCallback(async (folder) => {
    if (!userId) return;
    await resetMailboxCache(userId, mailAccountId, folder);
    // Rebuild from backend
    await loadFolder(folder, true);
  }, [userId, mailAccountId, loadFolder]);

  // ─── Body renderer ────────────────────────────────────────────────────────

  const renderBody = () => {
    if (bodyLoading) {
      return (
        <div className="flex items-center justify-center h-full text-slate-400 gap-2">
          <Loader2 className="w-5 h-5 animate-spin" /> Loading email...
        </div>
      );
    }
    if (emailBody.html_body) {
      return (
        <iframe
          srcDoc={emailBody.html_body}
          sandbox="allow-same-origin"
          style={{ width: '100%', height: '100%', border: 'none', background: 'white' }}
          title="Email Content"
        />
      );
    }
    if (emailBody.text_body) {
      return (
        <div className="p-6 overflow-y-auto h-full flex-1 whitespace-pre-wrap text-sm text-slate-800 leading-relaxed">
          {emailBody.text_body}
        </div>
      );
    }
    return (
      <div className="flex items-center justify-center h-full text-slate-400 text-sm italic">
        (Empty Body)
      </div>
    );
  };

  const displayEmails = emails.filter(e => {
    if (searchQuery) {
      if (!e.prospect_company_name) return false;
      return e.prospect_company_name.toLowerCase().includes(searchQuery.toLowerCase());
    }
    return true;
  });

  return (
    <div className="space-y-6 flex flex-col h-[calc(100vh-64px)] overflow-hidden">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 shrink-0">
        <div>
          <h1 className="text-2xl font-black text-slate-900 tracking-tight flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-sky-600 text-white flex items-center justify-center shadow-md">
              <Mail className="w-5 h-5" />
            </div>
            Mail Inbox
          </h1>
          <p className="text-slate-500 text-sm mt-1 font-medium">View emails from your configured mail account.</p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={handleCompose} className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-sm rounded-xl transition flex items-center gap-2 shadow-sm">
            <Edit3 className="w-4 h-4" /> Compose
          </button>
          <button onClick={handleRefresh} disabled={loading} className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-sm rounded-xl transition flex items-center gap-2 border border-slate-200 disabled:opacity-50">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Sync
          </button>
        </div>
      </div>

      <div className="flex-1 min-h-0 bg-white border border-slate-200 rounded-2xl shadow-sm flex overflow-hidden">
        {/* Sidebar */}
        <div className="w-56 border-r border-slate-200 bg-slate-50 flex flex-col shrink-0">
          <div className="p-4 border-b border-slate-200">
            <h2 className="text-xs font-black text-slate-400 uppercase tracking-wider">Folders</h2>
          </div>
          <nav className="flex-1 overflow-y-auto p-2 space-y-1">
            {FOLDERS.map((f) => {
              const Icon = f.icon;
              return (
                <button
                  key={f.id}
                  onClick={() => handleFolderSwitch(f.id)}
                  className={`w-full flex items-center gap-3 px-3 py-2 text-sm font-bold rounded-xl transition ${activeFolder === f.id ? 'bg-sky-100 text-sky-700' : 'text-slate-600 hover:bg-slate-100'}`}
                >
                  <Icon className="w-4 h-4" />
                  {f.label}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Content */}
        <div className="flex-1 flex min-w-0 bg-white overflow-hidden">
          {/* Email list */}
          <div className={`flex flex-col border-r border-slate-100 overflow-y-auto transition-all ${selectedEmail ? 'w-72 shrink-0' : 'flex-1'}`}>
            <div className="p-3 border-b border-slate-100 sticky top-0 bg-white z-10 shrink-0">
              <input 
                type="text" 
                placeholder="Search by company..." 
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 text-slate-800 placeholder-slate-400 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 font-medium transition-all"
              />
            </div>
            {loading ? (
              <div className="flex items-center justify-center h-full text-slate-400 gap-2 font-medium">
                <Loader2 className="w-5 h-5 animate-spin" /> Loading emails...
              </div>
            ) : displayEmails.length === 0 ? (
              <div className="flex items-center justify-center h-full text-slate-400 font-medium">No emails found in this folder.</div>
            ) : (
              <ul className="divide-y divide-slate-100">
                {displayEmails.map((email) => (
                  <li
                    key={email.uid || email.id}
                    onClick={() => openEmail(email)}
                    className={`p-4 cursor-pointer transition ${selectedEmail?.uid === email.uid ? 'bg-sky-50 border-l-2 border-sky-500' : 'hover:bg-slate-50'}`}
                  >
                    <div className="flex items-baseline justify-between gap-2 mb-0.5">
                      <span className={`text-xs truncate flex-1 ${email.is_unread ? 'font-bold text-slate-900' : 'font-medium text-slate-600'}`}>
                        {email.prospect_company_name ? (
                          <span className="inline-flex items-center gap-1 text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200 text-[10px] uppercase font-bold tracking-wider mr-1.5">
                            <Building2 className="w-3 h-3" /> {email.prospect_company_name}
                          </span>
                        ) : null}
                        {activeFolder.includes('Sent') 
                          ? `To: ${email.to?.replace(/<.*>/, '').trim() || email.to}` 
                          : email.from?.replace(/<.*>/, '').trim() || email.from}
                      </span>
                      <span className="text-[10px] text-slate-400 shrink-0 font-medium">{email.date?.split(' ').slice(1, 4).join(' ')}</span>
                    </div>
                    <h4 className={`text-xs truncate ${email.is_unread ? 'font-bold text-slate-800' : 'font-semibold text-slate-600'}`}>
                      {email.subject || '(No Subject)'}
                    </h4>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Email body panel */}
          {selectedEmail && (
            <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
              <div className="p-4 border-b border-slate-100 flex items-start gap-3 shrink-0 bg-white">
                <button
                  onClick={() => { setSelectedEmail(null); setEmailBodyState({ html_body: '', text_body: '' }); }}
                  className="p-1.5 hover:bg-slate-100 rounded-full transition text-slate-500 mt-0.5 shrink-0"
                >
                  <ChevronLeft className="w-5 h-5" />
                </button>
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-4">
                    <h2 className="text-base font-bold text-slate-900 leading-tight">{selectedEmail.subject || '(No Subject)'}</h2>
                    <button onClick={handleReply} className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded-lg transition flex items-center gap-1.5 border border-slate-200 shrink-0">
                      <Reply className="w-3.5 h-3.5" /> Reply
                    </button>
                  </div>
                  <div className="flex items-center gap-2 mt-1 text-xs text-slate-500 flex-wrap">
                    <span>From: <span className="font-semibold text-slate-700">{selectedEmail.from}</span></span>
                    <span className="text-slate-300">·</span>
                    <span>{selectedEmail.date}</span>
                  </div>
                </div>
              </div>
              <div className="flex-1 overflow-hidden flex flex-col">
                {emailBody.attachments && emailBody.attachments.length > 0 && (
                  <div className="p-4 border-b border-slate-100 bg-slate-50/50 flex flex-wrap gap-2 shrink-0">
                    <span className="text-xs font-bold text-slate-500 w-full mb-1">Attachments ({emailBody.attachments.length})</span>
                    {emailBody.attachments.map((att, idx) => (
                      <a
                        key={idx}
                        href={`data:${att.content_type || 'application/octet-stream'};base64,${att.data}`}
                        download={att.filename}
                        className="flex items-center gap-2 px-3 py-1.5 bg-white border border-slate-200 rounded-lg shadow-sm hover:border-sky-300 hover:text-sky-700 transition text-xs font-semibold text-slate-700"
                      >
                        <Paperclip className="w-3.5 h-3.5" />
                        <span className="truncate max-w-[200px]">{att.filename}</span>
                        <span className="text-[10px] text-slate-400">({Math.round((att.size || 0) / 1024)} KB)</span>
                      </a>
                    ))}
                  </div>
                )}
                <div className="flex-1 overflow-hidden">
                  {renderBody()}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {showCompose && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-2xl overflow-hidden border border-slate-200 flex flex-col">
            <div className="bg-slate-900 p-4 text-white flex items-center justify-between">
              <h3 className="font-bold text-lg">Compose Email</h3>
              <button onClick={() => setShowCompose(false)} className="text-slate-400 hover:text-white transition">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4 flex flex-col gap-4">
              <div className="flex items-center gap-3">
                <label className="text-sm font-bold text-slate-600 w-16">To:</label>
                <input 
                  type="email" 
                  value={composeData.to} 
                  onChange={(e) => setComposeData({...composeData, to: e.target.value})}
                  className="flex-1 p-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500" 
                  placeholder="recipient@example.com"
                />
              </div>
              <div className="flex items-center gap-3">
                <label className="text-sm font-bold text-slate-600 w-16">Subject:</label>
                <input 
                  type="text" 
                  value={composeData.subject} 
                  onChange={(e) => setComposeData({...composeData, subject: e.target.value})}
                  className="flex-1 p-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500" 
                  placeholder="Subject"
                />
              </div>
              <div className="flex items-start gap-3 flex-1">
                <textarea 
                  value={composeData.body}
                  onChange={(e) => setComposeData({...composeData, body: e.target.value})}
                  className="flex-1 p-3 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 min-h-[250px] resize-none"
                  placeholder="Write your email here..."
                ></textarea>
              </div>
            </div>
            <div className="bg-slate-50 p-4 border-t border-slate-200 flex justify-end gap-3">
              <button onClick={() => setShowCompose(false)} className="px-4 py-2 bg-white border border-slate-300 text-slate-700 font-bold text-sm rounded-lg hover:bg-slate-50 transition">Cancel</button>
              <button onClick={sendEmail} disabled={sendingEmail} className="px-6 py-2 bg-sky-600 hover:bg-sky-700 text-white font-bold text-sm rounded-lg shadow-sm transition flex items-center gap-2 disabled:opacity-50">
                {sendingEmail ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />} Send
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default InboxPage;
