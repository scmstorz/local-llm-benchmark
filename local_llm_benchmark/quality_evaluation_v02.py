"""Irreversible blind-evaluation pipeline for repeated quality studies.

The pipeline is additive to the frozen v0.1 execution controller. It never
opens model mappings or study performance data before both scalar and pairwise
judgments have been validated, written, and content-hashed.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import tempfile
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

from .json_schema import JsonSchemaError, validate_json
from .runner import RunnerError, load_json, resolve_repo_path, sha256_file, utc_now


EVALUATION_DIR_NAME = "evaluation-v0.2"
STATE_FILE_NAME = "state.json"
SCALAR_FREEZE_FILE_NAME = "scalar-freeze.json"
PAIRWISE_FREEZE_FILE_NAME = "pairwise-freeze.json"
REVEALED_FILE_NAME = "revealed-results.json"
AGGREGATE_FILE_NAME = "aggregate-public.json"
REPORT_FILE_NAME = "report-public.md"
PHASES = ("initialized", "scalar_frozen", "pairwise_frozen", "revealed")
USABLE_VERDICTS = {"excellent", "good", "usable"}


def _atomic_write_json(path: Path, value: Any, *, replace: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not replace:
        raise RunnerError(f"Refusing to overwrite immutable artifact: {path}")
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists() and not replace:
            raise RunnerError(f"Refusing to overwrite immutable artifact: {path}")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RunnerError(f"Refusing to overwrite immutable artifact: {path}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            raise RunnerError(f"Refusing to overwrite immutable artifact: {path}")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _safe_child(parent: Path, relative: str) -> Path:
    path = (parent / relative).resolve()
    parent_resolved = parent.resolve()
    if path != parent_resolved and parent_resolved not in path.parents:
        raise RunnerError(f"Artifact escapes judge bundle: {relative}")
    return path


def _bundle_index(study_dir: Path) -> list[dict[str, Any]]:
    """Read only anonymized bundle material, never private maps or study data."""

    bundles_root = study_dir / "judge-bundles"
    if not bundles_root.is_dir():
        raise RunnerError(f"Judge bundles do not exist: {bundles_root}")
    bundles: list[dict[str, Any]] = []
    global_candidates: set[str] = set()
    for bundle_dir in sorted(path for path in bundles_root.iterdir() if path.is_dir()):
        manifest_path = bundle_dir / "manifest.json"
        manifest = load_json(manifest_path)
        if manifest.get("anonymized") is not True:
            raise RunnerError(f"Judge bundle is not anonymized: {bundle_dir.name}")
        if manifest.get("model_identity_included") is not False:
            raise RunnerError(f"Judge bundle exposes model identity: {bundle_dir.name}")
        candidate_ids = manifest.get("candidate_ids")
        if not isinstance(candidate_ids, list) or not candidate_ids or not all(
            isinstance(item, str) and item for item in candidate_ids
        ):
            raise RunnerError(f"Invalid candidate_ids in {manifest_path}")
        if len(candidate_ids) != len(set(candidate_ids)):
            raise RunnerError(f"Duplicate candidate ID in {manifest_path}")
        duplicate_global = global_candidates.intersection(candidate_ids)
        if duplicate_global:
            raise RunnerError(
                "Candidate IDs must be globally unique: "
                + ", ".join(sorted(duplicate_global))
            )
        global_candidates.update(candidate_ids)

        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise RunnerError(f"Judge bundle has no artifact manifest: {bundle_dir.name}")
        artifact_hashes: dict[str, str] = {}
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                raise RunnerError(f"Invalid artifact record in {manifest_path}")
            relative = artifact.get("path")
            expected = artifact.get("sha256")
            if not isinstance(relative, str) or not isinstance(expected, str):
                raise RunnerError(f"Invalid artifact record in {manifest_path}")
            if relative in artifact_hashes:
                raise RunnerError(f"Duplicate artifact path in {manifest_path}: {relative}")
            path = _safe_child(bundle_dir, relative)
            if not path.is_file():
                raise RunnerError(f"Judge bundle artifact is missing: {path}")
            actual = sha256_file(path)
            if actual != expected:
                raise RunnerError(f"Judge bundle artifact changed: {path}")
            artifact_hashes[relative] = expected

        schema_paths = [
            relative
            for relative in artifact_hashes
            if relative.endswith("judge-result.schema.json")
        ]
        if len(schema_paths) != 1:
            raise RunnerError(
                f"Expected exactly one judge-result schema in {bundle_dir.name}"
            )
        schema_path = _safe_child(bundle_dir, schema_paths[0])
        schema = load_json(schema_path)
        pairwise_path = bundle_dir / "pairwise-plan.json"
        if "pairwise-plan.json" not in artifact_hashes:
            raise RunnerError(f"Pairwise plan is not frozen in {bundle_dir.name}")
        pairwise_plan = load_json(pairwise_path)

        candidates: dict[str, dict[str, Any]] = {}
        for candidate_id in candidate_ids:
            candidate_relative = f"candidates/{candidate_id}.md"
            checks_relative = f"checks/{candidate_id}.json"
            if candidate_relative not in artifact_hashes:
                raise RunnerError(f"Candidate is not frozen: {candidate_id}")
            if checks_relative not in artifact_hashes:
                raise RunnerError(f"Candidate checks are not frozen: {candidate_id}")
            candidates[candidate_id] = {
                "content_sha256": artifact_hashes[candidate_relative],
                "checks": load_json(_safe_child(bundle_dir, checks_relative)),
            }

        case_id = manifest.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise RunnerError(f"Judge bundle has no case_id: {bundle_dir.name}")
        if pairwise_plan.get("case_id") != case_id:
            raise RunnerError(f"Pairwise case identity changed: {bundle_dir.name}")
        pairs = pairwise_plan.get("pairs")
        if not isinstance(pairs, list):
            raise RunnerError(f"Invalid pairwise plan for {bundle_dir.name}")
        pair_ids: set[str] = set()
        for pair in pairs:
            if not isinstance(pair, dict) or set(pair) != {
                "pair_id",
                "repetition",
                "candidate_a",
                "candidate_b",
            }:
                raise RunnerError(f"Invalid pair record in {bundle_dir.name}")
            pair_id = pair.get("pair_id")
            repetition = pair.get("repetition")
            candidate_a = pair.get("candidate_a")
            candidate_b = pair.get("candidate_b")
            if not isinstance(pair_id, str) or not pair_id or pair_id in pair_ids:
                raise RunnerError(f"Invalid or duplicate pair_id in {bundle_dir.name}")
            if not isinstance(repetition, int) or isinstance(repetition, bool) or repetition < 1:
                raise RunnerError(f"Invalid pair repetition in {bundle_dir.name}")
            if (
                candidate_a not in candidates
                or candidate_b not in candidates
                or candidate_a == candidate_b
            ):
                raise RunnerError(f"Invalid pair candidates in {bundle_dir.name}")
            pair_ids.add(pair_id)
        bundles.append(
            {
                "case_alias": bundle_dir.name,
                "case_id": case_id,
                "manifest_sha256": sha256_file(manifest_path),
                "schema_sha256": sha256_file(schema_path),
                "schema": schema,
                "candidate_ids": sorted(candidate_ids),
                "candidates": candidates,
                "pairs": pairs,
            }
        )
    if not bundles:
        raise RunnerError("No anonymized judge bundles found")
    return bundles


def _fingerprints(bundles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "case_alias": bundle["case_alias"],
            "case_id": bundle["case_id"],
            "manifest_sha256": bundle["manifest_sha256"],
            "schema_sha256": bundle["schema_sha256"],
            "candidate_ids": bundle["candidate_ids"],
        }
        for bundle in bundles
    ]


def _evaluation_dir(study_dir: Path) -> Path:
    return study_dir / EVALUATION_DIR_NAME


def _state_path(study_dir: Path) -> Path:
    return _evaluation_dir(study_dir) / STATE_FILE_NAME


def _load_state(study_dir: Path) -> dict[str, Any]:
    state = load_json(_state_path(study_dir))
    if state.get("schema_version") != "quality_evaluation_state_v0.2":
        raise RunnerError("Unsupported quality evaluation state")
    if state.get("phase") not in PHASES:
        raise RunnerError("Invalid quality evaluation phase")
    return state


def _write_state(study_dir: Path, state: dict[str, Any]) -> None:
    _atomic_write_json(_state_path(study_dir), state, replace=True)


def _verify_bundle_state(
    study_dir: Path, state: dict[str, Any]
) -> list[dict[str, Any]]:
    bundles = _bundle_index(study_dir)
    if _fingerprints(bundles) != state.get("bundle_fingerprints"):
        raise RunnerError("An anonymized judge bundle changed after evaluation init")
    return bundles


def _verify_freeze(study_dir: Path, state: dict[str, Any], key: str) -> Path:
    record = state.get("artifacts", {}).get(key)
    if not isinstance(record, dict):
        raise RunnerError(f"Evaluation state has no {key} artifact")
    relative = record.get("path")
    expected = record.get("sha256")
    if not isinstance(relative, str) or not isinstance(expected, str):
        raise RunnerError(f"Evaluation state has an invalid {key} artifact")
    path = _safe_child(_evaluation_dir(study_dir), relative)
    if not path.is_file() or sha256_file(path) != expected:
        raise RunnerError(f"Immutable {key} artifact is missing or changed")
    return path


def _verify_recorded_output(
    study_dir: Path, state: dict[str, Any], key: str
) -> Path:
    record = state.get("artifacts", {}).get(key)
    if not isinstance(record, dict):
        raise RunnerError(f"Evaluation state has no {key} artifact")
    path_value = record.get("path")
    expected = record.get("sha256")
    if not isinstance(path_value, str) or not isinstance(expected, str):
        raise RunnerError(f"Evaluation state has an invalid {key} artifact")
    path = Path(path_value)
    if not path.is_absolute():
        path = _safe_child(_evaluation_dir(study_dir), path_value)
    if not path.is_file() or sha256_file(path) != expected:
        raise RunnerError(f"Immutable {key} artifact is missing or changed")
    return path


def initialize_evaluation(study_dir: Path) -> dict[str, Any]:
    state_path = _state_path(study_dir)
    if state_path.exists():
        return evaluation_status(study_dir)
    bundles = _bundle_index(study_dir)
    evaluation_dir = _evaluation_dir(study_dir)
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    pairs = sum(len(bundle["pairs"] or []) for bundle in bundles)
    state = {
        "schema_version": "quality_evaluation_state_v0.2",
        "pipeline_version": "0.2.0",
        "phase": "initialized",
        "initialized_at": utc_now(),
        "bundle_fingerprints": _fingerprints(bundles),
        "expected": {
            "cases": len(bundles),
            "scalar_candidates": sum(len(bundle["candidate_ids"]) for bundle in bundles),
            "pairwise_comparisons": pairs,
        },
        "artifacts": {},
    }
    _atomic_write_json(state_path, state, replace=False)
    return evaluation_status(study_dir)


def _load_result_files(results_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    if not results_dir.is_dir():
        raise RunnerError(f"Judge-result directory does not exist: {results_dir}")
    paths = sorted(results_dir.rglob("*.json"))
    if not paths:
        raise RunnerError(f"Judge-result directory contains no JSON files: {results_dir}")
    return [(path, load_json(path)) for path in paths]


def freeze_scalar_results(study_dir: Path, results_dir: Path) -> dict[str, Any]:
    if not _state_path(study_dir).exists():
        initialize_evaluation(study_dir)
    state = _load_state(study_dir)
    if state["phase"] != "initialized":
        _verify_bundle_state(study_dir, state)
        _verify_freeze(study_dir, state, "scalar_freeze")
        return evaluation_status(study_dir)
    bundles = _verify_bundle_state(study_dir, state)
    by_candidate: dict[str, dict[str, Any]] = {}
    evaluation_ids: set[str] = set()
    candidate_to_bundle = {
        candidate_id: bundle
        for bundle in bundles
        for candidate_id in bundle["candidate_ids"]
    }
    for path, result in _load_result_files(results_dir):
        candidate_id = result.get("candidate_id")
        if not isinstance(candidate_id, str):
            raise RunnerError(f"Judge result has no candidate_id: {path}")
        if candidate_id in by_candidate:
            raise RunnerError(f"Duplicate scalar result for {candidate_id}")
        bundle = candidate_to_bundle.get(candidate_id)
        if bundle is None:
            raise RunnerError(f"Unexpected scalar candidate: {candidate_id}")
        try:
            validate_json(result, bundle["schema"])
        except JsonSchemaError as error:
            raise RunnerError(f"Invalid judge result {path}: {error}") from error
        if result.get("deterministic_checks") != bundle["candidates"][candidate_id]["checks"]:
            raise RunnerError(f"Deterministic checks changed for {candidate_id}")
        evaluation_id = result.get("evaluation_id")
        if evaluation_id in evaluation_ids:
            raise RunnerError(f"Duplicate evaluation_id: {evaluation_id}")
        evaluation_ids.add(evaluation_id)
        by_candidate[candidate_id] = {
            "case_alias": bundle["case_alias"],
            "case_id": bundle["case_id"],
            "candidate_id": candidate_id,
            "content_sha256": bundle["candidates"][candidate_id]["content_sha256"],
            "result": result,
        }
    expected = set(candidate_to_bundle)
    observed = set(by_candidate)
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise RunnerError(f"Scalar result coverage mismatch; missing={missing}, extra={extra}")

    freeze = {
        "schema_version": "quality_evaluation_scalar_freeze_v0.2",
        "frozen_at": utc_now(),
        "mapping_opened": False,
        "pairwise_review_started": False,
        "bundle_fingerprints": state["bundle_fingerprints"],
        "candidate_results": [by_candidate[key] for key in sorted(by_candidate)],
    }
    path = _evaluation_dir(study_dir) / SCALAR_FREEZE_FILE_NAME
    _atomic_write_json(path, freeze, replace=False)
    state["phase"] = "scalar_frozen"
    state["scalar_frozen_at"] = freeze["frozen_at"]
    state["artifacts"]["scalar_freeze"] = {
        "path": SCALAR_FREEZE_FILE_NAME,
        "sha256": sha256_file(path),
    }
    _write_state(study_dir, state)
    return evaluation_status(study_dir)


def _validate_pairwise_input(
    value: dict[str, Any], bundles: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if set(value) != {"schema_version", "comparisons"}:
        raise RunnerError("Pairwise input must contain only schema_version and comparisons")
    if value.get("schema_version") != "quality_evaluation_pairwise_input_v0.2":
        raise RunnerError("Unsupported pairwise input schema_version")
    comparisons = value.get("comparisons")
    if not isinstance(comparisons, list):
        raise RunnerError("Pairwise comparisons must be an array")
    expected: dict[tuple[str, str], dict[str, Any]] = {}
    for bundle in bundles:
        pairs = bundle["pairs"]
        if not isinstance(pairs, list):
            raise RunnerError(f"Invalid pairwise plan for {bundle['case_alias']}")
        for pair in pairs:
            if not isinstance(pair, dict):
                raise RunnerError(f"Invalid pairwise plan for {bundle['case_alias']}")
            key = (bundle["case_id"], pair.get("pair_id"))
            if key in expected:
                raise RunnerError(f"Duplicate planned pair: {key}")
            expected[key] = {
                "case_id": bundle["case_id"],
                "pair_id": pair.get("pair_id"),
                "repetition": pair.get("repetition"),
                "candidate_a": pair.get("candidate_a"),
                "candidate_b": pair.get("candidate_b"),
            }
    required = {
        "case_id",
        "pair_id",
        "repetition",
        "candidate_a",
        "candidate_b",
        "preference",
        "rationale",
    }
    observed: dict[tuple[str, str], dict[str, Any]] = {}
    for index, comparison in enumerate(comparisons):
        if not isinstance(comparison, dict) or set(comparison) != required:
            raise RunnerError(f"Pairwise comparison {index} has invalid fields")
        key = (comparison.get("case_id"), comparison.get("pair_id"))
        if key in observed:
            raise RunnerError(f"Duplicate pairwise comparison: {key}")
        planned = expected.get(key)
        if planned is None:
            raise RunnerError(f"Unexpected pairwise comparison: {key}")
        fixed = {key_name: comparison.get(key_name) for key_name in planned}
        if fixed != planned:
            raise RunnerError(f"Pair orientation or identity changed: {key}")
        if comparison.get("preference") not in {"A", "B", "tie"}:
            raise RunnerError(f"Invalid pairwise preference: {key}")
        if not isinstance(comparison.get("rationale"), str) or not comparison["rationale"].strip():
            raise RunnerError(f"Pairwise rationale is empty: {key}")
        observed[key] = comparison
    if set(observed) != set(expected):
        raise RunnerError(
            "Pairwise result coverage mismatch; missing="
            + repr(sorted(set(expected) - set(observed)))
        )
    return [observed[key] for key in sorted(observed)]


def freeze_pairwise_results(study_dir: Path, results_path: Path) -> dict[str, Any]:
    state = _load_state(study_dir)
    if state["phase"] == "initialized":
        raise RunnerError("Scalar results must be frozen before pairwise review")
    bundles = _verify_bundle_state(study_dir, state)
    scalar_path = _verify_freeze(study_dir, state, "scalar_freeze")
    if state["phase"] != "scalar_frozen":
        _verify_freeze(study_dir, state, "pairwise_freeze")
        return evaluation_status(study_dir)
    value = load_json(results_path)
    comparisons = _validate_pairwise_input(value, bundles)
    freeze = {
        "schema_version": "quality_evaluation_pairwise_freeze_v0.2",
        "frozen_at": utc_now(),
        "mapping_opened": False,
        "score_adjustments_permitted": False,
        "scalar_freeze_sha256": sha256_file(scalar_path),
        "bundle_fingerprints": state["bundle_fingerprints"],
        "comparisons": comparisons,
    }
    path = _evaluation_dir(study_dir) / PAIRWISE_FREEZE_FILE_NAME
    _atomic_write_json(path, freeze, replace=False)
    state["phase"] = "pairwise_frozen"
    state["pairwise_frozen_at"] = freeze["frozen_at"]
    state["artifacts"]["pairwise_freeze"] = {
        "path": PAIRWISE_FREEZE_FILE_NAME,
        "sha256": sha256_file(path),
    }
    _write_state(study_dir, state)
    return evaluation_status(study_dir)


def _stats(values: list[float]) -> dict[str, Any] | None:
    if not values:
        return None
    numeric = [float(value) for value in values]
    result: dict[str, Any] = {
        "n": len(numeric),
        "values": numeric,
        "mean": statistics.fmean(numeric),
        "median_p50": statistics.median(numeric),
        "standard_deviation_sample": statistics.stdev(numeric) if len(numeric) > 1 else 0.0,
        "minimum": min(numeric),
        "maximum": max(numeric),
    }
    return result


def _deterministic_pass(checks: dict[str, Any]) -> bool:
    required_true = {
        "nonempty",
        "language_pass",
        "maximum_words_pass",
        "source_location_labels_absent",
        "heading_pass",
        "reasoning_markup_absent",
        "generation_complete",
    }
    return required_true.issubset(checks) and all(
        checks[key] is True for key in required_true
    )


def _counter_records(counter: Counter[str]) -> list[dict[str, Any]]:
    return [
        {"value": value, "count": count}
        for value, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def _build_aggregate(
    *,
    study: dict[str, Any],
    plan: dict[str, Any],
    mapping: dict[str, Any],
    scalar: dict[str, Any],
    pairwise: dict[str, Any],
    scalar_hash: str,
    pairwise_hash: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    deployments = {item["alias"]: item for item in plan["deployments"]}
    cases = {item["alias"]: item for item in plan["cases"]}
    units = {item["unit_id"]: item for item in study["units"]}
    candidate_results = {
        item["candidate_id"]: item for item in scalar["candidate_results"]
    }
    if set(mapping) != set(candidate_results):
        raise RunnerError("Private candidate mapping does not exactly cover scalar results")

    joined: list[dict[str, Any]] = []
    for candidate_id in sorted(candidate_results):
        scalar_item = candidate_results[candidate_id]
        private = mapping[candidate_id]
        if private.get("case_id") != scalar_item["case_id"]:
            raise RunnerError(f"Candidate case mapping changed: {candidate_id}")
        unit = units.get(private.get("unit_id"))
        if unit is None or unit.get("run", {}).get("run_id") != private.get("run_id"):
            raise RunnerError(f"Candidate run mapping changed: {candidate_id}")
        result = scalar_item["result"]
        joined.append(
            {
                "candidate_id": candidate_id,
                "content_sha256": scalar_item["content_sha256"],
                "case_alias": scalar_item["case_alias"],
                "case_id": scalar_item["case_id"],
                "model": private["model"],
                "digest": private["digest"],
                "repetition": private["repetition"],
                "run_id": private["run_id"],
                "unit_id": private["unit_id"],
                "score": result["score_summary"]["final_total"],
                "verdict": result["verdict"],
                "errors": result["errors"],
                "deterministic_checks": result["deterministic_checks"],
                "metrics": unit.get("run", {}).get("metrics") or {},
            }
        )

    pair_records: list[dict[str, Any]] = []
    pair_totals: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for comparison in pairwise["comparisons"]:
        left = mapping[comparison["candidate_a"]]
        right = mapping[comparison["candidate_b"]]
        if left["case_id"] != comparison["case_id"] or right["case_id"] != comparison["case_id"]:
            raise RunnerError(f"Pairwise mapping changed: {comparison['pair_id']}")
        preference = comparison["preference"]
        if preference == "tie":
            pair_totals[(left["model"], comparison["case_id"])]["ties"] += 1
            pair_totals[(right["model"], comparison["case_id"])]["ties"] += 1
            preferred_model = None
        else:
            winner = left if preference == "A" else right
            loser = right if preference == "A" else left
            pair_totals[(winner["model"], comparison["case_id"])]["wins"] += 1
            pair_totals[(loser["model"], comparison["case_id"])]["losses"] += 1
            preferred_model = winner["model"]
        pair_records.append(
            {
                **comparison,
                "model_a": left["model"],
                "model_b": right["model"],
                "preferred_model": preferred_model,
            }
        )

    result_rows: list[dict[str, Any]] = []
    for case_alias, case in cases.items():
        for deployment_alias, deployment in deployments.items():
            condition_units = [
                unit
                for unit in study["units"]
                if unit.get("case_alias") == case_alias
                and unit.get("deployment_alias") == deployment_alias
            ]
            condition_candidates = sorted(
                (
                    item
                    for item in joined
                    if item["case_id"] == case["case_id"]
                    and item["model"] == deployment["name"]
                ),
                key=lambda item: item["repetition"],
            )
            scores = [float(item["score"]) for item in condition_candidates]
            verdicts = Counter(item["verdict"] for item in condition_candidates)
            error_types: Counter[str] = Counter()
            error_severities: Counter[str] = Counter()
            known_errors: Counter[str] = Counter()
            for item in condition_candidates:
                for error in item["errors"]:
                    error_types[error["type"]] += 1
                    error_severities[error["severity"]] += 1
                    known_id = error.get("known_error_id")
                    if known_id:
                        known_errors[known_id] += 1
            hashes = Counter(item["content_sha256"] for item in condition_candidates)
            duplicate_groups = sorted(
                (count for count in hashes.values() if count > 1), reverse=True
            )
            failures = Counter(
                (unit.get("failure") or {}).get("category", "unclassified")
                for unit in condition_units
                if unit.get("status") != "complete"
            )
            metric_names = {
                "wall_time_seconds": "wall_time_seconds",
                "time_to_first_content_seconds": "time_to_first_content_seconds",
                "generation_duration_seconds": "eval_duration_seconds",
                "output_tokens_per_second": "output_tokens_per_second",
            }
            performance = {
                output_name: _stats(
                    [
                        float(item["metrics"][source_name])
                        for item in condition_candidates
                        if isinstance(item["metrics"].get(source_name), (int, float))
                    ]
                )
                for output_name, source_name in metric_names.items()
            }
            pair_count = pair_totals[(deployment["name"], case["case_id"])]
            result_rows.append(
                {
                    "case_id": case["case_id"],
                    "model": deployment["name"],
                    "digest": deployment["digest"],
                    "quality": {
                        "scores_by_repetition": [
                            {"repetition": item["repetition"], "score": item["score"]}
                            for item in condition_candidates
                        ],
                        "score_distribution": _stats(scores),
                        "usable_outputs": sum(
                            item["verdict"] in USABLE_VERDICTS
                            for item in condition_candidates
                        ),
                        "verdicts": _counter_records(verdicts),
                        "deterministic_compliance": sum(
                            _deterministic_pass(item["deterministic_checks"])
                            for item in condition_candidates
                        ),
                    },
                    "variation": {
                        "evaluated_outputs": len(condition_candidates),
                        "unique_response_hashes": len(hashes),
                        "byte_identical_group_sizes": duplicate_groups,
                    },
                    "errors": {
                        "total": sum(error_types.values()),
                        "by_type": _counter_records(error_types),
                        "by_severity": _counter_records(error_severities),
                        "known_error_ids": _counter_records(known_errors),
                        "recurring_types": _counter_records(
                            Counter({key: value for key, value in error_types.items() if value > 1})
                        ),
                        "recurring_known_error_ids": _counter_records(
                            Counter({key: value for key, value in known_errors.items() if value > 1})
                        ),
                    },
                    "pairwise": {
                        "wins": pair_count["wins"],
                        "losses": pair_count["losses"],
                        "ties": pair_count["ties"],
                    },
                    "reliability": {
                        "planned_runs": len(condition_units),
                        "technical_successes": sum(
                            unit.get("status") == "complete" for unit in condition_units
                        ),
                        "technical_failures": sum(
                            unit.get("status") != "complete" for unit in condition_units
                        ),
                        "failure_categories": _counter_records(failures),
                    },
                    "performance": performance,
                }
            )

    aggregate = {
        "schema_version": "quality_evaluation_public_aggregate_v0.2",
        "pipeline_version": "0.2.0",
        "generated_at": utc_now(),
        "study_id": study.get("study_id"),
        "source_freezes": {
            "scalar_sha256": scalar_hash,
            "pairwise_sha256": pairwise_hash,
        },
        "interpretation": {
            "score_scale": "0-100 within each task-specific rubric",
            "small_sample_rule": (
                "Raw values, mean, median, sample standard deviation, minimum and "
                "maximum are reported. No P90, P95, P99 or precise reliability "
                "probability is inferred for n < 10."
            ),
            "composite_score": False,
        },
        "results": sorted(result_rows, key=lambda item: (item["case_id"], item["model"])),
    }
    revealed = {
        "schema_version": "quality_evaluation_revealed_v0.2",
        "revealed_at": utc_now(),
        "study_id": study.get("study_id"),
        "source_freezes": aggregate["source_freezes"],
        "candidate_results": joined,
        "pairwise_results": pair_records,
    }
    return aggregate, revealed


def render_public_report(aggregate: dict[str, Any]) -> str:
    lines = [
        "# Repeated Quality Evaluation",
        "",
        f"Study: `{aggregate.get('study_id')}`",
        "",
        "This report was generated only after scalar and pairwise judgments were",
        "schema-validated, frozen, and content-hashed. Model identity and runtime",
        "metadata were revealed afterwards.",
        "",
        "Scores use task-specific 0–100 rubrics. Quality, reliability, performance",
        "and variation remain separate; no composite score is reported. With this",
        "small sample, timings are descriptive and no tail percentiles or precise",
        "failure probabilities are claimed.",
        "",
        "## Results",
        "",
        "| Case | Model | Scores | Mean | Median | Range | Pair W-L-T | Unique outputs | Technical |",
        "| --- | --- | --- | ---: | ---: | --- | --- | ---: | --- |",
    ]
    for row in aggregate["results"]:
        distribution = row["quality"]["score_distribution"]
        if distribution is None:
            scores = "—"
            mean = median = range_text = "—"
        else:
            scores = ", ".join(
                str(item["score"]) for item in row["quality"]["scores_by_repetition"]
            )
            mean = f"{distribution['mean']:.2f}"
            median = f"{distribution['median_p50']:.2f}"
            range_text = f"{distribution['minimum']:g}–{distribution['maximum']:g}"
        pairwise = row["pairwise"]
        reliability = row["reliability"]
        lines.append(
            f"| `{row['case_id']}` | `{row['model']}` | {scores} | {mean} | "
            f"{median} | {range_text} | {pairwise['wins']}-{pairwise['losses']}-"
            f"{pairwise['ties']} | {row['variation']['unique_response_hashes']} | "
            f"{reliability['technical_successes']}/{reliability['planned_runs']} |"
        )
    lines.extend(["", "## Recurring errors", ""])
    any_recurring = False
    for row in aggregate["results"]:
        recurring = row["errors"]["recurring_types"]
        known = row["errors"]["recurring_known_error_ids"]
        if not recurring and not known:
            continue
        any_recurring = True
        descriptions = [f"{item['value']} × {item['count']}" for item in recurring]
        descriptions.extend(f"{item['value']} × {item['count']}" for item in known)
        lines.append(
            f"- `{row['case_id']}` / `{row['model']}`: " + ", ".join(descriptions)
        )
    if not any_recurring:
        lines.append("No recurring judged error category was observed.")
    lines.extend(
        [
            "",
            "## Freeze provenance",
            "",
            f"- Scalar judgments: `{aggregate['source_freezes']['scalar_sha256']}`",
            f"- Pairwise judgments: `{aggregate['source_freezes']['pairwise_sha256']}`",
            "",
        ]
    )
    return "\n".join(lines)


def reveal_and_aggregate(
    repo_root: Path,
    study_dir: Path,
    *,
    aggregate_path: Path | None = None,
    report_path: Path | None = None,
) -> dict[str, Any]:
    state = _load_state(study_dir)
    if state["phase"] in {"initialized", "scalar_frozen"}:
        raise RunnerError("Both scalar and pairwise results must be frozen before reveal")
    _verify_bundle_state(study_dir, state)
    scalar_path = _verify_freeze(study_dir, state, "scalar_freeze")
    pairwise_path = _verify_freeze(study_dir, state, "pairwise_freeze")
    if state["phase"] == "revealed":
        return evaluation_status(study_dir)

    scalar = load_json(scalar_path)
    pairwise = load_json(pairwise_path)
    if pairwise.get("scalar_freeze_sha256") != sha256_file(scalar_path):
        raise RunnerError("Pairwise freeze is not bound to the current scalar freeze")

    private_map_record = load_json(study_dir / "judge-bundles" / "private-map.json")
    mapping = private_map_record.get("private_model_mapping")
    if not isinstance(mapping, dict):
        raise RunnerError("Private judge-bundle map is invalid")
    study = load_json(study_dir / "study.json")
    plan_record = study.get("plan", {})
    plan_path_value = plan_record.get("path")
    if not isinstance(plan_path_value, str):
        raise RunnerError("Study record has no frozen plan path")
    plan_path = resolve_repo_path(repo_root, plan_path_value)
    if sha256_file(plan_path) != plan_record.get("sha256"):
        raise RunnerError("Study plan changed before evaluation reveal")
    plan = load_json(plan_path)

    aggregate, revealed = _build_aggregate(
        study=study,
        plan=plan,
        mapping=mapping,
        scalar=scalar,
        pairwise=pairwise,
        scalar_hash=sha256_file(scalar_path),
        pairwise_hash=sha256_file(pairwise_path),
    )
    evaluation_dir = _evaluation_dir(study_dir)
    revealed_path = evaluation_dir / REVEALED_FILE_NAME
    resolved_aggregate = (
        resolve_repo_path(repo_root, aggregate_path)
        if aggregate_path is not None
        else evaluation_dir / AGGREGATE_FILE_NAME
    )
    resolved_report = (
        resolve_repo_path(repo_root, report_path)
        if report_path is not None
        else evaluation_dir / REPORT_FILE_NAME
    )
    output_paths = (revealed_path, resolved_aggregate, resolved_report)
    if len({path.resolve() for path in output_paths}) != len(output_paths):
        raise RunnerError("Reveal output paths must be distinct")
    existing = [path for path in output_paths if path.exists()]
    if existing:
        raise RunnerError(
            "Refusing reveal because an immutable output already exists: "
            + ", ".join(str(path) for path in existing)
        )
    _atomic_write_json(revealed_path, revealed, replace=False)
    _atomic_write_json(resolved_aggregate, aggregate, replace=False)
    _atomic_write_text(resolved_report, render_public_report(aggregate))

    state["phase"] = "revealed"
    state["revealed_at"] = revealed["revealed_at"]
    state["artifacts"].update(
        {
            "revealed_results": {
                "path": REVEALED_FILE_NAME,
                "sha256": sha256_file(revealed_path),
            },
            "public_aggregate": {
                "path": str(resolved_aggregate),
                "sha256": sha256_file(resolved_aggregate),
            },
            "public_report": {
                "path": str(resolved_report),
                "sha256": sha256_file(resolved_report),
            },
        }
    )
    _write_state(study_dir, state)
    return evaluation_status(study_dir)


def evaluation_status(study_dir: Path) -> dict[str, Any]:
    state_path = _state_path(study_dir)
    if not state_path.is_file():
        return {"pipeline_version": "0.2.0", "phase": "not_initialized"}
    state = _load_state(study_dir)
    _verify_bundle_state(study_dir, state)
    if state["phase"] in {"scalar_frozen", "pairwise_frozen", "revealed"}:
        _verify_freeze(study_dir, state, "scalar_freeze")
    if state["phase"] in {"pairwise_frozen", "revealed"}:
        _verify_freeze(study_dir, state, "pairwise_freeze")
    if state["phase"] == "revealed":
        _verify_recorded_output(study_dir, state, "revealed_results")
        _verify_recorded_output(study_dir, state, "public_aggregate")
        _verify_recorded_output(study_dir, state, "public_report")
    result: dict[str, Any] = {
        "pipeline_version": state["pipeline_version"],
        "phase": state["phase"],
        "expected": deepcopy(state["expected"]),
        "scalar_freeze_sha256": state.get("artifacts", {})
        .get("scalar_freeze", {})
        .get("sha256"),
        "pairwise_freeze_sha256": state.get("artifacts", {})
        .get("pairwise_freeze", {})
        .get("sha256"),
    }
    if state["phase"] == "revealed":
        result["outputs"] = {
            key: deepcopy(state["artifacts"][key])
            for key in ("public_aggregate", "public_report")
        }
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quality-evaluation-v0.2")
    commands = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (
        ("init", "Bind the evaluator to anonymized judge bundles"),
        ("status", "Verify and show the current irreversible phase"),
    ):
        child = commands.add_parser(command, help=help_text)
        child.add_argument("--study-dir", type=Path, required=True)
    scalar = commands.add_parser(
        "freeze-scalars", help="Validate and freeze one scalar result per candidate"
    )
    scalar.add_argument("--study-dir", type=Path, required=True)
    scalar.add_argument("--results-dir", type=Path, required=True)
    pairwise = commands.add_parser(
        "freeze-pairs", help="Validate and freeze all predeclared pairwise results"
    )
    pairwise.add_argument("--study-dir", type=Path, required=True)
    pairwise.add_argument("--results", type=Path, required=True)
    reveal = commands.add_parser(
        "reveal", help="Open the private map and generate private/public aggregates"
    )
    reveal.add_argument("--study-dir", type=Path, required=True)
    reveal.add_argument("--aggregate-json", type=Path)
    reveal.add_argument("--report", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    repo_root = Path.cwd().resolve()
    study_dir = resolve_repo_path(repo_root, args.study_dir).resolve()
    try:
        if args.command == "init":
            result = initialize_evaluation(study_dir)
        elif args.command == "freeze-scalars":
            result = freeze_scalar_results(
                study_dir, resolve_repo_path(repo_root, args.results_dir).resolve()
            )
        elif args.command == "freeze-pairs":
            result = freeze_pairwise_results(
                study_dir, resolve_repo_path(repo_root, args.results).resolve()
            )
        elif args.command == "reveal":
            result = reveal_and_aggregate(
                repo_root,
                study_dir,
                aggregate_path=args.aggregate_json,
                report_path=args.report,
            )
        else:
            result = evaluation_status(study_dir)
    except Exception as error:
        print(json.dumps({"status": "failed", "error": str(error)}))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
