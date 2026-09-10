from __future__ import annotations

import copy
import unittest
from pathlib import Path

from local_llm_benchmark.multi_format_document_analysis import (
    EXPECTED_CHECK_IDS,
    load_multi_format_case,
    verify_multi_format_report,
)
from local_llm_benchmark.runner import load_json


REPO_ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = Path(
    "tasks/agentic/multi-format-document-analysis/"
    "rollout-readiness-reconciliation/case-v0.1.json"
)
QUALIFICATION_PATH = REPO_ROOT / (
    "tasks/agentic/multi-format-document-analysis/"
    "multi-format-v0.1-offline-qualification.json"
)


def failed_ids(result: dict[str, object]) -> set[str]:
    return {
        item["check_id"]
        for item in result["checks"]
        if not item["passed"]
    }


class MultiFormatDocumentAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.loaded = load_multi_format_case(REPO_ROOT, CASE_PATH)
        self.reference = load_json(self.loaded["reference_report_path"])

    def test_design_is_locked_against_live_execution(self) -> None:
        case = self.loaded["case"]
        self.assertEqual(case["status"], "design_complete_artifacts_pending")
        self.assertFalse(case["live_execution_authorized"])
        self.assertFalse(case["artifact_generation_complete"])
        self.assertFalse(case["canonical_extraction_complete"])

        qualification = load_json(QUALIFICATION_PATH)
        self.assertFalse(qualification["live_inference_performed"])
        self.assertFalse(qualification["live_execution_authorized"])
        self.assertIn(
            "freeze binary hashes and tool/runtime versions",
            qualification["blocking_gates"],
        )

    def test_two_conditions_keep_model_reasoning_and_artifact_access_separate(self) -> None:
        conditions = self.loaded["case"]["evaluation_conditions"]
        self.assertEqual(
            [item["condition_id"] for item in conditions],
            ["canonical-representation", "real-artifact-harness"],
        )
        self.assertEqual([item["track"] for item in conditions], ["A", "B"])
        self.assertEqual(
            [item["artifact_tooling_is_part_of_identity"] for item in conditions],
            [False, True],
        )

    def test_blueprint_has_exactly_three_formats_and_unique_anchors(self) -> None:
        blueprint = self.loaded["blueprint"]
        self.assertEqual(
            {item["format"] for item in blueprint["artifacts"]},
            {"docx", "pdf", "xlsx"},
        )
        facts = blueprint["facts"]
        self.assertEqual(
            len({item["fact_code"] for item in facts}), len(facts)
        )
        self.assertEqual(
            len({item["source_ref"] for item in facts}), len(facts)
        )

    def test_reference_passes_all_eleven_checks(self) -> None:
        result = verify_multi_format_report(REPO_ROOT, CASE_PATH, self.reference)
        self.assertEqual(
            [item["check_id"] for item in result["checks"]],
            EXPECTED_CHECK_IDS,
        )
        self.assertEqual(result["essential_pass_count"], 11)
        self.assertTrue(result["semantic_verified_success"])
        self.assertTrue(result["supplemental_free_text_review_required"])

    def test_task_exposes_every_deterministic_check_marker(self) -> None:
        contract = self.loaded["contract"]
        task = self.loaded["task_path"].read_text(encoding="utf-8")
        self.assertEqual(
            [item["check_id"] for item in contract["essential_checks"]],
            EXPECTED_CHECK_IDS,
        )
        for item in contract["essential_checks"]:
            self.assertIn(item["visible_marker"], task)

    def test_planned_files_match_the_blueprint_exactly(self) -> None:
        self.assertEqual(
            set(self.loaded["case"]["candidate_context"]["planned_files"]),
            {item["filename"] for item in self.loaded["blueprint"]["artifacts"]},
        )
        self.assertEqual(
            self.loaded["case"]["output_contract"][
                "strict_json_transport_scored_separately"
            ],
            self.loaded["contract"]["strict_transport_scored_separately"],
        )

    def test_schema_failure_is_not_repaired_or_semantically_guessed(self) -> None:
        malformed = copy.deepcopy(self.reference)
        del malformed["decision"]
        result = verify_multi_format_report(REPO_ROOT, CASE_PATH, malformed)
        self.assertEqual(failed_ids(result), set(EXPECTED_CHECK_IDS))
        self.assertFalse(result["semantic_verified_success"])

    def test_decision_region_and_blocker_near_misses_fail(self) -> None:
        wrong_decision = copy.deepcopy(self.reference)
        wrong_decision["decision"]["code"] = "full_go"
        self.assertEqual(
            failed_ids(verify_multi_format_report(REPO_ROOT, CASE_PATH, wrong_decision)),
            {"decision"},
        )

        wrong_regions = copy.deepcopy(self.reference)
        wrong_regions["decision"]["approved_regions"] = ["north", "central"]
        self.assertEqual(
            failed_ids(verify_multi_format_report(REPO_ROOT, CASE_PATH, wrong_regions)),
            {"approved_regions"},
        )

        wrong_blocker = copy.deepcopy(self.reference)
        wrong_blocker["decision"]["blocked_regions"][0]["blocker_code"] = (
            "capacity_below_threshold"
        )
        self.assertEqual(
            failed_ids(verify_multi_format_report(REPO_ROOT, CASE_PATH, wrong_blocker)),
            {"region_blockers"},
        )

    def test_citation_and_required_evidence_are_independent(self) -> None:
        wrong_anchor = copy.deepcopy(self.reference)
        wrong_anchor["evidence"][0]["source_ref"] = "rollout-policy.docx#not-real"
        result = verify_multi_format_report(REPO_ROOT, CASE_PATH, wrong_anchor)
        self.assertEqual(failed_ids(result), {"citation_integrity"})

        missing_fact = copy.deepcopy(self.reference)
        missing_fact["evidence"] = [
            item for item in missing_fact["evidence"] if item["fact_code"] != "POL-CUTOFF"
        ]
        result = verify_multi_format_report(REPO_ROOT, CASE_PATH, missing_fact)
        self.assertEqual(failed_ids(result), {"required_evidence"})

    def test_cross_format_conflict_action_and_uncertainty_near_misses_fail(self) -> None:
        no_xlsx = copy.deepcopy(self.reference)
        no_xlsx["evidence"] = [
            item
            for item in no_xlsx["evidence"]
            if not item["source_ref"].startswith("regional-readiness.xlsx")
        ]
        result = verify_multi_format_report(REPO_ROOT, CASE_PATH, no_xlsx)
        self.assertEqual(
            failed_ids(result), {"required_evidence", "cross_format_coverage"}
        )

        no_conflict = copy.deepcopy(self.reference)
        no_conflict["conflicts"] = no_conflict["conflicts"][:1]
        self.assertEqual(
            failed_ids(verify_multi_format_report(REPO_ROOT, CASE_PATH, no_conflict)),
            {"conflict_resolution"},
        )

        no_action = copy.deepcopy(self.reference)
        no_action["recommended_actions"] = no_action["recommended_actions"][:-1]
        self.assertEqual(
            failed_ids(verify_multi_format_report(REPO_ROOT, CASE_PATH, no_action)),
            {"action_plan"},
        )

        no_uncertainty = copy.deepcopy(self.reference)
        no_uncertainty["uncertainties"] = no_uncertainty["uncertainties"][:-1]
        self.assertEqual(
            failed_ids(
                verify_multi_format_report(REPO_ROOT, CASE_PATH, no_uncertainty)
            ),
            {"uncertainty"},
        )

    def test_invented_controlled_value_fails_integrity(self) -> None:
        invented = copy.deepcopy(self.reference)
        invented["recommended_actions"].append(
            {"code": "invented_action", "rationale": "Not in the visible codebook."}
        )
        result = verify_multi_format_report(REPO_ROOT, CASE_PATH, invented)
        self.assertEqual(failed_ids(result), {"controlled_value_integrity"})

    def test_duplicate_blocker_or_conflict_does_not_hide_behind_set_equality(self) -> None:
        duplicate_blocker = copy.deepcopy(self.reference)
        duplicate_blocker["decision"]["blocked_regions"].append(
            copy.deepcopy(duplicate_blocker["decision"]["blocked_regions"][0])
        )
        self.assertEqual(
            failed_ids(
                verify_multi_format_report(REPO_ROOT, CASE_PATH, duplicate_blocker)
            ),
            {"region_blockers"},
        )

        duplicate_conflict = copy.deepcopy(self.reference)
        duplicate_conflict["conflicts"].append(
            copy.deepcopy(duplicate_conflict["conflicts"][0])
        )
        self.assertEqual(
            failed_ids(
                verify_multi_format_report(REPO_ROOT, CASE_PATH, duplicate_conflict)
            ),
            {"conflict_resolution"},
        )


if __name__ == "__main__":
    unittest.main()
