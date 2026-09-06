import copy
import json
import tempfile
import unittest
from pathlib import Path

from local_llm_benchmark.log_incident import (
    DEFAULT_CASE_PATH,
    load_log_incident_case,
    verify_incident_report,
)


class LogIncidentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path.cwd().resolve()
        self.loaded = load_log_incident_case(self.repo_root, DEFAULT_CASE_PATH)
        self.reference = json.loads(
            self.loaded["reference_report_path"].read_text(encoding="utf-8")
        )

    def verify(self, report: dict) -> dict:
        return verify_incident_report(self.repo_root, DEFAULT_CASE_PATH, report)

    def test_reference_passes_every_essential_check(self) -> None:
        result = self.verify(self.reference)

        self.assertTrue(result["verified_success"])
        self.assertEqual(result["essential_check_count"], 13)
        self.assertEqual(result["essential_pass_count"], 13)

    def test_wrong_timezone_boundary_fails(self) -> None:
        candidate = copy.deepcopy(self.reference)
        candidate["incident"]["start_utc"] = "2026-09-05T10:17:06Z"

        result = self.verify(candidate)

        self.assertFalse(result["verified_success"])
        failed = {item["check_id"] for item in result["checks"] if not item["passed"]}
        self.assertEqual(failed, {"incident_window_utc"})

    def test_traffic_trigger_is_not_accepted_as_root_cause(self) -> None:
        candidate = copy.deepcopy(self.reference)
        candidate["diagnosis"]["root_cause_code"] = "capacity_exhaustion"

        result = self.verify(candidate)

        self.assertFalse(result["verified_success"])
        self.assertIn(
            "root_cause",
            {item["check_id"] for item in result["checks"] if not item["passed"]},
        )

    def test_wrong_event_file_fails_citation_integrity(self) -> None:
        candidate = copy.deepcopy(self.reference)
        candidate["evidence"][0]["file"] = "logs/postgres.log"

        result = self.verify(candidate)

        self.assertFalse(result["verified_success"])
        self.assertIn(
            "citation_integrity",
            {item["check_id"] for item in result["checks"] if not item["passed"]},
        )

    def test_missing_recovery_chain_fails(self) -> None:
        candidate = copy.deepcopy(self.reference)
        candidate["causal_chain"] = candidate["causal_chain"][:-3]

        result = self.verify(candidate)

        self.assertFalse(result["verified_success"])
        self.assertIn(
            "causal_chain",
            {item["check_id"] for item in result["checks"] if not item["passed"]},
        )

    def test_database_outage_overclaim_fails(self) -> None:
        candidate = copy.deepcopy(self.reference)
        candidate["diagnosis"]["summary"] += " A database outage caused the incident."

        result = self.verify(candidate)

        self.assertFalse(result["verified_success"])
        self.assertIn(
            "unsupported_claims",
            {item["check_id"] for item in result["checks"] if not item["passed"]},
        )

    def test_missing_uncertainty_fails(self) -> None:
        candidate = copy.deepcopy(self.reference)
        candidate["uncertainties"] = candidate["uncertainties"][:1]

        result = self.verify(candidate)

        self.assertFalse(result["verified_success"])
        self.assertIn(
            "uncertainty",
            {item["check_id"] for item in result["checks"] if not item["passed"]},
        )

    def test_extra_top_level_field_fails_strict_schema(self) -> None:
        candidate = copy.deepcopy(self.reference)
        candidate["confidence"] = 0.9

        result = self.verify(candidate)

        self.assertFalse(result["verified_success"])
        self.assertEqual(result["failure_code"], "report_schema_failed")

    def test_nested_wrong_type_is_a_schema_failure_not_a_verifier_crash(self) -> None:
        candidate = copy.deepcopy(self.reference)
        candidate["recommended_actions"][0]["code"] = ["not", "a", "string"]

        result = self.verify(candidate)

        self.assertFalse(result["verified_success"])
        self.assertEqual(result["failure_code"], "report_schema_failed")

    def test_fixture_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = copy.deepcopy(self.loaded["case"])
            fixture_root = root / "fixture"
            fixture_root.mkdir()
            manifest_path = root / "manifest.json"
            case_path = root / "case.json"
            case["fixture"]["root"] = str(fixture_root)
            case["fixture"]["manifest_path"] = str(manifest_path)
            manifest_path.write_text(
                json.dumps(self.loaded["manifest"]), encoding="utf-8"
            )
            case_path.write_text(json.dumps(case), encoding="utf-8")

            with self.assertRaisesRegex(Exception, "inventory differs"):
                load_log_incident_case(self.repo_root, case_path)


if __name__ == "__main__":
    unittest.main()
