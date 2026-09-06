import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import logReadonlyPolicyExtension, {
  loadPolicy,
  relativeWorkspacePath,
} from "./log-readonly-policy-v0.1.mjs";


function createFixture(overrides = {}) {
  const root = mkdtempSync(join(tmpdir(), "llm-benchmark-pi-log-policy-"));
  mkdirSync(join(root, "logs"));
  writeFileSync(join(root, "logs", "allowed.log"), "EVENT-1 ok\n", "utf8");
  writeFileSync(join(root, "logs", "hidden.log"), "SECRET\n", "utf8");
  const policyPath = join(root, "policy.json");
  const auditPath = join(root, "audit.jsonl");
  writeFileSync(policyPath, JSON.stringify({
    schema_version: "1.0.0",
    workspace_root: root,
    audit_log_path: auditPath,
    readable_paths: ["logs/allowed.log"],
    allowed_tools: ["read"],
    maximum_file_reads: 2,
    parent_maximum_active_wall_time_seconds: 300,
    ...overrides,
  }), "utf8");
  return { root, policyPath, auditPath };
}


function handlersFor(policyPath) {
  const handlers = new Map();
  const previous = process.env.LOCAL_LLM_BENCHMARK_POLICY_PATH;
  process.env.LOCAL_LLM_BENCHMARK_POLICY_PATH = policyPath;
  try {
    logReadonlyPolicyExtension({ on(name, handler) { handlers.set(name, handler); } });
  } finally {
    if (previous === undefined) delete process.env.LOCAL_LLM_BENCHMARK_POLICY_PATH;
    else process.env.LOCAL_LLM_BENCHMARK_POLICY_PATH = previous;
  }
  return handlers;
}


test("policy accepts only the read capability and measurement-only effort", () => {
  const { policyPath } = createFixture();
  const policy = loadPolicy(policyPath);
  assert.deepEqual(policy.allowed_tools, ["read"]);
  for (const forbidden of [
    "writable_paths",
    "public_test_command",
    "maximum_file_writes",
    "maximum_public_test_runs",
    "maximum_agent_turns",
    "maximum_total_output_tokens",
    "maximum_wall_time_seconds",
  ]) {
    const fixture = createFixture({ [forbidden]: forbidden.endsWith("paths") ? [] : 1 });
    assert.throws(() => loadPolicy(fixture.policyPath));
  }
});


test("read policy permits declared files and rejects traversal and hidden files", async () => {
  const { root, policyPath } = createFixture();
  const toolCall = handlersFor(policyPath).get("tool_call");
  assert.equal(await toolCall({ toolName: "read", input: { path: "logs/allowed.log" } }), undefined);
  assert.equal((await toolCall({ toolName: "read", input: { path: "logs/hidden.log" } })).block, true);
  assert.equal((await toolCall({ toolName: "read", input: { path: "../secret" } })).block, true);
  assert.equal(relativeWorkspacePath(root, "logs/allowed.log"), "logs/allowed.log");
});


test("write and shell tools terminate even if a caller tries to inject them", async () => {
  const { policyPath } = createFixture();
  const toolCall = handlersFor(policyPath).get("tool_call");
  for (const toolName of ["write", "edit", "bash", "browser"] ) {
    const result = await toolCall({ toolName, input: { path: "logs/allowed.log" } });
    assert.equal(result.block, true);
    assert.equal(result.terminate, true);
  }
});


test("read repetitions and the emergency safeguard remain visible", async () => {
  const { policyPath, auditPath } = createFixture();
  const handlers = handlersFor(policyPath);
  const toolCall = handlers.get("tool_call");
  await toolCall({ toolName: "read", input: { path: "logs/allowed.log" } });
  await toolCall({ toolName: "read", input: { path: "logs/allowed.log" } });
  const blocked = await toolCall({ toolName: "read", input: { path: "logs/allowed.log" } });
  await handlers.get("agent_end")({});
  assert.equal(blocked.block, true);
  assert.equal(blocked.terminate, true);
  const audit = readFileSync(auditPath, "utf8");
  assert.match(audit, /"repeated_file_reads":1/);
  assert.match(audit, /"read_paths":\{"logs\/allowed.log":2\}/);
});
