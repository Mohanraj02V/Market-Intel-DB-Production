import { createSlice } from '@reduxjs/toolkit';
import { cookieStorage } from '../../utils/cookieStorage';

// Use session cookies so tokens are shared across all tabs and cleared when the browser closes.
const _storage = cookieStorage;

const initialState = {
  user: null,
  accessToken: _storage.getItem('accessToken') || null,
  refreshToken: _storage.getItem('refreshToken') || null,
  isAuthenticated: !!_storage.getItem('accessToken'),
  loading: false,
  error: null,
};

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    loginStart: (state) => {
      state.loading = true;
      state.error = null;
    },
    loginSuccess: (state, action) => {
      state.loading = false;
      state.isAuthenticated = true;
      state.accessToken = action.payload.access;
      state.refreshToken = action.payload.refresh;
      state.user = action.payload.user;
      _storage.setItem('accessToken', action.payload.access);
      _storage.setItem('refreshToken', action.payload.refresh);
    },
    loginFailure: (state, action) => {
      state.loading = false;
      state.error = action.payload;
    },
    logout: (state) => {
      state.user = null;
      state.accessToken = null;
      state.refreshToken = null;
      state.isAuthenticated = false;
      // Clear ALL session storage to prevent stale WhatsApp polling or cached data.
      _storage.clear();
    },
    tokenRefreshed: (state, action) => {
      state.accessToken = action.payload.access;
      // If the server rotated the refresh token, update it too.
      if (action.payload.refresh) {
        state.refreshToken = action.payload.refresh;
        _storage.setItem('refreshToken', action.payload.refresh);
      }
      _storage.setItem('accessToken', action.payload.access);
    },
  },
});

export const { loginStart, loginSuccess, loginFailure, logout, tokenRefreshed } = authSlice.actions;
export default authSlice.reducer;
