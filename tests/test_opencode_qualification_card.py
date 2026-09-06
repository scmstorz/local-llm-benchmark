import json
import unittest
from pathlib import Path


class OpenCodeQualificationCardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[1]
        cls.card = json.loads(
            (
                cls.repo_root
                / "tasks/coding/track-b/opencode-qualification-card-v0.1.json"
            ).read_text(encoding="utf-8")
        )

    def test_card_does_not_prequalify_or_authorize_a_run(self) -> None:
        self.assertFalse(self.card["decision"]["eligible_for_measured_track_b"])
        self.assertTrue(self.card["decision"]["does_not_authorize_inference"])
        self.assertEqual(
            self.card["package_lock_candidate"]["state"],
            "selected_for_qualification_not_installed_by_project",
        )
        self.assertEqual(self.card["planned_smoke"]["status"], "not_authorized_not_frozen")

    def test_card_preserves_shared_turn_and_verifier_semantics(self) -> None:
        self.assertIsNone(self.card["candidate_harness"]["normal_turn_limit"])
        self.assertTrue(self.card["candidate_harness"]["turns_are_measurement_only"])
        outcomes = self.card["event_and_outcome_requirements"]
        self.assertTrue(outcomes["final_verifier_runs_after_harness_exit"])
        self.assertTrue(
            outcomes["runtime_success_verifier_success_and_verified_success_separate"]
        )

    def test_card_requires_no_inference_gates_before_one_excluded_smoke(self) -> None:
        sequence = self.card["qualification_sequence"]
        self.assertEqual([stage["inference"] for stage in sequence[:4]], [False] * 4)
        self.assertTrue(sequence[4]["inference"])
        self.assertEqual(self.card["planned_smoke"]["attempts"], 1)
        self.assertEqual(self.card["planned_smoke"]["retries"], 0)
        self.assertTrue(self.card["planned_smoke"]["excluded_from_measured_results"])

    def test_card_requires_hidden_model_call_accounting_and_official_sources(self) -> None:
        hidden = self.card["hidden_model_call_policy"]
        self.assertEqual(hidden["unobserved_or_unattributed_call"], "qualification_failure")
        self.assertIn("automatic compaction", hidden["specifically_audit"])
        urls = [item["url"] for item in self.card["official_source_evidence"]]
        self.assertGreaterEqual(len(urls), 5)
        self.assertTrue(all(url.startswith("https://") for url in urls))


if __name__ == "__main__":
    unittest.main()
