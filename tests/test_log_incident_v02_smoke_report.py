import json
import unittest
from pathlib import Path

from local_llm_benchmark.runner import sha256_file


REPORT_PATH = Path(
    "reports/agentic/log-incident-qualification-smokes-v0.2.json"
)


class LogIncidentV02SmokeReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    def test_report_binds_plan_and_preserves_both_terminal_failures(self) -> None:
        plan = self.report["plan"]
        self.assertEqual(sha256_file(Path(plan["path"])), plan["sha256"])
        units = self.report["admitted_units"]
        self.assertEqual(
            [unit["harness_id"] for unit in units],
            ["mini-log-v0.2", "pi-log-v0.2"],
        )
        self.assertTrue(all(unit["runtime_success"] for unit in units))
        self.assertTrue(all(unit["agent_termination_valid"] for unit in units))
        self.assertTrue(all(unit["verified_success"] is False for unit in units))

    def test_protocol_deviation_and_control_events_are_not_hidden(self) -> None:
        compliance = self.report["protocol_compliance"]
        self.assertFalse(compliance["strict_one_execution_attempt_compliance"])
        self.assertEqual(len(self.report["control_events"]), 2)
        self.assertTrue(
            all(
                event["admitted_as_model_outcome"] is False
                for event in self.report["control_events"]
            )
        )
        self.assertEqual(
            self.report["interpretation"]["machinery_gate"],
            "passed_with_documented_protocol_deviation",
        )

    def test_public_report_contains_no_candidate_output_or_private_path(self) -> None:
        serialized = REPORT_PATH.read_text(encoding="utf-8")
        markdown = Path(
            "reports/agentic/log-incident-qualification-smokes-v0.2.md"
        ).read_text(encoding="utf-8")
        for content in (serialized, markdown):
            self.assertNotIn("/Users/", content)
            self.assertNotIn("candidate-response", content)
            self.assertNotIn("root_cause_code", content)
        self.assertFalse(
            self.report["interpretation"]["candidate_outputs_published"]
        )


if __name__ == "__main__":
    unittest.main()
