import assert from "node:assert/strict";
import { test } from "node:test";

import {
  SettingsManager,
} from "./node_modules/@earendil-works/pi-coding-agent/dist/core/settings-manager.js";


test("pinned Pi loads the Pi Log retry-free 180-second transport settings", () => {
  const settings = SettingsManager.inMemory({
    retry: {
      enabled: false,
      maxRetries: 0,
      provider: {
        maxRetries: 0,
        timeoutMs: 180_000,
      },
    },
    httpIdleTimeoutMs: 180_000,
  });

  assert.equal(settings.getProviderRetrySettings().timeoutMs, 180_000);
  assert.equal(settings.getProviderRetrySettings().maxRetries, 0);
  assert.equal(settings.getHttpIdleTimeoutMs(), 180_000);
  assert.equal(settings.getRetrySettings().enabled, false);
});
