import hashlib
import json
import subprocess
import unittest
from pathlib import Path


PLAN_PATH = Path(
    "tasks/coding/track-b/async-cache-qwen38-development-smokes-v0.2.json"
)


class TrackBV02DevelopmentSmokePlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path.cwd().resolve()

    def test_plan_is_frozen_excluded_turn_unlimited_and_hash_complete(self) -> None:
        plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        self.assertEqual(plan["status"], "frozen_before_execution")
        self.assertEqual(plan["evidence_class"], "excluded_development_smoke")
        self.assertEqual(plan["execution_order"], ["mini-v0.2", "pi-v0.2"])
        self.assertEqual([item["attempts"] for item in plan["attempts"]], [1, 1])
        self.assertIsNone(plan["shared_inference"]["normal_agent_turn_limit"])
        self.assertTrue(plan["shared_inference"]["agent_turns_are_measurement_only"])
        self.assertEqual(plan["failure_policy"]["automatic_retries"], 0)
        self.assertFalse(plan["failure_policy"]["adaptive_repetitions"])
        self.assertEqual(
            plan["deployment"]["digest"],
            "5642e97495e1a088883805981563dcdc4a040c2f53388b7a41d1f24d3622cf7e",
        )

        paths = {
            "case_file_sha256": "tasks/coding/dev/async-cache-coalescing/case.json",
            "fixture_manifest_file_sha256": "tasks/coding/dev/async-cache-coalescing/fixture-manifest.json",
            "task_file_sha256": "tasks/coding/dev/async-cache-coalescing/TASK.md",
            "benchmark_card_file_sha256": "tasks/coding/dev/async-cache-coalescing/benchmark-card.json",
            "public_test_file_sha256": "tasks/coding/dev/async-cache-coalescing/fixture/tests/cache.test.mjs",
            "hidden_test_file_sha256": "tasks/coding/dev/async-cache-coalescing/verifier/hidden_tests.mjs",
            "fixture_package_file_sha256": "tasks/coding/dev/async-cache-coalescing/fixture/package.json",
            "protocol_file_sha256": "tasks/coding/track-b/track-b-v0.2.json",
            "mini_harness_file_sha256": "tasks/coding/track-b/mini-v0.2.json",
            "pi_harness_file_sha256": "tasks/coding/track-b/pi-v0.2.json",
            "mini_system_prompt_file_sha256": "tasks/coding/track-b/prompts/mini-system-v0.2.txt",
            "pi_system_prompt_file_sha256": "tasks/coding/track-b/prompts/pi-system-v0.1.txt",
            "mini_action_schema_file_sha256": "tasks/coding/track-b/schemas/mini-action-v0.2.json",
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
