from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = REPO_ROOT / "reports/agentic/multi-format-capability-sweep-v0.1.json"
AUDIT_PATH = (
    REPO_ROOT
    / "reports/agentic/multi-format-capability-sweep-v0.1-quality-audit.json"
)


class MultiFormatQualityAuditTests(unittest.TestCase):
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
        self.assertEqual(source["planned_cell_count"], self.report["cell_count"])

    def test_every_position_has_exactly_one_review_classification(self) -> None:
        reviews = self.audit["reviews"]
        self.assertEqual([item["position"] for item in reviews], list(range(1, 16)))
        by_class = {
            name: [
                item["position"]
                for item in reviews
                if item["classification"] == name
            ]
            for name in ("pass", "fail", "not_applicable")
        }
        self.assertEqual(
            by_class,
            {
                name: self.audit["positions"][name]
                for name in ("pass", "fail", "not_applicable")
            },
        )

    def test_summary_and_combined_acceptance_reconcile(self) -> None:
        reviews = self.audit["reviews"]
        counts = {
            name: sum(item["classification"] == name for item in reviews)
            for name in ("pass", "fail", "not_applicable")
        }
        summary = self.audit["summary"]
        self.assertEqual(counts["pass"], summary["free_text_pass"])
        self.assertEqual(counts["fail"], summary["free_text_fail"])
        self.assertEqual(
            counts["not_applicable"], summary["free_text_not_applicable"]
        )
        deterministic = {
            cell["position"]
            for cell in self.report["cells"]
            if cell["outcome"]["semantic_verified_success"]
        }
        prose = {
            item["position"]
            for item in reviews
            if item["classification"] == "pass"
        }
        self.assertEqual(
            sorted(deterministic & prose),
            self.audit["positions"]["combined_deterministic_and_free_text_accepted"],
        )

    def test_public_audit_excludes_private_candidate_material(self) -> None:
        serialized = json.dumps(self.audit, ensure_ascii=False)
        self.assertNotIn("candidate-report.json", serialized)
        self.assertNotIn(str(REPO_ROOT), serialized)
        self.assertNotIn("executive_summary\":", serialized)
        self.assertEqual(len(self.audit["findings"]), 6)


if __name__ == "__main__":
    unittest.main()
