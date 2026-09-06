import json
import unittest
from pathlib import Path

from local_llm_benchmark.runner import sha256_file


PLAN_PATH = Path(
    "tasks/agentic/track-b/mini-log-qwen38-development-smoke-v0.1.json"
)


class MiniLogSmokePlanTests(unittest.TestCase):
    def test_plan_freezes_one_excluded_authorized_attempt(self) -> None:
        plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

        self.assertEqual(plan["status"], "frozen_before_execution")
        self.assertEqual(plan["harness_id"], "mini-log-v0.1")
        self.assertEqual(plan["evidence_class"], "excluded_development_smoke")
        self.assertEqual(plan["repository_commit"], "4eb37bbeb7f1a8d35be79406601f268f837a910e")
        self.assertEqual(plan["deployment"]["name"], "qwen3.8:27b-mlx")
        self.assertEqual(
            plan["case"]["case_id"], "agentic.ops.checkout-pool-regression"
        )
        self.assertEqual(plan["comparison_rules"]["attempts"], 1)
        self.assertEqual(plan["comparison_rules"]["automatic_retries"], 0)
        self.assertTrue(
            plan["comparison_rules"]["result_excluded_from_measured_aggregates"]
        )
        self.assertTrue(plan["authorization"]["live_execution_allowed_after_resource_gate"])

    def test_plan_freezes_current_qualified_artifacts(self) -> None:
        plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

        qualification = Path(plan["frozen_inputs"]["qualification_path"])
        self.assertEqual(
            sha256_file(qualification), plan["frozen_inputs"]["qualification_sha256"]
        )
        self.assertGreaterEqual(len(plan["frozen_inputs"]["artifacts"]), 24)
        for artifact in plan["frozen_inputs"]["artifacts"]:
            path = Path(artifact["path"])
            self.assertTrue(path.is_file(), artifact["path"])
            self.assertEqual(sha256_file(path), artifact["sha256"], artifact["path"])


if __name__ == "__main__":
    unittest.main()
