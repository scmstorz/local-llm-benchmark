import json
import unittest
from pathlib import Path


REPORT_PATH = Path(
    "reports/coding/track-b-pi-capability-sweep-v0.3.json"
)


class PiV03ReportTests(unittest.TestCase):
    def test_public_report_preserves_outcome_and_termination_distinctions(self) -> None:
        report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

        self.assertEqual(report["report_id"], "track-b-pi-capability-sweep-v0.3")
        self.assertEqual(report["summary"]["run_count"], 15)
        self.assertEqual(report["summary"]["verified_success_count"], 9)
        self.assertEqual(report["summary"]["verifier_success_count"], 10)
        self.assertEqual(
            {
                item["model"]: item["verified_success_count"]
                for item in report["by_model"]
            },
            {
                "qwen3.6:35b-a3b-mxfp8": 1,
                "qwen3.8:27b-mlx": 3,
                "muse-glimmer:30b-mlx": 1,
                "ornith-1.5:35b": 2,
                "gemma4:31b-mlx": 2,
            },
        )
        discrepancy = report["diagnostics"][
            "termination_precedence_discrepancies"
        ]
        self.assertEqual(len(discrepancy), 1)
        self.assertEqual(
            discrepancy[0]["trajectory_termination_reason"],
            "emergency_operation_safeguard_exceeded",
        )
        verifier_only = report["diagnostics"][
            "verifier_success_without_verified_success"
        ]
        self.assertEqual(len(verifier_only), 1)
        self.assertEqual(verifier_only[0]["model"], "ornith-1.5:35b")

    def test_public_report_contains_no_private_paths_or_raw_outputs(self) -> None:
        report_text = REPORT_PATH.read_text(encoding="utf-8")
        report = json.loads(report_text)

        self.assertNotIn("/Users/", report_text)
        self.assertFalse(report["privacy"]["raw_model_text_included"])
        self.assertFalse(report["privacy"]["candidate_source_included"])
        self.assertFalse(report["privacy"]["test_stdout_or_stderr_included"])
        self.assertTrue(
            all("stdout" not in unit and "stderr" not in unit for unit in report["units"])
        )


if __name__ == "__main__":
    unittest.main()
