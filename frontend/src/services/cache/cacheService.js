/**
 * cacheService.js
 *
 * Core IndexedDB cache service for MarketIntel DB.
 *
 * Design principles:
 *  - User-scoped: cache keys always include the authenticated userId.
 *  - Mutation-driven invalidation: no TTL for normal application data.
 *  - Never caches auth tokens, failed responses, or mutation requests.
 *  - An optional ttlMs parameter exists for future extensibility but is
 *    not applied to normal application resources.
 *  - All writes are fire-and-forget from the caller's perspective
 *    (the caller awaits the write but failures are non-fatal).
 */

const DB_NAME = 'marketintel-cache';
const DB_VERSION = 1;
const STORE_API = 'api-cache';

/** @type {IDBDatabase|null} */
let _db = null;

/**
 * Open (or reuse) the IndexedDB connection.
 * @returns {Promise<IDBDatabase>}
 */
function openDB() {
  if (_db) return Promise.resolve(_db);

  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = (event) => {
      const db = event.target.result;

      // General API cache store
      if (!db.objectStoreNames.contains(STORE_API)) {
        const store = db.createObjectStore(STORE_API, { keyPath: 'key' });
        store.createIndex('by_key', 'key', { unique: true });
        store.createIndex('by_prefix', 'prefix', { unique: false });
      }
    };

    request.onsuccess = (event) => {
      _db = event.target.result;
      resolve(_db);
    };

    request.onerror = (event) => {
      reject(event.target.error);
    };
  });
}

/**
 * Derive the prefix from a full cache key (everything up to and including
 * the resource segment, e.g. "u:5:market-events:list").
 * Used for prefix-based invalidation indexing.
 *
 * @param {string} key
 * @returns {string}
 */
function extractPrefix(key) {
  // Key format: u:{userId}:{resource}:{type}[:params]
  const parts = key.split(':');
  // Keep u, userId, resource, type (4 segments)
  return parts.slice(0, 4).join(':');
}

/**
 * Read a cached entry.
 *
 * @param {string} key - deterministic cache key
 * @returns {Promise<any|null>} the cached data, or null on miss/error
 */
export async function getCachedData(key) {
  try {
    const db = await openDB();
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_API, 'readonly');
      const store = tx.objectStore(STORE_API);
      const req = store.get(key);
      req.onsuccess = () => {
        const record = req.result;
        if (!record) return resolve(null);

        // Optional TTL check (for future use)
        if (record.expiresAt && record.expiresAt < Date.now()) {
          resolve(null);
          return;
        }

        resolve(record.data);
      };
      req.onerror = () => resolve(null);
    });
  } catch {
    return null;
  }
}

/**
 * Read a cached entry along with its metadata (e.g. cachedAt).
 *
 * @param {string} key - deterministic cache key
 * @returns {Promise<{data: any, cachedAt: number, expiresAt: number|null}|null>} 
 */
export async function getCachedRecord(key) {
  try {
    const db = await openDB();
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_API, 'readonly');
      const store = tx.objectStore(STORE_API);
      const req = store.get(key);
      req.onsuccess = () => {
        const record = req.result;
        if (!record) return resolve(null);
        
        if (record.expiresAt && record.expiresAt < Date.now()) {
          resolve(null);
          return;
        }
        resolve(record);
      };
      req.onerror = () => resolve(null);
    });
  } catch {
    return null;
  }
}

/**
 * Write a cache entry.
 *
 * @param {string}  key    - deterministic cache key
 * @param {any}     data   - the data to cache (must be structurally cloneable)
 * @param {number}  [ttlMs] - optional TTL in milliseconds (not used for normal resources)
 * @returns {Promise<void>}
 */
export async function setCachedData(key, data, ttlMs) {
  try {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_API, 'readwrite');
      const store = tx.objectStore(STORE_API);
      const record = {
        key,
        prefix: extractPrefix(key),
        data,
        cachedAt: Date.now(),
        expiresAt: ttlMs ? Date.now() + ttlMs : null,
      };
      const req = store.put(record);
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    });
  } catch {
    // Non-fatal: cache write failure should not break the UI
  }
}

/**
 * Remove a single cache entry by exact key.
 *
 * @param {string} key
 * @returns {Promise<void>}
 */
export async function removeCachedData(key) {
  try {
    const db = await openDB();
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_API, 'readwrite');
      const store = tx.objectStore(STORE_API);
      store.delete(key);
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve(); // non-fatal
    });
  } catch {
    // Non-fatal
  }
}

/**
 * Invalidate all cache entries whose key starts with the given prefix.
 *
 * Used after mutations to remove all list cache variants for a resource,
 * since the new list state is unknown (different filters/pages may be stale).
 *
 * @param {string} prefix - e.g. "u:5:market-events:list"
 * @returns {Promise<void>}
 */
export async function invalidateCache(prefix) {
  try {
    const db = await openDB();
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_API, 'readwrite');
      const store = tx.objectStore(STORE_API);

      // Use cursor to find and delete all matching keys
      const req = store.openCursor();
      req.onsuccess = (event) => {
        const cursor = event.target.result;
        if (!cursor) return; // done

        if (cursor.key.startsWith(prefix)) {
          cursor.delete();
        }
        cursor.continue();
      };

      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve(); // non-fatal
    });
  } catch {
    // Non-fatal
  }
}

/**
 * Clear ALL cached data belonging to a specific user.
 *
 * Called on logout to ensure no private data remains accessible
 * after a different user logs in.
 *
 * @param {number|string} userId
 * @returns {Promise<void>}
 */
export async function clearUserCache(userId) {
  if (!userId) return;
  const prefix = `u:${userId}:`;
  await invalidateCache(prefix);
}
