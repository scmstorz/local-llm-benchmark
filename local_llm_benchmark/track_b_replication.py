"""Run a frozen targeted Track B replication across Pi and Mini v0.3."""

from __future__ import annotations

import argparse
import json
import secrets
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from .macos_sandbox_v03 import validate_pi_v03_seatbelt
from .mini_v03_adapter import (
    MiniV03StartConfig,
    call_mini_v03_model,
    finalize_mini_v03_run,
    load_mini_v03_harness,
    start_mini_v03_run,
    step_mini_v03_action,
)
from .ollama import OllamaClient, OllamaError
from .pi_v03_adapter import (
    PiV03PrepareConfig,
    execute_pi_v03_agent_run,
    finalize_pi_v03_agent_run,
    load_pi_v03_harness,
    prepare_pi_v03_agent_run,
)
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


DEFAULT_PLAN_PATH = Path(
    "tasks/coding/track-b/targeted-system-replication-v0.1.json"
)


@dataclass(frozen=True)
class ReplicationConfig:
    """Inputs for one targeted Track B replication study."""

    plan_path: Path = DEFAULT_PLAN_PATH
    results_dir: Path = Path("results/agentic-studies")
    agent_results_dir: Path = Path("results/agentic-runs")
    host: str = "http://127.0.0.1:11434"


def _relative(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as exc:
        raise RunnerError(f"Replication artifact escapes repository: {path}") from exc


def _load_harnesses(repo_root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    harnesses = plan.get("harnesses")
    if not isinstance(harnesses, list):
        raise RunnerError("Replication plan must define harnesses")
    by_id: dict[str, Any] = {}
    loaders = {
        "pi-v0.3": load_pi_v03_harness,
        "mini-v0.3": load_mini_v03_harness,
    }
    for item in harnesses:
        if not isinstance(item, dict):
            raise RunnerError("Replication harness entries must be objects")
        harness_id = item.get("harness_id")
        path_value = item.get("harness_path")
        if harness_id not in loaders or not isinstance(path_value, str):
            raise RunnerError("Replication plan contains an unsupported harness")
        if harness_id in by_id:
            raise RunnerError(f"Duplicate replication harness: {harness_id}")
        loaded = loaders[harness_id](repo_root, Path(path_value))
        if loaded["harness"]["harness_id"] != harness_id:
            raise RunnerError(f"Replication harness identity mismatch: {harness_id}")
        by_id[harness_id] = {
            "path": Path(path_value),
            "loaded": loaded,
        }
    if set(by_id) != set(loaders):
        raise RunnerError("Replication plan must include Pi v0.3 and Mini v0.3")
    return by_id


def _validate_frozen_artifacts(repo_root: Path, plan: dict[str, Any]) -> None:
    artifacts = plan.get("frozen_inputs", {}).get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise RunnerError("Replication plan must freeze input artifacts")
    for position, item in enumerate(artifacts, start=1):
        if not isinstance(item, dict):
            raise RunnerError(f"Invalid frozen artifact at position {position}")
        path_value = item.get("path")
        digest = item.get("sha256")
        if not isinstance(path_value, str) or not isinstance(digest, str):
            raise RunnerError(f"Incomplete frozen artifact at position {position}")
        path = resolve_repo_path(repo_root, Path(path_value))
        if not path.is_file() or sha256_file(path) != digest:
            raise RunnerError(f"Replication frozen artifact drift: {path_value}")


def _load_baselines(repo_root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    baselines = plan.get("baseline_reports")
    if not isinstance(baselines, list) or len(baselines) != 2:
        raise RunnerError("Replication plan must freeze two baseline reports")
    expected = {
        "pi-v0.3": "track-b-pi-capability-sweep-v0.3",
        "mini-v0.3": "track-b-mini-capability-sweep-v0.3",
    }
    loaded: dict[str, Any] = {}
    for item in baselines:
        harness_id = item.get("harness_id") if isinstance(item, dict) else None
        path_value = item.get("path") if isinstance(item, dict) else None
        digest = item.get("sha256") if isinstance(item, dict) else None
        if harness_id not in expected or not isinstance(path_value, str):
            raise RunnerError("Invalid replication baseline identity")
        path = resolve_repo_path(repo_root, Path(path_value))
        if not path.is_file() or sha256_file(path) != digest:
            raise RunnerError(f"Replication baseline drift: {path_value}")
        report = load_json(path)
        if report.get("report_id") != expected[harness_id]:
            raise RunnerError(f"Unexpected baseline report for {harness_id}")
        loaded[harness_id] = {"path": path, "report": report}
    if set(loaded) != set(expected):
        raise RunnerError("Replication plan baseline harness coverage is incomplete")
    return loaded


def _validate_design(
    plan: dict[str, Any], baselines: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    deployments = plan.get("deployments")
    cases = plan.get("cases")
    selected = plan.get("selected_cells")
    order = plan.get("execution_order")
    if not all(isinstance(value, list) for value in (deployments, cases, selected, order)):
        raise RunnerError("Replication design lists are incomplete")
    model_by_name = {
        item["name"]: item
        for item in deployments
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    case_by_id = {
        item["case_id"]: item
        for item in cases
        if isinstance(item, dict) and isinstance(item.get("case_id"), str)
    }
    if len(model_by_name) != 2 or len(case_by_id) != 2 or len(selected) != 2:
        raise RunnerError("Targeted replication v0.1 requires two models and two cases")
    for model in model_by_name.values():
        if not isinstance(model.get("digest"), str) or len(model["digest"]) != 64:
            raise RunnerError("Replication deployment digest is incomplete")
        if not isinstance(model.get("deployment_id"), str):
            raise RunnerError("Replication deployment identity is incomplete")
    cells: set[tuple[str, str]] = set()
    for item in selected:
        key = (item.get("model"), item.get("case_id"))
        if key[0] not in model_by_name or key[1] not in case_by_id or key in cells:
            raise RunnerError(f"Invalid selected replication cell: {key}")
        cells.add(key)
    if len({model for model, _case in cells}) != 2 or len(
        {case for _model, case in cells}
    ) != 2:
        raise RunnerError("Selected cells must be a targeted diagonal, not a Cartesian sweep")

    replication = plan.get("replication", {})
    indices = replication.get("fresh_replication_indices")
    if indices != [2, 3] or replication.get("fresh_runs_per_system_cell") != 2:
        raise RunnerError("Targeted replication v0.1 requires fresh indices 2 and 3")
    expected = {
        (harness_id, model, case_id, index)
        for harness_id in ("pi-v0.3", "mini-v0.3")
        for model, case_id in cells
        for index in indices
    }
    observed = set()
    for position, item in enumerate(order, start=1):
        if not isinstance(item, dict) or item.get("position") != position:
            raise RunnerError("Replication execution positions must be contiguous")
        key = (
            item.get("harness_id"),
            item.get("model"),
            item.get("case_id"),
            item.get("replication_index"),
        )
        if key not in expected or key in observed:
            raise RunnerError(f"Invalid or duplicate replication unit: {key}")
        observed.add(key)
    if observed != expected:
        raise RunnerError("Replication execution order does not cover the frozen design")

    baseline_outcomes: dict[tuple[str, str, str], bool] = {}
    for harness_id, baseline in baselines.items():
        for unit in baseline["report"]["units"]:
            key = (harness_id, unit["model"], unit["case_id"])
            if (unit["model"], unit["case_id"]) in cells:
                baseline_outcomes[key] = bool(unit["verified_success"])
    for model, case_id in cells:
        pi = baseline_outcomes.get(("pi-v0.3", model, case_id))
        mini = baseline_outcomes.get(("mini-v0.3", model, case_id))
        if pi is None or mini is None or pi == mini:
            raise RunnerError(
                f"Selected cell is not a complete baseline disagreement: {model}, {case_id}"
            )
    return model_by_name, case_by_id


def load_replication_plan(repo_root: Path, plan_path: Path) -> dict[str, Any]:
    """Load and validate one frozen targeted replication plan."""
    resolved = resolve_repo_path(repo_root, plan_path)
    plan = load_json(resolved)
    if plan.get("schema_version") != "1.0.0":
        raise RunnerError("Unsupported replication plan schema")
    if plan.get("status") != "frozen_before_execution":
        raise RunnerError("Replication plan must be frozen before execution")
    if (
        plan.get("track") != "B"
        or plan.get("study_mode") != "targeted_outcome_replication"
        or plan.get("evidence_class") != "post_hoc_targeted_replication"
    ):
        raise RunnerError("Unexpected targeted replication identity")
    runtime = plan.get("runtime")
    if (
        not isinstance(runtime, dict)
        or runtime.get("name") != "ollama"
        or not isinstance(runtime.get("version"), str)
    ):
        raise RunnerError("Replication plan must freeze an Ollama version")
    harnesses = _load_harnesses(repo_root, plan)
    _validate_frozen_artifacts(repo_root, plan)
    baselines = _load_baselines(repo_root, plan)
    models, cases = _validate_design(plan, baselines)
    rules = plan.get("comparison_rules", {})
    if (
        rules.get("automatic_retries") != 0
        or rules.get("adaptive_repetitions") is not False
        or rules.get("reliability_probability_claims") is not False
        or rules.get("tail_performance_claims") is not False
    ):
        raise RunnerError("Replication plan comparison rules are not conservative")
    gate = plan.get("resource_gate", {}).get("empty_state_observation_seconds")
    if not isinstance(gate, int) or gate < 0:
        raise RunnerError("Replication resource gate is invalid")
    return {
        "plan": plan,
        "plan_path": resolved,
        "plan_sha256": sha256_file(resolved),
        "harnesses": harnesses,
        "baselines": baselines,
        "models": models,
        "cases": cases,
    }


def _summary(record: dict[str, Any], study_dir: Path) -> dict[str, Any]:
    current = next(
        (unit for unit in record["units"] if unit["status"] != "complete"), None
    )
    return {
        "study_id": record["study_id"],
        "study_dir": str(study_dir),
        "status": record["status"],
        "unit_count": record["unit_count"],
        "complete_unit_count": record["complete_unit_count"],
        "verified_success_count": record["verified_success_count"],
        "waiting": None
        if current is None
        else {
            key: current.get(key)
            for key in (
                "position",
                "harness_id",
                "model",
                "case_id",
                "replication_index",
                "status",
                "run_dir",
            )
        },
    }


def _recount(record: dict[str, Any]) -> None:
    complete = [unit for unit in record["units"] if unit["status"] == "complete"]
    record["complete_unit_count"] = len(complete)
    record["verified_success_count"] = sum(
        bool(unit.get("outcome", {}).get("verified_success")) for unit in complete
    )


def _current(record: dict[str, Any]) -> dict[str, Any] | None:
    return next((unit for unit in record["units"] if unit["status"] != "complete"), None)


def _load_study(
    repo_root: Path, study_dir: Path
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    resolved = resolve_repo_path(repo_root, study_dir)
    record = load_json(resolved / "study.json")
    if record.get("study_mode") != "targeted_outcome_replication":
        raise RunnerError("Study is not a targeted Track B replication")
    loaded = load_replication_plan(repo_root, Path(record["plan"]["path"]))
    if loaded["plan_sha256"] != record["plan"]["sha256"]:
        raise RunnerError("Replication plan changed after study creation")
    return resolved, record, loaded


def _sync_unit(repo_root: Path, unit: dict[str, Any]) -> dict[str, Any] | None:
    if not unit.get("run_dir"):
        return None
    run_dir = resolve_repo_path(repo_root, Path(unit["run_dir"]))
    run = load_json(run_dir / "run.json")
    state = run.get("state")
    if unit["harness_id"] == "pi-v0.3":
        if state == "running":
            unit.setdefault("interrupted_attempts", []).append(
                {
                    "run_id": unit["run_id"],
                    "run_dir": unit["run_dir"],
                    "preserved_at": utc_now(),
                    "reason": "process_interrupted_while_pi_v03_run_was_running",
                }
            )
            unit.update(
                {
                    "run_id": None,
                    "run_dir": None,
                    "status": "pending",
                    "resource_gate": None,
                }
            )
            return run
        acceptance_path = run_dir / "pi-sandbox-acceptance.json"
        accepted = (
            acceptance_path.is_file()
            and load_json(acceptance_path).get("passed") is True
        )
        states = {
            "prepared_not_executed": "awaiting_live" if accepted else "prepared",
            "execution_complete_verification_pending": "verification_pending",
            "complete": "complete_needs_cleanup",
        }
    else:
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
            unit.update(
                {
                    "run_id": None,
                    "run_dir": None,
                    "status": "pending",
                    "resource_gate": None,
                }
            )
            return run
        states = {
            "awaiting_model": "awaiting_live",
            "awaiting_action": "awaiting_action",
            "trajectory_complete_verification_pending": "verification_pending",
            "complete": "complete_needs_cleanup",
        }
    if state not in states:
        raise RunnerError(f"Unsupported {unit['harness_id']} run state: {state!r}")
    unit["status"] = states[state]
    if state == "complete":
        unit["outcome"] = run.get("outcome")
        unit["trajectory"] = run.get("trajectory")
    return run


def _prepare_unit(
    repo_root: Path,
    record: dict[str, Any],
    loaded: dict[str, Any],
    unit: dict[str, Any],
) -> None:
    common = {
        "model": unit["model"],
        "case_path": Path(unit["case_path"]),
        "results_dir": Path(record["agent_results_dir"]),
        "host": record["host"],
    }
    if unit["harness_id"] == "pi-v0.3":
        prepared = prepare_pi_v03_agent_run(
            repo_root,
            PiV03PrepareConfig(
                **common,
                harness_path=loaded["harnesses"]["pi-v0.3"]["path"],
            ),
        )
        status = "prepared"
    else:
        prepared = start_mini_v03_run(
            repo_root,
            MiniV03StartConfig(
                **common,
                harness_path=loaded["harnesses"]["mini-v0.3"]["path"],
            ),
        )
        status = "awaiting_live"
    unit["run_id"] = prepared["run_id"]
    unit["run_dir"] = _relative(repo_root, Path(prepared["run_dir"]))
    unit["started_at"] = utc_now()
    unit["status"] = status


def advance_replication(repo_root: Path, study_dir: Path) -> dict[str, Any]:
    """Advance preparation, sandbox checks, actions or final verification."""
    resolved, record, loaded = _load_study(repo_root, study_dir)
    path = resolved / "study.json"
    while True:
        unit = _current(record)
        if unit is None:
            record["status"] = "complete"
            record["completed_at"] = utc_now()
            record["pause"] = None
            _recount(record)
            write_json(path, record)
            return _summary(record, resolved)
        if unit.get("run_dir"):
            _sync_unit(repo_root, unit)
            _recount(record)
            write_json(path, record)
        if unit["status"] == "pending":
            _prepare_unit(repo_root, record, loaded, unit)
            record["status"] = "running"
            record["pause"] = None
            write_json(path, record)
            continue
        run_dir = resolve_repo_path(repo_root, Path(unit["run_dir"]))
        if unit["status"] == "prepared":
            acceptance = validate_pi_v03_seatbelt(run_dir)
            unit["sandbox_acceptance"] = {
                key: acceptance[key]
                for key in (
                    "passed",
                    "validated_at",
                    "profile_sha256",
                    "hidden_verifier_sha256",
                )
            }
            unit["status"] = "awaiting_live"
            write_json(path, record)
            return _summary(record, resolved)
        if unit["status"] == "awaiting_live":
            return _summary(record, resolved)
        if unit["status"] == "awaiting_action":
            if unit["harness_id"] != "mini-v0.3":
                raise RunnerError("Only Mini may await a controller action")
            step_mini_v03_action(repo_root, run_dir)
            _sync_unit(repo_root, unit)
            write_json(path, record)
            if unit["status"] == "awaiting_live":
                return _summary(record, resolved)
            continue
        if unit["status"] == "verification_pending":
            if unit["harness_id"] == "pi-v0.3":
                finalize_pi_v03_agent_run(repo_root, run_dir)
            else:
                finalize_mini_v03_run(repo_root, run_dir)
            _sync_unit(repo_root, unit)
            _recount(record)
            write_json(path, record)
            continue
        if unit["status"] == "complete_needs_cleanup":
            return _summary(record, resolved)
        raise RunnerError(f"Cannot advance replication state {unit['status']!r}")


def _empty_gate(
    client: OllamaClient,
    seconds: int,
    sleep: Callable[[float], None],
) -> dict[str, Any]:
    first = running_model_names(client.list_running_models())
    if first:
        raise ResourceGatePause(
            "Ollama resource gate found loaded models before observation: "
            + ", ".join(first)
        )
    observed_at = utc_now()
    if seconds:
        sleep(seconds)
    second = running_model_names(client.list_running_models())
    if second:
        raise ResourceGatePause(
            "Ollama resource gate observed model activity: " + ", ".join(second)
        )
    return {
        "observed_at": observed_at,
        "observation_seconds": seconds,
        "first_running_models": first,
        "second_running_models": second,
        "passed": True,
    }


def _validate_live_identity(
    client: OllamaClient, record: dict[str, Any], unit: dict[str, Any]
) -> None:
    version = client.version().get("version")
    if version != record["ollama_version"]:
        raise RunnerError(
            f"Replication requires Ollama {record['ollama_version']}, found {version}"
        )
    observed = find_model(client.list_models(), unit["model"])
    if observed.get("digest") != unit["digest"]:
        raise RunnerError(f"Ollama digest drift for {unit['model']}")


def run_replication_live_step(
    repo_root: Path,
    study_dir: Path,
    *,
    client: OllamaClient | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Cross the Ollama boundary for one Mini turn or one complete Pi trajectory."""
    resolved, record, loaded = _load_study(repo_root, study_dir)
    path = resolved / "study.json"
    unit = _current(record)
    if unit is None or unit.get("status") != "awaiting_live":
        raise RunnerError("Replication is not awaiting live model execution")
    run_dir = resolve_repo_path(repo_root, Path(unit["run_dir"]))
    run = _sync_unit(repo_root, unit)
    if unit["status"] != "awaiting_live" or run is None:
        write_json(path, record)
        raise RunnerError("Replication run state changed before live execution")
    ollama = client or OllamaClient(record["host"])
    _validate_live_identity(ollama, record, unit)
    first_request = unit["harness_id"] == "pi-v0.3" or (
        run.get("trajectory", {}).get("model_requests", 0) == 0
    )
    try:
        if first_request:
            unit["resource_gate"] = _empty_gate(
                ollama,
                loaded["plan"]["resource_gate"]["empty_state_observation_seconds"],
                sleep,
            )
        else:
            running = running_model_names(ollama.list_running_models())
            unexpected = sorted(name for name in running if name != unit["model"])
            if unexpected:
                raise ResourceGatePause(
                    "Unrelated Ollama model appeared during trajectory: "
                    + ", ".join(unexpected)
                )
    except ResourceGatePause as exc:
        record["status"] = "paused_resource_gate"
        record["pause"] = {
            "at": utc_now(),
            "position": unit["position"],
            "reason": str(exc),
        }
        write_json(path, record)
        raise

    record["status"] = "running"
    record["pause"] = None
    unit["status"] = "live_execution_running"
    write_json(path, record)
    if unit["harness_id"] == "pi-v0.3":
        execute_pi_v03_agent_run(repo_root, run_dir)
    else:
        call_mini_v03_model(repo_root, run_dir)
    _sync_unit(repo_root, unit)
    write_json(path, record)
    return _summary(record, resolved)


def cleanup_replication_unit(
    repo_root: Path,
    study_dir: Path,
    *,
    client: OllamaClient | None = None,
) -> dict[str, Any]:
    """Unload a terminal unit and prepare the next without inference."""
    resolved, record, _loaded = _load_study(repo_root, study_dir)
    path = resolved / "study.json"
    unit = _current(record)
    if unit is None or unit.get("status") != "complete_needs_cleanup":
        raise RunnerError("Replication has no completed unit awaiting cleanup")
    ollama = client or OllamaClient(record["host"])
    ollama.unload_model(unit["model"])
    running = running_model_names(ollama.list_running_models())
    unit["postflight_running_models"] = running
    if running:
        record["status"] = "paused_resource_gate"
        record["pause"] = {
            "at": utc_now(),
            "position": unit["position"],
            "reason": "Ollama not empty after replication cleanup: "
            + ", ".join(running),
        }
        write_json(path, record)
        raise ResourceGatePause(record["pause"]["reason"])
    unit["status"] = "complete"
    unit["completed_at"] = utc_now()
    _recount(record)
    record["status"] = "running"
    record["pause"] = None
    write_json(path, record)
    return advance_replication(repo_root, resolved)


def start_replication(
    repo_root: Path,
    config: ReplicationConfig,
    *,
    client: OllamaClient | None = None,
) -> dict[str, Any]:
    """Create a targeted replication record and prepare its first live boundary."""
    loaded = load_replication_plan(repo_root, config.plan_path)
    ollama = client or OllamaClient(config.host)
    version = ollama.version().get("version")
    if version != loaded["plan"]["runtime"]["version"]:
        raise RunnerError(
            f"Replication requires Ollama {loaded['plan']['runtime']['version']}, "
            f"found {version}"
        )
    observed_models = {}
    for name, frozen in loaded["models"].items():
        observed = find_model(ollama.list_models(), name)
        if observed.get("digest") != frozen["digest"]:
            raise RunnerError(f"Ollama digest drift for {name}")
        observed_models[name] = observed

    results = resolve_repo_path(repo_root, config.results_dir)
    results.mkdir(parents=True, exist_ok=True)
    agent_results = resolve_repo_path(repo_root, config.agent_results_dir)
    agent_results.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    study_id = f"track-b-replication-{timestamp}-{secrets.token_hex(4)}"
    study_dir = results / study_id
    study_dir.mkdir(parents=False, exist_ok=False)
    plan = loaded["plan"]
    record = {
        "schema_version": "1.0.0",
        "study_id": study_id,
        "status": "running",
        "started_at": utc_now(),
        "completed_at": None,
        "track": "B",
        "study_mode": plan["study_mode"],
        "evidence_class": plan["evidence_class"],
        "host": config.host,
        "ollama_version": version,
        "git_commit": git_commit(repo_root),
        "plan": {
            "plan_id": plan["plan_id"],
            "path": _relative(repo_root, loaded["plan_path"]),
            "sha256": loaded["plan_sha256"],
        },
        "agent_results_dir": _relative(repo_root, agent_results),
        "unit_count": len(plan["execution_order"]),
        "complete_unit_count": 0,
        "verified_success_count": 0,
        "pause": None,
        "observed_models": {
            name: {"digest": item.get("digest"), "size": item.get("size")}
            for name, item in observed_models.items()
        },
        "units": [
            {
                **item,
                "deployment_id": loaded["models"][item["model"]]["deployment_id"],
                "digest": loaded["models"][item["model"]]["digest"],
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
    write_json(study_dir / "study.json", record)
    return advance_replication(repo_root, study_dir)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser("start", help="Start the frozen replication")
    start.add_argument("--plan", type=Path, default=DEFAULT_PLAN_PATH)
    start.add_argument("--host", default="http://127.0.0.1:11434")
    start.add_argument(
        "--results-dir", type=Path, default=Path("results/agentic-studies")
    )
    start.add_argument(
        "--agent-results-dir", type=Path, default=Path("results/agentic-runs")
    )
    for name, help_text in (
        ("advance", "Run local preparation, action or final verification"),
        ("live", "Run one model boundary"),
        ("cleanup", "Unload one terminal unit"),
    ):
        child = subparsers.add_parser(name, help=help_text)
        child.add_argument("--study-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    try:
        if args.command == "start":
            result = start_replication(
                repo_root,
                ReplicationConfig(
                    plan_path=args.plan,
                    results_dir=args.results_dir,
                    agent_results_dir=args.agent_results_dir,
                    host=args.host,
                ),
            )
        elif args.command == "advance":
            result = advance_replication(repo_root, args.study_dir)
        elif args.command == "live":
            result = run_replication_live_step(repo_root, args.study_dir)
        else:
            result = cleanup_replication_unit(repo_root, args.study_dir)
    except (OSError, RunnerError, OllamaError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
