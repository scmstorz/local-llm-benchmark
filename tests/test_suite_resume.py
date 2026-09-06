import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_llm_benchmark.runner import (
    SuiteResumeConfig,
    preserve_interrupted_suite_case,
    resume_model_suite,
)


class FakeMetadataClient:
    def version(self) -> dict:
        return {"version": "0.32.15"}

    def list_models(self) -> dict:
        return {
            "models": [
                {"name": "model:a", "digest": "a" * 64, "capabilities": ["completion"]}
            ]
        }

    def list_running_models(self) -> dict:
        return {"models": []}

    def unload_model(self, model: str) -> dict:
        raise AssertionError(f"Nothing should be loaded, received {model}")


def loaded_case(case_id: str) -> dict:
    return {
        "case": {
            "case_id": case_id,
            "case_version": "1.0.0",
            "prompt": {"version": "1.0.0"},
        },
        "source_hash": "source-hash",
    }


class SuiteResumeTest(unittest.TestCase):
    def test_partial_case_is_preserved_before_a_fresh_pair(self) -> None:
        entry = {"position": 1, "case_path": "tasks/one/case.json"}
        original = {
            "position": 1,
            "case_id": "task.dev.one",
            "case_path": "tasks/one/case.json",
            "status": "running",
            "cold": {"run_id": "partial-cold"},
            "warm": None,
            "error": None,
            "interrupted_attempts": [],
        }

        replacement = preserve_interrupted_suite_case(
            original, entry, loaded_case("task.dev.one")
        )

        self.assertEqual(replacement["status"], "running")
        self.assertIsNone(replacement["cold"])
        self.assertEqual(replacement["resume_attempt"], 1)
        self.assertEqual(
            replacement["interrupted_attempts"][0]["cold"]["run_id"],
            "partial-cold",
        )
        self.assertEqual(
            replacement["interrupted_attempts"][0]["interruption_class"],
            "process_ended_before_case_terminal_state",
        )

    def test_resume_runs_only_unfinished_cases_and_never_retries_failures(self) -> None:
        methodology = {
            "temperature": 0.0,
            "seed": 42,
            "think": False,
            "num_predict": 100,
            "keep_alive": "10m",
            "timeout_seconds": 60.0,
        }
        suite_cases = [
            {
                "entry": {"position": position, "case_path": f"tasks/{name}/case.json"},
                "loaded_case": loaded_case(f"task.dev.{name}"),
            }
            for position, name in enumerate(("complete", "failed", "running"), 1)
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            repo_root = Path(temporary_directory)
            sweep_dir = repo_root / "results/sweeps/sweep-test"
            sweep_dir.mkdir(parents=True)
            record = {
                "schema_version": "1.0.0",
                "sweep_id": "sweep-test",
                "status": "running",
                "started_at": "2026-09-02T00:00:00Z",
                "completed_at": None,
                "suite": {
                    "suite_id": "suite-v1",
                    "suite_version": "1.0.0",
                    "manifest_path": "suite.json",
                    "manifest_sha256": "suite-hash",
                },
                "deployment": {
                    "model": "model:a",
                    "digest": "a" * 64,
                    "ollama_version": "0.32.15",
                },
                "methodology": dict(methodology),
                "case_count": 3,
                "complete_case_count": 1,
                "failed_case_count": 1,
                "quality_candidate_count": 1,
                "cases": [
                    {
                        "position": 1,
                        "case_id": "task.dev.complete",
                        "case_path": "tasks/complete/case.json",
                        "status": "complete",
                        "cold": {"run_id": "cold-complete"},
                        "warm": {"run_id": "warm-complete"},
                    },
                    {
                        "position": 2,
                        "case_id": "task.dev.failed",
                        "case_path": "tasks/failed/case.json",
                        "status": "failed",
                        "cold": None,
                        "warm": None,
                        "error": {"type": "OllamaError", "message": "preserve me"},
                    },
                    {
                        "position": 3,
                        "case_id": "task.dev.running",
                        "case_path": "tasks/running/case.json",
                        "status": "running",
                        "cold": {"run_id": "partial-cold"},
                        "warm": None,
                        "error": None,
                    },
                ],
                "final_running_models": None,
                "artifacts": {"candidate_map": "candidate-map.json"},
            }
            (sweep_dir / "sweep.json").write_text(
                json.dumps(record), encoding="utf-8"
            )
            loaded_suite = {
                "manifest": {
                    "suite_id": "suite-v1",
                    "suite_version": "1.0.0",
                    "methodology": methodology,
                },
                "path": repo_root / "suite.json",
                "sha256": "suite-hash",
                "cases": suite_cases,
            }

            def complete_pair(**kwargs: object) -> dict:
                case_record = kwargs["case_record"]
                assert isinstance(case_record, dict)
                case_record["cold"] = {"run_id": "fresh-cold"}
                case_record["warm"] = {"run_id": "fresh-warm"}
                case_record["status"] = "complete"
                return {
                    "candidate_id": "candidate-fresh",
                    "model": "model:a",
                    "case_id": "task.dev.running",
                    "run_id": "fresh-warm",
                    "measurement_phase": "warm",
                }

            with (
                patch(
                    "local_llm_benchmark.runner.load_suite_manifest",
                    return_value=loaded_suite,
                ),
                patch(
                    "local_llm_benchmark.runner.OllamaClient",
                    return_value=FakeMetadataClient(),
                ),
                patch(
                    "local_llm_benchmark.runner._execute_suite_case_pair",
                    side_effect=complete_pair,
                ) as execute,
                patch(
                    "local_llm_benchmark.runner._suite_candidate_mapping",
                    return_value={"candidate-fresh": {"run_id": "fresh-warm"}},
                ),
            ):
                result = resume_model_suite(
                    repo_root,
                    SuiteResumeConfig(sweep_dir=sweep_dir),
                )

            persisted = json.loads(
                (sweep_dir / "sweep.json").read_text(encoding="utf-8")
            )
            private_map = json.loads(
                (sweep_dir / "candidate-map.json").read_text(encoding="utf-8")
            )

        self.assertEqual(execute.call_count, 1)
        self.assertEqual(result["status"], "complete_with_failures")
        self.assertEqual(persisted["complete_case_count"], 2)
        self.assertEqual(persisted["failed_case_count"], 1)
        failed = persisted["cases"][1]
        self.assertEqual(failed["error"]["message"], "preserve me")
        resumed = persisted["cases"][2]
        self.assertEqual(resumed["warm"]["run_id"], "fresh-warm")
        self.assertEqual(
            resumed["interrupted_attempts"][0]["cold"]["run_id"], "partial-cold"
        )
        history = persisted["resume_history"][0]
        self.assertEqual(history["resumed_case_ids"], ["task.dev.running"])
        self.assertEqual(
            history["failed_case_ids_not_retried"], ["task.dev.failed"]
        )
        self.assertEqual(
            private_map["private_model_mapping"],
            {"candidate-fresh": {"run_id": "fresh-warm"}},
        )


if __name__ == "__main__":
    unittest.main()
