import json
import unittest
from pathlib import Path

from local_llm_benchmark.runner import sha256_file


QUALIFICATION_PATH = Path(
    "tasks/agentic/track-b/pi-log-v0.1-qualification.json"
)


class PiLogQualificationTests(unittest.TestCase):
    def test_qualification_is_no_inference_and_hash_complete(self) -> None:
        qualification = json.loads(QUALIFICATION_PATH.read_text(encoding="utf-8"))
        evidence = qualification["qualification_evidence"]

        self.assertEqual(qualification["harness_id"], "pi-log-v0.1")
        self.assertEqual(
            qualification["status"], "qualified_for_excluded_live_smoke"
        )
        self.assertFalse(evidence["live_model_inference"])
        self.assertEqual(evidence["live_ollama_requests"], 0)
        self.assertEqual(evidence["real_seatbelt_acceptance_checks_passed"], 9)
        self.assertEqual(evidence["real_seatbelt_acceptance_checks_total"], 9)
        for artifact in qualification["artifacts"]:
            path = Path(artifact["path"])
            self.assertTrue(path.is_file(), artifact["path"])
            self.assertEqual(sha256_file(path), artifact["sha256"], artifact["path"])

    def test_qualification_keeps_security_and_comparison_limits_explicit(self) -> None:
        qualification = json.loads(QUALIFICATION_PATH.read_text(encoding="utf-8"))
        boundary = qualification["execution_boundary"]
        observation = qualification["control_layer_observation"]

        self.assertEqual(qualification["tool_surface"], ["read"])
        self.assertFalse(boundary["candidate_workspace_writable"])
        self.assertFalse(boundary["shell_processes_allowed"])
        self.assertEqual(boundary["network_allowlist"], ["localhost:11434"])
        self.assertFalse(
            qualification["comparison_boundary"][
                "one_factor_causal_harness_claim_allowed"
            ]
        )
        self.assertFalse(observation["benchmark_outcome"])
        self.assertEqual(observation["inference_requests_made_across_both_attempts"], 0)


if __name__ == "__main__":
    unittest.main()
