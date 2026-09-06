"""Read-only Mini harness for Track B log incident analysis."""

from __future__ import annotations

import argparse
import json
import platform
import secrets
import shutil
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from .agentic import (
    _append_trajectory,
    _collect_ollama_turn,
    _load_list,
    _normalized_relative_path,
    _request_payload,
    _safe_workspace_file,
    _verified_relative_artifact,
    validate_local_ollama_host,
)
from .log_incident import load_log_incident_case, verify_incident_report
from .ollama import OllamaClient
from .runner import (
    RunnerError,
    find_model,
    git_commit,
    load_json,
    memory_total_bytes,
    nanoseconds_to_seconds,
    resolve_repo_path,
    sha256_file,
    sha256_text,
    tokens_per_second,
    utc_now,
    write_json,
)


DEFAULT_HARNESS_PATH = Path("tasks/agentic/track-b/mini-log-v0.1.json")
EXPECTED_ACTIONS = ["read_file", "finish_report"]


@dataclass(frozen=True)
class MiniLogStartConfig:
    """Inputs frozen before one read-only log investigation starts."""

    model: str
    case_path: Path
    harness_path: Path = DEFAULT_HARNESS_PATH
    results_dir: Path = Path("results/agentic-runs")
    host: str = "http://127.0.0.1:11434"


def _positive_integer(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RunnerError(f"{context} must be a positive integer")
    return value


def _artifact(
    repo_root: Path,
    owner: dict[str, Any],
    key: str,
    context: str,
) -> Path:
    relative = _normalized_relative_path(owner.get(key), context)
    path = resolve_repo_path(repo_root, Path(relative))
    if not path.is_file() or path.is_symlink():
        raise RunnerError(f"Missing or unsafe {context}: {path}")
    return path


def load_mini_log_harness(
    repo_root: Path,
    harness_path: Path = DEFAULT_HARNESS_PATH,
) -> dict[str, Any]:
    """Load and cross-check every versioned Mini Log harness artifact."""
    resolved_harness = resolve_repo_path(repo_root, harness_path)
    harness = load_json(resolved_harness)
    if (
        harness.get("schema_version") != "1.0.0"
        or harness.get("harness_id") != "mini-log-v0.1"
        or harness.get("harness_family") != "project_mini_harness"
    ):
        raise RunnerError("Unexpected Mini Log harness identity")
    if harness.get("status") != "qualification_candidate":
        raise RunnerError("Mini Log harness must remain a qualification candidate")
    if harness.get("actions") != EXPECTED_ACTIONS:
        raise RunnerError("Mini Log action surface changed")
    if harness.get("action_protocol") != "ollama_json_schema_action_per_turn":
        raise RunnerError("Mini Log requires a structured action protocol")

    protocol_path = _artifact(repo_root, harness, "protocol_path", "protocol")
    prompt_path = _artifact(repo_root, harness, "system_prompt_path", "system prompt")
    schema_path = _artifact(repo_root, harness, "action_schema_path", "action schema")
    inventory_path = _artifact(
        repo_root, harness, "capability_inventory_path", "capability inventory"
    )
    isolation_path = _artifact(
        repo_root, harness, "isolation_profile_path", "isolation profile"
    )
    protocol = load_json(protocol_path)
    schema = load_json(schema_path)
    inventory = load_json(inventory_path)
    isolation = load_json(isolation_path)

    if (
        protocol.get("schema_version") != "1.0.0"
        or protocol.get("protocol_id") != "agentic-log-incident-v0.1"
        or protocol.get("track") != "B"
        or protocol.get("study_mode") != "development_qualification"
        or protocol.get("status") != harness["status"]
    ):
        raise RunnerError("Unexpected Mini Log protocol identity or status")
    if (
        inventory.get("inventory_id") != harness["harness_id"]
        or inventory.get("status") != harness["status"]
        or [item.get("name") for item in inventory.get("actions", [])]
        != EXPECTED_ACTIONS
    ):
        raise RunnerError("Mini Log capability inventory differs from the harness")
    if (
        isolation.get("isolation_profile_id") != harness["harness_id"]
        or isolation.get("status") != harness["status"]
        or isolation.get("evaluation", {}).get("candidate_code_executed") is not False
    ):
        raise RunnerError("Unexpected Mini Log isolation profile")
    if not isinstance(schema.get("oneOf"), list) or len(schema["oneOf"]) != 2:
        raise RunnerError("Mini Log action schema must define exactly two actions")

    limits = protocol.get("normal_capability_limits")
    safeguards = protocol.get("runaway_operation_safeguards")
    inference = protocol.get("inference_defaults")
    if not all(isinstance(item, dict) for item in (limits, safeguards, inference)):
        raise RunnerError("Mini Log protocol limit objects are incomplete")
    for key in ("maximum_active_wall_time_seconds", "provider_request_timeout_seconds"):
        _positive_integer(limits.get(key), f"normal_capability_limits.{key}")
    for key in (
        "maximum_agent_turns",
        "maximum_total_output_tokens",
        "maximum_protocol_errors",
    ):
        if limits.get(key) is not None:
            raise RunnerError(f"Mini Log must keep {key} measurement-only")
    _positive_integer(safeguards.get("maximum_file_reads"), "maximum_file_reads")
    for key in ("num_ctx", "num_predict_per_turn", "request_timeout_seconds"):
        _positive_integer(inference.get(key), f"inference_defaults.{key}")
    if inference["request_timeout_seconds"] != limits["provider_request_timeout_seconds"]:
        raise RunnerError("Mini Log provider timeout definitions differ")
    if isinstance(inference.get("temperature"), bool) or not isinstance(
        inference.get("temperature"), (int, float)
    ):
        raise RunnerError("Mini Log temperature must be numeric")
    if isinstance(inference.get("seed"), bool) or not isinstance(
        inference.get("seed"), int
    ):
        raise RunnerError("Mini Log seed must be an integer")
    if not isinstance(inference.get("think"), (bool, str)):
        raise RunnerError("Mini Log think setting is invalid")
    if not isinstance(inference.get("keep_alive"), str):
        raise RunnerError("Mini Log keep_alive must be a string")

    return {
        "harness": harness,
        "harness_path": resolved_harness,
        "protocol": protocol,
        "protocol_path": protocol_path,
        "system_prompt": prompt_path.read_text(encoding="utf-8").strip(),
        "system_prompt_path": prompt_path,
        "action_schema": schema,
        "action_schema_path": schema_path,
        "capability_inventory": inventory,
        "capability_inventory_path": inventory_path,
        "isolation_profile": isolation,
        "isolation_profile_path": isolation_path,
    }


def load_mini_log_case(
    repo_root: Path,
    case_path: Path,
    harness_path: Path = DEFAULT_HARNESS_PATH,
) -> dict[str, Any]:
    """Bind one frozen incident fixture to the Mini Log harness."""
    harness = load_mini_log_harness(repo_root, harness_path)
    loaded = load_log_incident_case(repo_root, case_path)
    relative_case = loaded["case_path"].relative_to(repo_root).as_posix()
    selected = {
        item.get("case_path"): item.get("case_id")
        for item in harness["protocol"].get("task_subset", [])
        if isinstance(item, dict)
    }
    if selected.get(relative_case) != loaded["case"]["case_id"]:
        raise RunnerError("Incident case is outside the Mini Log task subset")
    report_keys = ("type", "additionalProperties", "required", "properties")
    expected_report = {key: loaded["schema"].get(key) for key in report_keys}
    action_definitions = harness["action_schema"].get("$defs", {})
    if action_definitions.get("incident_report") != expected_report:
        raise RunnerError("Action schema report contract differs from the case schema")
    if action_definitions.get("event_reference") != loaded["schema"].get(
        "$defs", {}
    ).get("event_reference"):
        raise RunnerError("Action schema event-reference contract differs from the case")
    return {**loaded, **harness, "relative_case_path": relative_case}


def parse_mini_log_action(response_text: str) -> dict[str, Any]:
    """Parse one strict action without repairing candidate output."""
    if not response_text.strip():
        return {
            "status": "invalid",
            "failure_code": "empty_action",
            "reason": "The model returned no visible action.",
            "action": None,
        }
    try:
        value = json.loads(response_text)
    except json.JSONDecodeError as exc:
        return {
            "status": "invalid",
            "failure_code": "malformed_action",
            "reason": f"Expected one JSON object: {exc.msg}",
            "action": None,
        }
    if not isinstance(value, dict):
        return {
            "status": "invalid",
            "failure_code": "malformed_action",
            "reason": "The action must be a JSON object.",
            "action": None,
        }
    name = value.get("action")
    if name == "read_file" and set(value) == {"action", "path"} and isinstance(
        value.get("path"), str
    ) and value["path"]:
        try:
            _normalized_relative_path(value["path"], "read_file action")
        except RunnerError as exc:
            return {
                "status": "invalid",
                "failure_code": "unsafe_path",
                "reason": str(exc),
                "action": name,
            }
        return {"status": "valid", "action": name, "value": value}
    if name == "finish_report" and set(value) == {"action", "report"} and isinstance(
        value.get("report"), dict
    ):
        return {"status": "valid", "action": name, "value": value}
    return {
        "status": "invalid",
        "failure_code": "unsupported_or_malformed_action",
        "reason": "Only exact read_file and finish_report action objects are allowed.",
        "action": name if isinstance(name, str) else None,
    }


def _initial_user_message(loaded: dict[str, Any]) -> str:
    files = "\n".join(f"- {item}" for item in loaded["case"]["candidate_context"]["files"])
    limits = loaded["protocol"]["normal_capability_limits"]
    reads = loaded["protocol"]["runaway_operation_safeguards"]["maximum_file_reads"]
    task = loaded["task_path"].read_text(encoding="utf-8").strip()
    return (
        f"# Task\n\n{task}\n\n"
        f"# Candidate-visible files\n\n{files}\n\n"
        "# Run boundary\n\n"
        f"- Active model and tool time: {limits['maximum_active_wall_time_seconds']} seconds.\n"
        "- Agent turns, output tokens and protocol errors have no normal cap.\n"
        f"- Emergency file-read safeguard: {reads}.\n"
        "- The hidden reference and verifier are unavailable until final verification.\n\n"
        "Return your first JSON action now."
    )


def _workspace_inventory(workspace: Path) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for path in sorted(workspace.rglob("*")):
        if path.is_symlink():
            raise RunnerError(f"Symlink found in Mini Log workspace: {path}")
        if path.is_file():
            inventory[path.relative_to(workspace).as_posix()] = {
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
    return inventory


def _verify_workspace_copy(workspace: Path, loaded: dict[str, Any]) -> dict[str, Any]:
    expected = {
        item["path"]: {"sha256": item["sha256"], "size_bytes": item["size_bytes"]}
        for item in loaded["manifest"]["files"]
    }
    observed = _workspace_inventory(workspace)
    if observed != expected:
        raise RunnerError("Fresh Mini Log workspace differs from the frozen manifest")
    return {
        "status": "passed",
        "fresh_workspace": True,
        "symlinks_present": False,
        "exact_fixture_manifest": True,
        "earlier_run_artifacts_visible": False,
        "file_count": len(observed),
    }


def _write_pending_request(
    run_dir: Path,
    record: dict[str, Any],
    messages: list[Any],
    loaded: dict[str, Any],
) -> None:
    turn = record["trajectory"]["agent_turns"] + 1
    relative = f"turns/{turn:03d}-request.json"
    path = run_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, _request_payload(record, messages, loaded["action_schema"]))
    record["state"] = "awaiting_model"
    record["artifacts"]["pending_request"] = relative
    record["artifacts"]["pending_request_sha256"] = sha256_file(path)


def start_mini_log_run(repo_root: Path, config: MiniLogStartConfig) -> dict[str, Any]:
    """Create a fresh run and first request without contacting Ollama."""
    host = validate_local_ollama_host(config.host)
    if not isinstance(config.model, str) or not config.model.strip():
        raise RunnerError("Mini Log model name must be non-empty")
    loaded = load_mini_log_case(repo_root, config.case_path, config.harness_path)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"mini-log-run-{timestamp}-{secrets.token_hex(4)}"
    results_dir = resolve_repo_path(repo_root, config.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    run_dir = results_dir / run_id
    run_dir.mkdir(parents=False, exist_ok=False)
    workspace = run_dir / "workspace"
    shutil.copytree(loaded["fixture_root"], workspace)
    contamination = _verify_workspace_copy(workspace, loaded)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": loaded["system_prompt"]},
        {"role": "user", "content": _initial_user_message(loaded)},
    ]
    messages_path = run_dir / "messages.json"
    write_json(messages_path, messages)
    inference = loaded["protocol"]["inference_defaults"]
    artifact_paths = {
        "harness": loaded["harness_path"],
        "protocol": loaded["protocol_path"],
        "system_prompt": loaded["system_prompt_path"],
        "action_schema": loaded["action_schema_path"],
        "capability_inventory": loaded["capability_inventory_path"],
        "isolation_profile": loaded["isolation_profile_path"],
    }
    record: dict[str, Any] = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "track": "B",
        "study_mode": "development_qualification",
        "state": "initializing",
        "started_at": utc_now(),
        "completed_at": None,
        "harness": {
            "harness_id": loaded["harness"]["harness_id"],
            "harness_family": loaded["harness"]["harness_family"],
            "harness_status": loaded["harness"]["status"],
            **{
                f"{key}_path": path.relative_to(repo_root).as_posix()
                for key, path in artifact_paths.items()
            },
            **{f"{key}_sha256": sha256_file(path) for key, path in artifact_paths.items()},
            "implementation_path": "local_llm_benchmark/log_incident_mini.py",
            "implementation_sha256": sha256_file(Path(__file__)),
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
            "report_schema_sha256": sha256_file(loaded["schema_path"]),
            "benchmark_card_sha256": sha256_file(loaded["card_path"]),
            "ground_truth_sha256": sha256_file(loaded["ground_truth_path"]),
            "reference_report_sha256": sha256_file(loaded["reference_report_path"]),
            "verifier_version": loaded["case"]["verification"]["version"],
            "candidate_visible_files": loaded["case"]["candidate_context"]["files"],
        },
        "deployment": {
            "requested_model": config.model,
            "ollama_host": host,
            "ollama_version": None,
            "model": None,
            "options": {
                "temperature": inference["temperature"],
                "seed": inference["seed"],
                "think": inference["think"],
                "num_ctx": inference["num_ctx"],
                "num_predict_per_turn": inference["num_predict_per_turn"],
                "keep_alive": inference["keep_alive"],
                "request_timeout_seconds": inference["request_timeout_seconds"],
            },
        },
        "limits": loaded["protocol"]["normal_capability_limits"],
        "safeguards": loaded["protocol"]["runaway_operation_safeguards"],
        "trajectory": {
            "agent_turns": 0,
            "model_requests": 0,
            "tool_calls": 0,
            "failed_tool_calls": 0,
            "protocol_errors": 0,
            "file_reads": 0,
            "repeated_file_reads": 0,
            "read_paths": {},
            "input_tokens": 0,
            "output_tokens": 0,
            "model_wall_time_seconds": 0.0,
            "tool_wall_time_seconds": 0.0,
            "active_wall_time_seconds": 0.0,
            "final_verification_wall_time_seconds": None,
        },
        "turns": [],
        "active_model_request": None,
        "last_model_request": None,
        "termination": None,
        "outcome": None,
        "verification": None,
        "environment": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor() or None,
            "memory_total_bytes": memory_total_bytes(),
            "python_version": platform.python_version(),
        },
        "execution_boundary": {
            "model_and_action_processes_separate": True,
            "inference_requests_made": 0,
            "candidate_code_executed": False,
            "candidate_commands_executed": False,
            "candidate_writes_performed": False,
            "hidden_verification_executed": False,
        },
        "contamination_check": contamination,
        "artifacts": {
            "messages": "messages.json",
            "messages_sha256": sha256_file(messages_path),
            "workspace": "workspace",
            "trajectory": "trajectory.jsonl",
            "trajectory_sha256": None,
            "pending_request": None,
            "pending_request_sha256": None,
            "candidate_report": None,
            "candidate_report_sha256": None,
            "final_verification": None,
            "final_verification_sha256": None,
        },
    }
    _write_pending_request(run_dir, record, messages, loaded)
    write_json(run_dir / "run.json", record)
    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "state": record["state"],
        "model": config.model,
        "case_id": loaded["case"]["case_id"],
        "next_action": "python3 -m local_llm_benchmark.log_incident_mini call",
    }


def _load_run(repo_root: Path, run_dir: Path) -> tuple[Path, dict[str, Any]]:
    resolved = resolve_repo_path(repo_root, run_dir)
    if not resolved.is_dir():
        raise RunnerError(f"Mini Log run directory does not exist: {resolved}")
    record = load_json(resolved / "run.json")
    if record.get("track") != "B" or record.get("harness", {}).get(
        "harness_id"
    ) != "mini-log-v0.1":
        raise RunnerError("Run does not belong to Mini Log v0.1")
    return resolved, record


def _validated_definition(repo_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    harness_record = record["harness"]
    case_record = record["case"]
    loaded = load_mini_log_case(
        repo_root,
        Path(_normalized_relative_path(case_record.get("case_path"), "run case")),
        Path(_normalized_relative_path(harness_record.get("harness_path"), "run harness")),
    )
    observed = {
        "harness_sha256": sha256_file(loaded["harness_path"]),
        "protocol_sha256": sha256_file(loaded["protocol_path"]),
        "system_prompt_sha256": sha256_file(loaded["system_prompt_path"]),
        "action_schema_sha256": sha256_file(loaded["action_schema_path"]),
        "capability_inventory_sha256": sha256_file(loaded["capability_inventory_path"]),
        "isolation_profile_sha256": sha256_file(loaded["isolation_profile_path"]),
        "implementation_sha256": sha256_file(Path(__file__)),
        "case_definition_sha256": sha256_file(loaded["case_path"]),
        "fixture_manifest_sha256": loaded["manifest_sha256"],
        "task_sha256": loaded["task_sha256"],
        "report_schema_sha256": sha256_file(loaded["schema_path"]),
        "benchmark_card_sha256": sha256_file(loaded["card_path"]),
        "ground_truth_sha256": sha256_file(loaded["ground_truth_path"]),
        "reference_report_sha256": sha256_file(loaded["reference_report_path"]),
    }
    mismatches = []
    for key, value in observed.items():
        owner = harness_record if key in harness_record else case_record
        if owner.get(key) != value:
            mismatches.append(key)
    if mismatches:
        raise RunnerError(
            "Mini Log benchmark definition changed after run start: "
            + ", ".join(sorted(mismatches))
        )
    return loaded


def _runtime_failure_type(exc: BaseException, phase: str) -> str:
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__ or current.__context__
    if any(
        "timed out" in str(item).casefold() or "timeout" in str(item).casefold()
        for item in chain
    ):
        return "provider_request_timeout"
    if any("without a final done=true event" in str(item) for item in chain):
        return "provider_stream_incomplete"
    if phase in {"model_resolution", "model_inspection"}:
        return "model_load_failure"
    return "runtime_failure"


def _end_trajectory(
    run_dir: Path,
    record: dict[str, Any],
    *,
    reason: str,
    runtime_success: bool,
) -> dict[str, Any]:
    record["state"] = "trajectory_complete_verification_pending"
    record["termination"] = {
        "reason": reason,
        "runtime_success": runtime_success,
        "agent_termination_valid": runtime_success and reason == "finish_report",
        "observed_at": utc_now(),
    }
    record["artifacts"]["pending_request"] = None
    record["artifacts"]["pending_request_sha256"] = None
    trajectory_path = run_dir / record["artifacts"]["trajectory"]
    record["artifacts"]["trajectory_sha256"] = (
        sha256_file(trajectory_path) if trajectory_path.is_file() else None
    )
    write_json(run_dir / "run.json", record)
    return {
        "run_id": record["run_id"],
        "run_dir": str(run_dir),
        "state": record["state"],
        "termination_reason": reason,
        "runtime_success": runtime_success,
        "agent_termination_valid": record["termination"]["agent_termination_valid"],
        "next_action": "python3 -m local_llm_benchmark.log_incident_mini finalize",
    }


def call_mini_log_model(repo_root: Path, run_dir: Path) -> dict[str, Any]:
    """Execute one Ollama request and no candidate action."""
    resolved, record = _load_run(repo_root, run_dir)
    if record.get("state") != "awaiting_model":
        raise RunnerError("Mini Log run is not awaiting a model call")
    _validated_definition(repo_root, record)
    trajectory = record["trajectory"]
    if trajectory["active_wall_time_seconds"] >= record["limits"][
        "maximum_active_wall_time_seconds"
    ]:
        return _end_trajectory(
            resolved,
            record,
            reason="maximum_active_wall_time_exceeded",
            runtime_success=False,
        )
    request_path = _verified_relative_artifact(
        resolved,
        record["artifacts"]["pending_request"],
        record["artifacts"]["pending_request_sha256"],
        "Mini Log pending request",
    )
    payload = load_json(request_path)
    deployment = record["deployment"]
    client = OllamaClient(
        deployment["ollama_host"],
        timeout_seconds=float(deployment["options"]["request_timeout_seconds"]),
    )
    turn_index = trajectory["agent_turns"] + 1
    request_index = trajectory["model_requests"] + 1
    stream_relative = f"turns/{turn_index:03d}-stream.ndjson"
    response_relative = f"turns/{turn_index:03d}-response.txt"
    thinking_relative = f"turns/{turn_index:03d}-thinking.txt"
    started = time.monotonic()
    phase = "inference"
    version_response: dict[str, Any] | None = None
    model_tag: dict[str, Any] | None = None
    model_show: dict[str, Any] | None = None
    trajectory["model_requests"] = request_index
    record["state"] = "model_call_running"
    record["active_model_request"] = {
        "request_index": request_index,
        "turn": turn_index,
        "started_at": utc_now(),
        "request": request_path.relative_to(resolved).as_posix(),
        "request_sha256": sha256_file(request_path),
    }
    write_json(resolved / "run.json", record)
    try:
        if deployment["model"] is None:
            phase = "ollama_version"
            version_response = client.version()
            phase = "model_resolution"
            model_tag = find_model(client.list_models(), deployment["requested_model"])
            phase = "model_inspection"
            model_show = client.show_model(deployment["requested_model"])
        phase = "inference"
        turn = _collect_ollama_turn(client, payload, resolved / stream_relative)
    except Exception as exc:
        duration = time.monotonic() - started
        trajectory["model_wall_time_seconds"] += duration
        trajectory["active_wall_time_seconds"] += duration
        failure_type = _runtime_failure_type(exc, phase)
        failure_path = resolved / f"turns/{turn_index:03d}-failure.json"
        write_json(
            failure_path,
            {
                "schema_version": "1.0.0",
                "run_id": record["run_id"],
                "failed_at": utc_now(),
                "phase": phase,
                "failure_type": failure_type,
                "duration_seconds": duration,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        record["execution_boundary"]["inference_requests_made"] = request_index
        record["active_model_request"].update(
            {"finished_at": utc_now(), "status": "failed", "failure_type": failure_type}
        )
        record["last_model_request"] = record["active_model_request"]
        record["active_model_request"] = None
        record["runtime_failure"] = {
            "type": failure_type,
            "artifact": failure_path.relative_to(resolved).as_posix(),
            "artifact_sha256": sha256_file(failure_path),
        }
        return _end_trajectory(
            resolved, record, reason=failure_type, runtime_success=False
        )

    duration = time.monotonic() - started
    final_event = turn["final_event"]
    response_path = resolved / response_relative
    response_path.write_text(turn["content"] + "\n", encoding="utf-8")
    thinking_path = resolved / thinking_relative
    if turn["thinking"]:
        thinking_path.write_text(turn["thinking"] + "\n", encoding="utf-8")
    turn_record = {
        "turn": turn_index,
        "request_index": request_index,
        "request": request_path.relative_to(resolved).as_posix(),
        "request_sha256": sha256_file(request_path),
        "response": response_relative,
        "response_sha256": sha256_file(response_path),
        "thinking": thinking_relative if turn["thinking"] else None,
        "thinking_sha256": sha256_file(thinking_path) if turn["thinking"] else None,
        "stream": stream_relative,
        "stream_sha256": sha256_file(resolved / stream_relative),
        "done_reason": final_event.get("done_reason"),
        "wall_time_seconds": duration,
        "inference_wall_time_seconds": turn["wall_time_seconds"],
        "time_to_first_content_seconds": turn["time_to_first_content_seconds"],
        "prompt_tokens": final_event.get("prompt_eval_count") or 0,
        "output_tokens": final_event.get("eval_count") or 0,
        "load_duration_seconds": nanoseconds_to_seconds(final_event.get("load_duration")),
        "prompt_eval_duration_seconds": nanoseconds_to_seconds(
            final_event.get("prompt_eval_duration")
        ),
        "eval_duration_seconds": nanoseconds_to_seconds(final_event.get("eval_duration")),
        "output_tokens_per_second": tokens_per_second(
            final_event.get("eval_count"), final_event.get("eval_duration")
        ),
        "action": None,
        "action_status": "pending",
    }
    record["turns"].append(turn_record)
    trajectory["agent_turns"] += 1
    trajectory["input_tokens"] += turn_record["prompt_tokens"]
    trajectory["output_tokens"] += turn_record["output_tokens"]
    trajectory["model_wall_time_seconds"] += duration
    trajectory["active_wall_time_seconds"] += duration
    record["execution_boundary"]["inference_requests_made"] = request_index
    record["active_model_request"].update(
        {
            "finished_at": utc_now(),
            "status": "complete",
            "response_sha256": turn_record["response_sha256"],
        }
    )
    record["last_model_request"] = record["active_model_request"]
    record["active_model_request"] = None
    if version_response is not None and model_tag is not None and model_show is not None:
        deployment["ollama_version"] = version_response.get("version")
        deployment["model"] = {
            "requested_name": deployment["requested_model"],
            "resolved_name": model_tag.get("name") or model_tag.get("model"),
            "digest": model_tag.get("digest"),
            "size_bytes": model_tag.get("size"),
            "modified_at": model_tag.get("modified_at"),
            "details": model_tag.get("details"),
            "capabilities": model_show.get("capabilities"),
            "parameters": model_show.get("parameters"),
            "template_sha256": sha256_text(model_show.get("template", "")),
        }
    record["state"] = "awaiting_action"
    record["artifacts"]["pending_request"] = None
    record["artifacts"]["pending_request_sha256"] = None
    write_json(resolved / "run.json", record)
    return {
        "run_id": record["run_id"],
        "run_dir": str(resolved),
        "state": record["state"],
        "turn": turn_index,
        "done_reason": final_event.get("done_reason"),
        "active_wall_time_seconds": trajectory["active_wall_time_seconds"],
        "next_action": "python3 -m local_llm_benchmark.log_incident_mini step",
    }


def _read_observation(
    workspace: Path,
    loaded: dict[str, Any],
    relative: str,
    trajectory: dict[str, Any],
) -> dict[str, Any]:
    trajectory["tool_calls"] += 1
    maximum = loaded["protocol"]["runaway_operation_safeguards"]["maximum_file_reads"]
    if trajectory["file_reads"] >= maximum:
        return {
            "ok": False,
            "action": "read_file",
            "failure_code": "file_read_safeguard_exceeded",
            "reason": f"The emergency safeguard permits at most {maximum} file reads.",
            "terminal": True,
        }
    if relative not in loaded["case"]["candidate_context"]["files"]:
        return {
            "ok": False,
            "action": "read_file",
            "path": relative,
            "failure_code": "path_not_candidate_visible",
            "reason": "The requested path is outside the declared fixture inventory.",
            "terminal": False,
        }
    try:
        path = _safe_workspace_file(workspace, relative)
    except RunnerError as exc:
        return {
            "ok": False,
            "action": "read_file",
            "path": relative,
            "failure_code": "unsafe_or_missing_file",
            "reason": str(exc),
            "terminal": False,
        }
    prior_reads = trajectory["read_paths"].get(relative, 0)
    trajectory["read_paths"][relative] = prior_reads + 1
    trajectory["file_reads"] += 1
    if prior_reads:
        trajectory["repeated_file_reads"] += 1
    return {
        "ok": True,
        "action": "read_file",
        "path": relative,
        "content": path.read_text(encoding="utf-8"),
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "terminal": False,
    }


def step_mini_log_action(repo_root: Path, run_dir: Path) -> dict[str, Any]:
    """Apply one saved read/report action and queue the next request if needed."""
    resolved, record = _load_run(repo_root, run_dir)
    if record.get("state") != "awaiting_action":
        raise RunnerError("Mini Log run is not awaiting action processing")
    loaded = _validated_definition(repo_root, record)
    messages_path = _verified_relative_artifact(
        resolved,
        record["artifacts"]["messages"],
        record["artifacts"]["messages_sha256"],
        "Mini Log messages",
    )
    last_turn = record["turns"][-1]
    response_path = _verified_relative_artifact(
        resolved,
        last_turn["response"],
        last_turn["response_sha256"],
        "Mini Log response",
    )
    response_text = response_path.read_text(encoding="utf-8").rstrip("\n")
    trajectory = record["trajectory"]
    maximum_active = record["limits"]["maximum_active_wall_time_seconds"]
    if trajectory["active_wall_time_seconds"] >= maximum_active:
        last_turn["action_status"] = "not_executed_active_time_exceeded"
        return _end_trajectory(
            resolved,
            record,
            reason="maximum_active_wall_time_exceeded",
            runtime_success=False,
        )

    parsed = parse_mini_log_action(response_text)
    started = time.monotonic()
    if parsed["status"] == "invalid":
        trajectory["protocol_errors"] += 1
        observation = {
            "ok": False,
            "action": parsed.get("action"),
            "failure_code": parsed["failure_code"],
            "failure_category": "model_protocol_failure",
            "reason": parsed["reason"],
            "terminal": False,
        }
        last_turn["action"] = parsed.get("action")
        last_turn["action_status"] = "protocol_error"
    else:
        action = parsed["value"]
        last_turn["action"] = action["action"]
        if action["action"] == "read_file":
            observation = _read_observation(
                resolved / record["artifacts"]["workspace"],
                loaded,
                action["path"],
                trajectory,
            )
            if not observation["ok"]:
                trajectory["failed_tool_calls"] += 1
            last_turn["action_status"] = (
                "complete" if observation["ok"] else "tool_error"
            )
        else:
            trajectory["tool_calls"] += 1
            report_path = resolved / "candidate-report.json"
            write_json(report_path, action["report"])
            record["artifacts"]["candidate_report"] = "candidate-report.json"
            record["artifacts"]["candidate_report_sha256"] = sha256_file(report_path)
            observation = {
                "ok": True,
                "action": "finish_report",
                "report_sha256": sha256_file(report_path),
                "terminal": True,
            }
            last_turn["action_status"] = "complete"
    duration = time.monotonic() - started
    trajectory["tool_wall_time_seconds"] += duration
    trajectory["active_wall_time_seconds"] += duration
    observation["tool_wall_time_seconds"] = duration
    _append_trajectory(
        resolved,
        {
            "schema_version": "1.0.0",
            "timestamp": utc_now(),
            "turn": last_turn["turn"],
            "response_sha256": last_turn["response_sha256"],
            "parsed_action": parsed,
            "observation": observation,
        },
    )
    record["artifacts"]["trajectory_sha256"] = sha256_file(
        resolved / record["artifacts"]["trajectory"]
    )
    if trajectory["active_wall_time_seconds"] >= maximum_active:
        return _end_trajectory(
            resolved,
            record,
            reason="maximum_active_wall_time_exceeded",
            runtime_success=False,
        )
    if observation.get("failure_code") == "file_read_safeguard_exceeded":
        return _end_trajectory(
            resolved,
            record,
            reason="emergency_operation_safeguard_exceeded",
            runtime_success=True,
        )
    if observation.get("terminal") and observation.get("action") == "finish_report":
        return _end_trajectory(
            resolved, record, reason="finish_report", runtime_success=True
        )

    messages = _load_list(messages_path, "Mini Log messages")
    messages.append({"role": "assistant", "content": response_text})
    messages.append(
        {
            "role": "user",
            "content": json.dumps(
                {"tool_observation": observation},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        }
    )
    write_json(messages_path, messages)
    record["artifacts"]["messages_sha256"] = sha256_file(messages_path)
    _write_pending_request(resolved, record, messages, loaded)
    write_json(resolved / "run.json", record)
    return {
        "run_id": record["run_id"],
        "run_dir": str(resolved),
        "state": record["state"],
        "turn": last_turn["turn"],
        "action": last_turn["action"],
        "action_status": last_turn["action_status"],
        "observation": observation,
        "active_wall_time_seconds": trajectory["active_wall_time_seconds"],
        "next_action": "python3 -m local_llm_benchmark.log_incident_mini call",
    }


def finalize_mini_log_run(repo_root: Path, run_dir: Path) -> dict[str, Any]:
    """Apply the hidden deterministic verifier after the trajectory stops."""
    resolved, record = _load_run(repo_root, run_dir)
    if record.get("state") != "trajectory_complete_verification_pending":
        raise RunnerError("Mini Log trajectory is not ready for final verification")
    _validated_definition(repo_root, record)
    trajectory_path = resolved / record["artifacts"]["trajectory"]
    expected_trajectory = record["artifacts"].get("trajectory_sha256")
    if expected_trajectory is not None and sha256_file(trajectory_path) != expected_trajectory:
        raise RunnerError("Mini Log trajectory changed before verification")
    report: dict[str, Any] | None = None
    if record["artifacts"].get("candidate_report"):
        report_path = _verified_relative_artifact(
            resolved,
            record["artifacts"]["candidate_report"],
            record["artifacts"]["candidate_report_sha256"],
            "Mini Log candidate report",
        )
        report = load_json(report_path)
    started = time.monotonic()
    verification = verify_incident_report(
        repo_root, Path(record["case"]["case_path"]), report
    )
    duration = time.monotonic() - started
    record["trajectory"]["final_verification_wall_time_seconds"] = duration
    verification_path = resolved / "final-verification.json"
    write_json(verification_path, verification)
    termination = record["termination"]
    runtime_success = bool(termination["runtime_success"])
    agent_valid = bool(termination["agent_termination_valid"])
    verifier_success = bool(verification["verified_success"])
    verified_success = runtime_success and agent_valid and verifier_success
    if not runtime_success:
        failure_category = "infrastructure_or_runtime_failure"
        failure_type = termination["reason"]
    elif not agent_valid:
        failure_category = "agent_failure"
        failure_type = termination["reason"]
    elif not verifier_success:
        failure_category = "task_or_verification_failure"
        failure_type = verification.get("failure_code") or "verification_failed"
    else:
        failure_category = None
        failure_type = None
    record["state"] = "complete"
    record["completed_at"] = utc_now()
    record["outcome"] = {
        "runtime_success": runtime_success,
        "agent_termination_valid": agent_valid,
        "verifier_success": verifier_success,
        "verified_success": verified_success,
        "failure_category": failure_category,
        "failure_type": failure_type,
        "trajectory_termination_reason": termination["reason"],
    }
    record["verification"] = verification
    record["execution_boundary"]["hidden_verification_executed"] = True
    record["artifacts"]["final_verification"] = "final-verification.json"
    record["artifacts"]["final_verification_sha256"] = sha256_file(verification_path)
    write_json(resolved / "run.json", record)
    return {
        "run_id": record["run_id"],
        "run_dir": str(resolved),
        "state": record["state"],
        **record["outcome"],
        "verification": {
            "essential_pass_count": verification.get("essential_pass_count", 0),
            "essential_check_count": verification.get("essential_check_count", 0),
        },
        "trajectory": record["trajectory"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser("start", help="Prepare without inference")
    start.add_argument("--model", required=True)
    start.add_argument("--case", type=Path, required=True)
    start.add_argument("--harness", type=Path, default=DEFAULT_HARNESS_PATH)
    start.add_argument("--results-dir", type=Path, default=Path("results/agentic-runs"))
    start.add_argument("--host", default="http://127.0.0.1:11434")
    for name, help_text in (
        ("call", "Execute exactly one model request"),
        ("step", "Apply exactly one saved read/report action"),
        ("finalize", "Run final deterministic verification"),
    ):
        child = subparsers.add_parser(name, help=help_text)
        child.add_argument("--run-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    try:
        if args.command == "start":
            result = start_mini_log_run(
                repo_root,
                MiniLogStartConfig(
                    model=args.model,
                    case_path=args.case,
                    harness_path=args.harness,
                    results_dir=args.results_dir,
                    host=args.host,
                ),
            )
        elif args.command == "call":
            result = call_mini_log_model(repo_root, args.run_dir)
        elif args.command == "step":
            result = step_mini_log_action(repo_root, args.run_dir)
        else:
            result = finalize_mini_log_run(repo_root, args.run_dir)
    except (OSError, RunnerError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.command == "finalize":
        return 0 if result["verified_success"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
