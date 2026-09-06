import json
import unittest
from pathlib import Path

from local_llm_benchmark.runner import sha256_file


QUALIFICATION_PATH = Path(
    "tasks/agentic/track-b/mini-log-v0.1-qualification.json"
)


class MiniLogQualificationTests(unittest.TestCase):
    def test_qualification_is_no_inference_and_hash_complete(self) -> None:
        qualification = json.loads(QUALIFICATION_PATH.read_text(encoding="utf-8"))
        evidence = qualification["qualification_evidence"]

        self.assertEqual(qualification["harness_id"], "mini-log-v0.1")
        self.assertEqual(
            qualification["status"], "qualified_for_excluded_live_smoke"
        )
        self.assertFalse(evidence["live_model_inference"])
        self.assertEqual(evidence["live_ollama_requests"], 0)
        self.assertEqual(evidence["reference_report_essential_checks_passed"], 13)
        for artifact in qualification["artifacts"]:
            path = Path(artifact["path"])
            self.assertTrue(path.is_file(), artifact["path"])
            self.assertEqual(sha256_file(path), artifact["sha256"], artifact["path"])

    def test_qualification_keeps_capability_and_comparison_limits_explicit(self) -> None:
        qualification = json.loads(QUALIFICATION_PATH.read_text(encoding="utf-8"))

        self.assertEqual(qualification["tool_surface"], ["read_file", "finish_report"])
        self.assertFalse(
            qualification["comparison_boundary"][
                "one_factor_causal_harness_claim_allowed"
            ]
        )
        self.assertFalse(
            qualification["execution_boundary"]["portable_standalone_os_sandbox"]
        )


if __name__ == "__main__":
    unittest.main()
