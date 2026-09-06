"""Resumable orchestration for excluded Mini/Pi log-incident smokes."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from .log_incident_mini import (
    MiniLogStartConfig,
    call_mini_log_model,
    finalize_mini_log_run,
    start_mini_log_run,
    step_mini_log_action,
)
from .log_incident_pi import (
    PiLogPrepareConfig,
    execute_pi_log_run,
    finalize_pi_log_run,
    prepare_pi_log_run,
)
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


DEFAULT_PAIR_PLAN = Path(
    "tasks/agentic/track-b/log-incident-qualification-smokes-v0.1.json"
)
TERMINAL_UNIT_STATUSES = {"complete", "interrupted_inconclusive"}


@dataclass(frozen=True)
class LogSmokeStudyConfig:
    """Local inputs for a new excluded qualification-smoke study."""

    plan_path: Path = DEFAULT_PAIR_PLAN
    results_dir: Path = Path("results/agentic-studies")
    agent_results_dir: Path = Path("results/agentic-runs")
    host: str = "http://127.0.0.1:11434"


class ResourceGatePause(RunnerError):
    """A safe pre-inference pause with sanitized supporting evidence."""

    def __init__(self, message: str, evidence: dict[str, Any]) -> None:
        super().__init__(message)
        self.evidence = evidence


def _validate_artifacts(repo_root: Path, artifacts: Any, context: str) -> None:
    if not isinstance(artifacts, list) or not artifacts:
        raise RunnerError(f"{context} must freeze at least one artifact")
    seen: set[str] = set()
    for position, artifact in enumerate(artifacts, start=1):
        if not isinstance(artifact, dict):
            raise RunnerError(f"Invalid {context} artifact at position {position}")
        relative = artifact.get("path")
        expected = artifact.get("sha256")
        if (
            not isinstance(relative, str)
            or not relative
            or relative in seen
            or not isinstance(expected, str)
            or len(expected) != 64
        ):
            raise RunnerError(f"Incomplete or duplicate {context} artifact: {relative!r}")
        path = resolve_repo_path(repo_root, Path(relative))
        if not path.is_file() or path.is_symlink() or sha256_file(path) != expected:
            raise RunnerError(f"{context} artifact drift: {relative}")
        seen.add(relative)


def load_excluded_smoke_plan(
    repo_root: Path, plan_path: Path, expected_harness: str
) -> dict[str, Any]:
    """Validate one frozen, one-attempt, excluded smoke definition."""
    resolved = resolve_repo_path(repo_root, plan_path)
    plan = load_json(resolved)
    if (
        plan.get("schema_version") != "1.0.0"
        or plan.get("status") != "frozen_before_execution"
        or plan.get("track") != "B"
        or plan.get("harness_id") != expected_harness
        or plan.get("evidence_class") != "excluded_development_smoke"
    ):
        raise RunnerError(f"Unexpected excluded smoke identity: {resolved}")
    comparison = plan.get("comparison_rules", {})
    if (
        comparison.get("attempts") != 1
        or comparison.get("automatic_retries") != 0
        or comparison.get("result_excluded_from_measured_aggregates") is not True
    ):
        raise RunnerError("A qualification smoke must remain one excluded attempt")
    deployment = plan.get("deployment", {})
    if (
        not isinstance(deployment.get("name"), str)
        or not isinstance(deployment.get("deployment_id"), str)
        or not isinstance(deployment.get("digest"), str)
        or len(deployment["digest"]) != 64
    ):
        raise RunnerError("Smoke deployment identity is incomplete")
    runtime = plan.get("runtime", {})
    if runtime.get("name") != "ollama" or not isinstance(runtime.get("version"), str):
        raise RunnerError("Smoke runtime identity is incomplete")
    case = plan.get("case", {})
    if (
        case.get("case_id") != "agentic.ops.checkout-pool-regression"
        or not isinstance(case.get("case_path"), str)
    ):
        raise RunnerError("Smoke case identity is unexpected")
    _validate_artifacts(
        repo_root, plan.get("frozen_inputs", {}).get("artifacts"), "smoke plan"
    )
    qualification_path = resolve_repo_path(
        repo_root, Path(plan["frozen_inputs"]["qualification_path"])
    )
    if sha256_file(qualification_path) != plan["frozen_inputs"].get(
        "qualification_sha256"
    ):
        raise RunnerError("Smoke qualification artifact drift")
    return {"plan": plan, "path": resolved, "sha256": sha256_file(resolved)}


def load_log_smoke_pair_plan(repo_root: Path, plan_path: Path) -> dict[str, Any]:
    """Validate the ordered pair and both independently frozen smokes."""
    resolved = resolve_repo_path(repo_root, plan_path)
    plan = load_json(resolved)
    if (
        plan.get("schema_version") != "1.0.0"
        or plan.get("status") != "frozen_before_execution"
        or plan.get("track") != "B"
        or plan.get("evidence_class") != "excluded_qualification_smoke_pair"
    ):
        raise RunnerError("Unexpected log-incident smoke-pair identity")
    order = plan.get("execution_order")
    if not isinstance(order, list) or [item.get("harness_id") for item in order] != [
        "mini-log-v0.1",
        "pi-log-v0.1",
    ]:
        raise RunnerError("Log smoke order must be Mini then Pi exactly once")
    if [item.get("position") for item in order] != [1, 2]:
        raise RunnerError("Log smoke positions must be contiguous")
    loaded_smokes: dict[str, dict[str, Any]] = {}
    for unit in order:
        harness_id = unit["harness_id"]
        loaded = load_excluded_smoke_plan(
            repo_root, Path(unit["smoke_plan_path"]), harness_id
        )
        if loaded["sha256"] != unit.get("smoke_plan_sha256"):
            raise RunnerError(f"Pair plan hash drift for {harness_id}")
        loaded_smokes[harness_id] = loaded
    identities = {
        (
            item["plan"]["deployment"]["name"],
            item["plan"]["deployment"]["digest"],
            item["plan"]["runtime"]["version"],
            item["plan"]["case"]["case_id"],
        )
        for item in loaded_smokes.values()
    }
    if len(identities) != 1:
        raise RunnerError("Paired smokes do not share deployment, runtime and case")
    comparison = plan.get("comparison_rules", {})
    if (
        comparison.get("one_attempt_per_complete_system") is not True
        or comparison.get("automatic_retries") != 0
        or comparison.get("measured_capability_evidence") is not False
        or comparison.get("one_factor_causal_harness_claim_allowed") is not False
    ):
        raise RunnerError("Pair comparison rules exceed qualification scope")
    gate = plan.get("resource_gate", {})
    if (
        not isinstance(gate.get("empty_state_observation_seconds"), int)
        or gate["empty_state_observation_seconds"] < 0
        or gate.get("loaded_models_must_be_empty_before_each_system") is not True
        or gate.get("manual_exclusive_window_confirmation_required") is not True
    ):
        raise RunnerError("Pair resource gate is incomplete")
    rules = gate.get("blocking_process_rules")
    if not isinstance(rules, list) or not rules:
        raise RunnerError("Pair resource gate needs explicit process rules")
    for rule in rules:
        if not isinstance(rule.get("rule_id"), str) or not isinstance(
            rule.get("pattern"), str
        ):
            raise RunnerError("Invalid blocking process rule")
        try:
            re.compile(rule["pattern"])
        except re.error as exc:
            raise RunnerError(f"Invalid process regex {rule['rule_id']}") from exc
    _validate_artifacts(
        repo_root, plan.get("frozen_inputs", {}).get("artifacts"), "pair plan"
    )
    return {
        "plan": plan,
        "path": resolved,
        "sha256": sha256_file(resolved),
        "smokes": loaded_smokes,
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
        raise RunnerError("Cannot inspect concurrent processes for the resource gate")
    processes: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        match = re.match(r"\s*(\d+)\s+([0-9.]+)\s+(\S+)\s+(.*)", line)
        if not match:
            continue
        processes.append(
            {
                "pid": int(match.group(1)),
                "cpu_percent": float(match.group(2)),
                "elapsed": match.group(3),
                "command": match.group(4),
            }
        )
    return processes


def _blocking_processes(
    rules: list[dict[str, str]], processes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return only sanitized match metadata; never persist full process commands."""
    blocked: list[dict[str, Any]] = []
    for process in processes:
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


def _gate_failure(
    reason: str,
    *,
    stage: str,
    blockers: list[dict[str, Any]] | None = None,
    running_models: list[str] | None = None,
) -> ResourceGatePause:
    evidence = {
        "passed": False,
        "observed_at": utc_now(),
        "stage": stage,
        "reason": reason,
        "blocking_processes": blockers or [],
        "running_models": running_models or [],
        "inference_requests_made": 0,
    }
    return ResourceGatePause(reason, evidence)


def run_resource_gate(
    plan: dict[str, Any],
    *,
    client: OllamaClient,
    process_reader: Callable[[], list[dict[str, Any]]] = _process_snapshot,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Check processes, deployment identity and an empty Ollama interval."""
    gate = plan["resource_gate"]
    rules = gate["blocking_process_rules"]
    first_processes = _blocking_processes(rules, process_reader())
    if first_processes:
        raise _gate_failure(
            "Concurrent workload blocked the benchmark before Ollama inspection.",
            stage="first_process_snapshot",
            blockers=first_processes,
        )
    runtime = plan["runtime"]
    version = client.version().get("version")
    if version != runtime["version"]:
        raise _gate_failure(
            f"Ollama version drift: expected {runtime['version']}, found {version}",
            stage="runtime_identity",
        )
    deployment = plan["deployment"]
    observed = find_model(client.list_models(), deployment["name"])
    if observed.get("digest") != deployment["digest"]:
        raise _gate_failure(
            f"Ollama digest drift for {deployment['name']}",
            stage="deployment_identity",
        )
    first_running = running_model_names(client.list_running_models())
    if first_running:
        raise _gate_failure(
            "Ollama already has a loaded model.",
            stage="first_ollama_snapshot",
            running_models=first_running,
        )
    observed_at = utc_now()
    seconds = gate["empty_state_observation_seconds"]
    if seconds:
        sleep(seconds)
    second_processes = _blocking_processes(rules, process_reader())
    if second_processes:
        raise _gate_failure(
            "Concurrent workload appeared during the empty-state observation.",
            stage="second_process_snapshot",
            blockers=second_processes,
        )
    second_running = running_model_names(client.list_running_models())
    if second_running:
        raise _gate_failure(
            "Ollama activity appeared during the empty-state observation.",
            stage="second_ollama_snapshot",
            running_models=second_running,
        )
    return {
        "passed": True,
        "observed_at": observed_at,
        "completed_at": utc_now(),
        "observation_seconds": seconds,
        "process_snapshots": 2,
        "blocking_processes": [],
        "first_running_models": [],
        "second_running_models": [],
        "ollama_version": version,
        "model": deployment["name"],
        "digest": deployment["digest"],
        "inference_requests_made": 0,
    }


def _relative(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise RunnerError(f"Smoke artifact escapes repository: {path}") from exc


def _summary(record: dict[str, Any], study_dir: Path) -> dict[str, Any]:
    current = next(
        (unit for unit in record["units"] if unit["status"] not in TERMINAL_UNIT_STATUSES),
        None,
    )
    return {
        "study_id": record["study_id"],
        "study_dir": str(study_dir),
        "status": record["status"],
        "complete_unit_count": sum(
            item["status"] == "complete" for item in record["units"]
        ),
        "inconclusive_unit_count": sum(
            item["status"] == "interrupted_inconclusive" for item in record["units"]
        ),
        "waiting": None
        if current is None
        else {
            "position": current["position"],
            "harness_id": current["harness_id"],
            "unit_status": current["status"],
            "run_dir": current.get("run_dir"),
        },
    }


def start_log_smoke_study(repo_root: Path, config: LogSmokeStudyConfig) -> dict[str, Any]:
    """Create the durable pair record without inspecting or contacting Ollama."""
    loaded = load_log_smoke_pair_plan(repo_root, config.plan_path)
    plan = loaded["plan"]
    if config.host.rstrip("/") != plan["runtime"]["host"].rstrip("/"):
        raise RunnerError("Configured Ollama host differs from the frozen pair plan")
    results = resolve_repo_path(repo_root, config.results_dir)
    agent_results = resolve_repo_path(repo_root, config.agent_results_dir)
    results.mkdir(parents=True, exist_ok=True)
    agent_results.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    study_id = f"log-smoke-pair-{timestamp}-{secrets.token_hex(4)}"
    study_dir = results / study_id
    study_dir.mkdir(parents=False, exist_ok=False)
    record = {
        "schema_version": "1.0.0",
        "study_id": study_id,
        "status": "ready_for_local_preparation",
        "started_at": utc_now(),
        "completed_at": None,
        "track": "B",
        "evidence_class": plan["evidence_class"],
        "git_commit": git_commit(repo_root),
        "host": config.host.rstrip("/"),
        "plan": {
            "plan_id": plan["plan_id"],
            "path": _relative(repo_root, loaded["path"]),
            "sha256": loaded["sha256"],
        },
        "agent_results_dir": _relative(repo_root, agent_results),
        "pause": None,
        "units": [
            {
                "position": item["position"],
                "harness_id": item["harness_id"],
                "smoke_plan_path": item["smoke_plan_path"],
                "smoke_plan_sha256": item["smoke_plan_sha256"],
                "status": "pending",
                "run_id": None,
                "run_dir": None,
                "resource_gate": None,
                "exclusive_window_confirmations": [],
                "sandbox_acceptance": None,
                "outcome": None,
                "trajectory": None,
                "postflight_running_models": None,
            }
            for item in plan["execution_order"]
        ],
    }
    write_json(study_dir / "study.json", record)
    return _summary(record, study_dir)


def _load_study(
    repo_root: Path, study_dir: Path
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    resolved = resolve_repo_path(repo_root, study_dir)
    record = load_json(resolved / "study.json")
    if record.get("evidence_class") != "excluded_qualification_smoke_pair":
        raise RunnerError("Study is not a log-incident qualification pair")
    loaded = load_log_smoke_pair_plan(repo_root, Path(record["plan"]["path"]))
    if loaded["sha256"] != record["plan"]["sha256"]:
        raise RunnerError("Smoke-pair plan changed after study creation")
    return resolved, record, loaded


def _current_unit(record: dict[str, Any]) -> dict[str, Any] | None:
    return next(
        (item for item in record["units"] if item["status"] not in TERMINAL_UNIT_STATUSES),
        None,
    )


def _run_record(repo_root: Path, unit: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    if not unit.get("run_dir"):
        raise RunnerError("Smoke unit has no run directory")
    run_dir = resolve_repo_path(repo_root, Path(unit["run_dir"]))
    return run_dir, load_json(run_dir / "run.json")


def _sync_unit(repo_root: Path, unit: dict[str, Any]) -> dict[str, Any] | None:
    if not unit.get("run_dir"):
        return None
    _run_dir, run = _run_record(repo_root, unit)
    state = run.get("state")
    if unit["harness_id"] == "mini-log-v0.1":
        mapping = {
            "awaiting_model": "awaiting_model",
            "awaiting_action": "awaiting_action",
            "trajectory_complete_verification_pending": "verification_pending",
            "complete": "complete_needs_cleanup",
        }
        if state == "model_call_running":
            unit["status"] = "interrupted_inconclusive_needs_cleanup"
            unit["interruption"] = {
                "preserved_at": utc_now(),
                "reason": "process_interrupted_while_mini_model_call_was_running",
                "run_id": unit["run_id"],
                "automatic_retry": False,
            }
            return run
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
            unit["status"] = "interrupted_inconclusive_needs_cleanup"
            unit["interruption"] = {
                "preserved_at": utc_now(),
                "reason": "process_interrupted_while_pi_run_was_running",
                "run_id": unit["run_id"],
                "automatic_retry": False,
            }
            return run
    if state not in mapping:
        raise RunnerError(f"Unsupported {unit['harness_id']} run state: {state!r}")
    unit["status"] = mapping[state]
    if state == "complete":
        unit["outcome"] = run.get("outcome")
        unit["trajectory"] = run.get("trajectory")
    return run


def advance_log_smoke_study(repo_root: Path, study_dir: Path) -> dict[str, Any]:
    """Advance preparation, action or verification without model contact."""
    resolved, record, loaded = _load_study(repo_root, study_dir)
    study_path = resolved / "study.json"
    unit = _current_unit(record)
    if unit is None:
        record["status"] = "complete"
        record["completed_at"] = record.get("completed_at") or utc_now()
        write_json(study_path, record)
        return _summary(record, resolved)
    run = _sync_unit(repo_root, unit)
    if unit["status"] == "interrupted_inconclusive_needs_cleanup":
        record["status"] = "paused_inconclusive_needs_cleanup"
        write_json(study_path, record)
        return _summary(record, resolved)
    smoke = loaded["smokes"][unit["harness_id"]]["plan"]
    if unit["status"] == "pending":
        if unit["harness_id"] == "mini-log-v0.1":
            started = start_mini_log_run(
                repo_root,
                MiniLogStartConfig(
                    model=smoke["deployment"]["name"],
                    case_path=Path(smoke["case"]["case_path"]),
                    results_dir=Path(record["agent_results_dir"]),
                    host=record["host"],
                ),
            )
            unit["status"] = "awaiting_model"
        else:
            started = prepare_pi_log_run(
                repo_root,
                PiLogPrepareConfig(
                    model=smoke["deployment"]["name"],
                    case_path=Path(smoke["case"]["case_path"]),
                    results_dir=Path(record["agent_results_dir"]),
                    host=record["host"],
                ),
            )
            unit["status"] = "sandbox_pending"
        unit["run_id"] = started["run_id"]
        unit["run_dir"] = _relative(repo_root, Path(started["run_dir"]))
        unit["prepared_at"] = utc_now()
        record["status"] = "waiting_for_local_step"
        record["pause"] = None
        write_json(study_path, record)
        return _summary(record, resolved)
    run_dir, run = _run_record(repo_root, unit)
    if unit["status"] == "awaiting_action":
        step_mini_log_action(repo_root, run_dir)
        _sync_unit(repo_root, unit)
    elif unit["status"] == "sandbox_pending":
        acceptance = validate_pi_log_seatbelt(run_dir)
        unit["sandbox_acceptance"] = {
            "passed": acceptance["passed"],
            "validated_at": acceptance["validated_at"],
            "profile_sha256": acceptance["profile_sha256"],
        }
        unit["status"] = "sandbox_accepted"
    elif unit["status"] == "verification_pending":
        if unit["harness_id"] == "mini-log-v0.1":
            finalize_mini_log_run(repo_root, run_dir)
        else:
            finalize_pi_log_run(repo_root, run_dir)
        _sync_unit(repo_root, unit)
    elif unit["status"] in {"awaiting_model", "sandbox_accepted", "complete_needs_cleanup"}:
        return _summary(record, resolved)
    else:
        raise RunnerError(f"Cannot advance smoke state {unit['status']!r}")
    record["status"] = "waiting_for_local_step"
    record["pause"] = None
    write_json(study_path, record)
    return _summary(record, resolved)


def run_log_smoke_live_step(
    repo_root: Path,
    study_dir: Path,
    *,
    client: OllamaClient | None = None,
    process_reader: Callable[[], list[dict[str, Any]]] = _process_snapshot,
    sleep: Callable[[float], None] = time.sleep,
    exclusive_window_confirmed: bool = False,
) -> dict[str, Any]:
    """Cross one model boundary only after the frozen resource gate passes."""
    resolved, record, loaded = _load_study(repo_root, study_dir)
    if not exclusive_window_confirmed:
        raise RunnerError(
            "Live smoke execution requires explicit confirmation that no external "
            "agent can restart a competing workload during the run"
        )
    unit = _current_unit(record)
    if unit is None:
        raise RunnerError("Smoke pair has no pending live boundary")
    unit.setdefault("exclusive_window_confirmations", []).append(
        {
            "confirmed": True,
            "recorded_at": utc_now(),
            "scope": "one_live_command",
        }
    )
    write_json(resolved / "study.json", record)
    run = _sync_unit(repo_root, unit)
    expected = (
        "awaiting_model" if unit["harness_id"] == "mini-log-v0.1" else "sandbox_accepted"
    )
    if unit["status"] != expected:
        raise RunnerError(f"Smoke unit is not ready for live execution: {unit['status']}")
    smoke = loaded["smokes"][unit["harness_id"]]["plan"]
    ollama = client or OllamaClient(record["host"])
    needs_empty_gate = unit["harness_id"] == "pi-log-v0.1" or (
        isinstance(run, dict) and run.get("trajectory", {}).get("model_requests") == 0
    )
    try:
        if needs_empty_gate:
            gate_plan = {
                "runtime": smoke["runtime"],
                "deployment": smoke["deployment"],
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
                raise _gate_failure(
                    "Concurrent workload appeared during the Mini trajectory.",
                    stage="continuation_process_snapshot",
                    blockers=blockers,
                )
            running = running_model_names(ollama.list_running_models())
            unexpected = sorted(
                name for name in running if name != smoke["deployment"]["name"]
            )
            if unexpected:
                raise _gate_failure(
                    "An unrelated Ollama model appeared during the Mini trajectory.",
                    stage="continuation_ollama_snapshot",
                    running_models=unexpected,
                )
    except ResourceGatePause as exc:
        record["status"] = "paused_resource_gate"
        record["pause"] = exc.evidence
        write_json(resolved / "study.json", record)
        raise
    run_dir, _run = _run_record(repo_root, unit)
    record["status"] = "running_live_boundary"
    record["pause"] = None
    write_json(resolved / "study.json", record)
    if unit["harness_id"] == "mini-log-v0.1":
        call_mini_log_model(repo_root, run_dir)
    else:
        execute_pi_log_run(repo_root, run_dir)
    _sync_unit(repo_root, unit)
    record["status"] = "waiting_for_local_step"
    write_json(resolved / "study.json", record)
    return _summary(record, resolved)


def cleanup_log_smoke_unit(
    repo_root: Path,
    study_dir: Path,
    *,
    client: OllamaClient | None = None,
) -> dict[str, Any]:
    """Unload one terminal unit and require an empty Ollama postflight."""
    resolved, record, loaded = _load_study(repo_root, study_dir)
    unit = _current_unit(record)
    cleanup_statuses = {
        "complete_needs_cleanup",
        "interrupted_inconclusive_needs_cleanup",
    }
    if unit is None or unit["status"] not in cleanup_statuses:
        raise RunnerError("No terminal smoke unit is awaiting cleanup")
    smoke = loaded["smokes"][unit["harness_id"]]["plan"]
    ollama = client or OllamaClient(record["host"])
    ollama.unload_model(smoke["deployment"]["name"])
    running = running_model_names(ollama.list_running_models())
    unit["postflight_running_models"] = running
    if running:
        evidence = {
            "passed": False,
            "observed_at": utc_now(),
            "stage": "postflight_cleanup",
            "reason": "Ollama was not empty after cleanup.",
            "running_models": running,
            "inference_requests_made": 0,
        }
        record["status"] = "paused_resource_gate"
        record["pause"] = evidence
        write_json(resolved / "study.json", record)
        raise ResourceGatePause(evidence["reason"], evidence)
    unit["status"] = (
        "interrupted_inconclusive"
        if unit["status"] == "interrupted_inconclusive_needs_cleanup"
        else "complete"
    )
    unit["completed_at"] = utc_now()
    record["status"] = "ready_for_local_preparation"
    record["pause"] = None
    write_json(resolved / "study.json", record)
    return _summary(record, resolved)


def _public_unit(repo_root: Path, unit: dict[str, Any]) -> dict[str, Any]:
    run_dir, run = _run_record(repo_root, unit)
    if unit["status"] == "interrupted_inconclusive":
        return {
            "position": unit["position"],
            "harness_id": unit["harness_id"],
            "status": unit["status"],
            "verified_success": None,
            "failure_category": "inconclusive_control_event",
            "failure_type": unit["interruption"]["reason"],
            "run_id": run.get("run_id"),
        }
    outcome = run.get("outcome") or {}
    trajectory = run.get("trajectory") or {}
    return {
        "position": unit["position"],
        "harness_id": unit["harness_id"],
        "status": "complete",
        "run_id": run.get("run_id"),
        "verified_success": outcome.get("verified_success"),
        "runtime_success": outcome.get("runtime_success"),
        "agent_termination_valid": outcome.get("agent_termination_valid"),
        "verifier_success": outcome.get("verifier_success"),
        "failure_category": outcome.get("failure_category"),
        "failure_type": outcome.get("failure_type"),
        "active_wall_time_seconds": trajectory.get("active_wall_time_seconds"),
        "agent_turns": trajectory.get("agent_turns"),
        "file_reads": trajectory.get("file_reads"),
        "repeated_file_reads": trajectory.get("repeated_file_reads"),
        "input_tokens": trajectory.get("input_tokens"),
        "output_tokens": trajectory.get("output_tokens"),
    }


def build_log_smoke_report(repo_root: Path, study_dir: Path) -> dict[str, Any]:
    """Create public-safe JSON and Markdown after terminal excluded smokes."""
    resolved, record, loaded = _load_study(repo_root, study_dir)
    if any(unit["status"] not in TERMINAL_UNIT_STATUSES for unit in record["units"]):
        raise RunnerError("Smoke report requires terminal outcomes for every planned unit")
    plan = loaded["plan"]
    units = [_public_unit(repo_root, unit) for unit in record["units"]]
    public = {
        "schema_version": "1.0.0",
        "report_id": plan["reporting"]["report_id"],
        "status": "complete" if all(u["status"] == "complete" for u in units) else "inconclusive",
        "generated_at": utc_now(),
        "evidence_class": plan["evidence_class"],
        "case_id": plan["case"]["case_id"],
        "deployment": {
            key: plan["deployment"][key]
            for key in ("name", "deployment_id", "digest", "quantization")
        },
        "runtime": plan["runtime"],
        "units": units,
        "interpretation": {
            "qualifies_machinery_only": True,
            "included_in_measured_aggregates": False,
            "comparison_unit": "complete_system",
            "one_factor_causal_harness_claim_allowed": False,
            "candidate_output_published": False,
            "next_gate": "Freeze a measured Capability Sweep only if both complete-system trajectories are interpretable and no orchestration defect is present.",
        },
    }
    json_path = resolve_repo_path(repo_root, Path(plan["reporting"]["json_path"]))
    markdown_path = resolve_repo_path(
        repo_root, Path(plan["reporting"]["markdown_path"])
    )
    write_json(json_path, public)
    rows = []
    for unit in units:
        outcome = (
            "pass"
            if unit.get("verified_success") is True
            else "fail"
            if unit.get("verified_success") is False
            else "inconclusive"
        )
        duration = unit.get("active_wall_time_seconds")
        rows.append(
            f"| `{unit['harness_id']}` | {outcome} | "
            f"{duration if duration is not None else 'n/a'} | "
            f"{unit.get('agent_turns', 'n/a')} | {unit.get('file_reads', 'n/a')} | "
            f"{unit.get('failure_type') or 'none'} |"
        )
    markdown = "\n".join(
        [
            "# Log-Incident Qualification Smokes v0.1",
            "",
            f"Status: **{public['status']}**",
            "",
            "These two one-attempt development smokes qualify machinery only. They are",
            "excluded from measured aggregates and cannot support a harness ranking.",
            "",
            "| Complete system | Outcome | Active seconds | Turns | File reads | Failure |",
            "| --- | --- | ---: | ---: | ---: | --- |",
            *rows,
            "",
            "Pi and Mini differ in prompts, tool protocols, context handling and failure",
            "behavior. Their results are therefore complete-system observations, not a",
            "one-factor causal estimate of the harness implementation.",
            "",
            "Candidate responses, log contents, verifier details and absolute local paths",
            "are intentionally absent from this public report.",
            "",
        ]
    )
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(markdown, encoding="utf-8")
    return {
        "status": public["status"],
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
        "unit_count": len(units),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="Validate frozen plans only")
    validate.add_argument("--plan", type=Path, default=DEFAULT_PAIR_PLAN)
    preflight = subparsers.add_parser(
        "preflight", help="Run the no-inference process and Ollama resource gate"
    )
    preflight.add_argument("--plan", type=Path, default=DEFAULT_PAIR_PLAN)
    start = subparsers.add_parser("start", help="Create a study without model contact")
    start.add_argument("--plan", type=Path, default=DEFAULT_PAIR_PLAN)
    start.add_argument("--host", default="http://127.0.0.1:11434")
    start.add_argument(
        "--results-dir", type=Path, default=Path("results/agentic-studies")
    )
    start.add_argument(
        "--agent-results-dir", type=Path, default=Path("results/agentic-runs")
    )
    for name, help_text in (
        ("advance", "Perform one local non-inference state transition"),
        ("live", "Perform one resource-gated model boundary"),
        ("cleanup", "Unload one completed unit"),
        ("report", "Verify terminal outcomes and write public-safe reports"),
        ("status", "Show the durable study state"),
    ):
        child = subparsers.add_parser(name, help=help_text)
        child.add_argument("--study-dir", type=Path, required=True)
        if name == "live":
            child.add_argument(
                "--exclusive-window-confirmed",
                action="store_true",
                help="Confirm that no external agent can restart a competing workload",
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    try:
        if args.command == "validate":
            loaded = load_log_smoke_pair_plan(repo_root, args.plan)
            result = {
                "status": "valid",
                "plan_id": loaded["plan"]["plan_id"],
                "plan_sha256": loaded["sha256"],
                "live_ollama_requests": 0,
            }
        elif args.command == "preflight":
            loaded = load_log_smoke_pair_plan(repo_root, args.plan)
            result = run_resource_gate(
                loaded["plan"], client=OllamaClient(loaded["plan"]["runtime"]["host"])
            )
        elif args.command == "start":
            result = start_log_smoke_study(
                repo_root,
                LogSmokeStudyConfig(
                    plan_path=args.plan,
                    results_dir=args.results_dir,
                    agent_results_dir=args.agent_results_dir,
                    host=args.host,
                ),
            )
        elif args.command == "advance":
            result = advance_log_smoke_study(repo_root, args.study_dir)
        elif args.command == "live":
            result = run_log_smoke_live_step(
                repo_root,
                args.study_dir,
                exclusive_window_confirmed=args.exclusive_window_confirmed,
            )
        elif args.command == "cleanup":
            result = cleanup_log_smoke_unit(repo_root, args.study_dir)
        elif args.command == "report":
            result = build_log_smoke_report(repo_root, args.study_dir)
        else:
            resolved, record, _loaded = _load_study(repo_root, args.study_dir)
            result = _summary(record, resolved)
    except ResourceGatePause as exc:
        print(
            json.dumps(
                {"status": "paused_resource_gate", "error": str(exc), "gate": exc.evidence},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 2
    except (OSError, RunnerError, OllamaError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
