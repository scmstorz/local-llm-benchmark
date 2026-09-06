/**
 * Create a small asynchronous TTL cache.
 *
 * The implementation intentionally lacks the overlap and invalidation-race
 * behavior required by the benchmark task.
 */
export function createAsyncCache(loader, { ttlMs, now = Date.now } = {}) {
  if (typeof loader !== "function") {
    throw new TypeError("loader must be a function");
  }
  if (!Number.isFinite(ttlMs) || ttlMs <= 0) {
    throw new RangeError("ttlMs must be a positive finite number");
  }
  if (typeof now !== "function") {
    throw new TypeError("now must be a function");
  }

  const values = new Map();

  return {
    async get(key) {
      const cached = values.get(key);
      if (cached && now() < cached.expiresAt) {
        return cached.value;
      }

      const value = await loader(key);
      values.set(key, { value, expiresAt: now() + ttlMs });
      return value;
    },

    invalidate(key) {
      values.delete(key);
    },

    clear() {
      values.clear();
    },
  };
}
