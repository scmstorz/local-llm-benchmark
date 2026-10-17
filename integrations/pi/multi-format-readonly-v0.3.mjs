/** Read-only supplier-artifact tools with structured final-report capture. */

import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  appendFileSync,
  existsSync,
  lstatSync,
  readFileSync,
  realpathSync,
  writeFileSync,
} from "node:fs";
import { basename, dirname, isAbsolute, resolve } from "node:path";
import { performance } from "node:perf_hooks";

export const ARTIFACT_TOOL_NAMES = ["list_artifacts", "read_docx", "read_pdf", "read_xlsx"];
export const TOOL_NAMES = [...ARTIFACT_TOOL_NAMES, "finish_report"];


function requirePositiveInteger(value, context) {
  if (!Number.isInteger(value) || value < 1) {
    throw new Error(`${context} must be a positive integer`);
  }
  return value;
}


function exactRegularFile(path, context) {
  if (!isAbsolute(path)) throw new Error(`${context} must be absolute`);
  const canonical = realpathSync(path);
  if (!lstatSync(canonical).isFile()) {
    throw new Error(`${context} must resolve to a regular file`);
  }
  return canonical;
}


function exactNewFile(path, privateRoot, context) {
  if (!isAbsolute(path) || existsSync(path)) {
    throw new Error(`${context} must be an absent absolute file`);
  }
  const parent = realpathSync(dirname(path));
  if (parent !== privateRoot) {
    throw new Error(`${context} must be directly inside private_run_root`);
  }
  return resolve(path);
}


function sha256Bytes(value) {
  return createHash("sha256").update(value).digest("hex");
}


function sha256File(path) {
  return sha256Bytes(readFileSync(path));
}


export function loadPolicy(policyPath) {
  if (!policyPath) throw new Error("LOCAL_LLM_BENCHMARK_POLICY_PATH is required");
  const policy = JSON.parse(readFileSync(policyPath, "utf8"));
  if (policy.schema_version !== "1.0.0" || policy.policy_id !== "pi-multi-format-readonly-v0.2") {
    throw new Error("Unsupported Pi multi-format transfer policy identity");
  }
  if (!isAbsolute(policy.private_run_root) || !isAbsolute(policy.workspace_root) || !isAbsolute(policy.audit_log_path)) {
    throw new Error("Pi transfer run, workspace and audit paths must be absolute");
  }
  const privateRoot = realpathSync(policy.private_run_root);
  if (realpathSync(dirname(policy.workspace_root)) !== privateRoot) {
    throw new Error("Pi transfer workspace must be directly inside private_run_root");
  }
  if (JSON.stringify(policy.allowed_tools) !== JSON.stringify(TOOL_NAMES)) {
    throw new Error("Pi transfer tool allowlist changed");
  }
  if (JSON.stringify(policy.artifact_operations) !== JSON.stringify(ARTIFACT_TOOL_NAMES)) {
    throw new Error("Pi transfer artifact operation allowlist changed");
  }
  const backendPath = exactRegularFile(policy.backend_path, "backend_path");
  const pythonPath = exactRegularFile(policy.python_path, "python_path");
  const pdftotextPath = exactRegularFile(policy.pdftotext_path, "pdftotext_path");
  const reportSchemaPath = exactRegularFile(policy.report_schema_path, "report_schema_path");
  for (const [path, expected, context] of [
    [backendPath, policy.backend_sha256, "backend"],
    [pythonPath, policy.python_sha256, "Python executable"],
    [pdftotextPath, policy.pdftotext_sha256, "pdftotext executable"],
    [reportSchemaPath, policy.report_schema_sha256, "report schema"],
  ]) {
    if (!/^[0-9a-f]{64}$/.test(expected ?? "") || sha256File(path) !== expected) {
      throw new Error(`${context} hash mismatch`);
    }
  }
  const pythonName = basename(pythonPath);
  if (!(pythonName === "Python" || pythonName.startsWith("python"))) {
    throw new Error("Pi transfer backend executable must be Python");
  }
  if (basename(pdftotextPath) !== "pdftotext") {
    throw new Error("Pi transfer PDF executable must be pdftotext");
  }
  requirePositiveInteger(policy.maximum_tool_calls, "maximum_tool_calls");
  requirePositiveInteger(policy.parent_maximum_active_wall_time_seconds, "parent_maximum_active_wall_time_seconds");
  requirePositiveInteger(policy.maximum_report_bytes, "maximum_report_bytes");
  const reportSchema = JSON.parse(readFileSync(reportSchemaPath, "utf8"));
  if (reportSchema?.type !== "object" || reportSchema?.properties?.schema_version?.const !== "2.0.0") {
    throw new Error("Pi transfer report schema identity changed");
  }
  const finalReportPath = exactNewFile(policy.final_report_path, privateRoot, "final_report_path");
  for (const forbidden of [
    "readable_paths",
    "writable_paths",
    "maximum_file_writes",
    "maximum_agent_turns",
    "maximum_total_output_tokens",
    "maximum_wall_time_seconds",
  ]) {
    if (policy[forbidden] !== undefined) {
      throw new Error(`Pi transfer policy contains forbidden field ${forbidden}`);
    }
  }
  return {
    ...policy,
    private_run_root: privateRoot,
    workspace_root: resolve(policy.workspace_root),
    audit_log_path: resolve(policy.audit_log_path),
    backend_path: backendPath,
    python_path: pythonPath,
    pdftotext_path: pdftotextPath,
    report_schema_path: reportSchemaPath,
    report_schema: reportSchema,
    final_report_path: finalReportPath,
  };
}


function backendRequest(policy, request) {
  const output = execFileSync(
    policy.python_path,
    [
      "-I",
      "-B",
      policy.backend_path,
      "--workspace",
      policy.workspace_root,
      "--pdftotext",
      policy.pdftotext_path,
    ],
    {
      cwd: policy.workspace_root,
      input: JSON.stringify(request),
      encoding: "utf8",
      timeout: 20000,
      maxBuffer: 16384,
      env: {LC_ALL: "C", PATH: "/usr/bin:/bin:/usr/sbin:/sbin", PYTHONNOUSERSITE: "1"},
      stdio: ["pipe", "pipe", "pipe"],
    },
  );
  const result = JSON.parse(output);
  if (result?.ok !== true || result?.api_version !== "0.2.0") {
    throw new Error("Artifact backend returned an invalid result");
  }
  return result;
}


export default function multiFormatReadonlyExtension(pi) {
  const policy = loadPolicy(process.env.LOCAL_LLM_BENCHMARK_POLICY_PATH);
  const counts = {
    agent_turns: 0,
    tool_calls: 0,
    failed_tool_calls: 0,
    list_calls: 0,
    docx_reads: 0,
    pdf_reads: 0,
    xlsx_reads: 0,
    finish_report_calls: 0,
    repeated_queries: 0,
    input_tokens: 0,
    output_tokens: 0,
  };
  const queryCounts = new Map();
  let reportCaptured = false;

  function audit(kind, detail = {}) {
    appendFileSync(
      policy.audit_log_path,
      `${JSON.stringify({timestamp: new Date().toISOString(), kind, counts: {...counts}, ...detail})}\n`,
      "utf8",
    );
  }

  function registerArtifact(name, description, parameters, toRequest) {
    pi.registerTool({
      name,
      label: name,
      description,
      promptSnippet: description,
      parameters,
      async execute(_toolCallId, params) {
        const request = toRequest(params);
        const started = performance.now();
        try {
          const result = backendRequest(policy, request);
          const serialized = JSON.stringify(result);
          audit("backend_result", {
            tool_name: name,
            ok: true,
            result_sha256: sha256Bytes(serialized),
            wall_time_seconds: (performance.now() - started) / 1000,
          });
          return {content: [{type: "text", text: serialized}], details: result};
        } catch (error) {
          counts.failed_tool_calls += 1;
          audit("backend_result", {
            tool_name: name,
            ok: false,
            error_type: error?.constructor?.name ?? "Error",
            wall_time_seconds: (performance.now() - started) / 1000,
          });
          throw new Error("The bounded artifact read failed");
        }
      },
    });
  }

  registerArtifact(
    "list_artifacts",
    "List the three frozen artifacts and their available bounded queries.",
    {type: "object", properties: {}, additionalProperties: false},
    () => ({operation: "list_artifacts"}),
  );
  registerArtifact(
    "read_docx",
    "Read one listed semantic anchor from the supplier policy.",
    {
      type: "object",
      properties: {anchor: {type: "string"}},
      required: ["anchor"],
      additionalProperties: false,
    },
    (params) => ({operation: "read_docx", anchor: params.anchor}),
  );
  registerArtifact(
    "read_pdf",
    "Read one listed page element from the supplier assurance review.",
    {
      type: "object",
      properties: {page: {type: "integer"}, element: {type: "string"}},
      required: ["page", "element"],
      additionalProperties: false,
    },
    (params) => ({operation: "read_pdf", page: params.page, element: params.element}),
  );
  registerArtifact(
    "read_xlsx",
    "Read one listed range with values and formulas from the bid evaluation.",
    {
      type: "object",
      properties: {sheet: {type: "string"}, range: {type: "string"}},
      required: ["sheet", "range"],
      additionalProperties: false,
    },
    (params) => ({operation: "read_xlsx", sheet: params.sheet, range: params.range}),
  );
  pi.registerTool({
    name: "finish_report",
    label: "finish_report",
    description: "Submit the complete German supplier-selection report and end the run.",
    promptSnippet: "Submit the final report only through finish_report.",
    parameters: {
      type: "object",
      additionalProperties: false,
      required: ["report"],
      properties: {report: policy.report_schema},
    },
    async execute(_toolCallId, params) {
      if (reportCaptured || existsSync(policy.final_report_path)) {
        counts.failed_tool_calls += 1;
        throw new Error("A final report was already captured");
      }
      if (!params?.report || typeof params.report !== "object" || Array.isArray(params.report)) {
        counts.failed_tool_calls += 1;
        throw new Error("finish_report requires one report object");
      }
      const serialized = JSON.stringify(params.report);
      const size = Buffer.byteLength(serialized, "utf8");
      if (size > policy.maximum_report_bytes) {
        counts.failed_tool_calls += 1;
        throw new Error("The final report exceeds the byte limit");
      }
      writeFileSync(policy.final_report_path, `${serialized}\n`, {
        encoding: "utf8",
        flag: "wx",
        mode: 0o600,
      });
      reportCaptured = true;
      audit("final_report_captured", {
        tool_name: "finish_report",
        report_sha256: sha256Bytes(serialized),
        report_size_bytes: size,
      });
      return {
        content: [{type: "text", text: '{"ok":true,"accepted":true}'}],
        details: {ok: true, accepted: true, report_sha256: sha256Bytes(serialized)},
      };
    },
  });

  pi.on("turn_start", async (event) => {
    counts.agent_turns += 1;
    audit("turn_start", {pi_turn_index: event.turnIndex});
  });
  pi.on("turn_end", async (event) => {
    const usage = event.message?.usage;
    counts.input_tokens += Number.isFinite(usage?.input) ? usage.input : 0;
    counts.output_tokens += Number.isFinite(usage?.output) ? usage.output : 0;
    audit("turn_end", {pi_turn_index: event.turnIndex});
  });
  pi.on("tool_call", async (event) => {
    counts.tool_calls += 1;
    if (!TOOL_NAMES.includes(event.toolName)) {
      counts.failed_tool_calls += 1;
      audit("tool_blocked", {
        tool_name: event.toolName,
        input: event.input,
        reason: "Tool is outside the read-only transfer allowlist.",
        terminate: true,
      });
      return {block: true, reason: "Tool is outside the read-only transfer allowlist.", terminate: true};
    }
    const artifactCalls = counts.list_calls + counts.docx_reads + counts.pdf_reads + counts.xlsx_reads;
    const artifactLimitExceeded = ARTIFACT_TOOL_NAMES.includes(event.toolName)
      && artifactCalls >= policy.maximum_tool_calls;
    const duplicateCompletion = event.toolName === "finish_report"
      && counts.finish_report_calls >= 1;
    if (artifactLimitExceeded || duplicateCompletion) {
      counts.failed_tool_calls += 1;
      audit("tool_blocked", {
        tool_name: event.toolName,
        input: event.input,
        reason: duplicateCompletion
          ? "Only one finish_report call is allowed."
          : "Emergency artifact-call safeguard exceeded.",
        terminate: true,
      });
      return {
        block: true,
        reason: duplicateCompletion
          ? "Only one finish_report call is allowed."
          : "Emergency artifact-call safeguard exceeded.",
        terminate: true,
      };
    }
    const query = JSON.stringify({tool_name: event.toolName, input: event.input});
    const prior = queryCounts.get(query) ?? 0;
    queryCounts.set(query, prior + 1);
    if (prior > 0) counts.repeated_queries += 1;
    if (event.toolName === "list_artifacts") counts.list_calls += 1;
    if (event.toolName === "read_docx") counts.docx_reads += 1;
    if (event.toolName === "read_pdf") counts.pdf_reads += 1;
    if (event.toolName === "read_xlsx") counts.xlsx_reads += 1;
    if (event.toolName === "finish_report") counts.finish_report_calls += 1;
    audit("tool_allowed", {tool_name: event.toolName, input: event.input});
    return undefined;
  });
  pi.on("tool_result", async (event, ctx) => {
    if (event.isError) counts.failed_tool_calls += 1;
    audit("tool_result", {tool_name: event.toolName, input: event.input, is_error: event.isError});
    if (event.toolName === "finish_report" && !event.isError && reportCaptured) {
      audit("structured_completion", {terminate: true});
      ctx.shutdown();
    }
  });
  pi.on("agent_end", async () => {
    audit("agent_end", {query_counts: Object.fromEntries(queryCounts)});
  });
}
