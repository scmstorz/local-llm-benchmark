# Implement an async TTL cache with request coalescing

`createAsyncCache()` wraps an asynchronous loader used by a service layer. The
existing implementation caches ordinary fulfilled values, but it does not
provide production-safe behavior when requests overlap or invalidation races
with an in-flight load.

Change the implementation so that all of these requirements hold:

1. Preserve the exported `createAsyncCache(loader, options)` API and the
   returned `get(key)`, `invalidate(key)` and `clear()` methods.
2. A fulfilled value is cached per key until its TTL expires. An entry is fresh
   only while `now() < expiresAt`; a request at the exact expiry boundary must
   reload. Start the TTL when the loader fulfills, not when it starts.
3. Concurrent cache misses for the same key share one loader call and settle
   from that same attempt. Different keys remain independent.
4. Cache every fulfilled JavaScript value, including `undefined`.
5. A rejected or synchronously thrown loader attempt is shared by its current
   same-key callers but is never cached. A later `get()` must retry.
6. `invalidate(key)` removes a settled value. If that key is loading, existing
   callers may still receive that attempt's result, but it must not repopulate
   the cache. A `get(key)` after invalidation starts a new independent attempt.
7. `clear()` applies the same invalidation semantics to every key, including
   all loads that were already in flight when `clear()` was called.
8. Preserve the existing argument validation and add no dependencies.

Only files under `src/` may be changed. Do not modify tests, `package.json` or
project metadata.
