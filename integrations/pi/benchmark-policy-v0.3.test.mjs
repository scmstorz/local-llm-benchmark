import assert from "node:assert/strict";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { mkdtempSync } from "node:fs";

import benchmarkPolicyExtension, {
  loadPolicy,
  relativeWorkspacePath,
} from "./benchmark-policy-v0.3.mjs";


function createFixture({ forbiddenLimit = null } = {}) {
  const root = mkdtempSync(join(tmpdir(), "llm-benchmark-pi-policy-v03-"));
  mkdirSync(join(root, "src"));
  mkdirSync(join(root, "tests"));
  writeFileSync(join(root, "src", "allowed.php"), "<?php\n", "utf8");
  writeFileSync(join(root, "src", "protected.php"), "<?php\n", "utf8");
  writeFileSync(join(root, "tests", "run.php"), "<?php\n", "utf8");
  const policyPath = join(root, "policy.json");
  const auditPath = join(root, "audit.jsonl");
  const policy = {
    schema_version: "1.1.0",
    workspace_root: root,
    audit_log_path: auditPath,
    readable_paths: ["src/allowed.php", "src/protected.php", "tests/run.php"],
    writable_paths: ["src/allowed.php"],
    public_test_command: "php tests/run.php",
    maximum_file_reads: 2,
    maximum_file_writes: 2,
    maximum_public_test_runs: 1,
    maximum_write_bytes: 1024,
    parent_maximum_active_wall_time_seconds: 900,
  };
  if (forbiddenLimit !== null) {
    policy[forbiddenLimit] = 10;
  }
  writeFileSync(policyPath, JSON.stringify(policy), "utf8");
  return { root, policyPath, auditPath };
}


function registerExtension(policyPath) {
  const handlers = new Map();
  const previous = process.env.LOCAL_LLM_BENCHMARK_POLICY_PATH;
  process.env.LOCAL_LLM_BENCHMARK_POLICY_PATH = policyPath;
  try {
    benchmarkPolicyExtension({
      on(name, handler) {
        handlers.set(name, handler);
      },
    });
  } finally {
    if (previous === undefined) {
      delete process.env.LOCAL_LLM_BENCHMARK_POLICY_PATH;
    } else {
      process.env.LOCAL_LLM_BENCHMARK_POLICY_PATH = previous;
    }
  }
  return handlers;
}


test("v0.3 policy rejects reintroduced turn, token, and extension-time limits", () => {
  for (const forbiddenLimit of [
    "maximum_agent_turns",
    "maximum_total_output_tokens",
    "maximum_wall_time_seconds",
  ]) {
    const { policyPath } = createFixture({ forbiddenLimit });
    assert.throws(() => loadPolicy(policyPath));
  }
});


test("v0.3 records arbitrarily large token usage without aborting", async () => {
  const { policyPath, auditPath } = createFixture();
  const handlers = registerExtension(policyPath);
  let aborted = false;

  await handlers.get("turn_end")(
    {
      turnIndex: 0,
      message: { usage: { input: 2_000_000, output: 1_000_000 } },
      toolResults: [],
    },
    { abort() { aborted = true; } },
  );

  assert.equal(aborted, false);
  const audit = readFileSync(auditPath, "utf8");
  assert.match(audit, /"output_tokens":1000000/);
  assert.equal(audit.includes("output_token_budget_exceeded"), false);
});


test("v0.3 records turns without an extension-side time or turn abort", async () => {
  const { policyPath, auditPath } = createFixture();
  const handlers = registerExtension(policyPath);
  let aborted = false;

  for (let index = 0; index < 100; index += 1) {
    await handlers.get("turn_start")(
      { turnIndex: index },
      { abort() { aborted = true; } },
    );
  }

  assert.equal(aborted, false);
  const audit = readFileSync(auditPath, "utf8");
  assert.equal(audit.split('"kind":"turn_start"').length - 1, 100);
});


test("v0.3 retains path, command, and emergency operation safeguards", async () => {
  const { root, policyPath } = createFixture();
  const handlers = registerExtension(policyPath);
  const toolCall = handlers.get("tool_call");

  const allowedRead = await toolCall({
    toolName: "read",
    input: { path: "src/allowed.php" },
  });
  const blockedWrite = await toolCall({
    toolName: "write",
    input: { path: "src/protected.php", content: "<?php\n" },
  });
  const blockedTraversal = await toolCall({
    toolName: "read",
    input: { path: "../secret" },
  });
  const blockedCommand = await toolCall({
    toolName: "bash",
    input: { command: "php tests/run.php && env" },
  });
  const allowedCommand = await toolCall({
    toolName: "bash",
    input: { command: "php tests/run.php" },
  });
  const repeatedCommand = await toolCall({
    toolName: "bash",
    input: { command: "php tests/run.php" },
  });

  assert.equal(allowedRead, undefined);
  assert.equal(blockedWrite.block, true);
  assert.equal(blockedTraversal.block, true);
  assert.equal(blockedCommand.block, true);
  assert.equal(allowedCommand, undefined);
  assert.equal(repeatedCommand.block, true);
  assert.equal(repeatedCommand.terminate, true);
  assert.equal(relativeWorkspacePath(root, "src/allowed.php"), "src/allowed.php");
});


test("v0.3 records the first successful public verification once", async () => {
  const { policyPath, auditPath } = createFixture();
  const handlers = registerExtension(policyPath);

  await handlers.get("tool_result")({
    toolName: "bash",
    input: { command: "php tests/run.php" },
    isError: false,
  });
  await handlers.get("tool_result")({
    toolName: "bash",
    input: { command: "php tests/run.php" },
    isError: false,
  });

  const audit = readFileSync(auditPath, "utf8");
  assert.equal(
    audit.split("first_successful_public_verification").length - 1,
    1,
  );
});
