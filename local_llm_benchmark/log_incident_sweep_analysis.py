"""Build a public-safe post-hoc analysis of a completed log-incident sweep."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from .log_incident_v02 import verify_incident_report_v02
from .runner import (
    RunnerError,
    load_json,
    resolve_repo_path,
    sha256_file,
    utc_now,
    write_json,
)


DEFAULT_PRIMARY_REPORT = Path(
    "reports/agentic/log-incident-capability-sweep-v0.2.json"
)
DEFAULT_JSON_OUTPUT = Path(
    "reports/agentic/log-incident-capability-sweep-v0.2-analysis.json"
)
DEFAULT_MARKDOWN_OUTPUT = Path(
    "reports/agentic/log-incident-capability-sweep-v0.2-analysis.md"
)


def _rounded(value: float | int | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _embedded_json_object(value: str) -> tuple[dict[str, Any] | None, str | None]:
    """Extract one embedded object without repairing its internal structure."""
    decoder = json.JSONDecoder()
    for position, character in enumerate(value):
        if character != "{":
            continue
        try:
            candidate, consumed = decoder.raw_decode(value[position:])
        except json.JSONDecodeError:
            continue
        if not isinstance(candidate, dict):
            continue
        prefix = value[:position].strip()
        suffix = value[position + consumed :].strip()
        if "```" in prefix or "```" in suffix:
            envelope = "markdown_code_fence"
        elif prefix or suffix:
            envelope = "surrounding_text"
        else:
            envelope = "none"
        return candidate, envelope
    return None, None


def _schema_valid(unit: dict[str, Any]) -> bool:
    """The frozen verifier reaches all 14 checks only after schema acceptance."""
    return unit.get("essential_checks_total") == 14


def _group_summary(units: list[dict[str, Any]], **identity: str) -> dict[str, Any]:
    schema_units = [unit for unit in units if _schema_valid(unit)]
    durations = [
        float(unit["active_wall_time_seconds"])
        for unit in units
        if isinstance(unit.get("active_wall_time_seconds"), (int, float))
    ]
    failed_checks = Counter(
        check_id
        for unit in schema_units
        for check_id in unit.get("failed_check_ids", [])
    )
    return {
        **identity,
        "run_count": len(units),
        "runtime_success_count": sum(bool(unit["runtime_success"]) for unit in units),
        "verified_success_count": sum(
            bool(unit["verified_success"]) for unit in units
        ),
        "schema_valid_report_count": len(schema_units),
        "schema_valid_checks_passed": sum(
            int(unit["essential_checks_passed"]) for unit in schema_units
        ),
        "schema_valid_checks_total": sum(
            int(unit["essential_checks_total"]) for unit in schema_units
        ),
        "schema_valid_failed_checks": dict(
            sorted(failed_checks.items(), key=lambda item: (-item[1], item[0]))
        ),
        "failure_types": dict(
            sorted(
                Counter(
                    unit["failure_type"]
                    for unit in units
                    if unit.get("failure_type") is not None
                ).items()
            )
        ),
        "active_wall_time_seconds": {
            "raw": durations,
            "minimum": _rounded(min(durations)) if durations else None,
            "median": _rounded(statistics.median(durations)) if durations else None,
            "maximum": _rounded(max(durations)) if durations else None,
            "total": _rounded(sum(durations)) if durations else None,
        },
    }


def _protocol_sensitivity(
    repo_root: Path,
    sweep: dict[str, Any],
    public_units: list[dict[str, Any]],
) -> dict[str, Any]:
    raw_by_position = {unit["position"]: unit for unit in sweep["units"]}
    candidates = [
        unit
        for unit in public_units
        if unit.get("failure_type") == "missing_or_malformed_report"
    ]
    recovered: list[dict[str, Any]] = []
    responses_available = 0
    for unit in candidates:
        raw_unit = raw_by_position.get(unit["position"])
        if not isinstance(raw_unit, dict) or not isinstance(raw_unit.get("run_dir"), str):
            continue
        run_dir = resolve_repo_path(repo_root, Path(raw_unit["run_dir"]))
        run_path = run_dir / "run.json"
        run = load_json(run_path)
        if run.get("run_id") != unit.get("run_id"):
            raise RunnerError("Sensitivity run identity mismatch")
        artifacts = run.get("artifacts") or {}
        response_name = artifacts.get("candidate_response")
        if not isinstance(response_name, str):
            continue
        responses_available += 1
        response_path = resolve_repo_path(run_dir, Path(response_name))
        expected_hash = artifacts.get("candidate_response_sha256")
        if isinstance(expected_hash, str) and sha256_file(response_path) != expected_hash:
            raise RunnerError("Candidate response hash mismatch")
        report, envelope = _embedded_json_object(
            response_path.read_text(encoding="utf-8")
        )
        if report is None:
            continue
        verification = verify_incident_report_v02(
            repo_root, Path(raw_unit["case_path"]), report
        )
        recovered.append(
            {
                "position": unit["position"],
                "harness_id": unit["harness_id"],
                "harness_label": unit["harness_label"],
                "model": unit["model"],
                "case_id": unit["case_id"],
                "case_label": unit["case_label"],
                "envelope": envelope,
                "schema_valid_after_recovery": (
                    verification["essential_check_count"] == 14
                ),
                "checks_passed_after_recovery": verification[
                    "essential_pass_count"
                ],
                "checks_total_after_recovery": verification[
                    "essential_check_count"
                ],
                "verified_success_after_recovery": verification[
                    "verified_success"
                ],
                "failed_check_ids_after_recovery": [
                    check["check_id"]
                    for check in verification["checks"]
                    if check.get("essential") is True
                    and check.get("passed") is not True
                ],
            }
        )
    return {
        "status": "post_hoc_exploratory_not_preregistered",
        "primary_outcomes_changed": False,
        "strict_invalid_report_count": len(candidates),
        "responses_available_for_analysis": responses_available,
        "embedded_object_recovered_count": len(recovered),
        "schema_valid_after_recovery_count": sum(
            item["schema_valid_after_recovery"] for item in recovered
        ),
        "verified_success_after_recovery_count": sum(
            item["verified_success_after_recovery"] for item in recovered
        ),
        "recovered_units": recovered,
        "interpretation": (
            "Only an outer prose or Markdown envelope was removed. The same frozen "
            "verifier was then applied, and no primary outcome was changed."
        ),
    }


def build_log_incident_sweep_analysis(
    repo_root: Path,
    sweep_dir: Path,
    primary_report_path: Path = DEFAULT_PRIMARY_REPORT,
    json_output_path: Path = DEFAULT_JSON_OUTPUT,
    markdown_output_path: Path = DEFAULT_MARKDOWN_OUTPUT,
) -> dict[str, Any]:
    """Build a derived diagnostic without modifying primary measurements."""
    resolved_sweep_dir = resolve_repo_path(repo_root, sweep_dir)
    sweep_path = resolved_sweep_dir / "sweep.json"
    sweep = load_json(sweep_path)
    if sweep.get("status") not in {"complete", "complete_with_failures"}:
        raise RunnerError("Post-hoc analysis requires a terminal sweep")

    resolved_primary = resolve_repo_path(repo_root, primary_report_path)
    primary = load_json(resolved_primary)
    if primary.get("report_id") != "log-incident-capability-sweep-v0.2":
        raise RunnerError("Unexpected primary report identity")
    source = primary.get("source") or {}
    if source.get("sweep_id") != sweep.get("sweep_id"):
        raise RunnerError("Primary report and sweep identity mismatch")
    if source.get("sweep_record_sha256") != sha256_file(sweep_path):
        raise RunnerError("Primary report and sweep hash mismatch")

    units = primary.get("units")
    if not isinstance(units, list) or len(units) != len(sweep.get("units", [])):
        raise RunnerError("Primary report unit set is incomplete")
    if [unit.get("position") for unit in units] != list(range(1, len(units) + 1)):
        raise RunnerError("Primary report positions are not contiguous")
    if any(unit.get("essential_checks_total") not in {None, 1, 14} for unit in units):
        raise RunnerError("Unexpected frozen-verifier check count")

    system_keys = [
        (item["harness_id"], item["harness_label"], item["model"])
        for item in primary["by_system_model"]
    ]
    case_keys = [
        (item["case_id"], item["case_label"]) for item in primary["by_case"]
    ]
    harness_keys = [
        (item["harness_id"], item["harness_label"])
        for item in primary["by_harness"]
    ]
    by_system_model = [
        _group_summary(
            [
                unit
                for unit in units
                if unit["harness_id"] == harness_id and unit["model"] == model
            ],
            harness_id=harness_id,
            harness_label=harness_label,
            model=model,
        )
        for harness_id, harness_label, model in system_keys
    ]
    by_harness = [
        _group_summary(
            [unit for unit in units if unit["harness_id"] == harness_id],
            harness_id=harness_id,
            harness_label=harness_label,
        )
        for harness_id, harness_label in harness_keys
    ]
    by_case = [
        _group_summary(
            [unit for unit in units if unit["case_id"] == case_id],
            case_id=case_id,
            case_label=case_label,
        )
        for case_id, case_label in case_keys
    ]
    summary = _group_summary(units)
    closest = sorted(
        [
            {
                "position": unit["position"],
                "harness_id": unit["harness_id"],
                "harness_label": unit["harness_label"],
                "model": unit["model"],
                "case_id": unit["case_id"],
                "case_label": unit["case_label"],
                "checks_passed": unit["essential_checks_passed"],
                "checks_total": unit["essential_checks_total"],
                "failed_check_ids": unit["failed_check_ids"],
            }
            for unit in units
            if _schema_valid(unit)
            and unit["essential_checks_total"] - unit["essential_checks_passed"]
            <= 2
        ],
        key=lambda item: (
            item["checks_total"] - item["checks_passed"],
            item["position"],
        ),
    )
    sensitivity = _protocol_sensitivity(repo_root, sweep, units)
    manual_calibration = {
        "status": "post_hoc_human_calibration_not_primary_scoring",
        "selection": "three_schema_valid_outcomes_with_fewest_failed_checks",
        "sample_size": 3,
        "primary_outcomes_changed": False,
        "findings": [
            {
                "position": 13,
                "assessment": "strong_operational_draft",
                "strict_failure_character": "narrow_evidence_to_hypothesis_assignment",
                "note": (
                    "The diagnosis, impact and recovery were coherent. A required "
                    "counter-evidence item was attached to another plausible rejected "
                    "hypothesis rather than the verifier-required hypothesis."
                ),
            },
            {
                "position": 16,
                "assessment": "strong_draft_with_material_window_error",
                "strict_failure_character": "pre_impact_event_used_as_incident_start",
                "note": (
                    "The analysis selected a deployment event rather than the first "
                    "observed user-facing impact as the incident start."
                ),
            },
            {
                "position": 22,
                "assessment": "strong_draft_with_window_and_role_errors",
                "strict_failure_character": "pre_impact_start_and_recovery_evidence_role",
                "note": (
                    "The analysis selected pool admission rather than first observed "
                    "user impact and assigned one recovery-state item to another role."
                ),
            },
        ],
        "conclusion": (
            "The nearest Qwen 3.8 outputs were useful analyst drafts, but none was a "
            "machine-verifiable autonomous outcome under the frozen contract."
        ),
    }
    specification_audit = {
        "status": "blocking_alignment_issue_found_after_measurement",
        "primary_outcomes_changed": False,
        "issues": [
            {
                "issue_id": "incident_start_semantics_under_specified",
                "affected_check": "incident_window_utc",
                "observed_failures_among_schema_valid_reports": summary[
                    "schema_valid_failed_checks"
                ].get("incident_window_utc", 0),
                "schema_valid_report_count": summary["schema_valid_report_count"],
                "visible_specification": (
                    "The task requires UTC normalization and defines last_observed_utc, "
                    "but does not define start_utc."
                ),
                "verifier_expectation": (
                    "start_utc is the first observed user-facing impact, not deployment, "
                    "trigger or component admission."
                ),
                "consequence": (
                    "Failures on this check cannot be attributed cleanly to model "
                    "capability. The task must be versioned before decision use."
                ),
            }
        ],
        "recommended_action": (
            "Retain v0.2 as historical evidence. Define start_utc explicitly in a new "
            "v0.3 visible contract, requalify fixtures and verifier, then run a small "
            "predeclared confirmation before any replication study."
        ),
    }
    analysis = {
        "schema_version": "1.0.0",
        "analysis_id": "log-incident-capability-sweep-v0.2-post-hoc",
        "generated_at": utc_now(),
        "status": "post_hoc_descriptive_analysis",
        "source": {
            "primary_report_path": resolved_primary.relative_to(repo_root).as_posix(),
            "primary_report_sha256": sha256_file(resolved_primary),
            "sweep_id": sweep["sweep_id"],
            "sweep_record_sha256": sha256_file(sweep_path),
            "execution_git_commit": source["execution_git_commit"],
            "ollama_version": source["ollama_version"],
        },
        "method": {
            "primary_outcome": "verified_success",
            "primary_outcomes_changed": False,
            "runs_per_configuration": 1,
            "comparison_unit": "complete_system",
            "schema_valid_definition": (
                "The frozen verifier reached all 14 essential checks."
            ),
            "check_coverage_role": "diagnostic_only_not_a_normalized_quality_score",
            "timing_role": "descriptive_only_not_performance_evidence",
            "timing_note": (
                "Heavy macOS Spotlight indexing was documented at launch, so timing "
                "differences are potentially confounded by uncontrolled host load."
            ),
        },
        "summary": summary,
        "by_system_model": by_system_model,
        "by_harness": by_harness,
        "by_case": by_case,
        "closest_strict_outcomes": closest,
        "post_hoc_protocol_sensitivity": sensitivity,
        "manual_calibration": manual_calibration,
        "specification_audit": specification_audit,
        "interpretation_boundaries": [
            "Zero verified successes means no tested system met the frozen deployment threshold in its single observed attempt.",
            "Partial check counts locate failure modes but are not a substitute primary score and are not normalized quality points.",
            "Each system-model-case cell has n=1, so no reliability or stochasticity claim is supported.",
            "Mini and Pi differ as complete systems; this design cannot isolate a causal harness effect.",
            "The response-envelope sensitivity was chosen after observing failures and is exploratory only.",
            "The visible start-time definition and hidden verifier expectation were not fully aligned, so v0.2 is not decision-ready capability evidence.",
            "No verifier criterion is removed or weakened after observing model output.",
            "No composite ranking or tail-latency claim is produced.",
        ],
        "privacy": {
            "candidate_reports_included": False,
            "raw_log_contents_included": False,
            "hidden_ground_truth_included": False,
            "absolute_paths_included": False,
            "raw_run_records_public": False,
        },
    }

    json_path = resolve_repo_path(repo_root, json_output_path)
    markdown_path = resolve_repo_path(repo_root, markdown_output_path)
    write_json(json_path, analysis)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(_markdown(analysis), encoding="utf-8")
    return {
        "analysis_id": analysis["analysis_id"],
        "json_path": json_path.relative_to(repo_root).as_posix(),
        "markdown_path": markdown_path.relative_to(repo_root).as_posix(),
        "run_count": summary["run_count"],
        "verified_success_count": summary["verified_success_count"],
    }


def _duration_text(item: dict[str, Any]) -> str:
    duration = item["active_wall_time_seconds"]
    if duration["median"] is None:
        return "n/a"
    return (
        f"{duration['median']:.2f} s "
        f"[{duration['minimum']:.2f}, {duration['maximum']:.2f}]"
    )


def _check_text(item: dict[str, Any]) -> str:
    total = item["schema_valid_checks_total"]
    if not total:
        return "n/a"
    return f"{item['schema_valid_checks_passed']}/{total}"


def _markdown(analysis: dict[str, Any]) -> str:
    summary = analysis["summary"]
    lines = [
        "# Agentic Log Incident Capability Sweep v0.2 — Post-hoc Analysis",
        "",
        "This document adds diagnostics to the frozen primary report. It does not",
        "change any run, verifier criterion or primary outcome.",
        "",
        "## Primary result",
        "",
        f"- Verified success: {summary['verified_success_count']}/{summary['run_count']}",
        f"- Runtime-complete: {summary['runtime_success_count']}/{summary['run_count']}",
        f"- Schema-valid reports: {summary['schema_valid_report_count']}/{summary['run_count']}",
        "- Result: no tested complete system met the frozen deployment threshold.",
        "",
        "## System diagnostics",
        "",
        "The check column is diagnostic coverage, not a normalized quality score.",
        "Timing is median [minimum, maximum] over three heterogeneous cases and is",
        "descriptive only because Spotlight load was present at launch.",
        "",
        "| Harness | Model | Verified | Schema-valid | Verifier checks | Active time |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for item in analysis["by_system_model"]:
        lines.append(
            f"| {item['harness_label']} | `{item['model']}` | "
            f"{item['verified_success_count']}/{item['run_count']} | "
            f"{item['schema_valid_report_count']}/{item['run_count']} | "
            f"{_check_text(item)} | {_duration_text(item)} |"
        )

    lines.extend(["", "## Closest strict outcomes", ""])
    closest = analysis["closest_strict_outcomes"]
    if closest:
        lines.extend(
            [
                "| Harness | Model | Case | Checks | Missing criteria |",
                "| --- | --- | --- | ---: | --- |",
            ]
        )
        for item in closest:
            lines.append(
                f"| {item['harness_label']} | `{item['model']}` | "
                f"{item['case_label']} | {item['checks_passed']}/"
                f"{item['checks_total']} | {', '.join(item['failed_check_ids'])} |"
            )
    else:
        lines.append("No schema-valid report finished within two checks of success.")

    lines.extend(
        [
            "",
            "## Recurring misses in schema-valid reports",
            "",
            "| Essential check | Failed reports |",
            "| --- | ---: |",
        ]
    )
    for check_id, count in summary["schema_valid_failed_checks"].items():
        lines.append(
            f"| `{check_id}` | {count}/{summary['schema_valid_report_count']} |"
        )

    sensitivity = analysis["post_hoc_protocol_sensitivity"]
    lines.extend(
        [
            "",
            "## Post-hoc response-envelope sensitivity",
            "",
            "This exploratory check removes only surrounding prose or Markdown fences",
            "and then runs the same frozen verifier. It is not a primary rescore.",
            "",
            f"- Strictly invalid report responses: {sensitivity['strict_invalid_report_count']}",
            f"- Embedded JSON objects recovered: {sensitivity['embedded_object_recovered_count']}",
            f"- Schema-valid after recovery: {sensitivity['schema_valid_after_recovery_count']}",
            f"- Fully verified after recovery: {sensitivity['verified_success_after_recovery_count']}",
            "- Primary outcomes changed: no",
        ]
    )
    if sensitivity["recovered_units"]:
        lines.extend(
            [
                "",
                "| Model | Case | Envelope | Recovered checks |",
                "| --- | --- | --- | ---: |",
            ]
        )
        for item in sensitivity["recovered_units"]:
            lines.append(
                f"| `{item['model']}` | {item['case_label']} | "
                f"`{item['envelope']}` | {item['checks_passed_after_recovery']}/"
                f"{item['checks_total_after_recovery']} |"
            )

    calibration = analysis["manual_calibration"]
    specification = analysis["specification_audit"]
    lines.extend(
        [
            "",
            "## Manual calibration and specification audit",
            "",
            "A post-hoc review of the three closest strict outcomes found that the",
            "Qwen 3.8 responses were useful analyst drafts. One miss was a narrow",
            "evidence-to-hypothesis assignment; two included materially different",
            "incident-start choices, and one also misassigned a recovery evidence role.",
            "The strict primary failures remain unchanged.",
            "",
            f"Calibration conclusion: {calibration['conclusion']}",
            "",
            "The audit also found a blocking specification mismatch: the visible task",
            "defines `last_observed_utc` but never defines `start_utc`, while the hidden",
            "verifier requires the first observed user-facing impact. Deployment, trigger",
            "or component-admission timestamps are plausible alternatives under the",
            "visible wording. This check failed in "
            f"{specification['issues'][0]['observed_failures_among_schema_valid_reports']}/"
            f"{specification['issues'][0]['schema_valid_report_count']} schema-valid reports.",
            "",
            "Therefore v0.2 is retained as historical protocol evidence but is not",
            "decision-ready evidence of model incapability. A v0.3 task contract must",
            "define the incident start before any confirmation or replication run.",
        ]
    )

    lines.extend(
        [
            "",
            "## Case diagnostics",
            "",
            "| Case | Verified | Schema-valid | Verifier checks |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for item in analysis["by_case"]:
        lines.append(
            f"| {item['case_label']} | "
            f"{item['verified_success_count']}/{item['run_count']} | "
            f"{item['schema_valid_report_count']}/{item['run_count']} | "
            f"{_check_text(item)} |"
        )

    lines.extend(["", "## Interpretation", ""])
    lines.extend(
        [
            "- Qwen 3.8 produced all three strict Mini reports and covered 36/42 checks. All three observed outcomes within two checks of strict success used Qwen 3.8, including the one close Pi outcome.",
            "- Mini produced 15/15 schema-valid reports; Pi produced 7/15. This is an observed complete-system difference, not an isolated causal harness effect.",
            "- Pi's eight strict format failures all contained an embedded JSON object, but envelope stripping still yielded zero fully verified reports. Format compliance matters, yet does not explain the zero-success result by itself.",
            "- Exact incident timing, causal-chain reconstruction, distractor rejection and critical-evidence selection are the dominant strict-verifier gaps.",
            "- No productive default route can be certified from v0.2. The specification mismatch must be corrected before deciding whether the models or the task contract caused the zero-success result.",
        ]
    )
    lines.extend(["", "## Interpretation boundaries", ""])
    lines.extend(
        f"- {item}" for item in analysis["interpretation_boundaries"]
    )
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sweep-dir", type=Path, required=True)
    parser.add_argument("--primary-report", type=Path, default=DEFAULT_PRIMARY_REPORT)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = build_log_incident_sweep_analysis(
            Path.cwd().resolve(),
            args.sweep_dir,
            args.primary_report,
            args.json_output,
            args.markdown_output,
        )
    except (OSError, RunnerError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
