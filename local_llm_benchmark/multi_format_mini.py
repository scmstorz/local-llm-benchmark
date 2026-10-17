"""Project-owned Mini harness for real multi-format artifacts v0.1."""

from __future__ import annotations

import argparse
import json
import platform
import secrets
import shutil
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .agentic import (
    _collect_ollama_turn,
    _load_list,
    _normalized_relative_path,
    _request_payload,
    _verified_relative_artifact,
    validate_local_ollama_host,
)
from .log_incident_mini import _artifact, _positive_integer, _runtime_failure_type
from .multi_format_artifacts import (
    ARTIFACTS,
    ArtifactToolError,
    execute_artifact_request,
    verify_workspace,
)
from .multi_format_document_analysis import (
    load_multi_format_case,
    verify_multi_format_report,
)
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


DEFAULT_HARNESS_PATH = Path("tasks/agentic/track-b/mini-multi-format-v0.1.json")
DEFAULT_CASE_PATH = Path(
    "tasks/agentic/multi-format-document-analysis/"
    "rollout-readiness-reconciliation/case-v0.1.json"
)
HARNESS_ID = "mini-multi-format-v0.1"
PROTOCOL_ID = "agentic-multi-format-v0.1"
EXPECTED_ACTIONS = [
    "list_artifacts",
    "read_docx",
    "read_pdf",
    "read_xlsx",
    "finish_report",
]


@dataclass(frozen=True)
class MiniMultiFormatStartConfig:
    """Frozen inputs for one no-write Mini multi-format run."""

    model: str
    case_path: Path = DEFAULT_CASE_PATH
    harness_path: Path = DEFAULT_HARNESS_PATH
    results_dir: Path = Path("results/agentic-runs")
    host: str = "http://127.0.0.1:11434"


def load_mini_multi_format_harness(
    repo_root: Path, harness_path: Path = DEFAULT_HARNESS_PATH
) -> dict[str, Any]:
    """Load and cross-check the complete frozen Mini definition."""
    path = resolve_repo_path(repo_root, harness_path)
    harness = load_json(path)
    if (
        harness.get("schema_version") != "1.0.0"
        or harness.get("harness_id") != HARNESS_ID
        or harness.get("harness_family") != "project_mini_harness"
        or harness.get("status") != "qualification_candidate"
        or harness.get("actions") != EXPECTED_ACTIONS
        or harness.get("action_protocol") != "ollama_json_schema_action_per_turn"
    ):
        raise RunnerError("Unexpected Mini multi-format harness definition")
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
        protocol.get("protocol_id") != PROTOCOL_ID
        or protocol.get("track") != "B"
        or protocol.get("study_mode") != "development_qualification"
        or protocol.get("status") != harness["status"]
        or protocol.get("artifact_api", {}).get("operations") != EXPECTED_ACTIONS[:-1]
        or protocol.get("artifact_api", {}).get("maximum_response_bytes") != 8192
    ):
        raise RunnerError("Unexpected Mini multi-format protocol")
    subset = protocol.get("task_subset")
    if not isinstance(subset, list) or len(subset) != 1:
        raise RunnerError("Mini multi-format requires exactly one case")
    if (
        inventory.get("inventory_id") != HARNESS_ID
        or [item.get("name") for item in inventory.get("actions", [])]
        != EXPECTED_ACTIONS
        or inventory.get("shared_backend")
        != "local_llm_benchmark/multi_format_artifacts.py"
    ):
        raise RunnerError("Mini multi-format capability inventory differs")
    if (
        isolation.get("isolation_profile_id") != HARNESS_ID
        or isolation.get("workspace", {}).get("fresh_artifact_only_copy_per_run")
        is not True
        or isolation.get("evaluation", {}).get("canonical_extraction_outside_workspace")
        is not True
        or isolation.get("evaluation", {}).get("candidate_code_executed") is not False
    ):
        raise RunnerError("Unexpected Mini multi-format isolation profile")
    if not isinstance(schema.get("oneOf"), list) or len(schema["oneOf"]) != 5:
        raise RunnerError("Mini multi-format action schema must define five actions")
    limits = protocol.get("normal_capability_limits")
    safeguards = protocol.get("runaway_operation_safeguards")
    inference = protocol.get("inference_defaults")
    if not all(isinstance(value, dict) for value in (limits, safeguards, inference)):
        raise RunnerError("Mini multi-format limit objects are incomplete")
    for key in ("maximum_active_wall_time_seconds", "provider_request_timeout_seconds"):
        _positive_integer(limits.get(key), key)
    for key in ("maximum_agent_turns", "maximum_total_output_tokens", "maximum_protocol_errors"):
        if limits.get(key) is not None:
            raise RunnerError(f"Mini multi-format must keep {key} measurement-only")
    _positive_integer(safeguards.get("maximum_artifact_tool_calls"), "maximum_artifact_tool_calls")
    for key in ("num_ctx", "num_predict_per_turn", "request_timeout_seconds"):
        _positive_integer(inference.get(key), key)
    if inference["request_timeout_seconds"] != limits["provider_request_timeout_seconds"]:
        raise RunnerError("Mini multi-format provider timeouts differ")
    return {
        "harness": harness,
        "harness_path": path,
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


def load_mini_multi_format_case(
    repo_root: Path,
    case_path: Path = DEFAULT_CASE_PATH,
    harness_path: Path = DEFAULT_HARNESS_PATH,
) -> dict[str, Any]:
    """Bind the one qualified artifact case to Mini."""
    harness = load_mini_multi_format_harness(repo_root, harness_path)
    loaded = load_multi_format_case(repo_root, case_path)
    relative_case = loaded["case_path"].relative_to(repo_root).as_posix()
    selected = harness["protocol"]["task_subset"][0]
    if (
        selected.get("case_path") != relative_case
        or selected.get("case_id") != loaded["case"]["case_id"]
        or selected.get("case_version") != loaded["case"]["case_version"]
    ):
        raise RunnerError("Case is outside the Mini multi-format subset")
    expected_report = {
        key: loaded["schema"].get(key)
        for key in ("type", "additionalProperties", "required", "properties")
    }
    if harness["action_schema"].get("$defs", {}).get("decision_report") != expected_report:
        raise RunnerError("Mini action schema differs from the decision report contract")
    fixture_root = resolve_repo_path(
        repo_root, Path(loaded["case"]["planned_artifact_root"])
    )
    if not fixture_root.is_dir():
        raise RunnerError("Multi-format fixture root is missing")
    return {
        **loaded,
        **harness,
        "relative_case_path": relative_case,
        "fixture_root": fixture_root,
    }


def _copy_workspace(source: Path, destination: Path) -> dict[str, Any]:
    destination.mkdir()
    for filename in ARTIFACTS:
        source_path = source / filename
        if not source_path.is_file() or source_path.is_symlink():
            raise RunnerError(f"Unsafe source artifact: {filename}")
        shutil.copyfile(source_path, destination / filename)
    try:
        return verify_workspace(destination)
    except ArtifactToolError as exc:
        raise RunnerError(str(exc)) from exc


def _initial_user_message(loaded: dict[str, Any]) -> str:
    task = loaded["task_path"].read_text(encoding="utf-8").strip()
    limits = loaded["protocol"]["normal_capability_limits"]
    calls = loaded["protocol"]["runaway_operation_safeguards"][
        "maximum_artifact_tool_calls"
    ]
    return (
        f"# Task\n\n{task}\n\n"
        "# Run boundary\n\n"
        "- Artifact contents are initially hidden; call list_artifacts first.\n"
        f"- Active model and tool time: {limits['maximum_active_wall_time_seconds']} seconds.\n"
        "- Agent turns, output tokens and protocol errors have no normal cap.\n"
        f"- Emergency artifact-call safeguard: {calls}.\n"
        "- Hidden references, the canonical extraction and verifier are unavailable.\n\n"
        "Return your first JSON action now."
    )


def _write_pending_request(
    run_dir: Path, record: dict[str, Any], messages: list[Any], loaded: dict[str, Any]
) -> None:
    turn = record["trajectory"]["agent_turns"] + 1
    relative = f"turns/{turn:03d}-request.json"
    path = run_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, _request_payload(record, messages, loaded["action_schema"]))
    record["state"] = "awaiting_model"
    record["artifacts"]["pending_request"] = relative
    record["artifacts"]["pending_request_sha256"] = sha256_file(path)


def start_mini_multi_format_run(
    repo_root: Path, config: MiniMultiFormatStartConfig
) -> dict[str, Any]:
    """Prepare one run and its first request without contacting Ollama."""
    host = validate_local_ollama_host(config.host)
    if not isinstance(config.model, str) or not config.model.strip():
        raise RunnerError("Mini multi-format model name must be non-empty")
    loaded = load_mini_multi_format_case(repo_root, config.case_path, config.harness_path)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"mini-multiformat-run-{timestamp}-{secrets.token_hex(4)}"
    results_dir = resolve_repo_path(repo_root, config.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    run_dir = results_dir / run_id
    run_dir.mkdir()
    workspace = run_dir / "workspace"
    contamination = _copy_workspace(loaded["fixture_root"], workspace)
    messages = [
        {"role": "system", "content": loaded["system_prompt"]},
        {"role": "user", "content": _initial_user_message(loaded)},
    ]
    messages_path = run_dir / "messages.json"
    write_json(messages_path, messages)
    implementation_path = repo_root / "local_llm_benchmark/multi_format_mini.py"
    backend_path = repo_root / "local_llm_benchmark/multi_format_artifacts.py"
    pdftotext = shutil.which("pdftotext")
    if pdftotext is None:
        raise RunnerError("pdftotext is required for multi-format PDF reads")
    definitions = {
        "harness": loaded["harness_path"],
        "protocol": loaded["protocol_path"],
        "system_prompt": loaded["system_prompt_path"],
        "action_schema": loaded["action_schema_path"],
        "capability_inventory": loaded["capability_inventory_path"],
        "isolation_profile": loaded["isolation_profile_path"],
        "implementation": implementation_path,
        "artifact_backend": backend_path,
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
            "harness_id": HARNESS_ID,
            "harness_family": "project_mini_harness",
            **{
                f"{key}_path": path.relative_to(repo_root).as_posix()
                for key, path in definitions.items()
            },
            **{f"{key}_sha256": sha256_file(path) for key, path in definitions.items()},
            "git_commit": git_commit(repo_root),
        },
        "case": {
            "case_id": loaded["case"]["case_id"],
            "case_version": loaded["case"]["case_version"],
            "case_path": loaded["relative_case_path"],
            "case_definition_sha256": sha256_file(loaded["case_path"]),
            "task_sha256": sha256_file(loaded["task_path"]),
            "report_schema_sha256": sha256_file(loaded["schema_path"]),
            "ground_truth_sha256": sha256_file(loaded["truth_path"]),
            "reference_report_sha256": sha256_file(loaded["reference_report_path"]),
            "candidate_visible_files": list(ARTIFACTS),
        },
        "deployment": {
            "requested_model": config.model,
            "ollama_host": host,
            "ollama_version": None,
            "model": None,
            "options": loaded["protocol"]["inference_defaults"],
        },
        "limits": loaded["protocol"]["normal_capability_limits"],
        "safeguards": loaded["protocol"]["runaway_operation_safeguards"],
        "artifact_backend": {
            "pdftotext_path": str(Path(pdftotext).resolve()),
            "response_limit_bytes": 8192,
        },
        "trajectory": {
            "agent_turns": 0,
            "model_requests": 0,
            "tool_calls": 0,
            "failed_tool_calls": 0,
            "protocol_errors": 0,
            "repeated_queries": 0,
            "queries": {},
            "input_tokens": 0,
            "output_tokens": 0,
            "model_wall_time_seconds": 0.0,
            "tool_wall_time_seconds": 0.0,
            "active_wall_time_seconds": 0.0,
            "final_verification_wall_time_seconds": None,
        },
        "turns": [],
        "termination": None,
        "outcome": None,
        "verification": None,
        "environment": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "memory_total_bytes": memory_total_bytes(),
        },
        "execution_boundary": {
            "artifact_only_workspace": True,
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
        "inference_requests_made": 0,
        "next_action": "python3 -m local_llm_benchmark.multi_format_mini call",
    }


def _load_run(repo_root: Path, run_dir: Path) -> tuple[Path, dict[str, Any]]:
    resolved = resolve_repo_path(repo_root, run_dir)
    record = load_json(resolved / "run.json")
    if record.get("harness", {}).get("harness_id") != HARNESS_ID:
        raise RunnerError("Run does not belong to Mini multi-format v0.1")
    try:
        verify_workspace(resolved / record["artifacts"]["workspace"])
    except ArtifactToolError as exc:
        raise RunnerError(f"Mini multi-format workspace drifted: {exc}") from exc
    return resolved, record


def _validated_definition(repo_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    loaded = load_mini_multi_format_case(
        repo_root,
        Path(_normalized_relative_path(record["case"]["case_path"], "run case")),
        Path(_normalized_relative_path(record["harness"]["harness_path"], "run harness")),
    )
    paths = {
        "harness": loaded["harness_path"],
        "protocol": loaded["protocol_path"],
        "system_prompt": loaded["system_prompt_path"],
        "action_schema": loaded["action_schema_path"],
        "capability_inventory": loaded["capability_inventory_path"],
        "isolation_profile": loaded["isolation_profile_path"],
        "implementation": repo_root / "local_llm_benchmark/multi_format_mini.py",
        "artifact_backend": repo_root / "local_llm_benchmark/multi_format_artifacts.py",
    }
    mismatches = [
        f"{key}_sha256"
        for key, path in paths.items()
        if record["harness"].get(f"{key}_sha256") != sha256_file(path)
    ]
    case_hashes = {
        "case_definition_sha256": sha256_file(loaded["case_path"]),
        "task_sha256": sha256_file(loaded["task_path"]),
        "report_schema_sha256": sha256_file(loaded["schema_path"]),
        "ground_truth_sha256": sha256_file(loaded["truth_path"]),
        "reference_report_sha256": sha256_file(loaded["reference_report_path"]),
    }
    mismatches += [key for key, value in case_hashes.items() if record["case"].get(key) != value]
    if mismatches:
        raise RunnerError("Mini multi-format definition changed: " + ", ".join(mismatches))
    return loaded


def _append_audit(run_dir: Path, event: dict[str, Any]) -> None:
    path = run_dir / "trajectory.jsonl"
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def parse_mini_multi_format_action(response_text: str) -> dict[str, Any]:
    """Parse one exact Mini action without output repair."""
    try:
        value = json.loads(response_text)
    except json.JSONDecodeError as exc:
        return {"status": "invalid", "failure_code": "malformed_action", "reason": exc.msg, "action": None}
    if not isinstance(value, dict) or not isinstance(value.get("action"), str):
        return {"status": "invalid", "failure_code": "malformed_action", "reason": "Action must be an object with an action name.", "action": None}
    action = value["action"]
    shapes = {
        "list_artifacts": {"action"},
        "read_docx": {"action", "anchor"},
        "read_pdf": {"action", "page", "element"},
        "read_xlsx": {"action", "sheet", "range"},
        "finish_report": {"action", "report"},
    }
    valid_types = (
        action == "list_artifacts"
        or action == "read_docx" and isinstance(value.get("anchor"), str)
        or action == "read_pdf" and isinstance(value.get("page"), int) and not isinstance(value.get("page"), bool) and isinstance(value.get("element"), str)
        or action == "read_xlsx" and isinstance(value.get("sheet"), str) and isinstance(value.get("range"), str)
        or action == "finish_report" and isinstance(value.get("report"), dict)
    )
    if action not in shapes or set(value) != shapes[action] or not valid_types:
        return {"status": "invalid", "failure_code": "unsupported_or_malformed_action", "reason": "Action shape is not allowed.", "action": action}
    return {"status": "valid", "action": action, "value": value}


def _end(run_dir: Path, record: dict[str, Any], reason: str, runtime_success: bool) -> dict[str, Any]:
    record["state"] = "trajectory_complete_verification_pending"
    record["termination"] = {
        "reason": reason,
        "runtime_success": runtime_success,
        "agent_termination_valid": runtime_success and reason == "finish_report",
        "observed_at": utc_now(),
    }
    record["artifacts"]["pending_request"] = None
    record["artifacts"]["pending_request_sha256"] = None
    audit_path = run_dir / "trajectory.jsonl"
    record["artifacts"]["trajectory_sha256"] = sha256_file(audit_path) if audit_path.is_file() else None
    write_json(run_dir / "run.json", record)
    return {"run_id": record["run_id"], "run_dir": str(run_dir), "state": record["state"], "termination_reason": reason, "runtime_success": runtime_success, "next_action": "python3 -m local_llm_benchmark.multi_format_mini finalize"}


def call_mini_multi_format_model(repo_root: Path, run_dir: Path) -> dict[str, Any]:
    """Perform one explicitly invoked Ollama request and no tool action."""
    resolved, record = _load_run(repo_root, run_dir)
    if record.get("state") != "awaiting_model":
        raise RunnerError("Mini multi-format run is not awaiting a model call")
    _validated_definition(repo_root, record)
    trajectory = record["trajectory"]
    if trajectory["active_wall_time_seconds"] >= record["limits"]["maximum_active_wall_time_seconds"]:
        return _end(resolved, record, "maximum_active_wall_time_exceeded", False)
    request_path = _verified_relative_artifact(resolved, record["artifacts"]["pending_request"], record["artifacts"]["pending_request_sha256"], "pending request")
    payload = load_json(request_path)
    deployment = record["deployment"]
    client = OllamaClient(deployment["ollama_host"], timeout_seconds=float(deployment["options"]["request_timeout_seconds"]))
    turn_index = trajectory["agent_turns"] + 1
    request_index = trajectory["model_requests"] + 1
    stream_relative = f"turns/{turn_index:03d}-stream.ndjson"
    started = time.monotonic()
    phase = "inference"
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
            version = client.version()
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
        record["active_model_request"].update(
            {"finished_at": utc_now(), "status": "failed", "phase": phase}
        )
        return _end(resolved, record, _runtime_failure_type(exc, phase), False)
    duration = time.monotonic() - started
    response_relative = f"turns/{turn_index:03d}-response.txt"
    response_path = resolved / response_relative
    response_path.write_text(turn["content"] + "\n", encoding="utf-8")
    final_event = turn["final_event"]
    turn_record = {
        "turn": turn_index,
        "request_index": request_index,
        "request": request_path.relative_to(resolved).as_posix(),
        "request_sha256": sha256_file(request_path),
        "response": response_relative,
        "response_sha256": sha256_file(response_path),
        "stream": stream_relative,
        "stream_sha256": sha256_file(resolved / stream_relative),
        "done_reason": final_event.get("done_reason"),
        "wall_time_seconds": duration,
        "prompt_tokens": final_event.get("prompt_eval_count") or 0,
        "output_tokens": final_event.get("eval_count") or 0,
        "output_tokens_per_second": tokens_per_second(final_event.get("eval_count"), final_event.get("eval_duration")),
        "load_duration_seconds": nanoseconds_to_seconds(final_event.get("load_duration")),
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
    if deployment["model"] is None:
        deployment["ollama_version"] = version.get("version")
        deployment["model"] = {
            "requested_name": deployment["requested_model"],
            "resolved_name": model_tag.get("name") or model_tag.get("model"),
            "digest": model_tag.get("digest"),
            "size_bytes": model_tag.get("size"),
            "details": model_tag.get("details"),
            "capabilities": model_show.get("capabilities"),
            "parameters": model_show.get("parameters"),
            "template_sha256": sha256_text(model_show.get("template", "")),
        }
    record["state"] = "awaiting_action"
    record["artifacts"]["pending_request"] = None
    record["artifacts"]["pending_request_sha256"] = None
    write_json(resolved / "run.json", record)
    return {"run_id": record["run_id"], "run_dir": str(resolved), "state": record["state"], "turn": turn_index, "next_action": "python3 -m local_llm_benchmark.multi_format_mini step"}


def step_mini_multi_format_action(repo_root: Path, run_dir: Path) -> dict[str, Any]:
    """Execute one saved structured action against the shared backend."""
    resolved, record = _load_run(repo_root, run_dir)
    if record.get("state") != "awaiting_action":
        raise RunnerError("Mini multi-format run is not awaiting action processing")
    loaded = _validated_definition(repo_root, record)
    messages_path = _verified_relative_artifact(resolved, record["artifacts"]["messages"], record["artifacts"]["messages_sha256"], "messages")
    turn = record["turns"][-1]
    response_path = _verified_relative_artifact(resolved, turn["response"], turn["response_sha256"], "response")
    response_text = response_path.read_text(encoding="utf-8").rstrip("\n")
    parsed = parse_mini_multi_format_action(response_text)
    trajectory = record["trajectory"]
    started = time.monotonic()
    if parsed["status"] == "invalid":
        trajectory["protocol_errors"] += 1
        observation = {"ok": False, "action": parsed.get("action"), "failure_code": parsed["failure_code"], "failure_category": "model_protocol_failure", "reason": parsed["reason"], "terminal": False}
        turn["action_status"] = "protocol_error"
    else:
        value = parsed["value"]
        action = value["action"]
        turn["action"] = action
        if action == "finish_report":
            report_path = resolved / "candidate-report.json"
            write_json(report_path, value["report"])
            record["artifacts"]["candidate_report"] = report_path.name
            record["artifacts"]["candidate_report_sha256"] = sha256_file(report_path)
            observation = {"ok": True, "action": action, "report_sha256": sha256_file(report_path), "terminal": True}
            turn["action_status"] = "complete"
        else:
            trajectory["tool_calls"] += 1
            if trajectory["tool_calls"] > record["safeguards"]["maximum_artifact_tool_calls"]:
                trajectory["failed_tool_calls"] += 1
                observation = {"ok": False, "action": action, "failure_code": "artifact_call_safeguard_exceeded", "reason": "Emergency artifact-call safeguard exceeded.", "terminal": True}
                turn["action_status"] = "tool_error"
            else:
                request = {"operation": action, **{key: item for key, item in value.items() if key != "action"}}
                query_key = json.dumps(request, sort_keys=True, separators=(",", ":"))
                prior = trajectory["queries"].get(query_key, 0)
                trajectory["queries"][query_key] = prior + 1
                if prior:
                    trajectory["repeated_queries"] += 1
                try:
                    result = execute_artifact_request(
                        resolved / "workspace",
                        request,
                        pdftotext_path=Path(record["artifact_backend"]["pdftotext_path"]),
                    )
                except ArtifactToolError as exc:
                    trajectory["failed_tool_calls"] += 1
                    observation = {"ok": False, "action": action, "failure_code": exc.code, "reason": str(exc), "terminal": False}
                    turn["action_status"] = "tool_error"
                else:
                    observation = {**result, "action": action, "terminal": False}
                    turn["action_status"] = "complete"
    duration = time.monotonic() - started
    trajectory["tool_wall_time_seconds"] += duration
    trajectory["active_wall_time_seconds"] += duration
    observation["tool_wall_time_seconds"] = duration
    serialized_result = json.dumps(observation, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    _append_audit(resolved, {"schema_version": "1.0.0", "timestamp": utc_now(), "turn": turn["turn"], "parsed_action": parsed, "result_sha256": sha256_text(serialized_result), "observation": observation})
    record["artifacts"]["trajectory_sha256"] = sha256_file(resolved / "trajectory.jsonl")
    if observation.get("failure_code") == "artifact_call_safeguard_exceeded":
        return _end(resolved, record, "emergency_operation_safeguard_exceeded", True)
    if observation.get("terminal") and observation.get("action") == "finish_report":
        return _end(resolved, record, "finish_report", True)
    if trajectory["active_wall_time_seconds"] >= record["limits"]["maximum_active_wall_time_seconds"]:
        return _end(resolved, record, "maximum_active_wall_time_exceeded", False)
    messages = _load_list(messages_path, "messages")
    messages.append({"role": "assistant", "content": response_text})
    messages.append({"role": "user", "content": json.dumps({"tool_observation": observation}, ensure_ascii=False, separators=(",", ":"))})
    write_json(messages_path, messages)
    record["artifacts"]["messages_sha256"] = sha256_file(messages_path)
    _write_pending_request(resolved, record, messages, loaded)
    write_json(resolved / "run.json", record)
    return {"run_id": record["run_id"], "run_dir": str(resolved), "state": record["state"], "turn": turn["turn"], "action": turn.get("action"), "action_status": turn["action_status"], "observation": observation, "next_action": "python3 -m local_llm_benchmark.multi_format_mini call"}


def finalize_mini_multi_format_run(repo_root: Path, run_dir: Path) -> dict[str, Any]:
    """Apply hidden deterministic verification after Mini terminates."""
    resolved, record = _load_run(repo_root, run_dir)
    if record.get("state") != "trajectory_complete_verification_pending":
        raise RunnerError("Mini multi-format trajectory is not ready for verification")
    _validated_definition(repo_root, record)
    report = None
    if record["artifacts"].get("candidate_report"):
        report_path = _verified_relative_artifact(resolved, record["artifacts"]["candidate_report"], record["artifacts"]["candidate_report_sha256"], "candidate report")
        report = load_json(report_path)
    started = time.monotonic()
    verification = verify_multi_format_report(repo_root, Path(record["case"]["case_path"]), report)
    record["trajectory"]["final_verification_wall_time_seconds"] = time.monotonic() - started
    verification_path = resolved / "final-verification.json"
    write_json(verification_path, verification)
    runtime_success = bool(record["termination"]["runtime_success"])
    agent_valid = bool(record["termination"]["agent_termination_valid"])
    semantic = bool(verification["semantic_verified_success"])
    success = runtime_success and agent_valid and semantic
    record["state"] = "complete"
    record["completed_at"] = utc_now()
    record["outcome"] = {
        "runtime_success": runtime_success,
        "agent_termination_valid": agent_valid,
        "semantic_verifier_success": semantic,
        "semantic_verified_success": success,
        "verified_success": success,
        "strict_transport_compliance": report is not None and record["termination"]["reason"] == "finish_report",
        "failure_category": None if success else ("infrastructure_or_runtime_failure" if not runtime_success else "agent_failure" if not agent_valid else "task_or_verification_failure"),
        "trajectory_termination_reason": record["termination"]["reason"],
    }
    record["verification"] = verification
    record["execution_boundary"]["hidden_verification_executed"] = True
    record["artifacts"]["final_verification"] = verification_path.name
    record["artifacts"]["final_verification_sha256"] = sha256_file(verification_path)
    write_json(resolved / "run.json", record)
    return {"run_id": record["run_id"], "run_dir": str(resolved), "state": "complete", **record["outcome"], "verification": {"essential_pass_count": verification["essential_pass_count"], "essential_check_count": verification["essential_check_count"]}, "trajectory": record["trajectory"]}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser("start")
    start.add_argument("--model", required=True)
    start.add_argument("--case", type=Path, default=DEFAULT_CASE_PATH)
    start.add_argument("--harness", type=Path, default=DEFAULT_HARNESS_PATH)
    start.add_argument("--results-dir", type=Path, default=Path("results/agentic-runs"))
    start.add_argument("--host", default="http://127.0.0.1:11434")
    for name in ("call", "step", "finalize"):
        command = subparsers.add_parser(name)
        command.add_argument("--run-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    if args.command == "start":
        result = start_mini_multi_format_run(repo_root, MiniMultiFormatStartConfig(model=args.model, case_path=args.case, harness_path=args.harness, results_dir=args.results_dir, host=args.host))
    elif args.command == "call":
        result = call_mini_multi_format_model(repo_root, args.run_dir)
    elif args.command == "step":
        result = step_mini_multi_format_action(repo_root, args.run_dir)
    else:
        result = finalize_mini_multi_format_run(repo_root, args.run_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
