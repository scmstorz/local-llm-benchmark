import json
import unittest
from pathlib import Path

from local_llm_benchmark.runner import sha256_file


QUALIFICATION_PATH = Path(
    "tasks/coding/track-b/mini-v0.3-qualification.json"
)


class MiniV03QualificationTests(unittest.TestCase):
    def test_qualification_is_no_inference_and_hash_complete(self) -> None:
        qualification = json.loads(QUALIFICATION_PATH.read_text(encoding="utf-8"))

        self.assertEqual(qualification["harness_id"], "mini-v0.3")
        self.assertEqual(
            qualification["status"], "qualified_for_excluded_live_smoke"
        )
        self.assertFalse(
            qualification["qualification_evidence"]["live_model_inference"]
        )
        self.assertEqual(
            qualification["qualification_evidence"]["live_ollama_requests"], 0
        )
        for artifact in qualification["artifacts"]:
            path = Path(artifact["path"])
            self.assertTrue(path.is_file(), artifact["path"])
            self.assertEqual(sha256_file(path), artifact["sha256"], artifact["path"])

    def test_qualification_preserves_system_level_comparison_limit(self) -> None:
        qualification = json.loads(QUALIFICATION_PATH.read_text(encoding="utf-8"))

        self.assertFalse(
            qualification["comparison_boundary"][
                "one_factor_causal_harness_claim_allowed"
            ]
        )
        self.assertTrue(
            qualification["execution_boundary"][
                "action_and_finalize_commands_require_surrounding_sandbox"
            ]
        )


if __name__ == "__main__":
    unittest.main()
