"""Durable controller for the targeted Qwen 3.8 multi-format confirmation."""

from __future__ import annotations

import argparse
import json
import re
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from . import multi_format_study as base
from .log_incident_smokes import ResourceGatePause, _validate_artifacts, run_resource_gate
from .multi_format_canonical import CanonicalRunConfig
from .multi_format_mini import MiniMultiFormatStartConfig
from .multi_format_pi import PiMultiFormatPrepareConfig
from .ollama import OllamaClient, OllamaError
from .runner import (
    RunnerError,
    git_commit,
    load_json,
    resolve_repo_path,
    running_model_names,
    sha256_file,
    utc_now,
    write_json,
)


DEFAULT_PLAN = Path("tasks/agentic/multi-format-qwen38-confirmation-v0.1.json")
DEFAULT_AUTHORIZATION = Path(
    "tasks/agentic/multi-format-qwen38-confirmation-v0.1-execution-authorization.json"
)
DEFAULT_CONTROLLER_QUALIFICATION = Path(
    "tasks/agentic/multi-format-qwen38-confirmation-v0.1-controller-qualification.json"
)
CONDITION_IDS = base.CONDITION_IDS
MODEL = "qwen3.8:27b-mlx"
CELL_COUNT = 9
REPEATS_PER_CONDITION = 3
EVIDENCE_CLASS = "measured_targeted_confirmation"


@dataclass(frozen=True)
class MultiFormatConfirmationConfig:
    """Frozen inputs for one nine-cell Qwen 3.8 confirmation."""

    plan_path: Path = DEFAULT_PLAN
    authorization_path: Path = DEFAULT_AUTHORIZATION
    results_dir: Path = Path("results/agentic-confirmations")
    agent_results_dir: Path = Path("results/agentic-runs")
    host: str = "http://127.0.0.1:11434"


def _load_controller_qualification(repo_root: Path) -> dict[str, Any]:
    path = resolve_repo_path(repo_root, DEFAULT_CONTROLLER_QUALIFICATION)
    qualification = load_json(path)
    evidence = qualification.get("qualification_evidence", {})
    if (
        qualification.get("qualification_id")
        != "multi-format-qwen38-confirmation-v0.1-controller-no-inference"
        or qualification.get("status") != "qualified_for_frozen_plan"
        or evidence.get("focused_tests_passed") != 8
        or evidence.get("live_ollama_requests") != 0
        or evidence.get("live_model_inference") is not False
        or evidence.get("repository_live_authorization_present") is not False
    ):
        raise RunnerError("Invalid multi-format confirmation controller qualification")
    _validate_artifacts(
        repo_root,
        qualification.get("artifacts"),
        "multi-format confirmation controller",
    )
    return {"qualification": qualification, "path": path, "sha256": sha256_file(path)}


def _validate_baseline(repo_root: Path, plan: dict[str, Any]) -> None:
    baseline = plan.get("baseline_evidence")
    if not isinstance(baseline, dict):
        raise RunnerError("Multi-format confirmation lacks baseline evidence")
    expected = {
        "capability_plan": (
            "tasks/agentic/multi-format-capability-sweep-v0.1.json",
            "822074b8abfe631bf7c1f63dcdcc03af24d81a7dd3a260722ceec4a485b26389",
        ),
        "deterministic_report": (
            "reports/agentic/multi-format-capability-sweep-v0.1.json",
            "20ec8341a6abbfd89bb32ba8f8695016023b02c78fee8cd6ee4c0ce3ba7ddefa",
        ),
        "quality_audit": (
            "reports/agentic/multi-format-capability-sweep-v0.1-quality-audit.json",
            "c472684b522d139e03891e2505b41da1b24da9253fd552ea01fe9843575acf63",
        ),
    }
    for key, (expected_path, expected_hash) in expected.items():
        item = baseline.get(key)
        if not isinstance(item, dict):
            raise RunnerError(f"Multi-format confirmation lacks {key} baseline")
        path_value = item.get("path")
        if path_value != expected_path or item.get("sha256") != expected_hash:
            raise RunnerError(f"Unexpected multi-format confirmation {key} baseline")
        path = resolve_repo_path(repo_root, Path(path_value))
        if sha256_file(path) != expected_hash:
            raise RunnerError(f"Multi-format confirmation baseline drift: {path_value}")
    if (
        baseline.get("observed_qwen38_semantic_success_positions") != [8, 12]
        or baseline.get("observed_qwen38_canonical_failure_position") != 4
        or baseline.get("historical_cells_reused") is not False
    ):
        raise RunnerError("Multi-format confirmation baseline interpretation drifted")


def load_multi_format_confirmation_plan(
    repo_root: Path, plan_path: Path = DEFAULT_PLAN
) -> dict[str, Any]:
    """Load and validate the frozen three-condition Qwen 3.8 repetition plan."""
    path = resolve_repo_path(repo_root, plan_path)
    plan = load_json(path)
    if (
        plan.get("schema_version") != "1.0.0"
        or plan.get("plan_id") != "multi-format-qwen38-confirmation-v0.1"
        or plan.get("status") != "frozen_before_execution"
        or plan.get("track") != "A+B"
        or plan.get("study_mode") != "targeted_confirmation"
        or plan.get("evidence_class") != EVIDENCE_CLASS
    ):
        raise RunnerError("Unexpected multi-format confirmation identity")
    runtime = plan.get("runtime", {})
    if (
        runtime.get("name") != "ollama"
        or runtime.get("expected_version") != "0.33.2"
        or runtime.get("host") != "http://127.0.0.1:11434"
        or runtime.get("must_be_reverified_before_execution") is not True
    ):
        raise RunnerError("Multi-format confirmation runtime identity is incomplete")
    _validate_baseline(repo_root, plan)
    conditions = base._load_conditions(repo_root, plan)

    deployment = plan.get("deployment")
    if not isinstance(deployment, dict):
        raise RunnerError("Multi-format confirmation requires one deployment")
    identity_source = plan.get("deployment_selection", {})
    source_value = identity_source.get("source")
    if not isinstance(source_value, str):
        raise RunnerError("Multi-format confirmation deployment source is missing")
    source_path = resolve_repo_path(repo_root, Path(source_value))
    source = load_json(source_path)
    source_by_name = {
        item.get("name"): item
        for item in source.get("deployments", [])
        if isinstance(item, dict)
    }
    expected_deployment = source_by_name.get(MODEL)
    if (
        sha256_file(source_path) != identity_source.get("source_sha256")
        or identity_source.get("selection_rule")
        != "exactly qwen3.8:27b-mlx after its two complete-system successes"
        or deployment.get("name") != MODEL
        or expected_deployment is None
        or any(
            deployment.get(key) != expected_deployment.get(key)
            for key in ("deployment_id", "digest", "size_bytes", "quantization")
        )
        or re.fullmatch(r"[0-9a-f]{64}", str(deployment.get("digest"))) is None
    ):
        raise RunnerError("Invalid Qwen 3.8 confirmation deployment")

    expected_order = [
        (CONDITION_IDS[0], 1),
        (CONDITION_IDS[1], 1),
        (CONDITION_IDS[2], 1),
        (CONDITION_IDS[1], 2),
        (CONDITION_IDS[2], 2),
        (CONDITION_IDS[0], 2),
        (CONDITION_IDS[2], 3),
        (CONDITION_IDS[0], 3),
        (CONDITION_IDS[1], 3),
    ]
    order = plan.get("execution_order")
    if not isinstance(order, list) or len(order) != CELL_COUNT:
        raise RunnerError("Multi-format confirmation requires exactly nine cells")
    observed_order = []
    for position, unit in enumerate(order, start=1):
        if (
            not isinstance(unit, dict)
            or unit.get("position") != position
            or unit.get("model") != MODEL
        ):
            raise RunnerError("Invalid multi-format confirmation cell identity")
        observed_order.append((unit.get("condition_id"), unit.get("repeat")))
    if observed_order != expected_order:
        raise RunnerError("Multi-format confirmation order differs from its balanced freeze")

    comparison = plan.get("comparison_rules", {})
    if (
        comparison.get("runs_per_configuration") != REPEATS_PER_CONDITION
        or comparison.get("scheduled_repetitions") != CELL_COUNT
        or comparison.get("automatic_retries") != 0
        or comparison.get("adaptive_repetitions") is not False
        or comparison.get("terminal_attempts_not_repeated") is not True
        or comparison.get("historical_cells_reused") is not False
        or comparison.get("track_a_and_track_b_pooled") is not False
        or comparison.get("one_factor_causal_harness_claim_allowed") is not False
        or comparison.get("reliability_probability_claims") is not False
        or comparison.get("latency_distribution_claims") is not False
    ):
        raise RunnerError("Multi-format confirmation comparison rules are invalid")
    outcome = plan.get("outcome_model", {})
    if (
        outcome.get("primary") != "semantic_verified_success"
        or outcome.get("secondary") != "strict_transport_compliance"
        or outcome.get("supplemental_free_text_claim_review_required") is not True
        or outcome.get("composite_score") is not False
    ):
        raise RunnerError("Multi-format confirmation outcome model is invalid")
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
        raise RunnerError("Multi-format confirmation inference controls differ")
    authorization = plan.get("authorization", {})
    if (
        authorization.get("live_execution_authorized") is not False
        or authorization.get("post_freeze_authorization_required") is not True
        or authorization.get("fresh_clean_window_confirmation_required") is not True
    ):
        raise RunnerError("Frozen confirmation plan must defer live authorization")
    gate = plan.get("resource_gate", {})
    rules = gate.get("blocking_process_rules")
    if (
        gate.get("empty_state_observation_seconds") != 30
        or gate.get("loaded_models_must_be_empty_before_each_unit") is not True
        or gate.get("model_unloaded_after_each_unit") is not True
        or not isinstance(rules, list)
        or not rules
    ):
        raise RunnerError("Multi-format confirmation resource gate is incomplete")
    for rule in rules:
        try:
            re.compile(rule["pattern"])
        except (KeyError, TypeError, re.error) as exc:
            raise RunnerError("Invalid multi-format confirmation process rule") from exc
    qualification_gate = plan.get("qualification_gate", {})
    controller = _load_controller_qualification(repo_root)
    if (
        qualification_gate.get("controller_qualification_path")
        != base._relative(repo_root, controller["path"])
        or qualification_gate.get("controller_qualification_sha256")
        != controller["sha256"]
    ):
        raise RunnerError("Confirmation controller qualification is not hash-bound")
    _validate_artifacts(
        repo_root,
        plan.get("frozen_inputs", {}).get("artifacts"),
        "multi-format confirmation",
    )
    return {
        "plan": plan,
        "path": path,
        "sha256": sha256_file(path),
        "conditions": conditions,
        "models": {MODEL: deployment},
        "resource_gate": {
            "empty_state_observation_seconds": 30,
            "loaded_models_must_be_empty_before_each_unit": True,
            "blocking_process_rules": rules,
        },
    }


def load_execution_authorization(
    repo_root: Path, authorization_path: Path, loaded_plan: dict[str, Any]
) -> dict[str, Any]:
    """Validate a separate authorization created only after plan freeze."""
    path = resolve_repo_path(repo_root, authorization_path)
    authorization = load_json(path)
    plan = loaded_plan["plan"]
    if (
        authorization.get("schema_version") != "1.0.0"
        or authorization.get("authorization_id")
        != "multi-format-qwen38-confirmation-v0.1-execution-authorization"
        or authorization.get("status") != "authorized_pending_resource_gate"
        or authorization.get("plan_id") != plan["plan_id"]
        or authorization.get("plan_sha256") != loaded_plan["sha256"]
        or authorization.get("live_execution_authorized") is not True
        or authorization.get("cell_count") != CELL_COUNT
        or authorization.get("scheduled_repetitions_per_condition")
        != REPEATS_PER_CONDITION
        or authorization.get("automatic_retries") != 0
        or authorization.get("authorized_models") != [MODEL]
        or authorization.get("authorized_conditions") != list(CONDITION_IDS)
        or authorization.get("resource_gate_still_required") is not True
    ):
        raise RunnerError("Invalid multi-format confirmation execution authorization")
    return {"authorization": authorization, "path": path, "sha256": sha256_file(path)}


def _load_confirmation(
    repo_root: Path, study_dir: Path
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    resolved = resolve_repo_path(repo_root, study_dir)
    record = load_json(resolved / "study.json")
    if record.get("evidence_class") != EVIDENCE_CLASS:
        raise RunnerError("Record is not a targeted multi-format confirmation")
    loaded = load_multi_format_confirmation_plan(repo_root, Path(record["plan"]["path"]))
    if loaded["sha256"] != record["plan"]["sha256"]:
        raise RunnerError("Multi-format confirmation plan changed after start")
    authorization = load_execution_authorization(
        repo_root, Path(record["authorization"]["path"]), loaded
    )
    if authorization["sha256"] != record["authorization"]["sha256"]:
        raise RunnerError("Multi-format confirmation authorization changed after start")
    controller = _load_controller_qualification(repo_root)
    if (
        record["controller"]["implementation_sha256"] != sha256_file(Path(__file__))
        or record["controller"]["qualification_sha256"] != controller["sha256"]
    ):
        raise RunnerError("Multi-format confirmation controller changed after start")
    return resolved, record, loaded


def start_multi_format_confirmation(
    repo_root: Path, config: MultiFormatConfirmationConfig
) -> dict[str, Any]:
    """Create a confirmation record and prepare its first cell without inference."""
    loaded = load_multi_format_confirmation_plan(repo_root, config.plan_path)
    authorization = load_execution_authorization(
        repo_root, config.authorization_path, loaded
    )
    controller = _load_controller_qualification(repo_root)
    plan = loaded["plan"]
    if config.host.rstrip("/") != plan["runtime"]["host"].rstrip("/"):
        raise RunnerError("Configured Ollama host differs from the frozen confirmation")
    results = resolve_repo_path(repo_root, config.results_dir)
    agent_results = resolve_repo_path(repo_root, config.agent_results_dir)
    results.mkdir(parents=True, exist_ok=True)
    agent_results.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    study_id = f"multi-format-qwen38-confirmation-{timestamp}-{secrets.token_hex(4)}"
    study_dir = results / study_id
    study_dir.mkdir()
    deployment = loaded["models"][MODEL]
    record = {
        "schema_version": "1.0.0",
        "study_id": study_id,
        "status": "ready_for_local_preparation",
        "started_at": utc_now(),
        "completed_at": None,
        "track": "A+B",
        "evidence_class": EVIDENCE_CLASS,
        "git_commit": git_commit(repo_root),
        "host": config.host.rstrip("/"),
        "ollama_version": plan["runtime"]["expected_version"],
        "plan": {
            "plan_id": plan["plan_id"],
            "path": base._relative(repo_root, loaded["path"]),
            "sha256": loaded["sha256"],
        },
        "authorization": {
            "authorization_id": authorization["authorization"]["authorization_id"],
            "path": base._relative(repo_root, authorization["path"]),
            "sha256": authorization["sha256"],
        },
        "controller": {
            "implementation_path": base._relative(repo_root, Path(__file__)),
            "implementation_sha256": sha256_file(Path(__file__)),
            "qualification_path": base._relative(repo_root, controller["path"]),
            "qualification_sha256": controller["sha256"],
        },
        "agent_results_dir": base._relative(repo_root, agent_results),
        "unit_count": CELL_COUNT,
        "complete_unit_count": 0,
        "failed_unit_count": 0,
        "semantic_verified_success_count": 0,
        "strict_transport_compliance_count": 0,
        "pause": None,
        "units": [
            {
                "position": item["position"],
                "repeat": item["repeat"],
                "condition_id": item["condition_id"],
                "track": "A" if item["condition_id"] == CONDITION_IDS[0] else "B",
                "model": MODEL,
                "deployment_id": deployment["deployment_id"],
                "digest": deployment["digest"],
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
    return advance_multi_format_confirmation(repo_root, study_dir)


def advance_multi_format_confirmation(repo_root: Path, study_dir: Path) -> dict[str, Any]:
    """Advance local preparation, action processing or verification."""
    resolved, record, loaded = _load_confirmation(repo_root, study_dir)
    path = resolved / "study.json"
    while True:
        unit = base._current_unit(record)
        if unit is None:
            base._recount(record)
            record["status"] = (
                "complete" if record["failed_unit_count"] == 0 else "complete_with_failures"
            )
            record["completed_at"] = record.get("completed_at") or utc_now()
            record["pause"] = None
            write_json(path, record)
            return base._summary(record, resolved)
        if unit.get("run_dir"):
            base._sync_unit(repo_root, unit)
            base._recount(record)
            write_json(path, record)
        condition = unit["condition_id"]
        if unit["status"] == "pending":
            declaration = loaded["conditions"][condition]["declaration"]
            if condition == CONDITION_IDS[0]:
                started = base.prepare_canonical_run(
                    repo_root,
                    CanonicalRunConfig(
                        model=MODEL,
                        condition_path=Path(declaration["condition_path"]),
                        results_dir=Path(record["agent_results_dir"]),
                        host=record["host"],
                    ),
                )
                unit["status"] = "awaiting_model"
            elif condition == CONDITION_IDS[1]:
                started = base.start_mini_multi_format_run(
                    repo_root,
                    MiniMultiFormatStartConfig(
                        model=MODEL,
                        harness_path=Path(declaration["harness_path"]),
                        results_dir=Path(record["agent_results_dir"]),
                        host=record["host"],
                    ),
                )
                unit["status"] = "awaiting_model"
            else:
                started = base.prepare_pi_multi_format_run(
                    repo_root,
                    PiMultiFormatPrepareConfig(
                        model=MODEL,
                        results_dir=Path(record["agent_results_dir"]),
                        host=record["host"],
                    ),
                )
                unit["status"] = "sandbox_pending"
            unit["run_id"] = started["run_id"]
            unit["run_dir"] = base._relative(repo_root, Path(started["run_dir"]))
            unit["prepared_at"] = utc_now()
            record["status"] = "waiting_for_live_boundary"
            write_json(path, record)
            continue
        run_dir, _run = base._run_record(repo_root, unit)
        if unit["status"] == "awaiting_action":
            base.step_mini_multi_format_action(repo_root, run_dir)
            base._sync_unit(repo_root, unit)
            write_json(path, record)
            continue
        if unit["status"] == "sandbox_pending":
            acceptance = base.validate_pi_multi_format_seatbelt(run_dir)
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
            return base._summary(record, resolved)
        if unit["status"] == "verification_pending":
            if condition == CONDITION_IDS[0]:
                base.finalize_canonical_run(repo_root, run_dir)
            elif condition == CONDITION_IDS[1]:
                base.finalize_mini_multi_format_run(repo_root, run_dir)
            else:
                base.finalize_pi_multi_format_run(repo_root, run_dir)
            base._sync_unit(repo_root, unit)
            base._recount(record)
            write_json(path, record)
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
            write_json(path, record)
            return base._summary(record, resolved)
        raise RunnerError(f"Cannot advance confirmation cell state {unit['status']!r}")


def run_multi_format_confirmation_live(
    repo_root: Path,
    study_dir: Path,
    *,
    client: OllamaClient | None = None,
    process_reader: Callable[[], list[dict[str, Any]]] = base._process_snapshot,
    sleep: Callable[[float], None] = time.sleep,
    exclusive_window_confirmed: bool = False,
) -> dict[str, Any]:
    """Execute one live boundary after the independent confirmation gate."""
    if not exclusive_window_confirmed:
        raise RunnerError(
            "Live multi-format confirmation requires an exclusive-window confirmation"
        )
    resolved, record, loaded = _load_confirmation(repo_root, study_dir)
    unit = base._current_unit(record)
    if unit is None:
        raise RunnerError("Multi-format confirmation has no pending live boundary")
    base._sync_unit(repo_root, unit)
    expected = (
        "sandbox_accepted" if unit["condition_id"] == CONDITION_IDS[2] else "awaiting_model"
    )
    if unit["status"] != expected:
        write_json(resolved / "study.json", record)
        raise RunnerError(f"Confirmation cell is not ready for live execution: {unit['status']}")
    ollama = client or OllamaClient(record["host"])
    base._validate_deployment(ollama, unit, record["ollama_version"])
    _run_dir, run = base._run_record(repo_root, unit)
    first_request = (
        unit["condition_id"] != CONDITION_IDS[1]
        or run.get("trajectory", {}).get("model_requests") == 0
    )
    try:
        if first_request:
            gate_plan = {
                "runtime": {"name": "ollama", "version": record["ollama_version"]},
                "deployment": {"name": MODEL, "digest": unit["digest"]},
                "resource_gate": loaded["resource_gate"],
            }
            unit["resource_gate"] = run_resource_gate(
                gate_plan, client=ollama, process_reader=process_reader, sleep=sleep
            )
        else:
            blockers = base._blocking_processes(
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
                if name != MODEL
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
    record["status"] = "running_live_boundary"
    record["pause"] = None
    write_json(resolved / "study.json", record)
    run_dir, _run = base._run_record(repo_root, unit)
    if unit["condition_id"] == CONDITION_IDS[0]:
        base.execute_canonical_run(repo_root, run_dir)
    elif unit["condition_id"] == CONDITION_IDS[1]:
        base.call_mini_multi_format_model(repo_root, run_dir)
    else:
        base.execute_pi_multi_format_run(repo_root, run_dir)
    base._sync_unit(repo_root, unit, after_live=True)
    record["status"] = "waiting_for_local_step"
    write_json(resolved / "study.json", record)
    return base._summary(record, resolved)


def cleanup_multi_format_confirmation_unit(
    repo_root: Path, study_dir: Path, *, client: OllamaClient | None = None
) -> dict[str, Any]:
    """Unload a terminal confirmation cell and advance without retrying it."""
    resolved, record, _loaded = _load_confirmation(repo_root, study_dir)
    unit = base._current_unit(record)
    if unit is None or unit["status"] not in {
        "complete_needs_cleanup",
        "failed_needs_cleanup",
    }:
        raise RunnerError("No terminal confirmation cell is awaiting cleanup")
    ollama = client or OllamaClient(record["host"])
    ollama.unload_model(MODEL)
    running = running_model_names(ollama.list_running_models())
    unit["postflight_running_models"] = running
    if running:
        record["status"] = "paused_resource_gate"
        record["pause"] = {
            "at": utc_now(),
            "stage": "postflight_cleanup",
            "reason": "Ollama was not empty after confirmation cleanup.",
            "running_models": running,
        }
        write_json(resolved / "study.json", record)
        raise ResourceGatePause(record["pause"]["reason"], record["pause"])
    unit["status"] = "failed" if unit["status"] == "failed_needs_cleanup" else "complete"
    unit["completed_at"] = utc_now()
    base._recount(record)
    record["status"] = "ready_for_local_preparation"
    record["pause"] = None
    write_json(resolved / "study.json", record)
    return advance_multi_format_confirmation(repo_root, resolved)


def drive_multi_format_confirmation(
    repo_root: Path, study_dir: Path, *, exclusive_window_confirmed: bool
) -> dict[str, Any]:
    """Drive all checkpoints until completion or a resource/control pause."""
    if not exclusive_window_confirmed:
        raise RunnerError("Drive mode requires an exclusive-window confirmation")
    while True:
        summary = advance_multi_format_confirmation(repo_root, study_dir)
        if summary["status"] in {"complete", "complete_with_failures"}:
            return summary
        status = summary["waiting"]["unit_status"]
        if status in {"awaiting_model", "sandbox_accepted"}:
            run_multi_format_confirmation_live(
                repo_root, study_dir, exclusive_window_confirmed=True
            )
        elif status in {"complete_needs_cleanup", "failed_needs_cleanup"}:
            cleanup_multi_format_confirmation_unit(repo_root, study_dir)
        else:
            raise RunnerError(f"Drive mode cannot continue from {status!r}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser("start")
    start.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    start.add_argument("--authorization", type=Path, default=DEFAULT_AUTHORIZATION)
    start.add_argument(
        "--results-dir", type=Path, default=Path("results/agentic-confirmations")
    )
    start.add_argument(
        "--agent-results-dir", type=Path, default=Path("results/agentic-runs")
    )
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
            result = start_multi_format_confirmation(
                repo_root,
                MultiFormatConfirmationConfig(
                    plan_path=args.plan,
                    authorization_path=args.authorization,
                    results_dir=args.results_dir,
                    agent_results_dir=args.agent_results_dir,
                    host=args.host,
                ),
            )
        elif args.command == "advance":
            result = advance_multi_format_confirmation(repo_root, args.study_dir)
        elif args.command == "live":
            result = run_multi_format_confirmation_live(
                repo_root,
                args.study_dir,
                exclusive_window_confirmed=args.exclusive_window_confirmed,
            )
        elif args.command == "cleanup":
            result = cleanup_multi_format_confirmation_unit(repo_root, args.study_dir)
        else:
            result = drive_multi_format_confirmation(
                repo_root,
                args.study_dir,
                exclusive_window_confirmed=args.exclusive_window_confirmed,
            )
    except (OSError, RunnerError, OllamaError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
