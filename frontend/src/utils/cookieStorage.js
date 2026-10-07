export const cookieStorage = {
  getItem: (key) => {
    const match = document.cookie.match(new RegExp('(^| )' + key + '=([^;]+)'));
    return match ? decodeURIComponent(match[2]) : null;
  },
  setItem: (key, value) => {
    document.cookie = `${key}=${encodeURIComponent(value)}; path=/; SameSite=Lax`;
  },
  removeItem: (key) => {
    document.cookie = `${key}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
  },
  clear: () => {
    document.cookie = `accessToken=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
    document.cookie = `refreshToken=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
  }
};
