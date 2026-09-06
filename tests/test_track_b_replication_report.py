import json
import unittest
from pathlib import Path

from local_llm_benchmark.runner import RunnerError
from local_llm_benchmark.track_b_replication_report import (
    _effective_failure,
    aggregate_system_cell,
    render_track_b_replication_markdown,
)


def observation(index: int, success: bool, duration: float = 10.0) -> dict:
    return {
        "model": "model",
        "deployment_id": "deployment",
        "case_id": "case",
        "case_label": "Case",
        "harness_id": "mini-v0.3",
        "replication_index": index,
        "verified_success": success,
        "effective_failure_type": None if success else "hidden_tests_failed",
        "active_duration_seconds": duration,
    }


class TrackBReplicationReportTests(unittest.TestCase):
    def test_time_limit_is_effective_agent_failure(self) -> None:
        category, failure_type = _effective_failure(
            verified_success=False,
            raw_category="infrastructure_or_runtime_failure",
            raw_type="maximum_active_wall_time_exceeded",
            effective_type=None,
            termination_reason="maximum_active_wall_time_exceeded",
        )

        self.assertEqual(category, "agent_failure")
        self.assertEqual(failure_type, "maximum_active_wall_time_exceeded")

    def test_normal_agent_end_preserves_hidden_test_failure(self) -> None:
        category, failure_type = _effective_failure(
            verified_success=False,
            raw_category="task_or_verification_failure",
            raw_type="hidden_tests_failed",
            effective_type=None,
            termination_reason="agent_end",
        )

        self.assertEqual(category, "task_or_verification_failure")
        self.assertEqual(failure_type, "hidden_tests_failed")

    def test_aggregate_preserves_baseline_and_small_sample_summary(self) -> None:
        aggregate = aggregate_system_cell(
            [
                observation(1, True, 12.0),
                observation(2, False, 20.0),
                observation(3, True, 16.0),
            ]
        )

        self.assertEqual(aggregate["outcome_pattern"], "mixed_outcomes")
        self.assertTrue(aggregate["baseline_verified_success"])
        self.assertEqual(aggregate["fresh_matches_baseline_count"], 1)
        self.assertEqual(
            aggregate["active_duration_all_outcomes"],
            {
                "n": 3,
                "median_seconds": 16.0,
                "minimum_seconds": 12.0,
                "maximum_seconds": 20.0,
            },
        )
        self.assertNotIn("p90", aggregate["active_duration_all_outcomes"])

    def test_aggregate_rejects_incomplete_replication_indices(self) -> None:
        with self.assertRaises(RunnerError):
            aggregate_system_cell([observation(1, True), observation(2, True)])

    def test_tracked_report_is_public_safe_and_complete(self) -> None:
        report_path = Path(
            "reports/coding/track-b-targeted-system-replication-v0.1.json"
        )
        if not report_path.exists():
            self.skipTest("generated report not present yet")
        report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(report["summary"]["planned_observation_count"], 12)
        self.assertEqual(report["summary"]["verified_success_count"], 5)
        self.assertEqual(report["summary"]["interrupted_attempt_count_excluded"], 1)
        self.assertEqual(len(report["system_cells"]), 4)
        self.assertFalse(report["method"]["reliability_probability_claimed"])
        self.assertFalse(report["privacy"]["raw_model_text_included"])
        serialized = json.dumps(report)
        self.assertNotIn("/Users/", serialized)
        self.assertNotIn("stdout", serialized)

        timeout_observations = [
            item
            for item in report["observations"]
            if item["raw_failure_type"] == "maximum_active_wall_time_exceeded"
        ]
        self.assertEqual(len(timeout_observations), 2)
        self.assertTrue(
            all(
                item["effective_failure_category"] == "agent_failure"
                for item in timeout_observations
            )
        )

    def test_markdown_states_descriptive_boundary(self) -> None:
        report_path = Path(
            "reports/coding/track-b-targeted-system-replication-v0.1.json"
        )
        if not report_path.exists():
            self.skipTest("generated report not present yet")
        report = json.loads(report_path.read_text(encoding="utf-8"))

        markdown = render_track_b_replication_markdown(report)

        self.assertIn("not estimated success probabilities", markdown)
        self.assertIn("omits tail percentiles", markdown)
        self.assertIn("mixed_outcomes", markdown)


if __name__ == "__main__":
    unittest.main()
