"""Checkpointed controller for repeated single-turn quality studies."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import time
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .log_incident_smokes import ResourceGatePause, run_resource_gate
from .ollama import OllamaClient
from .runner import (
    RunConfig,
    RunnerError,
    create_batch_judge_bundle,
    load_case,
    load_json,
    resolve_repo_path,
    running_model_names,
    run_once,
    sha256_file,
    utc_now,
    write_json,
)


DEFAULT_PLAN_PATH = Path("tasks/studies/quality-stochasticity-v0.1.json")
DEFAULT_STUDIES_DIR = Path("results/quality-stochasticity/studies")
DEFAULT_RUNS_DIR = Path("results/runs")
TERMINAL_UNIT_STATUSES = {"complete", "failed"}


@dataclass(frozen=True)
class QualityStudyConfig:
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
        raise RunnerError("Quality study plan must use schema_version 1.0.0")
    if plan.get("status") != "frozen_before_execution":
        raise RunnerError("Quality study plan must be frozen before execution")
    _required_string(plan, "plan_id", "Quality study plan")

    repetitions = plan.get("methodology", {}).get("measured_runs_per_condition")
    if not isinstance(repetitions, int) or repetitions < 2:
        raise RunnerError("Quality study requires at least two runs per condition")
    settings = plan.get("methodology", {}).get("generation_settings")
    if not isinstance(settings, dict):
        raise RunnerError("Quality study must define generation_settings")
    for key in ("temperature", "seed", "think", "num_predict", "keep_alive"):
        if key not in settings:
            raise RunnerError(f"Quality study generation_settings must define {key}")
    timeout = plan.get("methodology", {}).get("timeout_seconds")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        raise RunnerError("Quality study timeout_seconds must be positive")

    deployments = plan.get("deployments")
    cases = plan.get("cases")
    units = plan.get("execution_order")
    if not isinstance(deployments, list) or len(deployments) != 2:
        raise RunnerError("Quality study v0.1 requires exactly two deployments")
    if not isinstance(cases, list) or len(cases) < 1:
        raise RunnerError("Quality study must define at least one case")
    if not isinstance(units, list) or not units:
        raise RunnerError("Quality study must define an execution_order")

    deployment_aliases: set[str] = set()
    for deployment in deployments:
        if not isinstance(deployment, dict):
            raise RunnerError("Every quality study deployment must be an object")
        alias = _required_string(deployment, "alias", "Quality study deployment")
        if alias in deployment_aliases:
            raise RunnerError(f"Duplicate deployment alias: {alias}")
        deployment_aliases.add(alias)
        _required_string(deployment, "name", f"Deployment {alias}")
        digest = _required_string(deployment, "digest", f"Deployment {alias}")
        if len(digest) != 64:
            raise RunnerError(f"Deployment {alias} has an invalid digest")

    case_aliases: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise RunnerError("Every quality study case must be an object")
        alias = _required_string(case, "alias", "Quality study case")
        if alias in case_aliases:
            raise RunnerError(f"Duplicate case alias: {alias}")
        case_aliases.add(alias)
        _required_string(case, "case_id", f"Case {alias}")
        _required_string(case, "case_path", f"Case {alias}")
        num_ctx = case.get("num_ctx")
        if not isinstance(num_ctx, int) or isinstance(num_ctx, bool) or num_ctx < 1:
            raise RunnerError(f"Case {alias} has an invalid num_ctx")

    expected_conditions = {
        (deployment_alias, case_alias, repetition)
        for deployment_alias in deployment_aliases
        for case_alias in case_aliases
        for repetition in range(1, repetitions + 1)
    }
    observed_conditions: set[tuple[str, str, int]] = set()
    expected_positions = list(range(1, len(units) + 1))
    observed_positions: list[int] = []
    unit_ids: set[str] = set()
    for unit in units:
        if not isinstance(unit, dict):
            raise RunnerError("Every quality study unit must be an object")
        unit_id = _required_string(unit, "unit_id", "Quality study unit")
        if unit_id in unit_ids:
            raise RunnerError(f"Duplicate quality study unit_id: {unit_id}")
        unit_ids.add(unit_id)
        position = unit.get("position")
        repetition = unit.get("repetition")
        deployment_alias = unit.get("deployment_alias")
        case_alias = unit.get("case_alias")
        observed_positions.append(position)
        condition = (deployment_alias, case_alias, repetition)
        if condition in observed_conditions:
            raise RunnerError(f"Duplicate quality study condition: {condition}")
        observed_conditions.add(condition)
    if observed_positions != expected_positions:
        raise RunnerError("Quality study positions must be contiguous from one")
    if observed_conditions != expected_conditions:
        raise RunnerError("Quality study execution_order is not the full product")

    gate = plan.get("resource_gate")
    if not isinstance(gate, dict):
        raise RunnerError("Quality study must define a resource_gate")
    if gate.get("loaded_models_must_be_empty_before_each_unit") is not True:
        raise RunnerError("Quality study requires an empty Ollama state per unit")
    if gate.get("model_unloaded_after_each_unit") is not True:
        raise RunnerError("Quality study requires model unload after every unit")
    if not isinstance(gate.get("blocking_process_rules"), list):
        raise RunnerError("Quality study must define blocking_process_rules")
    blinding = plan.get("blinding")
    if not isinstance(blinding, dict):
        raise RunnerError("Quality study must define blinding settings")
    _required_string(blinding, "bundle_seed", "Quality study blinding")
    authorization = plan.get("authorization")
    if not isinstance(authorization, dict):
        raise RunnerError("Quality study must define authorization")
    if authorization.get("live_execution_authorized") is not True:
        raise RunnerError("Quality study live execution is not authorized")

    frozen_artifacts = plan.get("frozen_artifacts")
    if not isinstance(frozen_artifacts, list) or not frozen_artifacts:
        raise RunnerError("Quality study must freeze at least one artifact")
    for artifact in frozen_artifacts:
        if not isinstance(artifact, dict):
            raise RunnerError("Every frozen quality artifact must be an object")
        path_value = _required_string(artifact, "path", "Frozen artifact")
        digest = _required_string(artifact, "sha256", f"Frozen artifact {path_value}")
        if len(digest) != 64:
            raise RunnerError(f"Frozen artifact has an invalid digest: {path_value}")


def load_quality_plan(
    repo_root: Path,
    plan_path: Path = DEFAULT_PLAN_PATH,
    *,
    require_private_inputs: bool = True,
) -> dict[str, Any]:
    resolved = resolve_repo_path(repo_root, plan_path)
    plan = load_json(resolved)
    _validate_plan_structure(plan)

    for artifact in plan.get("frozen_artifacts", []):
        path_value = _required_string(artifact, "path", "Frozen artifact")
        expected = _required_string(artifact, "sha256", f"Frozen artifact {path_value}")
        path = resolve_repo_path(repo_root, path_value)
        visibility = artifact.get("visibility", "public")
        if not path.is_file():
            if visibility == "private" and not require_private_inputs:
                continue
            raise RunnerError(f"Frozen quality study artifact is missing: {path_value}")
        if sha256_file(path) != expected:
            raise RunnerError(f"Frozen quality study artifact changed: {path_value}")

    loaded_cases: dict[str, dict[str, Any]] = {}
    if require_private_inputs:
        for case_record in plan["cases"]:
            loaded = load_case(repo_root, Path(case_record["case_path"]))
            if loaded["case"].get("case_id") != case_record["case_id"]:
                raise RunnerError(f"Quality study case identity changed: {case_record['alias']}")
            loaded_cases[case_record["alias"]] = loaded
    return {
        "plan": plan,
        "path": resolved,
        "sha256": sha256_file(resolved),
        "loaded_cases": loaded_cases,
    }


def _summary(record: dict[str, Any], study_dir: Path) -> dict[str, Any]:
    next_unit = next(
        (unit for unit in record["units"] if unit["status"] not in TERMINAL_UNIT_STATUSES),
        None,
    )
    waiting = None
    if next_unit is not None:
        waiting = {
            key: next_unit[key]
            for key in (
                "unit_id",
                "position",
                "deployment_alias",
                "case_alias",
                "repetition",
                "status",
            )
        }
    return {
        "study_id": record["study_id"],
        "study_dir": str(study_dir),
        "status": record["status"],
        "complete_units": sum(unit["status"] == "complete" for unit in record["units"]),
        "failed_units": sum(unit["status"] == "failed" for unit in record["units"]),
        "total_units": len(record["units"]),
        "waiting": waiting,
        "judge_bundles": record.get("judge_bundles"),
    }


def start_quality_study(repo_root: Path, config: QualityStudyConfig) -> dict[str, Any]:
    loaded = load_quality_plan(repo_root, config.plan_path)
    plan = loaded["plan"]
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    study_id = f"quality-study-{timestamp}-{secrets.token_hex(4)}"
    studies_dir = resolve_repo_path(repo_root, config.studies_dir)
    study_dir = studies_dir / study_id
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
        "units": [
            {
                **deepcopy(unit),
                "status": "pending",
                "started_at": None,
                "completed_at": None,
                "resource_gate": None,
                "preload_wall_seconds": None,
                "run": None,
                "failure": None,
                "running_models_after_cleanup": None,
                "interrupted_attempts": [],
            }
            for unit in plan["execution_order"]
        ],
        "pause_history": [],
        "judge_bundles": None,
        "artifacts": {"private_map": "private-map.json"},
    }
    write_json(study_dir / "study.json", record)
    write_json(
        study_dir / "private-map.json",
        {"schema_version": "1.0.0", "private_model_mapping": {}},
    )
    return _summary(record, study_dir)


def _load_study(repo_root: Path, study_dir: Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    resolved = resolve_repo_path(repo_root, study_dir)
    record = load_json(resolved / "study.json")
    plan_record = record.get("plan", {})
    loaded = load_quality_plan(repo_root, Path(_required_string(plan_record, "path", "Study plan")))
    if loaded["sha256"] != plan_record.get("sha256"):
        raise RunnerError("Quality study plan changed after study creation")
    if loaded["plan"]["plan_id"] != plan_record.get("plan_id"):
        raise RunnerError("Quality study plan identity changed")
    return resolved, record, loaded


def _deployment_by_alias(plan: dict[str, Any], alias: str) -> dict[str, Any]:
    matches = [item for item in plan["deployments"] if item["alias"] == alias]
    if len(matches) != 1:
        raise RunnerError(f"Unknown quality study deployment alias: {alias}")
    return matches[0]


def _case_by_alias(plan: dict[str, Any], alias: str) -> dict[str, Any]:
    matches = [item for item in plan["cases"] if item["alias"] == alias]
    if len(matches) != 1:
        raise RunnerError(f"Unknown quality study case alias: {alias}")
    return matches[0]


def _find_completed_orphan(
    *,
    runs_dir: Path,
    study_id: str,
    unit: dict[str, Any],
    deployment: dict[str, Any],
    case: dict[str, Any],
) -> dict[str, Any] | None:
    matches: list[dict[str, Any]] = []
    if not runs_dir.is_dir():
        return None
    for run_path in runs_dir.glob("run-*/run.json"):
        run = load_json(run_path)
        measurement = run.get("measurement", {})
        if (
            run.get("status") == "complete"
            and measurement.get("comparison_id") == study_id
            and measurement.get("phase") == "warm"
            and measurement.get("iteration") == unit["repetition"]
            and run.get("case", {}).get("case_id") == case["case_id"]
            and run.get("deployment", {}).get("model", {}).get("requested_name")
            == deployment["name"]
        ):
            matches.append(run)
    if len(matches) > 1:
        raise RunnerError(f"Multiple completed runs match interrupted unit {unit['unit_id']}")
    return matches[0] if matches else None


def _record_complete_unit(unit: dict[str, Any], run: dict[str, Any]) -> None:
    unit["status"] = "complete"
    unit["completed_at"] = utc_now()
    unit["run"] = {
        "run_id": run["run_id"],
        "candidate_id": run["candidate_id"],
        "done_reason": run.get("execution", {}).get("done_reason"),
        "checks": run.get("checks"),
        "metrics": run.get("metrics"),
    }
    unit["failure"] = None


def _reconcile_interrupted_unit(
    *,
    repo_root: Path,
    record: dict[str, Any],
    unit: dict[str, Any],
    deployment: dict[str, Any],
    case: dict[str, Any],
) -> None:
    if unit["status"] != "running":
        return
    runs_dir = resolve_repo_path(repo_root, Path(record["runs_dir"]))
    completed = _find_completed_orphan(
        runs_dir=runs_dir,
        study_id=record["study_id"],
        unit=unit,
        deployment=deployment,
        case=case,
    )
    if completed is not None:
        _record_complete_unit(unit, completed)
        return
    unit["interrupted_attempts"].append(
        {
            "started_at": unit.get("started_at"),
            "preserved_at": utc_now(),
            "classification": "controller_or_host_interruption_before_terminal_run",
            "replacement_allowed": True,
        }
    )
    unit["status"] = "pending"
    unit["started_at"] = None
    unit["resource_gate"] = None
    unit["preload_wall_seconds"] = None


def _append_private_mapping(
    study_dir: Path,
    candidate_id: str,
    *,
    deployment: dict[str, Any],
    case: dict[str, Any],
    unit: dict[str, Any],
) -> None:
    path = study_dir / "private-map.json"
    mapping = load_json(path)
    private = mapping.setdefault("private_model_mapping", {})
    private[candidate_id] = {
        "model": deployment["name"],
        "digest": deployment["digest"],
        "case_id": case["case_id"],
        "run_id": unit["run"]["run_id"],
        "unit_id": unit["unit_id"],
        "repetition": unit["repetition"],
    }
    write_json(path, mapping)


def _bundle_seed(plan: dict[str, Any], case_alias: str) -> bytes:
    seed = f"{plan['blinding']['bundle_seed']}:{case_alias}".encode("utf-8")
    return hashlib.sha256(seed).digest()


def assemble_quality_bundles(
    repo_root: Path,
    study_dir: Path,
    record: dict[str, Any],
    loaded: dict[str, Any],
) -> dict[str, Any]:
    plan = loaded["plan"]
    runs_dir = resolve_repo_path(repo_root, Path(record["runs_dir"]))
    final_bundles = study_dir / "judge-bundles"
    final_private_map = final_bundles / "private-map.json"
    if final_bundles.exists():
        raise RunnerError("Quality judge bundles already exist")

    private_bundle_map: dict[str, Any] = {}
    bundle_records: list[dict[str, Any]] = []
    with TemporaryDirectory(prefix=".quality-bundles-", dir=study_dir) as temporary:
        staging = Path(temporary)
        bundles_root = staging / "judge-bundles"
        bundles_root.mkdir()

        for case_record in plan["cases"]:
            case_alias = case_record["alias"]
            complete_units = [
                unit
                for unit in record["units"]
                if unit["case_alias"] == case_alias and unit["status"] == "complete"
            ]
            opaque_candidates: list[dict[str, Any]] = []
            unit_to_opaque: dict[str, str] = {}
            for unit in complete_units:
                run_id = unit["run"]["run_id"]
                response_path = runs_dir / run_id / "response.md"
                checks = load_json(runs_dir / run_id / "checks.json")
                opaque_id = f"candidate-{secrets.token_hex(6)}"
                unit_to_opaque[unit["unit_id"]] = opaque_id
                opaque_candidates.append(
                    {
                        "candidate_id": opaque_id,
                        "response_text": response_path.read_text(encoding="utf-8").strip(),
                        "checks": checks,
                    }
                )
                deployment = _deployment_by_alias(plan, unit["deployment_alias"])
                private_bundle_map[opaque_id] = {
                    "model": deployment["name"],
                    "digest": deployment["digest"],
                    "case_id": case_record["case_id"],
                    "run_id": run_id,
                    "unit_id": unit["unit_id"],
                    "repetition": unit["repetition"],
                }

            ordering = sorted(
                opaque_candidates,
                key=lambda candidate: hashlib.sha256(
                    _bundle_seed(plan, case_alias)
                    + candidate["candidate_id"].encode("ascii")
                ).digest(),
            )
            bundle_dir = bundles_root / case_alias
            create_batch_judge_bundle(
                repo_root=repo_root,
                bundle_dir=bundle_dir,
                bundle_id=f"judge-bundle-{record['study_id']}-{case_alias}",
                loaded_case=loaded["loaded_cases"][case_alias],
                candidates=ordering,
            )

            pairs: list[dict[str, Any]] = []
            deployment_aliases = [item["alias"] for item in plan["deployments"]]
            for repetition in range(
                1, plan["methodology"]["measured_runs_per_condition"] + 1
            ):
                pair_units = [
                    unit
                    for unit in complete_units
                    if unit["repetition"] == repetition
                    and unit["deployment_alias"] in deployment_aliases
                ]
                if len(pair_units) != len(deployment_aliases):
                    continue
                ordered_pair = sorted(
                    pair_units,
                    key=lambda unit: hashlib.sha256(
                        _bundle_seed(plan, f"{case_alias}:{repetition}")
                        + unit_to_opaque[unit["unit_id"]].encode("ascii")
                    ).digest(),
                )
                pairs.append(
                    {
                        "pair_id": f"pair-{case_alias}-{repetition}",
                        "repetition": repetition,
                        "candidate_a": unit_to_opaque[ordered_pair[0]["unit_id"]],
                        "candidate_b": unit_to_opaque[ordered_pair[1]["unit_id"]],
                    }
                )
            pairwise_path = bundle_dir / "pairwise-plan.json"
            write_json(
                pairwise_path,
                {
                    "schema_version": "1.0.0",
                    "case_id": case_record["case_id"],
                    "rule": (
                        "Judge every predeclared same-repetition cross-deployment "
                        "pair after freezing all scalar scores. Do not change scalar "
                        "scores after pairwise review."
                    ),
                    "pairs": pairs,
                },
            )
            manifest_path = bundle_dir / "manifest.json"
            manifest = load_json(manifest_path)
            manifest["artifacts"].append(
                {"path": "pairwise-plan.json", "sha256": sha256_file(pairwise_path)}
            )
            manifest["artifacts"] = sorted(
                manifest["artifacts"], key=lambda item: item["path"]
            )
            write_json(manifest_path, manifest)
            bundle_records.append(
                {
                    "case_alias": case_alias,
                    "case_id": case_record["case_id"],
                    "path": f"judge-bundles/{case_alias}",
                    "candidate_count": len(ordering),
                    "pairwise_count": len(pairs),
                    "manifest_sha256": sha256_file(manifest_path),
                }
            )

        staged_private_map = bundles_root / "private-map.json"
        write_json(
            staged_private_map,
            {"schema_version": "1.0.0", "private_model_mapping": private_bundle_map},
        )
        bundles_root.replace(final_bundles)

    record["artifacts"]["bundle_private_map"] = str(
        final_private_map.relative_to(study_dir)
    )
    return {"bundles": bundle_records, "scalar_candidates": len(private_bundle_map)}


def advance_quality_study(
    repo_root: Path,
    study_dir: Path,
    *,
    host: str = "http://127.0.0.1:11434",
    execute_live: bool = False,
) -> dict[str, Any]:
    if not execute_live:
        raise RunnerError("Quality study advance requires --execute-live")
    resolved, record, loaded = _load_study(repo_root, study_dir)
    plan = loaded["plan"]
    if record["status"] == "complete":
        return _summary(record, resolved)

    unit = next(
        (item for item in record["units"] if item["status"] not in TERMINAL_UNIT_STATUSES),
        None,
    )
    if unit is None:
        record["judge_bundles"] = assemble_quality_bundles(
            repo_root, resolved, record, loaded
        )
        record["status"] = "complete"
        record["completed_at"] = utc_now()
        write_json(resolved / "study.json", record)
        return _summary(record, resolved)

    deployment = _deployment_by_alias(plan, unit["deployment_alias"])
    case = _case_by_alias(plan, unit["case_alias"])
    _reconcile_interrupted_unit(
        repo_root=repo_root,
        record=record,
        unit=unit,
        deployment=deployment,
        case=case,
    )
    if unit["status"] == "complete":
        _append_private_mapping(
            resolved,
            unit["run"]["candidate_id"],
            deployment=deployment,
            case=case,
            unit=unit,
        )
        write_json(resolved / "study.json", record)
        return _summary(record, resolved)

    client = OllamaClient(host, timeout_seconds=float(plan["methodology"]["timeout_seconds"]))
    gate_plan = {
        "resource_gate": plan["resource_gate"],
        "runtime": plan["runtime"],
        "deployment": deployment,
    }
    try:
        gate = run_resource_gate(gate_plan, client=client)
    except Exception as error:
        evidence = getattr(error, "evidence", None)
        record["status"] = "paused_resource_gate"
        record["pause_history"].append(
            {
                "paused_at": utc_now(),
                "unit_id": unit["unit_id"],
                "error_type": type(error).__name__,
                "reason": str(error),
                "evidence": evidence,
                "inference_requests_made": 0,
            }
        )
        write_json(resolved / "study.json", record)
        if isinstance(error, ResourceGatePause):
            raise
        raise ResourceGatePause(str(error), evidence or {}) from error

    record["status"] = "running"
    unit["status"] = "running"
    unit["started_at"] = utc_now()
    unit["resource_gate"] = gate
    write_json(resolved / "study.json", record)

    settings = plan["methodology"]["generation_settings"]
    try:
        preload_started = time.perf_counter()
        client.preload_model(deployment["name"], str(settings["keep_alive"]))
        unit["preload_wall_seconds"] = time.perf_counter() - preload_started
        running = running_model_names(client.list_running_models())
        if running != [deployment["name"]]:
            raise RunnerError(
                "Ollama did not report exactly the selected preloaded model: "
                + ", ".join(running)
            )
        write_json(resolved / "study.json", record)
        result = run_once(
            repo_root,
            RunConfig(
                model=deployment["name"],
                case_path=Path(case["case_path"]),
                host=host,
                results_dir=Path(record["runs_dir"]),
                temperature=float(settings["temperature"]),
                seed=int(settings["seed"]),
                num_ctx=int(case["num_ctx"]),
                num_predict=int(settings["num_predict"]),
                think=settings["think"],
                keep_alive=str(settings["keep_alive"]),
                timeout_seconds=float(plan["methodology"]["timeout_seconds"]),
                comparison_id=record["study_id"],
                measurement_phase="warm",
                measurement_iteration=int(unit["repetition"]),
            ),
        )
        run_record = load_json(
            resolve_repo_path(repo_root, Path(result["run_dir"])) / "run.json"
        )
        _record_complete_unit(unit, run_record)
        _append_private_mapping(
            resolved,
            run_record["candidate_id"],
            deployment=deployment,
            case=case,
            unit=unit,
        )
    except Exception as error:
        unit["status"] = "failed"
        unit["completed_at"] = utc_now()
        unit["failure"] = {
            "category": "infrastructure_or_runtime_failure",
            "error_type": type(error).__name__,
            "message": str(error),
            "automatic_retry": False,
        }
    finally:
        try:
            running_before_cleanup = running_model_names(client.list_running_models())
            if deployment["name"] in running_before_cleanup:
                client.unload_model(deployment["name"])
            unit["running_models_after_cleanup"] = running_model_names(
                client.list_running_models()
            )
        except Exception as cleanup_error:
            unit["cleanup_error"] = {
                "error_type": type(cleanup_error).__name__,
                "message": str(cleanup_error),
            }
        write_json(resolved / "study.json", record)

    if all(unit["status"] in TERMINAL_UNIT_STATUSES for unit in record["units"]):
        record["judge_bundles"] = assemble_quality_bundles(
            repo_root, resolved, record, loaded
        )
        record["status"] = "complete"
        record["completed_at"] = utc_now()
        write_json(resolved / "study.json", record)
    return _summary(record, resolved)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quality-stochasticity")
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start", help="Create a checkpointed study without inference")
    start.add_argument("--plan", type=Path, default=DEFAULT_PLAN_PATH)
    start.add_argument("--studies-dir", type=Path, default=DEFAULT_STUDIES_DIR)
    start.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    advance = commands.add_parser("advance", help="Execute exactly one planned live unit")
    advance.add_argument("--study-dir", type=Path, required=True)
    advance.add_argument("--host", default="http://127.0.0.1:11434")
    advance.add_argument("--execute-live", action="store_true")
    status = commands.add_parser("status", help="Show a study summary without inference")
    status.add_argument("--study-dir", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    repo_root = Path.cwd().resolve()
    try:
        if args.command == "start":
            result = start_quality_study(
                repo_root,
                QualityStudyConfig(
                    plan_path=args.plan,
                    studies_dir=args.studies_dir,
                    runs_dir=args.runs_dir,
                ),
            )
        elif args.command == "advance":
            result = advance_quality_study(
                repo_root,
                args.study_dir,
                host=args.host,
                execute_live=args.execute_live,
            )
        else:
            study_dir, record, _loaded = _load_study(repo_root, args.study_dir)
            result = _summary(record, study_dir)
    except ResourceGatePause as error:
        print(json.dumps({"status": "paused_resource_gate", "error": str(error)}))
        return 2
    except Exception as error:
        print(json.dumps({"status": "failed", "error": str(error)}))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
