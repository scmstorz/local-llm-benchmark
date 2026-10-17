from __future__ import annotations

import copy
import unittest
from pathlib import Path

from local_llm_benchmark import multi_format_transfer as original
from local_llm_benchmark import multi_format_transfer_v021 as current
from local_llm_benchmark.runner import load_json


ROOT = Path(__file__).resolve().parents[1]
CASE = Path(
    "tasks/agentic/multi-format-document-analysis/"
    "supplier-award-reconciliation/case-v0.2.json"
)
EXTRA = "supplier-assurance-review.pdf#page=3&table=Final-assurance&row=Atlas"


class SupplierVerifier021Tests(unittest.TestCase):
    def setUp(self) -> None:
        loaded = original.load_multi_format_transfer_case(ROOT, CASE)
        self.report = load_json(loaded["reference_report_path"])

    def verify(self) -> dict:
        return current.verify_multi_format_transfer_report(ROOT, CASE, self.report)

    def assert_conflict_fails(self) -> None:
        result = self.verify()
        self.assertFalse(result["semantic_verified_success"])
        self.assertIn(
            "conflict_resolution",
            {check["check_id"] for check in result["checks"] if not check["passed"]},
        )

    def test_reference_remains_successful_with_explicit_new_version(self) -> None:
        result = self.verify()
        self.assertEqual(result["verifier_version"], "2.1.0")
        self.assertEqual(result["evaluation_contract"]["version"], "0.3")
        self.assertEqual(result["essential_pass_count"], 12)
        self.assertTrue(result["supplemental_free_text_review_required"])

    def test_extra_known_anchor_is_allowed_only_by_new_verifier(self) -> None:
        self.report["conflicts"][0]["source_refs"].append(EXTRA)
        self.assertTrue(self.verify()["semantic_verified_success"])
        historical = original.verify_multi_format_transfer_report(ROOT, CASE, self.report)
        self.assertEqual(historical["verifier_version"], "2.0.0")
        self.assertEqual(historical["essential_pass_count"], 11)

    def test_unknown_extra_anchor_is_rejected(self) -> None:
        self.report["conflicts"][0]["source_refs"].append(EXTRA + "-invented")
        self.assert_conflict_fails()

    def test_required_anchor_cannot_be_replaced_by_known_extra(self) -> None:
        self.report["conflicts"][0]["source_refs"][0] = EXTRA
        self.assert_conflict_fails()

    def test_policy_anchor_elsewhere_does_not_replace_conflict_requirement(self) -> None:
        self.report["conflicts"][1]["source_refs"] = self.report["conflicts"][1]["source_refs"][1:]
        self.assert_conflict_fails()

    def test_duplicate_source_is_rejected(self) -> None:
        self.report["conflicts"][0]["source_refs"].append(
            self.report["conflicts"][0]["source_refs"][0]
        )
        self.assert_conflict_fails()

    def test_duplicate_conflict_is_rejected_even_with_different_extra_anchor(self) -> None:
        duplicate = copy.deepcopy(self.report["conflicts"][0])
        duplicate["source_refs"].append(EXTRA)
        self.report["conflicts"].append(duplicate)
        self.assert_conflict_fails()

    def test_missing_conflict_is_rejected(self) -> None:
        self.report["conflicts"].pop()
        self.assert_conflict_fails()

    def test_action_failure_is_not_repaired_by_more_citations(self) -> None:
        self.report["conflicts"][0]["source_refs"].append(EXTRA)
        self.report["recommended_actions"] = self.report["recommended_actions"][:-1]
        result = self.verify()
        failed = {c["check_id"] for c in result["checks"] if not c["passed"]}
        self.assertEqual(failed, {"action_plan"})

    def test_schema_failure_is_not_repaired(self) -> None:
        self.report["schema_version"] = "2.0"
        self.assertEqual(self.verify()["essential_pass_count"], 0)

    def test_evaluation_does_not_mutate_candidate_or_original_contract(self) -> None:
        previous = copy.deepcopy(self.report)
        self.verify()
        self.assertEqual(self.report, previous)
        self.assertEqual(load_json(ROOT / current.BASE_CONTRACT)["contract_version"], "0.2")


if __name__ == "__main__":
    unittest.main()
