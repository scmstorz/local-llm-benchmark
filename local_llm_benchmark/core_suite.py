"""One offline catalog, command planner and coverage view for the personal suite.

This module never constructs a model client or executes runner commands.
Existing qualified runners own execution, resume, resource and sandbox gates.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
from collections import Counter
from pathlib import Path
from typing import Any

from .runner import RunnerError, git_commit, load_json, sha256_file, utc_now, write_json


DEFAULT_SUITE = Path("tasks/core-suite-v0.1.json")
DEFAULT_SYSTEMS = Path("capabilities/core-systems-v0.1.json")


def _source(root: Path, value: str) -> Path:
    path = root / value
    if Path(value).is_absolute() or ".." in Path(value).parts or path.is_symlink():
        raise RunnerError(f"Unsafe suite source: {value}")
    if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise RunnerError(f"Missing suite source: {value}")
    return path


def load_catalog(root: Path, suite_path: Path = DEFAULT_SUITE,
                 systems_path: Path = DEFAULT_SYSTEMS) -> dict[str, Any]:
    suite = load_json(_source(root, str(suite_path)))
    registry = load_json(_source(root, str(systems_path)))
    if suite.get("schema_version") != "1.0.0" or registry.get("schema_version") != "1.0.0":
        raise RunnerError("Unsupported core catalog or system registry")
    cases = suite.get("cases", [])
    ids = [case["case_id"] for case in cases]
    if not ids or len(ids) != len(set(ids)):
        raise RunnerError("Core catalog has empty or duplicate cases")
    systems = registry.get("systems", {})
    for key, system in systems.items():
        if system.get("kind") not in {"direct", "mini", "pi"} or not system.get("prepare_argv"):
            raise RunnerError(f"Invalid runner declaration: {key}")
        if system.get("planning_status") != "admitted_with_fresh_execution_gates":
            raise RunnerError(f"Runner is not admitted for planning: {key}")
        if not set(system.get("additional_case_ids", [])) <= set(ids):
            raise RunnerError(f"Runner maps unknown tasks: {key}")
        for path in system.get("artifact_paths", []):
            _source(root, path)
    for case in cases:
        path = _source(root, case["case_path"])
        if load_json(path).get("case_id") != case["case_id"]:
            raise RunnerError("Core case identity differs")
        if sha256_file(path) != case.get("case_sha256"):
            raise RunnerError(f"Core case definition changed: {case['case_id']}")
        if not case.get("systems") or not set(case["systems"]) <= systems.keys():
            raise RunnerError("Core case maps an unknown runner")
        for evidence in case.get("historical_evidence", []):
            _source(root, evidence["path"])
    for profile in suite.get("profiles", {}).values():
        if not profile or len(profile) != len(set(profile)) or not set(profile) <= set(ids):
            raise RunnerError("Invalid core profile")
    return {"suite": suite, "registry": registry,
            "suite_path": str(suite_path), "systems_path": str(systems_path)}


def applicable_systems(loaded: dict[str, Any], case: dict[str, Any]) -> list[str]:
    return list(dict.fromkeys(case["systems"] + [
        key for key, value in loaded["registry"]["systems"].items()
        if case["case_id"] in value.get("additional_case_ids", [])
    ]))


def overview(root: Path, loaded: dict[str, Any]) -> dict[str, Any]:
    cases = loaded["suite"]["cases"]
    return {
        "suite_id": loaded["suite"]["suite_id"], "status": loaded["suite"]["status"],
        "task_count": len(cases), "families": dict(Counter(case["family"] for case in cases)),
        "task_system_variant_count": sum(len(applicable_systems(loaded, case)) for case in cases),
        "model_set_fixed": False, "execution_authorized": False,
        "cases": [{"case_id": case["case_id"], "family": case["family"],
                   "case_version": load_json(root / case["case_path"])["case_version"],
                   "systems": applicable_systems(loaded, case),
                   "historical_evidence": case["historical_evidence"],
                   "unsupported_conditions": case.get("unsupported_conditions", {})}
                  for case in cases],
        "history_rule": "Historical coverage is context, not a current-runtime matched baseline. Excluded smokes are not measured coverage; current_evaluation says nothing about runtime comparability.",
        "deferred_task_families": loaded["suite"]["deferred_task_families"],
    }


def first_comparison(loaded: dict[str, Any]) -> dict[str, Any]:
    selected = set(loaded["suite"]["profiles"]["first-comparison"])
    cases = [case for case in loaded["suite"]["cases"] if case["case_id"] in selected]
    return {
        "schema_version": "1.0.0", "plan_id": "core-first-comparison-v0.1",
        "status": "draft_awaiting_candidate_and_current_deployment_binding",
        "suite_path": loaded["suite_path"], "systems_path": loaded["systems_path"],
        "profile": "first-comparison", "reference_model": "qwen3.8:27b-mlx",
        "candidate_model": None, "runtime_version": None,
        "case_ids": [case["case_id"] for case in cases],
        "tasks": len(cases), "planned_deployments": 2,
        "task_system_cells_per_deployment": sum(len(applicable_systems(loaded, case)) for case in cases),
        "automatic_retries": 0, "execution_authorized": False,
        "repetitions": "One cold/warm text pair per task (warm is quality candidate); one attempt per remaining task/system cell. Repeated reliability studies are separate.",
        "selection_reason": "One task per existing family, including source integration, Bayes transfer, repository work, partial-recovery chronology and supplier document reconciliation.",
        "before_execution": [
            "Owner selects candidate; register both exact digests under the current shared Ollama version.",
            "Generate a bound plan with core_suite plan and commit its source inputs.",
            "Fresh model/system admission, Pi sandbox and resource checks; obtain the concrete live window and plan authorization.",
        ],
        "evaluation": "Use deterministic checks and strict transport separately; assess source-grounded prose; jointly judge text candidates under existing rubrics before interpreting quality differences.",
        "historical_reference_reuse": False,
    }


def _fingerprints(root: Path, loaded: dict[str, Any]) -> list[dict[str, str]]:
    paths = {loaded["suite_path"], loaded["systems_path"], loaded["suite"]["text_methodology_source"]}
    paths.update(case["case_path"] for case in loaded["suite"]["cases"])
    paths.update(str(path.relative_to(root)) for path in (root / "local_llm_benchmark").glob("*.py"))
    for system in loaded["registry"]["systems"].values():
        paths.update(system.get("artifact_paths", []))
    # Follow existing repository source references, including prompts, fixture
    # directories, contracts and lockfiles. Missing private inputs are left to
    # the existing task admission checks; no private content is embedded here.
    pending = list(paths)
    def references(value: Any):
        if isinstance(value, dict):
            for item in value.values():
                yield from references(item)
        elif isinstance(value, list):
            for item in value:
                yield from references(item)
        elif isinstance(value, str) and value.startswith(("tasks/", "capabilities/", "integrations/", "data/", "local_llm_benchmark/")):
            yield value
    while pending:
        path = root / pending.pop()
        if path.suffix != ".json":
            continue
        for reference in references(load_json(path)):
            candidate = root / reference
            if not candidate.exists():
                continue
            candidates = candidate.rglob("*") if candidate.is_dir() else [candidate]
            for source in candidates:
                if not source.is_file() or {"node_modules", "__pycache__"} & set(source.parts):
                    continue
                relative = str(source.relative_to(root))
                if relative not in paths:
                    _source(root, relative)
                    paths.add(relative)
                    pending.append(relative)
    return [{"path": path, "sha256": sha256_file(_source(root, path))} for path in sorted(paths)]


def prepare_plan(root: Path, loaded: dict[str, Any], *, catalog_path: Path,
                 deployment_ids: list[str], profile: str, output: Path) -> dict[str, Any]:
    """Bind arbitrary catalog deployments to tasks and print existing commands."""
    if profile not in loaded["suite"]["profiles"]:
        raise RunnerError("Unknown core profile")
    if not deployment_ids or len(deployment_ids) != len(set(deployment_ids)):
        raise RunnerError("Select unique deployment IDs")
    catalog = load_json(_source(root, str(catalog_path)))
    available = {entry["deployment_id"]: entry for entry in catalog["deployments"]}
    if not set(deployment_ids) <= available.keys():
        raise RunnerError("Unknown deployment ID; register current metadata first")
    deployments = [available[key] for key in deployment_ids]
    versions = {entry["runtime"]["version"] for entry in deployments}
    if len(versions) != 1 or any(entry["runtime"].get("name") != "ollama" for entry in deployments):
        raise RunnerError("A fresh comparison requires one shared Ollama version")
    if len({entry["resolved_name"] for entry in deployments}) != len(deployments):
        raise RunnerError("Choose one deployment per model tag in a comparison")
    for entry in deployments:
        if not re.fullmatch(r"[0-9a-f]{64}", entry.get("digest", "")):
            raise RunnerError("Deployment digest must be complete")
    directory = (root / output).resolve()
    if not directory.is_relative_to(root.resolve()) or directory.exists():
        raise RunnerError("Plan output must be a new directory inside the repository")
    selected_ids = loaded["suite"]["profiles"][profile]
    by_id = {case["case_id"]: case for case in loaded["suite"]["cases"]}
    cases = [by_id[key] for key in selected_ids]
    text_cases = [case for case in cases if "direct-text" in case["systems"]]
    text_manifest = load_json(root / loaded["suite"]["text_methodology_source"])
    text_manifest["suite_id"] = loaded["suite"]["suite_id"] + "-" + profile + "-text"
    text_manifest["purpose"] = "Selected unchanged text tasks inside a core-suite execution plan."
    text_manifest["cases"] = [dict(position=index, case_path=case["case_path"], num_ctx=case["num_ctx"])
                              for index, case in enumerate(text_cases, 1)]
    directory.mkdir(parents=True)
    if text_cases:
        write_json(directory / "text-suite.json", text_manifest)
    cells, blocks = [], []
    specs = [(None, "direct-text")] if text_cases else []
    specs += [(case, key) for case in cases for key in applicable_systems(loaded, case) if key != "direct-text"]
    for spec_index, (case, key) in enumerate(specs):
        system = loaded["registry"]["systems"][key]
        # Rotate deployment order between blocks; do not always run the reference first.
        order = deployments[spec_index % len(deployments):] + deployments[:spec_index % len(deployments)]
        for entry in order:
            block_id = f"block-{len(blocks) + 1:03d}"
            relative = directory.relative_to(root.resolve()) / block_id
            values = {"model": entry["resolved_name"], "case_path": case["case_path"] if case else "",
                      "text_suite": str(directory.relative_to(root.resolve()) / "text-suite.json"),
                      "results_dir": str(relative / "runs"), "sweeps_dir": str(relative / "sweeps")}
            blocks.append({"block_id": block_id, "system": key, "deployment_id": entry["deployment_id"],
                           "results_dir": values["results_dir"], "sweeps_dir": values["sweeps_dir"],
                           "prepare_runs_inference": system["prepare_runs_inference"],
                           "argv": [part.format(**values) for part in system["prepare_argv"]],
                           "actions": system["actions"]})
            for task in (text_cases if case is None else [case]):
                cells.append({"cell_id": f"cell-{len(cells) + 1:03d}", "block_id": block_id,
                              "case_id": task["case_id"], "case_path": task["case_path"],
                              "system": key, "deployment_id": entry["deployment_id"], "status": "not_run"})
    fingerprints = _fingerprints(root, loaded)
    fingerprints.append({"path": str(catalog_path), "sha256": sha256_file(root / catalog_path)})
    if text_cases:
        fingerprints.append({"path": str((directory / "text-suite.json").relative_to(root.resolve())),
                             "sha256": sha256_file(directory / "text-suite.json")})
    plan = {"schema_version": "1.0.0", "suite_id": loaded["suite"]["suite_id"], "profile": profile,
            "created_at": utc_now(), "source_commit": git_commit(root),
            "status": "prepared_execution_not_authorized", "execution_authorized": False,
            "automatic_retries": 0, "suite_path": loaded["suite_path"], "systems_path": loaded["systems_path"],
            "deployments": deployments, "ollama_version": next(iter(versions)),
            "source_fingerprints": fingerprints, "blocks": blocks, "cells": cells,
            "execution_gates": ["exact current deployment and runtime", "fresh exclusive window and resource gate",
                                "fresh task/system qualification and Pi sandbox acceptance", "separate concrete plan authorization"],
            "evaluation_policy": first_comparison(loaded)["evaluation"]}
    write_json(directory / "plan.json", plan)
    return plan


def _outcome(record: dict[str, Any]) -> dict[str, Any]:
    outcome = record.get("outcome") or {}
    verification = record.get("verification") or {}
    return {"runtime_success": outcome.get("runtime_success"),
            "verified_success": outcome.get("verified_success", verification.get("verified_success")),
            "strict_transport_compliance": outcome.get("strict_transport_compliance"),
            "essential_pass_count": verification.get("essential_pass_count"),
            "essential_check_count": verification.get("essential_check_count"),
            "quality_review": "pending_separate_source_grounded_assessment"}


def coverage(root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    """Read only this plan's isolated result directories, never old studies."""
    drift = [item["path"] for item in plan["source_fingerprints"]
             if not (root / item["path"]).is_file() or sha256_file(root / item["path"]) != item["sha256"]]
    deployments = {entry["deployment_id"]: entry for entry in plan["deployments"]}
    loaded = load_catalog(root, Path(plan["suite_path"]), Path(plan["systems_path"]))
    blocks = {block["block_id"]: block for block in plan["blocks"]}
    observed = []
    for cell in plan["cells"]:
        block = blocks[cell["block_id"]]
        directory = root / block["results_dir"]
        records = [(path, load_json(path)) for path in sorted(directory.glob("*/run.json"))]
        all_matching = [(path, record) for path, record in records if record.get("case", {}).get("case_id") == cell["case_id"]]
        matching = all_matching
        if cell["system"] == "direct-text":
            matching = [(path, record) for path, record in matching if (record.get("measurement") or {}).get("phase") == "warm"]
        row = {**cell, "status": "not_run", "outcome": None, "evidence": None}
        if len(matching) > 1:
            row["status"] = "ambiguous_multiple_attempts"
        elif matching:
            path, record = matching[0]
            expected = deployments[cell["deployment_id"]]
            deployment = record.get("deployment", {})
            model = deployment.get("model") or {}
            system = loaded["registry"]["systems"][cell["system"]]
            state = record.get("state", record.get("status"))
            created = record.get("started_at") or record.get("prepared_at") or ""
            wrong = created < plan["created_at"]
            if model or state == "complete":
                wrong |= (model.get("digest") != expected["digest"]
                          or deployment.get("ollama_version") != expected["runtime"]["version"]
                          or model.get("resolved_name") != expected["resolved_name"])
            if system.get("expected_harness_id"):
                actual_id = record.get("harness", {}).get("harness_id")
                if cell["system"] == "canonical-rollout":
                    actual_id = record.get("condition_id")
                wrong |= actual_id != system["expected_harness_id"]
            if system.get("evaluation_configuration_id"):
                wrong |= record.get("evaluation_configuration", {}).get("configuration_id") != system["evaluation_configuration_id"]
                if state == "complete":
                    wrong |= ((record.get("verification") or {}).get("verifier_version") != "2.1.0"
                              or (record.get("normalized_metrics") or {}).get("version") != "0.2.0")
            row.update(status="identity_mismatch" if wrong else "complete" if state == "complete"
                       else "prepared_not_executed" if not model else "in_progress",
                       evidence={"path": str(path.relative_to(root)), "sha256": sha256_file(path)},
                       outcome=_outcome(record))
        elif all_matching:
            row["status"] = "in_progress"
        elif cell["system"] != "direct-text" and directory.exists() and any(directory.iterdir()):
            row["status"] = "unrecorded_partial_attempt"
        if cell["system"] == "direct-text" and not matching:
            for path in (root / block["sweeps_dir"]).glob("*/sweep.json"):
                sweep = load_json(path)
                for task in sweep.get("cases", []):
                    if task["case_id"] == cell["case_id"] and task["status"] == "failed":
                        deployment = sweep.get("deployment", {})
                        expected = deployments[cell["deployment_id"]]
                        valid = (deployment.get("digest") == expected["digest"]
                                 and deployment.get("ollama_version") == expected["runtime"]["version"]
                                 and sweep.get("started_at", "") >= plan["created_at"])
                        row.update(status="execution_failed" if valid else "identity_mismatch",
                                   evidence={"path": str(path.relative_to(root)), "sha256": sha256_file(path)})
        observed.append(row)
    return {"suite_id": plan["suite_id"], "profile": plan["profile"], "source_drift": drift,
            "counts": dict(Counter(row["status"] for row in observed)), "cells": observed,
            "composite_score": None, "quality_comparison_ready": False,
            "interpretation": "Complete means recorded execution, not verified success or completed quality review. Missing, failed, ambiguous and identity-mismatched evidence remain distinct."}


def command_blocks(root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    observed = coverage(root, plan)
    if observed["source_drift"]:
        raise RunnerError("Plan sources changed; prepare a new plan before execution")
    blocks = []
    for block in plan["blocks"]:
        statuses = Counter(row["status"] for row in observed["cells"] if row["block_id"] == block["block_id"])
        untouched = set(statuses) == {"not_run"}
        blocks.append({"block_id": block["block_id"], "system": block["system"],
                       "command": shlex.join(block["argv"]) if untouched else None,
                       "start_command_available": untouched, "observed_statuses": dict(statuses),
                       "prepare_runs_inference": block["prepare_runs_inference"], "actions": block["actions"],
                       "continuation": None if untouched else "Use the existing run lifecycle or text suite-resume; retain terminal attempts. Do not restart this block."})
    return {"execution_authorized": False, "blocks": blocks}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--systems", type=Path, default=DEFAULT_SYSTEMS)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("overview")
    commands.add_parser("first-comparison")
    plan = commands.add_parser("plan")
    plan.add_argument("--catalog", type=Path, required=True)
    plan.add_argument("--deployments", nargs="+", required=True)
    plan.add_argument("--profile", default="first-comparison")
    plan.add_argument("--output", type=Path, required=True)
    for name in ("commands", "coverage"):
        commands.add_parser(name).add_argument("--plan", type=Path, required=True)
    args = parser.parse_args(argv)
    root = Path.cwd().resolve()
    try:
        if args.command in {"commands", "coverage"}:
            plan = load_json(args.plan)
            result = coverage(root, plan)
            if args.command == "commands":
                result = command_blocks(root, plan)
        else:
            loaded = load_catalog(root, args.suite, args.systems)
            result = (overview(root, loaded) if args.command == "overview" else first_comparison(loaded)
                      if args.command == "first-comparison" else prepare_plan(
                          root, loaded, catalog_path=args.catalog, deployment_ids=args.deployments,
                          profile=args.profile, output=args.output))
    except (RunnerError, KeyError, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
