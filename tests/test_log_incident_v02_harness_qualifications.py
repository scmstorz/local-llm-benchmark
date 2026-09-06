import json
import unittest
from pathlib import Path

from local_llm_benchmark.runner import sha256_file


QUALIFICATIONS = [
    Path("tasks/agentic/track-b/mini-log-v0.2-qualification.json"),
    Path("tasks/agentic/track-b/pi-log-v0.2-qualification.json"),
]


class LogIncidentV02HarnessQualificationTests(unittest.TestCase):
    def test_both_qualifications_are_no_inference_and_hash_complete(self) -> None:
        for path in QUALIFICATIONS:
            with self.subTest(path=path):
                qualification = json.loads(path.read_text(encoding="utf-8"))
                evidence = qualification["qualification_evidence"]
                self.assertEqual(
                    qualification["status"], "qualified_for_excluded_live_smoke"
                )
                self.assertEqual(qualification["case_count"], 3)
                self.assertEqual(evidence["live_ollama_requests"], 0)
                self.assertFalse(evidence["live_model_inference"])
                self.assertEqual(
                    evidence["reference_report_essential_checks_passed"], 42
                )
                for artifact in qualification["artifacts"]:
                    artifact_path = Path(artifact["path"])
                    self.assertTrue(artifact_path.is_file(), artifact["path"])
                    self.assertEqual(
                        sha256_file(artifact_path),
                        artifact["sha256"],
                        artifact["path"],
                    )

    def test_pi_requires_fresh_real_acceptance_before_any_live_run(self) -> None:
        qualification = json.loads(QUALIFICATIONS[1].read_text(encoding="utf-8"))
        boundary = qualification["execution_boundary"]
        evidence = qualification["seatbelt_backend_evidence"]

        self.assertTrue(boundary["per_run_real_seatbelt_acceptance_required"])
        self.assertTrue(evidence["implementation_reused_unchanged"])
        self.assertEqual(evidence["prior_real_acceptance_checks_passed"], 9)
        self.assertFalse(
            qualification["comparison_boundary"]["one_factor_causal_harness_claim_allowed"]
        )

    def test_mini_keeps_application_boundary_limitation_explicit(self) -> None:
        qualification = json.loads(QUALIFICATIONS[0].read_text(encoding="utf-8"))

        self.assertFalse(
            qualification["execution_boundary"]["portable_standalone_os_sandbox"]
        )
        self.assertFalse(
            qualification["comparison_boundary"]["v1_and_v2_results_poolable"]
        )


if __name__ == "__main__":
    unittest.main()
