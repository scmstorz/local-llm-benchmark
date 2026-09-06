"""Build a public-safe report for measured log-incident v0.5 sweeps."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from .log_incident_sweep_v05 import (
    HARNESS_IDS,
    load_log_incident_sweep_plan,
)
from .runner import (
    RunnerError,
    load_json,
    resolve_repo_path,
    sha256_file,
    utc_now,
    write_json,
)


CASE_LABELS = {
    "agentic.ops.checkout-pool-regression": "Checkout pool regression",
    "agentic.ops.retry-queue-amplification": "Retry queue amplification",
    "agentic.ops.clock-skew-partial-recovery": "Clock skew partial recovery",
}
HARNESS_LABELS = {
    "mini-log-v0.5": "Mini",
    "pi-log-v0.5": "Pi 0.84.4",
}


def _rounded(value: Any, digits: int = 2) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(float(value), digits)
    return None


def _public_unit(repo_root: Path, unit: dict[str, Any]) -> dict[str, Any]:
    if unit["status"] == "failed":
        outcome = unit.get("outcome") or {}
        return {
            "position": unit["position"],
            "run_id": unit.get("run_id"),
            "harness_id": unit["harness_id"],
            "harness_label": HARNESS_LABELS.get(
                unit["harness_id"], unit["harness_id"]
            ),
            "model": unit["model"],
            "deployment_id": unit["deployment_id"],
            "case_id": unit["case_id"],
            "case_label": CASE_LABELS.get(unit["case_id"], unit["case_id"]),
            "runtime_success": bool(outcome.get("runtime_success")),
            "agent_termination_valid": bool(
                outcome.get("agent_termination_valid")
            ),
            "semantic_verifier_success": bool(
                outcome.get("semantic_verifier_success")
            ),
            "semantic_verified_success": False,
            "strict_transport_compliance": bool(
                outcome.get("strict_transport_compliance")
            ),
            "response_normalization_applied": False,
            "failure_category": outcome.get("failure_category")
            or "infrastructure_or_control_failure",
            "failure_type": outcome.get("failure_type")
            or unit.get("error", {}).get("type")
            or "other",
            "essential_checks_passed": None,
            "essential_checks_total": None,
            "failed_check_ids": [],
            "active_wall_time_seconds": None,
            "agent_turns": None,
            "model_requests": None,
            "tool_calls": None,
            "file_reads": None,
            "repeated_file_reads": None,
            "failed_tool_calls": None,
            "protocol_errors": None,
            "input_tokens": None,
            "output_tokens": None,
        }
    run_dir_value = unit.get("run_dir")
    if not isinstance(run_dir_value, str):
        raise RunnerError("Complete log-incident unit lacks a raw run directory")
    run_dir = resolve_repo_path(repo_root, Path(run_dir_value))
    run_path = run_dir / "run.json"
    run = load_json(run_path)
    if (
        run.get("state") != "complete"
        or run.get("run_id") != unit.get("run_id")
        or run.get("case", {}).get("case_id") != unit["case_id"]
    ):
        raise RunnerError("Complete log-incident unit does not match its raw run")
    outcome = run.get("outcome")
    trajectory = run.get("trajectory")
    verification = run.get("verification")
    if not all(isinstance(item, dict) for item in (outcome, trajectory, verification)):
        raise RunnerError("Complete log-incident run lacks terminal evidence")
    checks = verification.get("checks")
    if not isinstance(checks, list):
        raise RunnerError("Complete log-incident run lacks verifier checks")
    return {
        "position": unit["position"],
        "run_id": unit["run_id"],
        "private_run_record_sha256": sha256_file(run_path),
        "harness_id": unit["harness_id"],
        "harness_label": HARNESS_LABELS.get(unit["harness_id"], unit["harness_id"]),
        "model": unit["model"],
        "deployment_id": unit["deployment_id"],
        "case_id": unit["case_id"],
        "case_label": CASE_LABELS.get(unit["case_id"], unit["case_id"]),
        "runtime_success": bool(outcome.get("runtime_success")),
        "agent_termination_valid": bool(outcome.get("agent_termination_valid")),
        "semantic_verifier_success": bool(
            outcome.get("semantic_verifier_success")
        ),
        "semantic_verified_success": bool(
            outcome.get("semantic_verified_success")
        ),
        "strict_transport_compliance": bool(
            outcome.get("strict_transport_compliance")
        ),
        "response_normalization_applied": bool(
            trajectory.get("response_normalization_applied")
        ),
        "failure_category": outcome.get("failure_category"),
        "failure_type": outcome.get("failure_type"),
        "essential_checks_passed": verification.get("essential_pass_count"),
        "essential_checks_total": verification.get("essential_check_count"),
        "failed_check_ids": [
            item.get("check_id")
            for item in checks
            if item.get("essential") is True and item.get("passed") is not True
        ],
        "active_wall_time_seconds": _rounded(
            trajectory.get("active_wall_time_seconds")
        ),
        "agent_turns": trajectory.get("agent_turns"),
        "model_requests": trajectory.get("model_requests"),
        "tool_calls": trajectory.get("tool_calls"),
        "file_reads": trajectory.get("file_reads"),
        "repeated_file_reads": trajectory.get("repeated_file_reads"),
        "failed_tool_calls": trajectory.get("failed_tool_calls"),
        "protocol_errors": trajectory.get("protocol_errors"),
        "input_tokens": trajectory.get("input_tokens"),
        "output_tokens": trajectory.get("output_tokens"),
    }


def _aggregate(units: list[dict[str, Any]], **identity: str) -> dict[str, Any]:
    complete_durations = [
        float(unit["active_wall_time_seconds"])
        for unit in units
        if unit["active_wall_time_seconds"] is not None
    ]
    checks_passed = [
        int(unit["essential_checks_passed"])
        for unit in units
        if unit["essential_checks_passed"] is not None
    ]
    checks_total = [
        int(unit["essential_checks_total"])
        for unit in units
        if unit["essential_checks_total"] is not None
    ]
    return {
        **identity,
        "run_count": len(units),
        "runtime_success_count": sum(unit["runtime_success"] for unit in units),
        "valid_agent_termination_count": sum(
            unit["agent_termination_valid"] for unit in units
        ),
        "semantic_verifier_success_count": sum(
            unit["semantic_verifier_success"] for unit in units
        ),
        "semantic_verified_success_count": sum(
            unit["semantic_verified_success"] for unit in units
        ),
        "strict_transport_compliance_count": sum(
            unit["strict_transport_compliance"] for unit in units
        ),
        "response_normalization_applied_count": sum(
            unit["response_normalization_applied"] for unit in units
        ),
        "essential_checks_passed": sum(checks_passed),
        "essential_checks_observed": sum(checks_total),
        "active_wall_time_seconds": {
            "raw": complete_durations,
            "minimum": _rounded(min(complete_durations)) if complete_durations else None,
            "median": _rounded(statistics.median(complete_durations))
            if complete_durations
            else None,
            "maximum": _rounded(max(complete_durations)) if complete_durations else None,
            "total": _rounded(sum(complete_durations)) if complete_durations else None,
        },
        "total_input_tokens": sum(
            int(unit["input_tokens"] or 0) for unit in units
        ),
        "total_output_tokens": sum(
            int(unit["output_tokens"] or 0) for unit in units
        ),
        "failures": dict(
            sorted(
                Counter(
                    unit["failure_type"]
                    for unit in units
                    if unit["failure_type"] is not None
                ).items()
            )
        ),
    }


def build_log_incident_sweep_report(
    repo_root: Path,
    sweep_dir: Path,
    *,
    json_output: Path = Path(
        "reports/agentic/log-incident-capability-sweep-v0.5.json"
    ),
    markdown_output: Path = Path(
        "reports/agentic/log-incident-capability-sweep-v0.5.md"
    ),
) -> dict[str, Any]:
    """Create JSON and Markdown reports without raw candidate content."""
    resolved = resolve_repo_path(repo_root, sweep_dir)
    sweep_path = resolved / "sweep.json"
    sweep = load_json(sweep_path)
    if sweep.get("status") not in {"complete", "complete_with_failures"}:
        raise RunnerError("Log-incident report requires a terminal sweep")
    if any(unit.get("status") not in {"complete", "failed"} for unit in sweep["units"]):
        raise RunnerError("Log-incident report requires every unit to be terminal")
    loaded = load_log_incident_sweep_plan(repo_root, Path(sweep["plan"]["path"]))
    if loaded["sha256"] != sweep["plan"]["sha256"]:
        raise RunnerError("Log-incident report source plan hash mismatch")
    units = [_public_unit(repo_root, unit) for unit in sweep["units"]]
    plan = loaded["plan"]
    by_system_model = [
        _aggregate(
            [
                unit
                for unit in units
                if unit["harness_id"] == harness["harness_id"]
                and unit["model"] == deployment["name"]
            ],
            harness_id=harness["harness_id"],
            harness_label=HARNESS_LABELS.get(
                harness["harness_id"], harness["harness_id"]
            ),
            model=deployment["name"],
        )
        for harness in plan["harnesses"]
        for deployment in plan["deployments"]
    ]
    by_case = [
        _aggregate(
            [unit for unit in units if unit["case_id"] == case["case_id"]],
            case_id=case["case_id"],
            case_label=CASE_LABELS.get(case["case_id"], case["case_id"]),
        )
        for case in plan["cases"]
    ]
    by_model = [
        _aggregate(
            [unit for unit in units if unit["model"] == deployment["name"]],
            model=deployment["name"],
        )
        for deployment in plan["deployments"]
    ]
    by_harness = [
        _aggregate(
            [unit for unit in units if unit["harness_id"] == harness["harness_id"]],
            harness_id=harness["harness_id"],
            harness_label=HARNESS_LABELS.get(
                harness["harness_id"], harness["harness_id"]
            ),
        )
        for harness in plan["harnesses"]
    ]
    report = {
        "schema_version": "1.0.0",
        "report_id": "log-incident-capability-sweep-v0.5",
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
            "task_family": "agentic_log_incident_analysis",
            "harnesses": list(HARNESS_IDS),
            "models": len(plan["deployments"]),
            "cases": 3,
            "runs_per_configuration": 1,
            "automatic_retries": 0,
            "primary_outcome": "semantic_verified_success",
            "secondary_outcome": "strict_transport_compliance",
            "supplemental_free_text_claim_review_required": True,
            "deterministic_success_is_not_final_quality_acceptance": True,
            "comparison_unit": "complete_system",
        },
        "summary": _aggregate(units),
        "by_model": by_model,
        "by_system_model": by_system_model,
        "by_harness": by_harness,
        "by_case": by_case,
        "units": units,
        "caveats": [
            "Each system-case configuration has n=1; this is a capability sweep, not a reliability, quality-stochasticity or latency-tail estimate.",
            "Duration summaries combine heterogeneous cases and are descriptive ranges and medians, not tail percentiles.",
            "Mini and Pi are complete-system conditions with different prompts, tool protocols and context handling; no one-factor causal harness claim is allowed.",
            "Historical v0.2, v0.3 and v0.4 attempts and the excluded v0.5 specification confirmation are not pooled with this measured sweep.",
            "A deterministically normalized report may be a semantic success while strict transport compliance remains false.",
            "Deterministic structured success is not final quality acceptance; all free-text claims require the separately recorded human grounding review.",
            "No composite quality-speed score or universal model ranking is calculated.",
        ],
        "privacy": {
            "candidate_reports_included": False,
            "raw_log_contents_included": False,
            "hidden_ground_truth_included": False,
            "absolute_paths_included": False,
            "raw_run_records_public": False,
        },
    }
    json_path = resolve_repo_path(
        repo_root,
        json_output,
    )
    markdown_path = resolve_repo_path(
        repo_root,
        markdown_output,
    )
    write_json(json_path, report)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return {
        "report_id": report["report_id"],
        "json_path": _relative(repo_root, json_path),
        "markdown_path": _relative(repo_root, markdown_path),
        "run_count": len(units),
        "semantic_verified_success_count": report["summary"][
            "semantic_verified_success_count"
        ],
        "strict_transport_compliance_count": report["summary"][
            "strict_transport_compliance_count"
        ],
    }


def _relative(repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Agentic Log Incident v0.5 Capability Sweep",
        "",
        "This measured sweep compares complete deployed systems. Each cell is",
        "executed once to map capability, not to estimate model reliability.",
        "",
        "## Per model and harness",
        "",
        "| Harness | Model | Semantic success | Strict transport | Runtime | Median active time |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for item in report["by_system_model"]:
        median = item["active_wall_time_seconds"]["median"]
        median_text = "n/a" if median is None else f"{median:.2f} s"
        lines.append(
            f"| {item['harness_label']} | `{item['model']}` | "
            f"{item['semantic_verified_success_count']}/{item['run_count']} | "
            f"{item['strict_transport_compliance_count']}/{item['run_count']} | "
            f"{item['runtime_success_count']}/{item['run_count']} | {median_text} |"
        )
    lines.extend(
        [
            "",
            "## Per model across both complete systems",
            "",
            "| Model | Semantic success | Strict transport | Runtime | Median active time |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in report["by_model"]:
        median = item["active_wall_time_seconds"]["median"]
        median_text = "n/a" if median is None else f"{median:.2f} s"
        lines.append(
            f"| `{item['model']}` | "
            f"{item['semantic_verified_success_count']}/{item['run_count']} | "
            f"{item['strict_transport_compliance_count']}/{item['run_count']} | "
            f"{item['runtime_success_count']}/{item['run_count']} | {median_text} |"
        )
    lines.extend(
        [
            "",
            "## Per case",
            "",
            "| Case | Semantic successes | Strict transport | Runtime-complete outcomes |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for item in report["by_case"]:
        lines.append(
            f"| {item['case_label']} | {item['semantic_verified_success_count']}/{item['run_count']} | "
            f"{item['strict_transport_compliance_count']}/{item['run_count']} | "
            f"{item['runtime_success_count']}/{item['run_count']} |"
        )
    lines.extend(["", "## Interpretation boundaries", ""])
    lines.extend(f"- {item}" for item in report["caveats"])
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sweep-dir", type=Path, required=True)
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path(
            "reports/agentic/log-incident-capability-sweep-v0.5.json"
        ),
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=Path(
            "reports/agentic/log-incident-capability-sweep-v0.5.md"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = build_log_incident_sweep_report(
            Path.cwd().resolve(),
            args.sweep_dir,
            json_output=args.json_output,
            markdown_output=args.markdown_output,
        )
    except (OSError, RunnerError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
