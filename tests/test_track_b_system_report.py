import unittest

from local_llm_benchmark.track_b_system_report import (
    _aggregate,
    _relation,
    render_track_b_system_markdown,
)


def cell(relation: str) -> dict:
    pi_success = relation in {"both_success", "pi_only_success"}
    mini_success = relation in {"both_success", "mini_only_success"}
    view = {
        "verifier_success": False,
        "runtime_success": True,
        "failure_type": "test_failure",
        "active_duration_seconds": 10.0,
        "agent_turns": 1,
        "tool_calls": 1,
        "failed_tool_calls": 0,
        "file_reads": 1,
        "file_writes": 0,
        "public_test_runs": 0,
        "input_tokens": 10,
        "output_tokens": 1,
    }
    return {
        "model": "model",
        "case_id": "case",
        "case_label": "Case",
        "outcome_agreement": relation in {"both_success", "both_failure"},
        "outcome_relation": relation,
        "pi": {**view, "verified_success": pi_success},
        "mini": {**view, "verified_success": mini_success},
    }


class TrackBSystemReportTests(unittest.TestCase):
    def test_relation_covers_all_binary_outcomes(self) -> None:
        self.assertEqual(_relation(True, True), "both_success")
        self.assertEqual(_relation(False, False), "both_failure")
        self.assertEqual(_relation(True, False), "pi_only_success")
        self.assertEqual(_relation(False, True), "mini_only_success")

    def test_aggregate_keeps_system_outcomes_separate(self) -> None:
        cells = [
            cell("both_success"),
            cell("pi_only_success"),
            cell("mini_only_success"),
        ]

        aggregate = _aggregate(cells, key="scope", value="all")

        self.assertEqual(aggregate["pi_verified_success_count"], 2)
        self.assertEqual(aggregate["mini_verified_success_count"], 2)
        self.assertEqual(aggregate["outcome_agreement_count"], 1)

    def test_markdown_labels_comparison_as_system_level(self) -> None:
        sample = cell("both_success")
        report = {
            "summary": {
                "configuration_count": 1,
                "pi_verified_success_count": 1,
                "mini_verified_success_count": 1,
                "outcome_agreement_count": 1,
            },
            "by_model": [
                {
                    "model": "model",
                    "pi_verified_success_count": 1,
                    "mini_verified_success_count": 1,
                    "outcome_agreement_count": 1,
                }
            ],
            "by_case": [
                {
                    "case_label": "Case",
                    "pi_verified_success_count": 1,
                    "mini_verified_success_count": 1,
                    "outcome_agreement_count": 1,
                }
            ],
            "cells": [sample],
            "findings": ["Finding."],
            "caveats": ["Complete-system comparison."],
            "sources": {
                "pi": {"report_id": "pi", "sha256": "a" * 64},
                "mini": {"report_id": "mini", "sha256": "b" * 64},
            },
        }

        markdown = render_track_b_system_markdown(report)

        self.assertIn("System Comparison", markdown)
        self.assertIn("Complete-system comparison.", markdown)


if __name__ == "__main__":
    unittest.main()
