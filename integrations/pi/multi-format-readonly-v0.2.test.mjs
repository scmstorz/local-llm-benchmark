import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { test } from "node:test";

import multiFormatReadonlyExtension, {
  TOOL_NAMES,
  loadPolicy,
} from "./multi-format-readonly-v0.2.mjs";


const repoRoot = resolve(import.meta.dirname, "../..");
const backendPath = join(repoRoot, "local_llm_benchmark", "multi_format_artifacts.py");
const pdftotextPath = "/opt/homebrew/Cellar/poppler/25.11.0/bin/pdftotext";


function createPolicy() {
  const root = mkdtempSync(join(tmpdir(), "llm-benchmark-pi-multiformat-v02-"));
  const pythonPath = join(root, "Python");
  const auditPath = join(root, "audit.jsonl");
  const policyPath = join(root, "policy.json");
  writeFileSync(pythonPath, "synthetic Python worker", "utf8");
  writeFileSync(auditPath, "", "utf8");
  const digest = (path) => createHash("sha256").update(readFileSync(path)).digest("hex");
  writeFileSync(policyPath, JSON.stringify({
    schema_version: "1.0.0",
    policy_id: "pi-multi-format-readonly-v0.1",
    workspace_root: root,
    audit_log_path: auditPath,
    backend_path: backendPath,
    backend_sha256: digest(backendPath),
    python_path: pythonPath,
    python_sha256: digest(pythonPath),
    pdftotext_path: pdftotextPath,
    pdftotext_sha256: digest(pdftotextPath),
    allowed_tools: TOOL_NAMES,
    maximum_tool_calls: 40,
    parent_maximum_active_wall_time_seconds: 300,
  }), "utf8");
  return { policyPath };
}


test("v0.2 admits the exact case-sensitive Python.app worker identity", () => {
  const policy = loadPolicy(createPolicy().policyPath);
  assert.equal(policy.python_path.endsWith("/Python"), true);
  assert.deepEqual(policy.allowed_tools, TOOL_NAMES);
});


test("v0.2 registers only the four bounded artifact tools", () => {
  const previous = process.env.LOCAL_LLM_BENCHMARK_POLICY_PATH;
  process.env.LOCAL_LLM_BENCHMARK_POLICY_PATH = createPolicy().policyPath;
  const tools = [];
  try {
    multiFormatReadonlyExtension({
      on() {},
      registerTool(definition) { tools.push(definition.name); },
    });
  } finally {
    if (previous === undefined) delete process.env.LOCAL_LLM_BENCHMARK_POLICY_PATH;
    else process.env.LOCAL_LLM_BENCHMARK_POLICY_PATH = previous;
  }
  assert.deepEqual(tools, TOOL_NAMES);
});
