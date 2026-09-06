"""Build sanitized aggregate reports from judged benchmark comparisons."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from statistics import fmean, median
from typing import Any

from .runner import RunnerError, load_json, resolve_repo_path, write_json


DEFAULT_SELECTION_PATH = Path("reports/comparison-selection.json")
DEFAULT_COMPARISONS_DIR = Path("results/comparisons")
DEFAULT_INDEX_OUTPUT = Path("reports/results-index.json")
DEFAULT_MARKDOWN_OUTPUT = Path("reports/overview.md")

COMPLIANCE_CHECKS = (
    "nonempty",
    "generation_complete",
    "language_pass",
    "maximum_words_pass",
    "heading_pass",
    "reasoning_markup_absent",
    "source_location_labels_absent",
)


def _require(value: dict[str, Any], key: str, context: str) -> Any:
    if key not in value:
        raise RunnerError(f"Missing {key!r} in {context}")
    return value[key]


def _number(value: Any, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RunnerError(f"Expected a number for {context}")
    return float(value)


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def _mean(values: list[float]) -> float | None:
    return _round(fmean(values)) if values else None


def _median(values: list[float]) -> float | None:
    return _round(float(median(values))) if values else None


def _phase_metrics(phase: dict[str, Any], context: str) -> dict[str, Any]:
    metrics = _require(phase, "metrics", context)
    if not isinstance(metrics, dict):
        raise RunnerError(f"Expected metrics object in {context}")
    checks = _require(phase, "checks", context)
    if not isinstance(checks, dict):
        raise RunnerError(f"Expected checks object in {context}")
    return {
        "status": phase.get("status"),
        "done_reason": phase.get("done_reason"),
        "wall_time_seconds": _round(
            _number(metrics.get("wall_time_seconds"), f"{context}.wall_time_seconds")
        ),
        "output_tokens_per_second": _round(
            _number(
                metrics.get("output_tokens_per_second"),
                f"{context}.output_tokens_per_second",
            )
        ),
        "word_count": checks.get("word_count"),
    }


def _is_complete(phase: dict[str, Any]) -> bool:
    checks = phase.get("checks", {})
    return phase.get("status") == "complete" and checks.get("generation_complete") is True


def _is_compliant(
    phase: dict[str, Any], inapplicable_checks: frozenset[str] = frozenset()
) -> bool:
    checks = phase.get("checks", {})
    applicable_checks = (
        key for key in COMPLIANCE_CHECKS if key not in inapplicable_checks
    )
    return _is_complete(phase) and all(
        checks.get(key) is True for key in applicable_checks
    )


def _validate_selection(selection: dict[str, Any]) -> list[dict[str, Any]]:
    entries = selection.get("comparisons")
    if not isinstance(entries, list) or not entries:
        raise RunnerError("Selection manifest must contain a non-empty comparisons list")
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("comparison_id"), str):
            raise RunnerError("Each selection entry must define a comparison_id string")
        comparison_id = entry["comparison_id"]
        if comparison_id in seen:
            raise RunnerError(f"Duplicate comparison in selection: {comparison_id}")
        seen.add(comparison_id)
        if entry.get("performance_evidence") not in {"controlled", "confounded"}:
            raise RunnerError(
                f"Selection entry {comparison_id} must classify performance_evidence"
            )
    return entries


def _build_case_result(
    comparison: dict[str, Any],
    quality: dict[str, Any],
    selection_entry: dict[str, Any],
) -> dict[str, Any]:
    comparison_id = selection_entry["comparison_id"]
    if comparison.get("comparison_id") != comparison_id:
        raise RunnerError(f"Comparison ID mismatch for {comparison_id}")
    if quality.get("comparison_id") != comparison_id:
        raise RunnerError(f"Quality-summary ID mismatch for {comparison_id}")
    if comparison.get("status") != "complete":
        raise RunnerError(f"Comparison is not complete: {comparison_id}")

    comparison_case = _require(comparison, "case", comparison_id)
    quality_case = _require(quality, "case", f"{comparison_id} quality summary")
    for key in ("case_id", "case_version"):
        if comparison_case.get(key) != quality_case.get(key):
            raise RunnerError(f"Case {key} mismatch for {comparison_id}")
    case_id = _require(comparison_case, "case_id", comparison_id)

    model_records = comparison.get("models")
    ranking = quality.get("ranking")
    if not isinstance(model_records, list) or not isinstance(ranking, list):
        raise RunnerError(f"Invalid model or ranking list in {comparison_id}")
    by_model: dict[str, dict[str, Any]] = {}
    for record in model_records:
        model = record.get("model") if isinstance(record, dict) else None
        if not isinstance(model, str) or model in by_model:
            raise RunnerError(f"Invalid or duplicate model in {comparison_id}")
        by_model[model] = record

    inapplicable_value = quality.get("inapplicable_compliance_checks", [])
    if not isinstance(inapplicable_value, list) or not all(
        isinstance(item, str) for item in inapplicable_value
    ):
        raise RunnerError(
            f"Invalid inapplicable_compliance_checks in {comparison_id}"
        )
    unknown_checks = set(inapplicable_value) - set(COMPLIANCE_CHECKS)
    if unknown_checks:
        raise RunnerError(
            f"Unknown inapplicable compliance checks in {comparison_id}: "
            f"{sorted(unknown_checks)}"
        )
    inapplicable_checks = frozenset(inapplicable_value)

    results: list[dict[str, Any]] = []
    ranked_models: set[str] = set()
    for ranked in ranking:
        if not isinstance(ranked, dict) or not isinstance(ranked.get("model"), str):
            raise RunnerError(f"Invalid ranking entry in {comparison_id}")
        model = ranked["model"]
        if model in ranked_models or model not in by_model:
            raise RunnerError(f"Unknown or duplicate ranked model {model!r} in {comparison_id}")
        ranked_models.add(model)
        record = by_model[model]
        warm = _require(record, "warm", f"{comparison_id} {model}")
        cold = _require(record, "cold", f"{comparison_id} {model}")
        score = _number(ranked.get("score"), f"{comparison_id} {model} score")
        raw_score = _number(
            ranked.get("raw_score", score), f"{comparison_id} {model} raw_score"
        )
        results.append(
            {
                "model": model,
                "rank": ranked.get("rank"),
                "score": _round(score),
                "raw_score": _round(raw_score),
                "verdict": ranked.get("verdict"),
                "complete": _is_complete(warm),
                "compliant": _is_compliant(warm, inapplicable_checks),
                "warm": _phase_metrics(warm, f"{comparison_id} {model} warm"),
                "cold": _phase_metrics(cold, f"{comparison_id} {model} cold"),
            }
        )
    if ranked_models != set(by_model):
        missing = sorted(set(by_model) - ranked_models)
        raise RunnerError(f"Models missing from quality ranking in {comparison_id}: {missing}")

    options = comparison.get("options", {})
    return {
        "case_id": case_id,
        "case_version": comparison_case.get("case_version"),
        "suite": case_id.split(".dev.", 1)[0],
        "comparison_id": comparison_id,
        "evaluated_at": quality.get("evaluated_at"),
        "performance_evidence": selection_entry["performance_evidence"],
        "selection_note": selection_entry.get("note"),
        "deployment": {
            "ollama_version": comparison.get("ollama_version"),
            "num_ctx": options.get("num_ctx"),
            "num_predict": options.get("num_predict"),
            "temperature": options.get("temperature"),
            "seed": options.get("seed"),
            "think": options.get("think"),
        },
        "results": sorted(results, key=lambda item: (item["rank"], item["model"])),
    }


def _aggregate_models(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        for result in case["results"]:
            grouped[result["model"]].append(result)

    summaries: list[dict[str, Any]] = []
    for model, results in grouped.items():
        scores = [float(item["score"]) for item in results]
        compliant_scores = [
            float(item["score"]) for item in results if item["compliant"]
        ]
        warm_times = [float(item["warm"]["wall_time_seconds"]) for item in results]
        warm_rates = [
            float(item["warm"]["output_tokens_per_second"]) for item in results
        ]
        summaries.append(
            {
                "model": model,
                "case_count": len(results),
                "completed_count": sum(item["complete"] for item in results),
                "compliant_count": sum(item["compliant"] for item in results),
                "invalid_count": sum(item["verdict"] == "invalid" for item in results),
                "penalized_count": sum(item["raw_score"] != item["score"] for item in results),
                "wins": sum(item["rank"] == 1 for item in results),
                "mean_quality_score": _mean(scores),
                "median_quality_score": _median(scores),
                "mean_compliant_quality_score": _mean(compliant_scores),
                "mean_warm_wall_time_seconds": _mean(warm_times),
                "mean_warm_output_tokens_per_second": _mean(warm_rates),
            }
        )
    return sorted(
        summaries,
        key=lambda item: (-float(item["mean_quality_score"]), item["model"]),
    )


def build_results_index(
    repo_root: Path,
    selection_path: Path = DEFAULT_SELECTION_PATH,
    comparisons_dir: Path = DEFAULT_COMPARISONS_DIR,
) -> dict[str, Any]:
    """Load selected local artifacts and return a public-safe aggregate index."""
    selection_file = resolve_repo_path(repo_root, selection_path)
    comparisons_root = resolve_repo_path(repo_root, comparisons_dir)
    selection = load_json(selection_file)
    entries = _validate_selection(selection)

    cases: list[dict[str, Any]] = []
    seen_cases: set[str] = set()
    for entry in entries:
        comparison_id = entry["comparison_id"]
        comparison_root = comparisons_root / comparison_id
        comparison = load_json(comparison_root / "comparison.json")
        quality = load_json(comparison_root / "quality-summary.json")
        case_result = _build_case_result(comparison, quality, entry)
        if case_result["case_id"] in seen_cases:
            raise RunnerError(
                f"Selection contains more than one result for case {case_result['case_id']}"
            )
        seen_cases.add(case_result["case_id"])
        cases.append(case_result)

    evaluated = [case["evaluated_at"] for case in cases if case.get("evaluated_at")]
    return {
        "schema_version": "1.0.0",
        "data_through": max(evaluated) if evaluated else None,
        "selection": {
            "strategy": "explicit_manifest",
            "manifest": selection_path.as_posix(),
            "comparison_count": len(cases),
        },
        "model_summary": _aggregate_models(cases),
        "cases": cases,
    }


def _display(value: Any, suffix: str = "") -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        rendered = f"{value:.2f}".rstrip("0").rstrip(".")
    else:
        rendered = str(value)
    return rendered + suffix


def _escape(value: Any) -> str:
    return str(value).replace("|", "\\|")


def render_markdown(index: dict[str, Any]) -> str:
    """Render a compact human-readable view of a results index."""
    lines = [
        "# Aggregate Benchmark Results",
        "",
        f"Data through: `{index.get('data_through')}`",
        "",
        (
            "This report includes one explicitly selected, judged comparison per case. "
            "Final quality scores include invalid generations and rubric caps; the "
            "compliant mean excludes outputs that failed deterministic format or "
            "completion checks. Performance values are controlled warm-run measurements."
        ),
        "",
        "The table is descriptive, not a claim that one model is universally best. "
        "The current suite is small and contains heterogeneous tasks.",
        "",
        "## Model summary",
        "",
        "| Model | Cases | Complete | Compliant | Invalid | Wins | Mean quality | Compliant mean | Mean warm time | Mean output speed |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in index["model_summary"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape(item["model"]),
                    _display(item["case_count"]),
                    _display(item["completed_count"]),
                    _display(item["compliant_count"]),
                    _display(item["invalid_count"]),
                    _display(item["wins"]),
                    _display(item["mean_quality_score"]),
                    _display(item["mean_compliant_quality_score"]),
                    _display(item["mean_warm_wall_time_seconds"], " s"),
                    _display(item["mean_warm_output_tokens_per_second"], " tok/s"),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Case results", ""])
    for case in index["cases"]:
        lines.extend(
            [
                f"### `{case['case_id']}`",
                "",
                (
                    f"Comparison: `{case['comparison_id']}` · context: "
                    f"{_display(case['deployment']['num_ctx'])} tokens · performance: "
                    f"{case['performance_evidence']}"
                ),
                "",
                "| Rank | Model | Quality | Verdict | Complete | Compliant | Warm time | Output speed | Words |",
                "| ---: | --- | ---: | --- | --- | --- | ---: | ---: | ---: |",
            ]
        )
        for result in case["results"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _display(result["rank"]),
                        _escape(result["model"]),
                        _display(result["score"]),
                        _escape(result["verdict"]),
                        "yes" if result["complete"] else "no",
                        "yes" if result["compliant"] else "no",
                        _display(result["warm"]["wall_time_seconds"], " s"),
                        _display(result["warm"]["output_tokens_per_second"], " tok/s"),
                        _display(result["warm"]["word_count"]),
                    ]
                )
                + " |"
            )
        lines.append("")

    lines.extend(
        [
            "## Rebuild",
            "",
            "```bash",
            "python3 -m local_llm_benchmark report",
            "```",
            "",
            "The generated files contain no candidate IDs, run IDs, prompts, source text, or raw model responses.",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(
    repo_root: Path,
    selection_path: Path = DEFAULT_SELECTION_PATH,
    comparisons_dir: Path = DEFAULT_COMPARISONS_DIR,
    index_output: Path = DEFAULT_INDEX_OUTPUT,
    markdown_output: Path = DEFAULT_MARKDOWN_OUTPUT,
) -> dict[str, Any]:
    """Build and write both machine-readable and Markdown aggregate reports."""
    index = build_results_index(repo_root, selection_path, comparisons_dir)
    index_path = resolve_repo_path(repo_root, index_output)
    markdown_path = resolve_repo_path(repo_root, markdown_output)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(index_path, index)
    markdown_path.write_text(render_markdown(index), encoding="utf-8")
    return {
        "status": "complete",
        "case_count": len(index["cases"]),
        "model_count": len(index["model_summary"]),
        "index_output": index_output.as_posix(),
        "markdown_output": markdown_output.as_posix(),
    }
