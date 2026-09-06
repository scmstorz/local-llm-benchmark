import json
import unittest
from pathlib import Path

from local_llm_benchmark.runner import sha256_file


QUALIFICATION_PATH = Path(
    "tasks/coding/track-b/pi-v0.3-qualification.json"
)


class PiV03QualificationTests(unittest.TestCase):
    def test_public_record_is_no_inference_and_hash_complete(self) -> None:
        repo_root = Path.cwd().resolve()
        record = json.loads(
            (repo_root / QUALIFICATION_PATH).read_text(encoding="utf-8")
        )

        self.assertEqual(record["status"], "passed")
        self.assertEqual(record["harness_id"], "pi-v0.3")
        self.assertEqual(record["protocol_id"], "coding-track-b-v0.3")
        self.assertEqual(record["execution_boundary"]["ollama_model_requests"], 0)
        self.assertFalse(record["execution_boundary"]["candidate_code_executed"])
        self.assertTrue(
            record["settings_and_transport_evidence"][
                "stalled_loopback_provider_probe"
            ]["passed"]
        )
        self.assertEqual(
            {case["language"] for case in record["seatbelt_evidence"]["cases"]},
            {"PHP", "JavaScript", "Python"},
        )
        self.assertTrue(
            all(case["passed"] for case in record["seatbelt_evidence"]["cases"])
        )
        for artifact in record["frozen_artifact_hashes"]:
            path = repo_root / artifact["path"]
            self.assertTrue(path.is_file(), artifact["path"])
            self.assertEqual(
                sha256_file(path), artifact["sha256"], artifact["path"]
            )
        self.assertNotIn("/Users/", json.dumps(record))


if __name__ == "__main__":
    unittest.main()
