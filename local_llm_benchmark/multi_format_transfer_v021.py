"""Supplier verifier 2.1.0: require conflict anchors and allow valid additions.

The frozen 2.0.0 verifier and its historical scores are unchanged. This explicit
offline entry point applies evaluation contract 0.3 to future evaluations.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from . import multi_format_transfer as original
from .runner import RunnerError, load_json, resolve_repo_path, sha256_file


VERIFIER_VERSION = "2.1.0"
DEFAULT_CONTRACT = Path(
    "tasks/agentic/multi-format-document-analysis/evaluation-contract-v0.3.json"
)
BASE_CONTRACT = DEFAULT_CONTRACT.with_name("evaluation-contract-v0.2.json")
CITATION_POLICY = {
    "conflict_codes": "exact_required_set_without_duplicates",
    "required_source_refs": "must_all_be_present_in_each_conflict",
    "additional_source_refs": "allowed_only_if_known_in_the_case_blueprint",
    "duplicate_source_refs": "rejected",
    "free_text_entailment": "separate_source_grounded_review",
}


def load_evaluation_contract(
    repo_root: Path, contract_path: Path = DEFAULT_CONTRACT
) -> dict[str, Any]:
    path = resolve_repo_path(repo_root, contract_path)
    contract = load_json(path)
    expected = copy.deepcopy(load_json(repo_root / BASE_CONTRACT))
    expected.update(
        contract_version="0.3",
        verifier_version=VERIFIER_VERSION,
        base_contract={
            "path": BASE_CONTRACT.as_posix(),
            "sha256": sha256_file(repo_root / BASE_CONTRACT),
        },
        conflict_citation_policy=CITATION_POLICY,
        historical_scores_changed=False,
        live_execution_authorized=False,
    )
    if contract != expected:
        raise RunnerError("Unexpected supplier evaluation contract 0.3")
    return {"contract": contract, "path": path, "sha256": sha256_file(path)}


def _conflicts_valid(report: dict[str, Any], loaded: dict[str, Any]) -> bool:
    expected = {
        conflict["code"]: set(conflict["source_refs"])
        for conflict in loaded["truth"]["required_conflicts"]
    }
    conflicts = report["conflicts"]
    codes = [conflict["code"] for conflict in conflicts]
    if len(codes) != len(set(codes)) or set(codes) != set(expected):
        return False
    known = {fact["source_ref"] for fact in loaded["blueprint"]["facts"]}
    return all(
        len(conflict["source_refs"]) == len(set(conflict["source_refs"]))
        and expected[conflict["code"]] <= set(conflict["source_refs"])
        and set(conflict["source_refs"]) <= known
        for conflict in conflicts
    )


def verify_multi_format_transfer_report(
    repo_root: Path, case_path: Path, report: Any
) -> dict[str, Any]:
    """Evaluate explicitly under 2.1.0 without changing a run or old verifier."""
    contract = load_evaluation_contract(repo_root)
    result = original.verify_multi_format_transfer_report(repo_root, case_path, report)
    result["verifier_version"] = VERIFIER_VERSION
    result["evaluation_contract"] = {
        "path": DEFAULT_CONTRACT.as_posix(),
        "sha256": contract["sha256"],
        "version": "0.3",
    }
    if result["checks"][0]["passed"]:
        loaded = original.load_multi_format_transfer_case(repo_root, case_path)
        for check in result["checks"]:
            if check["check_id"] == "conflict_resolution":
                check.update(
                    passed=_conflicts_valid(report, loaded),
                    detail=(
                        "Each required conflict must retain all mandatory anchors; "
                        "additional known anchors are allowed without duplicates"
                    ),
                )
    result["essential_pass_count"] = sum(check["passed"] for check in result["checks"])
    result["semantic_verified_success"] = (
        result["essential_pass_count"] == result["essential_check_count"]
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    root = Path.cwd().resolve()
    result = verify_multi_format_transfer_report(root, args.case, load_json(args.report))
    serialized = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as output:
            output.write(serialized)
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
