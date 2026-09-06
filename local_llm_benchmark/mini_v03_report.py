"""Build a public-safe cross-case report from one completed Mini v0.3 sweep."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from .mini_v03_adapter import load_mini_v03_harness
from .mini_v03_sweep import load_mini_v03_sweep_plan
from .runner import (
    RunnerError,
    load_json,
    resolve_repo_path,
    sha256_file,
    utc_now,
    write_json,
)


CASE_LABELS = {
    "coding.dev.php-payment-result-migration": "PHP payment migration",
    "coding.dev.async-cache-coalescing": "JavaScript async cache",
    "coding.dev.pagination-cycle-guard": "Python pagination guard",
}

AGENT_FAILURE_TYPES = {
    "emergency_operation_safeguard_exceeded",
    "maximum_active_wall_time_exceeded",
}

TASK_FAILURE_TYPES = {
    "hidden_tests_failed",
    "public_tests_failed",
    "verification_failed",
}


def _rounded(value: Any, digits: int = 2) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(float(value), digits)
    return None


def _effective_failure_category(
    *, verified_success: bool, failure_type: str | None, raw_category: str | None
) -> str | None:
    """Resolve known terminal semantics while preserving the raw classification."""
    if verified_success:
        return None
    if failure_type in AGENT_FAILURE_TYPES:
        return "agent_failure"
    if failure_type in TASK_FAILURE_TYPES:
        return "task_or_verification_failure"
    return raw_category or "other"


def _public_unit(repo_root: Path, unit: dict[str, Any]) -> dict[str, Any]:
    run_dir = resolve_repo_path(repo_root, Path(unit["run_dir"]))
    run = load_json(run_dir / "run.json")
    if run.get("run_id") != unit.get("run_id") or run.get("state") != "complete":
        raise RunnerError("Mini v0.3 report found an incomplete or mismatched run")
    outcome = run.get("outcome")
    trajectory = run.get("trajectory")
    verification = run.get("verification")
    if not all(isinstance(value, dict) for value in (outcome, trajectory, verification)):
        raise RunnerError("Mini v0.3 run is missing terminal evidence")
    tests = verification.get("tests") or {}
    public_tests = tests.get("public") or {}
    hidden_tests = tests.get("hidden") or {}
    verified_success = bool(outcome.get("verified_success"))
    failure_type = (
        None
        if verified_success
        else outcome.get("failure_type") or "verification_failed"
    )
    raw_failure_category = outcome.get("failure_category")
    return {
        "position": unit["position"],
        "run_id": unit["run_id"],
        "model": unit["model"],
        "deployment_id": unit["deployment_id"],
        "case_id": unit["case_id"],
        "case_label": CASE_LABELS.get(unit["case_id"], unit["case_id"]),
        "runtime_success": bool(outcome.get("runtime_success")),
        "agent_termination_valid": bool(outcome.get("agent_termination_valid")),
        "verifier_success": bool(outcome.get("verifier_success")),
        "verified_success": verified_success,
        "raw_failure_category": raw_failure_category,
        "effective_failure_category": _effective_failure_category(
            verified_success=verified_success,
            failure_type=failure_type,
            raw_category=raw_failure_category,
        ),
        "failure_type": failure_type,
        "trajectory_termination_reason": outcome.get(
            "trajectory_termination_reason"
        ),
        "public_tests_passed": bool(public_tests.get("passed")),
        "hidden_tests_passed": bool(hidden_tests.get("passed")),
        "active_duration_seconds": _rounded(
            trajectory.get("active_wall_time_seconds")
        ),
        "model_duration_seconds": _rounded(
            trajectory.get("model_wall_time_seconds")
        ),
        "tool_duration_seconds": _rounded(trajectory.get("tool_wall_time_seconds")),
        "final_verification_duration_seconds": _rounded(
            trajectory.get("final_verification_wall_time_seconds")
        ),
        "agent_turns": trajectory.get("agent_turns"),
        "model_requests": trajectory.get("model_requests"),
        "tool_calls": trajectory.get("tool_calls"),
        "failed_tool_calls": trajectory.get("failed_tool_calls"),
        "protocol_errors": trajectory.get("protocol_errors"),
        "file_reads": trajectory.get("file_reads"),
        "file_writes": trajectory.get("file_writes"),
        "public_test_runs": trajectory.get("public_test_runs"),
        "input_tokens": trajectory.get("input_tokens"),
        "output_tokens": trajectory.get("output_tokens"),
        "time_to_first_successful_public_verification_seconds": _rounded(
            trajectory.get("time_to_first_successful_public_verification_seconds")
        ),
        "interrupted_attempt_count": len(unit.get("interrupted_attempts") or []),
    }


def _aggregate_group(
    group: list[dict[str, Any]], *, key: str, value: str
) -> dict[str, Any]:
    durations = [item["active_duration_seconds"] for item in group]
    if any(duration is None for duration in durations):
        raise RunnerError("Mini v0.3 report requires active duration for every run")
    numeric_durations = [float(duration) for duration in durations]
    return {
        key: value,
        "run_count": len(group),
        "verified_success_count": sum(item["verified_success"] for item in group),
        "verifier_success_count": sum(item["verifier_success"] for item in group),
        "runtime_success_count": sum(item["runtime_success"] for item in group),
        "valid_agent_termination_count": sum(
            item["agent_termination_valid"] for item in group
        ),
        "active_duration_seconds": {
            "raw": durations,
            "minimum": _rounded(min(numeric_durations)),
            "median": _rounded(statistics.median(numeric_durations)),
            "maximum": _rounded(max(numeric_durations)),
            "total": _rounded(sum(numeric_durations)),
        },
        "total_agent_turns": sum(item["agent_turns"] for item in group),
        "total_model_requests": sum(item["model_requests"] for item in group),
        "total_tool_calls": sum(item["tool_calls"] for item in group),
        "total_protocol_errors": sum(item["protocol_errors"] for item in group),
        "total_output_tokens": sum(item["output_tokens"] for item in group),
        "interrupted_attempt_count": sum(
            item["interrupted_attempt_count"] for item in group
        ),
        "failures": dict(
            sorted(
                Counter(
                    item["failure_type"]
                    for item in group
                    if item["failure_type"] is not None
                ).items()
            )
        ),
    }


def _findings(
    by_model: list[dict[str, Any]], by_case: list[dict[str, Any]]
) -> list[str]:
    best_count = max(item["verified_success_count"] for item in by_model)
    best_models = [
        item["model"] for item in by_model if item["verified_success_count"] == best_count
    ]
    easiest_count = max(item["verified_success_count"] for item in by_case)
    hardest_count = min(item["verified_success_count"] for item in by_case)
    easiest = [
        item["case_label"]
        for item in by_case
        if item["verified_success_count"] == easiest_count
    ]
    hardest = [
        item["case_label"]
        for item in by_case
        if item["verified_success_count"] == hardest_count
    ]
    return [
        f"Highest observed coverage is {best_count}/3 for {', '.join(best_models)}.",
        f"Highest case success is {easiest_count}/5 on {', '.join(easiest)}.",
        f"Lowest case success is {hardest_count}/5 on {', '.join(hardest)}.",
        "Model, tool and final-verification time remain separate; active duration is only model plus tool time.",
    ]


def build_mini_v03_sweep_report(repo_root: Path, sweep_dir: Path) -> dict[str, Any]:
    """Build one deterministic-verifier report without private run content."""
    resolved_sweep = resolve_repo_path(repo_root, sweep_dir)
    sweep_path = resolved_sweep / "sweep.json"
    sweep = load_json(sweep_path)
    if sweep.get("harness_id") != "mini-v0.3" or sweep.get("status") != "complete":
        raise RunnerError("Mini v0.3 report requires one complete sweep")
    if sweep.get("complete_unit_count") != sweep.get("unit_count"):
        raise RunnerError("Mini v0.3 report requires every unit to be complete")
    loaded_plan = load_mini_v03_sweep_plan(repo_root, Path(sweep["plan"]["path"]))
    if loaded_plan["plan_sha256"] != sweep["plan"]["sha256"]:
        raise RunnerError("Mini v0.3 report source plan hash mismatch")
    harness = load_mini_v03_harness(repo_root, loaded_plan["harness_path"])

    units = [_public_unit(repo_root, unit) for unit in sweep["units"]]
    plan = loaded_plan["plan"]
    by_model = [
        _aggregate_group(
            [unit for unit in units if unit["model"] == deployment["name"]],
            key="model",
            value=deployment["name"],
        )
        for deployment in plan["deployments"]
    ]
    by_case = [
        {
            **_aggregate_group(
                [unit for unit in units if unit["case_id"] == case["case_id"]],
                key="case_id",
                value=case["case_id"],
            ),
            "case_label": CASE_LABELS.get(case["case_id"], case["case_id"]),
            "language": case["language"],
        }
        for case in plan["cases"]
    ]
    failures = Counter(
        unit["failure_type"]
        for unit in units
        if unit["failure_type"] is not None
    )
    category_discrepancies = [
        {
            "position": unit["position"],
            "model": unit["model"],
            "case_id": unit["case_id"],
            "failure_type": unit["failure_type"],
            "raw_failure_category": unit["raw_failure_category"],
            "effective_failure_category": unit["effective_failure_category"],
            "reporting_resolution": (
                "Treat an agent active-time ceiling as an agent failure while "
                "preserving the raw adapter classification."
            ),
        }
        for unit in units
        if unit["raw_failure_category"] != unit["effective_failure_category"]
    ]
    limits = harness["protocol"]["normal_capability_limits"]
    return {
        "schema_version": "1.0.0",
        "report_id": "track-b-mini-capability-sweep-v0.3",
        "generated_at": utc_now(),
        "evidence_class": "measured_capability_sweep",
        "source": {
            "sweep_id": sweep["sweep_id"],
            "sweep_record_sha256": sha256_file(sweep_path),
            "plan_id": sweep["plan"]["plan_id"],
            "plan_path": sweep["plan"]["path"],
            "plan_sha256": sweep["plan"]["sha256"],
            "execution_git_commit": sweep["git_commit"],
            "ollama_version": sweep["ollama_version"],
            "started_at": sweep["started_at"],
            "completed_at": sweep["completed_at"],
        },
        "method": {
            "track": "B",
            "harness": "mini-v0.3",
            "models": len(plan["deployments"]),
            "cases": len(plan["cases"]),
            "runs_per_configuration": 1,
            "automatic_retries": 0,
            "maximum_active_wall_time_seconds": limits[
                "maximum_active_wall_time_seconds"
            ],
            "provider_request_timeout_seconds": limits[
                "provider_request_timeout_seconds"
            ],
            "turns_total_tokens_and_protocol_errors": "measurement_only",
            "primary_outcome": "verified_success",
        },
        "summary": {
            "run_count": len(units),
            "complete_run_count": len(units),
            "verified_success_count": sum(
                unit["verified_success"] for unit in units
            ),
            "verifier_success_count": sum(
                unit["verifier_success"] for unit in units
            ),
            "runtime_success_count": sum(unit["runtime_success"] for unit in units),
            "interrupted_attempt_count": sum(
                unit["interrupted_attempt_count"] for unit in units
            ),
            "effective_failure_counts": dict(sorted(failures.items())),
        },
        "by_model": by_model,
        "by_case": by_case,
        "units": units,
        "findings": _findings(by_model, by_case),
        "diagnostics": {
            "failure_category_discrepancies": category_discrepancies,
        },
        "caveats": [
            "Each model-task configuration has n=1. These are Capability Sweep observations, not reliability probabilities or performance distributions.",
            "Median and range values summarize heterogeneous tasks or models; they are descriptive and not tail estimates.",
            "Pi v0.3 and Mini v0.3 are complete-system deployments with different prompts, protocols, tool implementations, context accumulation and error handling. Cross-harness differences are not one-factor causal effects.",
            "No composite quality-speed score or universal model ranking is inferred from three coding cases.",
            "Raw failure classifications are preserved. Known active-time classification discrepancies are resolved only in the public report and must be fixed in a future harness version, not by mutating the frozen adapter used for this sweep.",
        ],
        "privacy": {
            "raw_model_text_included": False,
            "candidate_source_included": False,
            "test_stdout_or_stderr_included": False,
            "absolute_local_paths_included": False,
        },
    }


def _cell(unit: dict[str, Any]) -> str:
    mark = "PASS" if unit["verified_success"] else "FAIL"
    return f"{mark} ({unit['active_duration_seconds']:.1f}s)"


def render_mini_v03_sweep_markdown(report: dict[str, Any]) -> str:
    """Render a compact public Markdown interpretation of the report."""
    units = report["units"]
    lines = [
        "# Track B Mini v0.3 Capability Sweep",
        "",
        "## Outcome",
        "",
        (
            f"The frozen {report['summary']['run_count']}-run sweep completed "
            f"with **{report['summary']['verified_success_count']}/"
            f"{report['summary']['run_count']} verified successful outcomes**."
        ),
        "",
        "| Model | PHP | JavaScript | Python | Verified | Verifier | Median active time |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    case_order = [
        "coding.dev.php-payment-result-migration",
        "coding.dev.async-cache-coalescing",
        "coding.dev.pagination-cycle-guard",
    ]
    for aggregate in report["by_model"]:
        model = aggregate["model"]
        model_units = {
            unit["case_id"]: unit for unit in units if unit["model"] == model
        }
        cells = [_cell(model_units[case_id]) for case_id in case_order]
        lines.append(
            f"| `{model}` | {' | '.join(cells)} | "
            f"{aggregate['verified_success_count']}/3 | "
            f"{aggregate['verifier_success_count']}/3 | "
            f"{aggregate['active_duration_seconds']['median']:.1f}s |"
        )
    lines.extend(
        [
            "",
            "## Results by case",
            "",
            "| Case | Verified | Verifier | Median | Range |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for aggregate in report["by_case"]:
        duration = aggregate["active_duration_seconds"]
        lines.append(
            f"| {aggregate['case_label']} | "
            f"{aggregate['verified_success_count']}/5 | "
            f"{aggregate['verifier_success_count']}/5 | "
            f"{duration['median']:.1f}s | "
            f"{duration['minimum']:.1f}–{duration['maximum']:.1f}s |"
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
            f"- Sweep: `{report['source']['sweep_id']}`",
            f"- Plan: `{report['source']['plan_id']}`",
            f"- Ollama: `{report['source']['ollama_version']}`",
            f"- Execution commit: `{report['source']['execution_git_commit']}`",
            f"- Sweep SHA-256: `{report['source']['sweep_record_sha256']}`",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sweep-dir", type=Path, required=True)
    parser.add_argument(
        "--json-out",
        type=Path,
        default=Path("reports/coding/track-b-mini-capability-sweep-v0.3.json"),
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        default=Path("reports/coding/track-b-mini-capability-sweep-v0.3.md"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    try:
        report = build_mini_v03_sweep_report(repo_root, args.sweep_dir)
        json_out = resolve_repo_path(repo_root, args.json_out)
        markdown_out = resolve_repo_path(repo_root, args.markdown_out)
        write_json(json_out, report)
        markdown_out.parent.mkdir(parents=True, exist_ok=True)
        markdown_out.write_text(
            render_mini_v03_sweep_markdown(report), encoding="utf-8"
        )
    except (OSError, RunnerError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            {
                "status": "complete",
                "report_id": report["report_id"],
                "verified_success_count": report["summary"][
                    "verified_success_count"
                ],
                "json_path": str(json_out),
                "markdown_path": str(markdown_out),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
