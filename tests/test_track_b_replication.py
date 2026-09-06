import json
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_llm_benchmark.runner import RunnerError
from local_llm_benchmark.runner import sha256_file
from local_llm_benchmark.track_b_replication import (
    ReplicationConfig,
    _relative,
    _summary,
    advance_replication,
    cleanup_replication_unit,
    load_replication_plan,
    run_replication_live_step,
    start_replication,
)


QWEN38 = "qwen3.8:27b-mlx"
QWEN36 = "qwen3.6:35b-a3b-mxfp8"
JS_CASE = "coding.dev.async-cache-coalescing"
PYTHON_CASE = "coding.dev.pagination-cycle-guard"


class FakeClient:
    def __init__(self) -> None:
        self.unloaded = []

    def version(self) -> dict:
        return {"version": "0.33.2"}

    def list_models(self) -> dict:
        return {
            "models": [
                {"name": QWEN38, "digest": "8" * 64, "size": 38},
                {"name": QWEN36, "digest": "6" * 64, "size": 36},
            ]
        }

    def list_running_models(self) -> dict:
        return {"models": []}

    def unload_model(self, model: str) -> dict:
        self.unloaded.append(model)
        return {"done": True}


class TrackBReplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path.cwd().resolve()

    def _plan(self, directory: Path) -> Path:
        pi_report = Path("reports/coding/track-b-pi-capability-sweep-v0.3.json")
        mini_report = Path("reports/coding/track-b-mini-capability-sweep-v0.3.json")
        artifacts = [
            Path("tasks/coding/track-b/pi-v0.3.json"),
            Path("tasks/coding/track-b/mini-v0.3.json"),
            Path("local_llm_benchmark/track_b_replication.py"),
            pi_report,
            mini_report,
        ]
        selected = [
            {"model": QWEN38, "case_id": JS_CASE},
            {"model": QWEN36, "case_id": PYTHON_CASE},
        ]
        order = []
        position = 0
        for replication_index in (2, 3):
            for harness_id, cell in (
                ("pi-v0.3", selected[0]),
                ("mini-v0.3", selected[1]),
                ("pi-v0.3", selected[1]),
                ("mini-v0.3", selected[0]),
            ):
                position += 1
                order.append(
                    {
                        "position": position,
                        "harness_id": harness_id,
                        "model": cell["model"],
                        "case_id": cell["case_id"],
                        "replication_index": replication_index,
                    }
                )
        plan = {
            "schema_version": "1.0.0",
            "plan_id": "test-targeted-replication",
            "status": "frozen_before_execution",
            "track": "B",
            "study_mode": "targeted_outcome_replication",
            "evidence_class": "post_hoc_targeted_replication",
            "runtime": {"name": "ollama", "version": "0.33.2"},
            "harnesses": [
                {
                    "harness_id": "pi-v0.3",
                    "harness_path": "tasks/coding/track-b/pi-v0.3.json",
                },
                {
                    "harness_id": "mini-v0.3",
                    "harness_path": "tasks/coding/track-b/mini-v0.3.json",
                },
            ],
            "baseline_reports": [
                {
                    "harness_id": "pi-v0.3",
                    "path": pi_report.as_posix(),
                    "sha256": sha256_file(pi_report),
                },
                {
                    "harness_id": "mini-v0.3",
                    "path": mini_report.as_posix(),
                    "sha256": sha256_file(mini_report),
                },
            ],
            "deployments": [
                {"name": QWEN38, "deployment_id": "qwen38", "digest": "8" * 64},
                {"name": QWEN36, "deployment_id": "qwen36", "digest": "6" * 64},
            ],
            "cases": [
                {
                    "case_id": JS_CASE,
                    "case_path": "tasks/coding/dev/async-cache-coalescing/case.json",
                },
                {
                    "case_id": PYTHON_CASE,
                    "case_path": "tasks/coding/dev/pagination-cycle-guard/case-whole-file-v1.2.json",
                },
            ],
            "selected_cells": selected,
            "replication": {
                "fresh_replication_indices": [2, 3],
                "fresh_runs_per_system_cell": 2,
            },
            "execution_order": order,
            "comparison_rules": {
                "automatic_retries": 0,
                "adaptive_repetitions": False,
                "reliability_probability_claims": False,
                "tail_performance_claims": False,
            },
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

    def test_relative_rejects_paths_outside_repository(self) -> None:
        with self.assertRaises(RunnerError):
            _relative(Path("/repo"), Path("/elsewhere/file"))

    def test_summary_exposes_only_the_first_incomplete_unit(self) -> None:
        record = {
            "study_id": "study",
            "status": "running",
            "unit_count": 2,
            "complete_unit_count": 1,
            "verified_success_count": 1,
            "units": [
                {"status": "complete"},
                {
                    "position": 2,
                    "harness_id": "mini-v0.3",
                    "model": "model",
                    "case_id": "case",
                    "replication_index": 2,
                    "status": "awaiting_live",
                    "run_dir": "results/run",
                },
            ],
        }

        summary = _summary(record, Path("/repo/results/study"))

        self.assertEqual(summary["waiting"]["position"], 2)
        self.assertEqual(summary["waiting"]["status"], "awaiting_live")

    def test_plan_requires_two_baseline_disagreements_and_eight_fresh_runs(self) -> None:
        results = self.repo_root / "results"
        results.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=results) as temporary:
            loaded = load_replication_plan(
                self.repo_root, self._plan(Path(temporary))
            )

        self.assertEqual(len(loaded["plan"]["execution_order"]), 8)
        self.assertEqual(set(loaded["harnesses"]), {"pi-v0.3", "mini-v0.3"})

    def test_tracked_plan_freezes_controller_and_balanced_targeted_order(self) -> None:
        loaded = load_replication_plan(
            self.repo_root,
            Path("tasks/coding/track-b/targeted-system-replication-v0.1.json"),
        )
        plan = loaded["plan"]

        self.assertEqual(plan["replication"]["fresh_run_count"], 8)
        self.assertEqual(
            plan["replication"]["descriptive_observations_per_system_cell_after_completion"],
            3,
        )
        self.assertFalse(plan["comparison_rules"]["reliability_probability_claims"])
        self.assertFalse(plan["comparison_rules"]["tail_performance_claims"])
        harness_position_sum = {}
        for unit in plan["execution_order"]:
            harness_position_sum.setdefault(unit["harness_id"], 0)
            harness_position_sum[unit["harness_id"]] += unit["position"]
        self.assertEqual(harness_position_sum, {"pi-v0.3": 18, "mini-v0.3": 18})

        commit = plan["frozen_inputs"]["implementation_git_commit"]
        for artifact in plan["frozen_inputs"]["artifacts"]:
            blob = subprocess.run(
                ["git", "show", f"{commit}:{artifact['path']}"],
                cwd=self.repo_root,
                capture_output=True,
                check=False,
            )
            self.assertEqual(blob.returncode, 0, artifact["path"])
            self.assertEqual(
                artifact["sha256"], hashlib.sha256(blob.stdout).hexdigest()
            )

    def test_mixed_controller_checkpoints_all_units(self) -> None:
        results = self.repo_root / "results"
        results.mkdir(exist_ok=True)
        client = FakeClient()
        with tempfile.TemporaryDirectory(dir=results) as temporary:
            root = Path(temporary)
            agent_root = root / "agent-runs"
            counter = {"value": 0}

            def create_run(prefix: str, state: str) -> dict:
                counter["value"] += 1
                run_id = f"{prefix}-{counter['value']}"
                run_dir = agent_root / run_id
                run_dir.mkdir(parents=True)
                (run_dir / "run.json").write_text(
                    json.dumps(
                        {
                            "state": state,
                            "trajectory": {"model_requests": 0},
                        }
                    ),
                    encoding="utf-8",
                )
                return {"run_id": run_id, "run_dir": str(run_dir)}

            def prepare_pi(*_args: object, **_kwargs: object) -> dict:
                return create_run("pi", "prepared_not_executed")

            def prepare_mini(*_args: object, **_kwargs: object) -> dict:
                return create_run("mini", "awaiting_model")

            def accept(run_dir: Path) -> dict:
                acceptance = {
                    "passed": True,
                    "validated_at": "2026-09-05T00:00:00Z",
                    "profile_sha256": "a" * 64,
                    "hidden_verifier_sha256": "b" * 64,
                }
                (run_dir / "pi-sandbox-acceptance.json").write_text(
                    json.dumps(acceptance), encoding="utf-8"
                )
                return acceptance

            def live_pi(_repo: Path, run_dir: Path) -> dict:
                (run_dir / "run.json").write_text(
                    json.dumps(
                        {
                            "state": "execution_complete_verification_pending",
                            "trajectory": {"agent_turns": 2},
                        }
                    ),
                    encoding="utf-8",
                )
                return {"state": "execution_complete_verification_pending"}

            def live_mini(_repo: Path, run_dir: Path) -> dict:
                (run_dir / "run.json").write_text(
                    json.dumps(
                        {
                            "state": "trajectory_complete_verification_pending",
                            "trajectory": {"model_requests": 1, "agent_turns": 1},
                        }
                    ),
                    encoding="utf-8",
                )
                return {"state": "trajectory_complete_verification_pending"}

            def finalize(_repo: Path, run_dir: Path) -> dict:
                outcome = {
                    "runtime_success": True,
                    "agent_termination_valid": True,
                    "verifier_success": True,
                    "verified_success": True,
                    "failure_category": None,
                    "failure_type": None,
                }
                (run_dir / "run.json").write_text(
                    json.dumps(
                        {
                            "state": "complete",
                            "outcome": outcome,
                            "trajectory": {"agent_turns": 2, "model_requests": 1},
                        }
                    ),
                    encoding="utf-8",
                )
                return outcome

            with (
                patch(
                    "local_llm_benchmark.track_b_replication.prepare_pi_v03_agent_run",
                    side_effect=prepare_pi,
                ),
                patch(
                    "local_llm_benchmark.track_b_replication.start_mini_v03_run",
                    side_effect=prepare_mini,
                ),
                patch(
                    "local_llm_benchmark.track_b_replication.validate_pi_v03_seatbelt",
                    side_effect=accept,
                ),
                patch(
                    "local_llm_benchmark.track_b_replication.execute_pi_v03_agent_run",
                    side_effect=live_pi,
                ),
                patch(
                    "local_llm_benchmark.track_b_replication.call_mini_v03_model",
                    side_effect=live_mini,
                ),
                patch(
                    "local_llm_benchmark.track_b_replication.finalize_pi_v03_agent_run",
                    side_effect=finalize,
                ),
                patch(
                    "local_llm_benchmark.track_b_replication.finalize_mini_v03_run",
                    side_effect=finalize,
                ),
            ):
                summary = start_replication(
                    self.repo_root,
                    ReplicationConfig(
                        plan_path=self._plan(root),
                        results_dir=root / "studies",
                        agent_results_dir=agent_root,
                    ),
                    client=client,
                )
                study_dir = Path(summary["study_dir"])
                while summary["status"] != "complete":
                    waiting = summary["waiting"]
                    if waiting["status"] == "awaiting_live":
                        summary = run_replication_live_step(
                            self.repo_root,
                            study_dir,
                            client=client,
                            sleep=lambda _seconds: None,
                        )
                    elif waiting["status"] in {
                        "awaiting_action",
                        "verification_pending",
                    }:
                        summary = advance_replication(self.repo_root, study_dir)
                    elif waiting["status"] == "complete_needs_cleanup":
                        summary = cleanup_replication_unit(
                            self.repo_root, study_dir, client=client
                        )
                    else:
                        self.fail(f"Unexpected controller state: {waiting}")

            record = json.loads(
                (study_dir / "study.json").read_text(encoding="utf-8")
            )

        self.assertEqual(summary["complete_unit_count"], 8)
        self.assertEqual(summary["verified_success_count"], 8)
        self.assertEqual(len(client.unloaded), 8)
        self.assertTrue(all(unit["status"] == "complete" for unit in record["units"]))


if __name__ == "__main__":
    unittest.main()
