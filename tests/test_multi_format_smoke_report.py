from __future__ import annotations

import unittest
from pathlib import Path

from local_llm_benchmark.runner import load_json, sha256_file


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT = REPO_ROOT / "reports/agentic/multi-format-qualification-smokes-v0.1.json"


class MultiFormatSmokeReportTests(unittest.TestCase):
    def test_report_preserves_versioned_outcomes_and_final_successes(self) -> None:
        report = load_json(REPORT)
        outcomes = {item["system_id"]: item for item in report["outcomes"]}
        self.assertEqual(
            report["accepted_complete_systems"],
            ["mini-multi-format-v0.1", "pi-multi-format-v0.3"],
        )
        self.assertTrue(outcomes["mini-multi-format-v0.1"]["semantic_verified_success"])
        self.assertTrue(outcomes["mini-multi-format-v0.1"]["strict_transport_compliance"])
        self.assertEqual(outcomes["pi-multi-format-v0.1"]["inference_requests_made"], 0)
        self.assertEqual(outcomes["pi-multi-format-v0.2"]["agent_turns"], 0)
        self.assertTrue(outcomes["pi-multi-format-v0.3"]["semantic_verified_success"])
        self.assertFalse(outcomes["pi-multi-format-v0.3"]["strict_transport_compliance"])
        self.assertEqual(
            outcomes["pi-multi-format-v0.3"]["response_normalization_kind"],
            "surrounding_text",
        )
        self.assertTrue(report["resource_control"]["postflight_passed"])
        self.assertFalse(
            report["qualification_conclusion"]["measured_execution_authorized"]
        )

    def test_every_source_plan_hash_is_current(self) -> None:
        plans = {
            "multi-format-qualification-smokes-v0.1":
                "tasks/agentic/track-b/multi-format-qualification-smokes-v0.1.json",
            "pi-multi-format-qwen38-development-smoke-v0.2":
                "tasks/agentic/track-b/pi-multi-format-qwen38-development-smoke-v0.2.json",
            "pi-multi-format-qwen38-development-smoke-v0.3":
                "tasks/agentic/track-b/pi-multi-format-qwen38-development-smoke-v0.3.json",
        }
        report = load_json(REPORT)
        for item in report["source_plans"]:
            with self.subTest(plan_id=item["plan_id"]):
                self.assertEqual(
                    sha256_file(REPO_ROOT / plans[item["plan_id"]]),
                    item["sha256"],
                )


if __name__ == "__main__":
    unittest.main()
