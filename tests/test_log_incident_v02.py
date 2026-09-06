import copy
import json
import tempfile
import unittest
from pathlib import Path

from local_llm_benchmark.log_incident_v02 import (
    load_log_incident_case_v02,
    verify_incident_report_v02,
)


RETRY_CASE = Path(
    "tasks/agentic/log-incident-analysis/retry-queue-amplification/case.json"
)
CLOCK_CASE = Path(
    "tasks/agentic/log-incident-analysis/clock-skew-partial-recovery/case.json"
)


class LogIncidentV02Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path.cwd().resolve()
        self.loaded = {
            path: load_log_incident_case_v02(self.repo_root, path)
            for path in (RETRY_CASE, CLOCK_CASE)
        }
        self.references = {
            path: json.loads(
                loaded["reference_report_path"].read_text(encoding="utf-8")
            )
            for path, loaded in self.loaded.items()
        }

    def verify(self, case_path: Path, report: dict) -> dict:
        return verify_incident_report_v02(self.repo_root, case_path, report)

    def assert_failed_check(self, result: dict, check_id: str) -> None:
        self.assertFalse(result["verified_success"])
        self.assertIn(
            check_id,
            {item["check_id"] for item in result["checks"] if not item["passed"]},
        )

    def test_both_references_pass_all_essential_checks(self) -> None:
        for case_path, reference in self.references.items():
            with self.subTest(case=case_path):
                result = self.verify(case_path, reference)
                self.assertTrue(result["verified_success"])
                self.assertEqual(result["essential_check_count"], 14)
                self.assertEqual(result["essential_pass_count"], 14)

    def test_retry_trigger_is_not_accepted_as_root_cause(self) -> None:
        candidate = copy.deepcopy(self.references[RETRY_CASE])
        candidate["diagnosis"]["root_cause_code"] = "dependency_outage"
        self.assert_failed_check(self.verify(RETRY_CASE, candidate), "root_cause")

    def test_retry_chain_without_amplification_event_fails(self) -> None:
        candidate = copy.deepcopy(self.references[RETRY_CASE])
        candidate["causal_chain"] = [
            item for item in candidate["causal_chain"] if item["event_id"] != "WRK-106"
        ]
        self.assert_failed_check(self.verify(RETRY_CASE, candidate), "causal_chain")

    def test_retry_missing_amplification_evidence_fails(self) -> None:
        candidate = copy.deepcopy(self.references[RETRY_CASE])
        candidate["evidence"] = [
            item for item in candidate["evidence"] if item["event_id"] != "BRK-301"
        ]
        self.assert_failed_check(self.verify(RETRY_CASE, candidate), "critical_evidence")

    def test_retry_broker_distractor_must_be_rejected(self) -> None:
        candidate = copy.deepcopy(self.references[RETRY_CASE])
        candidate["rejected_hypotheses"] = [
            item
            for item in candidate["rejected_hypotheses"]
            if item["code"] != "message_broker_outage"
        ]
        self.assert_failed_check(self.verify(RETRY_CASE, candidate), "distractor_rejection")

    def test_retry_test_tenant_error_must_be_rejected(self) -> None:
        candidate = copy.deepcopy(self.references[RETRY_CASE])
        candidate["rejected_hypotheses"] = [
            item
            for item in candidate["rejected_hypotheses"]
            if item["code"] != "notification_tls_failure"
        ]
        self.assert_failed_check(self.verify(RETRY_CASE, candidate), "distractor_rejection")

    def test_retry_premature_recovery_status_fails(self) -> None:
        candidate = copy.deepcopy(self.references[RETRY_CASE])
        candidate["incident"]["recovery_status"] = "partial"
        self.assert_failed_check(self.verify(RETRY_CASE, candidate), "recovery_status")

    def test_retry_unsupported_order_loss_fails(self) -> None:
        candidate = copy.deepcopy(self.references[RETRY_CASE])
        candidate["impact"]["codes"].append("orders_lost")
        self.assert_failed_check(self.verify(RETRY_CASE, candidate), "bounded_impact")

    def test_clock_naive_chronology_fails(self) -> None:
        candidate = copy.deepcopy(self.references[CLOCK_CASE])
        candidate["causal_chain"] = list(reversed(candidate["causal_chain"]))
        self.assert_failed_check(self.verify(CLOCK_CASE, candidate), "causal_chain")

    def test_clock_provider_is_not_accepted_as_root_cause(self) -> None:
        candidate = copy.deepcopy(self.references[CLOCK_CASE])
        candidate["diagnosis"]["root_cause_code"] = "provider_outage"
        self.assert_failed_check(self.verify(CLOCK_CASE, candidate), "root_cause")

    def test_clock_wrong_event_file_fails(self) -> None:
        candidate = copy.deepcopy(self.references[CLOCK_CASE])
        candidate["evidence"][0]["file"] = "logs/provider.jsonl"
        self.assert_failed_check(self.verify(CLOCK_CASE, candidate), "citation_integrity")

    def test_clock_offset_evidence_is_required(self) -> None:
        candidate = copy.deepcopy(self.references[CLOCK_CASE])
        candidate["evidence"] = [
            item for item in candidate["evidence"] if item["event_id"] != "TIME-101"
        ]
        self.assert_failed_check(self.verify(CLOCK_CASE, candidate), "critical_evidence")

    def test_clock_full_recovery_status_fails(self) -> None:
        candidate = copy.deepcopy(self.references[CLOCK_CASE])
        candidate["incident"]["recovery_status"] = "full"
        self.assert_failed_check(self.verify(CLOCK_CASE, candidate), "recovery_status")

    def test_clock_full_recovery_claim_fails(self) -> None:
        candidate = copy.deepcopy(self.references[CLOCK_CASE])
        candidate["impact"]["summary"] += " Full recovery was confirmed."
        self.assert_failed_check(self.verify(CLOCK_CASE, candidate), "unsupported_claims")

    def test_clock_remaining_backlog_is_required_impact(self) -> None:
        candidate = copy.deepcopy(self.references[CLOCK_CASE])
        candidate["impact"]["codes"].remove("reconciliation_backlog_remaining")
        self.assert_failed_check(self.verify(CLOCK_CASE, candidate), "bounded_impact")

    def test_clock_backlog_completion_uncertainty_is_required(self) -> None:
        candidate = copy.deepcopy(self.references[CLOCK_CASE])
        candidate["uncertainties"] = [
            item
            for item in candidate["uncertainties"]
            if item["code"] != "backlog_full_recovery_time_unknown"
        ]
        self.assert_failed_check(self.verify(CLOCK_CASE, candidate), "uncertainty")

    def test_extra_top_level_field_fails_strict_schema(self) -> None:
        candidate = copy.deepcopy(self.references[RETRY_CASE])
        candidate["confidence"] = 0.9
        result = self.verify(RETRY_CASE, candidate)
        self.assertFalse(result["verified_success"])
        self.assertEqual(result["failure_code"], "report_schema_failed")

    def test_nested_wrong_type_is_a_schema_failure(self) -> None:
        candidate = copy.deepcopy(self.references[CLOCK_CASE])
        candidate["incident"]["recovery_status"] = ["partial"]
        result = self.verify(CLOCK_CASE, candidate)
        self.assertFalse(result["verified_success"])
        self.assertEqual(result["failure_code"], "report_schema_failed")

    def test_fixture_drift_is_rejected(self) -> None:
        loaded = self.loaded[RETRY_CASE]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture_root = root / "fixture"
            fixture_root.mkdir()
            manifest_path = root / "manifest.json"
            case_path = root / "case.json"
            case = copy.deepcopy(loaded["case"])
            case["fixture"]["root"] = str(fixture_root)
            case["fixture"]["manifest_path"] = str(manifest_path)
            manifest_path.write_text(json.dumps(loaded["manifest"]), encoding="utf-8")
            case_path.write_text(json.dumps(case), encoding="utf-8")

            with self.assertRaisesRegex(Exception, "inventory differs"):
                load_log_incident_case_v02(self.repo_root, case_path)


if __name__ == "__main__":
    unittest.main()
