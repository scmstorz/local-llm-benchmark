import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, join, resolve } from "node:path";
import { test } from "node:test";

import multiFormatReadonlyExtension, {
  TOOL_NAMES,
  loadPolicy,
} from "./multi-format-readonly-v0.1.mjs";


const repoRoot = resolve(import.meta.dirname, "../..");
const backendPath = join(repoRoot, "local_llm_benchmark", "multi_format_artifacts.py");
const backendSha = createHash("sha256").update(readFileSync(backendPath)).digest("hex");
const pythonPath = process.env.MULTI_FORMAT_TEST_PYTHON
  ?? execFileSync("/usr/bin/which", ["python3"], { encoding: "utf8" }).trim();
const pdftotextPath = process.env.MULTI_FORMAT_TEST_PDFTOTEXT
  ?? execFileSync("/usr/bin/which", ["pdftotext"], { encoding: "utf8" }).trim();


function createPolicy(overrides = {}) {
  const root = mkdtempSync(join(tmpdir(), "llm-benchmark-pi-multiformat-policy-"));
  const policyPath = join(root, "policy.json");
  const auditPath = join(root, "audit.jsonl");
  writeFileSync(auditPath, "", "utf8");
  writeFileSync(policyPath, JSON.stringify({
    schema_version: "1.0.0",
    policy_id: "pi-multi-format-readonly-v0.1",
    workspace_root: root,
    audit_log_path: auditPath,
    backend_path: backendPath,
    backend_sha256: backendSha,
    python_path: pythonPath,
    python_sha256: createHash("sha256").update(readFileSync(pythonPath)).digest("hex"),
    pdftotext_path: pdftotextPath,
    pdftotext_sha256: createHash("sha256").update(readFileSync(pdftotextPath)).digest("hex"),
    allowed_tools: TOOL_NAMES,
    maximum_tool_calls: 40,
    parent_maximum_active_wall_time_seconds: 600,
    ...overrides,
  }), "utf8");
  return { root, policyPath, auditPath };
}


function handlersFor(policyPath) {
  const handlers = new Map();
  const tools = new Map();
  const previous = process.env.LOCAL_LLM_BENCHMARK_POLICY_PATH;
  process.env.LOCAL_LLM_BENCHMARK_POLICY_PATH = policyPath;
  try {
    multiFormatReadonlyExtension({
      on(name, handler) { handlers.set(name, handler); },
      registerTool(definition) { tools.set(definition.name, definition); },
    });
  } finally {
    if (previous === undefined) delete process.env.LOCAL_LLM_BENCHMARK_POLICY_PATH;
    else process.env.LOCAL_LLM_BENCHMARK_POLICY_PATH = previous;
  }
  return { handlers, tools };
}


test("multi-format policy freezes backend identity and effort boundary", () => {
  const { policyPath } = createPolicy();
  const policy = loadPolicy(policyPath);
  assert.equal(basename(policy.python_path).startsWith("python"), true);
  assert.equal(basename(policy.pdftotext_path), "pdftotext");
  assert.deepEqual(policy.allowed_tools, TOOL_NAMES);
  assert.throws(() => loadPolicy(createPolicy({ backend_sha256: "0".repeat(64) }).policyPath));
  assert.throws(() => loadPolicy(createPolicy({ writable_paths: ["out"] }).policyPath));
});


test("extension registers only the four shared artifact operations", () => {
  const { policyPath } = createPolicy();
  const { tools } = handlersFor(policyPath);
  assert.deepEqual([...tools.keys()], TOOL_NAMES);
});


test("policy logs allowed, repeated and injected tool calls", async () => {
  const { policyPath, auditPath } = createPolicy();
  const { handlers } = handlersFor(policyPath);
  const toolCall = handlers.get("tool_call");
  assert.equal(await toolCall({ toolName: "read_docx", input: { anchor: "heading=Decision-rule" } }), undefined);
  assert.equal(await toolCall({ toolName: "read_docx", input: { anchor: "heading=Decision-rule" } }), undefined);
  const blocked = await toolCall({ toolName: "read", input: { path: "secret" } });
  assert.equal(blocked.block, true);
  assert.equal(blocked.terminate, true);
  await handlers.get("agent_end")({});
  const audit = readFileSync(auditPath, "utf8");
  assert.match(audit, /"repeated_queries":1/);
  assert.match(audit, /"kind":"tool_blocked"/);
  assert.match(audit, /"query_counts"/);
});


test("emergency safeguard terminates the forty-first call", async () => {
  const { policyPath } = createPolicy();
  const { handlers } = handlersFor(policyPath);
  const toolCall = handlers.get("tool_call");
  for (let index = 0; index < 40; index += 1) {
    assert.equal(await toolCall({ toolName: "list_artifacts", input: {} }), undefined);
  }
  const blocked = await toolCall({ toolName: "list_artifacts", input: {} });
  assert.equal(blocked.block, true);
  assert.equal(blocked.terminate, true);
});


test("registered tools execute the shared backend against all three formats", async () => {
  const fixtureRoot = join(
    repoRoot,
    "tasks", "agentic", "multi-format-document-analysis",
    "rollout-readiness-reconciliation", "fixture",
  );
  const { policyPath, auditPath } = createPolicy({ workspace_root: fixtureRoot });
  const { handlers, tools } = handlersFor(policyPath);
  const requests = [
    ["list_artifacts", {}],
    ["read_docx", { anchor: "heading=Decision-rule" }],
    ["read_pdf", { page: 3, element: "table=Final-validation&row=North" }],
    ["read_xlsx", { sheet: "Capacity", range: "B4:E4" }],
  ];
  const factCodes = [];
  for (const [name, input] of requests) {
    assert.equal(await handlers.get("tool_call")({ toolName: name, input }), undefined);
    const result = await tools.get(name).execute("test-call", input);
    const parsed = JSON.parse(result.content[0].text);
    assert.equal(parsed.ok, true);
    if (parsed.record) factCodes.push(parsed.record.fact_code);
    await handlers.get("tool_result")({ toolName: name, input, isError: false });
  }
  assert.deepEqual(factCodes, ["POL-REGION", "REL-NORTH", "CAP-NORTH"]);
  assert.match(readFileSync(auditPath, "utf8"), /"kind":"backend_result"/);
});
