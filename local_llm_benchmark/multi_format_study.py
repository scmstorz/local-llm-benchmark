"""Durable controller for the measured multi-format Track A/Track B study."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from .log_incident_smokes import ResourceGatePause, _validate_artifacts, run_resource_gate
from .multi_format_canonical import (
    CanonicalRunConfig,
    execute_canonical_run,
    finalize_canonical_run,
    load_canonical_condition,
    prepare_canonical_run,
)
from .multi_format_mini import (
    MiniMultiFormatStartConfig,
    call_mini_multi_format_model,
    finalize_mini_multi_format_run,
    load_mini_multi_format_harness,
    start_mini_multi_format_run,
    step_mini_multi_format_action,
)
from .multi_format_pi_v03 import (
    finalize as finalize_pi_multi_format_run,
    prepare as prepare_pi_multi_format_run,
    run as execute_pi_multi_format_run,
    sandbox_check as validate_pi_multi_format_seatbelt,
)
from .multi_format_pi import PiMultiFormatPrepareConfig
from .ollama import OllamaClient, OllamaError
from .runner import (
    RunnerError,
    find_model,
    git_commit,
    load_json,
    resolve_repo_path,
    running_model_names,
    sha256_file,
    utc_now,
    write_json,
)


DEFAULT_PLAN = Path("tasks/agentic/multi-format-capability-sweep-v0.1.json")
DEFAULT_AUTHORIZATION = Path(
    "tasks/agentic/multi-format-capability-sweep-v0.1-execution-authorization.json"
)
DEFAULT_CONTROLLER_QUALIFICATION = Path(
    "tasks/agentic/multi-format-capability-sweep-v0.1-controller-qualification.json"
)
CONDITION_IDS = (
    "canonical-representation-v0.1",
    "mini-multi-format-v0.1",
    "pi-multi-format-v0.3",
)
TERMINAL_STATUSES = {"complete", "failed"}


@dataclass(frozen=True)
class MultiFormatStudyConfig:
    """Frozen inputs for one measured 15-cell capability study."""

    plan_path: Path = DEFAULT_PLAN
    authorization_path: Path = DEFAULT_AUTHORIZATION
    results_dir: Path = Path("results/agentic-sweeps")
    agent_results_dir: Path = Path("results/agentic-runs")
    host: str = "http://127.0.0.1:11434"


def _relative(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise RunnerError(f"Multi-format study artifact escapes repository: {path}") from exc


def _qualification(
    repo_root: Path, declaration: dict[str, Any], expected_id: str
) -> dict[str, Any]:
    value = declaration.get("qualification_path")
    if not isinstance(value, str) or not value:
        raise RunnerError(f"Condition {expected_id} lacks a qualification path")
    path = resolve_repo_path(repo_root, Path(value))
    document = load_json(path)
    if document.get("qualification_id") != declaration.get("qualification_id"):
        raise RunnerError(f"Condition qualification identity differs for {expected_id}")
    expected_hash = declaration.get("qualification_sha256")
    if not isinstance(expected_hash, str) or sha256_file(path) != expected_hash:
        raise RunnerError(f"Condition qualification drift for {expected_id}")
    return document


def _load_conditions(repo_root: Path, plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    declarations = plan.get("conditions")
    if (
        not isinstance(declarations, list)
        or [item.get("condition_id") for item in declarations if isinstance(item, dict)]
        != list(CONDITION_IDS)
    ):
        raise RunnerError("Study conditions must be canonical, Mini, then Pi v0.3")
    result: dict[str, dict[str, Any]] = {}
    for item in declarations:
        condition_id = item["condition_id"]
        qualification = _qualification(repo_root, item, condition_id)
        if condition_id == CONDITION_IDS[0]:
            path_value = item.get("condition_path")
            if not isinstance(path_value, str):
                raise RunnerError("Track A condition path is missing")
            loaded = load_canonical_condition(repo_root, Path(path_value))
            if (
                qualification.get("status") != "qualified_for_measured_plan"
                or qualification.get("condition_id") != condition_id
            ):
                raise RunnerError("Track A condition is not qualified for planning")
        elif condition_id == CONDITION_IDS[1]:
            path_value = item.get("harness_path")
            if not isinstance(path_value, str):
                raise RunnerError("Mini condition path is missing")
            loaded = load_mini_multi_format_harness(repo_root, Path(path_value))
            if qualification.get("harness_id") != condition_id:
                raise RunnerError("Mini qualification does not match its condition")
        else:
            path_value = item.get("harness_path")
            if not isinstance(path_value, str):
                raise RunnerError("Pi condition path is missing")
            # The v0.3 wrapper delegates definition validation during preparation.
            loaded = {"harness_path": resolve_repo_path(repo_root, Path(path_value))}
            if (
                qualification.get("harness_id") != condition_id
                or qualification.get("qualification_evidence", {}).get(
                    "fresh_real_seatbelt_checks_passed"
                )
                != 12
            ):
                raise RunnerError("Pi v0.3 qualification does not match its condition")
        result[condition_id] = {
            "declaration": item,
            "qualification": qualification,
            "loaded": loaded,
        }
    return result


def load_multi_format_study_plan(repo_root: Path, plan_path: Path = DEFAULT_PLAN) -> dict[str, Any]:
    """Load and validate the frozen three-condition, five-model study."""
    path = resolve_repo_path(repo_root, plan_path)
    plan = load_json(path)
    if (
        plan.get("schema_version") != "1.0.0"
        or plan.get("plan_id") != "multi-format-capability-sweep-v0.1"
        or plan.get("status") != "frozen_before_execution"
        or plan.get("track") != "A+B"
        or plan.get("study_mode") != "capability_sweep"
        or plan.get("evidence_class") != "measured_capability_sweep"
    ):
        raise RunnerError("Unexpected multi-format capability-study identity")
    runtime = plan.get("runtime", {})
    if (
        runtime.get("name") != "ollama"
        or runtime.get("expected_version") != "0.33.2"
        or runtime.get("host") != "http://127.0.0.1:11434"
        or runtime.get("must_be_reverified_before_execution") is not True
    ):
        raise RunnerError("Multi-format study runtime identity is incomplete")
    smoke_gate = plan.get("qualification_gate", {})
    report_value = smoke_gate.get("smoke_report_path")
    if not isinstance(report_value, str):
        raise RunnerError("Multi-format study lacks its smoke report gate")
    smoke_path = resolve_repo_path(repo_root, Path(report_value))
    smoke = load_json(smoke_path)
    if (
        sha256_file(smoke_path) != smoke_gate.get("smoke_report_sha256")
        or smoke.get("qualification_conclusion", {}).get(
            "smoke_gate_for_measured_plan_design_passed"
        )
        is not True
        or smoke.get("accepted_complete_systems")
        != ["mini-multi-format-v0.1", "pi-multi-format-v0.3"]
        or smoke_gate.get("smoke_runs_reused_as_measured") is not False
    ):
        raise RunnerError("Multi-format qualification-smoke gate is not satisfied")
    conditions = _load_conditions(repo_root, plan)
    lifecycle_value = plan.get("model_selection", {}).get("source")
    identity_value = plan.get("model_selection", {}).get("deployment_identity_source")
    if not isinstance(lifecycle_value, str) or not isinstance(identity_value, str):
        raise RunnerError("Multi-format study model sources are incomplete")
    lifecycle_path = resolve_repo_path(repo_root, Path(lifecycle_value))
    identity_path = resolve_repo_path(repo_root, Path(identity_value))
    lifecycle = load_json(lifecycle_path)
    identity = load_json(identity_path)
    selection = plan["model_selection"]
    if (
        sha256_file(lifecycle_path) != selection.get("source_sha256")
        or sha256_file(identity_path) != selection.get("deployment_identity_source_sha256")
        or selection.get("rule") != "include_in_default_sweeps equals true"
    ):
        raise RunnerError("Multi-format model-selection source drifted")
    expected_names = [
        item.get("model")
        for item in lifecycle.get("models", [])
        if isinstance(item, dict) and item.get("include_in_default_sweeps") is True
    ]
    identity_by_name = {
        item.get("name"): item
        for item in identity.get("deployments", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    deployments = plan.get("deployments")
    if (
        not isinstance(deployments, list)
        or [item.get("name") for item in deployments if isinstance(item, dict)]
        != expected_names
        or selection.get("selected_count") != len(expected_names)
        or len(expected_names) != 5
    ):
        raise RunnerError("Study deployments do not equal the active-default cohort")
    models: dict[str, dict[str, Any]] = {}
    for item in deployments:
        name = item["name"]
        source = identity_by_name.get(name)
        if (
            source is None
            or item.get("deployment_id") != source.get("deployment_id")
            or item.get("digest") != source.get("digest")
            or item.get("size_bytes") != source.get("size_bytes")
            or re.fullmatch(r"[0-9a-f]{64}", str(item.get("digest"))) is None
        ):
            raise RunnerError(f"Invalid deployment identity for {name}")
        models[name] = item
    expected = {(condition, model) for condition in CONDITION_IDS for model in models}
    observed: set[tuple[str, str]] = set()
    order = plan.get("execution_order")
    if not isinstance(order, list) or len(order) != 15:
        raise RunnerError("Multi-format study requires exactly 15 cells")
    prior_model = None
    for position, unit in enumerate(order, start=1):
        if not isinstance(unit, dict) or unit.get("position") != position:
            raise RunnerError("Multi-format study positions must be contiguous")
        key = (unit.get("condition_id"), unit.get("model"))
        if key not in expected or key in observed:
            raise RunnerError(f"Invalid or duplicate multi-format study cell: {key}")
        if unit.get("model") == prior_model:
            raise RunnerError("The same model may not occupy adjacent study cells")
        observed.add(key)
        prior_model = unit.get("model")
    if observed != expected:
        raise RunnerError("Execution order is not the full condition/model product")
    comparison = plan.get("comparison_rules", {})
    if (
        comparison.get("runs_per_configuration") != 1
        or comparison.get("automatic_retries") != 0
        or comparison.get("adaptive_repetitions") is not False
        or comparison.get("terminal_attempts_not_repeated") is not True
        or comparison.get("track_a_and_track_b_pooled") is not False
        or comparison.get("one_factor_causal_harness_claim_allowed") is not False
        or comparison.get("reliability_probability_claims") is not False
        or comparison.get("latency_distribution_claims") is not False
    ):
        raise RunnerError("Multi-format study comparison rules are invalid")
    outcome = plan.get("outcome_model", {})
    if (
        outcome.get("primary") != "semantic_verified_success"
        or outcome.get("secondary") != "strict_transport_compliance"
        or outcome.get("supplemental_free_text_claim_review_required") is not True
        or outcome.get("composite_score") is not False
    ):
        raise RunnerError("Multi-format study outcome model is invalid")
    inference = plan.get("shared_inference", {})
    if (
        inference.get("temperature") != 0.0
        or inference.get("seed") != 42
        or inference.get("think") is not False
        or inference.get("num_ctx") != 16384
        or inference.get("num_predict_per_turn") != 5000
        or inference.get("maximum_active_wall_time_seconds") != 300
        or inference.get("provider_request_timeout_seconds") != 180
    ):
        raise RunnerError("Multi-format study inference controls differ")
    authorization = plan.get("authorization", {})
    if (
        authorization.get("live_execution_authorized") is not False
        or authorization.get("post_freeze_authorization_required") is not True
        or authorization.get("fresh_clean_window_confirmation_required") is not True
    ):
        raise RunnerError("Frozen multi-format plan must defer live authorization")
    gate = plan.get("resource_gate", {})
    rules = gate.get("blocking_process_rules")
    if (
        gate.get("empty_state_observation_seconds") != 30
        or gate.get("loaded_models_must_be_empty_before_each_unit") is not True
        or gate.get("model_unloaded_after_each_unit") is not True
        or not isinstance(rules, list)
        or not rules
    ):
        raise RunnerError("Multi-format study resource gate is incomplete")
    for rule in rules:
        try:
            re.compile(rule["pattern"])
        except (KeyError, TypeError, re.error) as exc:
            raise RunnerError("Invalid multi-format study process rule") from exc
    _validate_artifacts(repo_root, plan.get("frozen_inputs", {}).get("artifacts"), "multi-format study")
    return {
        "plan": plan,
        "path": path,
        "sha256": sha256_file(path),
        "conditions": conditions,
        "models": models,
        "resource_gate": {
            "empty_state_observation_seconds": 30,
            "loaded_models_must_be_empty_before_each_unit": True,
            "blocking_process_rules": rules,
        },
    }


def load_execution_authorization(
    repo_root: Path, authorization_path: Path, loaded_plan: dict[str, Any]
) -> dict[str, Any]:
    """Validate authorization created only after the plan was frozen."""
    path = resolve_repo_path(repo_root, authorization_path)
    authorization = load_json(path)
    plan = loaded_plan["plan"]
    if (
        authorization.get("schema_version") != "1.0.0"
        or authorization.get("authorization_id")
        != "multi-format-capability-sweep-v0.1-execution-authorization"
        or authorization.get("status") != "authorized_pending_resource_gate"
        or authorization.get("plan_id") != plan["plan_id"]
        or authorization.get("plan_sha256") != loaded_plan["sha256"]
        or authorization.get("live_execution_authorized") is not True
        or authorization.get("cell_count") != 15
        or authorization.get("automatic_retries") != 0
        or authorization.get("authorized_models") != list(loaded_plan["models"])
        or authorization.get("authorized_conditions") != list(CONDITION_IDS)
        or authorization.get("resource_gate_still_required") is not True
    ):
        raise RunnerError("Invalid multi-format study execution authorization")
    return {"authorization": authorization, "path": path, "sha256": sha256_file(path)}


def load_controller_qualification(repo_root: Path) -> dict[str, Any]:
    """Require the no-inference-qualified controller before measured use."""
    path = resolve_repo_path(repo_root, DEFAULT_CONTROLLER_QUALIFICATION)
    qualification = load_json(path)
    evidence = qualification.get("qualification_evidence", {})
    if (
        qualification.get("qualification_id")
        != "multi-format-capability-sweep-v0.1-controller-no-inference"
        or qualification.get("status") != "qualified_for_frozen_plan"
        or evidence.get("live_ollama_requests") != 0
        or evidence.get("live_model_inference") is not False
    ):
        raise RunnerError("Invalid multi-format study controller qualification")
    _validate_artifacts(repo_root, qualification.get("artifacts"), "multi-format controller")
    return {"qualification": qualification, "path": path, "sha256": sha256_file(path)}


def _process_snapshot() -> list[dict[str, Any]]:
    completed = subprocess.run(
        ["ps", "-axo", "pid=,pcpu=,etime=,command="],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    if completed.returncode != 0:
        raise RunnerError("Cannot inspect concurrent processes")
    result = []
    for line in completed.stdout.splitlines():
        match = re.match(r"\s*(\d+)\s+([0-9.]+)\s+(\S+)\s+(.*)", line)
        if match:
            result.append(
                {
                    "pid": int(match.group(1)),
                    "cpu_percent": float(match.group(2)),
                    "elapsed": match.group(3),
                    "command": match.group(4),
                }
            )
    return result


def _blocking_processes(
    rules: list[dict[str, str]], processes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    blocked = []
    for process in processes:
        if process.get("pid") == os.getpid():
            continue
        command = str(process.get("command", ""))
        for rule in rules:
            if re.search(rule["pattern"], command):
                blocked.append(
                    {
                        "rule_id": rule["rule_id"],
                        "pid": process.get("pid"),
                        "cpu_percent": process.get("cpu_percent"),
                        "elapsed": process.get("elapsed"),
                        "command_sha256": hashlib.sha256(command.encode()).hexdigest(),
                    }
                )
                break
    return blocked


def _recount(record: dict[str, Any]) -> None:
    complete = [item for item in record["units"] if item["status"] == "complete"]
    record["complete_unit_count"] = len(complete)
    record["failed_unit_count"] = sum(item["status"] == "failed" for item in record["units"])
    record["semantic_verified_success_count"] = sum(
        bool(item.get("outcome", {}).get("semantic_verified_success")) for item in complete
    )
    record["strict_transport_compliance_count"] = sum(
        bool(item.get("outcome", {}).get("strict_transport_compliance")) for item in complete
    )


def _current_unit(record: dict[str, Any]) -> dict[str, Any] | None:
    return next((item for item in record["units"] if item["status"] not in TERMINAL_STATUSES), None)


def _summary(record: dict[str, Any], study_dir: Path) -> dict[str, Any]:
    waiting = _current_unit(record)
    return {
        "study_id": record["study_id"],
        "study_dir": str(study_dir),
        "status": record["status"],
        "unit_count": record["unit_count"],
        "complete_unit_count": record["complete_unit_count"],
        "failed_unit_count": record["failed_unit_count"],
        "semantic_verified_success_count": record["semantic_verified_success_count"],
        "strict_transport_compliance_count": record["strict_transport_compliance_count"],
        "waiting": None
        if waiting is None
        else {
            "position": waiting["position"],
            "condition_id": waiting["condition_id"],
            "model": waiting["model"],
            "unit_status": waiting["status"],
            "run_dir": waiting.get("run_dir"),
        },
    }


def _run_record(repo_root: Path, unit: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    value = unit.get("run_dir")
    if not isinstance(value, str):
        raise RunnerError("Study unit has no run directory")
    run_dir = resolve_repo_path(repo_root, Path(value))
    return run_dir, load_json(run_dir / "run.json")


def _mark_interrupted(unit: dict[str, Any], state: str) -> None:
    unit["status"] = "failed_needs_cleanup"
    unit["error"] = {
        "category": "infrastructure_or_control_failure",
        "type": "interrupted_live_process",
        "message": f"Controller resumed while raw run remained in state {state!r}.",
    }
    unit["outcome"] = {
        "runtime_success": False,
        "agent_termination_valid": False,
        "semantic_verified_success": False,
        "strict_transport_compliance": False,
        "failure_category": "infrastructure_or_control_failure",
        "failure_type": "interrupted_live_process",
    }


def _sync_unit(repo_root: Path, unit: dict[str, Any], *, after_live: bool = False) -> None:
    if not unit.get("run_dir"):
        return
    _run_dir, run = _run_record(repo_root, unit)
    state = run.get("state")
    if unit["condition_id"] == CONDITION_IDS[0]:
        mapping = {
            "prepared_not_executed": "awaiting_model",
            "execution_complete_verification_pending": "verification_pending",
            "complete": "complete_needs_cleanup",
        }
        running = "model_call_running"
    elif unit["condition_id"] == CONDITION_IDS[1]:
        mapping = {
            "awaiting_model": "awaiting_model",
            "awaiting_action": "awaiting_action",
            "trajectory_complete_verification_pending": "verification_pending",
            "complete": "complete_needs_cleanup",
        }
        running = "model_call_running"
    else:
        mapping = {
            "prepared_not_executed": "sandbox_accepted"
            if run.get("execution_boundary", {}).get("sandbox_acceptance_passed")
            and run.get("execution_boundary", {}).get("explicit_extension_acceptance_passed")
            else "sandbox_pending",
            "execution_complete_verification_pending": "verification_pending",
            "complete": "complete_needs_cleanup",
        }
        running = "running"
    if state == running:
        if after_live:
            raise RunnerError("Live boundary returned while the raw run remained running")
        _mark_interrupted(unit, str(state))
        return
    if state not in mapping:
        raise RunnerError(f"Unsupported raw state for {unit['condition_id']}: {state!r}")
    unit["status"] = mapping[state]
    if state == "complete":
        unit["outcome"] = run.get("outcome")
        unit["trajectory"] = run.get("trajectory")
        unit["verification"] = {
            "essential_pass_count": run.get("verification", {}).get("essential_pass_count"),
            "essential_check_count": run.get("verification", {}).get("essential_check_count"),
            "failed_check_ids": [
                item.get("check_id")
                for item in run.get("verification", {}).get("checks", [])
                if item.get("passed") is False
            ],
        }


def _load_study(repo_root: Path, study_dir: Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    resolved = resolve_repo_path(repo_root, study_dir)
    record = load_json(resolved / "study.json")
    if record.get("evidence_class") != "measured_capability_sweep":
        raise RunnerError("Record is not a measured multi-format study")
    loaded = load_multi_format_study_plan(repo_root, Path(record["plan"]["path"]))
    if loaded["sha256"] != record["plan"]["sha256"]:
        raise RunnerError("Multi-format study plan changed after start")
    authorization = load_execution_authorization(
        repo_root, Path(record["authorization"]["path"]), loaded
    )
    if authorization["sha256"] != record["authorization"]["sha256"]:
        raise RunnerError("Multi-format authorization changed after start")
    controller = load_controller_qualification(repo_root)
    if (
        record["controller"]["implementation_sha256"] != sha256_file(Path(__file__))
        or record["controller"]["qualification_sha256"] != controller["sha256"]
    ):
        raise RunnerError("Multi-format controller changed after start")
    return resolved, record, loaded


def start_multi_format_study(repo_root: Path, config: MultiFormatStudyConfig) -> dict[str, Any]:
    """Create the measured study record and prepare its first cell offline."""
    loaded = load_multi_format_study_plan(repo_root, config.plan_path)
    authorization = load_execution_authorization(repo_root, config.authorization_path, loaded)
    controller = load_controller_qualification(repo_root)
    plan = loaded["plan"]
    if config.host.rstrip("/") != plan["runtime"]["host"].rstrip("/"):
        raise RunnerError("Configured Ollama host differs from the frozen study")
    results = resolve_repo_path(repo_root, config.results_dir)
    agent_results = resolve_repo_path(repo_root, config.agent_results_dir)
    results.mkdir(parents=True, exist_ok=True)
    agent_results.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    study_id = f"multi-format-capability-{timestamp}-{secrets.token_hex(4)}"
    study_dir = results / study_id
    study_dir.mkdir()
    record = {
        "schema_version": "1.0.0",
        "study_id": study_id,
        "status": "ready_for_local_preparation",
        "started_at": utc_now(),
        "completed_at": None,
        "track": "A+B",
        "evidence_class": plan["evidence_class"],
        "git_commit": git_commit(repo_root),
        "host": config.host.rstrip("/"),
        "ollama_version": plan["runtime"]["expected_version"],
        "plan": {"plan_id": plan["plan_id"], "path": _relative(repo_root, loaded["path"]), "sha256": loaded["sha256"]},
        "authorization": {"authorization_id": authorization["authorization"]["authorization_id"], "path": _relative(repo_root, authorization["path"]), "sha256": authorization["sha256"]},
        "controller": {"implementation_path": _relative(repo_root, Path(__file__)), "implementation_sha256": sha256_file(Path(__file__)), "qualification_path": _relative(repo_root, controller["path"]), "qualification_sha256": controller["sha256"]},
        "agent_results_dir": _relative(repo_root, agent_results),
        "unit_count": len(plan["execution_order"]),
        "complete_unit_count": 0,
        "failed_unit_count": 0,
        "semantic_verified_success_count": 0,
        "strict_transport_compliance_count": 0,
        "pause": None,
        "units": [
            {
                "position": item["position"],
                "condition_id": item["condition_id"],
                "track": "A" if item["condition_id"] == CONDITION_IDS[0] else "B",
                "model": item["model"],
                "deployment_id": loaded["models"][item["model"]]["deployment_id"],
                "digest": loaded["models"][item["model"]]["digest"],
                "status": "pending",
                "run_id": None,
                "run_dir": None,
                "resource_gate": None,
                "sandbox_acceptance": None,
                "outcome": None,
                "trajectory": None,
                "verification": None,
                "error": None,
                "postflight_running_models": None,
            }
            for item in plan["execution_order"]
        ],
    }
    write_json(study_dir / "study.json", record)
    return advance_multi_format_study(repo_root, study_dir)


def advance_multi_format_study(repo_root: Path, study_dir: Path) -> dict[str, Any]:
    """Advance local preparation, action processing or verification."""
    resolved, record, loaded = _load_study(repo_root, study_dir)
    path = resolved / "study.json"
    while True:
        unit = _current_unit(record)
        if unit is None:
            _recount(record)
            record["status"] = "complete" if record["failed_unit_count"] == 0 else "complete_with_failures"
            record["completed_at"] = record.get("completed_at") or utc_now()
            record["pause"] = None
            write_json(path, record)
            return _summary(record, resolved)
        if unit.get("run_dir"):
            _sync_unit(repo_root, unit)
            _recount(record)
            write_json(path, record)
        condition = unit["condition_id"]
        if unit["status"] == "pending":
            if condition == CONDITION_IDS[0]:
                started = prepare_canonical_run(
                    repo_root,
                    CanonicalRunConfig(
                        model=unit["model"],
                        condition_path=Path(loaded["conditions"][condition]["declaration"]["condition_path"]),
                        results_dir=Path(record["agent_results_dir"]),
                        host=record["host"],
                    ),
                )
                unit["status"] = "awaiting_model"
            elif condition == CONDITION_IDS[1]:
                started = start_mini_multi_format_run(
                    repo_root,
                    MiniMultiFormatStartConfig(
                        model=unit["model"],
                        harness_path=Path(loaded["conditions"][condition]["declaration"]["harness_path"]),
                        results_dir=Path(record["agent_results_dir"]),
                        host=record["host"],
                    ),
                )
                unit["status"] = "awaiting_model"
            else:
                started = prepare_pi_multi_format_run(
                    repo_root,
                    PiMultiFormatPrepareConfig(
                        model=unit["model"],
                        results_dir=Path(record["agent_results_dir"]),
                        host=record["host"],
                    ),
                )
                unit["status"] = "sandbox_pending"
            unit["run_id"] = started["run_id"]
            unit["run_dir"] = _relative(repo_root, Path(started["run_dir"]))
            unit["prepared_at"] = utc_now()
            record["status"] = "waiting_for_live_boundary"
            write_json(path, record)
            continue
        run_dir, _run = _run_record(repo_root, unit)
        if unit["status"] == "awaiting_action":
            step_mini_multi_format_action(repo_root, run_dir)
            _sync_unit(repo_root, unit)
            write_json(path, record)
            continue
        if unit["status"] == "sandbox_pending":
            acceptance = validate_pi_multi_format_seatbelt(run_dir)
            unit["sandbox_acceptance"] = {
                "passed": acceptance["passed"],
                "validated_at": acceptance["validated_at"],
                "profile_sha256": acceptance["profile_sha256"],
                "checks_passed": sum(item["passed"] for item in acceptance["checks"]),
                "checks_total": len(acceptance["checks"]),
            }
            unit["status"] = "sandbox_accepted"
            record["status"] = "waiting_for_live_boundary"
            write_json(path, record)
            return _summary(record, resolved)
        if unit["status"] == "verification_pending":
            if condition == CONDITION_IDS[0]:
                finalize_canonical_run(repo_root, run_dir)
            elif condition == CONDITION_IDS[1]:
                finalize_mini_multi_format_run(repo_root, run_dir)
            else:
                finalize_pi_multi_format_run(repo_root, run_dir)
            _sync_unit(repo_root, unit)
            _recount(record)
            write_json(path, record)
            continue
        if unit["status"] in {"awaiting_model", "sandbox_accepted", "complete_needs_cleanup", "failed_needs_cleanup"}:
            record["status"] = "waiting_for_cleanup" if unit["status"].endswith("needs_cleanup") else "waiting_for_live_boundary"
            write_json(path, record)
            return _summary(record, resolved)
        raise RunnerError(f"Cannot advance multi-format unit state {unit['status']!r}")


def _validate_deployment(client: OllamaClient, unit: dict[str, Any], version: str) -> None:
    observed_version = client.version().get("version")
    if observed_version != version:
        raise RunnerError(f"Multi-format study requires Ollama {version}, found {observed_version}")
    model = find_model(client.list_models(), unit["model"])
    if model.get("digest") != unit["digest"]:
        raise RunnerError(f"Ollama digest drift for {unit['model']}")


def run_multi_format_study_live(
    repo_root: Path,
    study_dir: Path,
    *,
    client: OllamaClient | None = None,
    process_reader: Callable[[], list[dict[str, Any]]] = _process_snapshot,
    sleep: Callable[[float], None] = time.sleep,
    exclusive_window_confirmed: bool = False,
) -> dict[str, Any]:
    """Execute one live Track A request, Mini turn or complete Pi trajectory."""
    if not exclusive_window_confirmed:
        raise RunnerError("Live multi-format execution requires an exclusive-window confirmation")
    resolved, record, loaded = _load_study(repo_root, study_dir)
    unit = _current_unit(record)
    if unit is None:
        raise RunnerError("Multi-format study has no pending live boundary")
    _sync_unit(repo_root, unit)
    expected = "sandbox_accepted" if unit["condition_id"] == CONDITION_IDS[2] else "awaiting_model"
    if unit["status"] != expected:
        write_json(resolved / "study.json", record)
        raise RunnerError(f"Study cell is not ready for live execution: {unit['status']}")
    ollama = client or OllamaClient(record["host"])
    _validate_deployment(ollama, unit, record["ollama_version"])
    _run_dir, run = _run_record(repo_root, unit)
    first_request = unit["condition_id"] != CONDITION_IDS[1] or run.get("trajectory", {}).get("model_requests") == 0
    try:
        if first_request:
            gate_plan = {
                "runtime": {"name": "ollama", "version": record["ollama_version"]},
                "deployment": {"name": unit["model"], "digest": unit["digest"]},
                "resource_gate": loaded["resource_gate"],
            }
            unit["resource_gate"] = run_resource_gate(
                gate_plan, client=ollama, process_reader=process_reader, sleep=sleep
            )
        else:
            blockers = _blocking_processes(
                loaded["resource_gate"]["blocking_process_rules"], process_reader()
            )
            if blockers:
                raise ResourceGatePause(
                    "Concurrent workload appeared during the Mini trajectory.",
                    {"passed": False, "stage": "continuation_process_snapshot", "blocking_processes": blockers},
                )
            unexpected = sorted(
                name for name in running_model_names(ollama.list_running_models()) if name != unit["model"]
            )
            if unexpected:
                raise ResourceGatePause(
                    "Unrelated Ollama activity appeared during the Mini trajectory.",
                    {"passed": False, "stage": "continuation_ollama_snapshot", "running_models": unexpected},
                )
    except ResourceGatePause as exc:
        record["status"] = "paused_resource_gate"
        record["pause"] = getattr(exc, "evidence", {"reason": str(exc)})
        write_json(resolved / "study.json", record)
        raise
    record["status"] = "running_live_boundary"
    record["pause"] = None
    write_json(resolved / "study.json", record)
    run_dir, _run = _run_record(repo_root, unit)
    if unit["condition_id"] == CONDITION_IDS[0]:
        execute_canonical_run(repo_root, run_dir)
    elif unit["condition_id"] == CONDITION_IDS[1]:
        call_mini_multi_format_model(repo_root, run_dir)
    else:
        execute_pi_multi_format_run(repo_root, run_dir)
    _sync_unit(repo_root, unit, after_live=True)
    record["status"] = "waiting_for_local_step"
    write_json(resolved / "study.json", record)
    return _summary(record, resolved)


def cleanup_multi_format_study_unit(
    repo_root: Path, study_dir: Path, *, client: OllamaClient | None = None
) -> dict[str, Any]:
    """Unload the terminal cell and advance without retrying it."""
    resolved, record, _loaded = _load_study(repo_root, study_dir)
    unit = _current_unit(record)
    if unit is None or unit["status"] not in {"complete_needs_cleanup", "failed_needs_cleanup"}:
        raise RunnerError("No terminal multi-format cell is awaiting cleanup")
    ollama = client or OllamaClient(record["host"])
    ollama.unload_model(unit["model"])
    running = running_model_names(ollama.list_running_models())
    unit["postflight_running_models"] = running
    if running:
        record["status"] = "paused_resource_gate"
        record["pause"] = {
            "at": utc_now(),
            "stage": "postflight_cleanup",
            "reason": "Ollama was not empty after cleanup.",
            "running_models": running,
        }
        write_json(resolved / "study.json", record)
        raise ResourceGatePause(record["pause"]["reason"], record["pause"])
    unit["status"] = "failed" if unit["status"] == "failed_needs_cleanup" else "complete"
    unit["completed_at"] = utc_now()
    _recount(record)
    record["status"] = "ready_for_local_preparation"
    record["pause"] = None
    write_json(resolved / "study.json", record)
    return advance_multi_format_study(repo_root, resolved)


def drive_multi_format_study(
    repo_root: Path, study_dir: Path, *, exclusive_window_confirmed: bool
) -> dict[str, Any]:
    """Drive all checkpoints until completion or a resource/control pause."""
    if not exclusive_window_confirmed:
        raise RunnerError("Drive mode requires an exclusive-window confirmation")
    while True:
        summary = advance_multi_format_study(repo_root, study_dir)
        if summary["status"] in {"complete", "complete_with_failures"}:
            return summary
        status = summary["waiting"]["unit_status"]
        if status in {"awaiting_model", "sandbox_accepted"}:
            run_multi_format_study_live(
                repo_root, study_dir, exclusive_window_confirmed=True
            )
        elif status in {"complete_needs_cleanup", "failed_needs_cleanup"}:
            cleanup_multi_format_study_unit(repo_root, study_dir)
        else:
            raise RunnerError(f"Drive mode cannot continue from {status!r}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser("start")
    start.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    start.add_argument("--authorization", type=Path, default=DEFAULT_AUTHORIZATION)
    start.add_argument("--results-dir", type=Path, default=Path("results/agentic-sweeps"))
    start.add_argument("--agent-results-dir", type=Path, default=Path("results/agentic-runs"))
    start.add_argument("--host", default="http://127.0.0.1:11434")
    for name in ("advance", "live", "cleanup", "drive"):
        child = subparsers.add_parser(name)
        child.add_argument("--study-dir", type=Path, required=True)
        if name in {"live", "drive"}:
            child.add_argument("--exclusive-window-confirmed", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    try:
        if args.command == "start":
            result = start_multi_format_study(
                repo_root,
                MultiFormatStudyConfig(
                    plan_path=args.plan,
                    authorization_path=args.authorization,
                    results_dir=args.results_dir,
                    agent_results_dir=args.agent_results_dir,
                    host=args.host,
                ),
            )
        elif args.command == "advance":
            result = advance_multi_format_study(repo_root, args.study_dir)
        elif args.command == "live":
            result = run_multi_format_study_live(
                repo_root, args.study_dir, exclusive_window_confirmed=args.exclusive_window_confirmed
            )
        elif args.command == "cleanup":
            result = cleanup_multi_format_study_unit(repo_root, args.study_dir)
        else:
            result = drive_multi_format_study(
                repo_root, args.study_dir, exclusive_window_confirmed=args.exclusive_window_confirmed
            )
    except (OSError, RunnerError, OllamaError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
