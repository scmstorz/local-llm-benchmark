import hashlib
import json
import subprocess
import unittest
from collections import Counter
from pathlib import Path

from local_llm_benchmark.log_incident_sweep import (
    DEFAULT_SWEEP_PLAN,
    HARNESS_IDS,
    load_log_incident_sweep_plan,
)


class FrozenLogIncidentSweepPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path.cwd().resolve()

    def test_plan_freezes_active_models_full_product_and_balanced_order(self) -> None:
        loaded = load_log_incident_sweep_plan(self.repo_root, DEFAULT_SWEEP_PLAN)
        plan = loaded["plan"]
        lifecycle = json.loads(
            (self.repo_root / "models/lifecycle.json").read_text(encoding="utf-8")
        )
        active_models = {
            item["model"]
            for item in lifecycle["models"]
            if item["include_in_default_sweeps"] is True
        }

        self.assertEqual({item["name"] for item in plan["deployments"]}, active_models)
        self.assertEqual(len(plan["deployments"]), 5)
        self.assertEqual(len(plan["cases"]), 3)
        self.assertEqual(len(plan["execution_order"]), 30)
        self.assertEqual(
            {item["harness_id"] for item in plan["harnesses"]}, set(HARNESS_IDS)
        )
        self.assertTrue(
            all(
                left["model"] != right["model"]
                for left, right in zip(
                    plan["execution_order"], plan["execution_order"][1:]
                )
            )
        )
        model_positions = Counter()
        case_positions = Counter()
        harness_positions = Counter()
        for unit in plan["execution_order"]:
            model_positions[unit["model"]] += unit["position"]
            case_positions[unit["case_id"]] += unit["position"]
            harness_positions[unit["harness_id"]] += unit["position"]
        self.assertLessEqual(max(model_positions.values()) - min(model_positions.values()), 2)
        self.assertLessEqual(max(case_positions.values()) - min(case_positions.values()), 2)
        self.assertLessEqual(
            max(harness_positions.values()) - min(harness_positions.values()), 1
        )

    def test_every_frozen_artifact_matches_the_pre_plan_commit(self) -> None:
        plan = json.loads(DEFAULT_SWEEP_PLAN.read_text(encoding="utf-8"))
        implementation_commit = plan["frozen_inputs"]["implementation_git_commit"]
        for artifact in plan["frozen_inputs"]["artifacts"]:
            blob = subprocess.run(
                ["git", "show", f"{implementation_commit}:{artifact['path']}"],
                cwd=self.repo_root,
                capture_output=True,
                check=False,
            )
            self.assertEqual(blob.returncode, 0, artifact["path"])
            self.assertEqual(
                artifact["sha256"], hashlib.sha256(blob.stdout).hexdigest()
            )


if __name__ == "__main__":
    unittest.main()
