from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = REPO_ROOT / "reports/agentic/multi-format-qwen38-confirmation-v0.1.json"
AUDIT_PATH = (
    REPO_ROOT
    / "reports/agentic/multi-format-qwen38-confirmation-v0.1-quality-audit.json"
)


class MultiFormatConfirmationQualityAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        self.audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))

    def test_audit_is_bound_to_the_terminal_public_report(self) -> None:
        source = self.audit["source_report"]
        self.assertEqual(source["path"], REPORT_PATH.relative_to(REPO_ROOT).as_posix())
        self.assertEqual(
            source["sha256"], hashlib.sha256(REPORT_PATH.read_bytes()).hexdigest()
        )
        self.assertEqual(source["study_id"], self.report["study_id"])
        self.assertEqual(
            source["study_record_sha256"], self.report["study_record_sha256"]
        )
        self.assertEqual(source["planned_cell_count"], self.report["cell_count"])

    def test_every_position_has_one_review_decision(self) -> None:
        judgments = self.audit["judgments"]
        self.assertEqual([item["position"] for item in judgments], list(range(1, 10)))
        by_decision = {
            name: [
                item["position"]
                for item in judgments
                if item["free_text_decision"] == name
            ]
            for name in ("pass", "fail")
        }
        self.assertEqual(by_decision["pass"], self.audit["positions"]["pass"])
        self.assertEqual(by_decision["fail"], self.audit["positions"]["fail"])
        self.assertEqual(self.audit["positions"]["not_applicable"], [])

    def test_summary_and_combined_acceptance_reconcile(self) -> None:
        pass_positions = set(self.audit["positions"]["pass"])
        deterministic = {
            cell["position"]
            for cell in self.report["cells"]
            if cell["outcome"]["semantic_verified_success"]
        }
        strict = {
            cell["position"]
            for cell in self.report["cells"]
            if cell["outcome"]["strict_transport_compliance"]
        }
        self.assertEqual(
            sorted(deterministic & pass_positions),
            self.audit["positions"]["combined_deterministic_and_free_text_accepted"],
        )
        self.assertEqual(
            sorted(deterministic & pass_positions & strict),
            self.audit["positions"][
                "combined_deterministic_free_text_and_strict_transport_accepted"
            ],
        )
        summary = self.audit["summary"]
        self.assertEqual(summary["free_text_pass"], 6)
        self.assertEqual(summary["deterministic_and_free_text_accepted"], 5)
        self.assertEqual(
            summary["deterministic_free_text_and_strict_transport_accepted"], 3
        )

    def test_public_audit_excludes_private_candidate_material(self) -> None:
        serialized = json.dumps(self.audit, ensure_ascii=False)
        self.assertNotIn("candidate-report.json", serialized)
        self.assertNotIn(str(REPO_ROOT), serialized)
        self.assertNotIn('"executive_summary":', serialized)
        self.assertEqual(len(self.audit["aggregate_findings"]), 3)


if __name__ == "__main__":
    unittest.main()
