import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  cpSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { test } from "node:test";

import multiFormatReadonlyExtension, {
  ARTIFACT_TOOL_NAMES,
  TOOL_NAMES,
  loadPolicy,
} from "./multi-format-readonly-v0.3.mjs";


const repoRoot = resolve(import.meta.dirname, "../..");
const backendPath = join(repoRoot, "local_llm_benchmark", "multi_format_transfer_artifacts.py");
const schemaPath = join(repoRoot, "tasks/agentic/multi-format-document-analysis/report-schema-v2.json");
const referencePath = join(repoRoot, "tasks/agentic/multi-format-document-analysis/supplier-award-reconciliation/reference/reference-report-v0.2.json");
const fixtureRoot = join(repoRoot, "tasks/agentic/multi-format-document-analysis/supplier-award-reconciliation/fixture");
const pythonPath = process.env.PYTHON_PATH
  ?? execFileSync("/usr/bin/which", ["python3"], {encoding: "utf8"}).trim();
const pdftotextPath = process.env.PDFTOTEXT_PATH
  ?? execFileSync("/usr/bin/which", ["pdftotext"], {encoding: "utf8"}).trim();


function sha256File(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}


function createPolicy() {
  const root = mkdtempSync(join(tmpdir(), "llm-benchmark-pi-transfer-v04-"));
  const workspace = join(root, "workspace");
  mkdirSync(workspace);
  for (const filename of [
    "supplier-selection-policy.docx",
    "supplier-assurance-review.pdf",
    "bid-evaluation.xlsx",
  ]) {
    cpSync(join(fixtureRoot, filename), join(workspace, filename));
  }
  const auditPath = join(root, "audit.jsonl");
  const finalReportPath = join(root, "captured-report.json");
  const policyPath = join(root, "policy.json");
  writeFileSync(auditPath, "", "utf8");
  writeFileSync(policyPath, JSON.stringify({
    schema_version: "1.0.0",
    policy_id: "pi-multi-format-readonly-v0.2",
    private_run_root: root,
    workspace_root: workspace,
    audit_log_path: auditPath,
    backend_path: backendPath,
    backend_sha256: sha256File(backendPath),
    python_path: pythonPath,
    python_sha256: sha256File(pythonPath),
    pdftotext_path: pdftotextPath,
    pdftotext_sha256: sha256File(pdftotextPath),
    report_schema_path: schemaPath,
    report_schema_sha256: sha256File(schemaPath),
    final_report_path: finalReportPath,
    maximum_report_bytes: 32768,
    allowed_tools: TOOL_NAMES,
    artifact_operations: ARTIFACT_TOOL_NAMES,
    maximum_tool_calls: 40,
    parent_maximum_active_wall_time_seconds: 300,
  }), "utf8");
  return {root, workspace, auditPath, finalReportPath, policyPath};
}


function loadExtension(paths) {
  const previous = process.env.LOCAL_LLM_BENCHMARK_POLICY_PATH;
  process.env.LOCAL_LLM_BENCHMARK_POLICY_PATH = paths.policyPath;
  const tools = [];
  const handlers = {};
  try {
    multiFormatReadonlyExtension({
      registerTool(definition) { tools.push(definition); },
      on(name, handler) { handlers[name] = handler; },
    });
  } finally {
    if (previous === undefined) delete process.env.LOCAL_LLM_BENCHMARK_POLICY_PATH;
    else process.env.LOCAL_LLM_BENCHMARK_POLICY_PATH = previous;
  }
  return {tools, handlers};
}


test("v0.4 policy freezes transfer backend, schema and exact private output", () => {
  const paths = createPolicy();
  const policy = loadPolicy(paths.policyPath);
  assert.equal(policy.backend_path, backendPath);
  assert.equal(policy.report_schema.properties.schema_version.const, "2.0.0");
  assert.equal(policy.final_report_path, paths.finalReportPath);
  assert.deepEqual(policy.allowed_tools, TOOL_NAMES);
});


test("v0.4 registers only four artifact readers plus finish_report", () => {
  const {tools} = loadExtension(createPolicy());
  assert.deepEqual(tools.map((item) => item.name), TOOL_NAMES);
  assert.equal(tools.at(-1).parameters.properties.report.properties.schema_version.const, "2.0.0");
});


test("registered artifact tools execute the shared v0.2 backend", async () => {
  const {tools} = loadExtension(createPolicy());
  const byName = Object.fromEntries(tools.map((item) => [item.name, item]));
  const requests = [
    ["list_artifacts", {}],
    ["read_docx", {anchor: "heading=Selection-sequence"}],
    ["read_pdf", {page: 3, element: "table=Final-assurance&row=Atlas"}],
    ["read_xlsx", {sheet: "Bid Analysis", range: "B5:J5"}],
  ];
  for (const [name, params] of requests) {
    const result = await byName[name].execute("call", params);
    assert.equal(result.details.ok, true);
    assert.equal(result.details.api_version, "0.2.0");
  }
});


test("finish_report captures one exact structured report and shuts down", async () => {
  const paths = createPolicy();
  const {tools, handlers} = loadExtension(paths);
  const finish = tools.find((item) => item.name === "finish_report");
  const report = JSON.parse(readFileSync(referencePath, "utf8"));
  const result = await finish.execute("finish", {report});
  assert.equal(result.details.accepted, true);
  assert.deepEqual(JSON.parse(readFileSync(paths.finalReportPath, "utf8")), report);
  let shutdown = false;
  await handlers.tool_result(
    {toolName: "finish_report", input: {report}, isError: false},
    {shutdown() { shutdown = true; }},
  );
  assert.equal(shutdown, true);
  const audit = readFileSync(paths.auditPath, "utf8");
  assert.match(audit, /"final_report_captured"/);
  assert.match(audit, /"report_sha256"/);
});


test("finish_report rejects a second capture", async () => {
  const {tools} = loadExtension(createPolicy());
  const finish = tools.find((item) => item.name === "finish_report");
  const report = JSON.parse(readFileSync(referencePath, "utf8"));
  await finish.execute("first", {report});
  await assert.rejects(finish.execute("second", {report}), /already captured/);
});


test("injected tools and duplicate completion calls fail closed", async () => {
  const {handlers} = loadExtension(createPolicy());
  const injected = await handlers.tool_call({toolName: "shell", input: {command: "id"}});
  assert.equal(injected.block, true);
  assert.equal(injected.terminate, true);
  await handlers.tool_call({toolName: "finish_report", input: {report: {}}});
  const duplicate = await handlers.tool_call({toolName: "finish_report", input: {report: {}}});
  assert.equal(duplicate.block, true);
  assert.equal(duplicate.terminate, true);
});
