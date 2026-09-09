from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from local_llm_benchmark.quality_stochasticity import (
    DEFAULT_PLAN_PATH,
    QualityStudyConfig,
    _validate_plan_structure,
    advance_quality_study,
    load_quality_plan,
    start_quality_study,
)
from local_llm_benchmark.runner import RunnerError


KNOWLEDGE_PLAN_PATH = Path(
    "tasks/studies/quality-stochasticity-knowledge-v0.2.json"
)


def synthetic_plan() -> dict:
    units = []
    position = 0
    for repetition in (1, 2):
        for deployment_alias, case_alias in (("A", "S"), ("B", "W"), ("A", "W"), ("B", "S")):
            position += 1
            units.append(
                {
                    "position": position,
                    "unit_id": f"u{position:02d}",
                    "deployment_alias": deployment_alias,
                    "case_alias": case_alias,
                    "repetition": repetition,
                }
            )
    return {
        "schema_version": "1.0.0",
        "plan_id": "quality-test-plan",
        "status": "frozen_before_execution",
        "runtime": {"name": "ollama", "version": "0.33.2"},
        "deployments": [
            {"alias": "A", "name": "model:a", "digest": "a" * 64},
            {"alias": "B", "name": "model:b", "digest": "b" * 64},
        ],
        "cases": [
            {"alias": "S", "case_id": "case.s", "case_path": "s.json", "num_ctx": 8},
            {"alias": "W", "case_id": "case.w", "case_path": "w.json", "num_ctx": 8},
        ],
        "methodology": {
            "measured_runs_per_condition": 2,
            "timeout_seconds": 60,
            "generation_settings": {
                "temperature": 0.0,
                "seed": 42,
                "think": False,
                "num_predict": 100,
                "keep_alive": "10m",
            },
        },
        "execution_order": units,
        "resource_gate": {
            "loaded_models_must_be_empty_before_each_unit": True,
            "model_unloaded_after_each_unit": True,
            "blocking_process_rules": [],
        },
        "blinding": {"bundle_seed": "test"},
        "authorization": {"live_execution_authorized": True},
        "frozen_artifacts": [{"path": "artifact", "sha256": "c" * 64}],
    }


class QualityStochasticityTests(unittest.TestCase):
    def test_frozen_default_plan_is_complete_and_hash_bound(self) -> None:
        repo_root = Path.cwd().resolve()
        loaded = load_quality_plan(
            repo_root,
            DEFAULT_PLAN_PATH,
            require_private_inputs=False,
        )
        plan = loaded["plan"]
        self.assertEqual(plan["implementation_commit"], "1cba52ce3c0db20d23524817ff4f66a36499a1a8")
        self.assertEqual(plan["methodology"]["total_planned_measured_runs"], 20)
        self.assertEqual(len(plan["execution_order"]), 20)
        self.assertEqual(
            {case["alias"] for case in plan["cases"]},
            {"S", "W"},
        )
        self.assertEqual(
            {deployment["alias"] for deployment in plan["deployments"]},
            {"O", "G"},
        )

    def test_frozen_knowledge_plan_is_complete_and_hash_bound(self) -> None:
        repo_root = Path.cwd().resolve()
        loaded = load_quality_plan(
            repo_root,
            KNOWLEDGE_PLAN_PATH,
            require_private_inputs=False,
        )
        plan = loaded["plan"]
        self.assertEqual(plan["study_version"], "0.2.0")
        self.assertEqual(plan["methodology"]["total_planned_measured_runs"], 20)
        self.assertEqual(len(plan["execution_order"]), 20)
        self.assertEqual(
            {case["alias"] for case in plan["cases"]},
            {"B", "L"},
        )
        self.assertEqual(
            {deployment["alias"] for deployment in plan["deployments"]},
            {"Q", "G"},
        )
        self.assertEqual(
            plan["selection_evidence"]["selected_challenger"],
            "muse-glimmer:30b-mlx",
        )
        self.assertFalse(
            plan["authorization"]["preparation_turn_inference_authorized"]
        )
        self.assertTrue(
            plan["authorization"]["next_live_action_requires_explicit_user_go_ahead"]
        )

    def test_structure_requires_the_full_repeated_product(self) -> None:
        plan = synthetic_plan()
        _validate_plan_structure(plan)

        plan["execution_order"].pop()
        with self.assertRaisesRegex(RunnerError, "full product"):
            _validate_plan_structure(plan)

    def test_start_checkpoints_every_unit_without_inference(self) -> None:
        plan = synthetic_plan()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            loaded = {
                "plan": plan,
                "path": plan_path,
                "sha256": "plan-hash",
                "loaded_cases": {"S": {}, "W": {}},
            }
            with patch(
                "local_llm_benchmark.quality_stochasticity.load_quality_plan",
                return_value=loaded,
            ):
                result = start_quality_study(
                    root,
                    QualityStudyConfig(
                        plan_path=plan_path,
                        studies_dir=Path("studies"),
                        runs_dir=Path("runs"),
                    ),
                )
            self.assertEqual(result["total_units"], 8)
            self.assertEqual(result["complete_units"], 0)
            study = json.loads(
                (Path(result["study_dir"]) / "study.json").read_text(encoding="utf-8")
            )
            self.assertTrue(all(unit["status"] == "pending" for unit in study["units"]))

    def test_live_advance_requires_an_explicit_flag(self) -> None:
        with self.assertRaisesRegex(RunnerError, "execute-live"):
            advance_quality_study(Path.cwd(), Path("unused"))

    def test_advance_checkpoints_exactly_one_run_and_unloads_model(self) -> None:
        plan = synthetic_plan()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            study_dir = root / "study"
            runs_dir = root / "runs"
            run_dir = runs_dir / "run-one"
            study_dir.mkdir()
            run_dir.mkdir(parents=True)
            record = {
                "schema_version": "1.0.0",
                "study_id": "quality-study-test",
                "status": "running",
                "started_at": "2026-09-08T00:00:00Z",
                "completed_at": None,
                "plan": {
                    "plan_id": plan["plan_id"],
                    "path": "plan.json",
                    "sha256": "plan-hash",
                },
                "runs_dir": str(runs_dir),
                "units": [
                    {
                        **unit,
                        "status": "pending",
                        "started_at": None,
                        "completed_at": None,
                        "resource_gate": None,
                        "preload_wall_seconds": None,
                        "run": None,
                        "failure": None,
                        "running_models_after_cleanup": None,
                        "interrupted_attempts": [],
                    }
                    for unit in plan["execution_order"]
                ],
                "pause_history": [],
                "judge_bundles": None,
                "artifacts": {"private_map": "private-map.json"},
            }
            (study_dir / "private-map.json").write_text(
                json.dumps(
                    {"schema_version": "1.0.0", "private_model_mapping": {}}
                ),
                encoding="utf-8",
            )
            run_record = {
                "schema_version": "1.0.0",
                "run_id": "run-one",
                "candidate_id": "candidate-one",
                "status": "complete",
                "case": {"case_id": "case.s"},
                "deployment": {
                    "model": {"requested_name": "model:a"},
                },
                "execution": {"done_reason": "stop"},
                "measurement": {
                    "comparison_id": "quality-study-test",
                    "phase": "warm",
                    "iteration": 1,
                },
                "metrics": {"wall_time_seconds": 1.0},
                "checks": {"generation_complete": True},
            }
            (run_dir / "run.json").write_text(
                json.dumps(run_record), encoding="utf-8"
            )
            loaded = {
                "plan": plan,
                "path": root / "plan.json",
                "sha256": "plan-hash",
                "loaded_cases": {"S": {}, "W": {}},
            }
            client = MagicMock()
            client.preload_model.return_value = {}
            client.list_running_models.side_effect = [
                {"models": [{"name": "model:a"}]},
                {"models": [{"name": "model:a"}]},
                {"models": []},
            ]
            client.unload_model.return_value = {}
            with (
                patch(
                    "local_llm_benchmark.quality_stochasticity._load_study",
                    return_value=(study_dir, record, loaded),
                ),
                patch(
                    "local_llm_benchmark.quality_stochasticity.OllamaClient",
                    return_value=client,
                ),
                patch(
                    "local_llm_benchmark.quality_stochasticity.run_resource_gate",
                    return_value={"passed": True},
                ),
                patch(
                    "local_llm_benchmark.quality_stochasticity.run_once",
                    return_value={"run_dir": str(run_dir)},
                ) as run_mock,
            ):
                result = advance_quality_study(
                    root,
                    study_dir,
                    execute_live=True,
                )

            self.assertEqual(result["complete_units"], 1)
            self.assertEqual(result["failed_units"], 0)
            self.assertEqual(run_mock.call_count, 1)
            client.unload_model.assert_called_once_with("model:a")
            mapping = json.loads(
                (study_dir / "private-map.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                mapping["private_model_mapping"]["candidate-one"]["model"],
                "model:a",
            )


if __name__ == "__main__":
    unittest.main()
