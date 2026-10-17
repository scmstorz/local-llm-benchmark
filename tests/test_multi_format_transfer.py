from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from local_llm_benchmark.multi_format_transfer import (
    EXPECTED_CHECK_IDS,
    load_multi_format_transfer_case,
    verify_multi_format_transfer_report,
)
from local_llm_benchmark.runner import load_json


REPO_ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = Path(
    "tasks/agentic/multi-format-document-analysis/"
    "supplier-award-reconciliation/case-v0.2.json"
)
QUALIFICATION_PATH = REPO_ROOT / (
    "tasks/agentic/multi-format-document-analysis/"
    "supplier-award-reconciliation/offline-qualification-v0.2.json"
)


def failed_ids(result: dict[str, object]) -> set[str]:
    return {
        item["check_id"]
        for item in result["checks"]
        if not item["passed"]
    }


class MultiFormatTransferTests(unittest.TestCase):
    def setUp(self) -> None:
        self.loaded = load_multi_format_transfer_case(REPO_ROOT, CASE_PATH)
        self.reference = load_json(self.loaded["reference_report_path"])

    def test_case_is_offline_with_qualified_artifacts_canonical_and_api(self) -> None:
        case = self.loaded["case"]
        self.assertEqual(
            case["status"],
            "complete_systems_qualified_pending_smoke_freeze",
        )
        self.assertFalse(case["live_execution_authorized"])
        self.assertTrue(case["artifact_generation_complete"])
        self.assertTrue(case["canonical_extraction_complete"])
        self.assertEqual(
            case["candidate_context"]["planned_files"],
            [
                "supplier-selection-policy.docx",
                "supplier-assurance-review.pdf",
                "bid-evaluation.xlsx",
            ],
        )
        fixture_root = REPO_ROOT / case["planned_artifact_root"]
        self.assertEqual(
            sorted(path.name for path in fixture_root.iterdir()),
            sorted(case["candidate_context"]["planned_files"]),
        )

    def test_offline_qualification_binds_the_semantic_contract(self) -> None:
        qualification = load_json(QUALIFICATION_PATH)
        self.assertEqual(
            qualification["status"],
            "complete_systems_qualified_pending_smoke_freeze",
        )
        self.assertFalse(qualification["live_inference_performed"])
        self.assertFalse(qualification["live_execution_authorized"])
        for key, relative in (
            ("case", "case_path"),
            ("task", "task_path"),
            ("source_blueprint", "source_blueprint_path"),
            ("ground_truth", "ground_truth_path"),
            ("reference_report", "reference_report_path"),
            ("report_schema", "report_schema_path"),
            ("evaluation_contract", "evaluation_contract_path"),
            ("canonical_schema", "canonical_schema_path"),
            ("verifier", "verifier_path"),
        ):
            path = REPO_ROOT / qualification["semantic_contract"][relative]
            self.assertEqual(
                qualification["semantic_contract"][f"{key}_sha256"],
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        self.assertNotIn(
            "resolve the unavailable workspace dependency loader before XLSX authoring or authorize a new case-specific alternative-runtime amendment",
            qualification["blocking_gates"],
        )
        self.assertNotIn(
            "build and qualify the canonical extraction from the frozen binaries",
            qualification["blocking_gates"],
        )
        self.assertEqual(
            qualification["blocking_gates"],
            [
                "design and freeze a separate excluded no-retry transfer smoke",
                "obtain a separate post-freeze authorization before any Ollama request",
            ],
        )

    def test_binary_artifact_qualifications_bind_frozen_files_and_inputs(self) -> None:
        case = self.loaded["case"]
        for format_name, relative_qualification in case["artifact_qualifications"].items():
            with self.subTest(format=format_name):
                qualification = load_json(REPO_ROOT / relative_qualification)
                self.assertEqual(qualification["status"], "qualified")
                self.assertFalse(qualification["live_inference_performed"])
                artifact = REPO_ROOT / qualification["artifact"]["path"]
                self.assertEqual(artifact.suffix, f".{format_name}")
                self.assertEqual(qualification["artifact"]["size_bytes"], artifact.stat().st_size)
                self.assertEqual(
                    qualification["artifact"]["sha256"],
                    hashlib.sha256(artifact.read_bytes()).hexdigest(),
                )
                amendment = REPO_ROOT / qualification["authoring_protocol"]["amendment_path"]
                self.assertEqual(
                    qualification["authoring_protocol"]["amendment_sha256"],
                    hashlib.sha256(amendment.read_bytes()).hexdigest(),
                )
                self.assertTrue(qualification["authoring_protocol"]["artifact_operation_marker_recorded"])
                for item in qualification["reproducibility_inputs"]:
                    path = REPO_ROOT / item["path"]
                    self.assertEqual(item["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
                visual_qa = qualification.get(
                    "render_and_visual_qa", qualification.get("visual_qa")
                )
                self.assertIsInstance(visual_qa, dict)
                self.assertTrue(visual_qa["passed"])

    def test_track_b_artifact_api_qualification_binds_backend_and_parity(self) -> None:
        case = self.loaded["case"]
        qualification_path = REPO_ROOT / case["track_b_harness"]["artifact_api_qualification_path"]
        qualification = load_json(qualification_path)
        self.assertEqual(qualification["status"], "qualified_for_complete_system_adaptation")
        self.assertEqual(qualification["live_ollama_requests"], 0)
        self.assertFalse(qualification["live_model_inference"])
        evidence = qualification["qualification_evidence"]
        self.assertEqual(evidence["records_equal_frozen_canonical_extraction"], 16)
        self.assertTrue(evidence["standalone_bridge_matches_direct_import"])
        self.assertTrue(evidence["artifact_bytes_unchanged_after_all_reads"])
        for item in qualification["artifacts"]:
            path = REPO_ROOT / item["path"]
            self.assertEqual(item["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())

    def test_transfer_design_changes_domain_and_reasoning_shape(self) -> None:
        transfer = self.loaded["blueprint"]["transfer_design"]
        self.assertEqual(
            transfer["source_case"],
            "agentic.documents.rollout-readiness-reconciliation",
        )
        self.assertFalse(transfer["reused_source_artifacts"])
        self.assertFalse(transfer["reused_candidate_observations"])
        self.assertIn("filter suppliers", transfer["changed_reasoning_shape"])
        self.assertGreaterEqual(len(transfer["anti_isomorphism_controls"]), 5)

    def test_blueprint_has_three_formats_and_unique_facts(self) -> None:
        blueprint = self.loaded["blueprint"]
        self.assertEqual(
            [item["format"] for item in blueprint["artifacts"]],
            ["docx", "pdf", "xlsx"],
        )
        facts = blueprint["facts"]
        self.assertEqual(len(facts), 16)
        self.assertEqual(len({item["fact_code"] for item in facts}), 16)
        self.assertEqual(len({item["source_ref"] for item in facts}), 16)
        self.assertEqual(
            {item["artifact"] for item in facts}, {"docx", "pdf", "xlsx"}
        )

    def test_task_exposes_all_twelve_check_markers(self) -> None:
        self.assertEqual(len(EXPECTED_CHECK_IDS), 12)
        self.assertEqual(
            [item["check_id"] for item in self.loaded["contract"]["essential_checks"]],
            EXPECTED_CHECK_IDS,
        )
        task_text = self.loaded["task_path"].read_text(encoding="utf-8")
        for item in self.loaded["contract"]["essential_checks"]:
            self.assertIn(item["visible_marker"], task_text)

    def test_planned_canonical_schema_is_case_specific_and_complete(self) -> None:
        schema = self.loaded["canonical_schema"]
        properties = schema["properties"]
        self.assertEqual(
            properties["case_id"]["const"],
            "agentic.documents.supplier-award-reconciliation",
        )
        self.assertEqual(properties["evidence_records"]["minItems"], 16)
        self.assertEqual(properties["evidence_records"]["maxItems"], 16)
        self.assertIn(
            "signed_final_at_cutoff",
            schema["$defs"]["evidence_record"]["properties"]["authority"]["enum"],
        )

    def test_reference_passes_all_twelve_checks(self) -> None:
        result = verify_multi_format_transfer_report(
            REPO_ROOT, CASE_PATH, self.reference
        )
        self.assertTrue(result["semantic_verified_success"])
        self.assertEqual(result["essential_pass_count"], 12)
        self.assertEqual(result["essential_check_count"], 12)
        self.assertEqual(failed_ids(result), set())
        self.assertTrue(result["supplemental_free_text_review_required"])

    def test_swapping_eligible_primary_and_reserve_fails_both_rank_checks(self) -> None:
        report = copy.deepcopy(self.reference)
        report["decision"]["primary_supplier"] = "boreal"
        report["decision"]["reserve_supplier"] = "atlas"
        self.assertEqual(
            failed_ids(verify_multi_format_transfer_report(REPO_ROOT, CASE_PATH, report)),
            {"primary_supplier", "reserve_supplier"},
        )

    def test_cheapest_but_ineligible_supplier_cannot_win(self) -> None:
        report = copy.deepcopy(self.reference)
        report["decision"]["primary_supplier"] = "cedar"
        report["decision"]["reserve_supplier"] = "atlas"
        self.assertEqual(
            failed_ids(verify_multi_format_transfer_report(REPO_ROOT, CASE_PATH, report)),
            {"primary_supplier", "reserve_supplier"},
        )

    def test_supplier_blocker_near_miss_fails(self) -> None:
        report = copy.deepcopy(self.reference)
        report["decision"]["rejected_suppliers"][1]["blocker_code"] = (
            "cost_above_ceiling"
        )
        self.assertEqual(
            failed_ids(verify_multi_format_transfer_report(REPO_ROOT, CASE_PATH, report)),
            {"supplier_blockers"},
        )

    def test_wrong_anchor_and_missing_fact_fail_independently(self) -> None:
        report = copy.deepcopy(self.reference)
        report["evidence"][0]["source_ref"] += "-wrong"
        self.assertEqual(
            failed_ids(verify_multi_format_transfer_report(REPO_ROOT, CASE_PATH, report)),
            {"citation_integrity"},
        )

        report = copy.deepcopy(self.reference)
        report["evidence"] = [
            item for item in report["evidence"] if item["fact_code"] != "BID-BOREAL"
        ]
        self.assertEqual(
            failed_ids(verify_multi_format_transfer_report(REPO_ROOT, CASE_PATH, report)),
            {"required_evidence"},
        )

    def test_cross_format_coverage_is_not_implied_by_other_checks(self) -> None:
        report = copy.deepcopy(self.reference)
        report["evidence"] = [
            item
            for item in report["evidence"]
            if not item["source_ref"].startswith("bid-evaluation.xlsx")
        ]
        result = verify_multi_format_transfer_report(REPO_ROOT, CASE_PATH, report)
        self.assertIn("required_evidence", failed_ids(result))
        self.assertIn("cross_format_coverage", failed_ids(result))

    def test_conflict_action_and_uncertainty_near_misses_fail(self) -> None:
        report = copy.deepcopy(self.reference)
        report["conflicts"] = report["conflicts"][:1]
        report["recommended_actions"] = report["recommended_actions"][:-1]
        report["uncertainties"] = report["uncertainties"][:1]
        self.assertEqual(
            failed_ids(verify_multi_format_transfer_report(REPO_ROOT, CASE_PATH, report)),
            {"conflict_resolution", "action_plan", "uncertainty"},
        )

    def test_schema_failure_is_not_semantically_repaired(self) -> None:
        report = copy.deepcopy(self.reference)
        report["schema_version"] = "2.0"
        result = verify_multi_format_transfer_report(REPO_ROOT, CASE_PATH, report)
        self.assertFalse(result["semantic_verified_success"])
        self.assertEqual(result["essential_pass_count"], 0)
        self.assertEqual(failed_ids(result), set(EXPECTED_CHECK_IDS))

    def test_invented_controlled_value_fails_integrity(self) -> None:
        report = copy.deepcopy(self.reference)
        report["recommended_actions"].append(
            {"code": "invented_action", "rationale": "Nicht kontrolliert."}
        )
        self.assertEqual(
            failed_ids(verify_multi_format_transfer_report(REPO_ROOT, CASE_PATH, report)),
            {"controlled_value_integrity"},
        )

    def test_serialized_reference_stays_within_public_contract(self) -> None:
        serialized = json.dumps(self.reference, ensure_ascii=False).encode("utf-8")
        self.assertLessEqual(
            len(serialized), self.loaded["case"]["output_contract"]["maximum_serialized_bytes"]
        )


if __name__ == "__main__":
    unittest.main()
