import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";
import { join, resolve } from "node:path";


if (process.argv.length !== 3) {
  throw new Error("usage: hidden_tests.mjs FIXTURE_ROOT");
}

const fixtureRoot = resolve(process.argv[2]);
const moduleUrl = pathToFileURL(join(fixtureRoot, "src", "index.mjs"));
const { createAsyncCache } = await import(moduleUrl.href);


function deferred() {
  let resolvePromise;
  let rejectPromise;
  const promise = new Promise((resolve, reject) => {
    resolvePromise = resolve;
    rejectPromise = reject;
  });
  return { promise, resolve: resolvePromise, reject: rejectPromise };
}


const cases = [];

function check(name, run) {
  cases.push({ name, run });
}


check("preserves constructor argument validation", async () => {
  assert.throws(
    () => createAsyncCache(null, { ttlMs: 10 }),
    { name: "TypeError", message: "loader must be a function" },
  );
  assert.throws(
    () => createAsyncCache(async () => "value", { ttlMs: 0 }),
    { name: "RangeError", message: "ttlMs must be a positive finite number" },
  );
  assert.throws(
    () => createAsyncCache(async () => "value", { ttlMs: 10, now: null }),
    { name: "TypeError", message: "now must be a function" },
  );
});


check("caches undefined as a fulfilled value", async () => {
  let calls = 0;
  const cache = createAsyncCache(
    async () => {
      calls += 1;
      return undefined;
    },
    { ttlMs: 10, now: () => 0 },
  );

  assert.equal(await cache.get("alpha"), undefined);
  assert.equal(await cache.get("alpha"), undefined);
  assert.equal(calls, 1);
});


check("keeps concurrent keys independent", async () => {
  const pending = new Map([
    ["alpha", deferred()],
    ["beta", deferred()],
  ]);
  const calls = [];
  const cache = createAsyncCache(
    async (key) => {
      calls.push(key);
      return pending.get(key).promise;
    },
    { ttlMs: 10, now: () => 0 },
  );

  const alpha = cache.get("alpha");
  const beta = cache.get("beta");
  await Promise.resolve();
  assert.deepEqual(calls, ["alpha", "beta"]);
  pending.get("beta").resolve("B");
  pending.get("alpha").resolve("A");
  assert.deepEqual(await Promise.all([alpha, beta]), ["A", "B"]);
});


check("starts the TTL when the loader fulfills", async () => {
  let currentTime = 0;
  let calls = 0;
  const first = deferred();
  const cache = createAsyncCache(
    async () => {
      calls += 1;
      return calls === 1 ? first.promise : "fresh";
    },
    { ttlMs: 10, now: () => currentTime },
  );

  const loading = cache.get("alpha");
  await Promise.resolve();
  currentTime = 100;
  first.resolve("initial");
  assert.equal(await loading, "initial");
  currentTime = 109;
  assert.equal(await cache.get("alpha"), "initial");
  currentTime = 110;
  assert.equal(await cache.get("alpha"), "fresh");
  assert.equal(calls, 2);
});


check("shares one rejected attempt and retries later", async () => {
  const first = deferred();
  const expected = new Error("temporary");
  let calls = 0;
  const cache = createAsyncCache(
    async () => {
      calls += 1;
      return calls === 1 ? first.promise : "recovered";
    },
    { ttlMs: 10, now: () => 0 },
  );

  const one = cache.get("alpha");
  const two = cache.get("alpha");
  await Promise.resolve();
  assert.equal(calls, 1);
  first.reject(expected);
  const settled = await Promise.allSettled([one, two]);
  assert.deepEqual(settled.map((item) => item.status), ["rejected", "rejected"]);
  assert.equal(settled[0].reason, expected);
  assert.equal(settled[1].reason, expected);
  assert.equal(await cache.get("alpha"), "recovered");
  assert.equal(calls, 2);
});


check("retries after a synchronous loader throw", async () => {
  const expected = new Error("synchronous failure");
  let calls = 0;
  const cache = createAsyncCache(
    () => {
      calls += 1;
      if (calls === 1) {
        throw expected;
      }
      return "recovered";
    },
    { ttlMs: 10, now: () => 0 },
  );

  await assert.rejects(cache.get("alpha"), expected);
  assert.equal(await cache.get("alpha"), "recovered");
  assert.equal(calls, 2);
});


check("invalidate prevents an in-flight result from repopulating", async () => {
  const attempts = [deferred(), deferred()];
  let calls = 0;
  const cache = createAsyncCache(
    async () => attempts[calls++].promise,
    { ttlMs: 10, now: () => 0 },
  );

  const stale = cache.get("alpha");
  await Promise.resolve();
  cache.invalidate("alpha");
  const fresh = cache.get("alpha");
  await Promise.resolve();
  assert.equal(calls, 2);

  attempts[1].resolve("fresh");
  assert.equal(await fresh, "fresh");
  attempts[0].resolve("stale");
  assert.equal(await stale, "stale");
  assert.equal(await cache.get("alpha"), "fresh");
  assert.equal(calls, 2);
});


check("clear invalidates all in-flight keys without cancelling callers", async () => {
  const attempts = new Map([
    ["alpha", [deferred(), deferred()]],
    ["beta", [deferred(), deferred()]],
  ]);
  const calls = new Map();
  const cache = createAsyncCache(
    async (key) => {
      const count = calls.get(key) ?? 0;
      calls.set(key, count + 1);
      return attempts.get(key)[count].promise;
    },
    { ttlMs: 10, now: () => 0 },
  );

  const staleAlpha = cache.get("alpha");
  const staleBeta = cache.get("beta");
  await Promise.resolve();
  cache.clear();
  const freshAlpha = cache.get("alpha");
  const freshBeta = cache.get("beta");
  await Promise.resolve();
  assert.deepEqual(Object.fromEntries(calls), { alpha: 2, beta: 2 });

  attempts.get("alpha")[1].resolve("fresh-a");
  attempts.get("beta")[1].resolve("fresh-b");
  assert.deepEqual(await Promise.all([freshAlpha, freshBeta]), ["fresh-a", "fresh-b"]);
  attempts.get("alpha")[0].resolve("stale-a");
  attempts.get("beta")[0].resolve("stale-b");
  assert.deepEqual(
    await Promise.all([staleAlpha, staleBeta]),
    ["stale-a", "stale-b"],
  );
  assert.equal(await cache.get("alpha"), "fresh-a");
  assert.equal(await cache.get("beta"), "fresh-b");
  assert.deepEqual(Object.fromEntries(calls), { alpha: 2, beta: 2 });
});


let failures = 0;
for (const { name, run } of cases) {
  try {
    await run();
    console.log(`ok - ${name}`);
  } catch (error) {
    failures += 1;
    console.error(`not ok - ${name}`);
    console.error(error?.stack ?? error);
  }
}

console.log(`${cases.length - failures}/${cases.length} hidden checks passed`);
if (failures > 0) {
  process.exitCode = 1;
}
