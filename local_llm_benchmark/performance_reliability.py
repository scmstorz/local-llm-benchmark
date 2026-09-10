"""Resumable steady-state performance and reliability studies."""

from __future__ import annotations

import argparse
import json
import math
import re
import secrets
import statistics
import time
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .log_incident_smokes import (
    ResourceGatePause,
    _blocking_processes,
    _process_snapshot,
    run_resource_gate,
)
from .ollama import OllamaClient, OllamaError
from .runner import (
    RunConfig,
    RunnerError,
    find_model,
    load_case,
    load_json,
    resolve_repo_path,
    run_once,
    running_model_names,
    sha256_file,
    sha256_text,
    utc_now,
    write_json,
)


DEFAULT_PLAN_PATH = Path("tasks/studies/performance-reliability-v0.1.json")
DEFAULT_STUDIES_DIR = Path("results/performance-reliability/studies")
DEFAULT_RUNS_DIR = Path("results/runs")
TERMINAL_ATTEMPT_STATUSES = {"complete", "infrastructure_failed"}
TERMINAL_BLOCK_STATUSES = {"complete"}


@dataclass(frozen=True)
class PerformanceStudyConfig:
    plan_path: Path = DEFAULT_PLAN_PATH
    studies_dir: Path = DEFAULT_STUDIES_DIR
    runs_dir: Path = DEFAULT_RUNS_DIR


def _required_string(value: dict[str, Any], key: str, context: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise RunnerError(f"{context} must define {key}")
    return result


def _validate_plan_structure(plan: dict[str, Any]) -> None:
    if plan.get("schema_version") != "1.0.0":
        raise RunnerError("Performance study plan must use schema_version 1.0.0")
    if plan.get("status") != "frozen_before_execution":
        raise RunnerError("Performance study plan must be frozen before execution")
    if plan.get("study_mode") != "performance_and_reliability":
        raise RunnerError("Unexpected performance study mode")
    _required_string(plan, "plan_id", "Performance study plan")

    methodology = plan.get("methodology")
    if not isinstance(methodology, dict):
        raise RunnerError("Performance study must define methodology")
    repetitions = methodology.get("measured_runs_per_condition")
    if not isinstance(repetitions, int) or isinstance(repetitions, bool) or repetitions < 20:
        raise RunnerError("Performance study requires at least 20 measured runs per condition")
    if methodology.get("warmup_runs_per_block") != 1:
        raise RunnerError("Performance study v0.1 requires one excluded warm-up per block")
    per_block = methodology.get("measured_runs_per_block")
    segments = methodology.get("segments_per_condition")
    if (
        not isinstance(per_block, int)
        or isinstance(per_block, bool)
        or per_block < 1
        or not isinstance(segments, int)
        or isinstance(segments, bool)
        or segments < 2
        or per_block * segments != repetitions
    ):
        raise RunnerError("Measured block size and segment count must partition each condition")
    timeout = methodology.get("timeout_seconds")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        raise RunnerError("Performance study timeout_seconds must be positive")

    deployments = plan.get("deployments")
    workloads = plan.get("workloads")
    blocks = plan.get("execution_order")
    if not isinstance(deployments, list) or len(deployments) != 2:
        raise RunnerError("Performance study v0.1 requires exactly two deployments")
    if not isinstance(workloads, list) or len(workloads) != 2:
        raise RunnerError("Performance study v0.1 requires exactly two workloads")
    expected_block_count = len(deployments) * len(workloads) * segments
    if not isinstance(blocks, list) or len(blocks) != expected_block_count:
        raise RunnerError(
            f"Performance study v0.1 requires exactly {expected_block_count} blocks"
        )

    deployment_aliases: set[str] = set()
    for deployment in deployments:
        if not isinstance(deployment, dict):
            raise RunnerError("Every deployment must be an object")
        alias = _required_string(deployment, "alias", "Deployment")
        if alias in deployment_aliases:
            raise RunnerError(f"Duplicate deployment alias: {alias}")
        deployment_aliases.add(alias)
        _required_string(deployment, "name", f"Deployment {alias}")
        digest = _required_string(deployment, "digest", f"Deployment {alias}")
        if len(digest) != 64:
            raise RunnerError(f"Deployment {alias} has an invalid digest")

    workload_aliases: set[str] = set()
    observed_kinds: set[str] = set()
    for workload in workloads:
        if not isinstance(workload, dict):
            raise RunnerError("Every workload must be an object")
        alias = _required_string(workload, "alias", "Workload")
        if alias in workload_aliases:
            raise RunnerError(f"Duplicate workload alias: {alias}")
        workload_aliases.add(alias)
        kind = _required_string(workload, "kind", f"Workload {alias}")
        if kind not in {"natural_output", "controlled_decode"}:
            raise RunnerError(f"Unsupported performance workload kind: {kind}")
        observed_kinds.add(kind)
        _required_string(workload, "case_path", f"Workload {alias}")
        for key in ("num_ctx", "num_predict"):
            setting = workload.get(key)
            if not isinstance(setting, int) or isinstance(setting, bool) or setting < 1:
                raise RunnerError(f"Workload {alias} has invalid {key}")
        if kind == "controlled_decode" and workload.get("target_eval_count") != workload.get(
            "num_predict"
        ):
            raise RunnerError("Controlled decode target must equal num_predict")
    if observed_kinds != {"natural_output", "controlled_decode"}:
        raise RunnerError("Study must separate natural and controlled workloads")

    observed_segments: set[tuple[str, str, int]] = set()
    observed_repetitions: dict[tuple[str, str], set[int]] = {}
    for expected_position, block in enumerate(blocks, start=1):
        if not isinstance(block, dict) or block.get("position") != expected_position:
            raise RunnerError("Performance study positions must be contiguous from one")
        _required_string(block, "block_id", "Execution block")
        pair = (block.get("deployment_alias"), block.get("workload_alias"))
        segment = block.get("segment")
        segment_key = (*pair, segment)
        if (
            pair[0] not in deployment_aliases
            or pair[1] not in workload_aliases
            or not isinstance(segment, int)
            or isinstance(segment, bool)
            or segment < 1
            or segment > segments
            or segment_key in observed_segments
        ):
            raise RunnerError(f"Invalid or duplicate performance study segment: {segment_key}")
        observed_segments.add(segment_key)
        repetitions_in_block = block.get("repetitions")
        if (
            not isinstance(repetitions_in_block, list)
            or len(repetitions_in_block) != per_block
            or any(
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 1
                or value > repetitions
                for value in repetitions_in_block
            )
            or len(set(repetitions_in_block)) != len(repetitions_in_block)
        ):
            raise RunnerError(f"Invalid repetitions in performance block {block.get('block_id')}")
        observed_repetitions.setdefault(pair, set()).update(repetitions_in_block)
    expected_pairs = {
        (deployment_alias, workload_alias)
        for deployment_alias in deployment_aliases
        for workload_alias in workload_aliases
    }
    expected_segments = {
        (*pair, segment)
        for pair in expected_pairs
        for segment in range(1, segments + 1)
    }
    if observed_segments != expected_segments:
        raise RunnerError("Performance study execution order is not the segmented product")
    if any(
        observed_repetitions.get(pair) != set(range(1, repetitions + 1))
        for pair in expected_pairs
    ):
        raise RunnerError("Performance repetitions do not cover each condition exactly")

    gate = plan.get("resource_gate")
    if not isinstance(gate, dict):
        raise RunnerError("Performance study must define a resource gate")
    if gate.get("loaded_models_must_be_empty_before_each_block") is not True:
        raise RunnerError("Performance blocks require an initially empty Ollama state")
    if gate.get("model_unloaded_after_each_block") is not True:
        raise RunnerError("Performance blocks require model unload after completion")
    if gate.get("guard_before_each_measured_run") is not True:
        raise RunnerError("Performance blocks require an active guard before every run")
    if not isinstance(gate.get("blocking_process_rules"), list):
        raise RunnerError("Performance study must define blocking process rules")

    reporting = plan.get("reporting")
    if not isinstance(reporting, dict) or reporting.get("p90_minimum_n") != 20:
        raise RunnerError("Performance study must enforce the n >= 20 P90 boundary")
    if reporting.get("p95_minimum_n") != 50 or reporting.get("p99_minimum_n") != 100:
        raise RunnerError("Performance study tail-reporting boundaries changed")

    artifacts = plan.get("frozen_artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise RunnerError("Performance study must freeze its artifacts")
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise RunnerError("Every frozen artifact must be an object")
        path_value = _required_string(artifact, "path", "Frozen artifact")
        digest = _required_string(artifact, "sha256", f"Frozen artifact {path_value}")
        if len(digest) != 64:
            raise RunnerError(f"Frozen artifact has invalid digest: {path_value}")


def load_performance_plan(repo_root: Path, plan_path: Path = DEFAULT_PLAN_PATH) -> dict[str, Any]:
    resolved = resolve_repo_path(repo_root, plan_path)
    plan = load_json(resolved)
    _validate_plan_structure(plan)
    for artifact in plan["frozen_artifacts"]:
        path = resolve_repo_path(repo_root, artifact["path"])
        if not path.is_file() or path.is_symlink():
            raise RunnerError(f"Frozen performance artifact is missing: {artifact['path']}")
        if sha256_file(path) != artifact["sha256"]:
            raise RunnerError(f"Frozen performance artifact changed: {artifact['path']}")
    for workload in plan["workloads"]:
        loaded = load_case(repo_root, Path(workload["case_path"]))
        if loaded["case"]["case_id"] != workload["case_id"]:
            raise RunnerError(f"Performance workload identity changed: {workload['alias']}")
    return {"plan": plan, "path": resolved, "sha256": sha256_file(resolved)}


def _deployment(plan: dict[str, Any], alias: str) -> dict[str, Any]:
    matches = [item for item in plan["deployments"] if item["alias"] == alias]
    if len(matches) != 1:
        raise RunnerError(f"Unknown deployment alias: {alias}")
    return matches[0]


def _workload(plan: dict[str, Any], alias: str) -> dict[str, Any]:
    matches = [item for item in plan["workloads"] if item["alias"] == alias]
    if len(matches) != 1:
        raise RunnerError(f"Unknown workload alias: {alias}")
    return matches[0]


def _new_attempt(repetition: int) -> dict[str, Any]:
    return {
        "repetition": repetition,
        "status": "pending",
        "started_at": None,
        "completed_at": None,
        "run": None,
        "failure": None,
        "output_contract": None,
        "interrupted_attempts": [],
    }


def start_performance_study(repo_root: Path, config: PerformanceStudyConfig) -> dict[str, Any]:
    loaded = load_performance_plan(repo_root, config.plan_path)
    plan = loaded["plan"]
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    study_id = f"performance-study-{timestamp}-{secrets.token_hex(4)}"
    study_dir = resolve_repo_path(repo_root, config.studies_dir) / study_id
    study_dir.mkdir(parents=True, exist_ok=False)
    record = {
        "schema_version": "1.0.0",
        "study_id": study_id,
        "status": "running",
        "started_at": utc_now(),
        "completed_at": None,
        "plan": {
            "plan_id": plan["plan_id"],
            "path": str(loaded["path"].relative_to(repo_root)),
            "sha256": loaded["sha256"],
        },
        "runs_dir": str(resolve_repo_path(repo_root, config.runs_dir).relative_to(repo_root)),
        "blocks": [
            {
                **deepcopy(block),
                "status": "pending",
                "started_at": None,
                "completed_at": None,
                "resource_gate": None,
                "preload_attempts": [],
                "warmup_attempts": [],
                "measured_runs": [
                    _new_attempt(index) for index in block["repetitions"]
                ],
                "running_models_after_cleanup": None,
                "pause_history": [],
            }
            for block in plan["execution_order"]
        ],
        "outputs": None,
    }
    write_json(study_dir / "study.json", record)
    return _summary(record, study_dir)


def _load_study(repo_root: Path, study_dir: Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    resolved = resolve_repo_path(repo_root, study_dir)
    record = load_json(resolved / "study.json")
    plan_record = record.get("plan", {})
    loaded = load_performance_plan(
        repo_root, Path(_required_string(plan_record, "path", "Study plan"))
    )
    if loaded["sha256"] != plan_record.get("sha256"):
        raise RunnerError("Performance study plan changed after checkpoint creation")
    if loaded["plan"]["plan_id"] != plan_record.get("plan_id"):
        raise RunnerError("Performance study plan identity changed")
    return resolved, record, loaded


def _summary(record: dict[str, Any], study_dir: Path) -> dict[str, Any]:
    waiting = next(
        (block for block in record["blocks"] if block["status"] not in TERMINAL_BLOCK_STATUSES),
        None,
    )
    attempts = [attempt for block in record["blocks"] for attempt in block["measured_runs"]]
    return {
        "study_id": record["study_id"],
        "study_dir": str(study_dir),
        "status": record["status"],
        "complete_blocks": sum(block["status"] == "complete" for block in record["blocks"]),
        "total_blocks": len(record["blocks"]),
        "measured_complete": sum(attempt["status"] == "complete" for attempt in attempts),
        "measured_infrastructure_failed": sum(
            attempt["status"] == "infrastructure_failed" for attempt in attempts
        ),
        "measured_total": len(attempts),
        "waiting": None
        if waiting is None
        else {
            "block_id": waiting["block_id"],
            "position": waiting["position"],
            "deployment_alias": waiting["deployment_alias"],
            "workload_alias": waiting["workload_alias"],
            "status": waiting["status"],
            "remaining_measured_runs": sum(
                item["status"] not in TERMINAL_ATTEMPT_STATUSES
                for item in waiting["measured_runs"]
            ),
        },
        "outputs": record.get("outputs"),
    }


def _run_config(
    *,
    record: dict[str, Any],
    deployment: dict[str, Any],
    workload: dict[str, Any],
    host: str,
    comparison_id: str | None,
    repetition: int | None,
) -> RunConfig:
    settings = workload["generation_settings"]
    return RunConfig(
        model=deployment["name"],
        case_path=Path(workload["case_path"]),
        host=host,
        results_dir=Path(record["runs_dir"]),
        temperature=float(settings["temperature"]),
        seed=int(settings["seed"]),
        num_ctx=int(workload["num_ctx"]),
        num_predict=int(workload["num_predict"]),
        think=settings["think"],
        keep_alive=str(settings["keep_alive"]),
        timeout_seconds=float(settings["timeout_seconds"]),
        comparison_id=comparison_id,
        measurement_phase="warm" if comparison_id is not None else None,
        measurement_iteration=repetition,
    )


def _failure_category(error: BaseException, *, stage: str) -> str:
    message = str(error).casefold()
    if "timed out" in message or "timeout" in message:
        return "timeout"
    if "out of memory" in message or "cannot allocate" in message:
        return "out_of_memory"
    if stage == "preload":
        return "model_load_failure"
    if "cannot reach ollama" in message or "connection refused" in message:
        return "runtime_unavailable"
    if isinstance(error, OllamaError):
        return "runtime_crash"
    return "other"


def _compact_run(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": result["run_id"],
        "done_reason": result.get("done_reason"),
        "checks": result.get("checks"),
        "metrics": result.get("metrics"),
    }


def _output_contract(
    *, repo_root: Path, result: dict[str, Any], workload: dict[str, Any]
) -> dict[str, Any]:
    checks = result.get("checks") or {}
    if workload["kind"] == "natural_output":
        required = workload["output_contract"]["required_checks"]
        failed = [key for key in required if checks.get(key) is not True]
        return {
            "status": "passed" if not failed else "failed",
            "verifier_kind": "deterministic_output_contract",
            "failed_checks": failed,
            "semantic_quality_verified": False,
        }

    response_path = resolve_repo_path(repo_root, Path(result["run_dir"])) / "response.md"
    response = response_path.read_text(encoding="utf-8").strip()
    protocol_match = re.fullmatch(r"vector(?:\s+vector)*", response) is not None
    metrics = result.get("metrics") or {}
    target = workload["target_eval_count"]
    conditions = {
        "nonempty": bool(response),
        "protocol_match": protocol_match,
        "done_reason_is_length": result.get("done_reason") == "length",
        "eval_count_matches_target": metrics.get("eval_count") == target,
    }
    failed = [key for key, passed in conditions.items() if not passed]
    return {
        "status": "passed" if not failed else "failed",
        "verifier_kind": "controlled_decode_protocol",
        "failed_checks": failed,
        "conditions": conditions,
        "response_sha256": sha256_text(response),
        "semantic_quality_verified": False,
    }


def _find_completed_orphan(
    repo_root: Path,
    record: dict[str, Any],
    deployment: dict[str, Any],
    workload: dict[str, Any],
    repetition: int,
) -> dict[str, Any] | None:
    runs_dir = resolve_repo_path(repo_root, Path(record["runs_dir"]))
    matches: list[dict[str, Any]] = []
    if not runs_dir.is_dir():
        return None
    for run_path in runs_dir.glob("run-*/run.json"):
        run = load_json(run_path)
        measurement = run.get("measurement") or {}
        if (
            run.get("status") == "complete"
            and measurement.get("comparison_id") == record["study_id"]
            and measurement.get("phase") == "warm"
            and measurement.get("iteration") == repetition
            and run.get("case", {}).get("case_id") == workload["case_id"]
            and run.get("deployment", {}).get("model", {}).get("requested_name")
            == deployment["name"]
        ):
            matches.append({"path": run_path, "record": run})
    if len(matches) > 1:
        raise RunnerError("Multiple completed runs match one interrupted attempt")
    if not matches:
        return None
    match = matches[0]
    run = match["record"]
    run_dir = match["path"].parent
    return {
        "run_id": run["run_id"],
        "run_dir": str(run_dir),
        "done_reason": run.get("execution", {}).get("done_reason"),
        "checks": run.get("checks"),
        "metrics": run.get("metrics"),
    }


def _reconcile_running_attempts(
    *,
    repo_root: Path,
    record: dict[str, Any],
    block: dict[str, Any],
    deployment: dict[str, Any],
    workload: dict[str, Any],
) -> None:
    for attempt in block["measured_runs"]:
        if attempt["status"] != "running":
            continue
        completed = _find_completed_orphan(
            repo_root, record, deployment, workload, attempt["repetition"]
        )
        if completed is not None:
            attempt["status"] = "complete"
            attempt["completed_at"] = utc_now()
            attempt["run"] = _compact_run(completed)
            attempt["output_contract"] = _output_contract(
                repo_root=repo_root, result=completed, workload=workload
            )
            continue
        attempt["interrupted_attempts"].append(
            {
                "started_at": attempt.get("started_at"),
                "preserved_at": utc_now(),
                "classification": "controller_or_host_interruption_before_terminal_result",
                "replacement_allowed": True,
            }
        )
        attempt["status"] = "pending"
        attempt["started_at"] = None


def _active_guard(
    *, client: OllamaClient, plan: dict[str, Any], deployment: dict[str, Any]
) -> dict[str, Any]:
    blockers = _blocking_processes(
        plan["resource_gate"]["blocking_process_rules"], _process_snapshot()
    )
    if blockers:
        raise ResourceGatePause(
            "Concurrent workload appeared during a measurement block.",
            {
                "stage": "active_process_guard",
                "blocking_processes": blockers,
                "inference_requests_made": 0,
            },
        )
    version = client.version().get("version")
    if version != plan["runtime"]["version"]:
        raise ResourceGatePause(
            f"Ollama version drift: expected {plan['runtime']['version']}, found {version}",
            {"stage": "active_runtime_guard", "inference_requests_made": 0},
        )
    observed = find_model(client.list_models(), deployment["name"])
    if observed.get("digest") != deployment["digest"]:
        raise ResourceGatePause(
            f"Ollama digest drift for {deployment['name']}",
            {"stage": "active_deployment_guard", "inference_requests_made": 0},
        )
    running = running_model_names(client.list_running_models())
    if running != [deployment["name"]]:
        raise ResourceGatePause(
            "Ollama no longer reports exactly the selected deployment.",
            {
                "stage": "active_ollama_guard",
                "running_models": running,
                "inference_requests_made": 0,
            },
        )
    return {"checked_at": utc_now(), "ollama_version": version, "running_models": running}


def advance_performance_study(
    repo_root: Path,
    study_dir: Path,
    *,
    host: str = "http://127.0.0.1:11434",
    execute_live: bool = False,
) -> dict[str, Any]:
    if not execute_live:
        raise RunnerError("Performance study advance requires --execute-live")
    resolved, record, loaded = _load_study(repo_root, study_dir)
    plan = loaded["plan"]
    if record["status"] == "complete":
        return _summary(record, resolved)
    block = next(
        (item for item in record["blocks"] if item["status"] not in TERMINAL_BLOCK_STATUSES),
        None,
    )
    if block is None:
        record["status"] = "complete"
        record["completed_at"] = utc_now()
        record["outputs"] = write_performance_report(repo_root, resolved, record, plan)
        write_json(resolved / "study.json", record)
        return _summary(record, resolved)

    deployment = _deployment(plan, block["deployment_alias"])
    workload = _workload(plan, block["workload_alias"])
    _reconcile_running_attempts(
        repo_root=repo_root,
        record=record,
        block=block,
        deployment=deployment,
        workload=workload,
    )
    if all(item["status"] in TERMINAL_ATTEMPT_STATUSES for item in block["measured_runs"]):
        block["status"] = "complete"
        block["completed_at"] = block.get("completed_at") or utc_now()
        write_json(resolved / "study.json", record)
        return _summary(record, resolved)

    client = OllamaClient(host, timeout_seconds=float(plan["methodology"]["timeout_seconds"]))
    gate_plan = {
        "resource_gate": {
            **plan["resource_gate"],
            "loaded_models_must_be_empty_before_each_unit": True,
        },
        "runtime": plan["runtime"],
        "deployment": deployment,
    }
    try:
        gate = run_resource_gate(gate_plan, client=client)
    except Exception as error:
        evidence = getattr(error, "evidence", {})
        block["status"] = "paused_resource_gate"
        block["pause_history"].append(
            {
                "paused_at": utc_now(),
                "reason": str(error),
                "evidence": evidence,
                "inference_requests_made": 0,
            }
        )
        record["status"] = "paused_resource_gate"
        write_json(resolved / "study.json", record)
        if isinstance(error, ResourceGatePause):
            raise
        raise ResourceGatePause(str(error), evidence) from error

    record["status"] = "running"
    block["status"] = "running"
    block["started_at"] = block.get("started_at") or utc_now()
    block["resource_gate"] = gate
    write_json(resolved / "study.json", record)

    preload_entry = {"started_at": utc_now(), "status": "running"}
    block["preload_attempts"].append(preload_entry)
    try:
        preload_started = time.perf_counter()
        preload_response = client.preload_model(
            deployment["name"], workload["generation_settings"]["keep_alive"]
        )
        preload_entry.update(
            {
                "status": "complete",
                "completed_at": utc_now(),
                "wall_time_seconds": time.perf_counter() - preload_started,
                "ollama_load_duration_ns": preload_response.get("load_duration"),
            }
        )
        _active_guard(client=client, plan=plan, deployment=deployment)
        warmup_entry = {"started_at": utc_now(), "status": "running"}
        block["warmup_attempts"].append(warmup_entry)
        write_json(resolved / "study.json", record)
        warmup_result = run_once(
            repo_root,
            _run_config(
                record=record,
                deployment=deployment,
                workload=workload,
                host=host,
                comparison_id=None,
                repetition=None,
            ),
        )
        warmup_entry.update(
            {
                "status": "complete",
                "completed_at": utc_now(),
                "run": _compact_run(warmup_result),
                "excluded_from_steady_state": True,
            }
        )
        write_json(resolved / "study.json", record)

        for attempt in block["measured_runs"]:
            if attempt["status"] in TERMINAL_ATTEMPT_STATUSES:
                continue
            guard = _active_guard(client=client, plan=plan, deployment=deployment)
            attempt["status"] = "running"
            attempt["started_at"] = utc_now()
            attempt["active_guard"] = guard
            write_json(resolved / "study.json", record)
            try:
                result = run_once(
                    repo_root,
                    _run_config(
                        record=record,
                        deployment=deployment,
                        workload=workload,
                        host=host,
                        comparison_id=record["study_id"],
                        repetition=attempt["repetition"],
                    ),
                )
                attempt["status"] = "complete"
                attempt["completed_at"] = utc_now()
                attempt["run"] = _compact_run(result)
                attempt["output_contract"] = _output_contract(
                    repo_root=repo_root, result=result, workload=workload
                )
            except Exception as error:
                attempt["status"] = "infrastructure_failed"
                attempt["completed_at"] = utc_now()
                attempt["failure"] = {
                    "category": _failure_category(error, stage="measured_request"),
                    "error_type": type(error).__name__,
                    "message": str(error),
                    "automatic_retry": False,
                }
                write_json(resolved / "study.json", record)
                raise ResourceGatePause(
                    "A measured request failed; its outcome was preserved and the block paused.",
                    {
                        "stage": "measured_request",
                        "failure_category": attempt["failure"]["category"],
                        "inference_requests_made": 1,
                    },
                ) from error
            write_json(resolved / "study.json", record)

        block["status"] = "complete"
        block["completed_at"] = utc_now()
    except ResourceGatePause as error:
        block["status"] = "paused_resource_gate"
        block["pause_history"].append(
            {
                "paused_at": utc_now(),
                "reason": str(error),
                "evidence": error.evidence,
            }
        )
        record["status"] = "paused_resource_gate"
    except (KeyboardInterrupt, SystemExit):
        block["status"] = "paused_interrupted"
        record["status"] = "paused_interrupted"
        raise
    except Exception as error:
        stage = "preload" if preload_entry["status"] == "running" else "warmup"
        target = preload_entry if stage == "preload" else block["warmup_attempts"][-1]
        target.update(
            {
                "status": "failed",
                "completed_at": utc_now(),
                "failure": {
                    "category": _failure_category(error, stage=stage),
                    "error_type": type(error).__name__,
                    "message": str(error),
                },
            }
        )
        block["status"] = "paused_runtime"
        record["status"] = "paused_runtime"
    finally:
        try:
            running = running_model_names(client.list_running_models())
            if deployment["name"] in running:
                client.unload_model(deployment["name"])
            block["running_models_after_cleanup"] = running_model_names(
                client.list_running_models()
            )
        except Exception as cleanup_error:
            block["cleanup_failure"] = {
                "category": "cleanup_failure",
                "error_type": type(cleanup_error).__name__,
                "message": str(cleanup_error),
            }
        write_json(resolved / "study.json", record)

    if all(item["status"] in TERMINAL_BLOCK_STATUSES for item in record["blocks"]):
        record["status"] = "complete"
        record["completed_at"] = utc_now()
        record["outputs"] = write_performance_report(repo_root, resolved, record, plan)
        write_json(resolved / "study.json", record)
    return _summary(record, resolved)


def _nearest_rank(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def _statistics(values: list[float], reporting: dict[str, Any]) -> dict[str, Any]:
    ordered = sorted(values)
    result: dict[str, Any] = {
        "n": len(values),
        "values": values,
        "mean": statistics.fmean(values) if values else None,
        "standard_deviation_sample": statistics.stdev(values) if len(values) > 1 else None,
        "minimum": ordered[0] if ordered else None,
        "median_p50": statistics.median(ordered) if ordered else None,
        "maximum": ordered[-1] if ordered else None,
        "percentile_method": "nearest_rank",
    }
    result["p90"] = (
        _nearest_rank(values, 0.90) if len(values) >= reporting["p90_minimum_n"] else None
    )
    result["p95"] = (
        _nearest_rank(values, 0.95) if len(values) >= reporting["p95_minimum_n"] else None
    )
    result["p99"] = (
        _nearest_rank(values, 0.99) if len(values) >= reporting["p99_minimum_n"] else None
    )
    return result


def _metric_distribution(
    attempts: list[dict[str, Any]], key: str, reporting: dict[str, Any]
) -> dict[str, Any]:
    values: list[float] = []
    for attempt in attempts:
        if attempt["status"] != "complete":
            continue
        if (attempt.get("output_contract") or {}).get("status") != "passed":
            continue
        value = (attempt.get("run", {}).get("metrics") or {}).get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.append(float(value))
    return _statistics(values, reporting)


def _aggregate_condition(
    blocks: list[dict[str, Any]], plan: dict[str, Any]
) -> dict[str, Any]:
    if not blocks:
        raise RunnerError("Cannot aggregate an empty performance condition")
    block = blocks[0]
    deployment = _deployment(plan, block["deployment_alias"])
    workload = _workload(plan, block["workload_alias"])
    attempts = [attempt for current in blocks for attempt in current["measured_runs"]]
    technical_successes = sum(item["status"] == "complete" for item in attempts)
    infrastructure_failures = sum(
        item["status"] == "infrastructure_failed" for item in attempts
    )
    output_passes = sum(
        item["status"] == "complete"
        and (item.get("output_contract") or {}).get("status") == "passed"
        for item in attempts
    )
    output_failures = technical_successes - output_passes
    failure_categories = Counter(
        item["failure"]["category"]
        for item in attempts
        if item.get("failure") and item["failure"].get("category")
    )
    for item in attempts:
        contract = item.get("output_contract") or {}
        if item["status"] == "complete" and contract.get("status") == "failed":
            for failed_check in contract.get("failed_checks", []):
                failure_categories[f"output_contract:{failed_check}"] += 1
    planned = len(attempts)
    return {
        "block_ids": [current["block_id"] for current in blocks],
        "model": deployment["name"],
        "model_digest": deployment["digest"],
        "workload_id": workload["workload_id"],
        "workload_kind": workload["kind"],
        "case_id": workload["case_id"],
        "planned_measured_runs": planned,
        "reliability": {
            "technical_successes": technical_successes,
            "infrastructure_failures": infrastructure_failures,
            "output_contract_passes": output_passes,
            "output_contract_failures": output_failures,
            "observed_technical_failure_rate": infrastructure_failures / planned,
            "observed_output_contract_failure_rate": output_failures / planned,
            "failure_categories": dict(sorted(failure_categories.items())),
            "semantic_quality_verified": False,
        },
        "performance": {
            key: _metric_distribution(attempts, key, plan["reporting"])
            for key in (
                "wall_time_seconds",
                "time_to_first_content_seconds",
                "prompt_eval_count",
                "prompt_eval_duration_seconds",
                "prompt_tokens_per_second",
                "eval_count",
                "eval_duration_seconds",
                "output_tokens_per_second",
            )
        },
        "model_load": [
            {
                key: attempt.get(key)
                for key in (
                    "status",
                    "wall_time_seconds",
                    "ollama_load_duration_ns",
                )
            }
            for current in blocks
            for attempt in current["preload_attempts"]
        ],
        "excluded_warmups": [
            {
                "status": attempt.get("status"),
                "metrics": (attempt.get("run") or {}).get("metrics"),
                "excluded_from_steady_state": attempt.get(
                    "excluded_from_steady_state", True
                ),
            }
            for current in blocks
            for attempt in current["warmup_attempts"]
        ],
    }


def _format_metric(distribution: dict[str, Any], key: str) -> str:
    value = distribution.get(key)
    return "—" if value is None else f"{value:.2f}"


def write_performance_report(
    repo_root: Path,
    study_dir: Path,
    record: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any]:
    condition_blocks: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for block in record["blocks"]:
        key = (block["deployment_alias"], block["workload_alias"])
        condition_blocks.setdefault(key, []).append(block)
    aggregates = [
        _aggregate_condition(condition_blocks[key], plan)
        for key in sorted(condition_blocks)
    ]
    public = {
        "schema_version": "1.0.0",
        "study_id": record["study_id"],
        "plan_id": plan["plan_id"],
        "plan_sha256": record["plan"]["sha256"],
        "generated_at": utc_now(),
        "methodology": {
            "warmup_runs_per_block": plan["methodology"]["warmup_runs_per_block"],
            "measured_runs_per_condition": plan["methodology"]["measured_runs_per_condition"],
            "measured_runs_per_block": plan["methodology"]["measured_runs_per_block"],
            "segments_per_condition": plan["methodology"]["segments_per_condition"],
            "performance_population": "Technically complete measured runs that passed the workload-specific deterministic output contract.",
            "reliability_population": "Every planned measured attempt, including infrastructure and output-contract failures.",
            "p90_minimum_n": plan["reporting"]["p90_minimum_n"],
            "p95_minimum_n": plan["reporting"]["p95_minimum_n"],
            "p99_minimum_n": plan["reporting"]["p99_minimum_n"],
            "percentile_method": "nearest_rank",
            "quality_evaluated": False,
            "composite_score": False,
        },
        "results": aggregates,
    }
    output_json = resolve_repo_path(repo_root, plan["reporting"]["public_json_path"])
    output_md = resolve_repo_path(repo_root, plan["reporting"]["public_markdown_path"])
    output_json.parent.mkdir(parents=True, exist_ok=True)
    write_json(output_json, public)

    lines = [
        "# Performance and Reliability Study v0.1",
        "",
        "This report separates natural-output latency from a controlled 256-token",
        "decode workload. Warm-up runs and model load are excluded from steady-state",
        "distributions. Reliability counts every planned measured attempt.",
        "",
        "| Workload | Model | Technical | Output contract | Wall P50 | Wall P90 | First content P50 | Decode tok/s P50 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in aggregates:
        reliability = result["reliability"]
        performance = result["performance"]
        lines.append(
            "| {workload} | `{model}` | {technical}/{planned} | {output}/{planned} | {wall50} s | {wall90} s | {first50} s | {decode50} |".format(
                workload=result["workload_kind"],
                model=result["model"],
                technical=reliability["technical_successes"],
                output=reliability["output_contract_passes"],
                planned=result["planned_measured_runs"],
                wall50=_format_metric(performance["wall_time_seconds"], "median_p50"),
                wall90=_format_metric(performance["wall_time_seconds"], "p90"),
                first50=_format_metric(
                    performance["time_to_first_content_seconds"], "median_p50"
                ),
                decode50=_format_metric(
                    performance["output_tokens_per_second"], "median_p50"
                ),
            )
        )
    lines.extend(
        [
            "",
            "P90 is shown only when at least 20 valid measured observations remain.",
            "P95 and P99 are not reported at this sample size. Natural-output timings",
            "include answer-length variation and must not be read as pure runtime speed.",
            "No semantic quality judgment or composite score is part of this study.",
            "",
        ]
    )
    output_md.write_text("\n".join(lines), encoding="utf-8")
    return {
        "public_json": {
            "path": str(output_json.relative_to(repo_root)),
            "sha256": sha256_file(output_json),
        },
        "public_markdown": {
            "path": str(output_md.relative_to(repo_root)),
            "sha256": sha256_file(output_md),
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="performance-reliability")
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start", help="Create a checkpoint without inference")
    start.add_argument("--plan", type=Path, default=DEFAULT_PLAN_PATH)
    start.add_argument("--studies-dir", type=Path, default=DEFAULT_STUDIES_DIR)
    start.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    advance = commands.add_parser("advance", help="Execute the next complete warm block")
    advance.add_argument("--study-dir", type=Path, required=True)
    advance.add_argument("--host", default="http://127.0.0.1:11434")
    advance.add_argument("--execute-live", action="store_true")
    status = commands.add_parser("status", help="Inspect a checkpoint without inference")
    status.add_argument("--study-dir", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    repo_root = Path.cwd().resolve()
    try:
        if args.command == "start":
            result = start_performance_study(
                repo_root,
                PerformanceStudyConfig(
                    plan_path=args.plan,
                    studies_dir=args.studies_dir,
                    runs_dir=args.runs_dir,
                ),
            )
        elif args.command == "advance":
            result = advance_performance_study(
                repo_root,
                args.study_dir,
                host=args.host,
                execute_live=args.execute_live,
            )
        else:
            resolved, record, _loaded = _load_study(repo_root, args.study_dir)
            result = _summary(record, resolved)
    except ResourceGatePause as error:
        print(
            json.dumps(
                {"status": "paused_resource_gate", "error": str(error)},
                ensure_ascii=False,
            )
        )
        return 2
    except Exception as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
