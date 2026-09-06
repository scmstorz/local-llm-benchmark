import json
import unittest
from pathlib import Path

from local_llm_benchmark.mini_v03_sweep import load_mini_v03_sweep_plan
from local_llm_benchmark.runner import sha256_file


PLAN_PATH = Path("tasks/coding/track-b/mini-capability-sweep-v0.3.json")
PI_PLAN_PATH = Path("tasks/coding/track-b/pi-capability-sweep-v0.3.json")


class MiniV03SweepPlanTests(unittest.TestCase):
    def test_plan_is_full_five_by_three_capability_screen(self) -> None:
        loaded = load_mini_v03_sweep_plan(Path.cwd().resolve(), PLAN_PATH)
        plan = loaded["plan"]

        self.assertEqual(plan["status"], "frozen_before_execution")
        self.assertEqual(len(plan["deployments"]), 5)
        self.assertEqual(len(plan["cases"]), 3)
        self.assertEqual(len(plan["execution_order"]), 15)
        self.assertEqual(plan["comparison_rules"]["runs_per_configuration"], 1)
        self.assertEqual(plan["comparison_rules"]["automatic_retries"], 0)
        self.assertFalse(plan["comparison_rules"]["performance_distribution_claims"])

    def test_plan_matches_pi_cell_order_but_not_harness_identity(self) -> None:
        mini = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        pi = json.loads(PI_PLAN_PATH.read_text(encoding="utf-8"))

        self.assertEqual(mini["execution_order"], pi["execution_order"])
        self.assertEqual(mini["deployments"], [
            {key: value for key, value in deployment.items() if key != "native_tools_advertised" and key != "compatibility_note"}
            for deployment in pi["deployments"]
        ])
        self.assertNotEqual(mini["harness_id"], pi["harness_id"])
        self.assertTrue(
            mini["comparison_rules"]["pi_comparison_is_system_level_not_one_factor_causal"]
        )

    def test_smoke_gate_is_passed_but_smoke_is_not_reused(self) -> None:
        plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        smoke = plan["smoke_gate"]

        self.assertTrue(smoke["passed"])
        self.assertFalse(smoke["verified_success_required"])
        self.assertFalse(smoke["result_reused_in_measured_cohort"])
        self.assertEqual(sha256_file(Path(smoke["report_path"])), smoke["report_sha256"])

    def test_every_frozen_artifact_matches(self) -> None:
        plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

        self.assertGreaterEqual(len(plan["frozen_inputs"]["artifacts"]), 30)
        for artifact in plan["frozen_inputs"]["artifacts"]:
            path = Path(artifact["path"])
            self.assertTrue(path.is_file(), artifact["path"])
            self.assertEqual(sha256_file(path), artifact["sha256"], artifact["path"])


if __name__ == "__main__":
    unittest.main()
