import hashlib
import json
import subprocess
import unittest
from pathlib import Path

PLAN_PATH = Path(
    "tasks/coding/track-b/php-ornith-development-smokes-v0.1.json"
)


class TrackBDevelopmentSmokePlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path.cwd().resolve()

    def test_plan_is_frozen_excluded_and_hash_complete(self) -> None:
        plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        self.assertEqual(plan["status"], "frozen_before_execution")
        self.assertEqual(plan["evidence_class"], "excluded_development_smoke")
        self.assertEqual(plan["execution_order"], ["mini-v0.1", "pi-v0.1"])
        self.assertEqual([item["attempts"] for item in plan["attempts"]], [1, 1])
        self.assertTrue(
            plan["reporting"]["exclude_from_future_measured_track_b_aggregates"]
        )
        self.assertFalse(plan["failure_policy"]["adaptive_repetitions"])
        self.assertEqual(plan["failure_policy"]["automatic_retries"], 0)

        paths = {
            "case_file_sha256": "tasks/coding/dev/php-payment-result-migration/case.json",
            "fixture_manifest_file_sha256": "tasks/coding/dev/php-payment-result-migration/fixture-manifest.json",
            "task_file_sha256": "tasks/coding/dev/php-payment-result-migration/TASK.md",
            "benchmark_card_file_sha256": "tasks/coding/dev/php-payment-result-migration/benchmark-card.json",
            "hidden_test_file_sha256": "tasks/coding/dev/php-payment-result-migration/verifier/hidden_tests.php",
            "protocol_file_sha256": "tasks/coding/track-b/track-b-v0.1.json",
            "mini_harness_file_sha256": "tasks/coding/track-b/mini-v0.1.json",
            "pi_harness_file_sha256": "tasks/coding/track-b/pi-v0.1.json",
            "mini_system_prompt_file_sha256": "tasks/coding/track-b/prompts/mini-system-v0.1.txt",
            "pi_system_prompt_file_sha256": "tasks/coding/track-b/prompts/pi-system-v0.1.txt",
            "mini_runner_file_sha256": "local_llm_benchmark/agentic.py",
            "pi_adapter_file_sha256": "local_llm_benchmark/pi_adapter.py",
            "macos_sandbox_file_sha256": "local_llm_benchmark/macos_sandbox.py",
            "cli_file_sha256": "local_llm_benchmark/cli.py",
            "pi_policy_extension_file_sha256": "integrations/pi/benchmark-policy.mjs",
            "pi_package_lock_file_sha256": "integrations/pi/package-lock.json",
        }
        frozen = plan["frozen_inputs"]
        commit = frozen["harness_git_commit"]
        completed = subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=self.repo_root,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0)
        for key, relative_path in paths.items():
            blob = subprocess.run(
                ["git", "show", f"{commit}:{relative_path}"],
                cwd=self.repo_root,
                capture_output=True,
                check=False,
            )
            self.assertEqual(blob.returncode, 0, relative_path)
            self.assertEqual(frozen[key], hashlib.sha256(blob.stdout).hexdigest())


if __name__ == "__main__":
    unittest.main()
