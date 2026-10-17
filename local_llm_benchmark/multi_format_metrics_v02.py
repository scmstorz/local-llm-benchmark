"""Offline, versioned metrics for Mini v0.2 and Pi v0.4 supplier runs.

Missing counts remain null. Native counters retain their adapter semantics;
only explicitly recorded artifact and completion operations are normalized.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .runner import RunnerError, load_json, resolve_repo_path, sha256_file


VERSION = "0.2.0"
CONTRACT_PATH = Path("tasks/agentic/multi-format-transfer-metrics-v0.2.json")
ARTIFACT_ACTIONS = {"list_artifacts", "read_docx", "read_pdf", "read_xlsx"}
METRIC_NAMES = ("model_requests", "artifact_tool_calls", "completion_calls")


def _count(value: dict[str, Any], key: str) -> int | None:
    observed = value.get(key)
    if observed is None:
        return None
    if type(observed) is not int or observed < 0:
        raise RunnerError(f"Invalid nonnegative integer counter: {key}")
    return observed


def normalize_run(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize recorded counters without estimating HTTP requests from turns."""
    system = record.get("harness", {}).get("harness_id")
    if system not in {"pi-multi-format-v0.4", "mini-multi-format-v0.2"}:
        raise RunnerError(f"Unsupported supplier metrics adapter: {system}")
    trajectory = record.get("trajectory")
    if not isinstance(trajectory, dict):
        raise RunnerError("Run has no trajectory object")
    requests = _count(trajectory, "model_requests")
    native = _count(trajectory, "tool_calls")
    sources: dict[str, Any] = {
        "model_requests": "trajectory.model_requests" if requests is not None else None,
    }
    if system.startswith("pi-"):
        names = ("list_calls", "docx_reads", "pdf_reads", "xlsx_reads")
        parts = [_count(trajectory, name) for name in names]
        artifacts = sum(parts) if all(value is not None for value in parts) else None
        completions = _count(trajectory, "finish_report_calls")
        total = native
        sources["artifact_tool_calls"] = [f"trajectory.{name}" for name in names] if artifacts is not None else None
        sources["completion_calls"] = "trajectory.finish_report_calls" if completions is not None else None
        if native is not None and artifacts is not None and completions is not None:
            if native != artifacts + completions:
                raise RunnerError("Pi native tool count disagrees with artifact/completion split")
    else:
        artifacts = native
        completions = None
        turns = record.get("turns")
        if turns is not None:
            if not isinstance(turns, list) or not all(isinstance(turn, dict) for turn in turns):
                raise RunnerError("Mini turns must be an array of objects")
            completions = sum(turn.get("action") == "finish_report" for turn in turns)
            observed_artifacts = sum(turn.get("action") in ARTIFACT_ACTIONS for turn in turns)
            if artifacts is not None and artifacts != observed_artifacts:
                raise RunnerError("Mini native tool count disagrees with recorded artifact actions")
        total = artifacts + completions if artifacts is not None and completions is not None else None
        sources["artifact_tool_calls"] = "trajectory.tool_calls" if artifacts is not None else None
        sources["completion_calls"] = "turns[].action=finish_report" if completions is not None else None
    return {
        "system_id": system,
        "model_requests": requests,
        "model_requests_status": "recorded" if requests is not None else "unknown",
        "model_requests_unknown_reason": None if requests is not None else "Adapter did not record trajectory.model_requests; agent turns are not HTTP request counts.",
        "artifact_tool_calls": artifacts,
        "completion_calls": completions,
        "total_tool_or_action_calls": total,
        "agent_turns": _count(trajectory, "agent_turns"),
        "adapter_tool_calls": native,
        "adapter_tool_calls_include_completion": system.startswith("pi-"),
        "counter_sources": sources,
    }


def aggregate_metrics(units: list[dict[str, Any]]) -> dict[str, Any]:
    """A total is known only if every contributing unit records the metric."""
    if not units:
        raise RunnerError("Cannot aggregate an empty set of metrics")
    result = {}
    for name in METRIC_NAMES:
        values = [_count(unit, name) for unit in units]
        known = [value for value in values if value is not None]
        complete = len(known) == len(values)
        result[name] = {
            "value": sum(known) if complete else None,
            "known_subtotal": sum(known) if known else None,
            "known_unit_count": len(known),
            "unit_count": len(values),
            "complete": complete,
        }
    return result


def build_metrics_report(repo_root: Path, study_dir: Path) -> dict[str, Any]:
    """Read completed evidence; do not rewrite its study, outcomes or reports."""
    from . import multi_format_transfer_smoke as original
    from . import multi_format_transfer_smoke_v03 as current

    directory = resolve_repo_path(repo_root, study_dir)
    preliminary = load_json(directory / "study.json")
    plan_id = preliminary.get("plan", {}).get("plan_id")
    if plan_id == current.PLAN_ID:
        with current._configured_base():
            _, study, loaded = original._load_study(repo_root, directory)
    elif plan_id == "multi-format-transfer-smoke-v0.2":
        _, study, loaded = original._load_study(repo_root, directory)
    else:
        raise RunnerError("Unsupported supplier study identity")
    units = study.get("units", [])
    if (
        study.get("status") not in {"complete", "complete_with_failures"}
        or study.get("terminal_unit_count") != 2
        or len(units) != 2
        or any(unit.get("status") not in {"complete", "failed"} for unit in units)
    ):
        raise RunnerError("Metrics reporting requires two terminal units")
    contract = load_json(repo_root / CONTRACT_PATH)
    if contract.get("metrics_version") != VERSION:
        raise RunnerError("Unexpected metrics contract version")
    normalized = []
    for unit in units:
        run_path = resolve_repo_path(repo_root, Path(unit["run_dir"])) / "run.json"
        run = load_json(run_path)
        if run.get("harness", {}).get("harness_id") != unit["system_id"]:
            raise RunnerError("Run/study system mismatch")
        if run.get("trajectory") != unit.get("trajectory"):
            raise RunnerError("Raw trajectory differs from the terminal study snapshot")
        normalized.append({
            "position": unit["position"],
            "source_run_sha256": sha256_file(run_path),
            **normalize_run(run),
        })
    return {
        "schema_version": "1.0.0",
        "report_id": f"{plan_id}-metrics-v0.2",
        "metrics_version": VERSION,
        "contract": {"path": CONTRACT_PATH.as_posix(), "sha256": sha256_file(repo_root / CONTRACT_PATH)},
        "source_study": {"study_id": study["study_id"], "sha256": sha256_file(directory / "study.json"), "plan_id": plan_id, "plan_sha256": loaded["sha256"]},
        "runtime": {"name": "ollama", "version": study["ollama_version"]},
        "model": loaded["plan"]["deployment"]["name"],
        "evidence_class": study["evidence_class"],
        "units": normalized,
        "totals": aggregate_metrics(normalized),
        "historical_outcomes_changed": False,
        "inference_performed": False,
        "interpretation": [
            "Unknown HTTP request counts are null and are never inferred from agent turns.",
            "A known subtotal is not a complete total when coverage is incomplete.",
            "Artifact operations include inventory and reads; report completion is counted separately.",
            "Native Pi tools and Mini actions are different system interactions; these counts alone do not establish efficiency.",
            "This derived metrics version does not rescore or rewrite historical semantic or prose outcomes.",
        ],
    }


def _markdown(report: dict[str, Any]) -> str:
    def shown(value: Any) -> str:
        return "unknown" if value is None else str(value)

    lines = [
        "# Supplier smoke metrics v0.2",
        "",
        f"Source: `{report['source_study']['study_id']}`; Ollama `{report['runtime']['version']}`.",
        "",
        "| System | HTTP requests | Artifact operations | Report completions | Agent turns |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for unit in report["units"]:
        lines.append(f"| `{unit['system_id']}` | {shown(unit['model_requests'])} | {shown(unit['artifact_tool_calls'])} | {shown(unit['completion_calls'])} | {shown(unit['agent_turns'])} |")
    requests = report["totals"]["model_requests"]
    lines.extend([
        "",
        f"Pair HTTP request total: **{shown(requests['value'])}**. Recorded subtotal: {shown(requests['known_subtotal'])}, covering {requests['known_unit_count']}/{requests['unit_count']} systems.",
        "",
        *[f"- {item}" for item in report["interpretation"]],
        "",
    ])
    return "\n".join(lines)


def write_metrics_report(repo_root: Path, study_dir: Path, output_dir: Path) -> dict[str, Any]:
    report = build_metrics_report(repo_root, study_dir)
    destination = resolve_repo_path(repo_root, output_dir)
    paths = [destination / f"{report['report_id']}.{suffix}" for suffix in ("json", "md")]
    if any(path.exists() for path in paths):
        raise RunnerError("Metrics report destination exists; refusing to overwrite")
    destination.mkdir(parents=True, exist_ok=True)
    with paths[0].open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2, sort_keys=True)
        output.write("\n")
    with paths[1].open("x", encoding="utf-8") as output:
        output.write(_markdown(report))
    return {"report_id": report["report_id"], "paths": [str(path) for path in paths]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/agentic"))
    args = parser.parse_args(argv)
    result = write_metrics_report(Path.cwd().resolve(), args.study_dir, args.output_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
