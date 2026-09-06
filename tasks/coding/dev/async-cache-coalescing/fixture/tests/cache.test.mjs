import assert from "node:assert/strict";
import test from "node:test";

import { createAsyncCache } from "../src/index.mjs";


function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}


test("caches a fulfilled value until the exact TTL boundary", async () => {
  let currentTime = 100;
  let calls = 0;
  const cache = createAsyncCache(
    async (key) => `${key}:${++calls}`,
    { ttlMs: 10, now: () => currentTime },
  );

  assert.equal(await cache.get("alpha"), "alpha:1");
  currentTime = 109;
  assert.equal(await cache.get("alpha"), "alpha:1");
  currentTime = 110;
  assert.equal(await cache.get("alpha"), "alpha:2");
  assert.equal(calls, 2);
});


test("coalesces concurrent misses for the same key", async () => {
  const pending = deferred();
  let calls = 0;
  const cache = createAsyncCache(
    async () => {
      calls += 1;
      return pending.promise;
    },
    { ttlMs: 50, now: () => 0 },
  );

  const first = cache.get("alpha");
  const second = cache.get("alpha");
  await Promise.resolve();

  assert.equal(calls, 1);
  pending.resolve("shared");
  assert.deepEqual(await Promise.all([first, second]), ["shared", "shared"]);
});


test("does not cache a rejected loader attempt", async () => {
  let calls = 0;
  const expected = new Error("temporary failure");
  const cache = createAsyncCache(
    async () => {
      calls += 1;
      if (calls === 1) {
        throw expected;
      }
      return "recovered";
    },
    { ttlMs: 50, now: () => 0 },
  );

  await assert.rejects(cache.get("alpha"), expected);
  assert.equal(await cache.get("alpha"), "recovered");
  assert.equal(calls, 2);
});


test("invalidate removes a settled value for only that key", async () => {
  const calls = new Map();
  const cache = createAsyncCache(
    async (key) => {
      const count = (calls.get(key) ?? 0) + 1;
      calls.set(key, count);
      return `${key}:${count}`;
    },
    { ttlMs: 50, now: () => 0 },
  );

  assert.equal(await cache.get("alpha"), "alpha:1");
  assert.equal(await cache.get("beta"), "beta:1");
  cache.invalidate("alpha");
  assert.equal(await cache.get("alpha"), "alpha:2");
  assert.equal(await cache.get("beta"), "beta:1");
});
