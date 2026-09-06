"""Stepwise, sandbox-preserving orchestration for Mini v0.3 sweeps."""

from __future__ import annotations

import argparse
import json
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from .mini_v03_adapter import (
    MiniV03StartConfig,
    call_mini_v03_model,
    finalize_mini_v03_run,
    load_mini_v03_harness,
    start_mini_v03_run,
    step_mini_v03_action,
)
from .ollama import OllamaClient
from .pi_v03_sweep import ResourceGatePause
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


DEFAULT_MINI_V03_SWEEP_PLAN = Path(
    "tasks/coding/track-b/mini-capability-sweep-v0.3.json"
)


@dataclass(frozen=True)
class MiniV03SweepConfig:
    """Inputs for creating a stepwise Mini v0.3 sweep."""

    plan_path: Path = DEFAULT_MINI_V03_SWEEP_PLAN
    results_dir: Path = Path("results/agentic-sweeps")
    agent_results_dir: Path = Path("results/agentic-runs")
    host: str = "http://127.0.0.1:11434"


def _relative_to_repo(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise RunnerError(f"Mini v0.3 artifact escapes repository: {path}") from exc


def load_mini_v03_sweep_plan(repo_root: Path, plan_path: Path) -> dict[str, Any]:
    """Validate one frozen Cartesian Mini v0.3 capability plan."""
    resolved_plan = resolve_repo_path(repo_root, plan_path)
    plan = load_json(resolved_plan)
    if plan.get("schema_version") != "1.0.0":
        raise RunnerError("Unsupported Mini v0.3 sweep plan schema")
    if plan.get("status") != "frozen_before_execution":
        raise RunnerError("Mini v0.3 sweep plan must be frozen before execution")
    if (
        plan.get("track") != "B"
        or plan.get("harness_id") != "mini-v0.3"
        or plan.get("evidence_class") != "measured_capability_sweep"
    ):
        raise RunnerError("Unexpected Mini v0.3 sweep identity")
    runtime = plan.get("runtime")
    if (
        not isinstance(runtime, dict)
        or runtime.get("name") != "ollama"
        or not isinstance(runtime.get("version"), str)
    ):
        raise RunnerError("Mini v0.3 plan must freeze an Ollama version")
    harness_value = plan.get("harness_path")
    if not isinstance(harness_value, str):
        raise RunnerError("Mini v0.3 plan must define harness_path")
    harness_path = Path(harness_value)
    loaded_harness = load_mini_v03_harness(repo_root, harness_path)
    if (
        loaded_harness["harness"]["status"]
        != "qualified_for_capability_sweep_planning"
    ):
        raise RunnerError("Mini v0.3 harness is not qualified for planning")

    artifacts = plan.get("frozen_inputs", {}).get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise RunnerError("Mini v0.3 plan must freeze input artifacts")
    for position, artifact in enumerate(artifacts, start=1):
        if not isinstance(artifact, dict):
            raise RunnerError(f"Invalid frozen artifact at position {position}")
        path_value = artifact.get("path")
        digest = artifact.get("sha256")
        if not isinstance(path_value, str) or not isinstance(digest, str):
            raise RunnerError(f"Incomplete frozen artifact at position {position}")
        path = resolve_repo_path(repo_root, Path(path_value))
        if not path.is_file() or sha256_file(path) != digest:
            raise RunnerError(f"Mini v0.3 frozen artifact drift: {path_value}")

    deployments = plan.get("deployments")
    cases = plan.get("cases")
    order = plan.get("execution_order")
    if not isinstance(deployments, list) or not deployments:
        raise RunnerError("Mini v0.3 plan must define deployments")
    if not isinstance(cases, list) or not cases:
        raise RunnerError("Mini v0.3 plan must define cases")
    if not isinstance(order, list):
        raise RunnerError("Mini v0.3 plan must define execution_order")
    model_by_name: dict[str, dict[str, Any]] = {}
    for deployment in deployments:
        if not isinstance(deployment, dict):
            raise RunnerError("Mini deployment entries must be objects")
        name = deployment.get("name")
        digest = deployment.get("digest")
        deployment_id = deployment.get("deployment_id")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(digest, str)
            or len(digest) != 64
            or not isinstance(deployment_id, str)
            or not deployment_id
        ):
            raise RunnerError("Mini deployment identity is incomplete")
        if name in model_by_name:
            raise RunnerError(f"Duplicate Mini deployment: {name}")
        model_by_name[name] = deployment

    selected_cases = {
        item["case_id"]: item["case_path"]
        for item in loaded_harness["protocol"]["task_subset"]
    }
    case_by_id: dict[str, dict[str, Any]] = {}
    for case in cases:
        if not isinstance(case, dict):
            raise RunnerError("Mini case entries must be objects")
        case_id = case.get("case_id")
        case_path = case.get("case_path")
        if (
            not isinstance(case_id, str)
            or selected_cases.get(case_id) != case_path
            or case_id in case_by_id
        ):
            raise RunnerError(f"Invalid Mini case identity: {case_id}")
        case_by_id[case_id] = case

    expected = {
        (model, case_id) for model in model_by_name for case_id in case_by_id
    }
    observed: set[tuple[str, str]] = set()
    for position, unit in enumerate(order, start=1):
        if not isinstance(unit, dict) or unit.get("position") != position:
            raise RunnerError("Mini execution positions must be contiguous")
        key = (unit.get("model"), unit.get("case_id"))
        if key not in expected or key in observed:
            raise RunnerError(f"Invalid or duplicate Mini execution unit: {key}")
        observed.add(key)
    if observed != expected:
        raise RunnerError("Mini execution order is not the full Cartesian product")

    rules = plan.get("comparison_rules", {})
    if (
        rules.get("runs_per_configuration") != 1
        or rules.get("automatic_retries") != 0
        or rules.get("performance_distribution_claims") is not False
    ):
        raise RunnerError("Mini v0.3 plan must remain a one-run capability screen")
    if plan.get("smoke_gate", {}).get("passed") is not True:
        raise RunnerError("Mini v0.3 sweep requires a passing excluded smoke gate")
    gate_seconds = plan.get("resource_gate", {}).get(
        "empty_state_observation_seconds"
    )
    if not isinstance(gate_seconds, int) or gate_seconds < 0:
        raise RunnerError("Mini resource-gate observation must be nonnegative")
    return {
        "plan": plan,
        "plan_path": resolved_plan,
        "plan_sha256": sha256_file(resolved_plan),
        "harness_path": harness_path,
        "models": model_by_name,
        "cases": case_by_id,
    }


def _summary(record: dict[str, Any], sweep_dir: Path) -> dict[str, Any]:
    waiting = next(
        (unit for unit in record["units"] if unit["status"] not in {"complete"}),
        None,
    )
    return {
        "sweep_id": record["sweep_id"],
        "sweep_dir": str(sweep_dir),
        "status": record["status"],
        "unit_count": record["unit_count"],
        "complete_unit_count": record["complete_unit_count"],
        "verified_success_count": record["verified_success_count"],
        "waiting": (
            None
            if waiting is None
            else {
                "position": waiting["position"],
                "model": waiting["model"],
                "case_id": waiting["case_id"],
                "unit_status": waiting["status"],
                "run_dir": waiting.get("run_dir"),
            }
        ),
    }


def _recount(record: dict[str, Any]) -> None:
    complete = [unit for unit in record["units"] if unit["status"] == "complete"]
    record["complete_unit_count"] = len(complete)
    record["verified_success_count"] = sum(
        bool(unit.get("outcome", {}).get("verified_success")) for unit in complete
    )


def _load_sweep(repo_root: Path, sweep_dir: Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    resolved = resolve_repo_path(repo_root, sweep_dir)
    record = load_json(resolved / "sweep.json")
    if record.get("harness_id") != "mini-v0.3":
        raise RunnerError("Sweep does not belong to Mini v0.3")
    plan = load_mini_v03_sweep_plan(repo_root, Path(record["plan"]["path"]))
    if plan["plan_sha256"] != record["plan"]["sha256"]:
        raise RunnerError("Mini v0.3 sweep plan changed after creation")
    return resolved, record, plan


def _current_unit(record: dict[str, Any]) -> dict[str, Any] | None:
    return next(
        (unit for unit in record["units"] if unit["status"] != "complete"),
        None,
    )


def _sync_run_state(repo_root: Path, unit: dict[str, Any]) -> dict[str, Any]:
    run_dir = resolve_repo_path(repo_root, Path(unit["run_dir"]))
    run = load_json(run_dir / "run.json")
    state_to_status = {
        "awaiting_model": "awaiting_model",
        "awaiting_action": "awaiting_action",
        "trajectory_complete_verification_pending": "verification_pending",
        "complete": "complete_needs_cleanup",
    }
    state = run.get("state")
    if state == "model_call_running":
        unit.setdefault("interrupted_attempts", []).append(
            {
                "run_id": unit["run_id"],
                "run_dir": unit["run_dir"],
                "preserved_at": utc_now(),
                "reason": "process_interrupted_while_mini_v03_model_call_was_running",
                "active_model_request": run.get("active_model_request"),
            }
        )
        unit["run_id"] = None
        unit["run_dir"] = None
        unit["status"] = "pending"
        unit["resource_gate"] = None
        return run
    if state not in state_to_status:
        raise RunnerError(f"Unsupported Mini v0.3 run state: {state!r}")
    unit["status"] = state_to_status[state]
    if state == "complete":
        unit["outcome"] = run.get("outcome")
        unit["trajectory"] = run.get("trajectory")
    return run


def start_mini_v03_sweep(
    repo_root: Path,
    config: MiniV03SweepConfig,
) -> dict[str, Any]:
    """Create an append-only sweep record without contacting Ollama."""
    loaded = load_mini_v03_sweep_plan(repo_root, config.plan_path)
    results = resolve_repo_path(repo_root, config.results_dir)
    results.mkdir(parents=True, exist_ok=True)
    agent_results = resolve_repo_path(repo_root, config.agent_results_dir)
    agent_results.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    sweep_id = f"mini-v03-sweep-{timestamp}-{secrets.token_hex(4)}"
    sweep_dir = results / sweep_id
    sweep_dir.mkdir(parents=False, exist_ok=False)
    plan = loaded["plan"]
    record = {
        "schema_version": "1.0.0",
        "sweep_id": sweep_id,
        "status": "running",
        "started_at": utc_now(),
        "completed_at": None,
        "track": "B",
        "harness_id": "mini-v0.3",
        "evidence_class": "measured_capability_sweep",
        "host": config.host,
        "ollama_version": plan["runtime"]["version"],
        "git_commit": git_commit(repo_root),
        "plan": {
            "plan_id": plan["plan_id"],
            "path": loaded["plan_path"].relative_to(repo_root).as_posix(),
            "sha256": loaded["plan_sha256"],
        },
        "agent_results_dir": _relative_to_repo(repo_root, agent_results),
        "unit_count": len(plan["execution_order"]),
        "complete_unit_count": 0,
        "verified_success_count": 0,
        "pause": None,
        "units": [
            {
                "position": item["position"],
                "model": item["model"],
                "deployment_id": loaded["models"][item["model"]]["deployment_id"],
                "digest": loaded["models"][item["model"]]["digest"],
                "case_id": item["case_id"],
                "case_path": loaded["cases"][item["case_id"]]["case_path"],
                "status": "pending",
                "run_id": None,
                "run_dir": None,
                "resource_gate": None,
                "interrupted_attempts": [],
                "outcome": None,
                "trajectory": None,
                "postflight_running_models": None,
            }
            for item in plan["execution_order"]
        ],
    }
    write_json(sweep_dir / "sweep.json", record)
    return advance_mini_v03_sweep(repo_root, sweep_dir)


def advance_mini_v03_sweep(repo_root: Path, sweep_dir: Path) -> dict[str, Any]:
    """Advance local preparation, action or verification to a network boundary."""
    resolved, record, loaded = _load_sweep(repo_root, sweep_dir)
    sweep_path = resolved / "sweep.json"
    while True:
        unit = _current_unit(record)
        if unit is None:
            record["status"] = "complete"
            record["completed_at"] = utc_now()
            record["pause"] = None
            _recount(record)
            write_json(sweep_path, record)
            return _summary(record, resolved)
        if unit["run_dir"]:
            _sync_run_state(repo_root, unit)
            _recount(record)
            write_json(sweep_path, record)
        if unit["status"] == "pending":
            started = start_mini_v03_run(
                repo_root,
                MiniV03StartConfig(
                    model=unit["model"],
                    case_path=Path(unit["case_path"]),
                    harness_path=loaded["harness_path"],
                    results_dir=Path(record["agent_results_dir"]),
                    host=record["host"],
                ),
            )
            unit["run_id"] = started["run_id"]
            unit["run_dir"] = _relative_to_repo(repo_root, Path(started["run_dir"]))
            unit["started_at"] = utc_now()
            unit["status"] = "awaiting_model"
            record["pause"] = None
            write_json(sweep_path, record)
            return _summary(record, resolved)
        run_dir = resolve_repo_path(repo_root, Path(unit["run_dir"]))
        if unit["status"] == "awaiting_model":
            return _summary(record, resolved)
        if unit["status"] == "awaiting_action":
            step_mini_v03_action(repo_root, run_dir)
            _sync_run_state(repo_root, unit)
            write_json(sweep_path, record)
            if unit["status"] == "awaiting_model":
                return _summary(record, resolved)
            continue
        if unit["status"] == "verification_pending":
            finalize_mini_v03_run(repo_root, run_dir)
            _sync_run_state(repo_root, unit)
            _recount(record)
            write_json(sweep_path, record)
            continue
        if unit["status"] == "complete_needs_cleanup":
            return _summary(record, resolved)
        raise RunnerError(f"Cannot advance Mini unit state {unit['status']!r}")


def _validate_deployment(
    client: OllamaClient,
    *,
    model: str,
    digest: str,
    expected_version: str,
) -> None:
    version = client.version().get("version")
    if version != expected_version:
        raise RunnerError(
            f"Mini v0.3 sweep requires Ollama {expected_version}, found {version}"
        )
    observed = find_model(client.list_models(), model)
    if observed.get("digest") != digest:
        raise RunnerError(
            f"Ollama digest drift for {model}: expected {digest}, "
            f"found {observed.get('digest')}"
        )


def _empty_gate(
    client: OllamaClient,
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


def call_mini_v03_sweep_model(
    repo_root: Path,
    sweep_dir: Path,
    *,
    client: OllamaClient | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Cross the Ollama-only boundary for exactly one pending model turn."""
    resolved, record, loaded = _load_sweep(repo_root, sweep_dir)
    unit = _current_unit(record)
    if unit is None or unit.get("status") != "awaiting_model":
        raise RunnerError("Mini v0.3 sweep is not awaiting a model call")
    run_dir = resolve_repo_path(repo_root, Path(unit["run_dir"]))
    run = _sync_run_state(repo_root, unit)
    if unit["status"] != "awaiting_model":
        write_json(resolved / "sweep.json", record)
        raise RunnerError("Mini run state changed before model call")
    ollama = client or OllamaClient(record["host"])
    _validate_deployment(
        ollama,
        model=unit["model"],
        digest=unit["digest"],
        expected_version=record["ollama_version"],
    )
    requests = run["trajectory"]["model_requests"]
    if requests == 0:
        try:
            unit["resource_gate"] = _empty_gate(
                ollama,
                loaded["plan"]["resource_gate"]["empty_state_observation_seconds"],
                sleep,
            )
        except ResourceGatePause as exc:
            record["status"] = "paused_resource_gate"
            record["pause"] = {
                "at": utc_now(),
                "position": unit["position"],
                "reason": str(exc),
            }
            write_json(resolved / "sweep.json", record)
            raise
    else:
        running = running_model_names(ollama.list_running_models())
        unexpected = sorted(name for name in running if name != unit["model"])
        if unexpected:
            record["status"] = "paused_resource_gate"
            record["pause"] = {
                "at": utc_now(),
                "position": unit["position"],
                "reason": "Unrelated Ollama model appeared during Mini trajectory: "
                + ", ".join(unexpected),
            }
            write_json(resolved / "sweep.json", record)
            raise ResourceGatePause(record["pause"]["reason"])
    record["status"] = "running"
    record["pause"] = None
    write_json(resolved / "sweep.json", record)
    call_mini_v03_model(repo_root, run_dir)
    _sync_run_state(repo_root, unit)
    write_json(resolved / "sweep.json", record)
    return _summary(record, resolved)


def cleanup_mini_v03_sweep_unit(
    repo_root: Path,
    sweep_dir: Path,
    *,
    client: OllamaClient | None = None,
) -> dict[str, Any]:
    """Unload one terminal unit before another deployment may start."""
    resolved, record, _loaded = _load_sweep(repo_root, sweep_dir)
    unit = _current_unit(record)
    if unit is None or unit.get("status") != "complete_needs_cleanup":
        raise RunnerError("Mini v0.3 sweep has no completed unit awaiting cleanup")
    ollama = client or OllamaClient(record["host"])
    ollama.unload_model(unit["model"])
    running = running_model_names(ollama.list_running_models())
    unit["postflight_running_models"] = running
    if running:
        record["status"] = "paused_resource_gate"
        record["pause"] = {
            "at": utc_now(),
            "position": unit["position"],
            "reason": "Ollama not empty after Mini unit cleanup: " + ", ".join(running),
        }
        write_json(resolved / "sweep.json", record)
        raise ResourceGatePause(record["pause"]["reason"])
    unit["status"] = "complete"
    unit["completed_at"] = utc_now()
    _recount(record)
    record["status"] = "running"
    record["pause"] = None
    write_json(resolved / "sweep.json", record)
    return advance_mini_v03_sweep(repo_root, resolved)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser("start", help="Create a frozen Mini sweep")
    start.add_argument("--plan", type=Path, default=DEFAULT_MINI_V03_SWEEP_PLAN)
    start.add_argument("--host", default="http://127.0.0.1:11434")
    start.add_argument(
        "--results-dir", type=Path, default=Path("results/agentic-sweeps")
    )
    start.add_argument(
        "--agent-results-dir", type=Path, default=Path("results/agentic-runs")
    )
    for name, help_text in (
        ("advance", "Execute local action or verification work"),
        ("model-call", "Execute one Ollama-only model turn"),
        ("cleanup", "Unload one terminal unit"),
    ):
        child = subparsers.add_parser(name, help=help_text)
        child.add_argument("--sweep-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    try:
        if args.command == "start":
            result = start_mini_v03_sweep(
                repo_root,
                MiniV03SweepConfig(
                    plan_path=args.plan,
                    results_dir=args.results_dir,
                    agent_results_dir=args.agent_results_dir,
                    host=args.host,
                ),
            )
        elif args.command == "advance":
            result = advance_mini_v03_sweep(repo_root, args.sweep_dir)
        elif args.command == "model-call":
            result = call_mini_v03_sweep_model(repo_root, args.sweep_dir)
        else:
            result = cleanup_mini_v03_sweep_unit(repo_root, args.sweep_dir)
    except (OSError, RunnerError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
