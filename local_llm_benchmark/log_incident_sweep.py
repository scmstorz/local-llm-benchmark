"""Durable orchestration for measured Mini/Pi log-incident capability sweeps."""

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

from .log_incident_mini_v02 import (
    MiniLogV02StartConfig,
    call_mini_log_v02_model,
    finalize_mini_log_v02_run,
    load_mini_log_v02_harness,
    start_mini_log_v02_run,
    step_mini_log_v02_action,
)
from .log_incident_pi_v02 import (
    PiLogV02PrepareConfig,
    execute_pi_log_v02_run,
    finalize_pi_log_v02_run,
    load_pi_log_v02_harness,
    prepare_pi_log_v02_run,
)
from .log_incident_smokes import ResourceGatePause, run_resource_gate
from .macos_sandbox_log import validate_pi_log_seatbelt
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


DEFAULT_SWEEP_PLAN = Path(
    "tasks/agentic/track-b/log-incident-capability-sweep-v0.2.json"
)
HARNESS_IDS = ("mini-log-v0.2", "pi-log-v0.2")
TERMINAL_STATUSES = {"complete", "failed"}


@dataclass(frozen=True)
class LogIncidentSweepConfig:
    """Inputs for a new measured log-incident sweep."""

    plan_path: Path = DEFAULT_SWEEP_PLAN
    results_dir: Path = Path("results/agentic-sweeps")
    agent_results_dir: Path = Path("results/agentic-runs")
    host: str = "http://127.0.0.1:11434"


def _relative(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise RunnerError(f"Log-incident sweep artifact escapes repository: {path}") from exc


def _validate_artifacts(repo_root: Path, artifacts: Any) -> None:
    if not isinstance(artifacts, list) or not artifacts:
        raise RunnerError("Log-incident sweep must freeze input artifacts")
    seen: set[str] = set()
    for position, item in enumerate(artifacts, start=1):
        if not isinstance(item, dict):
            raise RunnerError(f"Invalid frozen artifact at position {position}")
        relative = item.get("path")
        digest = item.get("sha256")
        if (
            not isinstance(relative, str)
            or not relative
            or relative in seen
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise RunnerError(f"Incomplete or duplicate frozen artifact: {relative!r}")
        path = resolve_repo_path(repo_root, Path(relative))
        if not path.is_file() or path.is_symlink() or sha256_file(path) != digest:
            raise RunnerError(f"Log-incident sweep artifact drift: {relative}")
        seen.add(relative)


def _load_harnesses(repo_root: Path, plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    declarations = plan.get("harnesses")
    if not isinstance(declarations, list) or [
        item.get("harness_id") for item in declarations if isinstance(item, dict)
    ] != list(HARNESS_IDS):
        raise RunnerError("Sweep harness order must be Mini v0.2 then Pi v0.2")
    loaders = {
        "mini-log-v0.2": load_mini_log_v02_harness,
        "pi-log-v0.2": load_pi_log_v02_harness,
    }
    loaded: dict[str, dict[str, Any]] = {}
    for declaration in declarations:
        harness_id = declaration["harness_id"]
        path_value = declaration.get("harness_path")
        qualification_value = declaration.get("qualification_path")
        if not isinstance(path_value, str) or not isinstance(qualification_value, str):
            raise RunnerError(f"Incomplete harness declaration for {harness_id}")
        harness = loaders[harness_id](repo_root, Path(path_value))
        if harness["harness"]["harness_id"] != harness_id:
            raise RunnerError(f"Harness identity mismatch for {harness_id}")
        qualification_path = resolve_repo_path(repo_root, Path(qualification_value))
        qualification = load_json(qualification_path)
        if (
            qualification.get("harness_id") != harness_id
            or qualification.get("status") != "qualified_for_excluded_live_smoke"
            or qualification.get("case_count") != 3
            or sha256_file(qualification_path) != declaration.get("qualification_sha256")
        ):
            raise RunnerError(f"Invalid qualification gate for {harness_id}")
        loaded[harness_id] = {
            **harness,
            "qualification_path": qualification_path,
            "qualification": qualification,
        }
    return loaded


def load_log_incident_sweep_plan(repo_root: Path, plan_path: Path) -> dict[str, Any]:
    """Load and validate one frozen complete-system capability sweep."""
    resolved = resolve_repo_path(repo_root, plan_path)
    plan = load_json(resolved)
    if (
        plan.get("schema_version") != "1.0.0"
        or plan.get("status") != "frozen_before_execution"
        or plan.get("track") != "B"
        or plan.get("protocol_id") != "agentic-log-incident-v0.2"
        or plan.get("evidence_class") != "measured_capability_sweep"
    ):
        raise RunnerError("Unexpected log-incident sweep identity")
    runtime = plan.get("runtime")
    if (
        not isinstance(runtime, dict)
        or runtime.get("name") != "ollama"
        or not isinstance(runtime.get("version"), str)
        or not runtime["version"]
        or not isinstance(runtime.get("host"), str)
    ):
        raise RunnerError("Log-incident sweep runtime is incomplete")

    qualification_gate = plan.get("qualification_gate")
    if not isinstance(qualification_gate, dict):
        raise RunnerError("Log-incident sweep lacks a qualification gate")
    report_path = resolve_repo_path(
        repo_root, Path(qualification_gate.get("smoke_report_path", ""))
    )
    smoke_report = load_json(report_path)
    if (
        sha256_file(report_path) != qualification_gate.get("smoke_report_sha256")
        or smoke_report.get("interpretation", {}).get("machinery_gate")
        != "passed_with_documented_protocol_deviation"
        or qualification_gate.get("excluded_smoke_reused_as_measured") is not False
    ):
        raise RunnerError("Excluded log-incident smoke gate is not satisfied")

    harnesses = _load_harnesses(repo_root, plan)
    subsets = []
    for harness_id in HARNESS_IDS:
        subsets.append(
            {
                item["case_id"]: (item["case_path"], item["case_version"])
                for item in harnesses[harness_id]["protocol"]["task_subset"]
            }
        )
    if subsets[0] != subsets[1] or len(subsets[0]) != 3:
        raise RunnerError("Mini and Pi must expose the same three-case protocol")

    deployments = plan.get("deployments")
    if not isinstance(deployments, list) or not deployments:
        raise RunnerError("Log-incident sweep must define deployments")
    model_by_name: dict[str, dict[str, Any]] = {}
    for deployment in deployments:
        if not isinstance(deployment, dict):
            raise RunnerError("Deployment entries must be objects")
        name = deployment.get("name")
        digest = deployment.get("digest")
        deployment_id = deployment.get("deployment_id")
        if (
            not isinstance(name, str)
            or not name
            or name in model_by_name
            or not isinstance(deployment_id, str)
            or not deployment_id
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            raise RunnerError(f"Invalid or duplicate deployment: {name!r}")
        model_by_name[name] = deployment

    cases = plan.get("cases")
    if not isinstance(cases, list) or len(cases) != 3:
        raise RunnerError("Log-incident sweep requires exactly three cases")
    case_by_id: dict[str, dict[str, Any]] = {}
    for case in cases:
        if not isinstance(case, dict):
            raise RunnerError("Case entries must be objects")
        case_id = case.get("case_id")
        case_path = case.get("case_path")
        case_version = case.get("case_version")
        if (
            not isinstance(case_id, str)
            or case_id in case_by_id
            or subsets[0].get(case_id) != (case_path, case_version)
        ):
            raise RunnerError(f"Invalid or duplicate sweep case: {case_id!r}")
        case_by_id[case_id] = case

    expected = {
        (harness_id, model, case_id)
        for harness_id in HARNESS_IDS
        for model in model_by_name
        for case_id in case_by_id
    }
    observed: set[tuple[str, str, str]] = set()
    order = plan.get("execution_order")
    if not isinstance(order, list):
        raise RunnerError("Log-incident sweep must define execution_order")
    for position, unit in enumerate(order, start=1):
        if not isinstance(unit, dict) or unit.get("position") != position:
            raise RunnerError("Log-incident execution positions must be contiguous")
        key = (unit.get("harness_id"), unit.get("model"), unit.get("case_id"))
        if key not in expected or key in observed:
            raise RunnerError(f"Invalid or duplicate sweep unit: {key}")
        observed.add(key)
    if observed != expected:
        raise RunnerError("Execution order is not the full harness/model/case product")

    comparison = plan.get("comparison_rules", {})
    if (
        comparison.get("runs_per_configuration") != 1
        or comparison.get("automatic_retries") != 0
        or comparison.get("performance_distribution_claims") is not False
        or comparison.get("one_factor_causal_harness_claim_allowed") is not False
    ):
        raise RunnerError("Log-incident sweep comparison rules are invalid")
    gate = plan.get("resource_gate", {})
    if (
        not isinstance(gate.get("empty_state_observation_seconds"), int)
        or gate["empty_state_observation_seconds"] < 0
        or gate.get("loaded_models_must_be_empty_before_each_unit") is not True
    ):
        raise RunnerError("Log-incident sweep resource gate is incomplete")
    rules = gate.get("blocking_process_rules")
    if not isinstance(rules, list) or not rules:
        raise RunnerError("Log-incident sweep needs blocking-process rules")
    for rule in rules:
        if not isinstance(rule.get("rule_id"), str) or not isinstance(
            rule.get("pattern"), str
        ):
            raise RunnerError("Invalid blocking-process rule")
        try:
            re.compile(rule["pattern"])
        except re.error as exc:
            raise RunnerError(f"Invalid process rule {rule['rule_id']}") from exc
    _validate_artifacts(repo_root, plan.get("frozen_inputs", {}).get("artifacts"))
    return {
        "plan": plan,
        "path": resolved,
        "sha256": sha256_file(resolved),
        "harnesses": harnesses,
        "models": model_by_name,
        "cases": case_by_id,
    }


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
    result: list[dict[str, Any]] = []
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
    blocked: list[dict[str, Any]] = []
    own_pid = str(os.getpid())
    for process in processes:
        if str(process.get("pid")) == own_pid:
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
                        "command_sha256": hashlib.sha256(
                            command.encode("utf-8")
                        ).hexdigest(),
                    }
                )
                break
    return blocked


def _summary(record: dict[str, Any], sweep_dir: Path) -> dict[str, Any]:
    waiting = next(
        (unit for unit in record["units"] if unit["status"] not in TERMINAL_STATUSES),
        None,
    )
    return {
        "sweep_id": record["sweep_id"],
        "sweep_dir": str(sweep_dir),
        "status": record["status"],
        "unit_count": record["unit_count"],
        "complete_unit_count": record["complete_unit_count"],
        "failed_unit_count": record["failed_unit_count"],
        "verified_success_count": record["verified_success_count"],
        "waiting": None
        if waiting is None
        else {
            "position": waiting["position"],
            "harness_id": waiting["harness_id"],
            "model": waiting["model"],
            "case_id": waiting["case_id"],
            "unit_status": waiting["status"],
            "run_dir": waiting.get("run_dir"),
        },
    }


def _recount(record: dict[str, Any]) -> None:
    complete = [unit for unit in record["units"] if unit["status"] == "complete"]
    record["complete_unit_count"] = len(complete)
    record["failed_unit_count"] = sum(
        unit["status"] == "failed" for unit in record["units"]
    )
    record["verified_success_count"] = sum(
        bool(unit.get("outcome", {}).get("verified_success")) for unit in complete
    )


def _load_sweep(
    repo_root: Path, sweep_dir: Path
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    resolved = resolve_repo_path(repo_root, sweep_dir)
    record = load_json(resolved / "sweep.json")
    if (
        record.get("track") != "B"
        or record.get("protocol_id") != "agentic-log-incident-v0.2"
        or record.get("evidence_class") != "measured_capability_sweep"
    ):
        raise RunnerError("Record is not a measured log-incident sweep")
    loaded = load_log_incident_sweep_plan(repo_root, Path(record["plan"]["path"]))
    if loaded["sha256"] != record["plan"]["sha256"]:
        raise RunnerError("Log-incident sweep plan changed after creation")
    return resolved, record, loaded


def _current_unit(record: dict[str, Any]) -> dict[str, Any] | None:
    return next(
        (unit for unit in record["units"] if unit["status"] not in TERMINAL_STATUSES),
        None,
    )


def _run_record(repo_root: Path, unit: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    if not unit.get("run_dir"):
        raise RunnerError("Sweep unit has no run directory")
    run_dir = resolve_repo_path(repo_root, Path(unit["run_dir"]))
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
        "verifier_success": False,
        "verified_success": False,
        "failure_category": "infrastructure_or_control_failure",
        "failure_type": "interrupted_live_process",
    }


def _sync_unit(repo_root: Path, unit: dict[str, Any], *, after_live: bool = False) -> None:
    if not unit.get("run_dir"):
        return
    _run_dir, run = _run_record(repo_root, unit)
    state = run.get("state")
    if unit["harness_id"] == "mini-log-v0.2":
        mapping = {
            "awaiting_model": "awaiting_model",
            "awaiting_action": "awaiting_action",
            "trajectory_complete_verification_pending": "verification_pending",
            "complete": "complete_needs_cleanup",
        }
        if state == "model_call_running":
            if after_live:
                raise RunnerError("Mini model call returned while raw state remained running")
            _mark_interrupted(unit, state)
            return
    else:
        mapping = {
            "prepared_not_executed": (
                "sandbox_accepted"
                if run.get("execution_boundary", {}).get("sandbox_acceptance_passed")
                else "sandbox_pending"
            ),
            "execution_complete_verification_pending": "verification_pending",
            "complete": "complete_needs_cleanup",
        }
        if state == "running":
            if after_live:
                raise RunnerError("Pi execution returned while raw state remained running")
            _mark_interrupted(unit, state)
            return
    if state not in mapping:
        raise RunnerError(f"Unsupported raw run state for {unit['harness_id']}: {state!r}")
    unit["status"] = mapping[state]
    if state == "complete":
        unit["outcome"] = run.get("outcome")
        unit["trajectory"] = run.get("trajectory")


def start_log_incident_sweep(
    repo_root: Path, config: LogIncidentSweepConfig
) -> dict[str, Any]:
    """Create the measured sweep record without contacting Ollama."""
    loaded = load_log_incident_sweep_plan(repo_root, config.plan_path)
    plan = loaded["plan"]
    if config.host.rstrip("/") != plan["runtime"]["host"].rstrip("/"):
        raise RunnerError("Configured Ollama host differs from the frozen plan")
    results = resolve_repo_path(repo_root, config.results_dir)
    agent_results = resolve_repo_path(repo_root, config.agent_results_dir)
    results.mkdir(parents=True, exist_ok=True)
    agent_results.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    sweep_id = f"log-incident-sweep-{timestamp}-{secrets.token_hex(4)}"
    sweep_dir = results / sweep_id
    sweep_dir.mkdir(parents=False, exist_ok=False)
    record = {
        "schema_version": "1.0.0",
        "sweep_id": sweep_id,
        "status": "ready_for_local_preparation",
        "started_at": utc_now(),
        "completed_at": None,
        "track": "B",
        "protocol_id": plan["protocol_id"],
        "evidence_class": plan["evidence_class"],
        "git_commit": git_commit(repo_root),
        "host": config.host.rstrip("/"),
        "ollama_version": plan["runtime"]["version"],
        "plan": {
            "plan_id": plan["plan_id"],
            "path": _relative(repo_root, loaded["path"]),
            "sha256": loaded["sha256"],
        },
        "agent_results_dir": _relative(repo_root, agent_results),
        "unit_count": len(plan["execution_order"]),
        "complete_unit_count": 0,
        "failed_unit_count": 0,
        "verified_success_count": 0,
        "pause": None,
        "units": [
            {
                "position": item["position"],
                "harness_id": item["harness_id"],
                "model": item["model"],
                "deployment_id": loaded["models"][item["model"]]["deployment_id"],
                "digest": loaded["models"][item["model"]]["digest"],
                "case_id": item["case_id"],
                "case_path": loaded["cases"][item["case_id"]]["case_path"],
                "status": "pending",
                "run_id": None,
                "run_dir": None,
                "resource_gate": None,
                "sandbox_acceptance": None,
                "outcome": None,
                "trajectory": None,
                "error": None,
                "postflight_running_models": None,
            }
            for item in plan["execution_order"]
        ],
    }
    write_json(sweep_dir / "sweep.json", record)
    return advance_log_incident_sweep(repo_root, sweep_dir)


def advance_log_incident_sweep(repo_root: Path, sweep_dir: Path) -> dict[str, Any]:
    """Advance preparation, tool action or verification to the next live boundary."""
    resolved, record, loaded = _load_sweep(repo_root, sweep_dir)
    sweep_path = resolved / "sweep.json"
    while True:
        unit = _current_unit(record)
        if unit is None:
            _recount(record)
            record["status"] = (
                "complete" if record["failed_unit_count"] == 0 else "complete_with_failures"
            )
            record["completed_at"] = record.get("completed_at") or utc_now()
            record["pause"] = None
            write_json(sweep_path, record)
            return _summary(record, resolved)
        if unit.get("run_dir"):
            _sync_unit(repo_root, unit)
            _recount(record)
            write_json(sweep_path, record)
        if unit["status"] == "pending":
            if unit["harness_id"] == "mini-log-v0.2":
                started = start_mini_log_v02_run(
                    repo_root,
                    MiniLogV02StartConfig(
                        model=unit["model"],
                        case_path=Path(unit["case_path"]),
                        results_dir=Path(record["agent_results_dir"]),
                        host=record["host"],
                    ),
                )
                unit["status"] = "awaiting_model"
            else:
                started = prepare_pi_log_v02_run(
                    repo_root,
                    PiLogV02PrepareConfig(
                        model=unit["model"],
                        case_path=Path(unit["case_path"]),
                        results_dir=Path(record["agent_results_dir"]),
                        host=record["host"],
                    ),
                )
                unit["status"] = "sandbox_pending"
            unit["run_id"] = started["run_id"]
            unit["run_dir"] = _relative(repo_root, Path(started["run_dir"]))
            unit["prepared_at"] = utc_now()
            record["status"] = "waiting_for_live_boundary"
            record["pause"] = None
            write_json(sweep_path, record)
            continue
        run_dir, _run = _run_record(repo_root, unit)
        if unit["status"] == "awaiting_action":
            step_mini_log_v02_action(repo_root, run_dir)
            _sync_unit(repo_root, unit)
            write_json(sweep_path, record)
            continue
        if unit["status"] == "sandbox_pending":
            acceptance = validate_pi_log_seatbelt(run_dir)
            unit["sandbox_acceptance"] = {
                "passed": acceptance["passed"],
                "validated_at": acceptance["validated_at"],
                "profile_sha256": acceptance["profile_sha256"],
            }
            unit["status"] = "sandbox_accepted"
            record["status"] = "waiting_for_live_boundary"
            write_json(sweep_path, record)
            return _summary(record, resolved)
        if unit["status"] == "verification_pending":
            if unit["harness_id"] == "mini-log-v0.2":
                finalize_mini_log_v02_run(repo_root, run_dir)
            else:
                finalize_pi_log_v02_run(repo_root, run_dir)
            _sync_unit(repo_root, unit)
            _recount(record)
            write_json(sweep_path, record)
            continue
        if unit["status"] in {
            "awaiting_model",
            "sandbox_accepted",
            "complete_needs_cleanup",
            "failed_needs_cleanup",
        }:
            record["status"] = (
                "waiting_for_cleanup"
                if unit["status"].endswith("needs_cleanup")
                else "waiting_for_live_boundary"
            )
            write_json(sweep_path, record)
            return _summary(record, resolved)
        raise RunnerError(f"Cannot advance sweep unit state {unit['status']!r}")


def _validate_unit_deployment(
    client: OllamaClient, unit: dict[str, Any], version: str
) -> None:
    observed_version = client.version().get("version")
    if observed_version != version:
        raise RunnerError(
            f"Log-incident sweep requires Ollama {version}, found {observed_version}"
        )
    observed = find_model(client.list_models(), unit["model"])
    if observed.get("digest") != unit["digest"]:
        raise RunnerError(f"Ollama digest drift for {unit['model']}")


def run_log_incident_sweep_live(
    repo_root: Path,
    sweep_dir: Path,
    *,
    client: OllamaClient | None = None,
    process_reader: Callable[[], list[dict[str, Any]]] = _process_snapshot,
    sleep: Callable[[float], None] = time.sleep,
    exclusive_window_confirmed: bool = False,
) -> dict[str, Any]:
    """Execute exactly one live Mini turn or one complete Pi trajectory."""
    if not exclusive_window_confirmed:
        raise RunnerError("Live sweep execution requires an exclusive-window confirmation")
    resolved, record, loaded = _load_sweep(repo_root, sweep_dir)
    unit = _current_unit(record)
    if unit is None:
        raise RunnerError("Log-incident sweep has no pending live boundary")
    _sync_unit(repo_root, unit)
    expected = (
        "awaiting_model"
        if unit["harness_id"] == "mini-log-v0.2"
        else "sandbox_accepted"
    )
    if unit["status"] != expected:
        write_json(resolved / "sweep.json", record)
        raise RunnerError(f"Sweep unit is not ready for live execution: {unit['status']}")
    ollama = client or OllamaClient(record["host"])
    _validate_unit_deployment(ollama, unit, record["ollama_version"])
    _run_dir, run = _run_record(repo_root, unit)
    first_request = unit["harness_id"] == "pi-log-v0.2" or (
        run.get("trajectory", {}).get("model_requests") == 0
    )
    try:
        if first_request:
            gate_plan = {
                "runtime": {
                    "name": "ollama",
                    "version": record["ollama_version"],
                },
                "deployment": {
                    "name": unit["model"],
                    "digest": unit["digest"],
                },
                "resource_gate": loaded["plan"]["resource_gate"],
            }
            unit["resource_gate"] = run_resource_gate(
                gate_plan,
                client=ollama,
                process_reader=process_reader,
                sleep=sleep,
            )
        else:
            blockers = _blocking_processes(
                loaded["plan"]["resource_gate"]["blocking_process_rules"],
                process_reader(),
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
        write_json(resolved / "sweep.json", record)
        raise
    record["status"] = "running_live_boundary"
    record["pause"] = None
    write_json(resolved / "sweep.json", record)
    run_dir, _run = _run_record(repo_root, unit)
    if unit["harness_id"] == "mini-log-v0.2":
        call_mini_log_v02_model(repo_root, run_dir)
    else:
        execute_pi_log_v02_run(repo_root, run_dir)
    _sync_unit(repo_root, unit, after_live=True)
    record["status"] = "waiting_for_local_step"
    write_json(resolved / "sweep.json", record)
    return _summary(record, resolved)


def cleanup_log_incident_sweep_unit(
    repo_root: Path,
    sweep_dir: Path,
    *,
    client: OllamaClient | None = None,
) -> dict[str, Any]:
    """Unload the terminal unit and move to the next cell without retrying it."""
    resolved, record, _loaded = _load_sweep(repo_root, sweep_dir)
    unit = _current_unit(record)
    if unit is None or unit["status"] not in {
        "complete_needs_cleanup",
        "failed_needs_cleanup",
    }:
        raise RunnerError("No terminal log-incident unit is awaiting cleanup")
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
        write_json(resolved / "sweep.json", record)
        raise ResourceGatePause(record["pause"]["reason"], record["pause"])
    unit["status"] = (
        "failed" if unit["status"] == "failed_needs_cleanup" else "complete"
    )
    unit["completed_at"] = utc_now()
    _recount(record)
    record["status"] = "ready_for_local_preparation"
    record["pause"] = None
    write_json(resolved / "sweep.json", record)
    return advance_log_incident_sweep(repo_root, resolved)


def drive_log_incident_sweep(
    repo_root: Path,
    sweep_dir: Path,
    *,
    exclusive_window_confirmed: bool,
) -> dict[str, Any]:
    """Run sequential checkpoints until completion or a resource/control pause."""
    if not exclusive_window_confirmed:
        raise RunnerError("Drive mode requires an exclusive-window confirmation")
    while True:
        summary = advance_log_incident_sweep(repo_root, sweep_dir)
        if summary["status"] in {"complete", "complete_with_failures"}:
            return summary
        status = summary["waiting"]["unit_status"]
        if status in {"awaiting_model", "sandbox_accepted"}:
            run_log_incident_sweep_live(
                repo_root,
                sweep_dir,
                exclusive_window_confirmed=True,
            )
        elif status in {"complete_needs_cleanup", "failed_needs_cleanup"}:
            cleanup_log_incident_sweep_unit(repo_root, sweep_dir)
        else:
            raise RunnerError(f"Drive mode cannot continue from {status!r}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser("start", help="Create a frozen measured sweep")
    start.add_argument("--plan", type=Path, default=DEFAULT_SWEEP_PLAN)
    start.add_argument("--host", default="http://127.0.0.1:11434")
    start.add_argument("--results-dir", type=Path, default=Path("results/agentic-sweeps"))
    start.add_argument(
        "--agent-results-dir", type=Path, default=Path("results/agentic-runs")
    )
    for name, help_text in (
        ("advance", "Perform preparation, action or verification work"),
        ("live", "Execute one live model boundary"),
        ("cleanup", "Unload one terminal unit"),
        ("drive", "Run all remaining units with durable checkpoints"),
    ):
        child = subparsers.add_parser(name, help=help_text)
        child.add_argument("--sweep-dir", type=Path, required=True)
        if name in {"live", "drive"}:
            child.add_argument("--exclusive-window-confirmed", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    try:
        if args.command == "start":
            result = start_log_incident_sweep(
                repo_root,
                LogIncidentSweepConfig(
                    plan_path=args.plan,
                    results_dir=args.results_dir,
                    agent_results_dir=args.agent_results_dir,
                    host=args.host,
                ),
            )
        elif args.command == "advance":
            result = advance_log_incident_sweep(repo_root, args.sweep_dir)
        elif args.command == "live":
            result = run_log_incident_sweep_live(
                repo_root,
                args.sweep_dir,
                exclusive_window_confirmed=args.exclusive_window_confirmed,
            )
        elif args.command == "cleanup":
            result = cleanup_log_incident_sweep_unit(repo_root, args.sweep_dir)
        else:
            result = drive_log_incident_sweep(
                repo_root,
                args.sweep_dir,
                exclusive_window_confirmed=args.exclusive_window_confirmed,
            )
    except (OSError, RunnerError, OllamaError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
