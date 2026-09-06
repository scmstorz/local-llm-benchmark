from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from local_llm_benchmark.log_incident_v05 import (
    EXPECTED_CHECK_IDS,
    load_log_incident_case_v05,
    parse_incident_report_response_v05,
    verify_incident_report_v05,
)
from local_llm_benchmark.runner import RunnerError, load_json


REPO_ROOT = Path(__file__).resolve().parents[1]
CASES = [
    Path("tasks/agentic/log-incident-analysis/checkout-pool-regression/case-v0.5.json"),
    Path("tasks/agentic/log-incident-analysis/retry-queue-amplification/case-v0.5.json"),
    Path("tasks/agentic/log-incident-analysis/clock-skew-partial-recovery/case-v0.5.json"),
]
V02_CASE = Path(
    "tasks/agentic/log-incident-analysis/checkout-pool-regression/case-v2.json"
)
V03_CASE = Path(
    "tasks/agentic/log-incident-analysis/checkout-pool-regression/case-v0.3.json"
)
V04_CASE = Path(
    "tasks/agentic/log-incident-analysis/checkout-pool-regression/case-v0.4.json"
)


def failed_ids(result: dict[str, object]) -> set[str]:
    return {
        item["check_id"]
        for item in result["checks"]
        if not item["passed"]
    }


class LogIncidentV05Tests(unittest.TestCase):
    def test_all_cases_are_aligned_and_references_pass_fifteen_checks(self) -> None:
        for case_path in CASES:
            with self.subTest(case=case_path):
                loaded = load_log_incident_case_v05(REPO_ROOT, case_path)
                report = load_json(loaded["reference_report_path"])
                result = verify_incident_report_v05(REPO_ROOT, case_path, report)
                self.assertEqual(
                    [item["check_id"] for item in result["checks"]],
                    EXPECTED_CHECK_IDS,
                )
                self.assertEqual(result["essential_pass_count"], 15)
                self.assertTrue(result["semantic_verified_success"])
                markers = [
                    item["visible_marker"]
                    for item in loaded["criteria"]["essential_checks"]
                ]
                task = loaded["task_path"].read_text(encoding="utf-8")
                self.assertTrue(all(marker in task for marker in markers))

    def test_incident_start_and_last_observation_are_independent(self) -> None:
        for case_path in CASES:
            loaded = load_log_incident_case_v05(REPO_ROOT, case_path)
            reference = load_json(loaded["reference_report_path"])
            start_mutation = copy.deepcopy(reference)
            start_mutation["incident"]["start_utc"] = "2000-01-01T00:00:00Z"
            start_result = verify_incident_report_v05(
                REPO_ROOT, case_path, start_mutation
            )
            self.assertEqual(failed_ids(start_result), {"incident_start_utc"})

            last_mutation = copy.deepcopy(reference)
            last_mutation["incident"]["last_observed_utc"] = (
                "2000-01-01T00:00:00Z"
            )
            last_result = verify_incident_report_v05(
                REPO_ROOT, case_path, last_mutation
            )
            self.assertEqual(failed_ids(last_result), {"last_observed_utc"})

    def test_scope_requires_exact_visible_controlled_ids(self) -> None:
        noncanonical = {
            CASES[0]: ("payment api", "Checkout"),
            CASES[1]: ("order worker", "order status / order fulfillment"),
            CASES[2]: ("payment-validation (payment-node-03)", "checkout authorization"),
        }
        for case_path, (service, journey) in noncanonical.items():
            with self.subTest(case=case_path):
                loaded = load_log_incident_case_v05(REPO_ROOT, case_path)
                report = load_json(loaded["reference_report_path"])
                report["incident"]["primary_service"] = service
                report["incident"]["affected_user_journey"] = journey
                result = verify_incident_report_v05(REPO_ROOT, case_path, report)
                self.assertIn("affected_scope", failed_ids(result))
                self.assertIn("controlled_code_integrity", failed_ids(result))

    def test_wrong_but_visible_scope_id_fails_affected_scope_only(self) -> None:
        loaded = load_log_incident_case_v05(REPO_ROOT, CASES[1])
        report = load_json(loaded["reference_report_path"])
        report["incident"]["affected_user_journey"] = "checkout"
        result = verify_incident_report_v05(REPO_ROOT, CASES[1], report)
        self.assertEqual(failed_ids(result), {"affected_scope"})

    def test_alternative_sufficient_counterevidence_groups_pass(self) -> None:
        alternatives = {
            CASES[0]: {
                "database_outage": ["DB-400", "DB-402", "DB-403"],
                "authentication_failure": ["AUTH-501", "AUTH-502"],
            },
            CASES[1]: {
                "message_broker_outage": ["BRK-300", "BRK-302"],
                "notification_tls_failure": ["NOTIFY-501", "NOTIFY-502"],
            },
        }
        for case_path, by_code in alternatives.items():
            with self.subTest(case=case_path):
                loaded = load_log_incident_case_v05(REPO_ROOT, case_path)
                report = load_json(loaded["reference_report_path"])
                for item in report["rejected_hypotheses"]:
                    if item["code"] in by_code:
                        item["evidence_ids"] = by_code[item["code"]]
                result = verify_incident_report_v05(REPO_ROOT, case_path, report)
                self.assertTrue(result["semantic_verified_success"])

    def test_partial_counterevidence_group_still_fails(self) -> None:
        loaded = load_log_incident_case_v05(REPO_ROOT, CASES[0])
        report = load_json(loaded["reference_report_path"])
        for item in report["rejected_hypotheses"]:
            if item["code"] == "authentication_failure":
                item["evidence_ids"] = ["AUTH-502"]
        result = verify_incident_report_v05(REPO_ROOT, CASES[0], report)
        self.assertEqual(failed_ids(result), {"distractor_rejection"})

    def test_event_id_mentioned_only_in_reason_does_not_count_as_attached(self) -> None:
        loaded = load_log_incident_case_v05(REPO_ROOT, CASES[0])
        report = load_json(loaded["reference_report_path"])
        for item in report["rejected_hypotheses"]:
            if item["code"] == "authentication_failure":
                item["evidence_ids"] = ["AUTH-502"]
                item["reason"] += " AUTH-500 was an unrelated admin probe."
        result = verify_incident_report_v05(REPO_ROOT, CASES[0], report)
        self.assertEqual(failed_ids(result), {"distractor_rejection"})

    def test_negated_forbidden_phrases_do_not_affect_deterministic_result(self) -> None:
        loaded = load_log_incident_case_v05(REPO_ROOT, CASES[1])
        report = load_json(loaded["reference_report_path"])
        report["impact"]["summary"] = (
            "No orders were lost; checkout was not unavailable; "
            "production notifications did not fail."
        )
        result = verify_incident_report_v05(REPO_ROOT, CASES[1], report)
        self.assertTrue(result["semantic_verified_success"])

    def test_free_text_claim_polarity_is_deferred_to_supplemental_review(self) -> None:
        loaded = load_log_incident_case_v05(REPO_ROOT, CASES[1])
        report = load_json(loaded["reference_report_path"])
        report["impact"]["summary"] = "Orders were lost."
        result = verify_incident_report_v05(REPO_ROOT, CASES[1], report)
        self.assertTrue(result["semantic_verified_success"])
        self.assertTrue(
            loaded["case"]["evaluation"][
                "supplemental_human_or_llm_free_text_claim_review_required"
            ]
        )

    def test_clock_reference_uses_each_event_under_one_direct_role(self) -> None:
        loaded = load_log_incident_case_v05(REPO_ROOT, CASES[2])
        report = load_json(loaded["reference_report_path"])
        pay_roles = [
            item["supports"]
            for item in report["evidence"]
            if item["event_id"] == "PAY3-300"
        ]
        self.assertEqual(pay_roles, ["symptom"])
        result = verify_incident_report_v05(REPO_ROOT, CASES[2], report)
        self.assertTrue(result["semantic_verified_success"])

    def test_targeted_semantic_near_misses_fail(self) -> None:
        loaded = load_log_incident_case_v05(REPO_ROOT, CASES[0])
        reference = load_json(loaded["reference_report_path"])
        mutations: list[tuple[str, object]] = []

        wrong_recovery = copy.deepcopy(reference)
        wrong_recovery["incident"]["recovery_status"] = "partial"
        mutations.append(("recovery_status", wrong_recovery))

        wrong_scope = copy.deepcopy(reference)
        wrong_scope["incident"]["primary_service"] = "postgres"
        mutations.append(("affected_scope", wrong_scope))

        wrong_cause = copy.deepcopy(reference)
        wrong_cause["diagnosis"]["root_cause_code"] = "dependency_outage"
        mutations.append(("root_cause", wrong_cause))

        no_trigger = copy.deepcopy(reference)
        no_trigger["diagnosis"]["trigger_codes"] = []
        mutations.append(("trigger", no_trigger))

        bad_citation = copy.deepcopy(reference)
        bad_citation["evidence"][0]["file"] = "logs/not-real.log"
        mutations.append(("citation_integrity", bad_citation))

        reversed_chain = copy.deepcopy(reference)
        reversed_chain["causal_chain"].reverse()
        mutations.append(("causal_chain", reversed_chain))

        missing_role = copy.deepcopy(reference)
        missing_role["evidence"] = [
            item
            for item in missing_role["evidence"]
            if item["event_id"] != "GATE-102"
        ]
        mutations.append(("critical_evidence", missing_role))

        weak_rejection = copy.deepcopy(reference)
        weak_rejection["rejected_hypotheses"][0]["evidence_ids"] = []
        mutations.append(("distractor_rejection", weak_rejection))

        unsupported_impact = copy.deepcopy(reference)
        unsupported_impact["impact"]["codes"].append("data_loss")
        mutations.append(("bounded_impact", unsupported_impact))

        missing_action = copy.deepcopy(reference)
        missing_action["recommended_actions"] = []
        mutations.append(("remediation", missing_action))

        missing_uncertainty = copy.deepcopy(reference)
        missing_uncertainty["uncertainties"] = []
        mutations.append(("uncertainty", missing_uncertainty))

        invented_code = copy.deepcopy(reference)
        invented_code["impact"]["codes"].append("invented_impact")
        mutations.append(("controlled_code_integrity", invented_code))

        for expected_failure, mutation in mutations:
            with self.subTest(check=expected_failure):
                result = verify_incident_report_v05(REPO_ROOT, CASES[0], mutation)
                self.assertIn(expected_failure, failed_ids(result))
                self.assertFalse(result["semantic_verified_success"])

    def test_schema_near_miss_fails_without_guessing(self) -> None:
        loaded = load_log_incident_case_v05(REPO_ROOT, CASES[0])
        report = load_json(loaded["reference_report_path"])
        del report["uncertainties"]
        result = verify_incident_report_v05(REPO_ROOT, CASES[0], report)
        self.assertEqual(failed_ids(result), {"report_schema"})
        self.assertEqual(result["failure_code"], "report_schema_failed")

    def test_prior_representations_are_not_silently_admitted(self) -> None:
        for prior_case in (V02_CASE, V03_CASE, V04_CASE):
            with self.subTest(case=prior_case):
                with self.assertRaisesRegex(RunnerError, "v0.5"):
                    load_log_incident_case_v05(REPO_ROOT, prior_case)


class LogIncidentV05ResponseParserTests(unittest.TestCase):
    def setUp(self) -> None:
        loaded = load_log_incident_case_v05(REPO_ROOT, CASES[0])
        self.report = load_json(loaded["reference_report_path"])
        self.encoded = json.dumps(self.report)

    def test_strict_object_is_valid_and_transport_compliant(self) -> None:
        result = parse_incident_report_response_v05(self.encoded)
        self.assertEqual(result["status"], "valid")
        self.assertTrue(result["strict_transport_compliance"])
        self.assertFalse(result["normalization_applied"])
        self.assertEqual(result["report"], self.report)

    def test_one_fenced_object_is_recovered_but_not_strict(self) -> None:
        result = parse_incident_report_response_v05(
            f"Here is the report:\n```json\n{self.encoded}\n```"
        )
        self.assertEqual(result["status"], "valid")
        self.assertFalse(result["strict_transport_compliance"])
        self.assertTrue(result["normalization_applied"])
        self.assertEqual(result["normalization_kind"], "markdown_code_fence")
        self.assertEqual(result["report"], self.report)

    def test_one_object_with_plain_prose_is_recovered(self) -> None:
        result = parse_incident_report_response_v05(
            f"Final answer follows.\n{self.encoded}\nEnd of answer."
        )
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["normalization_kind"], "surrounding_text")

    def test_normalizer_never_repairs_malformed_json(self) -> None:
        result = parse_incident_report_response_v05('{"broken": }')
        self.assertEqual(result["status"], "invalid")
        self.assertEqual(result["failure_code"], "no_intact_json_object")

    def test_multiple_objects_are_ambiguous(self) -> None:
        result = parse_incident_report_response_v05(
            f"{self.encoded}\n{self.encoded}"
        )
        self.assertEqual(result["status"], "invalid")
        self.assertEqual(
            result["failure_code"], "ambiguous_multiple_json_objects"
        )

    def test_json_like_braces_outside_object_are_rejected(self) -> None:
        result = parse_incident_report_response_v05(
            f"ignore {{not JSON}} then {self.encoded}"
        )
        self.assertEqual(result["status"], "invalid")
        self.assertEqual(
            result["failure_code"],
            "json_like_content_outside_recovered_object",
        )

    def test_valid_non_object_json_is_rejected(self) -> None:
        result = parse_incident_report_response_v05("[]")
        self.assertEqual(result["status"], "invalid")
        self.assertEqual(result["failure_code"], "final_json_not_object")


if __name__ == "__main__":
    unittest.main()
