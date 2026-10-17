from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from local_llm_benchmark.multi_format_smokes import (
    DEFAULT_PAIR_PLAN,
    load_multi_format_smoke_pair,
    run_multi_format_preflight,
)
from local_llm_benchmark.runner import RunnerError, load_json, sha256_file


REPO_ROOT = Path(__file__).resolve().parents[1]
QUALIFICATIONS = [
    REPO_ROOT / "tasks/agentic/track-b/multi-format-artifact-api-v0.1-qualification.json",
    REPO_ROOT / "tasks/agentic/track-b/mini-multi-format-v0.1-qualification.json",
    REPO_ROOT / "tasks/agentic/track-b/pi-multi-format-v0.1-qualification.json",
]


class MultiFormatHarnessQualificationTests(unittest.TestCase):
    def test_qualifications_are_no_inference_and_hash_complete(self) -> None:
        for path in QUALIFICATIONS:
            with self.subTest(path=path):
                qualification = load_json(path)
                self.assertFalse(qualification["live_model_inference"])
                self.assertEqual(qualification["live_ollama_requests"], 0)
                for artifact in qualification["artifacts"]:
                    self.assertEqual(
                        sha256_file(REPO_ROOT / artifact["path"]),
                        artifact["sha256"],
                        artifact["path"],
                    )

    def test_pi_qualification_defers_fresh_real_seatbelt_to_each_smoke(self) -> None:
        qualification = load_json(QUALIFICATIONS[2])
        self.assertTrue(
            qualification["execution_boundary"][
                "fresh_real_seatbelt_acceptance_required_before_each_live_run"
            ]
        )
        self.assertEqual(
            qualification["execution_boundary"]["network_allowlist"],
            ["localhost:11434"],
        )

    def test_pair_is_frozen_mini_then_pi_and_excluded(self) -> None:
        loaded = load_multi_format_smoke_pair(REPO_ROOT, DEFAULT_PAIR_PLAN)
        plan = loaded["plan"]
        self.assertEqual(
            [item["harness_id"] for item in plan["execution_order"]],
            ["mini-multi-format-v0.1", "pi-multi-format-v0.1"],
        )
        self.assertFalse(plan["comparison_rules"]["measured_capability_evidence"])
        self.assertFalse(plan["comparison_rules"]["one_factor_causal_harness_claim_allowed"])

    def test_preflight_stops_before_constructing_ollama_client_without_confirmation(self) -> None:
        with self.assertRaisesRegex(RunnerError, "fresh exclusive-window"):
            run_multi_format_preflight(REPO_ROOT, DEFAULT_PAIR_PLAN)


if __name__ == "__main__":
    unittest.main()
