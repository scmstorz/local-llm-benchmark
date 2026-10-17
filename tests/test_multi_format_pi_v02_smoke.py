from __future__ import annotations

import unittest
from pathlib import Path

from local_llm_benchmark.multi_format_smokes_v02 import (
    DEFAULT_PLAN,
    load_pi_multi_format_v02_smoke,
    run_preflight,
)
from local_llm_benchmark.runner import RunnerError


REPO_ROOT = Path(__file__).resolve().parents[1]


class PiMultiFormatV02SmokeTests(unittest.TestCase):
    def test_plan_is_one_excluded_new_system_attempt(self) -> None:
        plan = load_pi_multi_format_v02_smoke(REPO_ROOT)["plan"]
        self.assertEqual(plan["harness_id"], "pi-multi-format-v0.2")
        self.assertEqual(plan["comparison_rules"]["attempts"], 1)
        self.assertEqual(plan["comparison_rules"]["automatic_retries"], 0)
        self.assertFalse(plan["comparison_rules"]["completed_mini_smoke_repeated"])
        self.assertEqual(plan["predecessor_outcome"]["inference_requests_made"], 0)

    def test_preflight_refuses_to_construct_client_without_confirmation(self) -> None:
        with self.assertRaisesRegex(RunnerError, "fresh window"):
            run_preflight(REPO_ROOT, DEFAULT_PLAN)


if __name__ == "__main__":
    unittest.main()
