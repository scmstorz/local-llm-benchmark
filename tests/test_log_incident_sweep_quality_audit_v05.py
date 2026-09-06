import hashlib
import json
import unittest
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = (
    REPO_ROOT / "reports/agentic/log-incident-capability-sweep-v0.5.json"
)
AUDIT_PATH = (
    REPO_ROOT
    / "reports/agentic/log-incident-capability-sweep-v0.5-quality-audit.json"
)


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


class LogIncidentSweepQualityAuditV05Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = load_json(REPORT_PATH)
        cls.audit = load_json(AUDIT_PATH)
        cls.units_by_position = {
            unit["position"]: unit for unit in cls.report["units"]
        }

    def test_audit_is_bound_to_exact_public_report(self) -> None:
        digest = hashlib.sha256(REPORT_PATH.read_bytes()).hexdigest()
        self.assertEqual(self.audit["source_report"]["sha256"], digest)
        self.assertEqual(
            self.audit["source_report"]["planned_cell_count"],
            self.report["summary"]["run_count"],
        )

    def test_review_positions_partition_all_measured_cells(self) -> None:
        positions = self.audit["positions"]
        pass_positions = set(positions["pass"])
        fail_positions = set(positions["fail"])
        not_applicable = set(positions["not_applicable"])

        self.assertFalse(pass_positions & fail_positions)
        self.assertFalse(pass_positions & not_applicable)
        self.assertFalse(fail_positions & not_applicable)
        self.assertEqual(
            pass_positions | fail_positions | not_applicable,
            set(self.units_by_position),
        )
        self.assertTrue(
            all(self.units_by_position[p]["runtime_success"] for p in pass_positions)
        )
        self.assertTrue(
            all(self.units_by_position[p]["runtime_success"] for p in fail_positions)
        )
        self.assertTrue(
            all(
                not self.units_by_position[p]["runtime_success"]
                for p in not_applicable
            )
        )

    def test_summary_and_combined_acceptance_match_positions(self) -> None:
        summary = self.audit["summary"]
        positions = self.audit["positions"]
        self.assertEqual(summary["free_text_pass"], len(positions["pass"]))
        self.assertEqual(summary["free_text_fail"], len(positions["fail"]))
        self.assertEqual(
            summary["free_text_not_applicable"], len(positions["not_applicable"])
        )
        combined = sum(
            self.units_by_position[position]["semantic_verified_success"]
            for position in positions["pass"]
        )
        self.assertEqual(summary["deterministic_and_free_text_accepted"], combined)

    def test_findings_match_failed_positions_and_public_identities(self) -> None:
        findings = self.audit["findings"]
        self.assertEqual(
            {finding["position"] for finding in findings},
            set(self.audit["positions"]["fail"]),
        )
        for finding in findings:
            unit = self.units_by_position[finding["position"]]
            self.assertEqual(finding["model"], unit["model"])
            self.assertEqual(finding["harness_id"], unit["harness_id"])
            self.assertEqual(finding["case_id"], unit["case_id"])

    def test_published_aggregates_match_position_decisions(self) -> None:
        dispositions = {}
        for disposition, positions in self.audit["positions"].items():
            for position in positions:
                dispositions[position] = disposition

        for field, audit_key in (
            ("harness_id", "by_harness"),
            ("model", "by_model"),
            ("case_id", "by_case"),
        ):
            expected = {}
            for position, unit in self.units_by_position.items():
                key = unit[field]
                counts = expected.setdefault(key, Counter())
                counts[dispositions[position]] += 1
                if dispositions[position] != "not_applicable":
                    counts["applicable"] += 1

            for item in self.audit[audit_key]:
                key = item[field]
                self.assertEqual(item["pass"], expected[key]["pass"])
                self.assertEqual(item["fail"], expected[key]["fail"])
                self.assertEqual(
                    item["not_applicable"], expected[key]["not_applicable"]
                )
                self.assertEqual(item["applicable"], expected[key]["applicable"])

    def test_public_audit_contains_no_private_absolute_path(self) -> None:
        serialized = json.dumps(self.audit, sort_keys=True)
        self.assertNotIn("/Users/", serialized)
        self.assertNotIn("results/agentic-runs/", serialized)


if __name__ == "__main__":
    unittest.main()
