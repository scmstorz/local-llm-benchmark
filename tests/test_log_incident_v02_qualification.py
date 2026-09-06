import json
import unittest
from pathlib import Path

from local_llm_benchmark.runner import sha256_file


QUALIFICATION_PATH = Path(
    "tasks/agentic/log-incident-analysis/log-incident-v0.2-offline-qualification.json"
)


class LogIncidentV02QualificationTests(unittest.TestCase):
    def test_qualification_is_no_inference_and_hash_complete(self) -> None:
        qualification = json.loads(QUALIFICATION_PATH.read_text(encoding="utf-8"))
        evidence = qualification["qualification_evidence"]

        self.assertEqual(
            qualification["status"],
            "qualified_for_harness_adaptation_and_excluded_smokes",
        )
        self.assertFalse(evidence["live_model_inference"])
        self.assertEqual(evidence["live_ollama_requests"], 0)
        self.assertEqual(evidence["focused_python_tests_passed"], 19)
        self.assertEqual(len(evidence["deliberate_near_misses_rejected"]), 18)
        for case_result in evidence["reference_reports"].values():
            self.assertEqual(case_result["essential_checks_passed"], 14)
            self.assertEqual(case_result["essential_checks_total"], 14)
        for artifact in qualification["artifacts"]:
            path = Path(artifact["path"])
            self.assertTrue(path.is_file(), artifact["path"])
            self.assertEqual(sha256_file(path), artifact["sha256"], artifact["path"])

    def test_qualification_preserves_v01_and_requires_smokes(self) -> None:
        qualification = json.loads(QUALIFICATION_PATH.read_text(encoding="utf-8"))

        self.assertFalse(qualification["frozen_v0_1_boundary"]["modified"])
        self.assertIn("excluded smoke", qualification["next_gate"])
        self.assertEqual(
            qualification["report_contract"]["recovery_states"],
            ["full", "partial", "not_observed"],
        )


if __name__ == "__main__":
    unittest.main()
