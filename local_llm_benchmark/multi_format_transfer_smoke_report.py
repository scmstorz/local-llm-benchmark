"""Public-safe deterministic report builder for the Phase 96 transfer smoke."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .multi_format_transfer_smoke import _load_study
from .runner import RunnerError, write_json


def build_transfer_smoke_report(
    repo_root: Path, study_dir: Path
) -> dict[str, Any]:
    """Build a summary without raw candidate content or private paths."""
    _resolved, record, loaded = _load_study(repo_root, study_dir)
    if record.get("status") not in {"complete", "complete_with_failures"}:
        raise RunnerError("Transfer smoke is not terminal")
    if record.get("terminal_unit_count") != 2:
        raise RunnerError("Transfer smoke does not contain two terminal units")
    outcomes = []
    for unit in record["units"]:
        outcome = unit.get("outcome") or {}
        verification = unit.get("verification") or {}
        trajectory = unit.get("trajectory") or {}
        outcomes.append(
            {
                "position": unit["position"],
                "system_id": unit["system_id"],
                "model": unit["model"],
                "terminal_status": unit["status"],
                "runtime_success": bool(outcome.get("runtime_success")),
                "agent_termination_valid": bool(
                    outcome.get("agent_termination_valid")
                ),
                "semantic_verified_success": bool(
                    outcome.get("semantic_verified_success")
                ),
                "strict_transport_compliance": bool(
                    outcome.get("strict_transport_compliance")
                ),
                "failure_category": outcome.get("failure_category"),
                "failure_type": outcome.get("failure_type"),
                "essential_pass_count": verification.get("essential_pass_count"),
                "essential_check_count": verification.get("essential_check_count"),
                "failed_check_ids": verification.get("failed_check_ids", []),
                "model_requests": trajectory.get("model_requests"),
                "agent_turns": trajectory.get("agent_turns"),
                "artifact_tool_calls": trajectory.get("artifact_tool_calls"),
                "active_wall_time_seconds": trajectory.get(
                    "active_wall_time_seconds"
                ),
                "pi_seatbelt_checks_passed": (
                    unit.get("live_seatbelt_acceptance") or {}
                ).get("checks_passed"),
                "pi_seatbelt_checks_total": (
                    unit.get("live_seatbelt_acceptance") or {}
                ).get("checks_total"),
                "postflight_empty": unit.get("postflight_running_models") == [],
            }
        )
    return {
        "schema_version": "1.0.0",
        "report_id": loaded["plan"]["reporting"]["report_id"],
        "status": record["status"],
        "evidence_class": record["evidence_class"],
        "plan_id": loaded["plan"]["plan_id"],
        "plan_sha256": loaded["sha256"],
        "case_id": loaded["plan"]["case"]["case_id"],
        "model": loaded["plan"]["deployment"]["name"],
        "unit_count": 2,
        "automatic_retries": 0,
        "excluded_from_measured_aggregates": True,
        "outcomes": outcomes,
        "totals": {
            "semantic_verified_success_count": sum(
                item["semantic_verified_success"] for item in outcomes
            ),
            "strict_transport_compliance_count": sum(
                item["strict_transport_compliance"] for item in outcomes
            ),
            "postflight_empty_count": sum(item["postflight_empty"] for item in outcomes),
        },
        "interpretation_boundaries": [
            "This is excluded machinery evidence, not a measured model or system ranking.",
            "One attempt per complete system does not estimate reliability or latency distributions.",
            "Track A and historical Phase 95 outcomes are not pooled with this transfer smoke.",
            "Raw candidate content and private run paths are excluded from this report.",
        ],
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Multi-Format Transfer Smoke v0.2",
        "",
        f"Status: `{report['status']}`",
        "",
        "| Position | System | Semantic | Strict transport | Checks | Postflight empty |",
        "| ---: | --- | --- | --- | ---: | --- |",
    ]
    for item in report["outcomes"]:
        checks = f"{item['essential_pass_count']}/{item['essential_check_count']}"
        lines.append(
            f"| {item['position']} | `{item['system_id']}` | "
            f"{str(item['semantic_verified_success']).lower()} | "
            f"{str(item['strict_transport_compliance']).lower()} | {checks} | "
            f"{str(item['postflight_empty']).lower()} |"
        )
    lines.extend(["", "## Interpretation boundaries", ""])
    lines.extend(f"- {item}" for item in report["interpretation_boundaries"])
    return "\n".join(lines) + "\n"


def write_transfer_smoke_report(
    repo_root: Path, study_dir: Path
) -> dict[str, Any]:
    """Write the frozen public JSON and Markdown report destinations."""
    report = build_transfer_smoke_report(repo_root, study_dir)
    _resolved, _record, loaded = _load_study(repo_root, study_dir)
    reporting = loaded["plan"]["reporting"]
    json_path = repo_root / reporting["json_path"]
    markdown_path = repo_root / reporting["markdown_path"]
    write_json(json_path, report)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return {
        "status": report["status"],
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    repo_root = Path.cwd().resolve()
    try:
        result = write_transfer_smoke_report(repo_root, args.study_dir)
    except (OSError, RunnerError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
