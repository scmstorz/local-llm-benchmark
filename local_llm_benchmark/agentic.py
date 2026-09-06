"""Stateful, sandbox-friendly Coding Track B harnesses."""

from __future__ import annotations

import ipaddress
import json
import platform
import secrets
import shutil
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from .coding import (
    load_coding_case,
    run_public_tests_in_workspace,
    verify_coding_workspace,
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


DEFAULT_TRACK_B_PROTOCOL_PATH = Path("tasks/coding/track-b/track-b-v0.2.json")
DEFAULT_MINI_HARNESS_PATH = Path("tasks/coding/track-b/mini-v0.2.json")
MINI_HARNESS_PROTOCOL_IDS = {
    "mini-v0.1": "coding-track-b-v0.1",
    "mini-v0.2": "coding-track-b-v0.2",
}


@dataclass(frozen=True)
class MiniAgentStartConfig:
    """Configuration captured before a Track B mini-harness trajectory."""

    model: str
    case_path: Path
    harness_path: Path = DEFAULT_MINI_HARNESS_PATH
    results_dir: Path = Path("results/agentic-runs")
    host: str = "http://127.0.0.1:11434"


def validate_local_ollama_host(value: str) -> str:
    """Return a normalized loopback Ollama origin or reject external hosts."""
    if not isinstance(value, str) or not value:
        raise RunnerError("Track B Ollama host must be a non-empty URL")
    parsed = urlsplit(value)
    if parsed.scheme != "http" or not parsed.hostname:
        raise RunnerError("Track B Ollama host must use HTTP on a loopback address")
    if parsed.username or parsed.password:
        raise RunnerError("Track B Ollama host must not contain credentials")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise RunnerError("Track B Ollama host must be an origin without path or query")
    hostname = parsed.hostname.casefold()
    try:
        is_loopback = ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        is_loopback = hostname == "localhost"
    if not is_loopback:
        raise RunnerError("Track B forbids a non-loopback Ollama host")
    try:
        parsed.port
    except ValueError as exc:
        raise RunnerError(f"Invalid Track B Ollama port: {exc}") from exc
    return value.rstrip("/")


def _normalized_relative_path(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise RunnerError(f"Expected a non-empty relative path for {context}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value != path.as_posix():
        raise RunnerError(f"Unsafe or non-normalized path for {context}: {value!r}")
    return value


def _matches_any(path: str, patterns: list[str]) -> bool:
    candidate = PurePosixPath(path)
    return any(candidate.match(pattern) for pattern in patterns)


def _load_list(path: Path, context: str) -> list[Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RunnerError(f"Required {context} does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RunnerError(f"Invalid JSON in {context} {path}: {exc}") from exc
    if not isinstance(value, list):
        raise RunnerError(f"Expected a JSON array in {context}: {path}")
    return value


def _positive_integer(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise RunnerError(f"{context} must be a positive integer")
    return value


def load_mini_harness(
    repo_root: Path,
    harness_path: Path = DEFAULT_MINI_HARNESS_PATH,
) -> dict[str, Any]:
    """Load and validate the draft mini-harness and shared Track B protocol."""
    resolved_harness_path = resolve_repo_path(repo_root, harness_path)
    harness = load_json(resolved_harness_path)
    if harness.get("schema_version") != "1.0.0":
        raise RunnerError("Unsupported mini-harness schema version")
    harness_id = harness.get("harness_id")
    expected_protocol_id = MINI_HARNESS_PROTOCOL_IDS.get(harness_id)
    if expected_protocol_id is None:
        raise RunnerError("Unexpected mini-harness identity")
    if harness.get("harness_family") != "project_mini_harness":
        raise RunnerError("Unexpected mini-harness family")
    expected_harness_status = {
        "mini-v0.1": "implementation_draft",
        "mini-v0.2": "qualified_for_capability_sweep",
    }[harness_id]
    if harness.get("status") != expected_harness_status:
        raise RunnerError(
            f"Mini-harness {harness_id} status must be {expected_harness_status}"
        )

    protocol_path = Path(
        _normalized_relative_path(harness.get("protocol_path"), "Track B protocol")
    )
    resolved_protocol_path = resolve_repo_path(repo_root, protocol_path)
    protocol = load_json(resolved_protocol_path)
    if protocol.get("schema_version") != "1.0.0":
        raise RunnerError("Unsupported Track B protocol schema version")
    if protocol.get("protocol_id") != expected_protocol_id:
        raise RunnerError("Unexpected Track B protocol identity")
    expected_protocol_status = {
        "coding-track-b-v0.1": "draft_not_frozen",
        "coding-track-b-v0.2": "frozen_for_capability_sweep",
    }[expected_protocol_id]
    if (
        protocol.get("status") != expected_protocol_status
        or protocol.get("track") != "B"
    ):
        raise RunnerError(
            f"Track B protocol {expected_protocol_id} status must be "
            f"{expected_protocol_status}"
        )

    budgets = protocol.get("budgets")
    if not isinstance(budgets, dict):
        raise RunnerError("Track B protocol must define budgets")
    for key in (
        "maximum_protocol_errors",
        "maximum_file_reads",
        "maximum_file_writes",
        "maximum_public_test_runs",
        "maximum_total_output_tokens",
        "maximum_wall_time_seconds",
    ):
        _positive_integer(budgets.get(key), f"budgets.{key}")
    if expected_protocol_id == "coding-track-b-v0.1":
        _positive_integer(
            budgets.get("maximum_agent_turns"),
            "budgets.maximum_agent_turns",
        )
    elif "maximum_agent_turns" in budgets:
        raise RunnerError("Track B v0.2 must not define a normal agent-turn limit")

    inference = protocol.get("inference_defaults")
    if not isinstance(inference, dict):
        raise RunnerError("Track B protocol must define inference_defaults")
    for key in ("num_ctx", "num_predict_per_turn", "request_timeout_seconds"):
        _positive_integer(inference.get(key), f"inference_defaults.{key}")
    temperature = inference.get("temperature")
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
        raise RunnerError("inference_defaults.temperature must be numeric")
    if isinstance(inference.get("seed"), bool) or not isinstance(
        inference.get("seed"), int
    ):
        raise RunnerError("inference_defaults.seed must be an integer")
    if not isinstance(inference.get("think"), (bool, str)):
        raise RunnerError("inference_defaults.think must be boolean or string")
    if not isinstance(inference.get("keep_alive"), str):
        raise RunnerError("inference_defaults.keep_alive must be a string")

    actions = harness.get("actions")
    expected_actions = [
        "read_file",
        "write_file",
        "replace_text",
        "run_public_tests",
        "finish",
    ]
    if actions != expected_actions:
        raise RunnerError("Mini-harness actions differ from the v0.1 contract")

    system_prompt_path = Path(
        _normalized_relative_path(
            harness.get("system_prompt_path"), "mini-harness system prompt"
        )
    )
    resolved_system_prompt_path = resolve_repo_path(repo_root, system_prompt_path)
    if not resolved_system_prompt_path.is_file():
        raise RunnerError("Mini-harness system prompt does not exist")

    action_schema_path: Path | None = None
    action_schema: dict[str, Any] | None = None
    if harness_id == "mini-v0.2":
        action_schema_path = resolve_repo_path(
            repo_root,
            Path(
                _normalized_relative_path(
                    harness.get("action_schema_path"),
                    "mini-harness action schema",
                )
            ),
        )
        action_schema = load_json(action_schema_path)
        if not isinstance(action_schema.get("oneOf"), list):
            raise RunnerError("Mini v0.2 action schema must define oneOf")
        if harness.get("action_protocol") != "ollama_json_schema_action_per_turn":
            raise RunnerError("Mini v0.2 must use the structured-output action protocol")

    return {
        "harness": harness,
        "harness_path": resolved_harness_path,
        "protocol": protocol,
        "protocol_path": resolved_protocol_path,
        "system_prompt": resolved_system_prompt_path.read_text(encoding="utf-8").strip(),
        "system_prompt_path": resolved_system_prompt_path,
        "action_schema": action_schema,
        "action_schema_path": action_schema_path,
    }


def load_track_b_case(
    repo_root: Path,
    case_path: Path,
    harness_path: Path = DEFAULT_MINI_HARNESS_PATH,
) -> dict[str, Any]:
    """Bind one Track A fixture to the shared Track B mini-harness contract."""
    harness = load_mini_harness(repo_root, harness_path)
    loaded = load_coding_case(repo_root, case_path)
    case = loaded["case"]
    selected = {
        item.get("case_path"): item
        for item in harness["protocol"].get("task_subset", [])
        if isinstance(item, dict)
    }
    relative_case_path = loaded["case_path"].relative_to(repo_root).as_posix()
    if relative_case_path not in selected:
        raise RunnerError(
            f"Coding case is outside the selected Track B pilot subset: {relative_case_path}"
        )
    if selected[relative_case_path].get("case_id") != case["case_id"]:
        raise RunnerError("Track B task subset case identity mismatch")
    if loaded["artifact_contract"]["format"] != "whole_file_envelope":
        raise RunnerError("Track B mini harness requires a whole-file Track A base case")

    return {**loaded, **harness, "relative_case_path": relative_case_path}


def parse_mini_agent_action(response_text: str) -> dict[str, Any]:
    """Parse one strict mini-harness action without repairing model output."""
    stripped = response_text.strip()
    if not stripped:
        return {
            "status": "invalid",
            "failure_code": "empty_action",
            "reason": "The model returned no visible action.",
            "action": None,
        }
    try:
        value = json.loads(stripped)
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
    action = value.get("action")
    schemas: dict[str, tuple[set[str], set[str]]] = {
        "read_file": ({"action", "path"}, {"action", "path"}),
        "write_file": (
            {"action", "path", "content"},
            {"action", "path", "content"},
        ),
        "replace_text": (
            {"action", "path", "old", "new"},
            {"action", "path", "old", "new"},
        ),
        "run_public_tests": ({"action"}, {"action"}),
        "finish": ({"action"}, {"action", "summary"}),
    }
    if action not in schemas:
        return {
            "status": "invalid",
            "failure_code": "unknown_action",
            "reason": f"Unknown action: {action!r}",
            "action": action if isinstance(action, str) else None,
        }
    required, allowed = schemas[action]
    missing = sorted(required - set(value))
    extra = sorted(set(value) - allowed)
    if missing or extra:
        return {
            "status": "invalid",
            "failure_code": "malformed_action",
            "reason": f"Action fields mismatch; missing={missing}, extra={extra}",
            "action": action,
        }
    for key in required - {"action"}:
        if not isinstance(value.get(key), str):
            return {
                "status": "invalid",
                "failure_code": "malformed_action",
                "reason": f"Action field {key!r} must be a string.",
                "action": action,
            }
    if "summary" in value and not isinstance(value["summary"], str):
        return {
            "status": "invalid",
            "failure_code": "malformed_action",
            "reason": "Action field 'summary' must be a string.",
            "action": action,
        }
    return {"status": "valid", "failure_code": None, "action": action, "value": value}


def _initial_user_message(loaded: dict[str, Any]) -> str:
    case = loaded["case"]
    contract = loaded["artifact_contract"]
    budgets = loaded["protocol"]["budgets"]
    task_text = loaded["task_path"].read_text(encoding="utf-8").strip()
    readable = "\n".join(f"- {path}" for path in case["candidate_context"]["files"])
    writable = "\n".join(f"- {pattern}" for pattern in contract["allowed_path_globs"])
    turn_budget = budgets.get("maximum_agent_turns")
    turn_line = (
        f"- Agent turns: {turn_budget}\n"
        if turn_budget is not None
        else "- Agent turns: recorded as trajectory evidence; no normal turn cap.\n"
    )
    return (
        f"# Task\n\n{task_text}\n\n"
        f"# Candidate-visible files\n\n{readable}\n\n"
        f"# Writable path patterns\n\n{writable}\n\n"
        "# Run budgets\n\n"
        f"{turn_line}"
        f"- File reads: {budgets['maximum_file_reads']}\n"
        f"- File writes or replacements: {budgets['maximum_file_writes']}\n"
        f"- Public test runs: {budgets['maximum_public_test_runs']}\n"
        "- Hidden tests are unavailable until final controller verification.\n\n"
        "Return your first JSON action now."
    )


def _request_payload(
    record: dict[str, Any],
    messages: list[Any],
    action_schema: dict[str, Any] | None,
) -> dict[str, Any]:
    inference = record["deployment"]["options"]
    payload = {
        "model": record["deployment"]["requested_model"],
        "messages": messages,
        "stream": True,
        "think": inference["think"],
        "keep_alive": inference["keep_alive"],
        "options": {
            "temperature": inference["temperature"],
            "seed": inference["seed"],
            "num_ctx": inference["num_ctx"],
            "num_predict": inference["num_predict_per_turn"],
        },
    }
    if action_schema is not None:
        payload["format"] = action_schema
    return payload


def _write_pending_request(
    run_dir: Path,
    record: dict[str, Any],
    messages: list[Any],
    loaded: dict[str, Any],
) -> None:
    next_turn = record["trajectory_metrics"]["agent_turns"] + 1
    relative = f"turns/{next_turn:03d}-request.json"
    path = run_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, _request_payload(record, messages, loaded["action_schema"]))
    record["state"] = "awaiting_model"
    record["artifacts"]["pending_request"] = relative
    record["artifacts"]["pending_request_sha256"] = sha256_file(path)


def start_mini_agent_run(
    repo_root: Path,
    config: MiniAgentStartConfig,
) -> dict[str, Any]:
    """Create a Track B run and its first model request without contacting Ollama."""
    host = validate_local_ollama_host(config.host)
    if not isinstance(config.model, str) or not config.model.strip():
        raise RunnerError("Track B model name must be non-empty")
    loaded = load_track_b_case(repo_root, config.case_path, config.harness_path)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"agentic-run-{timestamp}-{secrets.token_hex(4)}"
    results_dir = resolve_repo_path(repo_root, config.results_dir)
    run_dir = results_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    workspace = run_dir / "workspace"
    shutil.copytree(loaded["fixture_root"], workspace)

    inference = loaded["protocol"]["inference_defaults"]
    messages: list[dict[str, str]] = [
        {"role": "system", "content": loaded["system_prompt"]},
        {"role": "user", "content": _initial_user_message(loaded)},
    ]
    messages_path = run_dir / "messages.json"
    write_json(messages_path, messages)
    record: dict[str, Any] = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "track": "B",
        "study_mode": loaded["protocol"]["study_mode"],
        "state": "initializing",
        "started_at": utc_now(),
        "completed_at": None,
        "harness": {
            "harness_id": loaded["harness"]["harness_id"],
            "harness_family": loaded["harness"]["harness_family"],
            "harness_status": loaded["harness"]["status"],
            "harness_path": loaded["harness_path"].relative_to(repo_root).as_posix(),
            "harness_sha256": sha256_file(loaded["harness_path"]),
            "protocol_path": loaded["protocol_path"].relative_to(repo_root).as_posix(),
            "protocol_sha256": sha256_file(loaded["protocol_path"]),
            "system_prompt_path": loaded["system_prompt_path"].relative_to(repo_root).as_posix(),
            "system_prompt_sha256": sha256_file(loaded["system_prompt_path"]),
            "action_schema_path": (
                loaded["action_schema_path"].relative_to(repo_root).as_posix()
                if loaded["action_schema_path"] is not None
                else None
            ),
            "action_schema_sha256": (
                sha256_file(loaded["action_schema_path"])
                if loaded["action_schema_path"] is not None
                else None
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
            "pre_run_task_features": loaded["card"]["pre_run_task_features"],
            "candidate_visible_files": loaded["case"]["candidate_context"]["files"],
            "allowed_write_globs": loaded["artifact_contract"]["allowed_path_globs"],
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
        "budgets": loaded["protocol"]["budgets"],
        "trajectory_metrics": {
            "agent_turns": 0,
            "tool_calls": 0,
            "failed_tool_calls": 0,
            "protocol_errors": 0,
            "file_reads": 0,
            "file_writes": 0,
            "public_test_runs": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "active_wall_time_seconds": 0.0,
            "time_to_first_successful_public_verification_seconds": None,
        },
        "turns": [],
        "termination": None,
        "outcome": None,
        "environment": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor() or None,
            "memory_total_bytes": memory_total_bytes(),
            "python_version": platform.python_version(),
        },
        "artifacts": {
            "messages": "messages.json",
            "messages_sha256": sha256_file(messages_path),
            "workspace": "workspace",
            "trajectory": "trajectory.jsonl",
            "trajectory_sha256": None,
            "pending_request": None,
            "pending_request_sha256": None,
            "final_verification": None,
            "final_verification_sha256": None,
            "candidate_files_manifest": None,
            "candidate_files_manifest_sha256": None,
        },
    }
    _write_pending_request(run_dir, record, messages, loaded)
    write_json(run_dir / "run.json", record)
    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "state": record["state"],
        "next_action": "coding-agent-mini-call",
        "model": config.model,
        "case_id": loaded["case"]["case_id"],
    }


def _load_mini_run(repo_root: Path, run_dir: Path) -> tuple[Path, dict[str, Any]]:
    resolved_run_dir = resolve_repo_path(repo_root, run_dir)
    if not resolved_run_dir.is_dir():
        raise RunnerError(f"Agentic run directory does not exist: {resolved_run_dir}")
    record = load_json(resolved_run_dir / "run.json")
    harness = record.get("harness")
    if record.get("track") != "B" or not isinstance(harness, dict):
        raise RunnerError("Run is not a Coding Track B record")
    if harness.get("harness_id") not in MINI_HARNESS_PROTOCOL_IDS:
        raise RunnerError("Run does not belong to a supported mini harness")
    return resolved_run_dir, record


def _validated_current_mini_definition(
    repo_root: Path,
    record: dict[str, Any],
) -> dict[str, Any]:
    """Reject definition drift before another model or tool step executes."""
    case = record.get("case")
    harness = record.get("harness")
    if not isinstance(case, dict) or not isinstance(harness, dict):
        raise RunnerError("Mini-agent run is missing case or harness identity")
    loaded = load_track_b_case(
        repo_root,
        Path(_normalized_relative_path(case.get("case_path"), "run case")),
        Path(_normalized_relative_path(harness.get("harness_path"), "run harness")),
    )
    observed = {
        "harness.harness_sha256": sha256_file(loaded["harness_path"]),
        "harness.protocol_sha256": sha256_file(loaded["protocol_path"]),
        "harness.system_prompt_sha256": sha256_file(loaded["system_prompt_path"]),
        "harness.action_schema_path": (
            loaded["action_schema_path"].relative_to(repo_root).as_posix()
            if loaded["action_schema_path"] is not None
            else None
        ),
        "harness.action_schema_sha256": (
            sha256_file(loaded["action_schema_path"])
            if loaded["action_schema_path"] is not None
            else None
        ),
        "case.case_id": loaded["case"]["case_id"],
        "case.case_version": loaded["case"]["case_version"],
        "case.case_definition_sha256": sha256_file(loaded["case_path"]),
        "case.fixture_manifest_sha256": loaded["manifest_sha256"],
        "case.task_sha256": loaded["task_sha256"],
        "case.benchmark_card_sha256": sha256_file(loaded["card_path"]),
        "case.verifier_version": loaded["case"]["verification"]["version"],
        "case.hidden_test_sha256": loaded["hidden_test_sha256"],
    }
    recorded = {
        "harness.harness_sha256": harness.get("harness_sha256"),
        "harness.protocol_sha256": harness.get("protocol_sha256"),
        "harness.system_prompt_sha256": harness.get("system_prompt_sha256"),
        "harness.action_schema_path": harness.get("action_schema_path"),
        "harness.action_schema_sha256": harness.get("action_schema_sha256"),
        "case.case_id": case.get("case_id"),
        "case.case_version": case.get("case_version"),
        "case.case_definition_sha256": case.get("case_definition_sha256"),
        "case.fixture_manifest_sha256": case.get("fixture_manifest_sha256"),
        "case.task_sha256": case.get("task_sha256"),
        "case.benchmark_card_sha256": case.get("benchmark_card_sha256"),
        "case.verifier_version": case.get("verifier_version"),
        "case.hidden_test_sha256": case.get("hidden_test_sha256"),
    }
    mismatches = sorted(
        key for key, value in observed.items() if recorded.get(key) != value
    )
    if mismatches:
        raise RunnerError(
            "Mini-agent benchmark definition changed after run start: "
            + ", ".join(mismatches)
        )
    return loaded


def _verified_relative_artifact(
    run_dir: Path,
    relative: Any,
    expected_sha256: Any,
    context: str,
) -> Path:
    normalized = _normalized_relative_path(relative, context)
    path = run_dir.joinpath(*PurePosixPath(normalized).parts)
    if not path.is_file() or path.is_symlink():
        raise RunnerError(f"Missing or unsafe {context}: {path}")
    if not isinstance(expected_sha256, str) or sha256_file(path) != expected_sha256:
        raise RunnerError(f"{context} hash mismatch")
    return path


def _collect_ollama_turn(
    client: OllamaClient,
    payload: dict[str, Any],
    stream_path: Path,
) -> dict[str, Any]:
    started = time.perf_counter()
    first_content_seconds: float | None = None
    content_parts: list[str] = []
    thinking_parts: list[str] = []
    final_event: dict[str, Any] | None = None
    with stream_path.open("w", encoding="utf-8") as stream_file:
        for event in client.stream_chat(payload):
            stream_file.write(
                json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
            )
            message = event.get("message") or {}
            content = message.get("content") or ""
            thinking = message.get("thinking") or ""
            if content and first_content_seconds is None:
                first_content_seconds = time.perf_counter() - started
            if content:
                content_parts.append(content)
            if thinking:
                thinking_parts.append(thinking)
            if event.get("done") is True:
                final_event = event
    if final_event is None:
        raise RunnerError("Ollama stream ended without a final done=true event")
    return {
        "content": "".join(content_parts),
        "thinking": "".join(thinking_parts),
        "final_event": final_event,
        "wall_time_seconds": time.perf_counter() - started,
        "time_to_first_content_seconds": first_content_seconds,
    }


def call_mini_agent_model(repo_root: Path, run_dir: Path) -> dict[str, Any]:
    """Execute one model turn only; never apply actions or execute candidate code."""
    resolved_run_dir, record = _load_mini_run(repo_root, run_dir)
    if record.get("state") != "awaiting_model":
        raise RunnerError("Mini-agent run is not awaiting a model turn")
    _validated_current_mini_definition(repo_root, record)
    metrics = record["trajectory_metrics"]
    maximum_agent_turns = record["budgets"].get("maximum_agent_turns")
    if (
        maximum_agent_turns is not None
        and metrics["agent_turns"] >= maximum_agent_turns
    ):
        raise RunnerError("Mini-agent turn budget is already exhausted")

    request_path = _verified_relative_artifact(
        resolved_run_dir,
        record["artifacts"]["pending_request"],
        record["artifacts"]["pending_request_sha256"],
        "pending model request",
    )
    request_payload = load_json(request_path)
    deployment = record["deployment"]
    client = OllamaClient(
        deployment["ollama_host"],
        timeout_seconds=float(deployment["options"]["request_timeout_seconds"]),
    )
    turn_index = metrics["agent_turns"] + 1
    stream_relative = f"turns/{turn_index:03d}-stream.ndjson"
    response_relative = f"turns/{turn_index:03d}-response.txt"
    thinking_relative = f"turns/{turn_index:03d}-thinking.txt"
    contact_started = time.perf_counter()
    failure_phase = "inference"
    version_response: dict[str, Any] | None = None
    model_tag: dict[str, Any] | None = None
    model_show: dict[str, Any] | None = None
    try:
        if deployment["model"] is None:
            failure_phase = "ollama_version"
            version_response = client.version()
            failure_phase = "model_resolution"
            model_tag = find_model(client.list_models(), deployment["requested_model"])
            failure_phase = "model_inspection"
            model_show = client.show_model(deployment["requested_model"])
        failure_phase = "inference"
        turn = _collect_ollama_turn(
            client,
            request_payload,
            resolved_run_dir / stream_relative,
        )
    except Exception as exc:
        failure_duration = time.perf_counter() - contact_started
        metrics["active_wall_time_seconds"] += failure_duration
        failure_code = (
            "model_load_failure"
            if failure_phase in {"model_resolution", "model_inspection"}
            else "runtime_failure"
        )
        record["state"] = "infrastructure_failed"
        record["completed_at"] = utc_now()
        record["termination"] = {
            "reason": failure_code,
            "agent_finish_action": False,
        }
        record["outcome"] = {
            "runtime_success": False,
            "agent_completed": False,
            "verifier_success": None,
            "verified_success": False,
            "runtime_failure_code": failure_code,
            "task_failure_code": None,
        }
        write_json(
            resolved_run_dir / "failure.json",
            {
                "schema_version": "1.0.0",
                "run_id": record["run_id"],
                "failed_at": utc_now(),
                "failure_phase": failure_phase,
                "duration_seconds": failure_duration,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        write_json(resolved_run_dir / "run.json", record)
        raise

    call_wall_time_seconds = time.perf_counter() - contact_started

    response_path = resolved_run_dir / response_relative
    response_path.write_text(turn["content"] + "\n", encoding="utf-8")
    thinking_path = resolved_run_dir / thinking_relative
    if turn["thinking"]:
        thinking_path.write_text(turn["thinking"] + "\n", encoding="utf-8")
    final_event = turn["final_event"]
    turn_record = {
        "turn": turn_index,
        "request": request_path.relative_to(resolved_run_dir).as_posix(),
        "request_sha256": sha256_file(request_path),
        "response": response_relative,
        "response_sha256": sha256_file(response_path),
        "thinking": thinking_relative if turn["thinking"] else None,
        "thinking_sha256": (
            sha256_file(thinking_path) if turn["thinking"] else None
        ),
        "stream": stream_relative,
        "stream_sha256": sha256_file(resolved_run_dir / stream_relative),
        "done_reason": final_event.get("done_reason"),
        "wall_time_seconds": call_wall_time_seconds,
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
    metrics["agent_turns"] += 1
    metrics["input_tokens"] += turn_record["prompt_tokens"]
    metrics["output_tokens"] += turn_record["output_tokens"]
    metrics["active_wall_time_seconds"] += call_wall_time_seconds
    if version_response is not None and model_tag is not None and model_show is not None:
        record["deployment"]["ollama_version"] = version_response.get("version")
        record["deployment"]["model"] = {
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
    write_json(resolved_run_dir / "run.json", record)
    return {
        "run_id": record["run_id"],
        "run_dir": str(resolved_run_dir),
        "state": record["state"],
        "turn": turn_index,
        "done_reason": final_event.get("done_reason"),
        "output_tokens": turn_record["output_tokens"],
        "next_action": "coding-agent-mini-step",
    }


def _safe_workspace_file(workspace: Path, relative: str) -> Path:
    path = workspace.joinpath(*PurePosixPath(relative).parts)
    if path.is_symlink() or not path.is_file():
        raise RunnerError(f"Workspace path is not an existing regular file: {relative}")
    try:
        path.resolve().relative_to(workspace.resolve())
    except ValueError as exc:
        raise RunnerError(f"Workspace path escapes the fixture: {relative}") from exc
    return path


def _truncate(value: str, maximum: int = 12000) -> str:
    if len(value) <= maximum:
        return value
    return value[:maximum] + f"\n[truncated after {maximum} characters]"


def _public_test_observation(result: dict[str, Any]) -> dict[str, Any]:
    public = result.get("public")
    runtime = result.get("runtime")
    return {
        "ok": result["passed"],
        "failure_code": result.get("failure_code"),
        "runtime": (
            None
            if runtime is None
            else {
                "status": runtime["status"],
                "passed": runtime["passed"],
                "exit_code": runtime["exit_code"],
                "stdout": _truncate(runtime["stdout"]),
                "stderr": _truncate(runtime["stderr"]),
            }
        ),
        "public_tests": (
            None
            if public is None
            else {
                "status": public["status"],
                "passed": public["passed"],
                "exit_code": public["exit_code"],
                "stdout": _truncate(public["stdout"]),
                "stderr": _truncate(public["stderr"]),
            }
        ),
        "hidden_tests_executed": False,
    }


def execute_mini_agent_action(
    repo_root: Path,
    loaded: dict[str, Any],
    workspace: Path,
    action: dict[str, Any],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    """Apply one validated mini action under the frozen path and tool budgets."""
    name = action["action"]
    budgets = loaded["protocol"]["budgets"]
    readable = set(loaded["case"]["candidate_context"]["files"])
    contract = loaded["artifact_contract"]
    allowed_writes = contract["allowed_path_globs"]

    if name == "finish":
        return {
            "ok": True,
            "action": name,
            "summary": action.get("summary", ""),
            "terminal": True,
        }
    metrics["tool_calls"] += 1
    if name == "run_public_tests":
        if metrics["public_test_runs"] >= budgets["maximum_public_test_runs"]:
            return {
                "ok": False,
                "action": name,
                "failure_code": "public_test_budget_exceeded",
                "terminal": False,
            }
        started = time.perf_counter()
        result = run_public_tests_in_workspace(
            repo_root,
            Path(loaded["relative_case_path"]),
            workspace,
        )
        metrics["active_wall_time_seconds"] += time.perf_counter() - started
        metrics["public_test_runs"] += 1
        if (
            result["passed"]
            and metrics["time_to_first_successful_public_verification_seconds"] is None
        ):
            metrics["time_to_first_successful_public_verification_seconds"] = metrics[
                "active_wall_time_seconds"
            ]
        return {"action": name, "terminal": False, **_public_test_observation(result)}

    try:
        relative = _normalized_relative_path(action.get("path"), f"{name} action")
    except RunnerError as exc:
        return {
            "ok": False,
            "action": name,
            "failure_code": "tool_scope_violation",
            "reason": str(exc),
            "terminal": False,
        }
    if name == "read_file":
        if metrics["file_reads"] >= budgets["maximum_file_reads"]:
            return {
                "ok": False,
                "action": name,
                "path": relative,
                "failure_code": "file_read_budget_exceeded",
                "terminal": False,
            }
        if relative not in readable:
            return {
                "ok": False,
                "action": name,
                "path": relative,
                "failure_code": "tool_scope_violation",
                "reason": "Path is not candidate-visible.",
                "terminal": False,
            }
        try:
            path = _safe_workspace_file(workspace, relative)
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError, RunnerError) as exc:
            return {
                "ok": False,
                "action": name,
                "path": relative,
                "failure_code": "tool_failure",
                "reason": str(exc),
                "terminal": False,
            }
        metrics["file_reads"] += 1
        return {
            "ok": True,
            "action": name,
            "path": relative,
            "content": content,
            "sha256": sha256_text(content),
            "size_bytes": len(content.encode("utf-8")),
            "terminal": False,
        }

    if metrics["file_writes"] >= budgets["maximum_file_writes"]:
        return {
            "ok": False,
            "action": name,
            "path": relative,
            "failure_code": "file_write_budget_exceeded",
            "terminal": False,
        }
    if not _matches_any(relative, allowed_writes):
        return {
            "ok": False,
            "action": name,
            "path": relative,
            "failure_code": "tool_scope_violation",
            "reason": "Path is outside the writable scope.",
            "terminal": False,
        }
    try:
        path = _safe_workspace_file(workspace, relative)
        before = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError, RunnerError) as exc:
        return {
            "ok": False,
            "action": name,
            "path": relative,
            "failure_code": "tool_failure",
            "reason": str(exc),
            "terminal": False,
        }

    if name == "write_file":
        after = action["content"]
    elif name == "replace_text":
        old = action["old"]
        if not old:
            return {
                "ok": False,
                "action": name,
                "path": relative,
                "failure_code": "tool_failure",
                "reason": "The old text must not be empty.",
                "terminal": False,
            }
        occurrences = before.count(old)
        if occurrences != 1:
            return {
                "ok": False,
                "action": name,
                "path": relative,
                "failure_code": "tool_failure",
                "reason": f"Expected exactly one old-text occurrence; found {occurrences}.",
                "terminal": False,
            }
        after = before.replace(old, action["new"], 1)
    else:
        raise RunnerError(f"Unhandled validated mini action: {name}")

    maximum_bytes = contract["maximum_bytes"]
    if len(after.encode("utf-8")) > maximum_bytes:
        return {
            "ok": False,
            "action": name,
            "path": relative,
            "failure_code": "tool_failure",
            "reason": f"Replacement exceeds {maximum_bytes} bytes.",
            "terminal": False,
        }
    try:
        path.write_text(after, encoding="utf-8")
    except OSError as exc:
        return {
            "ok": False,
            "action": name,
            "path": relative,
            "failure_code": "tool_failure",
            "reason": str(exc),
            "terminal": False,
        }
    metrics["file_writes"] += 1
    return {
        "ok": True,
        "action": name,
        "path": relative,
        "changed": before != after,
        "before_sha256": sha256_text(before),
        "after_sha256": sha256_text(after),
        "size_bytes": len(after.encode("utf-8")),
        "terminal": False,
    }


def _append_trajectory(run_dir: Path, event: dict[str, Any]) -> None:
    with (run_dir / "trajectory.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def _persist_candidate_files(
    run_dir: Path,
    workspace: Path,
    loaded: dict[str, Any],
    verification: dict[str, Any],
) -> str | None:
    changed_paths = verification.get("integrity", {}).get("changed_paths", [])
    allowed = loaded["artifact_contract"]["allowed_path_globs"]
    files: list[dict[str, Any]] = []
    for relative in changed_paths:
        if relative not in loaded["baseline_inventory"] or not _matches_any(relative, allowed):
            continue
        try:
            source = _safe_workspace_file(workspace, relative)
        except RunnerError:
            continue
        destination = run_dir / "candidate-files" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        files.append(
            {
                "path": relative,
                "baseline_sha256": loaded["baseline_inventory"][relative]["sha256"],
                "candidate_sha256": sha256_file(source),
                "size_bytes": source.stat().st_size,
            }
        )
    if not files:
        return None
    relative_manifest = "candidate-files.json"
    write_json(
        run_dir / relative_manifest,
        {"schema_version": "1.0.0", "files": files},
    )
    return relative_manifest


def _finalize_mini_run(
    repo_root: Path,
    run_dir: Path,
    record: dict[str, Any],
    loaded: dict[str, Any],
    termination_reason: str,
) -> dict[str, Any]:
    workspace = run_dir / record["artifacts"]["workspace"]
    started = time.perf_counter()
    verification = verify_coding_workspace(
        repo_root,
        Path(record["case"]["case_path"]),
        workspace,
    )
    record["trajectory_metrics"]["active_wall_time_seconds"] += (
        time.perf_counter() - started
    )
    verification_relative = "final-verification.json"
    write_json(run_dir / verification_relative, verification)
    candidate_manifest = _persist_candidate_files(
        run_dir,
        workspace,
        loaded,
        verification,
    )
    agent_completed = termination_reason == "finish_action"
    verified_success = agent_completed and verification["verified_success"]
    record["state"] = "complete"
    record["completed_at"] = utc_now()
    record["termination"] = {
        "reason": termination_reason,
        "agent_finish_action": agent_completed,
    }
    record["outcome"] = {
        "runtime_success": True,
        "agent_completed": agent_completed,
        "verifier_success": verification["verified_success"],
        "verified_success": verified_success,
        "agent_failure_code": None if agent_completed else termination_reason,
        "task_failure_code": verification.get("failure_code"),
    }
    record["artifacts"]["final_verification"] = verification_relative
    record["artifacts"]["final_verification_sha256"] = sha256_file(
        run_dir / verification_relative
    )
    record["artifacts"]["candidate_files_manifest"] = candidate_manifest
    record["artifacts"]["candidate_files_manifest_sha256"] = (
        sha256_file(run_dir / candidate_manifest) if candidate_manifest else None
    )
    trajectory_path = run_dir / record["artifacts"]["trajectory"]
    record["artifacts"]["trajectory_sha256"] = (
        sha256_file(trajectory_path) if trajectory_path.is_file() else None
    )
    record["artifacts"]["pending_request"] = None
    record["artifacts"]["pending_request_sha256"] = None
    record["environment"] = {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor() or None,
        "memory_total_bytes": memory_total_bytes(),
        "python_version": platform.python_version(),
    }
    write_json(run_dir / "run.json", record)
    return {
        "run_id": record["run_id"],
        "run_dir": str(run_dir),
        "state": "complete",
        "termination_reason": termination_reason,
        "verifier_success": verification["verified_success"],
        "verified_success": verified_success,
        "failure_code": (
            None
            if verified_success
            else (verification.get("failure_code") or termination_reason)
        ),
        "trajectory_metrics": record["trajectory_metrics"],
    }


def step_mini_agent_action(repo_root: Path, run_dir: Path) -> dict[str, Any]:
    """Apply one saved model action and either queue the next turn or verify."""
    resolved_run_dir, record = _load_mini_run(repo_root, run_dir)
    if record.get("state") != "awaiting_action":
        raise RunnerError("Mini-agent run is not awaiting action processing")
    loaded = _validated_current_mini_definition(repo_root, record)
    messages_path = _verified_relative_artifact(
        resolved_run_dir,
        record["artifacts"]["messages"],
        record["artifacts"]["messages_sha256"],
        "mini-agent messages",
    )
    last_turn = record["turns"][-1]
    response_path = _verified_relative_artifact(
        resolved_run_dir,
        last_turn["response"],
        last_turn["response_sha256"],
        "model response",
    )
    response_text = response_path.read_text(encoding="utf-8").rstrip("\n")
    metrics = record["trajectory_metrics"]
    budgets = record["budgets"]

    if metrics["output_tokens"] > budgets["maximum_total_output_tokens"]:
        last_turn["action_status"] = "not_executed_output_budget_exceeded"
        _append_trajectory(
            resolved_run_dir,
            {
                "schema_version": "1.0.0",
                "timestamp": utc_now(),
                "turn": last_turn["turn"],
                "response_sha256": last_turn["response_sha256"],
                "parsed_action": None,
                "observation": {
                    "ok": False,
                    "action": None,
                    "failure_code": "maximum_total_output_tokens_exceeded",
                    "terminal": True,
                },
            },
        )
        write_json(resolved_run_dir / "run.json", record)
        return _finalize_mini_run(
            repo_root,
            resolved_run_dir,
            record,
            loaded,
            "maximum_total_output_tokens_exceeded",
        )

    parsed = parse_mini_agent_action(response_text)
    if parsed["status"] == "invalid":
        metrics["protocol_errors"] += 1
        observation = {
            "ok": False,
            "action": parsed.get("action"),
            "failure_code": parsed["failure_code"],
            "reason": parsed["reason"],
            "terminal": False,
        }
        last_turn["action"] = parsed.get("action")
        last_turn["action_status"] = "protocol_error"
    else:
        action = parsed["value"]
        observation = execute_mini_agent_action(
            repo_root,
            loaded,
            resolved_run_dir / record["artifacts"]["workspace"],
            action,
            metrics,
        )
        if not observation["ok"]:
            metrics["failed_tool_calls"] += 1
        last_turn["action"] = action["action"]
        last_turn["action_status"] = "complete" if observation["ok"] else "tool_error"

    _append_trajectory(
        resolved_run_dir,
        {
            "schema_version": "1.0.0",
            "timestamp": utc_now(),
            "turn": last_turn["turn"],
            "response_sha256": last_turn["response_sha256"],
            "parsed_action": parsed,
            "observation": observation,
        },
    )

    termination_reason = None
    if observation.get("terminal") and observation.get("action") == "finish":
        termination_reason = "finish_action"
    elif metrics["output_tokens"] >= budgets["maximum_total_output_tokens"]:
        termination_reason = "maximum_total_output_tokens_exceeded"
    elif metrics["protocol_errors"] >= budgets["maximum_protocol_errors"]:
        termination_reason = "maximum_protocol_errors_exceeded"
    elif metrics["active_wall_time_seconds"] >= budgets["maximum_wall_time_seconds"]:
        termination_reason = "maximum_wall_time_exceeded"
    elif (
        budgets.get("maximum_agent_turns") is not None
        and metrics["agent_turns"] >= budgets["maximum_agent_turns"]
    ):
        termination_reason = "maximum_agent_turns_exceeded"

    if termination_reason is not None:
        write_json(resolved_run_dir / "run.json", record)
        return _finalize_mini_run(
            repo_root,
            resolved_run_dir,
            record,
            loaded,
            termination_reason,
        )

    messages = _load_list(messages_path, "mini-agent messages")
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
    trajectory_path = resolved_run_dir / record["artifacts"]["trajectory"]
    record["artifacts"]["trajectory_sha256"] = sha256_file(trajectory_path)
    _write_pending_request(resolved_run_dir, record, messages, loaded)
    write_json(resolved_run_dir / "run.json", record)
    return {
        "run_id": record["run_id"],
        "run_dir": str(resolved_run_dir),
        "state": record["state"],
        "turn": last_turn["turn"],
        "action": last_turn["action"],
        "action_status": last_turn["action_status"],
        "observation": observation,
        "next_action": "coding-agent-mini-call",
    }
