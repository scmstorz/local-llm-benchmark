/** Candidate policy for Pi v0.3: enforce scope, record effort, let parent time bound capability. */

import { appendFileSync, lstatSync, readFileSync } from "node:fs";
import { isAbsolute, relative, resolve, sep } from "node:path";
import { performance } from "node:perf_hooks";


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
  if (policy.schema_version !== "1.1.0") {
    throw new Error("Unsupported benchmark policy schema version");
  }
  if (!isAbsolute(policy.workspace_root)) {
    throw new Error("workspace_root must be absolute");
  }
  if (!isAbsolute(policy.audit_log_path)) {
    throw new Error("audit_log_path must be absolute");
  }
  if (!Array.isArray(policy.readable_paths) || !Array.isArray(policy.writable_paths)) {
    throw new Error("Policy paths must be arrays");
  }
  if (typeof policy.public_test_command !== "string" || !policy.public_test_command) {
    throw new Error("public_test_command must be a non-empty string");
  }
  if (policy.maximum_agent_turns !== undefined) {
    throw new Error("Pi v0.3 does not accept a normal agent-turn limit");
  }
  if (policy.maximum_total_output_tokens !== undefined) {
    throw new Error("Pi v0.3 records total output tokens but does not enforce them");
  }
  if (policy.maximum_wall_time_seconds !== undefined) {
    throw new Error("Pi v0.3 delegates the normal wall-time limit to the parent process");
  }
  requirePositiveInteger(
    policy.parent_maximum_active_wall_time_seconds,
    "parent_maximum_active_wall_time_seconds",
  );
  requirePositiveInteger(policy.maximum_file_reads, "maximum_file_reads");
  requirePositiveInteger(policy.maximum_file_writes, "maximum_file_writes");
  requirePositiveInteger(policy.maximum_public_test_runs, "maximum_public_test_runs");
  requirePositiveInteger(policy.maximum_write_bytes, "maximum_write_bytes");
  return {
    ...policy,
    workspace_root: resolve(policy.workspace_root),
    readable_paths: new Set(policy.readable_paths),
    writable_paths: new Set(policy.writable_paths),
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


function compactInput(event, candidate) {
  if (event.toolName === "bash") {
    return { command: event.input.command };
  }
  if (event.toolName === "edit") {
    return { path: candidate, edit_count: Array.isArray(event.input.edits) ? event.input.edits.length : null };
  }
  if (event.toolName === "write") {
    return {
      path: candidate,
      content_bytes: typeof event.input.content === "string" ? Buffer.byteLength(event.input.content, "utf8") : null,
    };
  }
  return { path: candidate };
}


export default function benchmarkPolicyExtension(pi) {
  const policy = loadPolicy(process.env.LOCAL_LLM_BENCHMARK_POLICY_PATH);
  const startedAt = performance.now();
  const counts = {
    agent_turns: 0,
    tool_calls: 0,
    failed_tool_calls: 0,
    file_reads: 0,
    file_writes: 0,
    public_test_runs: 0,
    input_tokens: 0,
    output_tokens: 0,
  };
  let firstSuccessfulPublicVerificationSeconds = null;

  function elapsedSeconds() {
    return (performance.now() - startedAt) / 1000;
  }

  function audit(kind, detail = {}) {
    appendFileSync(
      policy.audit_log_path,
      `${JSON.stringify({ timestamp: new Date().toISOString(), kind, counts: { ...counts }, ...detail })}\n`,
      "utf8",
    );
  }

  function blocked(event, reason, candidate = null, terminate = false) {
    counts.failed_tool_calls += 1;
    audit("tool_blocked", {
      tool_name: event.toolName,
      input: compactInput(event, candidate),
      reason,
      terminate,
    });
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
    if (!["read", "write", "edit", "bash"].includes(event.toolName)) {
      return blocked(event, `Tool ${event.toolName} is outside the benchmark allowlist.`, null, true);
    }

    if (event.toolName === "bash") {
      if (counts.public_test_runs >= policy.maximum_public_test_runs) {
        return blocked(event, "Emergency public-test safeguard exceeded.", null, true);
      }
      if (event.input.command !== policy.public_test_command) {
        return blocked(event, "Only the exact frozen public-test command is allowed.");
      }
      counts.public_test_runs += 1;
      audit("tool_allowed", { tool_name: event.toolName, input: compactInput(event, null) });
      return undefined;
    }

    const candidate = relativeWorkspacePath(policy.workspace_root, event.input.path);
    if (!candidate || !isExistingRegularFile(policy.workspace_root, candidate)) {
      return blocked(event, "Path is outside the workspace or is not an existing regular file.", candidate);
    }
    if (event.toolName === "read") {
      if (counts.file_reads >= policy.maximum_file_reads) {
        return blocked(event, "Emergency file-read safeguard exceeded.", candidate, true);
      }
      if (!policy.readable_paths.has(candidate)) {
        return blocked(event, "Path is not candidate-visible.", candidate);
      }
      counts.file_reads += 1;
      audit("tool_allowed", { tool_name: event.toolName, input: compactInput(event, candidate) });
      return undefined;
    }

    if (counts.file_writes >= policy.maximum_file_writes) {
      return blocked(event, "Emergency file-write safeguard exceeded.", candidate, true);
    }
    if (!policy.writable_paths.has(candidate)) {
      return blocked(event, "Path is outside the writable scope.", candidate);
    }
    if (
      event.toolName === "write"
      && (typeof event.input.content !== "string"
        || Buffer.byteLength(event.input.content, "utf8") > policy.maximum_write_bytes)
    ) {
      return blocked(event, "Write content exceeds the byte limit.", candidate);
    }
    if (event.toolName === "edit") {
      if (!Array.isArray(event.input.edits) || event.input.edits.length < 1) {
        return blocked(event, "Edit must contain at least one replacement.", candidate);
      }
      const oversized = event.input.edits.some(
        (edit) => typeof edit.newText !== "string"
          || Buffer.byteLength(edit.newText, "utf8") > policy.maximum_write_bytes,
      );
      if (oversized) {
        return blocked(event, "Edit replacement exceeds the byte limit.", candidate);
      }
    }
    counts.file_writes += 1;
    audit("tool_allowed", { tool_name: event.toolName, input: compactInput(event, candidate) });
    return undefined;
  });

  pi.on("tool_result", async (event) => {
    if (event.isError) {
      counts.failed_tool_calls += 1;
    }
    if (
      event.toolName === "bash"
      && !event.isError
      && firstSuccessfulPublicVerificationSeconds === null
    ) {
      firstSuccessfulPublicVerificationSeconds = elapsedSeconds();
      audit("first_successful_public_verification", {
        elapsed_seconds: firstSuccessfulPublicVerificationSeconds,
      });
    }
    audit("tool_result", {
      tool_name: event.toolName,
      is_error: event.isError,
    });
    return undefined;
  });

  pi.on("agent_end", async () => {
    audit("agent_end", { elapsed_seconds: elapsedSeconds() });
  });
}
