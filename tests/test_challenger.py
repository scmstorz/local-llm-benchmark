import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_llm_benchmark.challenger import (
    ChallengerBundleConfig,
    assemble_challenger_bundle_batch,
)


class MultiChallengerAssemblyTest(unittest.TestCase):
    def test_multiple_sweeps_and_variable_incumbents_are_derived(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory)
            comparison_records = {
                "comparison-one": {
                    "status": "complete",
                    "completed_at": "2026-09-01T10:00:00Z",
                    "case": {"case_id": "task.dev.one"},
                    "models": [
                        {"model": "incumbent:a", "warm": {"run_id": "inc-one-a"}}
                    ],
                },
                "comparison-two": {
                    "status": "complete",
                    "completed_at": "2026-09-01T10:00:00Z",
                    "case": {"case_id": "task.dev.two"},
                    "models": [
                        {"model": "incumbent:a", "warm": {"run_id": "inc-two-a"}},
                        {"model": "incumbent:b", "warm": {"run_id": "inc-two-b"}},
                    ],
                },
            }
            sweep_records = {
                "sweep-a": {
                    "sweep_id": "sweep-a",
                    "status": "complete",
                    "suite": {
                        "suite_id": "suite-v1",
                        "suite_version": "1.0.0",
                        "manifest_sha256": "suite-hash",
                    },
                    "deployment": {"model": "challenger:a", "digest": "a" * 64},
                    "cases": [
                        {
                            "case_id": "task.dev.one",
                            "case_path": "tasks/one/case.json",
                            "canonical_baseline_available": False,
                            "status": "complete",
                            "warm": {"run_id": "challenger-a-one"},
                        },
                        {
                            "case_id": "task.dev.two",
                            "case_path": "tasks/two/case.json",
                            "canonical_baseline_available": False,
                            "status": "complete",
                            "warm": {"run_id": "challenger-a-two"},
                        },
                    ],
                },
                "sweep-b": {
                    "sweep_id": "sweep-b",
                    "status": "complete",
                    "suite": {
                        "suite_id": "suite-v1",
                        "suite_version": "1.0.0",
                        "manifest_sha256": "suite-hash",
                    },
                    "deployment": {"model": "challenger:b", "digest": "b" * 64},
                    "cases": [
                        {
                            "case_id": "task.dev.one",
                            "case_path": "tasks/one/case.json",
                            "canonical_baseline_available": False,
                            "status": "complete",
                            "warm": {"run_id": "challenger-b-one"},
                        },
                        {
                            "case_id": "task.dev.two",
                            "case_path": "tasks/two/case.json",
                            "canonical_baseline_available": False,
                            "status": "complete",
                            "warm": {"run_id": "challenger-b-two"},
                        },
                    ],
                },
            }

            def fake_load_json(path: Path) -> dict:
                if path.name == "selection.json":
                    return {
                        "comparisons": [
                            {"comparison_id": "comparison-one"},
                            {"comparison_id": "comparison-two"},
                        ]
                    }
                if path.name == "comparison.json":
                    return comparison_records[path.parent.name]
                if path.name == "sweep.json":
                    return sweep_records[path.parent.name]
                raise AssertionError(f"Unexpected JSON path: {path}")

            def fake_candidate(
                *, results_dir: Path, run_id: str, expected_case_id: str
            ) -> dict:
                del results_dir
                if run_id.startswith("challenger-a"):
                    model, digest = "challenger:a", "a" * 64
                elif run_id.startswith("challenger-b"):
                    model, digest = "challenger:b", "b" * 64
                else:
                    model, digest = "incumbent", "i" * 64
                return {
                    "run": {
                        "completed_at": "2026-09-02T10:00:00Z",
                        "case": {
                            "case_id": expected_case_id,
                            "case_version": "1.0.0",
                            "prompt_version": "1.0.0",
                            "source_sha256": "source-hash",
                        },
                        "deployment": {
                            "model": {"requested_name": model, "digest": digest}
                        },
                    },
                    "response_text": run_id,
                    "response_sha256": "response-hash",
                    "checks": {},
                    "checks_sha256": "checks-hash",
                }

            candidate_counts: list[int] = []

            def fake_create_bundle(**kwargs: object) -> None:
                candidates = kwargs["candidates"]
                assert isinstance(candidates, list)
                candidate_counts.append(len(candidates))

            with (
                patch(
                    "local_llm_benchmark.challenger.load_json",
                    side_effect=fake_load_json,
                ),
                patch(
                    "local_llm_benchmark.challenger.load_case",
                    side_effect=lambda _root, path: {
                        "case": {
                            "case_id": f"task.dev.{path.parent.name}",
                            "case_version": "1.0.0",
                            "prompt": {"version": "1.0.0"},
                        },
                        "source_hash": "source-hash",
                    },
                ),
                patch(
                    "local_llm_benchmark.challenger._load_run_candidate",
                    side_effect=fake_candidate,
                ),
                patch(
                    "local_llm_benchmark.challenger.create_batch_judge_bundle",
                    side_effect=fake_create_bundle,
                ),
                patch("local_llm_benchmark.challenger.sha256_file", return_value="hash"),
            ):
                result = assemble_challenger_bundle_batch(
                    repo_root,
                    ChallengerBundleConfig(
                        sweep_dirs=(Path("sweep-a"), Path("sweep-b")),
                        selection_path=Path("selection.json"),
                        comparisons_dir=Path("comparisons"),
                        results_dir=Path("runs"),
                        output_dir=Path("output"),
                    ),
                )

        self.assertEqual(candidate_counts, [3, 4])
        self.assertIsNone(result["candidate_count_per_case"])
        self.assertEqual(result["minimum_candidate_count"], 3)
        self.assertEqual(result["maximum_candidate_count"], 4)


if __name__ == "__main__":
    unittest.main()
