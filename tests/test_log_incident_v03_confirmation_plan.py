from __future__ import annotations

import itertools
import subprocess
import unittest
from pathlib import Path

from local_llm_benchmark.runner import load_json, sha256_file


REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = Path(
    "tasks/agentic/track-b/log-incident-v0.3-confirmation-plan.json"
)


class LogIncidentV03ConfirmationPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = load_json(REPO_ROOT / PLAN_PATH)

    def test_plan_is_frozen_but_not_authorized_for_execution(self) -> None:
        self.assertEqual(self.plan["status"], "frozen_before_execution")
        self.assertEqual(self.plan["evidence_class"], "excluded_specification_confirmation")
        self.assertFalse(self.plan["authorization"]["live_execution_authorized"])
        self.assertTrue(
            self.plan["authorization"]["fresh_clean_window_confirmation_required"]
        )
        self.assertTrue(self.plan["resource_gate"]["behat_must_not_be_running"])

    def test_plan_contains_exact_two_by_three_single_attempt_matrix(self) -> None:
        harnesses = {item["harness_id"] for item in self.plan["harnesses"]}
        cases = {item["case_id"] for item in self.plan["cases"]}
        expected = set(itertools.product(harnesses, cases))
        observed = {
            (item["harness_id"], item["case_id"])
            for item in self.plan["execution_order"]
        }
        self.assertEqual(observed, expected)
        self.assertEqual(
            [item["position"] for item in self.plan["execution_order"]],
            list(range(1, 7)),
        )
        self.assertEqual(self.plan["execution_rules"]["runs_per_system_case"], 1)
        self.assertEqual(self.plan["execution_rules"]["automatic_retries"], 0)
        self.assertEqual(self.plan["deployment"]["name"], "qwen3.8:27b-mlx")

    def test_primary_and_transport_outcomes_are_separate(self) -> None:
        outcomes = self.plan["outcome_model"]
        self.assertEqual(outcomes["primary"], "semantic_verified_success")
        self.assertEqual(outcomes["secondary"], "strict_transport_compliance")
        self.assertFalse(outcomes["composite_score"])
        self.assertIsNone(
            self.plan["confirmation_interpretation"]["quantitative_success_threshold"]
        )

    def test_frozen_commit_and_artifact_hashes_exist(self) -> None:
        commit = self.plan["frozen_inputs"]["implementation_git_commit"]
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0)
        source = REPO_ROOT / self.plan["frozen_inputs"][
            "deployment_identity_source_path"
        ]
        self.assertEqual(
            sha256_file(source),
            self.plan["frozen_inputs"]["deployment_identity_source_sha256"],
        )
        for artifact in self.plan["frozen_inputs"]["artifacts"]:
            with self.subTest(artifact=artifact["path"]):
                self.assertEqual(
                    sha256_file(REPO_ROOT / artifact["path"]), artifact["sha256"]
                )


if __name__ == "__main__":
    unittest.main()
