import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  SettingsManager,
} from "./node_modules/@earendil-works/pi-coding-agent/dist/core/settings-manager.js";


test("pinned Pi loads the explicit v0.3 provider and HTTP timeouts", () => {
  const settings = SettingsManager.inMemory({
    retry: {
      enabled: false,
      maxRetries: 0,
      provider: {
        maxRetries: 0,
        timeoutMs: 300_000,
      },
    },
    httpIdleTimeoutMs: 300_000,
  });

  assert.equal(settings.getProviderRetrySettings().timeoutMs, 300_000);
  assert.equal(settings.getProviderRetrySettings().maxRetries, 0);
  assert.equal(settings.getHttpIdleTimeoutMs(), 300_000);
  assert.equal(settings.getRetrySettings().enabled, false);
});


test("pinned Pi forwards the selected timeout into its provider stream", () => {
  const source = readFileSync(
    new URL(
      "./node_modules/@earendil-works/pi-coding-agent/dist/core/sdk.js",
      import.meta.url,
    ),
    "utf8",
  );

  assert.match(
    source,
    /const timeoutMs = options\?\.timeoutMs \?\? providerRetrySettings\.timeoutMs \?\? effectiveTimeoutMs;/,
  );
  assert.match(source, /modelRuntime\.streamSimple\(model, context, \{/);
  assert.match(source, /\n\s*timeoutMs,\n/);
});
