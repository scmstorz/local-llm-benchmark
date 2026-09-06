import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, realpathSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawn } from "node:child_process";
import { test } from "node:test";


test(
  "pinned Pi aborts a stalled local provider at the configured timeout",
  {
    timeout: 10_000,
    skip: process.env.PI_V03_TRANSPORT_QUALIFICATION !== "1",
  },
  async () => {
  const root = mkdtempSync(join(tmpdir(), "llm-benchmark-pi-timeout-"));
  const agentDir = join(root, "agent");
  const workspace = join(root, "workspace");
  mkdirSync(agentDir);
  mkdirSync(workspace);

  let requestCount = 0;
  const server = createServer((request, _response) => {
    requestCount += 1;
    request.resume();
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  assert.equal(typeof address, "object");
  const baseUrl = `http://127.0.0.1:${address.port}/v1`;

  writeFileSync(
    join(agentDir, "models.json"),
    JSON.stringify({
      providers: {
        ollama: {
          baseUrl,
          api: "openai-completions",
          apiKey: "ollama",
          models: [{
            id: "timeout-probe",
            name: "timeout-probe",
            reasoning: false,
            input: ["text"],
            contextWindow: 4096,
            maxTokens: 128,
            cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
          }],
        },
      },
    }),
    "utf8",
  );
  writeFileSync(
    join(agentDir, "settings.json"),
    JSON.stringify({
      defaultProvider: "ollama",
      defaultModel: "timeout-probe",
      enableInstallTelemetry: false,
      enableAnalytics: false,
      defaultProjectTrust: "never",
      quietStartup: true,
      compaction: { enabled: false },
      retry: {
        enabled: false,
        maxRetries: 0,
        provider: { maxRetries: 0, timeoutMs: 250 },
      },
      httpIdleTimeoutMs: 250,
    }),
    "utf8",
  );

  const piEntrypoint = realpathSync("./node_modules/.bin/pi");
  const started = performance.now();
  let output = "";
  const child = spawn(
    process.execPath,
    [
      piEntrypoint,
      "--mode", "json",
      "--print",
      "--provider", "ollama",
      "--model", "timeout-probe",
      "--api-key", "ollama",
      "--thinking", "off",
      "--tools", "read",
      "--no-session",
      "--no-extensions",
      "--no-skills",
      "--no-prompt-templates",
      "--no-themes",
      "--no-context-files",
      "--no-approve",
      "--offline",
      "--system-prompt", "Answer briefly.",
      "--",
      "This is a local transport-timeout probe.",
    ],
    {
      cwd: workspace,
      env: {
        HOME: agentDir,
        PATH: process.env.PATH,
        PI_CODING_AGENT_DIR: agentDir,
        PI_OFFLINE: "1",
        PI_SKIP_VERSION_CHECK: "1",
        PI_TELEMETRY: "0",
      },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  child.stdout.on("data", (chunk) => { output += chunk.toString(); });
  child.stderr.on("data", (chunk) => { output += chunk.toString(); });
  const exitCode = await new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("close", resolve);
  });
  const elapsedMs = performance.now() - started;
  server.closeAllConnections();
  await new Promise((resolve) => server.close(resolve));

  assert.equal(requestCount, 1, output);
  assert.ok(elapsedMs >= 200, `timeout fired too early: ${elapsedMs}ms`);
  assert.ok(elapsedMs < 5_000, `timeout was not enforced promptly: ${elapsedMs}ms`);
  assert.notEqual(exitCode, null);
  assert.match(output, /timeout|timed out|aborted/i);
  },
);
