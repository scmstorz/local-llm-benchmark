"""Assemble blinded joint-evaluation bundles for one or more late challengers."""

from __future__ import annotations

import random
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .runner import (
    RunnerError,
    create_batch_judge_bundle,
    load_case,
    load_json,
    resolve_repo_path,
    sha256_file,
    utc_now,
    write_json,
)


DEFAULT_SELECTION_PATH = Path("reports/comparison-selection.json")
DEFAULT_COMPARISONS_DIR = Path("results/comparisons")
DEFAULT_RESULTS_DIR = Path("results/runs")
DEFAULT_OUTPUT_DIR = Path("results/challenger-evaluations")


@dataclass(frozen=True)
class ChallengerBundleConfig:
    sweep_dirs: tuple[Path, ...]
    selection_path: Path = DEFAULT_SELECTION_PATH
    comparisons_dir: Path = DEFAULT_COMPARISONS_DIR
    results_dir: Path = DEFAULT_RESULTS_DIR
    output_dir: Path = DEFAULT_OUTPUT_DIR
    allow_late_baseline: bool = False


def challenger_baseline_evidence(
    sweep_case: dict[str, Any],
    *,
    allow_late_baseline: bool,
    challenger_completed_at: str | None = None,
    comparison_completed_at: str | None = None,
) -> str:
    """Classify when canonical baseline evidence became available."""
    if sweep_case.get("canonical_baseline_available") is True:
        return "available_at_challenger_sweep"
    if challenger_completed_at is not None and comparison_completed_at is not None:
        try:
            challenger_time = datetime.fromisoformat(
                _require_string(
                    {"completed_at": challenger_completed_at},
                    "completed_at",
                    "challenger run",
                ).replace("Z", "+00:00")
            )
            comparison_time = datetime.fromisoformat(
                _require_string(
                    {"completed_at": comparison_completed_at},
                    "completed_at",
                    "canonical comparison",
                ).replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise RunnerError("Invalid late-baseline completion timestamp") from exc
        if comparison_time <= challenger_time:
            return "completed_before_challenger_run"
        if allow_late_baseline:
            return "completed_after_challenger_sweep"
        case_id = sweep_case.get("case_id", "<unknown>")
        raise RunnerError(
            "Canonical baseline completed after challenger evidence; pass "
            f"--allow-late-baseline to opt in: {case_id}"
        )
    case_id = sweep_case.get("case_id", "<unknown>")
    raise RunnerError(f"Sweep case is not marked baseline-compatible: {case_id}")


def summarize_candidate_counts(counts: list[int]) -> dict[str, int | None]:
    """Report an exact scalar only when every case has the same candidate count."""
    if not counts:
        return {
            "candidate_count_per_case": None,
            "minimum_candidate_count": None,
            "maximum_candidate_count": None,
        }
    return {
        "candidate_count_per_case": counts[0] if len(set(counts)) == 1 else None,
        "minimum_candidate_count": min(counts),
        "maximum_candidate_count": max(counts),
    }


def _require_string(value: dict[str, Any], key: str, context: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise RunnerError(f"Missing {key!r} in {context}")
    return result


def _load_run_candidate(
    *,
    results_dir: Path,
    run_id: str,
    expected_case_id: str,
) -> dict[str, Any]:
    run_dir = results_dir / run_id
    run = load_json(run_dir / "run.json")
    if run.get("status") != "complete":
        raise RunnerError(f"Source run is not complete: {run_id}")
    if run.get("case", {}).get("case_id") != expected_case_id:
        raise RunnerError(f"Source run case mismatch: {run_id}")
    response_path = run_dir / "response.md"
    checks_path = run_dir / "checks.json"
    response_text = response_path.read_text(encoding="utf-8").strip()
    checks = load_json(checks_path)
    if checks != run.get("checks"):
        raise RunnerError(f"Checks differ between run record and artifact: {run_id}")
    return {
        "run": run,
        "response_text": response_text,
        "response_sha256": sha256_file(response_path),
        "checks": checks,
        "checks_sha256": sha256_file(checks_path),
    }


def _validate_candidate_case(
    candidate: dict[str, Any],
    loaded_case: dict[str, Any],
    context: str,
) -> None:
    run_case = candidate["run"].get("case", {})
    current_case = loaded_case["case"]
    expected = {
        "case_id": current_case.get("case_id"),
        "case_version": current_case.get("case_version"),
        "prompt_version": current_case.get("prompt", {}).get("version"),
        "source_sha256": loaded_case.get("source_hash"),
    }
    for key, value in expected.items():
        if run_case.get(key) != value:
            raise RunnerError(f"{context} {key} does not match the current case")


def challenger_completion_result(record: dict[str, Any], batch_dir: Path) -> dict[str, Any]:
    """Return a console-safe batch summary without candidate or model mapping."""
    return {
        "batch_id": record["batch_id"],
        "batch_dir": str(batch_dir),
        "status": record["status"],
        "case_count": record["case_count"],
        "candidate_count_per_case": record["candidate_count_per_case"],
        "minimum_candidate_count": record["minimum_candidate_count"],
        "maximum_candidate_count": record["maximum_candidate_count"],
        "judge_bundles": record["judge_bundles"],
        "blinding_notice": (
            "Candidate-to-model mappings are withheld and stored only in the "
            "batch private-map.json."
        ),
    }


def assemble_challenger_bundle_batch(
    repo_root: Path,
    config: ChallengerBundleConfig,
) -> dict[str, Any]:
    """Combine exact canonical warm outputs and all challenger warm outputs per case."""
    selection_path = resolve_repo_path(repo_root, config.selection_path)
    comparisons_dir = resolve_repo_path(repo_root, config.comparisons_dir)
    results_dir = resolve_repo_path(repo_root, config.results_dir)
    output_dir = resolve_repo_path(repo_root, config.output_dir)

    if not config.sweep_dirs:
        raise RunnerError("At least one completed challenger sweep is required")
    resolved_sweep_dirs = [
        resolve_repo_path(repo_root, sweep_dir) for sweep_dir in config.sweep_dirs
    ]
    if len(set(resolved_sweep_dirs)) != len(resolved_sweep_dirs):
        raise RunnerError("Challenger sweep directories must be unique")

    selection = load_json(selection_path)
    selection_entries = selection.get("comparisons")
    if not isinstance(selection_entries, list) or not selection_entries:
        raise RunnerError("Canonical selection must contain comparisons")
    sweep_sources: list[dict[str, Any]] = []
    seen_sweep_ids: set[str] = set()
    suite_identities: set[tuple[str, str, str]] = set()
    for sweep_dir in resolved_sweep_dirs:
        sweep_path = sweep_dir / "sweep.json"
        sweep = load_json(sweep_path)
        if sweep.get("status") != "complete":
            raise RunnerError(f"Challenger sweep must be complete: {sweep_dir}")
        sweep_id = _require_string(sweep, "sweep_id", str(sweep_path))
        if sweep_id in seen_sweep_ids:
            raise RunnerError(f"Duplicate challenger sweep_id: {sweep_id}")
        seen_sweep_ids.add(sweep_id)
        suite_record = sweep.get("suite", {})
        suite_identity = (
            _require_string(suite_record, "suite_id", sweep_id),
            _require_string(suite_record, "suite_version", sweep_id),
            _require_string(suite_record, "manifest_sha256", sweep_id),
        )
        suite_identities.add(suite_identity)
        deployment = sweep.get("deployment", {})
        _require_string(deployment, "model", f"{sweep_id} deployment")
        _require_string(deployment, "digest", f"{sweep_id} deployment")
        sweep_sources.append(
            {
                "directory": sweep_dir,
                "path": sweep_path,
                "record": sweep,
                "suite_identity": suite_identity,
                "deployment": deployment,
                "cases": {
                    case.get("case_id"): case
                    for case in sweep.get("cases", [])
                    if isinstance(case, dict) and case.get("status") == "complete"
                },
            }
        )
    if len(suite_identities) != 1:
        raise RunnerError("Challenger sweeps must use the same suite manifest")

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    batch_id = f"challenger-evaluation-{timestamp}-{secrets.token_hex(4)}"
    batch_dir = output_dir / batch_id
    batch_dir.mkdir(parents=True, exist_ok=False)
    bundles_dir = batch_dir / "judge-bundles"
    bundles_dir.mkdir()

    record: dict[str, Any] = {
        "schema_version": "1.1.0",
        "batch_id": batch_id,
        "status": "assembling",
        "created_at": utc_now(),
        "selection": {
            "path": str(selection_path.relative_to(repo_root)),
            "sha256": sha256_file(selection_path),
        },
        "sweeps": [
            {
                "sweep_id": source["record"]["sweep_id"],
                "path": str(source["path"].relative_to(repo_root)),
                "sha256": sha256_file(source["path"]),
            }
            for source in sweep_sources
        ],
        "challenger_count": len(sweep_sources),
        "case_count": 0,
        "candidate_count_per_case": None,
        "minimum_candidate_count": None,
        "maximum_candidate_count": None,
        "cases": [],
        "judge_bundles": "judge-bundles/",
        "artifacts": {"private_map": "private-map.json"},
    }
    write_json(batch_dir / "batch.json", record)
    private_map: dict[str, Any] = {
        "schema_version": "1.1.0",
        "batch_id": batch_id,
        "candidate_mapping_by_case": {},
    }
    system_random = random.SystemRandom()

    for selection_entry in selection_entries:
        comparison_id = _require_string(
            selection_entry, "comparison_id", "canonical selection entry"
        )
        comparison_dir = comparisons_dir / comparison_id
        comparison = load_json(comparison_dir / "comparison.json")
        if comparison.get("status") != "complete":
            raise RunnerError(f"Canonical comparison is not complete: {comparison_id}")
        case_id = _require_string(comparison.get("case", {}), "case_id", comparison_id)
        sweep_cases: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for source in sweep_sources:
            sweep_case = source["cases"].get(case_id)
            if sweep_case is None:
                raise RunnerError(
                    f"Challenger sweep {source['record']['sweep_id']} has no "
                    f"complete case for {case_id}"
                )
            sweep_cases.append((source, sweep_case))

        case_paths = {
            _require_string(sweep_case, "case_path", case_id)
            for _, sweep_case in sweep_cases
        }
        if len(case_paths) != 1:
            raise RunnerError(f"Challenger case paths differ for {case_id}")
        case_path = Path(case_paths.pop())
        loaded_case = load_case(repo_root, case_path)
        candidates: list[dict[str, Any]] = []
        candidate_map: dict[str, Any] = {}
        for model_record in comparison.get("models", []):
            model = _require_string(model_record, "model", comparison_id)
            warm = model_record.get("warm")
            if not isinstance(warm, dict):
                raise RunnerError(f"Canonical model has no warm record: {comparison_id}")
            run_id = _require_string(warm, "run_id", f"{comparison_id} warm")
            source = _load_run_candidate(
                results_dir=results_dir,
                run_id=run_id,
                expected_case_id=case_id,
            )
            _validate_candidate_case(
                source, loaded_case, f"Canonical run {run_id}"
            )
            candidate_id = f"candidate-{secrets.token_hex(6)}"
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "response_text": source["response_text"],
                    "checks": source["checks"],
                }
            )
            candidate_map[candidate_id] = {
                "role": "canonical_incumbent",
                "model": model,
                "run_id": run_id,
                "response_sha256": source["response_sha256"],
                "checks_sha256": source["checks_sha256"],
            }

        baseline_evidence_by_sweep: list[dict[str, str]] = []
        challenger_deployments: set[tuple[str, str | None]] = set()
        for source, sweep_case in sweep_cases:
            challenger_warm = sweep_case.get("warm")
            if not isinstance(challenger_warm, dict):
                raise RunnerError(
                    f"Challenger sweep case has no warm record: {case_id}"
                )
            challenger_run_id = _require_string(
                challenger_warm, "run_id", f"{case_id} challenger warm"
            )
            challenger = _load_run_candidate(
                results_dir=results_dir,
                run_id=challenger_run_id,
                expected_case_id=case_id,
            )
            _validate_candidate_case(
                challenger, loaded_case, f"Challenger run {challenger_run_id}"
            )
            challenger_model_record = challenger["run"].get("deployment", {}).get(
                "model", {}
            )
            challenger_model = _require_string(
                challenger_model_record,
                "requested_name",
                f"{case_id} challenger deployment",
            )
            challenger_digest = _require_string(
                challenger_model_record,
                "digest",
                f"{case_id} challenger deployment",
            )
            if challenger_model != source["deployment"]["model"]:
                raise RunnerError(
                    f"Challenger model differs from sweep deployment for {case_id}"
                )
            if challenger_digest != source["deployment"]["digest"]:
                raise RunnerError(
                    f"Challenger digest differs from sweep deployment for {case_id}"
                )
            deployment_key = (challenger_model, challenger_digest)
            if deployment_key in challenger_deployments:
                raise RunnerError(
                    f"Duplicate challenger deployment for {case_id}: {challenger_model}"
                )
            challenger_deployments.add(deployment_key)
            baseline_evidence_by_sweep.append(
                {
                    "sweep_id": source["record"]["sweep_id"],
                    "evidence": challenger_baseline_evidence(
                        sweep_case,
                        allow_late_baseline=config.allow_late_baseline,
                        challenger_completed_at=challenger["run"].get("completed_at"),
                        comparison_completed_at=comparison.get("completed_at"),
                    ),
                }
            )
            challenger_candidate_id = f"candidate-{secrets.token_hex(6)}"
            candidates.append(
                {
                    "candidate_id": challenger_candidate_id,
                    "response_text": challenger["response_text"],
                    "checks": challenger["checks"],
                }
            )
            candidate_map[challenger_candidate_id] = {
                "role": "late_challenger",
                "sweep_id": source["record"]["sweep_id"],
                "model": challenger_model,
                "digest": challenger_digest,
                "run_id": challenger_run_id,
                "response_sha256": challenger["response_sha256"],
                "checks_sha256": challenger["checks_sha256"],
            }
        expected_candidate_count = len(comparison.get("models", [])) + len(
            sweep_sources
        )
        if len(candidates) != expected_candidate_count:
            raise RunnerError(
                f"Expected {expected_candidate_count} candidates for {case_id}; "
                f"received {len(candidates)}"
            )
        system_random.shuffle(candidates)

        slug = case_id.split(".dev.", 1)[-1]
        bundle_dir = bundles_dir / slug
        create_batch_judge_bundle(
            repo_root=repo_root,
            bundle_dir=bundle_dir,
            bundle_id=f"judge-bundle-{batch_id}-{slug}",
            loaded_case=loaded_case,
            candidates=candidates,
        )
        record["cases"].append(
            {
                "position": len(record["cases"]) + 1,
                "case_id": case_id,
                "case_path": str(case_path),
                "canonical_comparison_id": comparison_id,
                "baseline_evidence_by_challenger_sweep": baseline_evidence_by_sweep,
                "bundle_path": str(bundle_dir.relative_to(batch_dir)),
                "bundle_manifest_sha256": sha256_file(bundle_dir / "manifest.json"),
                "candidate_count": len(candidates),
            }
        )
        private_map["candidate_mapping_by_case"][case_id] = candidate_map
        record["case_count"] = len(record["cases"])
        count_summary = summarize_candidate_counts(
            [item["candidate_count"] for item in record["cases"]]
        )
        record.update(count_summary)
        write_json(batch_dir / "batch.json", record)

    write_json(batch_dir / "private-map.json", private_map)
    record["status"] = "ready_for_blinded_judgment"
    record["completed_at"] = utc_now()
    write_json(batch_dir / "batch.json", record)
    return challenger_completion_result(record, batch_dir)
