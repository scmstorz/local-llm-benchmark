/** Register and audit the shared read-only multi-format artifact API. */

import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { appendFileSync, lstatSync, readFileSync, realpathSync } from "node:fs";
import { isAbsolute, resolve } from "node:path";
import { performance } from "node:perf_hooks";

export const TOOL_NAMES = ["list_artifacts", "read_docx", "read_pdf", "read_xlsx"];


function requirePositiveInteger(value, context) {
  if (!Number.isInteger(value) || value < 1) {
    throw new Error(`${context} must be a positive integer`);
  }
  return value;
}


function exactRegularFile(path, context) {
  if (!isAbsolute(path)) throw new Error(`${context} must be absolute`);
  const canonical = realpathSync(path);
  const metadata = lstatSync(canonical);
  if (!metadata.isFile()) {
    throw new Error(`${context} must resolve to a regular file`);
  }
  return canonical;
}


function sha256File(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}


export function loadPolicy(policyPath) {
  if (!policyPath) throw new Error("LOCAL_LLM_BENCHMARK_POLICY_PATH is required");
  const policy = JSON.parse(readFileSync(policyPath, "utf8"));
  if (policy.schema_version !== "1.0.0" || policy.policy_id !== "pi-multi-format-readonly-v0.1") {
    throw new Error("Unsupported Pi multi-format policy identity");
  }
  if (!isAbsolute(policy.workspace_root) || !isAbsolute(policy.audit_log_path)) {
    throw new Error("Pi multi-format workspace and audit paths must be absolute");
  }
  if (JSON.stringify(policy.allowed_tools) !== JSON.stringify(TOOL_NAMES)) {
    throw new Error("Pi multi-format tool allowlist changed");
  }
  if (!/^[0-9a-f]{64}$/.test(policy.backend_sha256 ?? "")) {
    throw new Error("Pi multi-format backend hash is invalid");
  }
  const backendPath = exactRegularFile(policy.backend_path, "backend_path");
  if (sha256File(backendPath) !== policy.backend_sha256) {
    throw new Error("Pi multi-format backend hash mismatch");
  }
  const pythonPath = exactRegularFile(policy.python_path, "python_path");
  const pdftotextPath = exactRegularFile(policy.pdftotext_path, "pdftotext_path");
  if (sha256File(pythonPath) !== policy.python_sha256) {
    throw new Error("Pi multi-format Python executable hash mismatch");
  }
  if (sha256File(pdftotextPath) !== policy.pdftotext_sha256) {
    throw new Error("Pi multi-format pdftotext executable hash mismatch");
  }
  if (!pythonPath.split("/").at(-1).startsWith("python")) {
    throw new Error("Pi multi-format backend executable must be Python");
  }
  if (pdftotextPath.split("/").at(-1) !== "pdftotext") {
    throw new Error("Pi multi-format PDF executable must be pdftotext");
  }
  requirePositiveInteger(policy.maximum_tool_calls, "maximum_tool_calls");
  requirePositiveInteger(
    policy.parent_maximum_active_wall_time_seconds,
    "parent_maximum_active_wall_time_seconds",
  );
  for (const forbidden of [
    "readable_paths",
    "writable_paths",
    "maximum_file_writes",
    "maximum_agent_turns",
    "maximum_total_output_tokens",
    "maximum_wall_time_seconds",
  ]) {
    if (policy[forbidden] !== undefined) {
      throw new Error(`Pi multi-format policy contains forbidden field ${forbidden}`);
    }
  }
  return {
    ...policy,
    workspace_root: resolve(policy.workspace_root),
    audit_log_path: resolve(policy.audit_log_path),
    backend_path: backendPath,
    python_path: pythonPath,
    pdftotext_path: pdftotextPath,
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
      env: {
        LC_ALL: "C",
        PATH: "/usr/bin:/bin:/usr/sbin:/sbin",
        PYTHONNOUSERSITE: "1",
      },
      stdio: ["pipe", "pipe", "pipe"],
    },
  );
  const result = JSON.parse(output);
  if (result?.ok !== true || result?.api_version !== "0.1.0") {
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
    repeated_queries: 0,
    input_tokens: 0,
    output_tokens: 0,
  };
  const queryCounts = new Map();

  function audit(kind, detail = {}) {
    appendFileSync(
      policy.audit_log_path,
      `${JSON.stringify({ timestamp: new Date().toISOString(), kind, counts: { ...counts }, ...detail })}\n`,
      "utf8",
    );
  }

  function register(name, description, parameters, toRequest) {
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
            result_sha256: createHash("sha256").update(serialized).digest("hex"),
            wall_time_seconds: (performance.now() - started) / 1000,
          });
          return { content: [{ type: "text", text: serialized }], details: result };
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

  register(
    "list_artifacts",
    "List the three frozen artifacts and their available bounded queries.",
    { type: "object", properties: {}, additionalProperties: false },
    () => ({ operation: "list_artifacts" }),
  );
  register(
    "read_docx",
    "Read one listed semantic anchor from the Word policy.",
    {
      type: "object",
      properties: { anchor: { type: "string" } },
      required: ["anchor"],
      additionalProperties: false,
    },
    (params) => ({ operation: "read_docx", anchor: params.anchor }),
  );
  register(
    "read_pdf",
    "Read one listed page element from the reliability PDF.",
    {
      type: "object",
      properties: { page: { type: "integer" }, element: { type: "string" } },
      required: ["page", "element"],
      additionalProperties: false,
    },
    (params) => ({ operation: "read_pdf", page: params.page, element: params.element }),
  );
  register(
    "read_xlsx",
    "Read one listed range with values and formulas from the readiness workbook.",
    {
      type: "object",
      properties: { sheet: { type: "string" }, range: { type: "string" } },
      required: ["sheet", "range"],
      additionalProperties: false,
    },
    (params) => ({ operation: "read_xlsx", sheet: params.sheet, range: params.range }),
  );

  pi.on("turn_start", async (event) => {
    counts.agent_turns += 1;
    audit("turn_start", { pi_turn_index: event.turnIndex });
  });
  pi.on("turn_end", async (event) => {
    const usage = event.message?.usage;
    counts.input_tokens += Number.isFinite(usage?.input) ? usage.input : 0;
    counts.output_tokens += Number.isFinite(usage?.output) ? usage.output : 0;
    audit("turn_end", { pi_turn_index: event.turnIndex });
  });
  pi.on("tool_call", async (event) => {
    counts.tool_calls += 1;
    if (!TOOL_NAMES.includes(event.toolName)) {
      counts.failed_tool_calls += 1;
      audit("tool_blocked", {
        tool_name: event.toolName,
        input: event.input,
        reason: "Tool is outside the read-only artifact allowlist.",
        terminate: true,
      });
      return { block: true, reason: "Tool is outside the read-only artifact allowlist.", terminate: true };
    }
    if (counts.tool_calls > policy.maximum_tool_calls) {
      counts.failed_tool_calls += 1;
      audit("tool_blocked", {
        tool_name: event.toolName,
        input: event.input,
        reason: "Emergency artifact-call safeguard exceeded.",
        terminate: true,
      });
      return { block: true, reason: "Emergency artifact-call safeguard exceeded.", terminate: true };
    }
    const query = JSON.stringify({ tool_name: event.toolName, input: event.input });
    const prior = queryCounts.get(query) ?? 0;
    queryCounts.set(query, prior + 1);
    if (prior > 0) counts.repeated_queries += 1;
    if (event.toolName === "list_artifacts") counts.list_calls += 1;
    if (event.toolName === "read_docx") counts.docx_reads += 1;
    if (event.toolName === "read_pdf") counts.pdf_reads += 1;
    if (event.toolName === "read_xlsx") counts.xlsx_reads += 1;
    audit("tool_allowed", { tool_name: event.toolName, input: event.input });
    return undefined;
  });
  pi.on("tool_result", async (event) => {
    if (event.isError) counts.failed_tool_calls += 1;
    audit("tool_result", { tool_name: event.toolName, input: event.input, is_error: event.isError });
  });
  pi.on("agent_end", async () => {
    audit("agent_end", { query_counts: Object.fromEntries(queryCounts) });
  });
}
