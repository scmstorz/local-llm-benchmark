from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from local_llm_benchmark.performance_reliability import (
    DEFAULT_PLAN_PATH,
    PerformanceStudyConfig,
    _aggregate_condition,
    _output_contract,
    _statistics,
    advance_performance_study,
    load_performance_plan,
    start_performance_study,
)
from local_llm_benchmark.runner import RunnerError


class PerformanceReliabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[1]
        cls.loaded = load_performance_plan(cls.repo_root, DEFAULT_PLAN_PATH)

    def test_frozen_plan_is_segmented_and_complete(self) -> None:
        plan = self.loaded["plan"]
        self.assertEqual(plan["methodology"]["measured_runs_per_condition"], 20)
        self.assertEqual(plan["methodology"]["measured_runs_per_block"], 5)
        self.assertEqual(plan["methodology"]["segments_per_condition"], 4)
        self.assertEqual(plan["methodology"]["total_planned_measured_runs"], 80)
        self.assertEqual(len(plan["execution_order"]), 16)
        self.assertEqual(
            {item["kind"] for item in plan["workloads"]},
            {"natural_output", "controlled_decode"},
        )

    def test_start_is_offline_and_creates_exactly_eighty_pending_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = start_performance_study(
                self.repo_root,
                PerformanceStudyConfig(
                    studies_dir=Path(directory),
                    runs_dir=Path("results/runs"),
                ),
            )
            record = json.loads(
                (Path(result["study_dir"]) / "study.json").read_text(encoding="utf-8")
            )
        self.assertEqual(result["measured_total"], 80)
        self.assertEqual(result["total_blocks"], 16)
        self.assertEqual(
            sum(len(block["measured_runs"]) for block in record["blocks"]), 80
        )
        self.assertTrue(
            all(
                attempt["status"] == "pending"
                for block in record["blocks"]
                for attempt in block["measured_runs"]
            )
        )

    def test_tail_statistics_follow_sample_boundaries(self) -> None:
        reporting = self.loaded["plan"]["reporting"]
        small = _statistics([float(value) for value in range(1, 10)], reporting)
        full = _statistics([float(value) for value in range(1, 21)], reporting)
        self.assertIsNone(small["p90"])
        self.assertEqual(full["p90"], 18.0)
        self.assertIsNone(full["p95"])
        self.assertIsNone(full["p99"])
        self.assertEqual(full["percentile_method"], "nearest_rank")

    def test_workload_output_contracts_remain_distinct(self) -> None:
        plan = self.loaded["plan"]
        natural = next(item for item in plan["workloads"] if item["kind"] == "natural_output")
        controlled = next(
            item for item in plan["workloads"] if item["kind"] == "controlled_decode"
        )
        natural_result = {
            "checks": {key: True for key in natural["output_contract"]["required_checks"]}
        }
        natural_contract = _output_contract(
            repo_root=self.repo_root,
            result=natural_result,
            workload=natural,
        )
        self.assertEqual(natural_contract["status"], "passed")
        self.assertFalse(natural_contract["semantic_quality_verified"])

        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "response.md").write_text(
                "vector vector vector\n", encoding="utf-8"
            )
            controlled_result = {
                "run_dir": str(run_dir),
                "done_reason": "length",
                "metrics": {"eval_count": 256},
            }
            controlled_contract = _output_contract(
                repo_root=self.repo_root,
                result=controlled_result,
                workload=controlled,
            )
        self.assertEqual(controlled_contract["status"], "passed")
        self.assertTrue(controlled_contract["conditions"]["protocol_match"])

    def test_public_condition_aggregate_has_raw_metrics_but_no_run_ids(self) -> None:
        plan = self.loaded["plan"]
        blocks = []
        for segment in range(1, 5):
            attempts = []
            for offset in range(1, 6):
                value = float((segment - 1) * 5 + offset)
                attempts.append(
                    {
                        "status": "complete",
                        "failure": None,
                        "output_contract": {"status": "passed"},
                        "run": {
                            "run_id": f"private-{segment}-{offset}",
                            "metrics": {
                                "wall_time_seconds": value,
                                "time_to_first_content_seconds": value / 10,
                                "output_tokens_per_second": 40.0,
                            },
                        },
                    }
                )
            blocks.append(
                {
                    "block_id": f"block-{segment}",
                    "deployment_alias": "Q",
                    "workload_alias": "N",
                    "measured_runs": attempts,
                    "preload_attempts": [],
                    "warmup_attempts": [],
                }
            )
        aggregate = _aggregate_condition(blocks, plan)
        self.assertEqual(aggregate["performance"]["wall_time_seconds"]["p90"], 18.0)
        self.assertEqual(aggregate["reliability"]["technical_successes"], 20)
        self.assertNotIn("private-", json.dumps(aggregate))

    def test_advance_requires_explicit_live_flag(self) -> None:
        with self.assertRaises(RunnerError):
            advance_performance_study(
                self.repo_root,
                Path("does-not-matter"),
                execute_live=False,
            )

    @patch("local_llm_benchmark.performance_reliability.run_once")
    @patch("local_llm_benchmark.performance_reliability._active_guard")
    @patch("local_llm_benchmark.performance_reliability.run_resource_gate")
    @patch("local_llm_benchmark.performance_reliability.OllamaClient")
    def test_live_advance_checkpoints_one_five_run_block(
        self,
        client_type: MagicMock,
        resource_gate: MagicMock,
        active_guard: MagicMock,
        run_once_mock: MagicMock,
    ) -> None:
        natural = next(
            item
            for item in self.loaded["plan"]["workloads"]
            if item["kind"] == "natural_output"
        )
        required_checks = natural["output_contract"]["required_checks"]
        call_count = 0

        def completed_run(*_args: object, **_kwargs: object) -> dict:
            nonlocal call_count
            call_count += 1
            return {
                "run_id": f"run-{call_count}",
                "run_dir": "/tmp/not-read-for-natural-output",
                "done_reason": "stop",
                "checks": {key: True for key in required_checks},
                "metrics": {
                    "wall_time_seconds": float(call_count),
                    "time_to_first_content_seconds": 0.5,
                    "output_tokens_per_second": 40.0,
                },
            }

        run_once_mock.side_effect = completed_run
        resource_gate.return_value = {"passed": True}
        active_guard.return_value = {"checked_at": "now"}
        client = client_type.return_value
        client.preload_model.return_value = {"load_duration": 1}
        client.list_running_models.return_value = {"models": []}

        with tempfile.TemporaryDirectory() as directory:
            started = start_performance_study(
                self.repo_root,
                PerformanceStudyConfig(studies_dir=Path(directory)),
            )
            result = advance_performance_study(
                self.repo_root,
                Path(started["study_dir"]),
                execute_live=True,
            )
            record = json.loads(
                (Path(started["study_dir"]) / "study.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(run_once_mock.call_count, 6)
        self.assertEqual(result["complete_blocks"], 1)
        self.assertEqual(result["measured_complete"], 5)
        self.assertEqual(result["waiting"]["position"], 2)
        first = record["blocks"][0]
        self.assertEqual(first["status"], "complete")
        self.assertEqual(len(first["warmup_attempts"]), 1)
        self.assertTrue(first["warmup_attempts"][0]["excluded_from_steady_state"])


if __name__ == "__main__":
    unittest.main()
