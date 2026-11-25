import axios from 'axios';
import { store } from '../app/store';
import { tokenRefreshed, logout } from '../features/auth/authSlice';

const getBaseUrl = () => {
  // Local development: always use Vite's proxy (/api -> http://127.0.0.1:8000)
  if (typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' || window.location.port === '5173')) {
    const envUrl = import.meta.env.VITE_API_BASE_URL;
    if (envUrl && (envUrl.includes('localhost') || envUrl.includes('127.0.0.1'))) {
      const clean = envUrl.trim().replace(/\/+$/, '');
      return clean.endsWith('/api') ? clean : `${clean}/api`;
    }
    return '/api';
  }
  const envUrl = import.meta.env.VITE_API_BASE_URL;
  // If explicitly configured in .env (e.g. https://marketintel.hikasimat.com/api)
  if (envUrl && envUrl.trim() && envUrl.trim() !== '/api') {
    const clean = envUrl.trim().replace(/\/+$/, '');
    return clean.endsWith('/api') ? clean : `${clean}/api`;
  }
  // Production frontend domain connects to backend API domain
  if (typeof window !== 'undefined' && window.location.hostname === 'marketinteldbapp.hikasimat.com') {
    return 'https://marketintel.hikasimat.com/api';
  }
  // Fallback default
  return '/api';
};

const getCookieValue = (name) => {
  if (typeof document === 'undefined' || !document.cookie) return null;
  const match = document.cookie
    .split('; ')
    .find((row) => row.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split('=').slice(1).join('=')) : null;
};

let cachedCsrfToken = null;

export const ensureCsrfToken = async () => {
  const fromCookie = getCookieValue('csrftoken');
  if (fromCookie) {
    cachedCsrfToken = fromCookie;
    return fromCookie;
  }
  if (cachedCsrfToken) return cachedCsrfToken;
  try {
    const res = await axios.get(`${getBaseUrl()}/auth/csrf/`, { withCredentials: true });
    if (res.data?.csrfToken) {
      cachedCsrfToken = res.data.csrfToken;
      return cachedCsrfToken;
    }
  } catch (_) {}
  return getCookieValue('csrftoken');
};

export const clearApiAuthHeader = () => {
  if (api?.defaults?.headers?.common) {
    delete api.defaults.headers.common['Authorization'];
  }
};

const api = axios.create({
  baseURL: getBaseUrl(),
  timeout: 30000,
  withCredentials: true,
  xsrfCookieName: 'csrftoken',
  xsrfHeaderName: 'X-CSRFToken',
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use(
  async (config) => {
    const token = store.getState().auth.accessToken;
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`;
    } else if (config.headers && config.headers['Authorization']) {
      delete config.headers['Authorization'];
    }

    const method = (config.method || 'get').toLowerCase();
    if (['post', 'put', 'patch', 'delete'].includes(method)) {
      const csrfToken = getCookieValue('csrftoken') || cachedCsrfToken || (await ensureCsrfToken());
      if (csrfToken) {
        config.headers['X-CSRFToken'] = csrfToken;
      }
    }
    // If sending FormData, delete Content-Type so Axios and browser stream multipart/form-data with boundary
    if (config.data instanceof FormData) {
      if (config.headers) {
        if (typeof config.headers.delete === 'function') {
          config.headers.delete('Content-Type');
          config.headers.delete('content-type');
        } else {
          delete config.headers['Content-Type'];
          delete config.headers['content-type'];
        }
      }
    }
    return config;
  },
  (error) => Promise.reject(error)
);

let isRefreshing = false;
let failedQueue = [];

const processQueue = (error, token = null) => {
  failedQueue.forEach(prom => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  
  failedQueue = [];
};

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    const isAuthEndpoint = originalRequest?.url?.includes('/auth/login/') || originalRequest?.url?.includes('/auth/refresh/');
    if (error.response?.status === 401 && !originalRequest._retry && !isAuthEndpoint) {
      if (isRefreshing) {
        return new Promise(function(resolve, reject) {
          failedQueue.push({ resolve, reject });
        }).then(token => {
          originalRequest.headers['Authorization'] = `Bearer ${token}`;
          return api(originalRequest);
        }).catch(err => {
          return Promise.reject(err);
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;
      
      try {
        const csrfToken = getCookieValue('csrftoken') || cachedCsrfToken || (await ensureCsrfToken());
        const refreshHeaders = csrfToken ? { 'X-CSRFToken': csrfToken } : {};
        const response = await axios.post(
          `${api.defaults.baseURL}/auth/refresh/`,
          {},
          { withCredentials: true, headers: refreshHeaders }
        );
        
        store.dispatch(tokenRefreshed({ access: response.data.access }));
          
        const newToken = response.data.access;
        processQueue(null, newToken);
          
        originalRequest.headers['Authorization'] = `Bearer ${newToken}`;
        return api(originalRequest);
      } catch (refreshError) {
        // Refresh token failed/expired — wipe invalid session and redirect to login
        processQueue(refreshError, null);
        clearApiAuthHeader();
        store.dispatch(logout());
        try {
          sessionStorage.removeItem('isAuthenticated');
          sessionStorage.removeItem('reduxState');
        } catch (_) {}
        if (typeof window !== 'undefined' && !window.location.pathname.includes('/login')) {
          window.location.href = '/login';
        }
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    } else if (error.response?.status === 401 && isAuthEndpoint && !originalRequest?.url?.includes('/auth/login/')) {
      // Direct call to /auth/refresh/ failed (token completely expired or missing)
      clearApiAuthHeader();
      store.dispatch(logout());
      try {
        sessionStorage.removeItem('isAuthenticated');
        sessionStorage.removeItem('reduxState');
      } catch (_) {}
      if (typeof window !== 'undefined' && !window.location.pathname.includes('/login')) {
        window.location.href = '/login';
      }
    }
    // Never retry explicitly aborted/cancelled requests (AbortController)
    if (axios.isCancel(error) || error.code === 'ERR_CANCELED') {
      return Promise.reject(error);
    }
    const method = (originalRequest?.method || 'get').toLowerCase();
    const isTransient =
      !error.response ||
      error.code === 'ECONNABORTED' ||
      [502, 503, 504].includes(error.response.status);
    if (
      originalRequest &&
      method === 'get' &&
      !originalRequest.skipRetry &&
      !isAuthEndpoint &&
      !originalRequest.url?.includes('/auth/logout/') &&
      isTransient &&
      (originalRequest._transientRetryCount || 0) < 2
    ) {
      originalRequest._transientRetryCount = (originalRequest._transientRetryCount || 0) + 1;
      const delayMs = originalRequest._transientRetryCount === 1 ? 500 : 1200;
      await new Promise((resolve) => setTimeout(resolve, delayMs));
      return api(originalRequest);
    }
    return Promise.reject(error);
  }
);

export default api;
