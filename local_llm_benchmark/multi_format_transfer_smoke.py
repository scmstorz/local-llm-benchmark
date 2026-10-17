"""Durable controller for the excluded Phase 96 transfer smoke pair.

Offline preparation is intentionally allowed without an execution authorization.
Every Ollama boundary requires a separate post-freeze authorization, an explicit
exclusive-window confirmation and the frozen resource gate.
"""

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
from .multi_format_mini import MiniMultiFormatStartConfig
from .multi_format_mini_v02 import call as call_mini
from .multi_format_mini_v02 import finalize as finalize_mini
from .multi_format_mini_v02 import start as prepare_mini
from .multi_format_mini_v02 import step as step_mini
from .multi_format_pi import PiMultiFormatPrepareConfig
from .multi_format_pi_v04 import finalize as finalize_pi
from .multi_format_pi_v04 import prepare as prepare_pi
from .multi_format_pi_v04 import run as run_pi
from .multi_format_pi_v04 import sandbox_check as check_pi_sandbox
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


DEFAULT_PLAN = Path("tasks/agentic/track-b/multi-format-transfer-smoke-v0.2.json")
DEFAULT_AUTHORIZATION = Path(
    "tasks/agentic/track-b/"
    "multi-format-transfer-smoke-v0.2-execution-authorization.json"
)
DEFAULT_CONTROLLER_QUALIFICATION = Path(
    "tasks/agentic/track-b/"
    "multi-format-transfer-smoke-v0.2-controller-qualification.json"
)
SYSTEM_IDS = ("pi-multi-format-v0.4", "mini-multi-format-v0.2")
MODEL = "qwen3.8:27b-mlx"
TERMINAL_STATUSES = {"complete", "failed"}


@dataclass(frozen=True)
class TransferSmokeConfig:
    """Frozen inputs for one excluded two-system transfer smoke."""

    plan_path: Path = DEFAULT_PLAN
    results_dir: Path = Path("results/agentic-transfer-smokes")
    agent_results_dir: Path = Path("results/agentic-runs")
    host: str = "http://127.0.0.1:11434"


def _relative(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise RunnerError(f"Transfer-smoke artifact escapes repository: {path}") from exc


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


def load_transfer_smoke_plan(
    repo_root: Path, plan_path: Path = DEFAULT_PLAN
) -> dict[str, Any]:
    """Load the frozen two-system, one-attempt excluded smoke plan."""
    path = resolve_repo_path(repo_root, plan_path)
    plan = load_json(path)
    if (
        plan.get("schema_version") != "1.0.0"
        or plan.get("plan_id") != "multi-format-transfer-smoke-v0.2"
        or plan.get("status") != "frozen_before_execution"
        or plan.get("track") != "B"
        or plan.get("study_mode") != "transfer_qualification_smoke"
        or plan.get("evidence_class") != "excluded_development_smoke_pair"
    ):
        raise RunnerError("Unexpected Phase 96 transfer-smoke identity")
    runtime = plan.get("runtime", {})
    if (
        runtime.get("name") != "ollama"
        or runtime.get("expected_version") != "0.33.2"
        or runtime.get("host") != "http://127.0.0.1:11434"
        or runtime.get("must_be_reverified_before_execution") is not True
    ):
        raise RunnerError("Transfer-smoke runtime identity is incomplete")
    deployment = plan.get("deployment", {})
    if (
        deployment.get("name") != MODEL
        or deployment.get("deployment_id")
        != "qwen3-8-27b-mlx-5642e97495e1-ollama-0-33-2"
        or deployment.get("digest")
        != "5642e97495e1a088883805981563dcdc4a040c2f53388b7a41d1f24d3622cf7e"
        or deployment.get("size_bytes") != 18174721847
        or deployment.get("selection_rule")
        != "same previously characterized deployment used for both machinery smokes"
    ):
        raise RunnerError("Transfer-smoke deployment identity differs")
    case = plan.get("case", {})
    if (
        case.get("case_id") != "agentic.documents.supplier-award-reconciliation"
        or case.get("case_version") != "2.0.0"
        or case.get("case_path")
        != "tasks/agentic/multi-format-document-analysis/"
        "supplier-award-reconciliation/case-v0.2.json"
    ):
        raise RunnerError("Transfer-smoke case identity differs")
    systems = plan.get("systems")
    if (
        not isinstance(systems, list)
        or [item.get("system_id") for item in systems if isinstance(item, dict)]
        != list(SYSTEM_IDS)
    ):
        raise RunnerError("Transfer-smoke systems must be Pi v0.4 then Mini v0.2")
    for system in systems:
        harness_value = system.get("harness_path")
        qualification_value = system.get("qualification_path")
        if not isinstance(harness_value, str) or not isinstance(
            qualification_value, str
        ):
            raise RunnerError("Transfer-smoke system paths are incomplete")
        harness_path = resolve_repo_path(repo_root, Path(harness_value))
        qualification_path = resolve_repo_path(repo_root, Path(qualification_value))
        if sha256_file(harness_path) != system.get("harness_sha256"):
            raise RunnerError(f"Harness drift for {system['system_id']}")
        if sha256_file(qualification_path) != system.get("qualification_sha256"):
            raise RunnerError(f"Qualification drift for {system['system_id']}")
        qualification = load_json(qualification_path)
        if (
            qualification.get("harness_id") != system["system_id"]
            or qualification.get("status") != "qualified_for_transfer_smoke_freeze"
            or qualification.get("live_ollama_requests") != 0
        ):
            raise RunnerError(f"Unqualified transfer system {system['system_id']}")
    order = plan.get("execution_order")
    if (
        not isinstance(order, list)
        or [item.get("position") for item in order if isinstance(item, dict)] != [1, 2]
        or [item.get("system_id") for item in order if isinstance(item, dict)]
        != list(SYSTEM_IDS)
        or any(item.get("model") != MODEL for item in order)
    ):
        raise RunnerError("Transfer-smoke execution order differs")
    inference = plan.get("shared_inference", {})
    if (
        inference.get("temperature") != 0.0
        or inference.get("seed") != 42
        or inference.get("think") is not False
        or inference.get("num_ctx") != 16384
        or inference.get("num_predict_per_turn") != 5000
        or inference.get("maximum_active_wall_time_seconds") != 300
        or inference.get("provider_request_timeout_seconds") != 180
        or inference.get("maximum_agent_turns") is not None
        or inference.get("maximum_total_output_tokens") is not None
        or inference.get("maximum_protocol_errors") is not None
        or inference.get("maximum_artifact_tool_calls_emergency") != 40
        or inference.get("automatic_retries") != 0
    ):
        raise RunnerError("Transfer-smoke inference controls differ")
    comparison = plan.get("comparison_rules", {})
    if (
        comparison.get("one_attempt_per_complete_system") is not True
        or comparison.get("automatic_retries") != 0
        or comparison.get("adaptive_repetitions") is not False
        or comparison.get("historical_runs_reused") is not False
        or comparison.get("excluded_from_measured_aggregates") is not True
        or comparison.get("model_or_system_ranking_claim_allowed") is not False
        or comparison.get("one_factor_causal_claim_allowed") is not False
    ):
        raise RunnerError("Transfer-smoke comparison rules differ")
    authorization = plan.get("authorization", {})
    if (
        authorization.get("live_execution_authorized") is not False
        or authorization.get("authorization_artifact_present") is not False
        or authorization.get("post_freeze_hash_bound_authorization_required")
        is not True
        or authorization.get("fresh_exclusive_window_confirmation_required")
        is not True
        or authorization.get("resource_gate_still_required_after_authorization")
        is not True
    ):
        raise RunnerError("Frozen transfer smoke must not authorize execution")
    execution = plan.get("execution_protocol", {})
    if (
        execution.get("offline_preparation_of_both_systems_before_authorization_allowed")
        is not True
        or execution.get("offline_preparation_contacts_ollama") is not False
        or execution.get("offline_pi_readiness_acceptance_is_live_freshness") is not False
        or execution.get(
            "fresh_real_thirteen_check_seatbelt_acceptance_after_resource_gate_before_pi_inference"
        )
        is not True
        or execution.get("hidden_verification_after_terminal_model_output") is not True
        or execution.get("raw_runs_preserved") is not True
        or execution.get("automatic_retries") != 0
        or execution.get("authorization_file_may_be_created_only_after_this_plan_is_committed")
        is not True
    ):
        raise RunnerError("Transfer-smoke execution protocol differs")
    gate = plan.get("resource_gate", {})
    rules = gate.get("blocking_process_rules")
    if (
        gate.get("empty_state_observation_seconds") != 30
        or gate.get("loaded_models_must_be_empty_before_each_system") is not True
        or gate.get("model_unloaded_after_each_system") is not True
        or gate.get("postflight_loaded_models_must_be_empty") is not True
        or not isinstance(rules, list)
        or not rules
    ):
        raise RunnerError("Transfer-smoke resource gate is incomplete")
    for rule in rules:
        try:
            re.compile(rule["pattern"])
        except (KeyError, TypeError, re.error) as exc:
            raise RunnerError("Invalid transfer-smoke process rule") from exc
    success = plan.get("success_gate", {})
    if (
        success.get("both_units_must_have_terminal_outcomes") is not True
        or success.get("verified_success_required") is not False
        or success.get("adapter_or_orchestration_defect_allowed") is not False
        or success.get("unclassified_failure_allowed") is not False
        or success.get("strict_transport_reported_separately") is not True
    ):
        raise RunnerError("Transfer-smoke success gate differs")
    reporting = plan.get("reporting", {})
    if (
        reporting.get("report_id") != "multi-format-transfer-smoke-v0.2"
        or reporting.get("json_path")
        != "reports/agentic/multi-format-transfer-smoke-v0.2.json"
        or reporting.get("markdown_path")
        != "reports/agentic/multi-format-transfer-smoke-v0.2.md"
        or reporting.get("candidate_outputs_public") is not False
        or reporting.get("absolute_paths_public") is not False
        or reporting.get("raw_evidence_public") is not False
    ):
        raise RunnerError("Transfer-smoke reporting boundary differs")
    _validate_artifacts(
        repo_root, plan.get("frozen_inputs", {}).get("artifacts"), "transfer smoke"
    )
    return {
        "plan": plan,
        "path": path,
        "sha256": sha256_file(path),
        "systems": {item["system_id"]: item for item in systems},
        "resource_gate": {
            "empty_state_observation_seconds": 30,
            "loaded_models_must_be_empty_before_each_system": True,
            "blocking_process_rules": rules,
        },
    }


def load_controller_qualification(repo_root: Path) -> dict[str, Any]:
    """Require the no-inference controller qualification."""
    path = resolve_repo_path(repo_root, DEFAULT_CONTROLLER_QUALIFICATION)
    qualification = load_json(path)
    evidence = qualification.get("qualification_evidence", {})
    if (
        qualification.get("qualification_id")
        != "multi-format-transfer-smoke-v0.2-controller-no-inference"
        or qualification.get("status") != "qualified_for_frozen_smoke"
        or evidence.get("live_ollama_requests") != 0
        or evidence.get("live_model_inference") is not False
        or evidence.get("repository_execution_authorization_present") is not False
    ):
        raise RunnerError("Invalid transfer-smoke controller qualification")
    _validate_artifacts(
        repo_root, qualification.get("artifacts"), "transfer-smoke controller"
    )
    return {"qualification": qualification, "path": path, "sha256": sha256_file(path)}


def load_execution_authorization(
    repo_root: Path, authorization_path: Path, loaded_plan: dict[str, Any]
) -> dict[str, Any]:
    """Validate an authorization created only after the plan was frozen."""
    path = resolve_repo_path(repo_root, authorization_path)
    authorization = load_json(path)
    if (
        authorization.get("schema_version") != "1.0.0"
        or authorization.get("authorization_id")
        != "multi-format-transfer-smoke-v0.2-execution-authorization"
        or authorization.get("status") != "authorized_pending_resource_gate"
        or authorization.get("plan_id") != loaded_plan["plan"]["plan_id"]
        or authorization.get("plan_sha256") != loaded_plan["sha256"]
        or authorization.get("live_execution_authorized") is not True
        or authorization.get("unit_count") != 2
        or authorization.get("attempts_per_system") != 1
        or authorization.get("automatic_retries") != 0
        or authorization.get("authorized_model") != MODEL
        or authorization.get("authorized_systems") != list(SYSTEM_IDS)
        or authorization.get("resource_gate_still_required") is not True
    ):
        raise RunnerError("Invalid transfer-smoke execution authorization")
    return {"authorization": authorization, "path": path, "sha256": sha256_file(path)}


def _current_unit(record: dict[str, Any]) -> dict[str, Any] | None:
    return next(
        (item for item in record["units"] if item["status"] not in TERMINAL_STATUSES),
        None,
    )


def _recount(record: dict[str, Any]) -> None:
    terminal = [item for item in record["units"] if item["status"] in TERMINAL_STATUSES]
    record["terminal_unit_count"] = len(terminal)
    record["complete_unit_count"] = sum(item["status"] == "complete" for item in terminal)
    record["failed_unit_count"] = sum(item["status"] == "failed" for item in terminal)
    record["semantic_verified_success_count"] = sum(
        bool(item.get("outcome", {}).get("semantic_verified_success"))
        for item in terminal
    )
    record["strict_transport_compliance_count"] = sum(
        bool(item.get("outcome", {}).get("strict_transport_compliance"))
        for item in terminal
    )
    record["model_requests_observed"] = sum(
        int((item.get("trajectory") or {}).get("model_requests", 0) or 0)
        for item in record["units"]
    )


def _summary(record: dict[str, Any], study_dir: Path) -> dict[str, Any]:
    waiting = _current_unit(record)
    return {
        "study_id": record["study_id"],
        "study_dir": str(study_dir),
        "status": record["status"],
        "unit_count": record["unit_count"],
        "terminal_unit_count": record["terminal_unit_count"],
        "model_requests_observed": record["model_requests_observed"],
        "waiting": None
        if waiting is None
        else {
            "position": waiting["position"],
            "system_id": waiting["system_id"],
            "unit_status": waiting["status"],
            "run_dir": waiting.get("run_dir"),
        },
    }


def _raw_run(repo_root: Path, unit: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    value = unit.get("run_dir")
    if not isinstance(value, str):
        raise RunnerError("Transfer-smoke unit has no run directory")
    run_dir = resolve_repo_path(repo_root, Path(value))
    return run_dir, load_json(run_dir / "run.json")


def _sync_unit(repo_root: Path, unit: dict[str, Any]) -> None:
    run_dir, run = _raw_run(repo_root, unit)
    state = run.get("state")
    if unit["system_id"] == SYSTEM_IDS[0]:
        mapping = {
            "prepared_not_executed": "sandbox_ready"
            if run.get("execution_boundary", {}).get("sandbox_acceptance_passed")
            and run.get("execution_boundary", {}).get(
                "explicit_extension_acceptance_passed"
            )
            else "sandbox_pending",
            "execution_complete_verification_pending": "verification_pending",
            "complete": "complete_needs_cleanup",
        }
    else:
        mapping = {
            "awaiting_model": "awaiting_model",
            "awaiting_action": "awaiting_action",
            "trajectory_complete_verification_pending": "verification_pending",
            "complete": "complete_needs_cleanup",
        }
    if state not in mapping:
        raise RunnerError(
            f"Unsupported raw state for {unit['system_id']}: {state!r} in {run_dir}"
        )
    unit["status"] = mapping[state]
    unit["trajectory"] = run.get("trajectory")
    if state == "complete":
        unit["outcome"] = run.get("outcome")
        unit["verification"] = {
            "essential_pass_count": run.get("verification", {}).get(
                "essential_pass_count"
            ),
            "essential_check_count": run.get("verification", {}).get(
                "essential_check_count"
            ),
            "failed_check_ids": [
                item.get("check_id")
                for item in run.get("verification", {}).get("checks", [])
                if item.get("passed") is False
            ],
        }


def _load_study(
    repo_root: Path, study_dir: Path
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    resolved = resolve_repo_path(repo_root, study_dir)
    record = load_json(resolved / "study.json")
    if record.get("evidence_class") != "excluded_development_smoke_pair":
        raise RunnerError("Record is not a Phase 96 transfer smoke")
    loaded = load_transfer_smoke_plan(repo_root, Path(record["plan"]["path"]))
    if loaded["sha256"] != record["plan"]["sha256"]:
        raise RunnerError("Transfer-smoke plan changed after start")
    controller = load_controller_qualification(repo_root)
    if (
        record["controller"]["implementation_sha256"] != sha256_file(Path(__file__))
        or record["controller"]["qualification_sha256"] != controller["sha256"]
    ):
        raise RunnerError("Transfer-smoke controller changed after start")
    return resolved, record, loaded


def start_transfer_smoke(repo_root: Path, config: TransferSmokeConfig) -> dict[str, Any]:
    """Prepare both raw system runs and Pi's offline readiness acceptance."""
    loaded = load_transfer_smoke_plan(repo_root, config.plan_path)
    controller = load_controller_qualification(repo_root)
    plan = loaded["plan"]
    if config.host.rstrip("/") != plan["runtime"]["host"].rstrip("/"):
        raise RunnerError("Configured Ollama host differs from the frozen smoke")
    results = resolve_repo_path(repo_root, config.results_dir)
    agent_results = resolve_repo_path(repo_root, config.agent_results_dir)
    results.mkdir(parents=True, exist_ok=True)
    agent_results.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    study_id = f"multi-format-transfer-smoke-{timestamp}-{secrets.token_hex(4)}"
    study_dir = results / study_id
    study_dir.mkdir()
    record = {
        "schema_version": "1.0.0",
        "study_id": study_id,
        "status": "preparing_offline",
        "started_at": utc_now(),
        "completed_at": None,
        "track": "B",
        "evidence_class": plan["evidence_class"],
        "git_commit": git_commit(repo_root),
        "host": config.host.rstrip("/"),
        "ollama_version": plan["runtime"]["expected_version"],
        "plan": {
            "plan_id": plan["plan_id"],
            "path": _relative(repo_root, loaded["path"]),
            "sha256": loaded["sha256"],
        },
        "authorization": None,
        "controller": {
            "implementation_path": _relative(repo_root, Path(__file__)),
            "implementation_sha256": sha256_file(Path(__file__)),
            "qualification_path": _relative(repo_root, controller["path"]),
            "qualification_sha256": controller["sha256"],
        },
        "agent_results_dir": _relative(repo_root, agent_results),
        "unit_count": 2,
        "terminal_unit_count": 0,
        "complete_unit_count": 0,
        "failed_unit_count": 0,
        "semantic_verified_success_count": 0,
        "strict_transport_compliance_count": 0,
        "model_requests_observed": 0,
        "pause": None,
        "units": [
            {
                **item,
                "deployment_id": plan["deployment"]["deployment_id"],
                "digest": plan["deployment"]["digest"],
                "status": "pending_offline_preparation",
                "run_id": None,
                "run_dir": None,
                "offline_seatbelt_acceptance": None,
                "live_seatbelt_acceptance": None,
                "resource_gate": None,
                "outcome": None,
                "trajectory": None,
                "verification": None,
                "postflight_running_models": None,
            }
            for item in plan["execution_order"]
        ],
    }
    record_path = study_dir / "study.json"
    write_json(record_path, record)
    for unit in record["units"]:
        try:
            if unit["system_id"] == SYSTEM_IDS[0]:
                started = prepare_pi(
                    repo_root,
                    PiMultiFormatPrepareConfig(
                        model=MODEL,
                        results_dir=Path(record["agent_results_dir"]),
                        host=record["host"],
                    ),
                )
                unit["run_id"] = started["run_id"]
                unit["run_dir"] = _relative(repo_root, Path(started["run_dir"]))
                acceptance = check_pi_sandbox(Path(started["run_dir"]))
                unit["offline_seatbelt_acceptance"] = {
                    "passed": acceptance["passed"],
                    "validated_at": acceptance["validated_at"],
                    "profile_sha256": acceptance["profile_sha256"],
                    "checks_passed": sum(
                        bool(item["passed"]) for item in acceptance["checks"]
                    ),
                    "checks_total": len(acceptance["checks"]),
                    "freshness_for_live_execution": False,
                }
            else:
                started = prepare_mini(
                    repo_root,
                    MiniMultiFormatStartConfig(
                        model=MODEL,
                        results_dir=Path(record["agent_results_dir"]),
                        host=record["host"],
                    ),
                )
                unit["run_id"] = started["run_id"]
                unit["run_dir"] = _relative(repo_root, Path(started["run_dir"]))
            unit["prepared_at"] = utc_now()
            _sync_unit(repo_root, unit)
            write_json(record_path, record)
        except Exception as exc:
            unit["status"] = "offline_preparation_failed"
            unit["preparation_error"] = {
                "type": exc.__class__.__name__,
                "message": str(exc),
                "model_requests_observed": 0,
            }
            record["status"] = "offline_preparation_failed"
            write_json(record_path, record)
            raise
    record["status"] = "prepared_pending_post_freeze_authorization"
    write_json(record_path, record)
    return _summary(record, study_dir)


def advance_transfer_smoke(repo_root: Path, study_dir: Path) -> dict[str, Any]:
    """Advance only local action processing and hidden verification."""
    resolved, record, _loaded = _load_study(repo_root, study_dir)
    record_path = resolved / "study.json"
    while True:
        unit = _current_unit(record)
        if unit is None:
            _recount(record)
            record["status"] = (
                "complete" if record["failed_unit_count"] == 0 else "complete_with_failures"
            )
            record["completed_at"] = record.get("completed_at") or utc_now()
            write_json(record_path, record)
            return _summary(record, resolved)
        _sync_unit(repo_root, unit)
        if unit["status"] == "awaiting_action":
            step_mini(repo_root, _raw_run(repo_root, unit)[0])
            _sync_unit(repo_root, unit)
            write_json(record_path, record)
            continue
        if unit["status"] == "verification_pending":
            run_dir = _raw_run(repo_root, unit)[0]
            if unit["system_id"] == SYSTEM_IDS[0]:
                finalize_pi(repo_root, run_dir)
            else:
                finalize_mini(repo_root, run_dir)
            _sync_unit(repo_root, unit)
            _recount(record)
            write_json(record_path, record)
            continue
        record["status"] = (
            "waiting_for_ollama_cleanup"
            if unit["status"] == "complete_needs_cleanup"
            else "prepared_pending_post_freeze_authorization"
            if record.get("authorization") is None
            else "waiting_for_live_boundary"
        )
        write_json(record_path, record)
        return _summary(record, resolved)


def _validate_deployment(client: OllamaClient, unit: dict[str, Any], version: str) -> None:
    observed = client.version().get("version")
    if observed != version:
        raise RunnerError(f"Transfer smoke requires Ollama {version}, found {observed}")
    model = find_model(client.list_models(), unit["model"])
    if model.get("digest") != unit["digest"]:
        raise RunnerError(f"Ollama digest drift for {unit['model']}")


def run_transfer_smoke_live(
    repo_root: Path,
    study_dir: Path,
    authorization_path: Path = DEFAULT_AUTHORIZATION,
    *,
    client: OllamaClient | None = None,
    process_reader: Callable[[], list[dict[str, Any]]] = _process_snapshot,
    sleep: Callable[[float], None] = time.sleep,
    exclusive_window_confirmed: bool = False,
) -> dict[str, Any]:
    """Execute exactly one authorized model boundary."""
    resolved, record, loaded = _load_study(repo_root, study_dir)
    authorization = load_execution_authorization(repo_root, authorization_path, loaded)
    if not exclusive_window_confirmed:
        raise RunnerError("Transfer-smoke live execution requires an exclusive window")
    unit = _current_unit(record)
    if unit is None:
        raise RunnerError("Transfer smoke has no pending live boundary")
    _sync_unit(repo_root, unit)
    if unit["status"] not in {"sandbox_ready", "awaiting_model"}:
        raise RunnerError(f"Transfer-smoke unit is not ready: {unit['status']}")
    ollama = client or OllamaClient(record["host"])
    run_dir, raw = _raw_run(repo_root, unit)
    first_request = (
        unit["system_id"] == SYSTEM_IDS[0]
        or raw.get("trajectory", {}).get("model_requests") == 0
    )
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
            _validate_deployment(ollama, unit, record["ollama_version"])
            blockers = _blocking_processes(
                loaded["resource_gate"]["blocking_process_rules"], process_reader()
            )
            if blockers:
                raise ResourceGatePause(
                    "Concurrent workload appeared during the Mini trajectory.",
                    {
                        "passed": False,
                        "stage": "continuation_process_snapshot",
                        "blocking_processes": blockers,
                    },
                )
            unexpected = sorted(
                name
                for name in running_model_names(ollama.list_running_models())
                if name != unit["model"]
            )
            if unexpected:
                raise ResourceGatePause(
                    "Unrelated Ollama activity appeared during the Mini trajectory.",
                    {
                        "passed": False,
                        "stage": "continuation_ollama_snapshot",
                        "running_models": unexpected,
                    },
                )
    except ResourceGatePause as exc:
        record["status"] = "paused_resource_gate"
        record["pause"] = getattr(exc, "evidence", {"reason": str(exc)})
        write_json(resolved / "study.json", record)
        raise
    record["authorization"] = {
        "authorization_id": authorization["authorization"]["authorization_id"],
        "path": _relative(repo_root, authorization["path"]),
        "sha256": authorization["sha256"],
    }
    record["status"] = "running_live_boundary"
    record["pause"] = None
    write_json(resolved / "study.json", record)
    if unit["system_id"] == SYSTEM_IDS[0]:
        acceptance = check_pi_sandbox(run_dir)
        unit["live_seatbelt_acceptance"] = {
            "passed": acceptance["passed"],
            "validated_at": acceptance["validated_at"],
            "profile_sha256": acceptance["profile_sha256"],
            "checks_passed": sum(bool(item["passed"]) for item in acceptance["checks"]),
            "checks_total": len(acceptance["checks"]),
        }
        write_json(resolved / "study.json", record)
        run_pi(repo_root, run_dir)
    else:
        call_mini(repo_root, run_dir)
    _sync_unit(repo_root, unit)
    _recount(record)
    record["status"] = "waiting_for_local_step"
    write_json(resolved / "study.json", record)
    return _summary(record, resolved)


def cleanup_transfer_smoke_unit(
    repo_root: Path,
    study_dir: Path,
    authorization_path: Path = DEFAULT_AUTHORIZATION,
    *,
    client: OllamaClient | None = None,
    exclusive_window_confirmed: bool = False,
) -> dict[str, Any]:
    """Unload one terminal system and advance without retrying it."""
    resolved, record, loaded = _load_study(repo_root, study_dir)
    authorization = load_execution_authorization(repo_root, authorization_path, loaded)
    if not exclusive_window_confirmed:
        raise RunnerError("Transfer-smoke cleanup requires an exclusive window")
    if record.get("authorization", {}).get("sha256") != authorization["sha256"]:
        raise RunnerError("Transfer-smoke authorization differs from live execution")
    unit = _current_unit(record)
    if unit is None or unit["status"] != "complete_needs_cleanup":
        raise RunnerError("No terminal transfer-smoke unit is awaiting cleanup")
    ollama = client or OllamaClient(record["host"])
    ollama.unload_model(unit["model"])
    running = running_model_names(ollama.list_running_models())
    unit["postflight_running_models"] = running
    if running:
        raise ResourceGatePause(
            "Ollama was not empty after transfer-smoke cleanup.",
            {"stage": "postflight_cleanup", "running_models": running},
        )
    unit["status"] = "complete"
    unit["completed_at"] = utc_now()
    _recount(record)
    record["status"] = "waiting_for_local_step"
    write_json(resolved / "study.json", record)
    return advance_transfer_smoke(repo_root, resolved)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser("start")
    start.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    start.add_argument(
        "--results-dir", type=Path, default=Path("results/agentic-transfer-smokes")
    )
    start.add_argument(
        "--agent-results-dir", type=Path, default=Path("results/agentic-runs")
    )
    start.add_argument("--host", default="http://127.0.0.1:11434")
    advance = subparsers.add_parser("advance")
    advance.add_argument("--study-dir", type=Path, required=True)
    for name in ("live", "cleanup"):
        child = subparsers.add_parser(name)
        child.add_argument("--study-dir", type=Path, required=True)
        child.add_argument("--authorization", type=Path, default=DEFAULT_AUTHORIZATION)
        child.add_argument("--exclusive-window-confirmed", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    try:
        if args.command == "start":
            result = start_transfer_smoke(
                repo_root,
                TransferSmokeConfig(
                    plan_path=args.plan,
                    results_dir=args.results_dir,
                    agent_results_dir=args.agent_results_dir,
                    host=args.host,
                ),
            )
        elif args.command == "advance":
            result = advance_transfer_smoke(repo_root, args.study_dir)
        elif args.command == "live":
            result = run_transfer_smoke_live(
                repo_root,
                args.study_dir,
                args.authorization,
                exclusive_window_confirmed=args.exclusive_window_confirmed,
            )
        else:
            result = cleanup_transfer_smoke_unit(
                repo_root,
                args.study_dir,
                args.authorization,
                exclusive_window_confirmed=args.exclusive_window_confirmed,
            )
    except (OSError, RunnerError, OllamaError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
