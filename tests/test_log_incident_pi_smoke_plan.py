import json
import subprocess
import unittest
from pathlib import Path

from local_llm_benchmark.log_incident_smokes import load_excluded_smoke_plan
from local_llm_benchmark.runner import sha256_file


PLAN_PATH = Path(
    "tasks/agentic/track-b/pi-log-qwen38-development-smoke-v0.1.json"
)


class PiLogSmokePlanTests(unittest.TestCase):
    def test_plan_freezes_one_excluded_no_retry_attempt(self) -> None:
        repo_root = Path.cwd().resolve()
        loaded = load_excluded_smoke_plan(repo_root, PLAN_PATH, "pi-log-v0.1")
        plan = loaded["plan"]

        self.assertEqual(plan["deployment"]["name"], "qwen3.8:27b-mlx")
        self.assertEqual(plan["comparison_rules"]["attempts"], 1)
        self.assertEqual(plan["comparison_rules"]["automatic_retries"], 0)
        self.assertTrue(
            plan["comparison_rules"]["result_excluded_from_measured_aggregates"]
        )
        self.assertFalse(plan["execution_boundary"]["candidate_workspace_writable"])

    def test_plan_binds_qualification_artifacts_and_existing_commit(self) -> None:
        repo_root = Path.cwd().resolve()
        plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        qualification = Path(plan["frozen_inputs"]["qualification_path"])

        self.assertEqual(
            sha256_file(qualification), plan["frozen_inputs"]["qualification_sha256"]
        )
        self.assertGreaterEqual(len(plan["frozen_inputs"]["artifacts"]), 25)
        completed = subprocess.run(
            ["git", "cat-file", "-e", f"{plan['repository_commit']}^{{commit}}"],
            cwd=repo_root,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0)


if __name__ == "__main__":
    unittest.main()
