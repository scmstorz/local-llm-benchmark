"""Build a public-safe cross-case report from one completed Pi v0.3 sweep."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from .pi_v03_sweep import load_pi_v03_sweep_plan
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


def _rounded(value: Any, digits: int = 2) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(float(value), digits)
    return None


def _effective_failure(unit: dict[str, Any]) -> str | None:
    if unit["outcome"]["verified_success"]:
        return None
    termination = unit["trajectory"].get("termination_reason")
    if termination and termination != "agent_end":
        return str(termination)
    return unit["outcome"].get("failure_type") or "verification_failed"


def _public_unit(unit: dict[str, Any]) -> dict[str, Any]:
    trajectory = unit["trajectory"]
    outcome = unit["outcome"]
    public_tests = outcome.get("public_tests") or {}
    hidden_tests = outcome.get("hidden_tests") or {}
    return {
        "position": unit["position"],
        "run_id": unit["run_id"],
        "model": unit["model"],
        "deployment_id": unit["deployment_id"],
        "case_id": unit["case_id"],
        "case_label": CASE_LABELS.get(unit["case_id"], unit["case_id"]),
        "runtime_success": bool(outcome["runtime_success"]),
        "agent_termination_valid_raw": bool(outcome["agent_termination_valid"]),
        "verifier_success": bool(outcome["verifier_success"]),
        "verified_success": bool(outcome["verified_success"]),
        "raw_failure_category": outcome.get("failure_category"),
        "raw_failure_type": outcome.get("failure_type"),
        "trajectory_termination_reason": trajectory.get("termination_reason"),
        "effective_failure_type": _effective_failure(unit),
        "public_tests_passed": bool(public_tests.get("passed")),
        "hidden_tests_passed": bool(hidden_tests.get("passed")),
        "active_duration_seconds": _rounded(
            trajectory.get("active_wall_time_seconds")
        ),
        "agent_turns": trajectory.get("agent_turns"),
        "tool_calls": trajectory.get("tool_calls"),
        "failed_tool_calls": trajectory.get("failed_tool_calls"),
        "file_reads": trajectory.get("file_reads"),
        "file_writes": trajectory.get("file_writes"),
        "public_test_runs": trajectory.get("public_test_runs"),
        "input_tokens": trajectory.get("input_tokens"),
        "output_tokens": trajectory.get("output_tokens"),
        "time_to_first_successful_public_verification_seconds": _rounded(
            trajectory.get("time_to_first_successful_public_verification_seconds")
        ),
    }


def _aggregate_group(
    group: list[dict[str, Any]], *, key: str, value: str
) -> dict[str, Any]:
    durations = [item["active_duration_seconds"] for item in group]
    return {
        key: value,
        "run_count": len(group),
        "verified_success_count": sum(item["verified_success"] for item in group),
        "verifier_success_count": sum(item["verifier_success"] for item in group),
        "runtime_success_count": sum(item["runtime_success"] for item in group),
        "valid_agent_termination_count_raw": sum(
            item["agent_termination_valid_raw"] for item in group
        ),
        "active_duration_seconds": {
            "raw": durations,
            "minimum": _rounded(min(durations)),
            "median": _rounded(statistics.median(durations)),
            "maximum": _rounded(max(durations)),
            "total": _rounded(sum(durations)),
        },
        "total_agent_turns": sum(item["agent_turns"] for item in group),
        "total_tool_calls": sum(item["tool_calls"] for item in group),
        "total_output_tokens": sum(item["output_tokens"] for item in group),
        "effective_failures": dict(
            sorted(
                Counter(
                    item["effective_failure_type"]
                    for item in group
                    if item["effective_failure_type"] is not None
                ).items()
            )
        ),
    }


def build_pi_v03_sweep_report(repo_root: Path, sweep_dir: Path) -> dict[str, Any]:
    """Build one deterministic-verifier report without raw output or local paths."""
    resolved_sweep = resolve_repo_path(repo_root, sweep_dir)
    sweep_path = resolved_sweep / "sweep.json"
    sweep = load_json(sweep_path)
    if sweep.get("harness_id") != "pi-v0.3" or sweep.get("status") != "complete":
        raise RunnerError("Pi v0.3 report requires one complete sweep")
    if sweep.get("complete_unit_count") != sweep.get("unit_count"):
        raise RunnerError("Pi v0.3 report requires every unit to be complete")
    plan_path = Path(sweep["plan"]["path"])
    loaded_plan = load_pi_v03_sweep_plan(repo_root, plan_path)
    if loaded_plan["plan_sha256"] != sweep["plan"]["sha256"]:
        raise RunnerError("Pi v0.3 report source plan hash mismatch")

    units = [_public_unit(unit) for unit in sweep["units"]]
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
    failure_counts = Counter(
        unit["effective_failure_type"]
        for unit in units
        if unit["effective_failure_type"] is not None
    )
    precedence_discrepancies = [
        {
            "position": unit["position"],
            "model": unit["model"],
            "case_id": unit["case_id"],
            "raw_failure_type": unit["raw_failure_type"],
            "trajectory_termination_reason": unit[
                "trajectory_termination_reason"
            ],
            "reporting_resolution": (
                "Use the explicit terminal trajectory condition as the primary "
                "effective failure while preserving the verifier result."
            ),
        }
        for unit in units
        if unit["trajectory_termination_reason"] not in {None, "agent_end"}
        and unit["raw_failure_type"] != unit["trajectory_termination_reason"]
    ]
    verifier_without_verified = [
        {
            "position": unit["position"],
            "model": unit["model"],
            "case_id": unit["case_id"],
            "effective_failure_type": unit["effective_failure_type"],
        }
        for unit in units
        if unit["verifier_success"] and not unit["verified_success"]
    ]
    return {
        "schema_version": "1.0.0",
        "report_id": "track-b-pi-capability-sweep-v0.3",
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
            "harness": "pi-v0.3",
            "pi_version": "0.84.4",
            "models": len(plan["deployments"]),
            "cases": len(plan["cases"]),
            "runs_per_configuration": 1,
            "automatic_retries": 0,
            "maximum_active_wall_time_seconds": plan["shared_inference"][
                "maximum_active_wall_time_seconds"
            ],
            "provider_request_timeout_seconds": plan["shared_inference"][
                "provider_request_timeout_seconds"
            ],
            "turns_and_total_tokens": "measurement_only",
            "primary_outcome": "verified_success",
        },
        "summary": {
            "run_count": len(units),
            "complete_run_count": sum(
                unit["position"] is not None for unit in units
            ),
            "verified_success_count": sum(
                unit["verified_success"] for unit in units
            ),
            "verifier_success_count": sum(
                unit["verifier_success"] for unit in units
            ),
            "runtime_success_count": sum(
                unit["runtime_success"] for unit in units
            ),
            "effective_failure_counts": dict(sorted(failure_counts.items())),
        },
        "by_model": by_model,
        "by_case": by_case,
        "units": units,
        "diagnostics": {
            "termination_precedence_discrepancies": precedence_discrepancies,
            "verifier_success_without_verified_success": verifier_without_verified,
        },
        "findings": [
            "qwen3.8:27b-mlx is the only deployment with verified success on all three cases in this single-run screen.",
            "All five deployments solve the PHP case; only qwen3.8:27b-mlx reaches verified success on the JavaScript case.",
            "Three deployments solve Python, but active duration ranges from about 195 seconds to about 780 seconds among those successes.",
            "ornith-1.5:35b leaves a fully verifier-passing JavaScript workspace when the 900-second active task limit terminates the agent, so the user-relevant outcome remains a failure.",
            "muse-glimmer:30b-mlx succeeds on PHP but ends with an invalid model stream on both JavaScript and Python, showing that Track A text quality does not imply stable agentic system behavior.",
        ],
        "caveats": [
            "Each model-task configuration has n=1. These are Capability Sweep observations, not reliability probabilities or performance distributions.",
            "Median and range values summarize three heterogeneous per-model runs or five per-case runs; they are descriptive and not tail estimates.",
            "The host was unavailable for part of the sweep. Per-run active monotonic duration is reported; total sweep elapsed time is not treated as performance evidence.",
            "The raw Qwen 3.6 Python outcome prioritizes its red public verifier, while its trajectory records the terminal emergency test-run safeguard. The public report preserves both and uses the explicit terminal condition as the effective failure.",
            "No composite quality-speed score or universal model ranking is inferred from three heterogeneous coding cases.",
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


def render_pi_v03_sweep_markdown(report: dict[str, Any]) -> str:
    """Render a compact public Markdown interpretation of the report."""
    units = report["units"]
    lines = [
        "# Track B Pi v0.3 Capability Sweep",
        "",
        "## Outcome",
        "",
        (
            f"The frozen 15-run sweep completed with "
            f"**{report['summary']['verified_success_count']}/15 verified "
            "successful outcomes**. `qwen3.8:27b-mlx` is the only model that "
            "passes all three cases in this single-run screen."
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
        model_units = {unit["case_id"]: unit for unit in units if unit["model"] == model}
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
    lines.extend(
        [
            "",
            "The Ornith JavaScript run is deliberately a failure despite a green "
            "final verifier: the workspace is verifier-passing when the preregistered "
            "900-second limit terminates the still-running agent. This distinction is "
            "the intended meaning of verified success.",
            "",
            "Qwen 3.6 on Python reached 59 turns and 30 public test runs before the "
            "emergency safeguard terminated the trajectory. Its final workspace also "
            "failed verification. The raw outcome labels the red public tests as the "
            "failure, while the trajectory carries the more causally prior safeguard "
            "termination; both facts remain preserved.",
            "",
            "## Methodological limits",
            "",
        ]
    )
    lines.extend(f"- {caveat}" for caveat in report["caveats"])
    lines.extend(
        [
            "",
            "## Provenance",
            "",
            f"- Sweep: `{report['source']['sweep_id']}`",
            f"- Plan: `{report['source']['plan_id']}`",
            f"- Ollama: `{report['source']['ollama_version']}`",
            f"- Pi: `{report['method']['pi_version']}`",
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
        default=Path("reports/coding/track-b-pi-capability-sweep-v0.3.json"),
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        default=Path("reports/coding/track-b-pi-capability-sweep-v0.3.md"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    try:
        report = build_pi_v03_sweep_report(repo_root, args.sweep_dir)
        json_out = resolve_repo_path(repo_root, args.json_out)
        markdown_out = resolve_repo_path(repo_root, args.markdown_out)
        write_json(json_out, report)
        markdown_out.parent.mkdir(parents=True, exist_ok=True)
        markdown_out.write_text(
            render_pi_v03_sweep_markdown(report), encoding="utf-8"
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
