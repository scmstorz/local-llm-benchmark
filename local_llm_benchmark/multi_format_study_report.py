"""Build public-safe deterministic results for the multi-format capability study."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .runner import RunnerError, load_json, resolve_repo_path, sha256_file, write_json


def _metrics(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    keys = (
        "active_wall_time_seconds",
        "agent_turns",
        "model_requests",
        "tool_calls",
        "failed_tool_calls",
        "protocol_errors",
        "repeated_queries",
        "input_tokens",
        "output_tokens",
        "response_normalization_applied",
        "response_normalization_kind",
    )
    return {key: source.get(key) for key in keys}


def _aggregate(cells: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cell in cells:
        groups[str(cell[key])].append(cell)
    return [
        {
            key: name,
            "cell_count": len(items),
            "terminal_count": sum(item["status"] in {"complete", "failed"} for item in items),
            "runtime_success_count": sum(bool(item["outcome"].get("runtime_success")) for item in items),
            "semantic_verified_success_count": sum(bool(item["outcome"].get("semantic_verified_success")) for item in items),
            "strict_transport_compliance_count": sum(bool(item["outcome"].get("strict_transport_compliance")) for item in items),
            "essential_checks_passed": sum(item["verification"].get("essential_pass_count") or 0 for item in items),
            "essential_checks_total": sum(item["verification"].get("essential_check_count") or 0 for item in items),
        }
        for name, items in groups.items()
    ]


def build_multi_format_study_report(repo_root: Path, study_dir: Path) -> dict[str, Any]:
    """Aggregate a terminal study without exposing candidate text or local paths."""
    resolved = resolve_repo_path(repo_root, study_dir)
    study_path = resolved / "study.json"
    study = load_json(study_path)
    if study.get("status") not in {"complete", "complete_with_failures"}:
        raise RunnerError("Multi-format study report requires a terminal study")
    plan_path = resolve_repo_path(repo_root, Path(study["plan"]["path"]))
    plan = load_json(plan_path)
    if sha256_file(plan_path) != study["plan"]["sha256"]:
        raise RunnerError("Multi-format study plan changed before reporting")
    cells = []
    for unit in study.get("units", []):
        outcome = unit.get("outcome") if isinstance(unit.get("outcome"), dict) else {}
        verification = unit.get("verification") if isinstance(unit.get("verification"), dict) else {}
        cells.append(
            {
                "position": unit.get("position"),
                "track": unit.get("track"),
                "condition_id": unit.get("condition_id"),
                "model": unit.get("model"),
                "deployment_id": unit.get("deployment_id"),
                "run_id": unit.get("run_id"),
                "status": unit.get("status"),
                "outcome": {
                    "runtime_success": bool(outcome.get("runtime_success")),
                    "agent_termination_valid": bool(outcome.get("agent_termination_valid")),
                    "semantic_verified_success": bool(outcome.get("semantic_verified_success")),
                    "strict_transport_compliance": bool(outcome.get("strict_transport_compliance")),
                    "failure_category": outcome.get("failure_category"),
                    "failure_type": outcome.get("failure_type"),
                },
                "verification": {
                    "essential_pass_count": verification.get("essential_pass_count"),
                    "essential_check_count": verification.get("essential_check_count"),
                    "failed_check_ids": verification.get("failed_check_ids", []),
                },
                "trajectory": _metrics(unit.get("trajectory")),
                "seatbelt_checks": unit.get("sandbox_acceptance"),
            }
        )
    report = {
        "schema_version": "1.0.0",
        "report_id": "multi-format-capability-sweep-v0.1",
        "status": "deterministic_results_complete_supplemental_review_pending",
        "evidence_class": "measured_capability_sweep",
        "study_id": study["study_id"],
        "study_record_sha256": sha256_file(study_path),
        "plan_id": plan["plan_id"],
        "plan_sha256": study["plan"]["sha256"],
        "cell_count": len(cells),
        "cells": cells,
        "by_track": _aggregate(cells, "track"),
        "by_condition": _aggregate(cells, "condition_id"),
        "by_model": _aggregate(cells, "model"),
        "primary_outcome": "semantic_verified_success",
        "secondary_outcome": "strict_transport_compliance",
        "supplemental_free_text_review": {
            "required": True,
            "status": "pending",
            "deterministic_success_is_final_quality_acceptance": False,
        },
        "interpretation_boundaries": {
            "track_a_and_track_b_pooled": False,
            "runs_per_configuration": 1,
            "reliability_probability_claims": False,
            "latency_distribution_claims": False,
            "quality_stochasticity_claims": False,
            "one_factor_causal_harness_claim_allowed": False,
            "trajectory_metrics_are_descriptive": True,
            "check_counts_are_normalized_scores": False,
        },
        "public_safety": {
            "candidate_outputs_included": False,
            "canonical_evidence_text_included": False,
            "binary_contents_included": False,
            "hidden_ground_truth_included": False,
            "absolute_paths_included": False,
        },
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    """Render the public-safe machine-result report."""
    lines = [
        "# Multi-Format Capability Sweep v0.1",
        "",
        "The 15-cell measured sweep is complete. Results keep the canonical",
        "Track A condition separate from the two real-artifact Track B complete",
        "systems. Each exact configuration has one attempt; this is capability",
        "evidence, not a reliability or latency-distribution estimate.",
        "",
        "## Deterministic outcomes by condition",
        "",
        "| Condition | Cells | Runtime | Semantic | Strict transport | Checks |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in report["by_condition"]:
        lines.append(
            f"| `{item['condition_id']}` | {item['cell_count']} | "
            f"{item['runtime_success_count']}/{item['cell_count']} | "
            f"{item['semantic_verified_success_count']}/{item['cell_count']} | "
            f"{item['strict_transport_compliance_count']}/{item['cell_count']} | "
            f"{item['essential_checks_passed']}/{item['essential_checks_total']} |"
        )
    lines.extend(
        [
            "",
            "## Deterministic outcomes by model",
            "",
            "| Model | Cells | Semantic | Strict transport | Checks |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in report["by_model"]:
        lines.append(
            f"| `{item['model']}` | {item['cell_count']} | "
            f"{item['semantic_verified_success_count']}/{item['cell_count']} | "
            f"{item['strict_transport_compliance_count']}/{item['cell_count']} | "
            f"{item['essential_checks_passed']}/{item['essential_checks_total']} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "Track A and Track B are not pooled. The Mini and Pi observations are",
            "complete-system outcomes, not a one-factor causal harness comparison.",
            "Turns, tokens and timing are descriptive only. A separate review of",
            "free-text grounding, polarity and usefulness remains mandatory before",
            "deterministic success can be treated as final content acceptance.",
            "",
            "Raw responses, document contents, hidden references and absolute paths",
            "are intentionally excluded from this report.",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", type=Path, required=True)
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("reports/agentic/multi-format-capability-sweep-v0.1.json"),
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=Path("reports/agentic/multi-format-capability-sweep-v0.1.md"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    report = build_multi_format_study_report(repo_root, args.study_dir)
    json_path = resolve_repo_path(repo_root, args.json_output)
    markdown_path = resolve_repo_path(repo_root, args.markdown_output)
    write_json(json_path, report)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "complete",
                "json_path": str(json_path),
                "json_sha256": sha256_file(json_path),
                "markdown_path": str(markdown_path),
                "markdown_sha256": sha256_file(markdown_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
