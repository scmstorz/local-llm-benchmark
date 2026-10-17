"""Direct Track A runner for the frozen multi-format canonical extraction."""

from __future__ import annotations

import argparse
import json
import platform
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .agentic import _collect_ollama_turn, validate_local_ollama_host
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


DEFAULT_CONDITION_PATH = Path("tasks/agentic/track-a/multi-format-canonical-v0.1.json")
CONDITION_ID = "canonical-representation-v0.1"
PROTOCOL_ID = "agentic-multi-format-canonical-v0.1"


@dataclass(frozen=True)
class CanonicalRunConfig:
    """Inputs for one direct, tool-free canonical-representation run."""

    model: str
    condition_path: Path = DEFAULT_CONDITION_PATH
    results_dir: Path = Path("results/agentic-runs")
    host: str = "http://127.0.0.1:11434"


def _required_path(repo_root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise RunnerError(f"Track A canonical condition lacks {label}")
    path = resolve_repo_path(repo_root, Path(value))
    if not path.is_file() or path.is_symlink():
        raise RunnerError(f"Unsafe or missing Track A {label}: {value}")
    return path


def load_canonical_condition(
    repo_root: Path, condition_path: Path = DEFAULT_CONDITION_PATH
) -> dict[str, Any]:
    """Load and cross-check the frozen Track A representation boundary."""
    path = resolve_repo_path(repo_root, condition_path)
    condition = load_json(path)
    if (
        condition.get("schema_version") != "1.0.0"
        or condition.get("condition_id") != CONDITION_ID
        or condition.get("protocol_id") != PROTOCOL_ID
        or condition.get("track") != "A"
        or condition.get("study_mode") != "measured_capability"
        or condition.get("status") != "qualification_candidate"
    ):
        raise RunnerError("Unexpected Track A canonical condition identity")
    boundary = condition.get("candidate_boundary", {})
    if (
        boundary.get("canonical_representation_only") is not True
        or boundary.get("artifact_files_available") is not False
        or boundary.get("tools_available") is not False
        or boundary.get("hidden_ground_truth_available") is not False
        or boundary.get("external_network_available") is not False
    ):
        raise RunnerError("Track A canonical candidate boundary changed")
    inference = condition.get("inference_defaults", {})
    limits = condition.get("normal_capability_limits", {})
    if (
        inference.get("temperature") != 0.0
        or inference.get("seed") != 42
        or inference.get("think") is not False
        or inference.get("num_ctx") != 16384
        or inference.get("num_predict") != 5000
        or inference.get("keep_alive") != "5m"
        or limits.get("maximum_active_wall_time_seconds") != 300
        or limits.get("provider_request_timeout_seconds") != 180
    ):
        raise RunnerError("Track A canonical inference boundary changed")
    case_path = _required_path(repo_root, condition.get("case_path"), "case")
    loaded_case = load_multi_format_case(repo_root, case_path.relative_to(repo_root))
    paths = {
        "task": _required_path(repo_root, condition.get("task_path"), "task"),
        "canonical_extraction": _required_path(
            repo_root, condition.get("canonical_extraction_path"), "canonical extraction"
        ),
        "canonical_extraction_schema": _required_path(
            repo_root,
            condition.get("canonical_extraction_schema_path"),
            "canonical extraction schema",
        ),
        "system_prompt": _required_path(
            repo_root, condition.get("system_prompt_path"), "system prompt"
        ),
        "report_schema": _required_path(
            repo_root, condition.get("report_schema_path"), "report schema"
        ),
    }
    expected = {
        "task": loaded_case["task_path"],
        "canonical_extraction": loaded_case["canonical_path"],
        "canonical_extraction_schema": loaded_case["canonical_schema_path"],
        "report_schema": loaded_case["schema_path"],
    }
    if any(paths[key].resolve() != value.resolve() for key, value in expected.items()):
        raise RunnerError("Track A canonical condition differs from the qualified case")
    canonical = load_json(paths["canonical_extraction"])
    if canonical.get("case_id") != loaded_case["case"]["case_id"]:
        raise RunnerError("Track A canonical extraction case identity differs")
    return {
        "condition": condition,
        "condition_path": path,
        "case": loaded_case,
        "canonical": canonical,
        "paths": paths,
        "system_prompt": paths["system_prompt"].read_text(encoding="utf-8").strip(),
        "report_schema": load_json(paths["report_schema"]),
    }


def parse_final_object(value: str | None) -> dict[str, Any]:
    """Recover at most one intact JSON object and score strict transport."""
    if not isinstance(value, str) or not value.strip():
        return {
            "status": "invalid",
            "failure_code": "empty_final_response",
            "report": None,
            "strict_transport_compliance": False,
            "normalization_applied": False,
            "normalization_kind": None,
        }
    stripped = value.strip()
    try:
        strict = json.loads(stripped)
    except json.JSONDecodeError:
        strict = None
    else:
        if isinstance(strict, dict):
            return {
                "status": "valid",
                "failure_code": None,
                "report": strict,
                "strict_transport_compliance": True,
                "normalization_applied": False,
                "normalization_kind": "none",
            }
        return {
            "status": "invalid",
            "failure_code": "final_json_not_object",
            "report": None,
            "strict_transport_compliance": False,
            "normalization_applied": False,
            "normalization_kind": None,
        }
    decoder = json.JSONDecoder()
    objects: list[tuple[int, int, dict[str, Any]]] = []
    position = 0
    while position < len(stripped):
        opening = stripped.find("{", position)
        if opening < 0:
            break
        try:
            candidate, consumed = decoder.raw_decode(stripped[opening:])
        except json.JSONDecodeError:
            position = opening + 1
            continue
        end = opening + consumed
        if isinstance(candidate, dict):
            objects.append((opening, end, candidate))
            position = end
        else:
            position = opening + max(consumed, 1)
    if len(objects) != 1:
        return {
            "status": "invalid",
            "failure_code": "no_intact_json_object" if not objects else "ambiguous_multiple_json_objects",
            "report": None,
            "strict_transport_compliance": False,
            "normalization_applied": False,
            "normalization_kind": None,
        }
    opening, end, report = objects[0]
    outside = (stripped[:opening].strip() + stripped[end:].strip())
    if "{" in outside or "}" in outside:
        return {
            "status": "invalid",
            "failure_code": "json_like_content_outside_recovered_object",
            "report": None,
            "strict_transport_compliance": False,
            "normalization_applied": False,
            "normalization_kind": None,
        }
    fenced = "```" in stripped[:opening] or "```" in stripped[end:]
    return {
        "status": "valid",
        "failure_code": None,
        "report": report,
        "strict_transport_compliance": False,
        "normalization_applied": True,
        "normalization_kind": "markdown_code_fence" if fenced else "surrounding_text",
    }


def _user_message(loaded: dict[str, Any]) -> str:
    task = loaded["paths"]["task"].read_text(encoding="utf-8").strip()
    canonical = json.dumps(loaded["canonical"], ensure_ascii=False, indent=2, sort_keys=True)
    schema = json.dumps(loaded["report_schema"], ensure_ascii=False, indent=2, sort_keys=True)
    return (
        f"# Task\n\n{task}\n\n"
        f"# Frozen canonical extraction\n\n{canonical}\n\n"
        f"# Final JSON Schema\n\n{schema}\n\n"
        "Return exactly one final JSON object now."
    )


def prepare_canonical_run(repo_root: Path, config: CanonicalRunConfig) -> dict[str, Any]:
    """Prepare one Track A request without contacting Ollama."""
    host = validate_local_ollama_host(config.host)
    if not isinstance(config.model, str) or not config.model.strip():
        raise RunnerError("Track A canonical model name must be non-empty")
    loaded = load_canonical_condition(repo_root, config.condition_path)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"canonical-multiformat-run-{timestamp}-{secrets.token_hex(4)}"
    results_dir = resolve_repo_path(repo_root, config.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    run_dir = results_dir / run_id
    run_dir.mkdir()
    messages = [
        {"role": "system", "content": loaded["system_prompt"]},
        {"role": "user", "content": _user_message(loaded)},
    ]
    inference = loaded["condition"]["inference_defaults"]
    request = {
        "model": config.model,
        "messages": messages,
        "stream": True,
        "think": inference["think"],
        "keep_alive": inference["keep_alive"],
        "format": loaded["report_schema"],
        "options": {
            "temperature": inference["temperature"],
            "seed": inference["seed"],
            "num_ctx": inference["num_ctx"],
            "num_predict": inference["num_predict"],
        },
    }
    request_path = run_dir / "request.json"
    write_json(request_path, request)
    implementation = Path(__file__).resolve()
    definitions = {
        "condition": loaded["condition_path"],
        **loaded["paths"],
        "implementation": implementation,
    }
    record = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "track": "A",
        "condition_id": CONDITION_ID,
        "protocol_id": PROTOCOL_ID,
        "study_mode": "measured_capability",
        "state": "prepared_not_executed",
        "started_at": utc_now(),
        "completed_at": None,
        "git_commit": git_commit(repo_root),
        "definitions": {
            f"{key}_path": value.relative_to(repo_root).as_posix()
            for key, value in definitions.items()
        }
        | {f"{key}_sha256": sha256_file(value) for key, value in definitions.items()},
        "case": {
            "case_id": loaded["case"]["case"]["case_id"],
            "case_version": loaded["case"]["case"]["case_version"],
            "canonical_record_count": len(
                loaded["canonical"].get("evidence_records", [])
            ),
        },
        "deployment": {
            "requested_model": config.model,
            "ollama_host": host,
            "ollama_version": None,
            "model": None,
            "options": inference,
        },
        "limits": loaded["condition"]["normal_capability_limits"],
        "trajectory": {
            "agent_turns": 0,
            "model_requests": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "active_wall_time_seconds": 0.0,
            "time_to_first_content_seconds": None,
            "output_tokens_per_second": None,
            "strict_transport_compliance": False,
            "response_normalization_applied": False,
            "response_normalization_kind": None,
        },
        "execution": {
            "started_at": None,
            "finished_at": None,
            "runtime_success": None,
            "agent_termination_valid": None,
            "failure": None,
        },
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
            "inference_requests_made": 0,
            "tools_available": False,
            "artifact_files_available": False,
            "hidden_verification_executed": False,
        },
        "artifacts": {
            "request": request_path.name,
            "request_sha256": sha256_file(request_path),
            "stream": None,
            "stream_sha256": None,
            "candidate_response": None,
            "candidate_response_sha256": None,
            "candidate_report": None,
            "candidate_report_sha256": None,
            "final_verification": None,
            "final_verification_sha256": None,
        },
    }
    write_json(run_dir / "run.json", record)
    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "state": record["state"],
        "inference_requests_made": 0,
    }


def _load_run(repo_root: Path, run_dir: Path) -> tuple[Path, dict[str, Any]]:
    resolved = resolve_repo_path(repo_root, run_dir)
    record = load_json(resolved / "run.json")
    if record.get("condition_id") != CONDITION_ID or record.get("protocol_id") != PROTOCOL_ID:
        raise RunnerError("Run does not belong to Track A canonical v0.1")
    loaded = load_canonical_condition(
        repo_root, Path(record["definitions"]["condition_path"])
    )
    definitions = {
        "condition": loaded["condition_path"],
        **loaded["paths"],
        "implementation": Path(__file__).resolve(),
    }
    drift = [
        key
        for key, path in definitions.items()
        if record["definitions"].get(f"{key}_sha256") != sha256_file(path)
    ]
    if drift:
        raise RunnerError("Track A canonical definition changed: " + ", ".join(drift))
    return resolved, record


def execute_canonical_run(repo_root: Path, run_dir: Path) -> dict[str, Any]:
    """Execute the one frozen Track A Ollama request."""
    resolved, record = _load_run(repo_root, run_dir)
    if record.get("state") != "prepared_not_executed":
        raise RunnerError("Track A canonical run is not ready for execution")
    request_path = resolved / record["artifacts"]["request"]
    if sha256_file(request_path) != record["artifacts"]["request_sha256"]:
        raise RunnerError("Track A canonical request changed")
    client = OllamaClient(
        record["deployment"]["ollama_host"],
        timeout_seconds=float(record["limits"]["provider_request_timeout_seconds"]),
    )
    record["state"] = "model_call_running"
    record["execution"]["started_at"] = utc_now()
    write_json(resolved / "run.json", record)
    started = time.monotonic()
    phase = "ollama_version"
    try:
        version = client.version()
        phase = "model_resolution"
        model = find_model(client.list_models(), record["deployment"]["requested_model"])
        phase = "model_inspection"
        shown = client.show_model(record["deployment"]["requested_model"])
        phase = "inference"
        record["trajectory"]["model_requests"] = 1
        record["execution_boundary"]["inference_requests_made"] = 1
        write_json(resolved / "run.json", record)
        stream_path = resolved / "stream.ndjson"
        turn = _collect_ollama_turn(client, load_json(request_path), stream_path)
    except Exception as exc:
        duration = time.monotonic() - started
        record["state"] = "execution_complete_verification_pending"
        record["trajectory"]["active_wall_time_seconds"] = duration
        record["execution"].update(
            {
                "finished_at": utc_now(),
                "runtime_success": False,
                "agent_termination_valid": False,
                "failure": {"phase": phase, "type": type(exc).__name__, "message": str(exc)},
            }
        )
        write_json(resolved / "run.json", record)
        return {"run_id": record["run_id"], "state": record["state"], "runtime_success": False}
    duration = time.monotonic() - started
    response_path = resolved / "candidate-response.txt"
    response_path.write_text(turn["content"] + "\n", encoding="utf-8")
    parsed = parse_final_object(turn["content"])
    report_path = None
    if parsed["status"] == "valid":
        report_path = resolved / "candidate-report.json"
        write_json(report_path, parsed["report"])
    final = turn["final_event"]
    record["state"] = "execution_complete_verification_pending"
    record["deployment"].update(
        {
            "ollama_version": version.get("version"),
            "model": {
                "resolved_name": model.get("name") or model.get("model"),
                "digest": model.get("digest"),
                "size_bytes": model.get("size"),
                "details": model.get("details"),
                "capabilities": shown.get("capabilities"),
                "parameters": shown.get("parameters"),
                "template_sha256": sha256_text(shown.get("template", "")),
            },
        }
    )
    record["trajectory"].update(
        {
            "agent_turns": 1,
            "input_tokens": final.get("prompt_eval_count") or 0,
            "output_tokens": final.get("eval_count") or 0,
            "active_wall_time_seconds": duration,
            "time_to_first_content_seconds": turn["time_to_first_content_seconds"],
            "output_tokens_per_second": tokens_per_second(
                final.get("eval_count"), final.get("eval_duration")
            ),
            "load_duration_seconds": nanoseconds_to_seconds(final.get("load_duration")),
            "done_reason": final.get("done_reason"),
            "final_report_parse_status": parsed["status"],
            "final_report_parse_failure": parsed["failure_code"],
            "strict_transport_compliance": parsed["strict_transport_compliance"],
            "response_normalization_applied": parsed["normalization_applied"],
            "response_normalization_kind": parsed["normalization_kind"],
        }
    )
    record["execution"].update(
        {
            "finished_at": utc_now(),
            "runtime_success": True,
            "agent_termination_valid": parsed["status"] == "valid",
            "failure": None,
        }
    )
    record["artifacts"].update(
        {
            "stream": stream_path.name,
            "stream_sha256": sha256_file(stream_path),
            "candidate_response": response_path.name,
            "candidate_response_sha256": sha256_file(response_path),
            "candidate_report": report_path.name if report_path else None,
            "candidate_report_sha256": sha256_file(report_path) if report_path else None,
        }
    )
    write_json(resolved / "run.json", record)
    return {
        "run_id": record["run_id"],
        "state": record["state"],
        "runtime_success": True,
        "agent_termination_valid": record["execution"]["agent_termination_valid"],
    }


def finalize_canonical_run(repo_root: Path, run_dir: Path) -> dict[str, Any]:
    """Apply the unchanged hidden verifier after the Track A response."""
    resolved, record = _load_run(repo_root, run_dir)
    if record.get("state") != "execution_complete_verification_pending":
        raise RunnerError("Track A canonical run is not ready for verification")
    report = None
    if record["artifacts"].get("candidate_report"):
        report_path = resolved / record["artifacts"]["candidate_report"]
        if sha256_file(report_path) != record["artifacts"]["candidate_report_sha256"]:
            raise RunnerError("Track A canonical candidate report changed")
        report = load_json(report_path)
    condition = load_json(repo_root / record["definitions"]["condition_path"])
    verification = verify_multi_format_report(
        repo_root, Path(condition["case_path"]), report
    )
    verification_path = resolved / "final-verification.json"
    write_json(verification_path, verification)
    runtime = bool(record["execution"]["runtime_success"])
    agent_valid = bool(record["execution"]["agent_termination_valid"])
    semantic = bool(verification["semantic_verified_success"])
    success = runtime and agent_valid and semantic
    record["state"] = "complete"
    record["completed_at"] = utc_now()
    record["outcome"] = {
        "runtime_success": runtime,
        "agent_termination_valid": agent_valid,
        "semantic_verifier_success": semantic,
        "semantic_verified_success": success,
        "verified_success": success,
        "strict_transport_compliance": bool(
            record["trajectory"]["strict_transport_compliance"]
        ),
        "failure_category": None
        if success
        else (
            "infrastructure_or_runtime_failure"
            if not runtime
            else "agent_failure"
            if not agent_valid
            else "task_or_verification_failure"
        ),
    }
    record["verification"] = verification
    record["execution_boundary"]["hidden_verification_executed"] = True
    record["artifacts"]["final_verification"] = verification_path.name
    record["artifacts"]["final_verification_sha256"] = sha256_file(verification_path)
    write_json(resolved / "run.json", record)
    return {
        "run_id": record["run_id"],
        "state": "complete",
        **record["outcome"],
        "verification": {
            "essential_pass_count": verification["essential_pass_count"],
            "essential_check_count": verification["essential_check_count"],
        },
        "trajectory": record["trajectory"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--model", required=True)
    prepare.add_argument("--condition", type=Path, default=DEFAULT_CONDITION_PATH)
    prepare.add_argument("--results-dir", type=Path, default=Path("results/agentic-runs"))
    prepare.add_argument("--host", default="http://127.0.0.1:11434")
    for name in ("run", "finalize"):
        command = subparsers.add_parser(name)
        command.add_argument("--run-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    if args.command == "prepare":
        result = prepare_canonical_run(
            repo_root,
            CanonicalRunConfig(
                model=args.model,
                condition_path=args.condition,
                results_dir=args.results_dir,
                host=args.host,
            ),
        )
    elif args.command == "run":
        result = execute_canonical_run(repo_root, args.run_dir)
    else:
        result = finalize_canonical_run(repo_root, args.run_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
