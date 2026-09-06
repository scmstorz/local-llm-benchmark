import assert from "node:assert/strict";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { mkdtempSync } from "node:fs";

import benchmarkPolicyExtension, {
  loadPolicy,
  relativeWorkspacePath,
} from "./benchmark-policy.mjs";


function createFixture({ maximumAgentTurns = 4 } = {}) {
  const root = mkdtempSync(join(tmpdir(), "llm-benchmark-pi-policy-"));
  mkdirSync(join(root, "src"));
  mkdirSync(join(root, "tests"));
  writeFileSync(join(root, "src", "allowed.php"), "<?php\n", "utf8");
  writeFileSync(join(root, "src", "protected.php"), "<?php\n", "utf8");
  writeFileSync(join(root, "tests", "run.php"), "<?php\n", "utf8");
  const policyPath = join(root, "policy.json");
  const auditPath = join(root, "audit.jsonl");
  const policy = {
      schema_version: "1.0.0",
      workspace_root: root,
      audit_log_path: auditPath,
      readable_paths: ["src/allowed.php", "src/protected.php", "tests/run.php"],
      writable_paths: ["src/allowed.php"],
      public_test_command: "php tests/run.php",
      maximum_file_reads: 2,
      maximum_file_writes: 2,
      maximum_public_test_runs: 1,
      maximum_total_output_tokens: 10,
      maximum_write_bytes: 1024,
      maximum_wall_time_seconds: 60,
  };
  if (maximumAgentTurns !== null) {
    policy.maximum_agent_turns = maximumAgentTurns;
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


test("policy loader and relative path guard reject unsafe configuration", () => {
  const { root, policyPath } = createFixture();
  const policy = loadPolicy(policyPath);
  assert.equal(policy.workspace_root, root);
  assert.equal(relativeWorkspacePath(root, "src/allowed.php"), "src/allowed.php");
  assert.equal(relativeWorkspacePath(root, "../outside"), null);
  assert.equal(relativeWorkspacePath(root, root), null);
});


test("extension permits declared operations and blocks scope and command drift", async () => {
  const { root, policyPath, auditPath } = createFixture();
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
  const allowedWrite = await toolCall({
    toolName: "write",
    input: { path: "src/allowed.php", content: "<?php // private-candidate-text\n" },
  });
  const allowedEdit = await toolCall({
    toolName: "edit",
    input: {
      path: "src/allowed.php",
      edits: [{ oldText: "<?php", newText: "<?php // another-private-string" }],
    },
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
  assert.equal(allowedWrite, undefined);
  assert.equal(allowedEdit, undefined);
  assert.equal(blockedCommand.block, true);
  assert.equal(allowedCommand, undefined);
  assert.equal(repeatedCommand.block, true);
  assert.equal(relativeWorkspacePath(root, "src/allowed.php"), "src/allowed.php");
  const audit = readFileSync(auditPath, "utf8");
  assert.equal(audit.includes("private-candidate-text"), false);
  assert.equal(audit.includes("another-private-string"), false);
});


test("extension records usage and aborts after the total output budget", async () => {
  const { policyPath } = createFixture();
  const handlers = registerExtension(policyPath);
  let aborted = false;

  await handlers.get("turn_end")(
    {
      turnIndex: 0,
      message: { usage: { input: 20, output: 11 } },
      toolResults: [],
    },
    { abort() { aborted = true; } },
  );

  assert.equal(aborted, true);
});


test("extension records turns without a normal turn limit", async () => {
  const { policyPath, auditPath } = createFixture({ maximumAgentTurns: null });
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


test("extension records the first successful public verification once", async () => {
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
