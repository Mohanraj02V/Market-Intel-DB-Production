/**
 * cacheKeys.js
 *
 * Deterministic, consistent cache key builders.
 *
 * Rules:
 *  - Every key is prefixed with the authenticated userId so no two users
 *    ever share the same key space.
 *  - All query parameters (search, page, filters, etc.) are sorted and
 *    serialized so the same logical request always yields the same key.
 *  - Never use a mutable value (Date.now, Math.random) as part of a key.
 */

/**
 * Serialize an arbitrary params object into a stable, sorted query string.
 * Empty / null / undefined values are excluded.
 *
 * @param {Record<string, any>} params
 * @returns {string}
 */
export function serializeParams(params = {}) {
  if (!params || typeof params !== 'object') return '';
  const entries = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return entries.join('&');
}

/**
 * Build a cache key for a paginated / filtered list resource.
 *
 * @param {number|string} userId  - authenticated user ID
 * @param {string}        resource - e.g. 'market-events', 'prospects'
 * @param {object}        params   - all query params (search, page, filters …)
 * @returns {string}
 */
export function listCacheKey(userId, resource, params = {}) {
  const serialized = serializeParams(params);
  return serialized
    ? `u:${userId}:${resource}:list:${serialized}`
    : `u:${userId}:${resource}:list`;
}

/**
 * Build a cache key for a single resource detail.
 *
 * @param {number|string} userId
 * @param {string}        resource
 * @param {string|number} id
 * @returns {string}
 */
export function detailCacheKey(userId, resource, id) {
  return `u:${userId}:${resource}:detail:${id}`;
}

/**
 * Build the prefix used to invalidate all list entries for a resource.
 * Used with invalidateCache(prefix).
 *
 * @param {number|string} userId
 * @param {string}        resource
 * @returns {string}
 */
export function listCachePrefix(userId, resource) {
  return `u:${userId}:${resource}:list`;
}

/**
 * Build the user-scope prefix (used for full user cache clear on logout).
 *
 * @param {number|string} userId
 * @returns {string}
 */
export function userScopePrefix(userId) {
  return `u:${userId}:`;
}
