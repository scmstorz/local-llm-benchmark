"""Preparation and integrity checks for the pinned Pi Track B harness."""

from __future__ import annotations

import json
import os
import platform
import re
import resource
import secrets
import shlex
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from .agentic import validate_local_ollama_host
from .coding import load_coding_case, verify_coding_workspace
from .macos_sandbox import (
    SEATBELT_EXECUTABLE,
    pi_sandbox_environment,
    write_pi_seatbelt_artifacts,
)
from .runner import (
    RunnerError,
    git_commit,
    load_json,
    resolve_repo_path,
    sha256_file,
    utc_now,
    write_json,
)


DEFAULT_PI_HARNESS_PATH = Path("tasks/coding/track-b/pi-v0.2.json")
PI_INTEGRATION_ROOT = Path("integrations/pi")
PI_HARNESS_PROTOCOL_IDS = {
    "pi-v0.1": "coding-track-b-v0.1",
    "pi-v0.2": "coding-track-b-v0.2",
}


@dataclass(frozen=True)
class PiAgentPrepareConfig:
    """Inputs for a no-inference pinned-Pi run preparation."""

    model: str
    case_path: Path
    harness_path: Path = DEFAULT_PI_HARNESS_PATH
    results_dir: Path = Path("results/agentic-runs")
    host: str = "http://127.0.0.1:11434"


def _relative_path(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise RunnerError(f"Expected a non-empty relative path for {context}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value != path.as_posix():
        raise RunnerError(f"Unsafe or non-normalized path for {context}: {value!r}")
    return value


def _matches_any(path: str, patterns: list[str]) -> bool:
    candidate = PurePosixPath(path)
    return any(candidate.match(pattern) for pattern in patterns)


def _package_version(binary: Path, integration_root: Path) -> str:
    try:
        completed = subprocess.run(
            [str(binary), "--version"],
            cwd=integration_root,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RunnerError(f"Cannot execute pinned Pi binary: {exc}") from exc
    if completed.returncode != 0:
        raise RunnerError(
            f"Pinned Pi version check failed: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def _node_version(integration_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["node", "--version"],
            cwd=integration_root,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RunnerError(f"Cannot determine Node.js version: {exc}") from exc
    if completed.returncode != 0:
        raise RunnerError(f"Node.js version check failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def load_pi_harness(
    repo_root: Path,
    harness_path: Path = DEFAULT_PI_HARNESS_PATH,
) -> dict[str, Any]:
    """Validate the Pi adapter, package lock and installed binary identity."""
    resolved_harness_path = resolve_repo_path(repo_root, harness_path)
    harness = load_json(resolved_harness_path)
    if harness.get("schema_version") != "1.0.0":
        raise RunnerError("Unsupported Pi harness schema version")
    harness_id = harness.get("harness_id")
    expected_protocol_id = PI_HARNESS_PROTOCOL_IDS.get(harness_id)
    if (
        expected_protocol_id is None
        or harness.get("harness_family") != "pinned_pi"
    ):
        raise RunnerError("Unexpected Pi harness identity")
    expected_harness_status = {
        "pi-v0.1": "implementation_draft",
        "pi-v0.2": "qualified_for_capability_sweep",
    }[harness_id]
    if harness.get("status") != expected_harness_status:
        raise RunnerError(
            f"Pi harness {harness_id} status must be {expected_harness_status}"
        )

    protocol_path = Path(_relative_path(harness.get("protocol_path"), "Track B protocol"))
    resolved_protocol_path = resolve_repo_path(repo_root, protocol_path)
    protocol = load_json(resolved_protocol_path)
    if protocol.get("protocol_id") != expected_protocol_id:
        raise RunnerError("Unexpected Track B protocol identity")
    expected_protocol_status = {
        "coding-track-b-v0.1": "draft_not_frozen",
        "coding-track-b-v0.2": "frozen_for_capability_sweep",
    }[expected_protocol_id]
    if protocol.get("status") != expected_protocol_status:
        raise RunnerError(
            f"Track B protocol {expected_protocol_id} status must be "
            f"{expected_protocol_status}"
        )

    system_prompt_path = Path(
        _relative_path(harness.get("system_prompt_path"), "Pi system prompt")
    )
    resolved_system_prompt_path = resolve_repo_path(repo_root, system_prompt_path)
    extension_path = Path(
        _relative_path(
            harness.get("integration", {}).get("explicit_extension"),
            "Pi policy extension",
        )
    )
    resolved_extension_path = resolve_repo_path(repo_root, extension_path)
    for path, description in (
        (resolved_system_prompt_path, "Pi system prompt"),
        (resolved_extension_path, "Pi policy extension"),
    ):
        if not path.is_file():
            raise RunnerError(f"{description} does not exist: {path}")

    integration_root = resolve_repo_path(repo_root, PI_INTEGRATION_ROOT)
    package_json_path = integration_root / "package.json"
    package_lock_path = integration_root / "package-lock.json"
    package_json = load_json(package_json_path)
    package_lock = load_json(package_lock_path)
    package = harness.get("package")
    if not isinstance(package, dict):
        raise RunnerError("Pi harness must define an exact package identity")
    name = package.get("name")
    version = package.get("version")
    if package_json.get("dependencies", {}).get(name) != version:
        raise RunnerError("Pi package.json does not use the frozen exact version")
    locked = package_lock.get("packages", {}).get(f"node_modules/{name}")
    if not isinstance(locked, dict):
        raise RunnerError("Pi package is missing from package-lock.json")
    if locked.get("version") != version:
        raise RunnerError("Pi package-lock version mismatch")
    if locked.get("integrity") != package.get("npm_integrity"):
        raise RunnerError("Pi package-lock integrity mismatch")

    binary = integration_root / "node_modules" / ".bin" / "pi"
    if not binary.exists():
        raise RunnerError(
            "Pinned Pi is not installed; run npm install --ignore-scripts in integrations/pi"
        )
    observed_version = _package_version(binary, integration_root)
    if observed_version != version:
        raise RunnerError(
            f"Installed Pi version mismatch: expected {version}, found {observed_version}"
        )

    return {
        "harness": harness,
        "harness_path": resolved_harness_path,
        "protocol": protocol,
        "protocol_path": resolved_protocol_path,
        "system_prompt": resolved_system_prompt_path.read_text(encoding="utf-8").strip(),
        "system_prompt_path": resolved_system_prompt_path,
        "extension_path": resolved_extension_path,
        "integration_root": integration_root,
        "package_json_path": package_json_path,
        "package_lock_path": package_lock_path,
        "binary": binary,
        "observed_version": observed_version,
        "node_version": _node_version(integration_root),
    }


def load_pi_track_b_case(
    repo_root: Path,
    case_path: Path,
    harness_path: Path = DEFAULT_PI_HARNESS_PATH,
) -> dict[str, Any]:
    """Bind a selected Track A fixture to the pinned Pi adapter."""
    pi = load_pi_harness(repo_root, harness_path)
    loaded = load_coding_case(repo_root, case_path)
    relative_case_path = loaded["case_path"].relative_to(repo_root).as_posix()
    selected = {
        item.get("case_path"): item
        for item in pi["protocol"].get("task_subset", [])
        if isinstance(item, dict)
    }
    if relative_case_path not in selected:
        raise RunnerError(
            f"Coding case is outside the selected Track B pilot subset: {relative_case_path}"
        )
    if selected[relative_case_path].get("case_id") != loaded["case"]["case_id"]:
        raise RunnerError("Track B task subset case identity mismatch")
    if loaded["artifact_contract"]["format"] != "whole_file_envelope":
        raise RunnerError("Pinned Pi requires a whole-file Track A base case")
    return {**loaded, **pi, "relative_case_path": relative_case_path}


def _public_test_command(loaded: dict[str, Any]) -> str:
    command = loaded["case"]["verification"]["public_test_command"]
    if any(token.startswith("{") and token.endswith("}") for token in command):
        raise RunnerError("Pi v0.1 pilot public commands must not use controller tokens")
    safe_token = re.compile(r"^[A-Za-z0-9_./:+-]+$")
    if not all(safe_token.fullmatch(token) for token in command):
        raise RunnerError("Pi public test command contains unsupported shell characters")
    return shlex.join(command)


def _pi_user_message(loaded: dict[str, Any], public_test_command: str) -> str:
    task = loaded["task_path"].read_text(encoding="utf-8").strip()
    readable = "\n".join(
        f"- {path}" for path in loaded["case"]["candidate_context"]["files"]
    )
    writable_paths = sorted(
        path
        for path in loaded["baseline_inventory"]
        if _matches_any(path, loaded["artifact_contract"]["allowed_path_globs"])
    )
    writable = "\n".join(f"- {path}" for path in writable_paths)
    return (
        f"# Task\n\n{task}\n\n"
        f"# Candidate-visible files\n\n{readable}\n\n"
        f"# Writable existing files\n\n{writable}\n\n"
        f"# Exact allowed public-test command\n\n`{public_test_command}`\n\n"
        "Hidden tests run only after the trajectory. Solve the task in this workspace."
    )


def prepare_pi_agent_run(
    repo_root: Path,
    config: PiAgentPrepareConfig,
) -> dict[str, Any]:
    """Prepare an exact Pi invocation and isolated workspace without inference."""
    host = validate_local_ollama_host(config.host)
    if not isinstance(config.model, str) or not config.model.strip():
        raise RunnerError("Track B model name must be non-empty")
    loaded = load_pi_track_b_case(repo_root, config.case_path, config.harness_path)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"pi-agentic-run-{timestamp}-{secrets.token_hex(4)}"
    results_dir = resolve_repo_path(repo_root, config.results_dir)
    run_dir = results_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    workspace = run_dir / "workspace"
    shutil.copytree(loaded["fixture_root"], workspace)
    agent_dir = run_dir / "pi-agent"
    agent_dir.mkdir()

    protocol = loaded["protocol"]
    inference = protocol["inference_defaults"]
    integration = loaded["harness"]["integration"]
    package = loaded["harness"]["package"]
    provider_base_url = host + "/v1"
    write_json(
        agent_dir / "models.json",
        {
            "providers": {
                "ollama": {
                    "baseUrl": provider_base_url,
                    "api": "openai-completions",
                    "apiKey": "ollama",
                    "compat": {
                        "supportsDeveloperRole": False,
                        "supportsReasoningEffort": False,
                    },
                    "models": [
                        {
                            "id": config.model,
                            "name": config.model,
                            "reasoning": False,
                            "input": ["text"],
                            "contextWindow": inference["num_ctx"],
                            "maxTokens": inference["num_predict_per_turn"],
                            "samplingParams": {
                                "temperature": inference["temperature"],
                                "seed": inference["seed"],
                            },
                            "cost": {
                                "input": 0,
                                "output": 0,
                                "cacheRead": 0,
                                "cacheWrite": 0,
                            },
                        }
                    ],
                }
            }
        },
    )
    write_json(
        agent_dir / "settings.json",
        {
            "defaultProvider": "ollama",
            "defaultModel": config.model,
            "enableInstallTelemetry": False,
            "enableAnalytics": False,
            "defaultProjectTrust": "never",
            "shellPath": "/bin/bash",
            "quietStartup": True,
            "compaction": {"enabled": False},
            "retry": {
                "enabled": False,
                "maxRetries": 0,
                "provider": {"maxRetries": 0},
            },
        },
    )

    public_test_command = _public_test_command(loaded)
    writable_paths = sorted(
        path
        for path in loaded["baseline_inventory"]
        if _matches_any(path, loaded["artifact_contract"]["allowed_path_globs"])
    )
    policy_path = run_dir / "pi-policy.json"
    policy = {
        "schema_version": "1.0.0",
        "workspace_root": str(workspace.resolve()),
        "audit_log_path": str((run_dir / "pi-policy-audit.jsonl").resolve()),
        "readable_paths": loaded["case"]["candidate_context"]["files"],
        "writable_paths": writable_paths,
        "public_test_command": public_test_command,
        "maximum_file_reads": protocol["budgets"]["maximum_file_reads"],
        "maximum_file_writes": protocol["budgets"]["maximum_file_writes"],
        "maximum_public_test_runs": protocol["budgets"]["maximum_public_test_runs"],
        "maximum_total_output_tokens": protocol["budgets"][
            "maximum_total_output_tokens"
        ],
        "maximum_write_bytes": loaded["artifact_contract"]["maximum_bytes"],
        "maximum_wall_time_seconds": protocol["budgets"]["maximum_wall_time_seconds"],
    }
    if "maximum_agent_turns" in protocol["budgets"]:
        policy["maximum_agent_turns"] = protocol["budgets"]["maximum_agent_turns"]
    write_json(policy_path, policy)

    user_message = _pi_user_message(loaded, public_test_command)
    invocation = {
        "schema_version": "1.0.0",
        "cwd": str(workspace.resolve()),
        "executable": str(loaded["binary"].resolve()),
        "argv": [
            "--mode",
            "json",
            "--print",
            "--provider",
            integration["provider"],
            "--model",
            config.model,
            "--api-key",
            "ollama",
            "--thinking",
            "off",
            "--tools",
            ",".join(integration["tools"]),
            "--no-session",
            "--no-extensions",
            "--extension",
            str(loaded["extension_path"].resolve()),
            "--no-skills",
            "--no-prompt-templates",
            "--no-themes",
            "--no-context-files",
            "--no-approve",
            "--offline",
            "--system-prompt",
            loaded["system_prompt"],
            "--",
            user_message,
        ],
        "environment": {
            "PI_CODING_AGENT_DIR": str(agent_dir.resolve()),
            "PI_OFFLINE": "1",
            "PI_SKIP_VERSION_CHECK": "1",
            "PI_TELEMETRY": "0",
            "LOCAL_LLM_BENCHMARK_POLICY_PATH": str(policy_path.resolve()),
        },
        "stdout_path": str((run_dir / "pi-events.jsonl").resolve()),
        "stderr_path": str((run_dir / "pi-stderr.txt").resolve()),
        "timeout_seconds": protocol["budgets"]["maximum_wall_time_seconds"],
        "requires_os_sandbox": True,
    }
    invocation_path = run_dir / "pi-invocation.json"
    write_json(invocation_path, invocation)
    sandbox = write_pi_seatbelt_artifacts(
        repo_root,
        run_dir,
        invocation,
        load_json(policy_path),
    )

    record = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "track": "B",
        "state": "prepared_not_executed",
        "prepared_at": utc_now(),
        "harness": {
            "harness_id": loaded["harness"]["harness_id"],
            "harness_family": loaded["harness"]["harness_family"],
            "harness_status": loaded["harness"]["status"],
            "harness_path": loaded["harness_path"].relative_to(repo_root).as_posix(),
            "harness_sha256": sha256_file(loaded["harness_path"]),
            "protocol_path": loaded["protocol_path"].relative_to(repo_root).as_posix(),
            "protocol_sha256": sha256_file(loaded["protocol_path"]),
            "system_prompt_sha256": sha256_file(loaded["system_prompt_path"]),
            "extension_sha256": sha256_file(loaded["extension_path"]),
            "package_name": package["name"],
            "package_version": package["version"],
            "package_integrity": package["npm_integrity"],
            "package_lock_sha256": sha256_file(loaded["package_lock_path"]),
            "git_commit": git_commit(repo_root),
        },
        "case": {
            "case_id": loaded["case"]["case_id"],
            "case_version": loaded["case"]["case_version"],
            "case_path": loaded["relative_case_path"],
            "case_definition_sha256": sha256_file(loaded["case_path"]),
            "task_family": loaded["case"]["task_family"],
            "fixture_manifest_sha256": loaded["manifest_sha256"],
            "task_sha256": loaded["task_sha256"],
            "benchmark_card_sha256": sha256_file(loaded["card_path"]),
            "verifier_version": loaded["case"]["verification"]["version"],
            "hidden_test_sha256": loaded["hidden_test_sha256"],
            "candidate_visible_files": loaded["case"]["candidate_context"]["files"],
            "writable_files": writable_paths,
            "public_test_command": public_test_command,
        },
        "deployment": {
            "requested_model": config.model,
            "ollama_base_url": provider_base_url,
            "options": inference,
        },
        "execution_boundary": {
            "inference_requests_made": 0,
            "candidate_code_executed": False,
            "requires_os_sandbox": True,
            "live_execution_implemented": False,
            "sandbox_backend": sandbox["backend"],
            "sandbox_profile_sha256": sandbox["profile_sha256"],
            "sandbox_acceptance_passed": False,
        },
        "environment": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "node_version": loaded["node_version"],
        },
        "artifacts": {
            "workspace": "workspace",
            "pi_agent_dir": "pi-agent",
            "policy": "pi-policy.json",
            "invocation": "pi-invocation.json",
            "sandbox_profile": "pi-sandbox.sb",
            "sandbox_metadata": "pi-sandbox.json",
            "prepared_sha256": {
                "invocation": sha256_file(invocation_path),
                "policy": sha256_file(policy_path),
                "sandbox_profile": sandbox["profile_sha256"],
                "sandbox_metadata": sha256_file(run_dir / "pi-sandbox.json"),
            },
        },
    }
    write_json(run_dir / "run.json", record)
    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "state": record["state"],
        "model": config.model,
        "case_id": loaded["case"]["case_id"],
        "pi_version": loaded["observed_version"],
        "inference_requests_made": 0,
        "candidate_code_executed": False,
        "next_requirement": "Select and validate an OS sandbox before live Pi execution.",
    }


def _load_json_lines(path: Path) -> tuple[list[dict[str, Any]], int]:
    events: list[dict[str, Any]] = []
    malformed = 0
    if not path.exists():
        return events, malformed
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(event, dict):
            events.append(event)
        else:
            malformed += 1
    return events, malformed


def _last_audit_counts(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    events, malformed = _load_json_lines(path)
    counts: dict[str, Any] = {}
    for event in events:
        observed = event.get("counts")
        if isinstance(observed, dict):
            counts = observed
    return counts, events, malformed


def _require_hash(path: Path, expected: str, description: str) -> None:
    if not path.is_file() or sha256_file(path) != expected:
        raise RunnerError(f"Prepared Pi {description} hash mismatch")


def _load_prepared_pi_run(
    repo_root: Path,
    run_dir: Path,
    *,
    allowed_states: set[str],
) -> dict[str, Any]:
    resolved_run = resolve_repo_path(repo_root, run_dir)
    record_path = resolved_run / "run.json"
    record = load_json(record_path)
    if record.get("state") not in allowed_states:
        raise RunnerError(
            f"Pi run state must be one of {sorted(allowed_states)}, found {record.get('state')!r}"
        )
    case_path = Path(record["case"]["case_path"])
    harness_path = Path(record["harness"]["harness_path"])
    loaded = load_pi_track_b_case(repo_root, case_path, harness_path)
    expected_hashes = {
        loaded["harness_path"]: record["harness"]["harness_sha256"],
        loaded["protocol_path"]: record["harness"]["protocol_sha256"],
        loaded["system_prompt_path"]: record["harness"]["system_prompt_sha256"],
        loaded["extension_path"]: record["harness"]["extension_sha256"],
        loaded["package_lock_path"]: record["harness"]["package_lock_sha256"],
        loaded["case_path"]: record["case"]["case_definition_sha256"],
        loaded["card_path"]: record["case"]["benchmark_card_sha256"],
    }
    for path, expected in expected_hashes.items():
        _require_hash(path, expected, path.name)
    if loaded["manifest_sha256"] != record["case"]["fixture_manifest_sha256"]:
        raise RunnerError("Prepared Pi fixture manifest hash mismatch")
    if loaded["task_sha256"] != record["case"]["task_sha256"]:
        raise RunnerError("Prepared Pi task hash mismatch")
    if loaded["hidden_test_sha256"] != record["case"]["hidden_test_sha256"]:
        raise RunnerError("Prepared Pi hidden verifier hash mismatch")

    artifacts = record["artifacts"]
    invocation_path = resolved_run / artifacts["invocation"]
    policy_path = resolved_run / artifacts["policy"]
    sandbox_path = resolved_run / artifacts["sandbox_metadata"]
    profile_path = resolved_run / artifacts["sandbox_profile"]
    prepared_hashes = artifacts["prepared_sha256"]
    for path, key in (
        (invocation_path, "invocation"),
        (policy_path, "policy"),
        (sandbox_path, "sandbox_metadata"),
        (profile_path, "sandbox_profile"),
    ):
        _require_hash(path, prepared_hashes[key], key)
    invocation = load_json(invocation_path)
    policy = load_json(policy_path)
    sandbox = load_json(sandbox_path)
    if sandbox["profile_sha256"] != prepared_hashes["sandbox_profile"]:
        raise RunnerError("Prepared Pi sandbox metadata/profile mismatch")

    return {
        **loaded,
        "run_dir": resolved_run,
        "record_path": record_path,
        "record": record,
        "invocation": invocation,
        "policy": policy,
        "sandbox": sandbox,
        "profile_path": profile_path,
    }


def _pi_resource_limits(timeout_seconds: int) -> Any:
    def apply_limits() -> None:
        def lower_soft_limit(resource_name: int, requested: int) -> None:
            _current_soft, current_hard = resource.getrlimit(resource_name)
            target = (
                requested
                if current_hard == resource.RLIM_INFINITY
                else min(requested, current_hard)
            )
            resource.setrlimit(resource_name, (target, current_hard))

        cpu_limit = max(60, timeout_seconds + 30)
        lower_soft_limit(resource.RLIMIT_CPU, cpu_limit)
        lower_soft_limit(resource.RLIMIT_FSIZE, 64 * 1024 * 1024)
        lower_soft_limit(resource.RLIMIT_NOFILE, 256)

    return apply_limits


def _summarize_pi_trajectory(
    events_path: Path,
    audit_path: Path,
    wall_time_seconds: float,
) -> dict[str, Any]:
    events, malformed_events = _load_json_lines(events_path)
    counts, audit_events, malformed_audit = _last_audit_counts(audit_path)
    event_types: dict[str, int] = {}
    agent_end_events: list[dict[str, Any]] = []
    for event in events:
        event_type = str(event.get("type", "unknown"))
        event_types[event_type] = event_types.get(event_type, 0) + 1
        if event_type == "agent_end":
            agent_end_events.append(event)
    first_public = None
    for event in audit_events:
        if event.get("kind") == "first_successful_public_verification":
            first_public = event.get("elapsed_seconds")
            break
    final_stop_reason = None
    agent_end_will_retry = None
    if agent_end_events:
        final_agent_end = agent_end_events[-1]
        agent_end_will_retry = final_agent_end.get("willRetry")
        messages = final_agent_end.get("messages")
        if isinstance(messages, list):
            for message in reversed(messages):
                if isinstance(message, dict) and message.get("role") == "assistant":
                    final_stop_reason = message.get("stopReason")
                    break
    agent_end_valid = (
        bool(agent_end_events)
        and agent_end_will_retry is False
        and final_stop_reason not in {None, "error", "aborted"}
    )
    return {
        "agent_turns": counts.get("agent_turns", event_types.get("turn_start", 0)),
        "tool_calls": counts.get("tool_calls", event_types.get("tool_execution_start", 0)),
        "failed_tool_calls": counts.get("failed_tool_calls", 0),
        "protocol_errors": 0,
        "file_reads": counts.get("file_reads", 0),
        "file_writes": counts.get("file_writes", 0),
        "public_test_runs": counts.get("public_test_runs", 0),
        "input_tokens": counts.get("input_tokens", 0),
        "output_tokens": counts.get("output_tokens", 0),
        "active_wall_time_seconds": wall_time_seconds,
        "time_to_first_successful_public_verification_seconds": first_public,
        "retry_events": event_types.get("auto_retry_start", 0),
        "event_type_counts": event_types,
        "malformed_event_lines": malformed_events,
        "malformed_audit_lines": malformed_audit,
        "agent_end_observed": event_types.get("agent_end", 0) > 0,
        "agent_end_will_retry": agent_end_will_retry,
        "final_assistant_stop_reason": final_stop_reason,
        "agent_end_valid": agent_end_valid,
    }


def execute_pi_agent_run(repo_root: Path, run_dir: Path) -> dict[str, Any]:
    """Run pinned Pi inside accepted Seatbelt, leaving hidden verification pending."""
    loaded = _load_prepared_pi_run(
        repo_root, run_dir, allowed_states={"prepared_not_executed"}
    )
    resolved_run = loaded["run_dir"]
    acceptance_path = resolved_run / "pi-sandbox-acceptance.json"
    acceptance = load_json(acceptance_path)
    record = loaded["record"]
    boundary = record["execution_boundary"]
    if not acceptance.get("passed") or not boundary.get("sandbox_acceptance_passed"):
        raise RunnerError("Pi live execution requires a passing sandbox acceptance")
    _require_hash(
        acceptance_path,
        boundary["sandbox_acceptance_sha256"],
        "sandbox acceptance",
    )
    if acceptance.get("profile_sha256") != loaded["sandbox"]["profile_sha256"]:
        raise RunnerError("Pi sandbox acceptance belongs to a different profile")

    invocation = loaded["invocation"]
    sandbox = loaded["sandbox"]
    events_path = Path(invocation["stdout_path"])
    stderr_path = Path(invocation["stderr_path"])
    audit_path = Path(loaded["policy"]["audit_log_path"])
    for path in (events_path, stderr_path):
        if path.exists() and path.stat().st_size:
            raise RunnerError(f"Prepared Pi output is unexpectedly non-empty: {path.name}")
    if audit_path.stat().st_size:
        raise RunnerError("Prepared Pi policy audit is unexpectedly non-empty")

    command = [
        str(SEATBELT_EXECUTABLE),
        "-f",
        str(loaded["profile_path"]),
        sandbox["node_binary"],
        invocation["executable"],
        *invocation["argv"],
    ]
    environment = pi_sandbox_environment(sandbox, invocation)
    timeout_seconds = int(invocation["timeout_seconds"])
    record["state"] = "running"
    record["execution"] = {
        "started_at": utc_now(),
        "command_shape": "sandbox-exec -f PROFILE NODE PINNED_PI_ENTRYPOINT ARGS",
        "timeout_seconds": timeout_seconds,
    }
    write_json(loaded["record_path"], record)

    started = time.monotonic()
    timed_out = False
    returncode: int | None = None
    launch_error: str | None = None
    with events_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr_handle:
        try:
            process = subprocess.Popen(
                command,
                cwd=invocation["cwd"],
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=True,
                preexec_fn=_pi_resource_limits(timeout_seconds),
            )
            try:
                returncode = process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    returncode = process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    returncode = process.wait(timeout=5)
        except (OSError, subprocess.SubprocessError) as exc:
            launch_error = f"{type(exc).__name__}: {exc}"
    wall_time_seconds = time.monotonic() - started
    trajectory = _summarize_pi_trajectory(events_path, audit_path, wall_time_seconds)
    runtime_success = (
        launch_error is None
        and not timed_out
        and returncode == 0
        and trajectory["malformed_event_lines"] == 0
        and trajectory["malformed_audit_lines"] == 0
    )
    agent_termination_valid = runtime_success and trajectory["agent_end_valid"]
    if timed_out:
        termination_reason = "maximum_wall_time_exceeded"
    elif launch_error:
        termination_reason = "runtime_launch_failure"
    elif returncode != 0:
        termination_reason = "runtime_exit_nonzero"
    elif trajectory["malformed_event_lines"] or trajectory["malformed_audit_lines"]:
        termination_reason = "malformed_trajectory"
    elif not trajectory["agent_end_observed"]:
        termination_reason = "missing_agent_end"
    elif not trajectory["agent_end_valid"]:
        termination_reason = "invalid_agent_end"
    else:
        termination_reason = "agent_end"
    trajectory["termination_reason"] = termination_reason

    record = load_json(loaded["record_path"])
    record["state"] = "execution_complete_verification_pending"
    record["execution"].update(
        {
            "finished_at": utc_now(),
            "returncode": returncode,
            "timed_out": timed_out,
            "launch_error": launch_error,
            "runtime_success": runtime_success,
            "agent_termination_valid": agent_termination_valid,
            "wall_time_seconds": wall_time_seconds,
        }
    )
    record["trajectory"] = trajectory
    record["execution_boundary"].update(
        {
            "inference_requests_made": trajectory["agent_turns"],
            "candidate_code_executed": trajectory["public_test_runs"] > 0,
            "live_execution_implemented": True,
            "hidden_verification_executed": False,
        }
    )
    record["artifacts"]["execution_sha256"] = {
        "events": sha256_file(events_path),
        "stderr": sha256_file(stderr_path),
        "policy_audit": sha256_file(audit_path),
    }
    write_json(loaded["record_path"], record)
    return {
        "run_id": record["run_id"],
        "state": record["state"],
        "runtime_success": runtime_success,
        "agent_termination_valid": agent_termination_valid,
        "termination_reason": termination_reason,
        "trajectory": trajectory,
        "hidden_verification_executed": False,
        "next_action": "coding-agent-pi-finalize",
    }


def finalize_pi_agent_run(repo_root: Path, run_dir: Path) -> dict[str, Any]:
    """Run the separate final verifier after Pi no longer has model access."""
    loaded = _load_prepared_pi_run(
        repo_root,
        run_dir,
        allowed_states={"execution_complete_verification_pending"},
    )
    record = loaded["record"]
    for artifact, expected in record["artifacts"]["execution_sha256"].items():
        filename = {
            "events": "pi-events.jsonl",
            "stderr": "pi-stderr.txt",
            "policy_audit": "pi-policy-audit.jsonl",
        }[artifact]
        _require_hash(loaded["run_dir"] / filename, expected, filename)
    verification = verify_coding_workspace(
        repo_root,
        Path(record["case"]["case_path"]),
        loaded["run_dir"] / record["artifacts"]["workspace"],
    )
    verification_path = loaded["run_dir"] / "final-verification.json"
    write_json(verification_path, verification)
    runtime_success = bool(record["execution"]["runtime_success"])
    agent_termination_valid = bool(record["execution"]["agent_termination_valid"])
    verifier_success = bool(verification["verified_success"])
    verified_success = runtime_success and agent_termination_valid and verifier_success
    if not runtime_success:
        failure_category = "infrastructure_or_runtime_failure"
        failure_type = record["trajectory"]["termination_reason"]
    elif not agent_termination_valid:
        failure_category = "agent_failure"
        failure_type = record["trajectory"]["termination_reason"]
    elif not verifier_success:
        failure_category = "task_or_verification_failure"
        failure_type = verification.get("failure_code", "verification_failed")
    else:
        failure_category = None
        failure_type = None
    record["state"] = "complete"
    record["completed_at"] = utc_now()
    record["outcome"] = {
        "runtime_success": runtime_success,
        "agent_termination_valid": agent_termination_valid,
        "verifier_success": verifier_success,
        "verified_success": verified_success,
        "failure_category": failure_category,
        "failure_type": failure_type,
    }
    record["verification"] = verification
    record["execution_boundary"].update(
        {
            "candidate_code_executed": bool(
                record["execution_boundary"]["candidate_code_executed"]
                or verification.get("tests") is not None
            ),
            "hidden_verification_executed": True,
        }
    )
    record["artifacts"]["final_verification"] = "final-verification.json"
    record["artifacts"]["final_verification_sha256"] = sha256_file(verification_path)
    write_json(loaded["record_path"], record)
    return {
        "run_id": record["run_id"],
        "state": record["state"],
        **record["outcome"],
        "public_tests": (verification.get("tests") or {}).get("public"),
        "hidden_tests": (verification.get("tests") or {}).get("hidden"),
    }
