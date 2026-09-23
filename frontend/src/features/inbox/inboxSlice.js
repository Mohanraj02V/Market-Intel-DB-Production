import { createSlice } from '@reduxjs/toolkit';

/**
 * inboxSlice
 *
 * Manages in-memory inbox state for the current session.
 *
 * The IndexedDB cache (inboxCacheService.js) handles persistent storage.
 * This slice reflects what the UI currently displays.
 *
 * unreadCount:   used for the Inbox nav badge.
 * mailAccountId: the user's configured mail account ID (set on login).
 */
const inboxSlice = createSlice({
  name: 'inbox',
  initialState: {
    /** Unread count for INBOX folder, shown in nav badge */
    unreadCount: 0,
    /** The user's mail account ID (populated from user profile) */
    mailAccountId: null,
    /** Emails currently displayed in the active folder */
    emails: [],
    /** Active folder name */
    activeFolder: 'INBOX',
    /** Loading state for folder fetch */
    loading: false,
    /** Non-fatal sync error message (null = no error) */
    syncError: null,
  },
  reducers: {
    setUnreadCount(state, action) {
      state.unreadCount = action.payload;
    },
    setMailAccountId(state, action) {
      state.mailAccountId = action.payload;
    },
    setEmails(state, action) {
      state.emails = action.payload;
    },
    setActiveFolder(state, action) {
      state.activeFolder = action.payload;
    },
    setInboxLoading(state, action) {
      state.loading = action.payload;
    },
    setSyncError(state, action) {
      state.syncError = action.payload;
    },
    /** Merge newly fetched messages into the current list (by UID) */
    mergeEmails(state, action) {
      const incoming = action.payload; // array of message objects
      const map = new Map(state.emails.map((m) => [m.uid, m]));
      for (const msg of incoming) {
        map.set(msg.uid, msg);
      }
      // Sort newest first by UID
      state.emails = Array.from(map.values()).sort(
        (a, b) => parseInt(b.uid, 10) - parseInt(a.uid, 10)
      );
    },
    resetInbox(state) {
      state.unreadCount = 0;
      state.mailAccountId = null;
      state.emails = [];
      state.activeFolder = 'INBOX';
      state.loading = false;
      state.syncError = null;
    },
  },
});

export const {
  setUnreadCount,
  setMailAccountId,
  setEmails,
  setActiveFolder,
  setInboxLoading,
  setSyncError,
  mergeEmails,
  resetInbox,
} = inboxSlice.actions;

export default inboxSlice.reducer;
