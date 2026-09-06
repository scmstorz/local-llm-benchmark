import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_llm_benchmark.pi_sweep import (
    PiSweepConfig,
    _reconcile_unit,
    load_pi_sweep_plan,
    start_pi_sweep,
)
from local_llm_benchmark.runner import sha256_file


MODEL_NAME = "model:a"
MODEL_DIGEST = "a" * 64
CASE_ID = "coding.dev.async-cache-coalescing"
CASE_PATH = "tasks/coding/dev/async-cache-coalescing/case.json"


class FakeOllamaClient:
    def __init__(self) -> None:
        self.unloaded: list[str] = []

    def version(self) -> dict:
        return {"version": "0.32.15"}

    def list_models(self) -> dict:
        return {
            "models": [
                {"name": MODEL_NAME, "digest": MODEL_DIGEST, "size": 123}
            ]
        }

    def list_running_models(self) -> dict:
        return {"models": []}

    def unload_model(self, model: str) -> dict:
        self.unloaded.append(model)
        return {"done": True}


class PiSweepTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path.cwd().resolve()

    def _write_plan(self, directory: Path) -> Path:
        artifacts = [
            "tasks/coding/track-b/track-b-v0.2.json",
            "tasks/coding/track-b/pi-v0.2.json",
            CASE_PATH,
        ]
        plan = {
            "schema_version": "1.0.0",
            "plan_id": "test-pi-sweep",
            "status": "frozen_before_execution",
            "track": "B",
            "harness_id": "pi-v0.2",
            "harness_path": "tasks/coding/track-b/pi-v0.2.json",
            "evidence_class": "measured_capability_sweep",
            "runtime": {"name": "ollama", "version": "0.32.15"},
            "frozen_inputs": {
                "artifacts": [
                    {"path": path, "sha256": sha256_file(self.repo_root / path)}
                    for path in artifacts
                ]
            },
            "deployments": [
                {
                    "name": MODEL_NAME,
                    "digest": MODEL_DIGEST,
                    "deployment_id": "model-a-deployment",
                }
            ],
            "cases": [{"case_id": CASE_ID, "case_path": CASE_PATH}],
            "execution_order": [
                {"position": 1, "model": MODEL_NAME, "case_id": CASE_ID}
            ],
            "comparison_rules": {
                "runs_per_configuration": 1,
                "automatic_retries": 0,
                "performance_distribution_claims": False,
            },
            "resource_gate": {"empty_state_observation_seconds": 0},
        }
        path = directory / "plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        return path

    def test_plan_requires_one_complete_cartesian_execution_order(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.repo_root / "results") as temporary:
            plan_path = self._write_plan(Path(temporary))
            loaded = load_pi_sweep_plan(
                self.repo_root, plan_path.relative_to(self.repo_root)
            )

        self.assertEqual(list(loaded["models"]), [MODEL_NAME])
        self.assertEqual(list(loaded["cases"]), [CASE_ID])

    def test_tracked_eight_model_plan_is_frozen_and_hash_complete(self) -> None:
        plan_path = Path(
            "tasks/coding/track-b/pi-capability-sweep-v0.1.json"
        )
        plan = json.loads(
            (self.repo_root / plan_path).read_text(encoding="utf-8")
        )
        catalog = json.loads(
            (self.repo_root / "models/catalog.json").read_text(encoding="utf-8")
        )

        self.assertEqual(len(plan["deployments"]), 8)
        self.assertEqual(len(plan["cases"]), 2)
        self.assertEqual(len(plan["execution_order"]), 16)
        self.assertTrue(
            {item["name"] for item in plan["deployments"]}
            <= {item["requested_name"] for item in catalog["deployments"]}
        )
        self.assertTrue(plan["comparison_rules"]["development_smokes_reused"] is False)
        self.assertEqual(plan["comparison_rules"]["runs_per_configuration"], 1)
        self.assertEqual(plan["resource_gate"]["empty_state_observation_seconds"], 30)

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

    def test_post_crash_v02_plan_restarts_the_full_runtime_cohort(self) -> None:
        plan_path = Path(
            "tasks/coding/track-b/pi-capability-sweep-v0.2.json"
        )
        loaded = load_pi_sweep_plan(self.repo_root, plan_path)
        plan = loaded["plan"]

        self.assertEqual(plan["runtime"]["version"], "0.33.2")
        self.assertEqual(plan["prior_partial_sweep"]["complete_units"], 8)
        self.assertFalse(plan["prior_partial_sweep"]["reuse_in_v0.2"])
        self.assertEqual(len(plan["deployments"]), 8)
        self.assertEqual(len(plan["execution_order"]), 16)
        self.assertTrue(
            all(
                item["deployment_id"].endswith("-ollama-0-33-2")
                for item in plan["deployments"]
            )
        )

    def test_sweep_checkpoints_a_complete_verified_unit(self) -> None:
        client = FakeOllamaClient()
        with tempfile.TemporaryDirectory(dir=self.repo_root / "results") as temporary:
            root = Path(temporary)
            plan_path = self._write_plan(root)
            agent_root = root / "agent-runs"

            def prepare(*_args: object, **_kwargs: object) -> dict:
                run_dir = agent_root / "pi-agentic-run-test"
                run_dir.mkdir(parents=True)
                (run_dir / "run.json").write_text(
                    json.dumps({"state": "prepared_not_executed"}),
                    encoding="utf-8",
                )
                return {
                    "run_id": "pi-agentic-run-test",
                    "run_dir": str(run_dir),
                }

            def execute(_repo: Path, run_dir: Path) -> dict:
                (run_dir / "run.json").write_text(
                    json.dumps({"state": "execution_complete_verification_pending"}),
                    encoding="utf-8",
                )
                return {
                    "runtime_success": True,
                    "agent_termination_valid": True,
                    "termination_reason": "agent_end",
                    "trajectory": {"agent_turns": 4},
                }

            def finalize(_repo: Path, run_dir: Path) -> dict:
                trajectory = {"agent_turns": 4, "tool_calls": 3}
                (run_dir / "run.json").write_text(
                    json.dumps(
                        {
                            "state": "complete",
                            "outcome": {"verified_success": True},
                            "trajectory": trajectory,
                        }
                    ),
                    encoding="utf-8",
                )
                return {
                    "runtime_success": True,
                    "agent_termination_valid": True,
                    "verifier_success": True,
                    "verified_success": True,
                    "failure_category": None,
                    "failure_type": None,
                    "public_tests": {"passed": True},
                    "hidden_tests": {"passed": True},
                }

            with (
                patch(
                    "local_llm_benchmark.pi_sweep.prepare_pi_agent_run",
                    side_effect=prepare,
                ),
                patch(
                    "local_llm_benchmark.pi_sweep.validate_pi_seatbelt",
                    return_value={
                        "passed": True,
                        "validated_at": "2026-09-03T00:00:00Z",
                        "profile_sha256": "b" * 64,
                        "hidden_verifier_sha256": "c" * 64,
                    },
                ),
                patch(
                    "local_llm_benchmark.pi_sweep.execute_pi_agent_run",
                    side_effect=execute,
                ),
                patch(
                    "local_llm_benchmark.pi_sweep.finalize_pi_agent_run",
                    side_effect=finalize,
                ),
            ):
                result = start_pi_sweep(
                    self.repo_root,
                    PiSweepConfig(
                        plan_path=plan_path.relative_to(self.repo_root),
                        results_dir=(root / "sweeps").relative_to(self.repo_root),
                        agent_results_dir=agent_root.relative_to(self.repo_root),
                    ),
                    client=client,
                    sleep=lambda _seconds: None,
                )
            sweep = json.loads(
                (Path(result["sweep_dir"]) / "sweep.json").read_text(encoding="utf-8")
            )

        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["verified_success_count"], 1)
        self.assertEqual(sweep["units"][0]["trajectory"]["agent_turns"], 4)
        self.assertEqual(client.unloaded, [MODEL_NAME])

    def test_running_attempt_is_preserved_and_restarted_as_pending(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.repo_root / "results") as temporary:
            run_dir = Path(temporary) / "interrupted"
            run_dir.mkdir()
            (run_dir / "run.json").write_text(
                json.dumps({"state": "running"}), encoding="utf-8"
            )
            unit = {
                "status": "sandbox_accepted",
                "run_id": "pi-agentic-run-old",
                "run_dir": run_dir.relative_to(self.repo_root).as_posix(),
                "interrupted_attempts": [],
                "resource_gate": {"passed": True},
            }

            _reconcile_unit(self.repo_root, unit)

        self.assertEqual(unit["status"], "pending")
        self.assertIsNone(unit["run_id"])
        self.assertEqual(
            unit["interrupted_attempts"][0]["run_id"], "pi-agentic-run-old"
        )


if __name__ == "__main__":
    unittest.main()
