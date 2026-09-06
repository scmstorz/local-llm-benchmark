import json
import re
import unittest
from pathlib import Path

from local_llm_benchmark.runner import sha256_file


PAIR_PATH = Path(
    "tasks/agentic/track-b/log-incident-qualification-smokes-v0.2.json"
)


class LogIncidentV02SmokePlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.pair = json.loads(PAIR_PATH.read_text(encoding="utf-8"))

    def test_pair_is_one_excluded_attempt_per_system(self) -> None:
        self.assertEqual(self.pair["status"], "frozen_before_execution")
        self.assertEqual(
            [item["harness_id"] for item in self.pair["execution_order"]],
            ["mini-log-v0.2", "pi-log-v0.2"],
        )
        rules = self.pair["comparison_rules"]
        self.assertTrue(rules["one_attempt_per_complete_system"])
        self.assertEqual(rules["automatic_retries"], 0)
        self.assertFalse(rules["measured_capability_evidence"])
        self.assertFalse(rules["one_factor_causal_harness_claim_allowed"])

    def test_pair_uses_same_exact_deployment_and_new_case(self) -> None:
        identities = set()
        for unit in self.pair["execution_order"]:
            path = Path(unit["smoke_plan_path"])
            self.assertEqual(sha256_file(path), unit["smoke_plan_sha256"])
            smoke = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(smoke["comparison_rules"]["attempts"], 1)
            self.assertEqual(smoke["comparison_rules"]["automatic_retries"], 0)
            identities.add(
                (
                    smoke["deployment"]["name"],
                    smoke["deployment"]["digest"],
                    smoke["runtime"]["version"],
                    smoke["case"]["case_id"],
                    smoke["case"]["case_version"],
                )
            )
        self.assertEqual(len(identities), 1)
        identity = identities.pop()
        self.assertEqual(identity[0], "qwen3.8:27b-mlx")
        self.assertEqual(identity[3], "agentic.ops.retry-queue-amplification")

    def test_every_frozen_artifact_and_qualification_is_hash_complete(self) -> None:
        plans = [self.pair]
        plans.extend(
            json.loads(Path(unit["smoke_plan_path"]).read_text(encoding="utf-8"))
            for unit in self.pair["execution_order"]
        )
        for plan in plans:
            for artifact in plan["frozen_inputs"]["artifacts"]:
                path = Path(artifact["path"])
                self.assertTrue(path.is_file(), artifact["path"])
                self.assertEqual(sha256_file(path), artifact["sha256"])
            qualification_path = plan["frozen_inputs"].get("qualification_path")
            if qualification_path:
                self.assertEqual(
                    sha256_file(Path(qualification_path)),
                    plan["frozen_inputs"]["qualification_sha256"],
                )

    def test_resource_and_pi_sandbox_gates_are_predeclared(self) -> None:
        gate = self.pair["resource_gate"]
        self.assertEqual(gate["empty_state_observation_seconds"], 30)
        self.assertEqual(gate["process_snapshots_before_each_system"], 2)
        self.assertTrue(gate["postflight_loaded_models_must_be_empty"])
        for rule in gate["blocking_process_rules"]:
            re.compile(rule["pattern"])
        self.assertTrue(
            self.pair["execution_protocol"][
                "fresh_real_seatbelt_acceptance_before_pi_run"
            ]
        )


if __name__ == "__main__":
    unittest.main()
