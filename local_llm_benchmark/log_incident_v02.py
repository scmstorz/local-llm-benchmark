"""Data-driven verifier for the second log-incident task generation."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from .runner import RunnerError, load_json, resolve_repo_path, sha256_file, write_json


REPORT_VERSION = "2.0.0"
EXPECTED_REPORT_KEYS = {
    "schema_version",
    "incident",
    "diagnosis",
    "causal_chain",
    "evidence",
    "rejected_hypotheses",
    "impact",
    "recommended_actions",
    "uncertainties",
}
EVIDENCE_ROLES = {
    "root_cause",
    "trigger",
    "symptom",
    "impact",
    "recovery",
    "rejected_hypothesis",
}


def _relative_path(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise RunnerError(f"Expected a non-empty relative path for {context}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value != path.as_posix():
        raise RunnerError(f"Unsafe or non-normalized path for {context}: {value!r}")
    return value


def _fixture_inventory(root: Path) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        inventory[relative] = {
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
    return inventory


def load_log_incident_case_v02(repo_root: Path, case_path: Path) -> dict[str, Any]:
    """Load one v0.2 case and reject undeclared or modified fixture files."""
    resolved_case = resolve_repo_path(repo_root, case_path)
    case = load_json(resolved_case)
    if (
        case.get("schema_version") != "1.0.0"
        or case.get("track") != "B"
        or case.get("task_family") != "incident_investigation"
    ):
        raise RunnerError("Unexpected log incident case identity")
    for key in ("case_id", "case_version", "task_path"):
        if not isinstance(case.get(key), str) or not case[key]:
            raise RunnerError(f"Log incident case must define {key}")

    fixture = case.get("fixture")
    context = case.get("candidate_context")
    output = case.get("output_contract")
    verification = case.get("verification")
    evaluation = case.get("evaluation")
    if not all(
        isinstance(item, dict)
        for item in (fixture, context, output, verification, evaluation)
    ):
        raise RunnerError("Log incident case objects are incomplete")
    if (
        context.get("read_only") is not True
        or context.get("browsing_allowed") is not False
        or context.get("shared_state_allowed") is not False
    ):
        raise RunnerError("Log incident candidate context must be isolated and read-only")
    if (
        output.get("format") != "structured_incident_report"
        or output.get("version") != REPORT_VERSION
    ):
        raise RunnerError("Unsupported v0.2 log incident output contract")
    maximum_bytes = output.get("maximum_serialized_bytes")
    if isinstance(maximum_bytes, bool) or not isinstance(maximum_bytes, int) or maximum_bytes < 1:
        raise RunnerError("Log incident maximum report size must be positive")

    fixture_root = resolve_repo_path(repo_root, fixture.get("root", ""))
    manifest_path = resolve_repo_path(repo_root, fixture.get("manifest_path", ""))
    if not fixture_root.is_dir():
        raise RunnerError("Log incident fixture root does not exist")
    manifest = load_json(manifest_path)
    if (
        manifest.get("case_id") != case["case_id"]
        or manifest.get("manifest_version") != fixture.get("manifest_version")
    ):
        raise RunnerError("Log incident fixture manifest identity mismatch")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise RunnerError("Log incident manifest must contain files")
    declared: dict[str, dict[str, Any]] = {}
    for item in files:
        if not isinstance(item, dict):
            raise RunnerError("Log incident manifest entries must be objects")
        relative = _relative_path(item.get("path"), "fixture manifest")
        if relative in declared:
            raise RunnerError(f"Duplicate fixture path: {relative}")
        if (
            not isinstance(item.get("sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is None
            or not isinstance(item.get("size_bytes"), int)
            or item.get("candidate_visible") is not True
            or item.get("read_only") is not True
        ):
            raise RunnerError(f"Invalid fixture declaration: {relative}")
        declared[relative] = item
    actual = _fixture_inventory(fixture_root)
    if set(actual) != set(declared):
        raise RunnerError("Log incident fixture inventory differs from manifest")
    for relative, item in declared.items():
        expected = {"sha256": item["sha256"], "size_bytes": item["size_bytes"]}
        if actual[relative] != expected:
            raise RunnerError(f"Log incident fixture drift: {relative}")
    visible = context.get("files")
    if not isinstance(visible, list) or visible != sorted(declared):
        raise RunnerError("Candidate-visible log inventory must be sorted and complete")

    paths = {
        "task_path": resolve_repo_path(repo_root, case["task_path"]),
        "schema_path": resolve_repo_path(repo_root, output.get("schema_path", "")),
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
            raise RunnerError(f"Missing log incident {name}: {path}")
    schema = load_json(paths["schema_path"])
    truth = load_json(paths["ground_truth_path"])
    card = load_json(paths["card_path"])
    if truth.get("case_id") != case["case_id"]:
        raise RunnerError("Log incident ground-truth identity mismatch")
    if (
        card.get("case_id") != case["case_id"]
        or card.get("case_version") != case["case_version"]
        or card.get("card_version") != evaluation.get("benchmark_card_version")
    ):
        raise RunnerError("Log incident benchmark-card identity mismatch")
    if set(schema.get("required", [])) != EXPECTED_REPORT_KEYS:
        raise RunnerError("Log incident report schema top-level keys differ")
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
        "ground_truth": truth,
        "ground_truth_path": paths["ground_truth_path"],
        "reference_report_path": paths["reference_report_path"],
        "card": card,
        "card_path": paths["card_path"],
    }


def _event_index(fixture_root: Path) -> dict[str, str]:
    events: dict[str, str] = {}
    for path in sorted((fixture_root / "logs").iterdir()):
        relative = path.relative_to(fixture_root).as_posix()
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            if line.lstrip().startswith("{"):
                value = json.loads(line)
                event_id = value.get("event_id")
            else:
                event_id = line.split(maxsplit=1)[0]
            if not isinstance(event_id, str) or not event_id:
                raise RunnerError(f"Fixture line lacks an event id: {relative}")
            if event_id in events:
                raise RunnerError(f"Duplicate fixture event id: {event_id}")
            events[event_id] = relative
    return events


def _object_shape(value: Any, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def _list_of_objects(value: Any, keys: set[str]) -> bool:
    return isinstance(value, list) and all(_object_shape(item, keys) for item in value)


def _strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _report_value_types_valid(report: dict[str, Any]) -> bool:
    incident = report.get("incident", {})
    diagnosis = report.get("diagnosis", {})
    impact = report.get("impact", {})
    return (
        all(isinstance(value, str) for value in incident.values())
        and isinstance(diagnosis.get("root_cause_code"), str)
        and _strings(diagnosis.get("trigger_codes"))
        and isinstance(diagnosis.get("summary"), str)
        and all(
            isinstance(item.get("event_id"), str)
            and isinstance(item.get("file"), str)
            for item in report.get("causal_chain", [])
        )
        and all(
            isinstance(item.get("event_id"), str)
            and isinstance(item.get("file"), str)
            and isinstance(item.get("supports"), str)
            for item in report.get("evidence", [])
        )
        and all(
            isinstance(item.get("code"), str)
            and _strings(item.get("evidence_ids"))
            and isinstance(item.get("reason"), str)
            for item in report.get("rejected_hypotheses", [])
        )
        and _strings(impact.get("codes"))
        and isinstance(impact.get("summary"), str)
        and all(
            isinstance(item.get("code"), str)
            and isinstance(item.get("rationale"), str)
            for item in report.get("recommended_actions", [])
        )
        and all(
            isinstance(item.get("code"), str)
            and isinstance(item.get("reason"), str)
            for item in report.get("uncertainties", [])
        )
    )


def _subsequence(expected: list[str], observed: list[str]) -> bool:
    position = 0
    for item in observed:
        if position < len(expected) and item == expected[position]:
            position += 1
    return position == len(expected)


def verify_incident_report_v02(
    repo_root: Path, case_path: Path, report: dict[str, Any] | None
) -> dict[str, Any]:
    """Verify a v0.2 report without executing candidate-authored code."""
    loaded = load_log_incident_case_v02(repo_root, case_path)
    truth = loaded["ground_truth"]
    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, detail: str) -> None:
        checks.append(
            {"check_id": check_id, "essential": True, "passed": bool(passed), "detail": detail}
        )

    def result(failure_code: str | None, serialized_bytes: int | None = None) -> dict[str, Any]:
        success = bool(checks) and all(item["passed"] for item in checks if item["essential"])
        value = {
            "schema_version": "1.0.0",
            "case_id": loaded["case"]["case_id"],
            "case_version": loaded["case"]["case_version"],
            "verifier_version": loaded["case"]["verification"]["version"],
            "fixture_manifest_sha256": loaded["manifest_sha256"],
            "ground_truth_sha256": sha256_file(loaded["ground_truth_path"]),
            "checks": checks,
            "essential_check_count": len(checks),
            "essential_pass_count": sum(item["passed"] for item in checks),
            "verified_success": success,
            "failure_code": None if success else failure_code,
        }
        if serialized_bytes is not None:
            value["report_serialized_bytes"] = serialized_bytes
        return value

    if not isinstance(report, dict):
        check("report_object", False, "Candidate report must be a JSON object.")
        return result("missing_or_malformed_report")

    serialized_bytes = len(json.dumps(report, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    structural = (
        set(report) == EXPECTED_REPORT_KEYS
        and report.get("schema_version") == REPORT_VERSION
        and _object_shape(
            report.get("incident"),
            {"start_utc", "last_observed_utc", "primary_service", "affected_user_journey", "recovery_status"},
        )
        and _object_shape(report.get("diagnosis"), {"root_cause_code", "trigger_codes", "summary"})
        and _list_of_objects(report.get("causal_chain"), {"event_id", "file"})
        and _list_of_objects(report.get("evidence"), {"event_id", "file", "supports"})
        and _list_of_objects(report.get("rejected_hypotheses"), {"code", "evidence_ids", "reason"})
        and _object_shape(report.get("impact"), {"codes", "summary"})
        and _list_of_objects(report.get("recommended_actions"), {"code", "rationale"})
        and _list_of_objects(report.get("uncertainties"), {"code", "reason"})
        and _report_value_types_valid(report)
        and serialized_bytes <= loaded["case"]["output_contract"]["maximum_serialized_bytes"]
    )
    check("report_schema", structural, "Complete strict v2 report shape and size boundary.")
    if not structural:
        return result("report_schema_failed", serialized_bytes)

    incident = report["incident"]
    expected_incident = truth["incident"]
    check(
        "incident_window_utc",
        incident["start_utc"] == expected_incident["start_utc"]
        and incident["last_observed_utc"] == expected_incident["last_observed_utc"],
        "UTC impact start and final observation match the evidence.",
    )
    check(
        "recovery_status",
        incident["recovery_status"] == expected_incident["recovery_status"],
        "The report distinguishes full, partial and unobserved recovery.",
    )
    check(
        "affected_scope",
        incident["primary_service"] == expected_incident["primary_service"]
        and incident["affected_user_journey"] == expected_incident["affected_user_journey"],
        "Primary service and affected user journey are identified.",
    )
    diagnosis = report["diagnosis"]
    check(
        "root_cause",
        diagnosis["root_cause_code"] == truth["diagnosis"]["root_cause_code"],
        "Root cause is classified separately from trigger, amplification and impact.",
    )
    check(
        "trigger",
        set(truth["diagnosis"]["required_trigger_codes"]).issubset(diagnosis["trigger_codes"]),
        "Required initiating or exposing trigger is identified.",
    )

    event_index = _event_index(loaded["fixture_root"])
    all_references = [*report["causal_chain"], *report["evidence"]]
    references_valid = all(
        event_index.get(item["event_id"]) == item["file"] for item in all_references
    ) and all(item["supports"] in EVIDENCE_ROLES for item in report["evidence"])
    check("citation_integrity", references_valid, "Every citation exists in its declared source file.")
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
        "Required cause, trigger, propagation, impact and recovery evidence is cited.",
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
        "Plausible alternatives are rejected with supplied counter-evidence.",
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
        not any(fragment in diagnosis_text for fragment in truth["forbidden_diagnosis_fragments"])
        and not any(fragment in impact_text for fragment in truth["forbidden_impact_fragments"]),
        "Diagnosis and impact avoid frozen unsupported claims.",
    )
    return result("deterministic_checks_failed", serialized_bytes)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    reference = subparsers.add_parser("verify-reference", help="Verify the independent reference report")
    reference.add_argument("--case", type=Path, required=True)
    verify = subparsers.add_parser("verify", help="Verify a candidate report")
    verify.add_argument("--case", type=Path, required=True)
    verify.add_argument("--report", type=Path, required=True)
    verify.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    loaded = load_log_incident_case_v02(repo_root, args.case)
    report = (
        load_json(loaded["reference_report_path"])
        if args.command == "verify-reference"
        else load_json(resolve_repo_path(repo_root, args.report))
    )
    result = verify_incident_report_v02(repo_root, args.case, report)
    if getattr(args, "output", None):
        write_json(resolve_repo_path(repo_root, args.output), result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verified_success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
