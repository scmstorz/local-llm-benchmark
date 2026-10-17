from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from local_llm_benchmark.multi_format_canonical import (
    CanonicalRunConfig,
    execute_canonical_run,
    finalize_canonical_run,
    load_canonical_condition,
    parse_final_object,
    prepare_canonical_run,
)
from local_llm_benchmark.runner import load_json


REPO_ROOT = Path(__file__).resolve().parents[1]


class MultiFormatCanonicalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.results = REPO_ROOT / "results"
        self.results.mkdir(exist_ok=True)

    def test_condition_is_tool_free_and_contains_fifteen_records(self) -> None:
        loaded = load_canonical_condition(REPO_ROOT)
        self.assertEqual(loaded["condition"]["track"], "A")
        self.assertFalse(loaded["condition"]["candidate_boundary"]["tools_available"])
        self.assertEqual(len(loaded["canonical"]["evidence_records"]), 15)

    def test_prepare_builds_one_schema_constrained_request_without_inference(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            result = prepare_canonical_run(
                REPO_ROOT,
                CanonicalRunConfig(
                    model="qwen3.8:27b-mlx",
                    results_dir=Path(temporary).relative_to(REPO_ROOT),
                ),
            )
            run_dir = Path(result["run_dir"])
            record = load_json(run_dir / "run.json")
            request = load_json(run_dir / "request.json")
            self.assertEqual(record["case"]["canonical_record_count"], 15)
            self.assertEqual(record["execution_boundary"]["inference_requests_made"], 0)
            self.assertEqual(request["model"], "qwen3.8:27b-mlx")
            self.assertEqual(request["format"]["type"], "object")
            self.assertIn("Frozen canonical extraction", request["messages"][1]["content"])

    def test_response_parser_keeps_transport_separate(self) -> None:
        strict = parse_final_object('{"schema_version":"1.0.0"}')
        normalized = parse_final_object('Antwort: {"schema_version":"1.0.0"}')
        ambiguous = parse_final_object('{"a":1} {"b":2}')
        self.assertTrue(strict["strict_transport_compliance"])
        self.assertFalse(normalized["strict_transport_compliance"])
        self.assertEqual(normalized["normalization_kind"], "surrounding_text")
        self.assertEqual(ambiguous["failure_code"], "ambiguous_multiple_json_objects")

    def test_mocked_execution_and_hidden_verification_complete(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            result = prepare_canonical_run(
                REPO_ROOT,
                CanonicalRunConfig(
                    model="qwen3.8:27b-mlx",
                    results_dir=Path(temporary).relative_to(REPO_ROOT),
                ),
            )
            run_dir = Path(result["run_dir"])
            case = load_canonical_condition(REPO_ROOT)["case"]
            reference = load_json(case["reference_report_path"])
            client = MagicMock()
            client.version.return_value = {"version": "0.33.2"}
            client.list_models.return_value = {
                "models": [
                    {
                        "name": "qwen3.8:27b-mlx",
                        "digest": "a" * 64,
                        "size": 1,
                    }
                ]
            }
            client.show_model.return_value = {
                "template": "template",
                "capabilities": ["completion"],
                "parameters": "",
            }

            def turn(_client: object, _payload: object, stream_path: Path) -> dict:
                stream_path.write_text('{"done":true}\n', encoding="utf-8")
                return {
                    "content": json.dumps(reference, ensure_ascii=False),
                    "thinking": "",
                    "wall_time_seconds": 0.1,
                    "time_to_first_content_seconds": 0.01,
                    "final_event": {
                        "done": True,
                        "done_reason": "stop",
                        "prompt_eval_count": 100,
                        "eval_count": 50,
                        "eval_duration": 1_000_000_000,
                        "load_duration": 10,
                    },
                }

            with patch(
                "local_llm_benchmark.multi_format_canonical.OllamaClient",
                return_value=client,
            ), patch(
                "local_llm_benchmark.multi_format_canonical._collect_ollama_turn",
                side_effect=turn,
            ):
                executed = execute_canonical_run(REPO_ROOT, run_dir)
            self.assertTrue(executed["runtime_success"])
            completed = finalize_canonical_run(REPO_ROOT, run_dir)
            self.assertTrue(completed["semantic_verified_success"])
            self.assertTrue(completed["strict_transport_compliance"])
            record = load_json(run_dir / "run.json")
            self.assertTrue(record["execution_boundary"]["hidden_verification_executed"])


if __name__ == "__main__":
    unittest.main()
