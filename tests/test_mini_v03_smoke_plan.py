import json
import unittest
from pathlib import Path

from local_llm_benchmark.runner import sha256_file


PLAN_PATH = Path(
    "tasks/coding/track-b/mini-qwen38-js-development-smoke-v0.3.json"
)
SUCCESSOR_PATH = Path(
    "tasks/coding/track-b/mini-qwen38-js-development-smoke-v0.3.1.json"
)


class MiniV03SmokePlanTests(unittest.TestCase):
    def test_original_plan_is_preserved_as_unexecuted_and_superseded(self) -> None:
        plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

        self.assertEqual(plan["status"], "superseded_before_execution")
        self.assertEqual(plan["harness_id"], "mini-v0.3")
        self.assertEqual(plan["evidence_class"], "excluded_development_smoke")
        self.assertEqual(plan["deployment"]["name"], "qwen3.8:27b-mlx")
        self.assertEqual(
            plan["case"]["case_id"], "coding.dev.async-cache-coalescing"
        )
        self.assertEqual(plan["comparison_rules"]["attempts"], 1)
        self.assertEqual(plan["comparison_rules"]["automatic_retries"], 0)
        self.assertTrue(
            plan["comparison_rules"]["result_excluded_from_measured_aggregates"]
        )
        self.assertTrue(plan["authorization"]["live_execution_allowed_after_resource_gate"])
        self.assertFalse(plan["supersession"]["executed_before_supersession"])
        self.assertEqual(plan["supersession"]["live_ollama_requests"], 0)

    def test_original_plan_preserves_historical_artifact_hashes(self) -> None:
        plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

        self.assertGreaterEqual(len(plan["frozen_inputs"]["artifacts"]), 20)
        for artifact in plan["frozen_inputs"]["artifacts"]:
            path = Path(artifact["path"])
            self.assertTrue(path.is_file(), artifact["path"])
            self.assertEqual(len(artifact["sha256"]), 64, artifact["path"])

        adapter = next(
            item
            for item in plan["frozen_inputs"]["artifacts"]
            if item["path"] == "local_llm_benchmark/mini_v03_adapter.py"
        )
        self.assertNotEqual(sha256_file(Path(adapter["path"])), adapter["sha256"])

    def test_successor_freezes_one_excluded_authorized_attempt(self) -> None:
        plan = json.loads(SUCCESSOR_PATH.read_text(encoding="utf-8"))

        self.assertEqual(plan["status"], "frozen_before_execution")
        self.assertEqual(plan["harness_id"], "mini-v0.3")
        self.assertEqual(plan["evidence_class"], "excluded_development_smoke")
        self.assertEqual(plan["repository_commit"], "f26fa8febe802379ba5cee6833690d5e5b1e7be3")
        self.assertEqual(plan["deployment"]["name"], "qwen3.8:27b-mlx")
        self.assertEqual(
            plan["case"]["case_id"], "coding.dev.async-cache-coalescing"
        )
        self.assertEqual(plan["comparison_rules"]["attempts"], 1)
        self.assertEqual(plan["comparison_rules"]["automatic_retries"], 0)
        self.assertTrue(
            plan["comparison_rules"]["result_excluded_from_measured_aggregates"]
        )

    def test_successor_freezes_current_artifacts(self) -> None:
        plan = json.loads(SUCCESSOR_PATH.read_text(encoding="utf-8"))

        self.assertGreaterEqual(len(plan["frozen_inputs"]["artifacts"]), 24)
        for artifact in plan["frozen_inputs"]["artifacts"]:
            path = Path(artifact["path"])
            self.assertTrue(path.is_file(), artifact["path"])
            self.assertEqual(sha256_file(path), artifact["sha256"], artifact["path"])


if __name__ == "__main__":
    unittest.main()
