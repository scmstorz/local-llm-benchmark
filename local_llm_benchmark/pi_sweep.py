"""Append-only orchestration for measured multi-model Pi capability sweeps."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from .macos_sandbox import validate_pi_seatbelt
from .ollama import OllamaClient
from .pi_adapter import (
    PiAgentPrepareConfig,
    execute_pi_agent_run,
    finalize_pi_agent_run,
    load_pi_harness,
    prepare_pi_agent_run,
)
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


DEFAULT_PI_SWEEP_PLAN_PATH = Path(
    "tasks/coding/track-b/pi-capability-sweep-v0.1.json"
)


@dataclass(frozen=True)
class PiSweepConfig:
    """Inputs for a new measured Pi capability sweep."""

    plan_path: Path = DEFAULT_PI_SWEEP_PLAN_PATH
    results_dir: Path = Path("results/agentic-sweeps")
    agent_results_dir: Path = Path("results/agentic-runs")
    host: str = "http://127.0.0.1:11434"


@dataclass(frozen=True)
class PiSweepResumeConfig:
    """Inputs for resuming one existing Pi capability sweep."""

    sweep_dir: Path
    host: str = "http://127.0.0.1:11434"


class ResourceGatePause(RunnerError):
    """Raised when external Ollama activity prevents a controlled run."""


def load_pi_sweep_plan(repo_root: Path, plan_path: Path) -> dict[str, Any]:
    """Load and validate a frozen Cartesian model-by-task Pi sweep plan."""
    resolved_plan_path = resolve_repo_path(repo_root, plan_path)
    plan = load_json(resolved_plan_path)
    if plan.get("schema_version") != "1.0.0":
        raise RunnerError("Unsupported Pi sweep plan schema version")
    if plan.get("status") != "frozen_before_execution":
        raise RunnerError("Pi sweep plan must be frozen before execution")
    if plan.get("track") != "B" or plan.get("harness_id") != "pi-v0.2":
        raise RunnerError("Pi sweep plan must target Track B with pi-v0.2")
    if plan.get("evidence_class") != "measured_capability_sweep":
        raise RunnerError("Pi sweep plan has an unexpected evidence class")
    runtime = plan.get("runtime")
    if (
        not isinstance(runtime, dict)
        or runtime.get("name") != "ollama"
        or not isinstance(runtime.get("version"), str)
        or not runtime["version"]
    ):
        raise RunnerError("Pi sweep plan must freeze an exact Ollama version")

    harness_path_value = plan.get("harness_path")
    if not isinstance(harness_path_value, str) or not harness_path_value:
        raise RunnerError("Pi sweep plan must define harness_path")
    harness_path = Path(harness_path_value)
    loaded_harness = load_pi_harness(repo_root, harness_path)
    if loaded_harness["harness"]["harness_id"] != plan["harness_id"]:
        raise RunnerError("Pi sweep harness identity mismatch")

    frozen_inputs = plan.get("frozen_inputs")
    artifacts = frozen_inputs.get("artifacts") if isinstance(frozen_inputs, dict) else None
    if not isinstance(artifacts, list) or not artifacts:
        raise RunnerError("Pi sweep plan must freeze input artifact hashes")
    for position, artifact in enumerate(artifacts, start=1):
        if not isinstance(artifact, dict):
            raise RunnerError(f"Invalid frozen artifact at position {position}")
        relative = artifact.get("path")
        expected = artifact.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise RunnerError(f"Incomplete frozen artifact at position {position}")
        resolved = resolve_repo_path(repo_root, Path(relative))
        if not resolved.is_file() or sha256_file(resolved) != expected:
            raise RunnerError(f"Pi sweep frozen artifact drift: {relative}")

    models = plan.get("deployments")
    cases = plan.get("cases")
    execution_order = plan.get("execution_order")
    if not isinstance(models, list) or not models:
        raise RunnerError("Pi sweep plan must define deployments")
    if not isinstance(cases, list) or not cases:
        raise RunnerError("Pi sweep plan must define cases")
    if not isinstance(execution_order, list):
        raise RunnerError("Pi sweep plan must define execution_order")

    model_by_name: dict[str, dict[str, Any]] = {}
    for model in models:
        if not isinstance(model, dict):
            raise RunnerError("Pi sweep deployment entries must be objects")
        name = model.get("name")
        digest = model.get("digest")
        deployment_id = model.get("deployment_id")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(digest, str)
            or len(digest) != 64
            or not isinstance(deployment_id, str)
            or not deployment_id
        ):
            raise RunnerError("Pi sweep deployment identity is incomplete")
        if name in model_by_name:
            raise RunnerError(f"Duplicate Pi sweep deployment: {name}")
        model_by_name[name] = model

    case_by_id: dict[str, dict[str, Any]] = {}
    selected_protocol_cases = {
        item["case_id"]: item["case_path"]
        for item in loaded_harness["protocol"]["task_subset"]
    }
    for case in cases:
        if not isinstance(case, dict):
            raise RunnerError("Pi sweep case entries must be objects")
        case_id = case.get("case_id")
        case_path = case.get("case_path")
        if not isinstance(case_id, str) or not isinstance(case_path, str):
            raise RunnerError("Pi sweep case identity is incomplete")
        if case_id in case_by_id:
            raise RunnerError(f"Duplicate Pi sweep case: {case_id}")
        if selected_protocol_cases.get(case_id) != case_path:
            raise RunnerError(f"Pi sweep case is outside the frozen protocol: {case_id}")
        case_by_id[case_id] = case

    expected_units = {
        (model_name, case_id)
        for model_name in model_by_name
        for case_id in case_by_id
    }
    observed_units: set[tuple[str, str]] = set()
    for position, unit in enumerate(execution_order, start=1):
        if not isinstance(unit, dict) or unit.get("position") != position:
            raise RunnerError("Pi sweep execution positions must be contiguous")
        key = (unit.get("model"), unit.get("case_id"))
        if key not in expected_units or key in observed_units:
            raise RunnerError(f"Invalid or duplicate Pi sweep execution unit: {key}")
        observed_units.add(key)
    if observed_units != expected_units:
        raise RunnerError("Pi sweep execution order is not the full model-by-case product")

    comparison = plan.get("comparison_rules", {})
    if (
        comparison.get("runs_per_configuration") != 1
        or comparison.get("automatic_retries") != 0
        or comparison.get("performance_distribution_claims") is not False
    ):
        raise RunnerError("Pi sweep must remain a one-run capability screen")
    gate = plan.get("resource_gate", {})
    seconds = gate.get("empty_state_observation_seconds")
    if not isinstance(seconds, int) or seconds < 0:
        raise RunnerError("Pi sweep resource-gate observation must be nonnegative")

    return {
        "plan": plan,
        "plan_path": resolved_plan_path,
        "plan_sha256": sha256_file(resolved_plan_path),
        "harness_path": harness_path,
        "models": model_by_name,
        "cases": case_by_id,
    }


def _sweep_summary(record: dict[str, Any], sweep_dir: Path) -> dict[str, Any]:
    return {
        "sweep_id": record["sweep_id"],
        "sweep_dir": str(sweep_dir),
        "status": record["status"],
        "unit_count": record["unit_count"],
        "complete_unit_count": record["complete_unit_count"],
        "verified_success_count": record["verified_success_count"],
        "failed_unit_count": record["failed_unit_count"],
    }


def _recount(record: dict[str, Any]) -> None:
    complete = [unit for unit in record["units"] if unit["status"] == "complete"]
    record["complete_unit_count"] = len(complete)
    record["verified_success_count"] = sum(
        bool(unit.get("outcome", {}).get("verified_success")) for unit in complete
    )
    record["failed_unit_count"] = sum(
        unit["status"] == "failed" for unit in record["units"]
    )


def _validate_installed_deployments(
    client: OllamaClient, loaded_plan: dict[str, Any]
) -> dict[str, Any]:
    tags = client.list_models()
    observed: dict[str, Any] = {}
    for name, frozen in loaded_plan["models"].items():
        model = find_model(tags, name)
        if model.get("digest") != frozen["digest"]:
            raise RunnerError(
                f"Ollama digest drift for {name}: expected {frozen['digest']}, "
                f"found {model.get('digest')}"
            )
        observed[name] = model
    return observed


def _validate_unit_deployment(client: OllamaClient, unit: dict[str, Any]) -> None:
    observed = find_model(client.list_models(), unit["model"])
    if observed.get("digest") != unit["digest"]:
        raise RunnerError(
            f"Ollama digest drift for {unit['model']}: expected {unit['digest']}, "
            f"found {observed.get('digest')}"
        )


def _empty_resource_gate(
    client: OllamaClient,
    *,
    observation_seconds: int,
    sleep: Callable[[float], None],
) -> dict[str, Any]:
    first = running_model_names(client.list_running_models())
    if first:
        raise ResourceGatePause(
            "Ollama resource gate found loaded models before observation: "
            + ", ".join(first)
        )
    observed_at = utc_now()
    if observation_seconds:
        sleep(observation_seconds)
    second = running_model_names(client.list_running_models())
    if second:
        raise ResourceGatePause(
            "Ollama resource gate observed model activity: " + ", ".join(second)
        )
    return {
        "observed_at": observed_at,
        "observation_seconds": observation_seconds,
        "first_running_models": first,
        "second_running_models": second,
        "passed": True,
    }


def _relative_to_repo(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise RunnerError(f"Pi sweep artifact escapes repository: {path}") from exc


def _reconcile_unit(repo_root: Path, unit: dict[str, Any]) -> None:
    run_dir_value = unit.get("run_dir")
    if not run_dir_value:
        return
    run_dir = resolve_repo_path(repo_root, Path(run_dir_value))
    run_record = load_json(run_dir / "run.json")
    state = run_record.get("state")
    if state == "complete":
        unit["status"] = "complete"
        unit["outcome"] = run_record.get("outcome")
        unit["trajectory"] = run_record.get("trajectory")
        return
    if state == "execution_complete_verification_pending":
        unit["status"] = "execution_complete_verification_pending"
        return
    if state == "prepared_not_executed":
        acceptance = run_dir / "pi-sandbox-acceptance.json"
        unit["status"] = "sandbox_accepted" if acceptance.is_file() else "prepared"
        unit["resource_gate"] = None
        return
    if state == "running":
        unit.setdefault("interrupted_attempts", []).append(
            {
                "run_id": unit.get("run_id"),
                "run_dir": unit.get("run_dir"),
                "preserved_at": utc_now(),
                "reason": "process_interrupted_while_pi_run_state_was_running",
            }
        )
        unit["run_id"] = None
        unit["run_dir"] = None
        unit["status"] = "pending"
        unit["resource_gate"] = None
        return
    raise RunnerError(f"Cannot reconcile Pi run state {state!r}")


def _execute_sweep(
    repo_root: Path,
    sweep_dir: Path,
    loaded_plan: dict[str, Any],
    client: OllamaClient,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    sweep_path = sweep_dir / "sweep.json"
    record = load_json(sweep_path)
    if record["plan"]["sha256"] != loaded_plan["plan_sha256"]:
        raise RunnerError("Pi sweep plan changed after sweep creation")
    _validate_installed_deployments(client, loaded_plan)
    gate_seconds = loaded_plan["plan"]["resource_gate"][
        "empty_state_observation_seconds"
    ]

    for unit in record["units"]:
        _reconcile_unit(repo_root, unit)
        _recount(record)
        write_json(sweep_path, record)
        if unit["status"] in {"complete", "failed"}:
            continue
        try:
            if unit["status"] == "pending":
                prepared = prepare_pi_agent_run(
                    repo_root,
                    PiAgentPrepareConfig(
                        model=unit["model"],
                        case_path=Path(unit["case_path"]),
                        harness_path=loaded_plan["harness_path"],
                        results_dir=Path(record["agent_results_dir"]),
                        host=record["host"],
                    ),
                )
                unit["run_id"] = prepared["run_id"]
                unit["run_dir"] = _relative_to_repo(
                    repo_root, Path(prepared["run_dir"])
                )
                unit["status"] = "prepared"
                unit["started_at"] = utc_now()
                record["status"] = "running"
                record["pause"] = None
                write_json(sweep_path, record)

            run_dir = resolve_repo_path(repo_root, Path(unit["run_dir"]))
            if unit["status"] == "prepared":
                acceptance = validate_pi_seatbelt(run_dir)
                unit["sandbox_acceptance"] = {
                    "passed": acceptance["passed"],
                    "validated_at": acceptance["validated_at"],
                    "profile_sha256": acceptance["profile_sha256"],
                    "hidden_verifier_sha256": acceptance[
                        "hidden_verifier_sha256"
                    ],
                }
                unit["status"] = "sandbox_accepted"
                write_json(sweep_path, record)

            if unit["status"] == "sandbox_accepted":
                try:
                    unit["resource_gate"] = _empty_resource_gate(
                        client,
                        observation_seconds=gate_seconds,
                        sleep=sleep,
                    )
                except ResourceGatePause as exc:
                    record["status"] = "paused_resource_gate"
                    record["pause"] = {
                        "at": utc_now(),
                        "position": unit["position"],
                        "reason": str(exc),
                    }
                    write_json(sweep_path, record)
                    raise ResourceGatePause(
                        f"{exc}. Resume {sweep_dir} after Ollama is idle."
                    ) from exc
                _validate_unit_deployment(client, unit)
                write_json(sweep_path, record)
                execution = execute_pi_agent_run(repo_root, run_dir)
                unit["execution"] = {
                    key: execution[key]
                    for key in (
                        "runtime_success",
                        "agent_termination_valid",
                        "termination_reason",
                        "trajectory",
                    )
                }
                unit["status"] = "execution_complete_verification_pending"
                write_json(sweep_path, record)

            if unit["status"] == "execution_complete_verification_pending":
                outcome = finalize_pi_agent_run(repo_root, run_dir)
                raw_record = load_json(run_dir / "run.json")
                unit["outcome"] = {
                    key: outcome[key]
                    for key in (
                        "runtime_success",
                        "agent_termination_valid",
                        "verifier_success",
                        "verified_success",
                        "failure_category",
                        "failure_type",
                        "public_tests",
                        "hidden_tests",
                    )
                }
                unit["trajectory"] = raw_record.get("trajectory")
                unit["status"] = "complete"
                unit["completed_at"] = utc_now()
                client.unload_model(unit["model"])
                postflight = running_model_names(client.list_running_models())
                unit["postflight_running_models"] = postflight
                _recount(record)
                write_json(sweep_path, record)
                if postflight:
                    record["status"] = "paused_resource_gate"
                    record["pause"] = {
                        "at": utc_now(),
                        "position": unit["position"],
                        "reason": "Ollama was not empty after unloading the measured model: "
                        + ", ".join(postflight),
                    }
                    write_json(sweep_path, record)
                    raise ResourceGatePause(
                        f"Postflight resource gate failed. Resume {sweep_dir} after Ollama is idle."
                    )
        except ResourceGatePause:
            raise
        except Exception as exc:
            unit["status"] = "failed"
            unit["completed_at"] = utc_now()
            unit["error"] = {"type": type(exc).__name__, "message": str(exc)}
            try:
                client.unload_model(unit["model"])
            except Exception as cleanup_exc:
                unit["cleanup_error"] = {
                    "type": type(cleanup_exc).__name__,
                    "message": str(cleanup_exc),
                }
            _recount(record)
            record["status"] = "paused_infrastructure_failure"
            record["pause"] = {
                "at": utc_now(),
                "position": unit["position"],
                "reason": str(exc),
            }
            write_json(sweep_path, record)
            raise RunnerError(
                f"Pi sweep unit {unit['position']} failed before a complete outcome: "
                f"{exc}. Evidence is preserved in {sweep_dir}."
            ) from exc

    _recount(record)
    record["status"] = (
        "complete" if record["failed_unit_count"] == 0 else "complete_with_failures"
    )
    record["completed_at"] = utc_now()
    record["pause"] = None
    write_json(sweep_path, record)
    return _sweep_summary(record, sweep_dir)


def start_pi_sweep(
    repo_root: Path,
    config: PiSweepConfig,
    *,
    client: OllamaClient | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Create, checkpoint and execute one frozen Pi capability sweep."""
    loaded_plan = load_pi_sweep_plan(repo_root, config.plan_path)
    ollama = client or OllamaClient(config.host)
    deployments = _validate_installed_deployments(ollama, loaded_plan)
    version = ollama.version().get("version")
    expected_version = loaded_plan["plan"].get("runtime", {}).get("version")
    if expected_version != version:
        raise RunnerError(
            f"Pi sweep requires Ollama {expected_version}, found {version}"
        )
    results_dir = resolve_repo_path(repo_root, config.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    sweep_id = f"pi-sweep-{timestamp}-{secrets.token_hex(4)}"
    sweep_dir = results_dir / sweep_id
    sweep_dir.mkdir(parents=True, exist_ok=False)

    plan = loaded_plan["plan"]
    record = {
        "schema_version": "1.0.0",
        "sweep_id": sweep_id,
        "status": "running",
        "started_at": utc_now(),
        "completed_at": None,
        "track": "B",
        "evidence_class": plan["evidence_class"],
        "host": config.host,
        "ollama_version": version,
        "git_commit": git_commit(repo_root),
        "plan": {
            "plan_id": plan["plan_id"],
            "path": loaded_plan["plan_path"].relative_to(repo_root).as_posix(),
            "sha256": loaded_plan["plan_sha256"],
        },
        "agent_results_dir": _relative_to_repo(
            repo_root, resolve_repo_path(repo_root, config.agent_results_dir)
        ),
        "unit_count": len(plan["execution_order"]),
        "complete_unit_count": 0,
        "verified_success_count": 0,
        "failed_unit_count": 0,
        "pause": None,
        "deployments": [
            {
                **item,
                "observed_size_bytes": deployments[item["name"]].get("size"),
            }
            for item in plan["deployments"]
        ],
        "units": [
            {
                "position": item["position"],
                "model": item["model"],
                "deployment_id": loaded_plan["models"][item["model"]][
                    "deployment_id"
                ],
                "digest": loaded_plan["models"][item["model"]]["digest"],
                "case_id": item["case_id"],
                "case_path": loaded_plan["cases"][item["case_id"]]["case_path"],
                "status": "pending",
                "run_id": None,
                "run_dir": None,
                "resource_gate": None,
                "interrupted_attempts": [],
                "outcome": None,
                "trajectory": None,
                "error": None,
            }
            for item in plan["execution_order"]
        ],
    }
    write_json(sweep_dir / "sweep.json", record)
    return _execute_sweep(
        repo_root, sweep_dir, loaded_plan, ollama, sleep=sleep
    )


def resume_pi_sweep(
    repo_root: Path,
    config: PiSweepResumeConfig,
    *,
    client: OllamaClient | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Resume unfinished Pi units without repeating terminal outcomes."""
    sweep_dir = resolve_repo_path(repo_root, config.sweep_dir)
    record = load_json(sweep_dir / "sweep.json")
    plan_path = Path(record["plan"]["path"])
    loaded_plan = load_pi_sweep_plan(repo_root, plan_path)
    if loaded_plan["plan_sha256"] != record["plan"]["sha256"]:
        raise RunnerError("Pi sweep plan hash changed before resume")
    if record.get("status") in {"complete", "complete_with_failures"}:
        return _sweep_summary(record, sweep_dir)
    ollama = client or OllamaClient(config.host)
    if ollama.version().get("version") != record.get("ollama_version"):
        raise RunnerError("Ollama version changed before Pi sweep resume")
    return _execute_sweep(
        repo_root, sweep_dir, loaded_plan, ollama, sleep=sleep
    )
