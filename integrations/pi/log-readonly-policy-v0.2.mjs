/** Enforce and audit the v0.2 read-only Pi log-analysis capability surface. */

import { appendFileSync, lstatSync, readFileSync } from "node:fs";
import { isAbsolute, relative, resolve, sep } from "node:path";


function requirePositiveInteger(value, context) {
  if (!Number.isInteger(value) || value < 1) {
    throw new Error(`${context} must be a positive integer`);
  }
  return value;
}


export function loadPolicy(policyPath) {
  if (!policyPath) {
    throw new Error("LOCAL_LLM_BENCHMARK_POLICY_PATH is required");
  }
  const policy = JSON.parse(readFileSync(policyPath, "utf8"));
  if (policy.schema_version !== "1.0.0" || policy.policy_id !== "pi-log-readonly-v0.2") {
    throw new Error("Unsupported Pi Log v0.2 policy identity");
  }
  if (!isAbsolute(policy.workspace_root) || !isAbsolute(policy.audit_log_path)) {
    throw new Error("Pi Log policy paths must be absolute");
  }
  if (!Array.isArray(policy.readable_paths) || policy.readable_paths.length < 1) {
    throw new Error("Pi Log readable_paths must be a non-empty array");
  }
  if (new Set(policy.readable_paths).size !== policy.readable_paths.length) {
    throw new Error("Pi Log readable_paths must not contain duplicates");
  }
  if (policy.allowed_tools?.length !== 1 || policy.allowed_tools[0] !== "read") {
    throw new Error("Pi Log policy must expose only the read tool");
  }
  if (
    policy.writable_paths !== undefined
    || policy.public_test_command !== undefined
    || policy.maximum_file_writes !== undefined
    || policy.maximum_public_test_runs !== undefined
    || policy.maximum_agent_turns !== undefined
    || policy.maximum_total_output_tokens !== undefined
    || policy.maximum_wall_time_seconds !== undefined
  ) {
    throw new Error("Pi Log policy contains a forbidden capability or effort limit");
  }
  requirePositiveInteger(policy.maximum_file_reads, "maximum_file_reads");
  requirePositiveInteger(
    policy.parent_maximum_active_wall_time_seconds,
    "parent_maximum_active_wall_time_seconds",
  );
  return {
    ...policy,
    workspace_root: resolve(policy.workspace_root),
    readable_paths: new Set(policy.readable_paths),
  };
}


export function relativeWorkspacePath(workspaceRoot, inputPath) {
  if (typeof inputPath !== "string" || !inputPath) {
    return null;
  }
  const absolute = resolve(workspaceRoot, inputPath);
  const candidate = relative(workspaceRoot, absolute);
  if (!candidate || candidate === ".." || candidate.startsWith(`..${sep}`) || isAbsolute(candidate)) {
    return null;
  }
  return candidate.split(sep).join("/");
}


function isExistingRegularFile(workspaceRoot, candidate) {
  try {
    const metadata = lstatSync(resolve(workspaceRoot, candidate));
    return metadata.isFile() && !metadata.isSymbolicLink();
  } catch {
    return false;
  }
}


export default function logReadonlyPolicyExtension(pi) {
  const policy = loadPolicy(process.env.LOCAL_LLM_BENCHMARK_POLICY_PATH);
  const counts = {
    agent_turns: 0,
    tool_calls: 0,
    failed_tool_calls: 0,
    file_reads: 0,
    repeated_file_reads: 0,
    input_tokens: 0,
    output_tokens: 0,
  };
  const readsByPath = new Map();

  function audit(kind, detail = {}) {
    appendFileSync(
      policy.audit_log_path,
      `${JSON.stringify({ timestamp: new Date().toISOString(), kind, counts: { ...counts }, ...detail })}\n`,
      "utf8",
    );
  }

  function blocked(event, reason, candidate = null, terminate = false) {
    counts.failed_tool_calls += 1;
    audit("tool_blocked", { tool_name: event.toolName, path: candidate, reason, terminate });
    return { block: true, reason, terminate };
  }

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
    if (event.toolName !== "read") {
      return blocked(event, `Tool ${event.toolName} is outside the read-only allowlist.`, null, true);
    }
    const candidate = relativeWorkspacePath(policy.workspace_root, event.input.path);
    if (!candidate || !isExistingRegularFile(policy.workspace_root, candidate)) {
      return blocked(event, "Path is outside the workspace or is not an existing regular file.", candidate);
    }
    if (!policy.readable_paths.has(candidate)) {
      return blocked(event, "Path is not candidate-visible for the selected case.", candidate);
    }
    if (counts.file_reads >= policy.maximum_file_reads) {
      return blocked(event, "Emergency file-read safeguard exceeded.", candidate, true);
    }
    const prior = readsByPath.get(candidate) ?? 0;
    readsByPath.set(candidate, prior + 1);
    counts.file_reads += 1;
    if (prior > 0) {
      counts.repeated_file_reads += 1;
    }
    audit("tool_allowed", { tool_name: "read", path: candidate });
    return undefined;
  });

  pi.on("tool_result", async (event) => {
    if (event.isError) {
      counts.failed_tool_calls += 1;
    }
    audit("tool_result", { tool_name: event.toolName, is_error: event.isError });
  });

  pi.on("agent_end", async () => {
    audit("agent_end", { read_paths: Object.fromEntries(readsByPath) });
  });
}
