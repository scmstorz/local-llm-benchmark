import copy
import json
import unittest
from pathlib import Path

from local_llm_benchmark.log_incident_v02 import (
    load_log_incident_case_v02,
    verify_incident_report_v02,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = Path(
    "tasks/agentic/log-incident-analysis/checkout-pool-regression/case-v2.json"
)


class CheckoutLogIncidentV02Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.loaded = load_log_incident_case_v02(REPO_ROOT, CASE_PATH)
        self.reference = json.loads(
            self.loaded["reference_report_path"].read_text(encoding="utf-8")
        )

    def assert_failed_check(self, candidate: dict, check_id: str) -> None:
        result = verify_incident_report_v02(REPO_ROOT, CASE_PATH, candidate)
        self.assertFalse(result["verified_success"])
        self.assertIn(
            check_id,
            {item["check_id"] for item in result["checks"] if not item["passed"]},
        )

    def test_reference_passes_all_fourteen_checks(self) -> None:
        result = verify_incident_report_v02(REPO_ROOT, CASE_PATH, self.reference)
        self.assertTrue(result["verified_success"])
        self.assertEqual(result["essential_pass_count"], 14)

    def test_v2_requires_full_recovery_state(self) -> None:
        candidate = copy.deepcopy(self.reference)
        candidate["incident"]["recovery_status"] = "partial"
        self.assert_failed_check(candidate, "recovery_status")

    def test_v2_still_rejects_traffic_as_root_cause(self) -> None:
        candidate = copy.deepcopy(self.reference)
        candidate["diagnosis"]["root_cause_code"] = "capacity_exhaustion"
        self.assert_failed_check(candidate, "root_cause")

    def test_v2_still_requires_database_counter_evidence(self) -> None:
        candidate = copy.deepcopy(self.reference)
        candidate["rejected_hypotheses"] = candidate["rejected_hypotheses"][1:]
        self.assert_failed_check(candidate, "distractor_rejection")

    def test_v1_reference_shape_is_not_accepted_as_v2(self) -> None:
        v1 = json.loads(
            (
                REPO_ROOT
                / "tasks/agentic/log-incident-analysis/checkout-pool-regression/reference/reference-report.json"
            ).read_text(encoding="utf-8")
        )
        result = verify_incident_report_v02(REPO_ROOT, CASE_PATH, v1)
        self.assertFalse(result["verified_success"])
        self.assertEqual(result["failure_code"], "report_schema_failed")


if __name__ == "__main__":
    unittest.main()
