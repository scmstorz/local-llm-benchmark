import hashlib
import json
import unittest
from pathlib import Path


REPORT_PATH = Path("reports/coding/coding-track-a-v0.1.json")


class CodingTrackAReportTests(unittest.TestCase):
    def test_report_preserves_source_hashes_and_evidence_boundaries(self) -> None:
        report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

        self.assertEqual(report["report_id"], "coding-track-a-v0.1")
        self.assertEqual(report["scope"]["task_count"], 3)
        self.assertEqual(report["scope"]["deployment_count"], 5)
        self.assertEqual(report["scope"]["core_inference_attempts"], 15)

        for source in report["source_reports"]:
            payload = Path(source["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), source["sha256"])

        primary = {
            item["case_id"]: item for item in report["primary_frozen_outcomes"]
        }
        self.assertEqual(
            primary["coding.dev.pagination-cycle-guard"]["verified_successes"],
            3,
        )
        self.assertEqual(
            primary["coding.dev.pagination-cycle-guard"]
            ["known_later_false_positives"],
            1,
        )
        self.assertEqual(
            primary["coding.dev.async-cache-coalescing"]["verified_successes"],
            0,
        )
        self.assertEqual(
            primary["coding.dev.php-payment-result-migration"]
            ["strict_verified_successes"],
            0,
        )

        best_known = {
            item["case_id"]: item
            for item in report["best_known_requirement_evidence"]
        }
        self.assertFalse(
            best_known["coding.dev.pagination-cycle-guard"]
            ["formal_fresh_comparison"]
        )
        self.assertTrue(
            best_known["coding.dev.async-cache-coalescing"]
            ["formal_fresh_comparison"]
        )
        self.assertFalse(
            best_known["coding.dev.php-payment-result-migration"]
            ["formal_fresh_comparison"]
        )

        aggregate = report["aggregate"]
        self.assertEqual(aggregate["primary_frozen_successes_across_15_attempts"], 3)
        self.assertEqual(
            aggregate["primary_frozen_successes_known_valid_after_all_audits"],
            2,
        )
        self.assertEqual(
            aggregate["best_known_verifier_confirmed_task_outcomes_across_15_attempts"],
            5,
        )
        self.assertEqual(aggregate["models_solving_all_three_tasks"], 0)


if __name__ == "__main__":
    unittest.main()
