"""Offline contract and verifier for multi-format document analysis v0.1."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .json_schema import JsonSchemaError, validate_json
from .runner import RunnerError, load_json, resolve_repo_path


CASE_VERSION = "1.0.0"
REPORT_VERSION = "1.0.0"
VERIFIER_VERSION = "1.0.0"
EXPECTED_CHECK_IDS = [
    "report_schema",
    "decision",
    "approved_regions",
    "region_blockers",
    "citation_integrity",
    "required_evidence",
    "cross_format_coverage",
    "conflict_resolution",
    "action_plan",
    "uncertainty",
    "controlled_value_integrity",
]


def _string_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and all(isinstance(item, str) and item for item in value)
        and len(value) == len(set(value))
    )


def _controlled_values_valid(value: Any) -> bool:
    expected = {
        "decision_codes",
        "region_codes",
        "blocker_codes",
        "conflict_codes",
        "action_codes",
        "uncertainty_codes",
    }
    return (
        isinstance(value, dict)
        and set(value) == expected
        and all(_string_list(items) and items for items in value.values())
    )


def load_multi_format_case(repo_root: Path, case_path: Path) -> dict[str, Any]:
    """Load and validate the design-stage case without requiring binary fixtures."""
    resolved_case = resolve_repo_path(repo_root, case_path)
    case = load_json(resolved_case)
    if (
        case.get("schema_version") != "1.0.0"
        or case.get("case_version") != CASE_VERSION
        or case.get("track") != "A+B"
        or case.get("task_family") != "document_decision_reconciliation"
    ):
        raise RunnerError("Unexpected multi-format case identity")
    if case.get("status") != "design_complete_artifacts_pending":
        raise RunnerError("Multi-format v0.1 must remain in its design-stage state")
    if (
        case.get("live_execution_authorized") is not False
        or case.get("artifact_generation_complete") is not False
        or case.get("canonical_extraction_complete") is not False
    ):
        raise RunnerError("Multi-format design stage cannot authorize execution")

    task_path = resolve_repo_path(repo_root, case.get("task_path", ""))
    schema_path = resolve_repo_path(
        repo_root, case.get("output_contract", {}).get("schema_path", "")
    )
    blueprint_path = resolve_repo_path(
        repo_root, case.get("source_blueprint_path", "")
    )
    evaluation = case.get("evaluation")
    contract_path = resolve_repo_path(
        repo_root,
        evaluation.get("contract_path", "") if isinstance(evaluation, dict) else "",
    )
    truth_path = resolve_repo_path(
        repo_root, case.get("verification", {}).get("ground_truth_path", "")
    )
    reference_path = resolve_repo_path(
        repo_root, case.get("verification", {}).get("reference_report_path", "")
    )
    for label, path in (
        ("task", task_path),
        ("schema", schema_path),
        ("source blueprint", blueprint_path),
        ("evaluation contract", contract_path),
        ("ground truth", truth_path),
        ("reference report", reference_path),
    ):
        if not path.is_file():
            raise RunnerError(f"Multi-format {label} does not exist")

    blueprint = load_json(blueprint_path)
    artifacts = blueprint.get("artifacts")
    facts = blueprint.get("facts")
    planned_files = case.get("candidate_context", {}).get("planned_files")
    if (
        blueprint.get("case_id") != case.get("case_id")
        or not isinstance(artifacts, list)
        or {item.get("format") for item in artifacts if isinstance(item, dict)}
        != {"docx", "pdf", "xlsx"}
        or not isinstance(facts, list)
        or not facts
        or not _string_list(planned_files)
        or set(planned_files)
        != {
            item.get("filename")
            for item in artifacts
            if isinstance(item, dict)
        }
    ):
        raise RunnerError("Multi-format source blueprint is incomplete")
    fact_codes: set[str] = set()
    source_refs: set[str] = set()
    for fact in facts:
        if not isinstance(fact, dict):
            raise RunnerError("Multi-format facts must be objects")
        fact_code = fact.get("fact_code")
        source_ref = fact.get("source_ref")
        artifact = fact.get("artifact")
        if (
            not isinstance(fact_code, str)
            or not fact_code
            or not isinstance(source_ref, str)
            or not source_ref
            or artifact not in {"docx", "pdf", "xlsx"}
        ):
            raise RunnerError("Multi-format fact identity is invalid")
        if fact_code in fact_codes or source_ref in source_refs:
            raise RunnerError("Multi-format facts must have unique codes and references")
        fact_codes.add(fact_code)
        source_refs.add(source_ref)

    truth = load_json(truth_path)
    if (
        truth.get("case_id") != case.get("case_id")
        or truth.get("verifier_version") != VERIFIER_VERSION
        or not _controlled_values_valid(truth.get("visible_controlled_values"))
    ):
        raise RunnerError("Multi-format ground truth is incomplete")
    required_facts = truth.get("required_fact_codes")
    if not _string_list(required_facts) or not set(required_facts) <= fact_codes:
        raise RunnerError("Required multi-format facts are not present in the blueprint")

    output_contract = case.get("output_contract")
    if (
        not isinstance(output_contract, dict)
        or output_contract.get("format") != "structured_decision_report"
        or output_contract.get("version") != REPORT_VERSION
        or output_contract.get("strict_json_transport_scored_separately") is not True
        or not isinstance(evaluation, dict)
        or evaluation.get("primary_outcome") != "semantic_verified_success"
        or evaluation.get("supplemental_free_text_review_required") is not True
    ):
        raise RunnerError("Unexpected multi-format evaluation contract")

    contract = load_json(contract_path)
    essential_checks = contract.get("essential_checks")
    if (
        contract.get("schema_version") != "1.0.0"
        or contract.get("contract_version") != "0.1"
        or contract.get("task_family") != case.get("task_family")
        or contract.get("primary_outcome") != evaluation.get("primary_outcome")
        or contract.get("strict_transport_scored_separately") is not True
        or contract.get("supplemental_free_text_review_required") is not True
        or not isinstance(essential_checks, list)
        or [item.get("check_id") for item in essential_checks if isinstance(item, dict)]
        != EXPECTED_CHECK_IDS
    ):
        raise RunnerError("Multi-format evaluation contract is incomplete")
    task_text = task_path.read_text(encoding="utf-8")
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("visible_marker"), str)
        or item["visible_marker"] not in task_text
        for item in essential_checks
    ):
        raise RunnerError("Multi-format task does not expose every evaluation marker")

    return {
        "case": case,
        "case_path": resolved_case,
        "task_path": task_path,
        "schema_path": schema_path,
        "schema": load_json(schema_path),
        "blueprint_path": blueprint_path,
        "blueprint": blueprint,
        "contract_path": contract_path,
        "contract": contract,
        "truth_path": truth_path,
        "truth": truth,
        "reference_report_path": reference_path,
    }


def _check(check_id: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"check_id": check_id, "passed": bool(passed), "detail": detail}


def _pairs(items: Any, left: str, right: str) -> set[tuple[str, str]]:
    if not isinstance(items, list):
        return set()
    return {
        (item.get(left), item.get(right))
        for item in items
        if isinstance(item, dict)
        and isinstance(item.get(left), str)
        and isinstance(item.get(right), str)
    }


def verify_multi_format_report(
    repo_root: Path, case_path: Path, report: Any
) -> dict[str, Any]:
    """Apply deterministic semantic checks while keeping prose review separate."""
    loaded = load_multi_format_case(repo_root, case_path)
    truth = loaded["truth"]
    controlled = truth["visible_controlled_values"]
    checks: list[dict[str, Any]] = []

    try:
        validate_json(report, loaded["schema"])
    except JsonSchemaError as error:
        checks.append(_check("report_schema", False, str(error)))
        for check_id in EXPECTED_CHECK_IDS[1:]:
            checks.append(_check(check_id, False, "Report schema is invalid"))
        return {
            "verifier_version": VERIFIER_VERSION,
            "checks": checks,
            "essential_pass_count": 0,
            "essential_check_count": len(checks),
            "semantic_verified_success": False,
            "supplemental_free_text_review_required": True,
        }

    checks.append(
        _check("report_schema", True, "Report matches the strict JSON schema")
    )

    decision = report["decision"]
    checks.append(
        _check(
            "decision",
            decision["code"] == truth["decision_code"],
            "Decision code must match the cross-source policy outcome",
        )
    )
    checks.append(
        _check(
            "approved_regions",
            set(decision["approved_regions"]) == set(truth["approved_regions"]),
            "Approved regions must match the region-level gate result",
        )
    )
    blocker_pairs = _pairs(decision["blocked_regions"], "region", "blocker_code")
    expected_blockers = {
        (item["region"], item["blocker_code"])
        for item in truth["blocked_regions"]
    }
    checks.append(
        _check(
            "region_blockers",
            blocker_pairs == expected_blockers
            and len(blocker_pairs) == len(decision["blocked_regions"]),
            "Each blocked region must carry its decisive failed gate",
        )
    )

    fact_index = {
        item["fact_code"]: item for item in loaded["blueprint"]["facts"]
    }
    evidence_pairs = _pairs(report["evidence"], "fact_code", "source_ref")
    checks.append(
        _check(
            "citation_integrity",
            all(
                code in fact_index and fact_index[code]["source_ref"] == source_ref
                for code, source_ref in evidence_pairs
            )
            and len(evidence_pairs) == len(report["evidence"]),
            "Every fact code must point to its exact artifact anchor",
        )
    )
    cited_codes = {code for code, _ in evidence_pairs}
    checks.append(
        _check(
            "required_evidence",
            set(truth["required_fact_codes"]) <= cited_codes,
            "All facts needed for the decision and conflict must be cited",
        )
    )
    cited_formats = {
        fact_index[code]["artifact"] for code in cited_codes if code in fact_index
    }
    checks.append(
        _check(
            "cross_format_coverage",
            cited_formats == {"docx", "pdf", "xlsx"},
            "The report must use evidence from all three artifact formats",
        )
    )

    conflict_pairs = {
        (item["code"], tuple(sorted(item["source_refs"])))
        for item in report["conflicts"]
    }
    expected_conflicts = {
        (item["code"], tuple(sorted(item["source_refs"])))
        for item in truth["required_conflicts"]
    }
    checks.append(
        _check(
            "conflict_resolution",
            conflict_pairs == expected_conflicts
            and len(conflict_pairs) == len(report["conflicts"]),
            "The misleading aggregate dashboard conflict must be resolved",
        )
    )

    action_codes = {item["code"] for item in report["recommended_actions"]}
    checks.append(
        _check(
            "action_plan",
            set(truth["required_action_codes"]) <= action_codes,
            "The minimum safe rollout and correction actions are required",
        )
    )
    uncertainty_codes = {item["code"] for item in report["uncertainties"]}
    checks.append(
        _check(
            "uncertainty",
            set(truth["required_uncertainty_codes"]) <= uncertainty_codes,
            "Missing future evidence must remain explicitly uncertain",
        )
    )

    controlled_valid = (
        decision["code"] in controlled["decision_codes"]
        and set(decision["approved_regions"]) <= set(controlled["region_codes"])
        and all(
            item["region"] in controlled["region_codes"]
            and item["blocker_code"] in controlled["blocker_codes"]
            for item in decision["blocked_regions"]
        )
        and all(
            item["code"] in controlled["conflict_codes"]
            for item in report["conflicts"]
        )
        and action_codes <= set(controlled["action_codes"])
        and uncertainty_codes <= set(controlled["uncertainty_codes"])
    )
    checks.append(
        _check(
            "controlled_value_integrity",
            controlled_valid,
            "All controlled outcome values must come from the visible codebook",
        )
    )

    passed = sum(item["passed"] for item in checks)
    return {
        "verifier_version": VERIFIER_VERSION,
        "checks": checks,
        "essential_pass_count": passed,
        "essential_check_count": len(checks),
        "semantic_verified_success": passed == len(checks),
        "supplemental_free_text_review_required": True,
    }
