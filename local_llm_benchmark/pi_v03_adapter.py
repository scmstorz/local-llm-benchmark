"""Live adapter for the time-first pinned Pi v0.3 Track B harness."""

from __future__ import annotations

import argparse
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
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from .agentic import validate_local_ollama_host
from .coding import load_coding_case, verify_coding_workspace
from .macos_sandbox import SEATBELT_EXECUTABLE, pi_sandbox_environment
from .macos_sandbox_v03 import (
    validate_pi_v03_seatbelt,
    write_pi_v03_seatbelt_artifacts,
)
from .pi_v03_config import (
    PI_V03_HARNESS_PATH,
    build_pi_v03_policy,
    build_pi_v03_settings,
    load_pi_v03_candidate,
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


PI_INTEGRATION_ROOT = Path("integrations/pi")


@dataclass(frozen=True)
class PiV03PrepareConfig:
    """Inputs for a no-inference Pi v0.3 preparation."""

    model: str
    case_path: Path
    harness_path: Path = PI_V03_HARNESS_PATH
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


def load_pi_v03_harness(
    repo_root: Path,
    harness_path: Path = PI_V03_HARNESS_PATH,
) -> dict[str, Any]:
    """Validate the qualified v0.3 config and exact installed Pi package."""
    loaded = load_pi_v03_candidate(repo_root, harness_path)
    harness = loaded["harness"]
    integration_root = resolve_repo_path(repo_root, PI_INTEGRATION_ROOT)
    package_json_path = integration_root / "package.json"
    package_lock_path = integration_root / "package-lock.json"
    package_json = load_json(package_json_path)
    package_lock = load_json(package_lock_path)
    package = harness.get("package")
    if not isinstance(package, dict):
        raise RunnerError("Pi v0.3 must define an exact package identity")
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
        **loaded,
        "integration_root": integration_root,
        "package_json_path": package_json_path,
        "package_lock_path": package_lock_path,
        "binary": binary,
        "observed_version": observed_version,
        "node_version": _node_version(integration_root),
        "system_prompt": loaded["system_prompt_path"]
        .read_text(encoding="utf-8")
        .strip(),
    }


def load_pi_v03_track_b_case(
    repo_root: Path,
    case_path: Path,
    harness_path: Path = PI_V03_HARNESS_PATH,
) -> dict[str, Any]:
    """Bind one qualified PHP, JavaScript or Python task to Pi v0.3."""
    pi = load_pi_v03_harness(repo_root, harness_path)
    loaded = load_coding_case(repo_root, case_path)
    relative_case_path = loaded["case_path"].relative_to(repo_root).as_posix()
    selected = {
        item.get("case_path"): item
        for item in pi["protocol"].get("task_subset", [])
        if isinstance(item, dict)
    }
    if relative_case_path not in selected:
        raise RunnerError(
            f"Coding case is outside the Pi v0.3 task subset: {relative_case_path}"
        )
    if selected[relative_case_path].get("case_id") != loaded["case"]["case_id"]:
        raise RunnerError("Pi v0.3 task subset case identity mismatch")
    if loaded["artifact_contract"]["format"] != "whole_file_envelope":
        raise RunnerError("Pi v0.3 requires a whole-file Track A base case")
    return {**loaded, **pi, "relative_case_path": relative_case_path}


def _public_test_command(loaded: dict[str, Any]) -> str:
    declared = loaded["case"]["verification"]["public_test_command"]
    command: list[str] = []
    for token in declared:
        if token == "{python}":
            command.append(str(Path(sys.executable).resolve()))
        elif token == "php":
            direct_php = next(
                (
                    candidate.resolve()
                    for candidate in (
                        Path("/usr/local/bin/default-php"),
                        Path("/usr/local/bin/php8.4"),
                        Path("/opt/homebrew/bin/php8.4"),
                    )
                    if candidate.is_file() and os.access(candidate, os.X_OK)
                ),
                None,
            )
            if direct_php is None:
                raise RunnerError(
                    "Pi v0.3 requires a direct PHP executable, not a runtime-selection wrapper"
                )
            command.append(str(direct_php))
        elif token.startswith("{") and token.endswith("}"):
            raise RunnerError(
                f"Pi v0.3 public commands do not support controller token {token!r}"
            )
        else:
            command.append(token)
    safe_token = re.compile(r"^[A-Za-z0-9_./:@+-]+$")
    if not all(safe_token.fullmatch(token) for token in command):
        raise RunnerError("Pi v0.3 public test command contains unsafe characters")
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


def prepare_pi_v03_agent_run(
    repo_root: Path,
    config: PiV03PrepareConfig,
) -> dict[str, Any]:
    """Prepare an exact Pi v0.3 invocation without inference or candidate execution."""
    host = validate_local_ollama_host(config.host)
    if not isinstance(config.model, str) or not config.model.strip():
        raise RunnerError("Track B model name must be non-empty")
    loaded = load_pi_v03_track_b_case(
        repo_root, config.case_path, config.harness_path
    )
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"pi-v03-agentic-run-{timestamp}-{secrets.token_hex(4)}"
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
    settings = build_pi_v03_settings(config.model, protocol)
    write_json(agent_dir / "settings.json", settings)

    public_test_command = _public_test_command(loaded)
    writable_paths = sorted(
        path
        for path in loaded["baseline_inventory"]
        if _matches_any(path, loaded["artifact_contract"]["allowed_path_globs"])
    )
    policy_path = run_dir / "pi-policy.json"
    policy = build_pi_v03_policy(
        protocol,
        workspace_root=workspace,
        audit_log_path=run_dir / "pi-policy-audit.jsonl",
        readable_paths=loaded["case"]["candidate_context"]["files"],
        writable_paths=writable_paths,
        public_test_command=public_test_command,
        maximum_write_bytes=loaded["artifact_contract"]["maximum_bytes"],
    )
    write_json(policy_path, policy)
    timeout_seconds = protocol["normal_capability_limits"][
        "maximum_active_wall_time_seconds"
    ]

    user_message = _pi_user_message(loaded, public_test_command)
    invocation = {
        "schema_version": "1.1.0",
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
        "timeout_seconds": timeout_seconds,
        "timeout_clock": "parent_process_monotonic_wait",
        "requires_os_sandbox": True,
    }
    invocation_path = run_dir / "pi-invocation.json"
    write_json(invocation_path, invocation)
    sandbox = write_pi_v03_seatbelt_artifacts(
        repo_root, run_dir, invocation, policy
    )

    record = {
        "schema_version": "1.1.0",
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
            "adapter_path": "local_llm_benchmark/pi_v03_adapter.py",
            "adapter_sha256": sha256_file(
                repo_root / "local_llm_benchmark/pi_v03_adapter.py"
            ),
            "configuration_builder_path": "local_llm_benchmark/pi_v03_config.py",
            "configuration_builder_sha256": sha256_file(
                repo_root / "local_llm_benchmark/pi_v03_config.py"
            ),
            "sandbox_adapter_path": "local_llm_benchmark/macos_sandbox_v03.py",
            "sandbox_adapter_sha256": sha256_file(
                repo_root / "local_llm_benchmark/macos_sandbox_v03.py"
            ),
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
        "capability_budget": {
            "primary_limit": "active_wall_time_seconds",
            "maximum_active_wall_time_seconds": timeout_seconds,
            "provider_request_timeout_seconds": inference[
                "request_timeout_seconds"
            ],
            "agent_turns": "measurement_only",
            "total_output_tokens": "measurement_only",
            "emergency_operation_safeguards": {
                "maximum_file_reads": policy["maximum_file_reads"],
                "maximum_file_writes": policy["maximum_file_writes"],
                "maximum_public_test_runs": policy["maximum_public_test_runs"],
            },
        },
        "execution_boundary": {
            "inference_requests_made": 0,
            "candidate_code_executed": False,
            "requires_os_sandbox": True,
            "live_execution_implemented": True,
            "sandbox_backend": sandbox["backend"],
            "sandbox_profile_sha256": sandbox["profile_sha256"],
            "sandbox_acceptance_passed": False,
        },
        "environment": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "python_executable": str(Path(sys.executable).resolve()),
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
                "settings": sha256_file(agent_dir / "settings.json"),
                "models": sha256_file(agent_dir / "models.json"),
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
        "next_requirement": "Run the no-inference Pi v0.3 Seatbelt acceptance.",
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
        raise RunnerError(f"Prepared Pi v0.3 {description} hash mismatch")


def _load_prepared_pi_v03_run(
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
            f"Pi v0.3 run state must be one of {sorted(allowed_states)}, "
            f"found {record.get('state')!r}"
        )
    loaded = load_pi_v03_track_b_case(
        repo_root,
        Path(record["case"]["case_path"]),
        Path(record["harness"]["harness_path"]),
    )
    expected_hashes = {
        loaded["harness_path"]: record["harness"]["harness_sha256"],
        loaded["protocol_path"]: record["harness"]["protocol_sha256"],
        loaded["system_prompt_path"]: record["harness"]["system_prompt_sha256"],
        loaded["extension_path"]: record["harness"]["extension_sha256"],
        loaded["package_lock_path"]: record["harness"]["package_lock_sha256"],
        loaded["case_path"]: record["case"]["case_definition_sha256"],
        loaded["card_path"]: record["case"]["benchmark_card_sha256"],
        resolve_repo_path(
            repo_root, Path(record["harness"]["adapter_path"])
        ): record["harness"]["adapter_sha256"],
        resolve_repo_path(
            repo_root, Path(record["harness"]["configuration_builder_path"])
        ): record["harness"]["configuration_builder_sha256"],
        resolve_repo_path(
            repo_root, Path(record["harness"]["sandbox_adapter_path"])
        ): record["harness"]["sandbox_adapter_sha256"],
    }
    for path, expected in expected_hashes.items():
        _require_hash(path, expected, path.name)
    if loaded["manifest_sha256"] != record["case"]["fixture_manifest_sha256"]:
        raise RunnerError("Prepared Pi v0.3 fixture manifest hash mismatch")
    if loaded["task_sha256"] != record["case"]["task_sha256"]:
        raise RunnerError("Prepared Pi v0.3 task hash mismatch")
    if loaded["hidden_test_sha256"] != record["case"]["hidden_test_sha256"]:
        raise RunnerError("Prepared Pi v0.3 hidden verifier hash mismatch")

    artifacts = record["artifacts"]
    artifact_paths = {
        "invocation": resolved_run / artifacts["invocation"],
        "policy": resolved_run / artifacts["policy"],
        "sandbox_metadata": resolved_run / artifacts["sandbox_metadata"],
        "sandbox_profile": resolved_run / artifacts["sandbox_profile"],
        "settings": resolved_run / artifacts["pi_agent_dir"] / "settings.json",
        "models": resolved_run / artifacts["pi_agent_dir"] / "models.json",
    }
    for key, path in artifact_paths.items():
        _require_hash(path, artifacts["prepared_sha256"][key], key)
    invocation = load_json(artifact_paths["invocation"])
    policy = load_json(artifact_paths["policy"])
    sandbox = load_json(artifact_paths["sandbox_metadata"])
    if sandbox["profile_sha256"] != artifacts["prepared_sha256"]["sandbox_profile"]:
        raise RunnerError("Prepared Pi v0.3 sandbox metadata/profile mismatch")
    return {
        **loaded,
        "run_dir": resolved_run,
        "record_path": record_path,
        "record": record,
        "invocation": invocation,
        "policy": policy,
        "sandbox": sandbox,
        "profile_path": artifact_paths["sandbox_profile"],
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

        lower_soft_limit(resource.RLIMIT_CPU, max(60, timeout_seconds + 30))
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
    first_public = next(
        (
            event.get("elapsed_seconds")
            for event in audit_events
            if event.get("kind") == "first_successful_public_verification"
        ),
        None,
    )
    emergency_events = [
        event
        for event in audit_events
        if event.get("kind") == "tool_blocked"
        and event.get("terminate") is True
        and str(event.get("reason", "")).startswith("Emergency ")
    ]
    final_stop_reason = None
    final_error_message = None
    agent_end_will_retry = None
    if agent_end_events:
        final_agent_end = agent_end_events[-1]
        agent_end_will_retry = final_agent_end.get("willRetry")
        messages = final_agent_end.get("messages")
        if isinstance(messages, list):
            for message in reversed(messages):
                if isinstance(message, dict) and message.get("role") == "assistant":
                    final_stop_reason = message.get("stopReason")
                    final_error_message = message.get("errorMessage")
                    break
    provider_request_timed_out = (
        final_stop_reason == "error"
        and isinstance(final_error_message, str)
        and re.search(
            r"\b(?:request\s+)?timed?\s*out\b|\btimeout\b",
            final_error_message,
            re.IGNORECASE,
        )
        is not None
    )
    agent_end_valid = (
        bool(agent_end_events)
        and agent_end_will_retry is False
        and final_stop_reason not in {None, "error", "aborted"}
    )
    return {
        "agent_turns": counts.get("agent_turns", event_types.get("turn_start", 0)),
        "tool_calls": counts.get(
            "tool_calls", event_types.get("tool_execution_start", 0)
        ),
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
        "emergency_safeguard_triggered": bool(emergency_events),
        "emergency_safeguard_reasons": [
            str(event.get("reason")) for event in emergency_events
        ],
        "event_type_counts": event_types,
        "malformed_event_lines": malformed_events,
        "malformed_audit_lines": malformed_audit,
        "agent_end_observed": bool(agent_end_events),
        "agent_end_will_retry": agent_end_will_retry,
        "final_assistant_stop_reason": final_stop_reason,
        "final_assistant_error_message": final_error_message,
        "provider_request_timed_out": provider_request_timed_out,
        "agent_end_valid": agent_end_valid,
    }


def _termination_reason(
    *,
    timed_out: bool,
    launch_error: str | None,
    returncode: int | None,
    trajectory: dict[str, Any],
) -> str:
    if timed_out:
        return "maximum_active_wall_time_exceeded"
    if trajectory["provider_request_timed_out"]:
        return "provider_request_timeout"
    if launch_error:
        return "runtime_launch_failure"
    if trajectory["emergency_safeguard_triggered"]:
        return "emergency_operation_safeguard_exceeded"
    if trajectory["malformed_event_lines"] or trajectory["malformed_audit_lines"]:
        return "malformed_trajectory"
    if returncode != 0:
        return "runtime_exit_nonzero"
    if not trajectory["agent_end_observed"]:
        return "missing_agent_end"
    if not trajectory["agent_end_valid"]:
        return "invalid_agent_end"
    return "agent_end"


def execute_pi_v03_agent_run(repo_root: Path, run_dir: Path) -> dict[str, Any]:
    """Run qualified Pi v0.3 under Seatbelt, leaving verification pending."""
    loaded = _load_prepared_pi_v03_run(
        repo_root, run_dir, allowed_states={"prepared_not_executed"}
    )
    resolved_run = loaded["run_dir"]
    acceptance_path = resolved_run / "pi-sandbox-acceptance.json"
    acceptance = load_json(acceptance_path)
    record = loaded["record"]
    boundary = record["execution_boundary"]
    if not acceptance.get("passed") or not boundary.get("sandbox_acceptance_passed"):
        raise RunnerError("Pi v0.3 live execution requires passing sandbox acceptance")
    _require_hash(
        acceptance_path, boundary["sandbox_acceptance_sha256"], "sandbox acceptance"
    )
    if acceptance.get("profile_sha256") != loaded["sandbox"]["profile_sha256"]:
        raise RunnerError("Pi v0.3 sandbox acceptance belongs to another profile")

    invocation = loaded["invocation"]
    sandbox = loaded["sandbox"]
    events_path = Path(invocation["stdout_path"])
    stderr_path = Path(invocation["stderr_path"])
    audit_path = Path(loaded["policy"]["audit_log_path"])
    for path in (events_path, stderr_path):
        if path.exists() and path.stat().st_size:
            raise RunnerError(f"Prepared Pi v0.3 output is non-empty: {path.name}")
    if audit_path.stat().st_size:
        raise RunnerError("Prepared Pi v0.3 policy audit is non-empty")

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
        "timeout_clock": invocation["timeout_clock"],
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
        and not trajectory["provider_request_timed_out"]
        and returncode == 0
        and trajectory["malformed_event_lines"] == 0
        and trajectory["malformed_audit_lines"] == 0
    )
    agent_termination_valid = runtime_success and trajectory["agent_end_valid"]
    termination_reason = _termination_reason(
        timed_out=timed_out,
        launch_error=launch_error,
        returncode=returncode,
        trajectory=trajectory,
    )
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
        "next_action": "python3 -m local_llm_benchmark.pi_v03_adapter finalize",
    }


def finalize_pi_v03_agent_run(repo_root: Path, run_dir: Path) -> dict[str, Any]:
    """Run final public and hidden verification after Pi v0.3 has exited."""
    loaded = _load_prepared_pi_v03_run(
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
    record["artifacts"]["final_verification_sha256"] = sha256_file(
        verification_path
    )
    write_json(loaded["record_path"], record)
    return {
        "run_id": record["run_id"],
        "state": record["state"],
        **record["outcome"],
        "public_tests": (verification.get("tests") or {}).get("public"),
        "hidden_tests": (verification.get("tests") or {}).get("hidden"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare", help="Prepare without inference")
    prepare.add_argument("--model", required=True)
    prepare.add_argument("--case", type=Path, required=True)
    prepare.add_argument("--harness", type=Path, default=PI_V03_HARNESS_PATH)
    prepare.add_argument("--results-dir", type=Path, default=Path("results/agentic-runs"))
    prepare.add_argument("--host", default="http://127.0.0.1:11434")
    sandbox = subparsers.add_parser(
        "sandbox-check", help="Run no-inference Seatbelt checks"
    )
    sandbox.add_argument("--run-dir", type=Path, required=True)
    execute = subparsers.add_parser("run", help="Execute one accepted live run")
    execute.add_argument("--run-dir", type=Path, required=True)
    finalize = subparsers.add_parser(
        "finalize", help="Run separate final deterministic verification"
    )
    finalize.add_argument("--run-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    try:
        if args.command == "prepare":
            result = prepare_pi_v03_agent_run(
                repo_root,
                PiV03PrepareConfig(
                    model=args.model,
                    case_path=args.case,
                    harness_path=args.harness,
                    results_dir=args.results_dir,
                    host=args.host,
                ),
            )
        elif args.command == "sandbox-check":
            result = validate_pi_v03_seatbelt(args.run_dir)
        elif args.command == "run":
            result = execute_pi_v03_agent_run(repo_root, args.run_dir)
        else:
            result = finalize_pi_v03_agent_run(repo_root, args.run_dir)
    except (OSError, RunnerError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.command == "run":
        return 0 if result["runtime_success"] else 1
    if args.command == "finalize":
        return 0 if result["verified_success"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
