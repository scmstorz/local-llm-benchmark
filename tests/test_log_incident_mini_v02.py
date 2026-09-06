from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from local_llm_benchmark.log_incident_mini_v02 import (
    MiniLogV02StartConfig,
    _validated_definition,
    call_mini_log_v02_model,
    finalize_mini_log_v02_run,
    load_mini_log_v02_case,
    load_mini_log_v02_harness,
    start_mini_log_v02_run,
    step_mini_log_v02_action,
)
from local_llm_benchmark.runner import RunnerError, load_json, sha256_file, write_json


REPO_ROOT = Path(__file__).resolve().parents[1]
V1_CASE = Path(
    "tasks/agentic/log-incident-analysis/checkout-pool-regression/case.json"
)


class MiniLogV02HarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        harness = load_mini_log_v02_harness(REPO_ROOT)
        self.cases = [Path(item["case_path"]) for item in harness["protocol"]["task_subset"]]

    def _start(self, root: Path, case_path: Path) -> Path:
        result = start_mini_log_v02_run(
            REPO_ROOT,
            MiniLogV02StartConfig(
                model="not-contacted:test",
                case_path=case_path,
                results_dir=root,
            ),
        )
        self.assertEqual(result["inference_requests_made"], 0)
        return Path(result["run_dir"])

    def _fake_response(self, run_dir: Path, response: dict[str, object]) -> None:
        record = load_json(run_dir / "run.json")
        response_path = run_dir / "turns/001-response.txt"
        response_path.parent.mkdir(parents=True, exist_ok=True)
        response_path.write_text(json.dumps(response) + "\n", encoding="utf-8")
        record["state"] = "awaiting_action"
        record["artifacts"]["pending_request"] = None
        record["artifacts"]["pending_request_sha256"] = None
        record["trajectory"]["agent_turns"] = 1
        record["turns"] = [
            {
                "turn": 1,
                "response": "turns/001-response.txt",
                "response_sha256": sha256_file(response_path),
                "action": None,
                "action_status": "pending",
            }
        ]
        write_json(run_dir / "run.json", record)

    def test_harness_selects_three_unique_v2_cases(self) -> None:
        harness = load_mini_log_v02_harness(REPO_ROOT)
        subset = harness["protocol"]["task_subset"]
        self.assertEqual(len(subset), 3)
        self.assertEqual(len({item["case_id"] for item in subset}), 3)
        self.assertEqual(harness["harness"]["actions"], ["read_file", "finish_report"])
        self.assertTrue(
            harness["isolation_profile"]["workspace"]["other_case_fixtures_absent"]
        )

    def test_every_case_prepares_only_its_manifest_without_inference(self) -> None:
        expected_counts = [6, 6, 7]
        with tempfile.TemporaryDirectory() as temporary:
            for case_path, expected_count in zip(self.cases, expected_counts, strict=True):
                with self.subTest(case=case_path):
                    run_dir = self._start(Path(temporary), case_path)
                    record = load_json(run_dir / "run.json")
                    request = load_json(run_dir / record["artifacts"]["pending_request"])
                    self.assertEqual(record["contamination_check"]["file_count"], expected_count)
                    self.assertTrue(record["execution_boundary"]["selected_case_only"])
                    self.assertEqual(record["execution_boundary"]["inference_requests_made"], 0)
                    self.assertNotIn("ground-truth", json.dumps(request))
                    self.assertNotIn("reference-report", json.dumps(request))

    def test_cross_case_read_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self._start(Path(temporary), self.cases[1])
            self._fake_response(
                run_dir, {"action": "read_file", "path": "logs/payment-api.log"}
            )
            result = step_mini_log_v02_action(REPO_ROOT, run_dir)
            self.assertFalse(result["observation"]["ok"])
            self.assertEqual(
                result["observation"]["failure_code"], "path_not_candidate_visible"
            )

    def test_mocked_model_boundary_saves_one_action_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self._start(Path(temporary), self.cases[1])
            client = MagicMock()
            client.version.return_value = {"version": "mock"}
            client.list_models.return_value = {
                "models": [
                    {
                        "name": "not-contacted:test",
                        "digest": "0" * 64,
                        "size": 1,
                        "details": {},
                    }
                ]
            }
            client.show_model.return_value = {
                "capabilities": ["completion"],
                "parameters": "",
                "template": "mock",
            }

            def fake_turn(_client, _payload, stream_path):
                stream_path.write_text('{"mock":true}\n', encoding="utf-8")
                return {
                    "content": '{"action":"read_file","path":"logs/broker.log"}',
                    "thinking": "",
                    "wall_time_seconds": 0.01,
                    "time_to_first_content_seconds": 0.005,
                    "final_event": {
                        "done_reason": "stop",
                        "prompt_eval_count": 10,
                        "eval_count": 4,
                        "load_duration": 1,
                        "prompt_eval_duration": 1,
                        "eval_duration": 1,
                    },
                }

            with (
                patch(
                    "local_llm_benchmark.log_incident_mini_v02.OllamaClient",
                    return_value=client,
                ),
                patch(
                    "local_llm_benchmark.log_incident_mini_v02._collect_ollama_turn",
                    side_effect=fake_turn,
                ),
            ):
                result = call_mini_log_v02_model(REPO_ROOT, run_dir)
            record = load_json(run_dir / "run.json")
            self.assertEqual(result["state"], "awaiting_action")
            self.assertEqual(record["execution_boundary"]["inference_requests_made"], 1)
            self.assertEqual(record["turns"][0]["response_sha256"], sha256_file(run_dir / "turns/001-response.txt"))

    def test_every_reference_can_finish_and_verify(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            for case_path in self.cases:
                with self.subTest(case=case_path):
                    run_dir = self._start(Path(temporary), case_path)
                    loaded = load_mini_log_v02_case(REPO_ROOT, case_path)
                    report = load_json(loaded["reference_report_path"])
                    self._fake_response(
                        run_dir, {"action": "finish_report", "report": report}
                    )
                    stopped = step_mini_log_v02_action(REPO_ROOT, run_dir)
                    result = finalize_mini_log_v02_run(REPO_ROOT, run_dir)
                    self.assertEqual(stopped["termination_reason"], "finish_report")
                    self.assertTrue(result["verified_success"])
                    self.assertEqual(result["verification"]["essential_pass_count"], 14)

    def test_v1_case_is_not_silently_admitted(self) -> None:
        with self.assertRaisesRegex(RunnerError, "v0.2"):
            load_mini_log_v02_case(REPO_ROOT, V1_CASE)

    def test_definition_hash_mismatch_blocks_continuation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self._start(Path(temporary), self.cases[0])
            record = load_json(run_dir / "run.json")
            record["harness"]["action_schema_sha256"] = "0" * 64
            with self.assertRaisesRegex(RunnerError, "action_schema_sha256"):
                _validated_definition(REPO_ROOT, record)


if __name__ == "__main__":
    unittest.main()
