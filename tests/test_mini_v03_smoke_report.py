import json
import unittest
from pathlib import Path


REPORT_PATH = Path(
    "reports/coding/track-b-mini-qwen38-js-development-smoke-v0.3.1.json"
)


class MiniV03SmokeReportTests(unittest.TestCase):
    def test_smoke_is_complete_excluded_and_technically_usable(self) -> None:
        report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

        self.assertEqual(report["evidence_class"], "excluded_development_smoke")
        self.assertEqual(report["status"], "complete")
        self.assertFalse(report["outcome"]["verified_success"])
        self.assertEqual(report["outcome"]["failure_type"], "hidden_tests_failed")
        self.assertEqual(report["outcome"]["public_test_count"], 4)
        self.assertEqual(report["outcome"]["hidden_checks_passed"], 6)
        self.assertEqual(report["outcome"]["hidden_check_count"], 8)
        self.assertTrue(report["technical_gate"]["passed"])
        self.assertTrue(report["technical_gate"]["measured_sweep_may_be_planned"])

    def test_public_smoke_report_contains_no_private_payload(self) -> None:
        text = REPORT_PATH.read_text(encoding="utf-8")
        report = json.loads(text)

        self.assertNotIn("/Users/", text)
        self.assertFalse(report["privacy"]["raw_model_text_included"])
        self.assertFalse(report["privacy"]["candidate_source_included"])
        self.assertFalse(report["privacy"]["test_stdout_or_stderr_included"])
        self.assertFalse(report["privacy"]["absolute_local_paths_included"])


if __name__ == "__main__":
    unittest.main()
