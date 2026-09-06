from __future__ import annotations

import unittest
from collections import Counter
from pathlib import Path

from local_llm_benchmark.log_incident_sweep_v05 import (
    DEFAULT_SWEEP_PLAN,
    HARNESS_IDS,
    load_log_incident_sweep_plan,
)
from local_llm_benchmark.runner import load_json


REPO_ROOT = Path(__file__).resolve().parents[1]


class FrozenLogIncidentV05CapabilityPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.loaded = load_log_incident_sweep_plan(REPO_ROOT, DEFAULT_SWEEP_PLAN)
        cls.plan = cls.loaded["plan"]

    def test_exact_active_default_cohort_is_frozen(self) -> None:
        lifecycle = load_json(REPO_ROOT / "models/lifecycle.json")
        expected = [
            item["model"]
            for item in lifecycle["models"]
            if item["include_in_default_sweeps"] is True
        ]
        self.assertEqual([item["name"] for item in self.plan["deployments"]], expected)
        self.assertEqual(len(expected), 5)

    def test_order_is_complete_balanced_and_nonconsecutive(self) -> None:
        order = self.plan["execution_order"]
        self.assertEqual(len(order), 30)
        keys = {
            (item["harness_id"], item["model"], item["case_id"])
            for item in order
        }
        self.assertEqual(len(keys), 30)
        self.assertEqual(Counter(item["harness_id"] for item in order), {
            "mini-log-v0.5": 15,
            "pi-log-v0.5": 15,
        })
        self.assertTrue(
            all(left["model"] != right["model"] for left, right in zip(order, order[1:]))
        )
        model_sums = {
            model: sum(item["position"] for item in order if item["model"] == model)
            for model in self.loaded["models"]
        }
        self.assertLessEqual(max(model_sums.values()) - min(model_sums.values()), 2)

    def test_capability_not_distribution_contract_is_explicit(self) -> None:
        rules = self.plan["comparison_rules"]
        self.assertEqual(rules["runs_per_configuration"], 1)
        self.assertEqual(rules["automatic_retries"], 0)
        self.assertFalse(rules["adaptive_repetitions"])
        self.assertFalse(rules["performance_distribution_claims"])
        self.assertFalse(rules["reliability_probability_claims"])
        self.assertFalse(rules["quality_stochasticity_claims"])
        self.assertIsNone(self.plan["shared_inference"]["maximum_agent_turns"])
        self.assertIsNone(
            self.plan["shared_inference"]["maximum_total_output_tokens"]
        )

    def test_execution_permission_remains_post_freeze(self) -> None:
        self.assertFalse(self.plan["authorization"]["live_execution_authorized"])
        self.assertTrue(
            self.plan["authorization"]["fresh_clean_window_confirmation_required"]
        )
        self.assertEqual(
            self.plan["frozen_inputs"]["implementation_git_commit"],
            "2f7110e05575d44f3a1cfc4e6c479afd9cd794c0",
        )
        self.assertEqual(set(self.loaded["harnesses"]), set(HARNESS_IDS))


if __name__ == "__main__":
    unittest.main()
