from __future__ import annotations

import unittest
from pathlib import Path

from local_llm_benchmark.runner import load_json, sha256_file


REPO_ROOT = Path(__file__).resolve().parents[1]
QUALIFICATIONS = [
    Path(
        "tasks/agentic/log-incident-analysis/"
        "log-incident-v0.4-offline-qualification.json"
    ),
    Path("tasks/agentic/track-b/mini-log-v0.4-qualification.json"),
    Path("tasks/agentic/track-b/pi-log-v0.4-qualification.json"),
]


class LogIncidentV04QualificationTests(unittest.TestCase):
    def test_every_frozen_artifact_hash_matches(self) -> None:
        for qualification_path in QUALIFICATIONS:
            qualification = load_json(REPO_ROOT / qualification_path)
            for artifact in qualification["artifacts"]:
                with self.subTest(
                    qualification=qualification_path, artifact=artifact["path"]
                ):
                    self.assertEqual(
                        sha256_file(REPO_ROOT / artifact["path"]),
                        artifact["sha256"],
                    )

    def test_qualifications_record_zero_live_inference(self) -> None:
        for qualification_path in QUALIFICATIONS:
            qualification = load_json(REPO_ROOT / qualification_path)
            evidence = qualification["qualification_evidence"]
            self.assertEqual(evidence["live_ollama_requests"], 0)
            self.assertFalse(evidence["live_model_inference"])

    def test_harness_qualifications_share_protocol_and_outcome_boundary(self) -> None:
        mini = load_json(REPO_ROOT / QUALIFICATIONS[1])
        pi = load_json(REPO_ROOT / QUALIFICATIONS[2])
        self.assertEqual(mini["protocol_id"], "agentic-log-incident-v0.4")
        self.assertEqual(pi["protocol_id"], mini["protocol_id"])
        self.assertFalse(
            mini["comparison_boundary"]["prior_representation_results_poolable"]
        )
        self.assertFalse(
            pi["comparison_boundary"]["prior_representation_results_poolable"]
        )
        self.assertFalse(mini["comparison_boundary"]["strict_transport_is_primary"])
        self.assertFalse(pi["comparison_boundary"]["strict_transport_is_primary"])


if __name__ == "__main__":
    unittest.main()
