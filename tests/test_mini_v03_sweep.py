import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from local_llm_benchmark.mini_v03_sweep import (
    MiniV03SweepConfig,
    advance_mini_v03_sweep,
    call_mini_v03_sweep_model,
    cleanup_mini_v03_sweep_unit,
    load_mini_v03_sweep_plan,
    start_mini_v03_sweep,
)
from local_llm_benchmark.runner import sha256_file
from tests.test_mini_v03_adapter import action_stream, configure_client


HARNESS = Path("tasks/coding/track-b/mini-v0.3.json")
PHP_CASE = Path("tasks/coding/dev/php-payment-result-migration/case.json")


class MiniV03SweepTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path.cwd().resolve()

    def _plan(self, directory: Path) -> Path:
        artifacts = [
            HARNESS,
            Path("tasks/coding/track-b/track-b-mini-v0.3.json"),
            Path("tasks/coding/track-b/prompts/mini-system-v0.3.txt"),
            Path("tasks/coding/track-b/schemas/mini-action-v0.3.json"),
            Path("local_llm_benchmark/mini_v03_adapter.py"),
            PHP_CASE,
        ]
        plan = {
            "schema_version": "1.0.0",
            "plan_id": "test-mini-v03-sweep",
            "status": "frozen_before_execution",
            "track": "B",
            "harness_id": "mini-v0.3",
            "harness_path": HARNESS.as_posix(),
            "evidence_class": "measured_capability_sweep",
            "runtime": {"name": "ollama", "version": "test"},
            "deployments": [
                {
                    "name": "test-model:latest",
                    "deployment_id": "test-deployment",
                    "digest": "d" * 64,
                }
            ],
            "cases": [
                {
                    "case_id": "coding.dev.php-payment-result-migration",
                    "case_path": PHP_CASE.as_posix(),
                    "language": "php",
                }
            ],
            "execution_order": [
                {
                    "position": 1,
                    "model": "test-model:latest",
                    "case_id": "coding.dev.php-payment-result-migration",
                }
            ],
            "comparison_rules": {
                "runs_per_configuration": 1,
                "automatic_retries": 0,
                "performance_distribution_claims": False,
            },
            "smoke_gate": {"passed": True},
            "resource_gate": {"empty_state_observation_seconds": 0},
            "frozen_inputs": {
                "artifacts": [
                    {"path": path.as_posix(), "sha256": sha256_file(path)}
                    for path in artifacts
                ]
            },
        }
        path = directory / "plan.json"
        path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def _gate_client() -> MagicMock:
        client = MagicMock()
        client.version.return_value = {"version": "test"}
        client.list_models.return_value = {
            "models": [
                {"name": "test-model:latest", "digest": "d" * 64, "size": 1}
            ]
        }
        client.list_running_models.return_value = {"models": []}
        client.unload_model.return_value = {}
        return client

    def test_plan_loader_and_stepwise_controller_complete_one_unit(self) -> None:
        results_root = self.repo_root / "results"
        results_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=results_root) as temporary:
            root = Path(temporary)
            plan_path = self._plan(root)
            loaded = load_mini_v03_sweep_plan(self.repo_root, plan_path)
            self.assertEqual(len(loaded["plan"]["execution_order"]), 1)

            started = start_mini_v03_sweep(
                self.repo_root,
                MiniV03SweepConfig(
                    plan_path=plan_path,
                    results_dir=root / "sweeps",
                    agent_results_dir=root / "runs",
                ),
            )
            sweep_dir = Path(started["sweep_dir"])
            self.assertEqual(started["waiting"]["unit_status"], "awaiting_model")

            with patch(
                "local_llm_benchmark.mini_v03_adapter.OllamaClient"
            ) as client_type:
                configure_client(
                    client_type.return_value,
                    [action_stream({"action": "finish", "summary": "done"})],
                )
                called = call_mini_v03_sweep_model(
                    self.repo_root,
                    sweep_dir,
                    client=self._gate_client(),
                )
            self.assertEqual(called["waiting"]["unit_status"], "awaiting_action")

            advanced = advance_mini_v03_sweep(self.repo_root, sweep_dir)
            self.assertEqual(
                advanced["waiting"]["unit_status"], "complete_needs_cleanup"
            )
            completed = cleanup_mini_v03_sweep_unit(
                self.repo_root,
                sweep_dir,
                client=self._gate_client(),
            )
            self.assertEqual(completed["status"], "complete")
            self.assertEqual(completed["complete_unit_count"], 1)
            self.assertEqual(completed["verified_success_count"], 0)

    def test_interrupted_model_call_is_preserved_and_restarted_fresh(self) -> None:
        results_root = self.repo_root / "results"
        results_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=results_root) as temporary:
            root = Path(temporary)
            started = start_mini_v03_sweep(
                self.repo_root,
                MiniV03SweepConfig(
                    plan_path=self._plan(root),
                    results_dir=root / "sweeps",
                    agent_results_dir=root / "runs",
                ),
            )
            sweep_dir = Path(started["sweep_dir"])
            sweep_path = sweep_dir / "sweep.json"
            sweep = json.loads(sweep_path.read_text(encoding="utf-8"))
            original_run_id = sweep["units"][0]["run_id"]
            run_path = self.repo_root / sweep["units"][0]["run_dir"] / "run.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["state"] = "model_call_running"
            run["active_model_request"] = {"request_index": 1}
            run_path.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")

            resumed = advance_mini_v03_sweep(self.repo_root, sweep_dir)
            sweep = json.loads(sweep_path.read_text(encoding="utf-8"))
            unit = sweep["units"][0]
            self.assertEqual(resumed["waiting"]["unit_status"], "awaiting_model")
            self.assertNotEqual(unit["run_id"], original_run_id)
            self.assertEqual(unit["interrupted_attempts"][0]["run_id"], original_run_id)


if __name__ == "__main__":
    unittest.main()
