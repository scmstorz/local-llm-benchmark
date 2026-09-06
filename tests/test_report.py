import json
import tempfile
import unittest
from pathlib import Path

from local_llm_benchmark.report import build_results_index, render_markdown, write_report
from local_llm_benchmark.runner import RunnerError


class ReportTest(unittest.TestCase):
    def _write_comparison(
        self,
        root: Path,
        comparison_id: str,
        case_id: str,
        scores: tuple[float, float],
        second_compliant: bool = True,
        inapplicable_compliance_checks: tuple[str, ...] = (),
    ) -> None:
        target = root / "results/comparisons" / comparison_id
        target.mkdir(parents=True)
        models = []
        ranking = []
        for rank, (model, score) in enumerate(
            zip(("model:a", "model:b"), scores, strict=True), start=1
        ):
            checks = {
                "nonempty": True,
                "generation_complete": True,
                "language_pass": True,
                "maximum_words_pass": second_compliant or model == "model:a",
                "heading_pass": True,
                "reasoning_markup_absent": True,
                "source_location_labels_absent": True,
                "word_count": 500 + rank,
            }
            phase = {
                "run_id": f"run-secret-{rank}",
                "status": "complete",
                "done_reason": "stop",
                "checks": checks,
                "metrics": {
                    "wall_time_seconds": 10.0 * rank,
                    "output_tokens_per_second": 50.0 / rank,
                },
            }
            models.append({"model": model, "warm": phase, "cold": phase})
            ranking.append(
                {
                    "rank": rank,
                    "model": model,
                    "candidate_id": f"candidate-secret-{rank}",
                    "score": score,
                    "verdict": "excellent" if score >= 90 else "good",
                }
            )
        comparison = {
            "comparison_id": comparison_id,
            "status": "complete",
            "case": {"case_id": case_id, "case_version": "1.0.0"},
            "ollama_version": "1.2.3",
            "options": {
                "num_ctx": 8192,
                "num_predict": 1000,
                "temperature": 0.0,
                "seed": 42,
                "think": False,
            },
            "models": models,
        }
        quality = {
            "comparison_id": comparison_id,
            "evaluated_at": "2026-01-01T00:00:00Z",
            "case": {"case_id": case_id, "case_version": "1.0.0"},
            "ranking": ranking,
            "inapplicable_compliance_checks": list(inapplicable_compliance_checks),
        }
        (target / "comparison.json").write_text(json.dumps(comparison), encoding="utf-8")
        (target / "quality-summary.json").write_text(json.dumps(quality), encoding="utf-8")

    def _write_selection(self, root: Path, comparison_ids: list[str]) -> None:
        target = root / "reports/comparison-selection.json"
        target.parent.mkdir(parents=True)
        target.write_text(
            json.dumps(
                {
                    "schema_version": "1.0.0",
                    "comparisons": [
                        {
                            "comparison_id": comparison_id,
                            "performance_evidence": "controlled",
                        }
                        for comparison_id in comparison_ids
                    ],
                }
            ),
            encoding="utf-8",
        )

    def test_builds_sanitized_aggregate_and_compliance_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_comparison(
                root,
                "comparison-one",
                "summarization.dev.one",
                (95.0, 80.0),
                second_compliant=False,
            )
            self._write_comparison(
                root,
                "comparison-two",
                "general_knowledge.dev.two",
                (85.0, 90.0),
            )
            self._write_selection(root, ["comparison-one", "comparison-two"])

            index = build_results_index(root)
            serialized = json.dumps(index)

            self.assertEqual(index["selection"]["comparison_count"], 2)
            self.assertNotIn("candidate-secret", serialized)
            self.assertNotIn("run-secret", serialized)
            model_b = next(
                item for item in index["model_summary"] if item["model"] == "model:b"
            )
            self.assertEqual(model_b["mean_quality_score"], 85.0)
            self.assertEqual(model_b["mean_compliant_quality_score"], 90.0)
            self.assertEqual(model_b["compliant_count"], 1)

    def test_case_can_mark_a_shared_compliance_check_inapplicable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_comparison(
                root,
                "comparison-one",
                "source_grounded_writing.dev.one",
                (88.0, 82.0),
                inapplicable_compliance_checks=("heading_pass",),
            )
            comparison_path = (
                root / "results/comparisons/comparison-one/comparison.json"
            )
            comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
            for record in comparison["models"]:
                record["warm"]["checks"]["heading_pass"] = False
                record["cold"]["checks"]["heading_pass"] = False
            comparison_path.write_text(json.dumps(comparison), encoding="utf-8")
            self._write_selection(root, ["comparison-one"])

            index = build_results_index(root)

            self.assertTrue(
                all(result["compliant"] for result in index["cases"][0]["results"])
            )

    def test_rejects_unknown_inapplicable_compliance_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_comparison(
                root,
                "comparison-one",
                "source_grounded_writing.dev.one",
                (88.0, 82.0),
                inapplicable_compliance_checks=("invented_check",),
            )
            self._write_selection(root, ["comparison-one"])

            with self.assertRaisesRegex(RunnerError, "Unknown inapplicable"):
                build_results_index(root)

    def test_write_report_is_deterministic_and_renders_tables(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_comparison(
                root,
                "comparison-one",
                "summarization.dev.one",
                (95.0, 80.0),
            )
            self._write_selection(root, ["comparison-one"])

            result = write_report(root)
            first_json = (root / "reports/results-index.json").read_text(encoding="utf-8")
            first_markdown = (root / "reports/overview.md").read_text(encoding="utf-8")
            write_report(root)

            self.assertEqual(result["case_count"], 1)
            self.assertEqual(
                first_json,
                (root / "reports/results-index.json").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                first_markdown,
                (root / "reports/overview.md").read_text(encoding="utf-8"),
            )
            self.assertIn("## Model summary", first_markdown)
            self.assertIn("summarization.dev.one", first_markdown)

    def test_rejects_multiple_selected_comparisons_for_one_case(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_comparison(
                root, "comparison-one", "summarization.dev.same", (95.0, 80.0)
            )
            self._write_comparison(
                root, "comparison-two", "summarization.dev.same", (90.0, 85.0)
            )
            self._write_selection(root, ["comparison-one", "comparison-two"])

            with self.assertRaisesRegex(RunnerError, "more than one result for case"):
                build_results_index(root)

    def test_render_does_not_require_file_access(self) -> None:
        index = {
            "data_through": None,
            "model_summary": [],
            "cases": [],
        }
        self.assertIn("# Aggregate Benchmark Results", render_markdown(index))


if __name__ == "__main__":
    unittest.main()
