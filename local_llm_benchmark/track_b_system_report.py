"""Compare public Pi v0.3 and Mini v0.3 Track B system reports."""

from __future__ import annotations

import argparse
import json
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


EXPECTED_REPORTS = {
    "pi": "track-b-pi-capability-sweep-v0.3",
    "mini": "track-b-mini-capability-sweep-v0.3",
}


def _key(unit: dict[str, Any]) -> tuple[str, str]:
    return str(unit["model"]), str(unit["case_id"])


def _relation(pi_success: bool, mini_success: bool) -> str:
    if pi_success and mini_success:
        return "both_success"
    if not pi_success and not mini_success:
        return "both_failure"
    if pi_success:
        return "pi_only_success"
    return "mini_only_success"


def _failure_type(unit: dict[str, Any], system: str) -> str | None:
    if unit["verified_success"]:
        return None
    if system == "pi":
        return unit.get("effective_failure_type") or "verification_failed"
    return unit.get("failure_type") or "verification_failed"


def _system_view(unit: dict[str, Any], system: str) -> dict[str, Any]:
    return {
        "verified_success": bool(unit["verified_success"]),
        "verifier_success": bool(unit["verifier_success"]),
        "runtime_success": bool(unit["runtime_success"]),
        "failure_type": _failure_type(unit, system),
        "active_duration_seconds": unit["active_duration_seconds"],
        "agent_turns": unit["agent_turns"],
        "tool_calls": unit["tool_calls"],
        "failed_tool_calls": unit["failed_tool_calls"],
        "file_reads": unit["file_reads"],
        "file_writes": unit["file_writes"],
        "public_test_runs": unit["public_test_runs"],
        "input_tokens": unit["input_tokens"],
        "output_tokens": unit["output_tokens"],
    }


def _load_public_report(repo_root: Path, path: Path, system: str) -> tuple[Path, dict[str, Any]]:
    resolved = resolve_repo_path(repo_root, path)
    report = load_json(resolved)
    if report.get("report_id") != EXPECTED_REPORTS[system]:
        raise RunnerError(f"Unexpected {system} report_id")
    units = report.get("units")
    if not isinstance(units, list) or len(units) == 0:
        raise RunnerError(f"{system} report contains no units")
    return resolved, report


def _aggregate(
    cells: list[dict[str, Any]], *, key: str, value: str
) -> dict[str, Any]:
    relations = Counter(cell["outcome_relation"] for cell in cells)
    return {
        key: value,
        "configuration_count": len(cells),
        "pi_verified_success_count": sum(
            cell["pi"]["verified_success"] for cell in cells
        ),
        "mini_verified_success_count": sum(
            cell["mini"]["verified_success"] for cell in cells
        ),
        "outcome_agreement_count": sum(
            cell["outcome_agreement"] for cell in cells
        ),
        "relations": dict(sorted(relations.items())),
    }


def build_track_b_system_report(
    repo_root: Path, pi_path: Path, mini_path: Path
) -> dict[str, Any]:
    """Build a public-safe paired system comparison from public reports."""
    resolved_pi, pi_report = _load_public_report(repo_root, pi_path, "pi")
    resolved_mini, mini_report = _load_public_report(repo_root, mini_path, "mini")
    pi_units = {_key(unit): unit for unit in pi_report["units"]}
    mini_units = {_key(unit): unit for unit in mini_report["units"]}
    if pi_units.keys() != mini_units.keys():
        raise RunnerError("Pi and Mini reports do not cover identical model-task cells")

    cells = []
    for unit in pi_report["units"]:
        key = _key(unit)
        mini_unit = mini_units[key]
        pi_view = _system_view(unit, "pi")
        mini_view = _system_view(mini_unit, "mini")
        relation = _relation(
            pi_view["verified_success"], mini_view["verified_success"]
        )
        pi_duration = float(pi_view["active_duration_seconds"])
        mini_duration = float(mini_view["active_duration_seconds"])
        cells.append(
            {
                "model": key[0],
                "case_id": key[1],
                "case_label": unit["case_label"],
                "outcome_agreement": relation in {"both_success", "both_failure"},
                "outcome_relation": relation,
                "active_duration_delta_seconds_mini_minus_pi": round(
                    mini_duration - pi_duration, 2
                ),
                "active_duration_ratio_mini_to_pi": round(
                    mini_duration / pi_duration, 3
                ),
                "pi": pi_view,
                "mini": mini_view,
            }
        )

    model_order = [item["model"] for item in pi_report["by_model"]]
    case_order = [item["case_id"] for item in pi_report["by_case"]]
    by_model = [
        _aggregate(
            [cell for cell in cells if cell["model"] == model],
            key="model",
            value=model,
        )
        for model in model_order
    ]
    by_case = [
        {
            **_aggregate(
                [cell for cell in cells if cell["case_id"] == case_id],
                key="case_id",
                value=case_id,
            ),
            "case_label": next(
                cell["case_label"] for cell in cells if cell["case_id"] == case_id
            ),
        }
        for case_id in case_order
    ]
    summary = _aggregate(cells, key="scope", value="all_configurations")
    summary["both_success_count"] = sum(
        cell["outcome_relation"] == "both_success" for cell in cells
    )
    summary["both_failure_count"] = sum(
        cell["outcome_relation"] == "both_failure" for cell in cells
    )
    summary["pi_only_success_count"] = sum(
        cell["outcome_relation"] == "pi_only_success" for cell in cells
    )
    summary["mini_only_success_count"] = sum(
        cell["outcome_relation"] == "mini_only_success" for cell in cells
    )

    return {
        "schema_version": "1.0.0",
        "report_id": "track-b-pi-vs-mini-system-comparison-v0.3",
        "generated_at": utc_now(),
        "evidence_class": "paired_complete_system_comparison",
        "sources": {
            "pi": {
                "path": str(resolved_pi.relative_to(repo_root)),
                "report_id": pi_report["report_id"],
                "sha256": sha256_file(resolved_pi),
                "sweep_id": pi_report["source"]["sweep_id"],
            },
            "mini": {
                "path": str(resolved_mini.relative_to(repo_root)),
                "report_id": mini_report["report_id"],
                "sha256": sha256_file(resolved_mini),
                "sweep_id": mini_report["source"]["sweep_id"],
            },
        },
        "method": {
            "track": "B",
            "comparison_unit": "matched model-task cell",
            "systems": ["pi-v0.3", "mini-v0.3"],
            "primary_outcome": "verified_success",
            "runs_per_system_configuration": 1,
            "automatic_retries": 0,
            "causal_harness_effect_claimed": False,
        },
        "summary": summary,
        "by_model": by_model,
        "by_case": by_case,
        "cells": cells,
        "findings": [
            f"Pi produced {summary['pi_verified_success_count']}/{len(cells)} verified outcomes; Mini produced {summary['mini_verified_success_count']}/{len(cells)}.",
            f"The systems agreed on verified success or failure in {summary['outcome_agreement_count']}/{len(cells)} matched cells.",
            f"Pi alone succeeded in {summary['pi_only_success_count']} cells; Mini alone succeeded in {summary['mini_only_success_count']} cell.",
            f"Both systems succeeded in {summary['both_success_count']} cells and both failed in {summary['both_failure_count']} cells.",
        ],
        "caveats": [
            "Every matched system configuration has n=1, so outcome flips may reflect stochasticity and are not reliability estimates.",
            "Pi v0.3 and Mini v0.3 differ in prompts, protocol, tool implementations, context accumulation and error handling. This is a complete-system comparison, not an isolated causal estimate of harness quality.",
            "Active duration includes model and tool time, excludes host standby gaps, and is not adjusted for success. Duration deltas must be interpreted together with verified outcomes.",
            "Token and turn counts are system-level trajectory measurements whose semantics can differ across harnesses.",
            "No composite score or universal ranking is calculated.",
        ],
        "privacy": {
            "source_reports_only": True,
            "raw_model_text_included": False,
            "candidate_source_included": False,
            "absolute_local_paths_included": False,
        },
    }


def _outcome(view: dict[str, Any]) -> str:
    return "PASS" if view["verified_success"] else "FAIL"


def render_track_b_system_markdown(report: dict[str, Any]) -> str:
    """Render a compact public Markdown report."""
    summary = report["summary"]
    lines = [
        "# Track B Pi v0.3 vs Mini v0.3 System Comparison",
        "",
        "## Outcome",
        "",
        (
            f"Across {summary['configuration_count']} matched model-task cells, "
            f"Pi produced **{summary['pi_verified_success_count']} verified successes** "
            f"and Mini produced **{summary['mini_verified_success_count']}**. "
            f"The binary outcomes agreed in {summary['outcome_agreement_count']}/"
            f"{summary['configuration_count']} cells."
        ),
        "",
        "| Model | Pi verified | Mini verified | Agreement |",
        "| --- | ---: | ---: | ---: |",
    ]
    for item in report["by_model"]:
        lines.append(
            f"| `{item['model']}` | {item['pi_verified_success_count']}/3 | "
            f"{item['mini_verified_success_count']}/3 | "
            f"{item['outcome_agreement_count']}/3 |"
        )
    lines.extend(
        [
            "",
            "## Results by case",
            "",
            "| Case | Pi verified | Mini verified | Agreement |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for item in report["by_case"]:
        lines.append(
            f"| {item['case_label']} | {item['pi_verified_success_count']}/5 | "
            f"{item['mini_verified_success_count']}/5 | "
            f"{item['outcome_agreement_count']}/5 |"
        )
    lines.extend(
        [
            "",
            "## Paired cells",
            "",
            "| Model | Case | Pi | Mini | Relation |",
            "| --- | --- | ---: | ---: | --- |",
        ]
    )
    for cell in report["cells"]:
        lines.append(
            f"| `{cell['model']}` | {cell['case_label']} | "
            f"{_outcome(cell['pi'])} ({cell['pi']['active_duration_seconds']:.1f}s) | "
            f"{_outcome(cell['mini'])} ({cell['mini']['active_duration_seconds']:.1f}s) | "
            f"`{cell['outcome_relation']}` |"
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
            f"- Pi report: `{report['sources']['pi']['report_id']}` (`{report['sources']['pi']['sha256']}`)",
            f"- Mini report: `{report['sources']['mini']['report_id']}` (`{report['sources']['mini']['sha256']}`)",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pi-report",
        type=Path,
        default=Path("reports/coding/track-b-pi-capability-sweep-v0.3.json"),
    )
    parser.add_argument(
        "--mini-report",
        type=Path,
        default=Path("reports/coding/track-b-mini-capability-sweep-v0.3.json"),
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=Path("reports/coding/track-b-pi-vs-mini-system-comparison-v0.3.json"),
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        default=Path("reports/coding/track-b-pi-vs-mini-system-comparison-v0.3.md"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    try:
        report = build_track_b_system_report(
            repo_root, args.pi_report, args.mini_report
        )
        json_out = resolve_repo_path(repo_root, args.json_out)
        markdown_out = resolve_repo_path(repo_root, args.markdown_out)
        write_json(json_out, report)
        markdown_out.parent.mkdir(parents=True, exist_ok=True)
        markdown_out.write_text(
            render_track_b_system_markdown(report), encoding="utf-8"
        )
    except (OSError, RunnerError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(
        json.dumps(
            {
                "status": "complete",
                "report_id": report["report_id"],
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
