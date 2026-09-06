"""Build the public report for the targeted Track B replication study."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from .runner import (
    RunnerError,
    load_json,
    resolve_repo_path,
    sha256_file,
    utc_now,
    write_json,
)


DEFAULT_STUDY_DIR = Path(
    "results/agentic-studies/track-b-replication-20260905T065124Z-cbc09fb5"
)
DEFAULT_JSON_OUT = Path(
    "reports/coding/track-b-targeted-system-replication-v0.1.json"
)
DEFAULT_MARKDOWN_OUT = Path(
    "reports/coding/track-b-targeted-system-replication-v0.1.md"
)
EXPECTED_PLAN_ID = "track-b-targeted-system-replication-v0.1"
EXPECTED_BASELINE_REPORTS = {
    "pi-v0.3": "track-b-pi-capability-sweep-v0.3",
    "mini-v0.3": "track-b-mini-capability-sweep-v0.3",
}
AGENT_FAILURE_TYPES = {
    "emergency_operation_safeguard_exceeded",
    "invalid_agent_end",
    "maximum_active_wall_time_exceeded",
    "max_steps_exceeded",
    "protocol_error_limit_exceeded",
    "repeated_failure",
    "stalled_trajectory",
}
TASK_FAILURE_TYPES = {
    "hidden_tests_failed",
    "public_tests_failed",
    "tests_failed",
    "verification_failed",
}


def _rounded(value: Any) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _effective_failure(
    *,
    verified_success: bool,
    raw_category: str | None,
    raw_type: str | None,
    effective_type: str | None,
    termination_reason: str | None,
) -> tuple[str | None, str | None]:
    if verified_success:
        return None, None
    if effective_type is not None:
        resolved_type = effective_type
    elif termination_reason in AGENT_FAILURE_TYPES:
        resolved_type = termination_reason
    else:
        resolved_type = raw_type or termination_reason or "verification_failed"
    if resolved_type in AGENT_FAILURE_TYPES:
        return "agent_failure", resolved_type
    if resolved_type in TASK_FAILURE_TYPES:
        return "task_or_verification_failure", resolved_type
    return raw_category or "other", resolved_type


def _baseline_observation(
    unit: dict[str, Any], harness_id: str
) -> dict[str, Any]:
    verified_success = bool(unit["verified_success"])
    raw_category = unit.get("raw_failure_category")
    raw_type = (
        unit.get("raw_failure_type")
        if harness_id == "pi-v0.3"
        else unit.get("failure_type")
    )
    effective_type = (
        unit.get("effective_failure_type")
        if harness_id == "pi-v0.3"
        else unit.get("failure_type")
    )
    termination_reason = unit.get("trajectory_termination_reason")
    effective_category, effective_type = _effective_failure(
        verified_success=verified_success,
        raw_category=raw_category,
        raw_type=raw_type,
        effective_type=effective_type,
        termination_reason=termination_reason,
    )
    return {
        "model": unit["model"],
        "deployment_id": unit["deployment_id"],
        "case_id": unit["case_id"],
        "case_label": unit["case_label"],
        "harness_id": harness_id,
        "observation_origin": "baseline_capability_sweep",
        "replication_index": 1,
        "run_id": unit["run_id"],
        "verified_success": verified_success,
        "verifier_success": bool(unit["verifier_success"]),
        "runtime_success": bool(unit["runtime_success"]),
        "agent_termination_valid": bool(
            unit.get("agent_termination_valid_raw", unit.get("agent_termination_valid"))
        ),
        "raw_failure_category": raw_category,
        "raw_failure_type": raw_type,
        "effective_failure_category": effective_category,
        "effective_failure_type": effective_type,
        "trajectory_termination_reason": termination_reason,
        "active_duration_seconds": _rounded(unit["active_duration_seconds"]),
        "agent_turns": unit["agent_turns"],
        "tool_calls": unit["tool_calls"],
        "failed_tool_calls": unit["failed_tool_calls"],
        "file_reads": unit["file_reads"],
        "file_writes": unit["file_writes"],
        "public_test_runs": unit["public_test_runs"],
        "input_tokens": unit["input_tokens"],
        "output_tokens": unit["output_tokens"],
    }


def _fresh_observation(
    unit: dict[str, Any], case_label: str
) -> dict[str, Any]:
    outcome = unit["outcome"]
    trajectory = unit["trajectory"]
    verified_success = bool(outcome["verified_success"])
    raw_category = outcome.get("failure_category")
    raw_type = outcome.get("failure_type")
    termination_reason = trajectory.get("termination_reason") or outcome.get(
        "trajectory_termination_reason"
    )
    effective_category, effective_type = _effective_failure(
        verified_success=verified_success,
        raw_category=raw_category,
        raw_type=raw_type,
        effective_type=None,
        termination_reason=termination_reason,
    )
    return {
        "model": unit["model"],
        "deployment_id": unit["deployment_id"],
        "case_id": unit["case_id"],
        "case_label": case_label,
        "harness_id": unit["harness_id"],
        "observation_origin": "fresh_targeted_replication",
        "replication_index": unit["replication_index"],
        "run_id": unit["run_id"],
        "verified_success": verified_success,
        "verifier_success": bool(outcome["verifier_success"]),
        "runtime_success": bool(outcome["runtime_success"]),
        "agent_termination_valid": bool(outcome["agent_termination_valid"]),
        "raw_failure_category": raw_category,
        "raw_failure_type": raw_type,
        "effective_failure_category": effective_category,
        "effective_failure_type": effective_type,
        "trajectory_termination_reason": termination_reason,
        "active_duration_seconds": _rounded(trajectory["active_wall_time_seconds"]),
        "agent_turns": trajectory["agent_turns"],
        "tool_calls": trajectory["tool_calls"],
        "failed_tool_calls": trajectory["failed_tool_calls"],
        "file_reads": trajectory["file_reads"],
        "file_writes": trajectory["file_writes"],
        "public_test_runs": trajectory["public_test_runs"],
        "input_tokens": trajectory["input_tokens"],
        "output_tokens": trajectory["output_tokens"],
    }


def _duration_summary(observations: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(item["active_duration_seconds"]) for item in observations]
    if not values:
        return {
            "n": 0,
            "median_seconds": None,
            "minimum_seconds": None,
            "maximum_seconds": None,
        }
    return {
        "n": len(values),
        "median_seconds": round(statistics.median(values), 2),
        "minimum_seconds": round(min(values), 2),
        "maximum_seconds": round(max(values), 2),
    }


def _pattern(observations: list[dict[str, Any]]) -> str:
    outcomes = [item["verified_success"] for item in observations]
    if all(outcomes):
        return "consistent_success"
    if not any(outcomes):
        return "consistent_failure"
    return "mixed_outcomes"


def aggregate_system_cell(observations: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate one frozen system cell without estimating probabilities."""
    ordered = sorted(observations, key=lambda item: item["replication_index"])
    if len(ordered) != 3 or [item["replication_index"] for item in ordered] != [1, 2, 3]:
        raise RunnerError("Each replication system cell must contain indices 1, 2 and 3")
    identity = {
        (item["model"], item["case_id"], item["harness_id"])
        for item in ordered
    }
    if len(identity) != 1:
        raise RunnerError("Cannot aggregate observations from different system cells")
    baseline = ordered[0]
    fresh = ordered[1:]
    effective_failures = Counter(
        item["effective_failure_type"]
        for item in ordered
        if item["effective_failure_type"] is not None
    )
    return {
        "model": baseline["model"],
        "deployment_id": baseline["deployment_id"],
        "case_id": baseline["case_id"],
        "case_label": baseline["case_label"],
        "harness_id": baseline["harness_id"],
        "observation_count": 3,
        "verified_success_count": sum(item["verified_success"] for item in ordered),
        "verified_failure_count": sum(not item["verified_success"] for item in ordered),
        "outcome_pattern": _pattern(ordered),
        "baseline_verified_success": baseline["verified_success"],
        "fresh_verified_success_count": sum(item["verified_success"] for item in fresh),
        "fresh_observation_count": 2,
        "fresh_matches_baseline_count": sum(
            item["verified_success"] == baseline["verified_success"] for item in fresh
        ),
        "outcome_sequence_by_replication_index": [
            item["verified_success"] for item in ordered
        ],
        "active_duration_all_outcomes": _duration_summary(ordered),
        "active_duration_verified_successes": _duration_summary(
            [item for item in ordered if item["verified_success"]]
        ),
        "effective_failure_counts": dict(sorted(effective_failures.items())),
    }


def _load_baseline_reports(
    repo_root: Path, plan: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    reports: dict[str, dict[str, Any]] = {}
    sources: dict[str, Any] = {}
    for item in plan["baseline_reports"]:
        harness_id = item["harness_id"]
        path = resolve_repo_path(repo_root, Path(item["path"]))
        if sha256_file(path) != item["sha256"]:
            raise RunnerError(f"Baseline report drift: {item['path']}")
        report = load_json(path)
        if report.get("report_id") != EXPECTED_BASELINE_REPORTS.get(harness_id):
            raise RunnerError(f"Unexpected baseline report for {harness_id}")
        reports[harness_id] = report
        sources[harness_id] = {
            "path": path.relative_to(repo_root).as_posix(),
            "report_id": report["report_id"],
            "sha256": sha256_file(path),
        }
    if set(reports) != set(EXPECTED_BASELINE_REPORTS):
        raise RunnerError("Both frozen baseline reports are required")
    return reports, sources


def build_track_b_replication_report(
    repo_root: Path, study_dir: Path
) -> dict[str, Any]:
    """Build a public-safe report from a complete targeted study."""
    resolved_study_dir = resolve_repo_path(repo_root, study_dir)
    study_path = resolved_study_dir / "study.json"
    study = load_json(study_path)
    if study.get("status") != "complete" or study.get("complete_unit_count") != 8:
        raise RunnerError("Targeted replication study is not complete")
    plan_path = resolve_repo_path(repo_root, Path(study["plan"]["path"]))
    if sha256_file(plan_path) != study["plan"]["sha256"]:
        raise RunnerError("Targeted replication plan drift")
    plan = load_json(plan_path)
    if plan.get("plan_id") != EXPECTED_PLAN_ID:
        raise RunnerError("Unexpected targeted replication plan")
    baseline_reports, baseline_sources = _load_baseline_reports(repo_root, plan)

    selected_cells = {
        (item["model"], item["case_id"]) for item in plan["selected_cells"]
    }
    case_labels: dict[str, str] = {}
    observations: list[dict[str, Any]] = []
    for harness_id, baseline in baseline_reports.items():
        for unit in baseline["units"]:
            key = (unit["model"], unit["case_id"])
            if key in selected_cells:
                case_labels[unit["case_id"]] = unit["case_label"]
                observations.append(_baseline_observation(unit, harness_id))

    expected_fresh = {
        (
            item["harness_id"],
            item["model"],
            item["case_id"],
            item["replication_index"],
        )
        for item in plan["execution_order"]
    }
    observed_fresh = set()
    interrupted_attempt_count = 0
    for unit in study["units"]:
        identity = (
            unit["harness_id"],
            unit["model"],
            unit["case_id"],
            unit["replication_index"],
        )
        if unit.get("status") != "complete" or identity not in expected_fresh:
            raise RunnerError(f"Unexpected or incomplete fresh unit: {identity}")
        if identity in observed_fresh:
            raise RunnerError(f"Duplicate fresh unit: {identity}")
        observed_fresh.add(identity)
        interrupted_attempt_count += len(unit.get("interrupted_attempts", []))
        observations.append(_fresh_observation(unit, case_labels[unit["case_id"]]))
    if observed_fresh != expected_fresh:
        raise RunnerError("Fresh study coverage differs from the frozen plan")

    harness_order = ["pi-v0.3", "mini-v0.3"]
    cell_order = [
        (item["model"], item["case_id"]) for item in plan["selected_cells"]
    ]
    observations.sort(
        key=lambda item: (
            cell_order.index((item["model"], item["case_id"])),
            harness_order.index(item["harness_id"]),
            item["replication_index"],
        )
    )
    system_cells = []
    for model, case_id in cell_order:
        for harness_id in harness_order:
            system_cells.append(
                aggregate_system_cell(
                    [
                        item
                        for item in observations
                        if item["model"] == model
                        and item["case_id"] == case_id
                        and item["harness_id"] == harness_id
                    ]
                )
            )

    by_harness = []
    for harness_id in harness_order:
        selected = [item for item in observations if item["harness_id"] == harness_id]
        by_harness.append(
            {
                "harness_id": harness_id,
                "observation_count": len(selected),
                "verified_success_count": sum(
                    item["verified_success"] for item in selected
                ),
                "verified_failure_count": sum(
                    not item["verified_success"] for item in selected
                ),
            }
        )

    summary = {
        "selected_model_task_cell_count": len(cell_order),
        "system_cell_count": len(system_cells),
        "baseline_observation_count": 4,
        "fresh_observation_count": 8,
        "planned_observation_count": len(observations),
        "verified_success_count": sum(
            item["verified_success"] for item in observations
        ),
        "verified_failure_count": sum(
            not item["verified_success"] for item in observations
        ),
        "interrupted_attempt_count_excluded": interrupted_attempt_count,
        "consistent_success_system_cell_count": sum(
            item["outcome_pattern"] == "consistent_success" for item in system_cells
        ),
        "consistent_failure_system_cell_count": sum(
            item["outcome_pattern"] == "consistent_failure" for item in system_cells
        ),
        "mixed_outcome_system_cell_count": sum(
            item["outcome_pattern"] == "mixed_outcomes" for item in system_cells
        ),
    }

    return {
        "schema_version": "1.0.0",
        "report_id": "track-b-targeted-system-replication-v0.1",
        "generated_at": utc_now(),
        "evidence_class": "post_hoc_targeted_replication",
        "sources": {
            "study": {
                "study_id": study["study_id"],
                "path": study_path.relative_to(repo_root).as_posix(),
                "sha256": sha256_file(study_path),
                "implementation_git_commit": study["git_commit"],
                "ollama_version": study["ollama_version"],
            },
            "plan": {
                "plan_id": plan["plan_id"],
                "path": plan_path.relative_to(repo_root).as_posix(),
                "sha256": sha256_file(plan_path),
            },
            "baseline_reports": baseline_sources,
        },
        "method": {
            "track": "B",
            "study_mode": "targeted_outcome_replication",
            "selection_timing": "post_hoc_before_fresh_execution",
            "selected_model_task_cells": 2,
            "systems_per_selected_cell": 2,
            "baseline_observations_per_system_cell": 1,
            "fresh_observations_per_system_cell": 2,
            "descriptive_observations_per_system_cell": 3,
            "automatic_retries": 0,
            "adaptive_repetitions": False,
            "primary_outcome": "verified_success",
            "duration_reporting": "raw values plus median and range only",
            "reliability_probability_claimed": False,
            "tail_performance_claimed": False,
            "statistical_significance_claimed": False,
            "causal_harness_effect_claimed": False,
        },
        "summary": summary,
        "by_harness": by_harness,
        "system_cells": system_cells,
        "observations": observations,
        "findings": [
            "Qwen 3.8 on the JavaScript cache case succeeded in 2/3 Pi observations and 0/3 Mini observations; Pi's outcomes were mixed while Mini failed consistently.",
            "Qwen 3.6 on the Python pagination case succeeded in 0/3 Pi observations and 3/3 Mini observations, reproducing the baseline reversal twice in each direction.",
            "The two selected cross-system differences point in opposite directions. The evidence therefore rejects a simple claim that either harness is uniformly better.",
            "Pi/Qwen 3.6 reached an emergency operation safeguard once and the 900-second active-time boundary twice; Mini/Qwen 3.6 completed successfully in all three observations with 13 turns each.",
            "Mini/Qwen 3.8 finished quickly in all three observations but consistently failed hidden verification. Fast termination did not imply a verified outcome.",
        ],
        "caveats": [
            "The two model-task cells were selected after inspecting the original paired screen. This is targeted follow-up evidence, not a confirmatory random sample of tasks.",
            "Each system cell has only three descriptive observations. Counts are not success-probability estimates, and no P90, P95, P99 or statistical-significance claim is reported.",
            "The baseline remains explicitly separate from the two fresh repetitions even though deployment, task, runtime, harness and inference identities match.",
            "Pi and Mini differ in prompts, action protocols, tool implementations, context accumulation and error handling. Outcomes compare complete deployed systems and do not isolate a causal harness effect.",
            "Durations for failed runs remain visible but are not equivalent to time-to-success. Successful-only duration summaries are reported separately.",
            "One interrupted Pi attempt caused by host sleep or process interruption is preserved in raw evidence and excluded from all twelve planned observations.",
            "No composite score or universal model or harness ranking is calculated.",
        ],
        "privacy": {
            "raw_model_text_included": False,
            "candidate_source_included": False,
            "test_output_included": False,
            "absolute_local_paths_included": False,
        },
    }


def _outcome(value: bool) -> str:
    return "PASS" if value else "FAIL"


def render_track_b_replication_markdown(report: dict[str, Any]) -> str:
    """Render the targeted replication report as public Markdown."""
    summary = report["summary"]
    lines = [
        "# Track B Targeted System Replication v0.1",
        "",
        "## Outcome",
        "",
        (
            "The frozen follow-up completed all **8 fresh runs**. Together with "
            "the four explicitly identified baseline observations, the report "
            f"contains **{summary['planned_observation_count']} planned observations** "
            f"and {summary['verified_success_count']} verified successes."
        ),
        "",
        "| Model and case | System | Baseline | Fresh 2 | Fresh 3 | Pattern | Active duration, all outcomes |",
        "| --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    observations = report["observations"]
    for cell in report["system_cells"]:
        cell_observations = [
            item
            for item in observations
            if item["model"] == cell["model"]
            and item["case_id"] == cell["case_id"]
            and item["harness_id"] == cell["harness_id"]
        ]
        durations = cell["active_duration_all_outcomes"]
        values = {item["replication_index"]: item for item in cell_observations}
        lines.append(
            f"| `{cell['model']}` / {cell['case_label']} | `{cell['harness_id']}` | "
            f"{_outcome(values[1]['verified_success'])} | "
            f"{_outcome(values[2]['verified_success'])} | "
            f"{_outcome(values[3]['verified_success'])} | "
            f"`{cell['outcome_pattern']}` | median {durations['median_seconds']:.2f}s; "
            f"range {durations['minimum_seconds']:.2f}–{durations['maximum_seconds']:.2f}s |"
        )
    lines.extend(
        [
            "",
            "The counts are descriptive outcomes, not estimated success probabilities. "
            "With `n=3` per system cell, the report intentionally omits tail percentiles.",
            "",
            "## Individual observations",
            "",
            "| Model and case | System | Origin | Result | Active | Turns | Tools | Failed tools | Failure |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for item in observations:
        failure = item["effective_failure_type"] or "—"
        origin = "baseline" if item["replication_index"] == 1 else f"fresh {item['replication_index']}"
        lines.append(
            f"| `{item['model']}` / {item['case_label']} | `{item['harness_id']}` | "
            f"{origin} | {_outcome(item['verified_success'])} | "
            f"{item['active_duration_seconds']:.2f}s | {item['agent_turns']} | "
            f"{item['tool_calls']} | {item['failed_tool_calls']} | `{failure}` |"
        )
    lines.extend(["", "## Main observations", ""])
    lines.extend(f"- {finding}" for finding in report["findings"])
    lines.extend(["", "## Methodological limits", ""])
    lines.extend(f"- {caveat}" for caveat in report["caveats"])
    lines.extend(
        [
            "",
            "## Provenance",
            "",
            f"- Frozen plan: `{report['sources']['plan']['plan_id']}` (`{report['sources']['plan']['sha256']}`)",
            f"- Completed local study: `{report['sources']['study']['study_id']}` (`{report['sources']['study']['sha256']}`)",
            f"- Pi baseline: `{report['sources']['baseline_reports']['pi-v0.3']['report_id']}`",
            f"- Mini baseline: `{report['sources']['baseline_reports']['mini-v0.3']['report_id']}`",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", type=Path, default=DEFAULT_STUDY_DIR)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON_OUT)
    parser.add_argument("--markdown-out", type=Path, default=DEFAULT_MARKDOWN_OUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    report = build_track_b_replication_report(repo_root, args.study_dir)
    json_path = resolve_repo_path(repo_root, args.json_out)
    markdown_path = resolve_repo_path(repo_root, args.markdown_out)
    write_json(json_path, report)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(
        render_track_b_replication_markdown(report), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "json_report": json_path.relative_to(repo_root).as_posix(),
                "markdown_report": markdown_path.relative_to(repo_root).as_posix(),
                "observation_count": report["summary"]["planned_observation_count"],
                "verified_success_count": report["summary"]["verified_success_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
