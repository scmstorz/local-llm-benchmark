import unittest
from pathlib import Path

from local_llm_benchmark.mini_v03_report import (
    _aggregate_group,
    _effective_failure_category,
    _findings,
    render_mini_v03_sweep_markdown,
)


def public_unit(model: str, case_id: str, success: bool, duration: float) -> dict:
    return {
        "position": 1,
        "run_id": "run",
        "model": model,
        "deployment_id": f"{model}-deployment",
        "case_id": case_id,
        "case_label": case_id,
        "runtime_success": True,
        "agent_termination_valid": success,
        "verifier_success": success,
        "verified_success": success,
        "raw_failure_category": (
            None if success else "task_or_verification_failure"
        ),
        "effective_failure_category": (
            None if success else "task_or_verification_failure"
        ),
        "failure_type": None if success else "hidden_tests_failed",
        "trajectory_termination_reason": "finish_action",
        "public_tests_passed": success,
        "hidden_tests_passed": success,
        "active_duration_seconds": duration,
        "model_duration_seconds": duration - 1,
        "tool_duration_seconds": 1.0,
        "final_verification_duration_seconds": 0.1,
        "agent_turns": 2,
        "model_requests": 2,
        "tool_calls": 2,
        "failed_tool_calls": 0,
        "protocol_errors": 0,
        "file_reads": 1,
        "file_writes": 1,
        "public_test_runs": 0,
        "input_tokens": 100,
        "output_tokens": 20,
        "time_to_first_successful_public_verification_seconds": None,
        "interrupted_attempt_count": 0,
    }


class MiniV03ReportTests(unittest.TestCase):
    def test_active_time_limit_is_reported_as_agent_failure(self) -> None:
        category = _effective_failure_category(
            verified_success=False,
            failure_type="maximum_active_wall_time_exceeded",
            raw_category="infrastructure_or_runtime_failure",
        )

        self.assertEqual(category, "agent_failure")

    def test_aggregate_preserves_raw_duration_and_failure_counts(self) -> None:
        group = [
            public_unit("model", "case-a", True, 10.0),
            public_unit("model", "case-b", False, 14.0),
            public_unit("model", "case-c", True, 12.0),
        ]

        aggregate = _aggregate_group(group, key="model", value="model")

        self.assertEqual(aggregate["verified_success_count"], 2)
        self.assertEqual(aggregate["active_duration_seconds"]["raw"], [10.0, 14.0, 12.0])
        self.assertEqual(aggregate["active_duration_seconds"]["median"], 12.0)
        self.assertEqual(aggregate["failures"], {"hidden_tests_failed": 1})

    def test_findings_are_derived_instead_of_hard_coded(self) -> None:
        by_model = [
            {"model": "a", "verified_success_count": 3},
            {"model": "b", "verified_success_count": 1},
        ]
        by_case = [
            {"case_label": "easy", "verified_success_count": 2},
            {"case_label": "hard", "verified_success_count": 0},
        ]

        findings = _findings(by_model, by_case)

        self.assertIn("3/3 for a", findings[0])
        self.assertIn("2/5 on easy", findings[1])
        self.assertIn("0/5 on hard", findings[2])

    def test_markdown_contains_no_local_path_fields(self) -> None:
        cases = [
            "coding.dev.php-payment-result-migration",
            "coding.dev.async-cache-coalescing",
            "coding.dev.pagination-cycle-guard",
        ]
        units = [public_unit("model", case, True, 10.0) for case in cases]
        model_aggregate = _aggregate_group(units, key="model", value="model")
        case_aggregates = [
            {
                **_aggregate_group([unit], key="case_id", value=unit["case_id"]),
                "case_label": unit["case_label"],
                "language": "test",
            }
            for unit in units
        ]
        report = {
            "summary": {"run_count": 3, "verified_success_count": 3},
            "units": units,
            "by_model": [model_aggregate],
            "by_case": case_aggregates,
            "findings": ["Finding."],
            "caveats": ["Caveat."],
            "source": {
                "sweep_id": "sweep",
                "plan_id": "plan",
                "ollama_version": "test",
                "execution_git_commit": "commit",
                "sweep_record_sha256": "d" * 64,
            },
        }

        rendered = render_mini_v03_sweep_markdown(report)

        self.assertIn("3/3 verified successful outcomes", rendered)
        self.assertNotIn("/Users/", rendered)


if __name__ == "__main__":
    unittest.main()
