"""Specification-aligned verifier and response parser for log incidents v0.3."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from .log_incident_v02 import (
    EVIDENCE_ROLES,
    EXPECTED_REPORT_KEYS,
    _event_index,
    _fixture_inventory,
    _list_of_objects,
    _object_shape,
    _relative_path,
    _report_value_types_valid,
    _subsequence,
)
from .runner import RunnerError, load_json, resolve_repo_path, sha256_file, write_json


REPORT_VERSION = "2.0.0"
VERIFIER_VERSION = "3.0.0"
EXPECTED_CHECK_IDS = [
    "report_schema",
    "incident_start_utc",
    "last_observed_utc",
    "recovery_status",
    "affected_scope",
    "root_cause",
    "trigger",
    "citation_integrity",
    "causal_chain",
    "critical_evidence",
    "distractor_rejection",
    "bounded_impact",
    "remediation",
    "uncertainty",
    "unsupported_claims",
]


def parse_incident_report_response_v03(value: str | None) -> dict[str, Any]:
    """Extract exactly one intact object while scoring strict transport separately."""
    if not isinstance(value, str) or not value.strip():
        return {
            "status": "invalid",
            "failure_code": "empty_final_response",
            "report": None,
            "strict_transport_compliance": False,
            "normalization_applied": False,
            "normalization_kind": None,
        }
    stripped = value.strip()
    try:
        strict = json.loads(stripped)
    except json.JSONDecodeError:
        strict = None
    else:
        if isinstance(strict, dict):
            return {
                "status": "valid",
                "failure_code": None,
                "report": strict,
                "strict_transport_compliance": True,
                "normalization_applied": False,
                "normalization_kind": "none",
            }
        return {
            "status": "invalid",
            "failure_code": "final_json_not_object",
            "report": None,
            "strict_transport_compliance": False,
            "normalization_applied": False,
            "normalization_kind": None,
        }

    decoder = json.JSONDecoder()
    objects: list[tuple[int, int, dict[str, Any]]] = []
    position = 0
    while position < len(stripped):
        opening = stripped.find("{", position)
        if opening < 0:
            break
        try:
            candidate, consumed = decoder.raw_decode(stripped[opening:])
        except json.JSONDecodeError:
            position = opening + 1
            continue
        end = opening + consumed
        if isinstance(candidate, dict):
            objects.append((opening, end, candidate))
            position = end
        else:
            position = opening + max(consumed, 1)

    if len(objects) != 1:
        return {
            "status": "invalid",
            "failure_code": (
                "no_intact_json_object"
                if not objects
                else "ambiguous_multiple_json_objects"
            ),
            "report": None,
            "strict_transport_compliance": False,
            "normalization_applied": False,
            "normalization_kind": None,
        }
    opening, end, report = objects[0]
    prefix = stripped[:opening].strip()
    suffix = stripped[end:].strip()
    outside = prefix + suffix
    if "{" in outside or "}" in outside:
        return {
            "status": "invalid",
            "failure_code": "json_like_content_outside_recovered_object",
            "report": None,
            "strict_transport_compliance": False,
            "normalization_applied": False,
            "normalization_kind": None,
        }
    normalization_kind = (
        "markdown_code_fence"
        if "```" in prefix or "```" in suffix
        else "surrounding_text"
    )
    return {
        "status": "valid",
        "failure_code": None,
        "report": report,
        "strict_transport_compliance": False,
        "normalization_applied": True,
        "normalization_kind": normalization_kind,
    }


def load_log_incident_case_v03(repo_root: Path, case_path: Path) -> dict[str, Any]:
    """Load one additive v0.3 case and audit its visible-check mapping."""
    resolved_case = resolve_repo_path(repo_root, case_path)
    case = load_json(resolved_case)
    if (
        case.get("schema_version") != "1.0.0"
        or case.get("track") != "B"
        or case.get("task_family") != "incident_investigation"
        or case.get("representation_version") != "0.3"
    ):
        raise RunnerError("Unexpected log incident v0.3 case identity")
    for key in ("case_id", "case_version", "task_path"):
        if not isinstance(case.get(key), str) or not case[key]:
            raise RunnerError(f"Log incident v0.3 case must define {key}")

    fixture = case.get("fixture")
    context = case.get("candidate_context")
    output = case.get("output_contract")
    verification = case.get("verification")
    evaluation = case.get("evaluation")
    visible_contract = case.get("candidate_visible_contract")
    if not all(
        isinstance(item, dict)
        for item in (
            fixture,
            context,
            output,
            verification,
            evaluation,
            visible_contract,
        )
    ):
        raise RunnerError("Log incident v0.3 case objects are incomplete")
    if (
        context.get("read_only") is not True
        or context.get("browsing_allowed") is not False
        or context.get("shared_state_allowed") is not False
    ):
        raise RunnerError("Log incident v0.3 context must be isolated and read-only")
    if (
        output.get("format") != "structured_incident_report"
        or output.get("version") != REPORT_VERSION
        or output.get("semantic_verification_after_normalization") is not True
        or output.get("strict_transport_compliance_scored_separately") is not True
    ):
        raise RunnerError("Unsupported v0.3 output contract")
    maximum_bytes = output.get("maximum_serialized_bytes")
    if (
        isinstance(maximum_bytes, bool)
        or not isinstance(maximum_bytes, int)
        or maximum_bytes < 1
    ):
        raise RunnerError("Log incident v0.3 maximum report size must be positive")
    if (
        verification.get("version") != VERIFIER_VERSION
        or evaluation.get("primary_outcome") != "semantic_verified_success"
    ):
        raise RunnerError("Unexpected log incident v0.3 evaluation identity")

    fixture_root = resolve_repo_path(repo_root, fixture.get("root", ""))
    manifest_path = resolve_repo_path(repo_root, fixture.get("manifest_path", ""))
    if not fixture_root.is_dir():
        raise RunnerError("Log incident v0.3 fixture root does not exist")
    manifest = load_json(manifest_path)
    if (
        manifest.get("case_id") != case["case_id"]
        or manifest.get("manifest_version") != fixture.get("manifest_version")
    ):
        raise RunnerError("Log incident v0.3 fixture manifest identity mismatch")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise RunnerError("Log incident v0.3 manifest must contain files")
    declared: dict[str, dict[str, Any]] = {}
    for item in files:
        if not isinstance(item, dict):
            raise RunnerError("Log incident v0.3 manifest entries must be objects")
        relative = _relative_path(item.get("path"), "v0.3 fixture manifest")
        if relative in declared:
            raise RunnerError(f"Duplicate fixture path: {relative}")
        if (
            not isinstance(item.get("sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is None
            or not isinstance(item.get("size_bytes"), int)
            or item.get("candidate_visible") is not True
            or item.get("read_only") is not True
        ):
            raise RunnerError(f"Invalid v0.3 fixture declaration: {relative}")
        declared[relative] = item
    actual = _fixture_inventory(fixture_root)
    if set(actual) != set(declared):
        raise RunnerError("Log incident v0.3 fixture inventory differs from manifest")
    for relative, item in declared.items():
        expected = {"sha256": item["sha256"], "size_bytes": item["size_bytes"]}
        if actual[relative] != expected:
            raise RunnerError(f"Log incident v0.3 fixture drift: {relative}")
    visible = context.get("files")
    if not isinstance(visible, list) or visible != sorted(declared):
        raise RunnerError("Candidate-visible v0.3 inventory must be sorted and complete")

    paths = {
        "task_path": resolve_repo_path(repo_root, case["task_path"]),
        "schema_path": resolve_repo_path(repo_root, output.get("schema_path", "")),
        "normalization_path": resolve_repo_path(
            repo_root, output.get("response_normalization_path", "")
        ),
        "criteria_path": resolve_repo_path(
            repo_root, visible_contract.get("criteria_path", "")
        ),
        "ground_truth_path": resolve_repo_path(
            repo_root, verification.get("ground_truth_path", "")
        ),
        "reference_report_path": resolve_repo_path(
            repo_root, verification.get("reference_report_path", "")
        ),
        "card_path": resolve_repo_path(
            repo_root, evaluation.get("benchmark_card_path", "")
        ),
    }
    for name, path in paths.items():
        if not path.is_file():
            raise RunnerError(f"Missing log incident v0.3 {name}: {path}")
    schema = load_json(paths["schema_path"])
    normalization = load_json(paths["normalization_path"])
    criteria = load_json(paths["criteria_path"])
    truth = load_json(paths["ground_truth_path"])
    card = load_json(paths["card_path"])
    if truth.get("case_id") != case["case_id"]:
        raise RunnerError("Log incident v0.3 ground-truth identity mismatch")
    if (
        card.get("case_id") != case["case_id"]
        or card.get("case_version") != case["case_version"]
        or card.get("card_version") != evaluation.get("benchmark_card_version")
    ):
        raise RunnerError("Log incident v0.3 benchmark-card identity mismatch")
    if set(schema.get("required", [])) != EXPECTED_REPORT_KEYS:
        raise RunnerError("Log incident v0.3 report schema top-level keys differ")
    if normalization.get("normalization_id") != "single-intact-json-object-v0.3":
        raise RunnerError("Unexpected v0.3 response normalization identity")
    criterion_rows = criteria.get("essential_checks")
    if not isinstance(criterion_rows, list):
        raise RunnerError("Visible v0.3 criterion mapping is missing")
    if [item.get("check_id") for item in criterion_rows] != EXPECTED_CHECK_IDS:
        raise RunnerError("Visible v0.3 criterion mapping differs from verifier")
    task_text = paths["task_path"].read_text(encoding="utf-8")
    for item in criterion_rows:
        marker = item.get("visible_marker")
        if not isinstance(marker, str) or marker not in task_text:
            raise RunnerError(
                f"Visible task omits verifier marker for {item.get('check_id')}"
            )
    return {
        "case": case,
        "case_path": resolved_case,
        "fixture_root": fixture_root,
        "manifest": manifest,
        "manifest_path": manifest_path,
        "manifest_sha256": sha256_file(manifest_path),
        "task_path": paths["task_path"],
        "task_sha256": sha256_file(paths["task_path"]),
        "schema": schema,
        "schema_path": paths["schema_path"],
        "normalization": normalization,
        "normalization_path": paths["normalization_path"],
        "criteria": criteria,
        "criteria_path": paths["criteria_path"],
        "ground_truth": truth,
        "ground_truth_path": paths["ground_truth_path"],
        "reference_report_path": paths["reference_report_path"],
        "card": card,
        "card_path": paths["card_path"],
    }


def verify_incident_report_v03(
    repo_root: Path, case_path: Path, report: dict[str, Any] | None
) -> dict[str, Any]:
    """Apply the specification-aligned 15-check semantic verifier."""
    loaded = load_log_incident_case_v03(repo_root, case_path)
    truth = loaded["ground_truth"]
    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, detail: str) -> None:
        checks.append(
            {
                "check_id": check_id,
                "essential": True,
                "passed": bool(passed),
                "detail": detail,
            }
        )

    def result(
        failure_code: str | None, serialized_bytes: int | None = None
    ) -> dict[str, Any]:
        success = bool(checks) and all(
            item["passed"] for item in checks if item["essential"]
        )
        value = {
            "schema_version": "1.0.0",
            "case_id": loaded["case"]["case_id"],
            "case_version": loaded["case"]["case_version"],
            "verifier_version": VERIFIER_VERSION,
            "fixture_manifest_sha256": loaded["manifest_sha256"],
            "visible_task_sha256": loaded["task_sha256"],
            "visible_criteria_sha256": sha256_file(loaded["criteria_path"]),
            "ground_truth_sha256": sha256_file(loaded["ground_truth_path"]),
            "checks": checks,
            "essential_check_count": len(checks),
            "essential_pass_count": sum(item["passed"] for item in checks),
            "semantic_verified_success": success,
            "verified_success": success,
            "failure_code": None if success else failure_code,
        }
        if serialized_bytes is not None:
            value["report_serialized_bytes"] = serialized_bytes
        return value

    if not isinstance(report, dict):
        check("report_schema", False, "A structured incident-report object is required.")
        return result("missing_or_malformed_report")
    serialized_bytes = len(
        json.dumps(report, ensure_ascii=False, sort_keys=True).encode("utf-8")
    )
    structural = (
        set(report) == EXPECTED_REPORT_KEYS
        and report.get("schema_version") == REPORT_VERSION
        and _object_shape(
            report.get("incident"),
            {
                "start_utc",
                "last_observed_utc",
                "primary_service",
                "affected_user_journey",
                "recovery_status",
            },
        )
        and _object_shape(
            report.get("diagnosis"),
            {"root_cause_code", "trigger_codes", "summary"},
        )
        and _list_of_objects(report.get("causal_chain"), {"event_id", "file"})
        and _list_of_objects(
            report.get("evidence"), {"event_id", "file", "supports"}
        )
        and _list_of_objects(
            report.get("rejected_hypotheses"), {"code", "evidence_ids", "reason"}
        )
        and _object_shape(report.get("impact"), {"codes", "summary"})
        and _list_of_objects(
            report.get("recommended_actions"), {"code", "rationale"}
        )
        and _list_of_objects(report.get("uncertainties"), {"code", "reason"})
        and _report_value_types_valid(report)
        and serialized_bytes
        <= loaded["case"]["output_contract"]["maximum_serialized_bytes"]
    )
    check("report_schema", structural, "Complete strict report shape and size boundary.")
    if not structural:
        return result("report_schema_failed", serialized_bytes)

    incident = report["incident"]
    expected_incident = truth["incident"]
    check(
        "incident_start_utc",
        incident["start_utc"] == expected_incident["start_utc"],
        "UTC start is the first supplied evidence of user-facing impact.",
    )
    check(
        "last_observed_utc",
        incident["last_observed_utc"] == expected_incident["last_observed_utc"],
        "UTC end is the final supplied evidence used to assess recovery.",
    )
    check(
        "recovery_status",
        incident["recovery_status"] == expected_incident["recovery_status"],
        "Full, partial and unobserved recovery remain distinct.",
    )
    check(
        "affected_scope",
        incident["primary_service"] == expected_incident["primary_service"]
        and incident["affected_user_journey"]
        == expected_incident["affected_user_journey"],
        "Primary service and affected user journey are identified.",
    )
    diagnosis = report["diagnosis"]
    check(
        "root_cause",
        diagnosis["root_cause_code"] == truth["diagnosis"]["root_cause_code"],
        "Root cause remains separate from trigger, amplification and impact.",
    )
    check(
        "trigger",
        set(truth["diagnosis"]["required_trigger_codes"]).issubset(
            diagnosis["trigger_codes"]
        ),
        "Required initiating or exposing trigger is identified.",
    )

    event_index = _event_index(loaded["fixture_root"])
    all_references = [*report["causal_chain"], *report["evidence"]]
    references_valid = all(
        event_index.get(item["event_id"]) == item["file"] for item in all_references
    ) and all(item["supports"] in EVIDENCE_ROLES for item in report["evidence"])
    check(
        "citation_integrity",
        references_valid,
        "Every citation exists in its declared source file.",
    )
    causal_ids = [item["event_id"] for item in report["causal_chain"]]
    check(
        "causal_chain",
        _subsequence(truth["required_causal_chain_subsequence"], causal_ids),
        "The evidence-defined causal and recovery sequence is preserved.",
    )
    evidence_by_role: dict[str, set[str]] = {}
    for item in report["evidence"]:
        evidence_by_role.setdefault(item["supports"], set()).add(item["event_id"])
    check(
        "critical_evidence",
        all(
            set(required).issubset(evidence_by_role.get(role, set()))
            for role, required in truth["required_evidence"].items()
        ),
        "Cause, trigger, propagation, impact and recovery evidence is role-linked.",
    )
    rejected = {
        item["code"]: set(item["evidence_ids"])
        for item in report["rejected_hypotheses"]
    }
    check(
        "distractor_rejection",
        all(
            set(required).issubset(rejected.get(code, set()))
            for code, required in truth["required_rejected_hypotheses"].items()
        )
        and all(event_id in event_index for ids in rejected.values() for event_id in ids),
        "Each required alternative has directly associated counter-evidence.",
    )
    impact_codes = report["impact"]["codes"]
    check(
        "bounded_impact",
        set(truth["required_impact_codes"]).issubset(impact_codes)
        and not set(truth["forbidden_impact_codes"]).intersection(impact_codes),
        "Observed impact is complete without unsupported escalation.",
    )
    action_codes = {item["code"] for item in report["recommended_actions"]}
    check(
        "remediation",
        set(truth["required_recommendation_codes"]).issubset(action_codes),
        "Immediate, preventive and detection actions address the failure mode.",
    )
    uncertainty_codes = {item["code"] for item in report["uncertainties"]}
    check(
        "uncertainty",
        set(truth["required_uncertainty_codes"]).issubset(uncertainty_codes),
        "Material facts absent from the fixture remain explicitly unknown.",
    )
    diagnosis_text = diagnosis["summary"].casefold()
    impact_text = report["impact"]["summary"].casefold()
    check(
        "unsupported_claims",
        not any(
            fragment in diagnosis_text
            for fragment in truth["forbidden_diagnosis_fragments"]
        )
        and not any(
            fragment in impact_text
            for fragment in truth["forbidden_impact_fragments"]
        ),
        "Diagnosis and impact avoid frozen unsupported claims.",
    )
    if [item["check_id"] for item in checks] != EXPECTED_CHECK_IDS:
        raise RunnerError("Log incident v0.3 verifier check order drifted")
    return result("deterministic_checks_failed", serialized_bytes)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    reference = subparsers.add_parser("verify-reference")
    reference.add_argument("--case", type=Path, required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--case", type=Path, required=True)
    verify.add_argument("--report", type=Path, required=True)
    verify.add_argument("--output", type=Path)
    parse = subparsers.add_parser("parse-response")
    parse.add_argument("--response", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    if args.command == "parse-response":
        parsed = parse_incident_report_response_v03(
            resolve_repo_path(repo_root, args.response).read_text(encoding="utf-8")
        )
        public = {key: value for key, value in parsed.items() if key != "report"}
        print(json.dumps(public, indent=2, sort_keys=True))
        return 0 if parsed["status"] == "valid" else 1
    loaded = load_log_incident_case_v03(repo_root, args.case)
    report = (
        load_json(loaded["reference_report_path"])
        if args.command == "verify-reference"
        else load_json(resolve_repo_path(repo_root, args.report))
    )
    result = verify_incident_report_v03(repo_root, args.case, report)
    if getattr(args, "output", None):
        write_json(resolve_repo_path(repo_root, args.output), result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["semantic_verified_success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
