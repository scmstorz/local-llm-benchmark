import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_llm_benchmark.agentic import (
    MiniAgentStartConfig,
    call_mini_agent_model,
    execute_mini_agent_action,
    load_mini_harness,
    load_track_b_case,
    parse_mini_agent_action,
    start_mini_agent_run,
    step_mini_agent_action,
    validate_local_ollama_host,
)
from local_llm_benchmark.coding import verify_coding_workspace
from local_llm_benchmark.ollama import OllamaError
from local_llm_benchmark.runner import RunnerError
from tests.test_coding import (
    REFERENCE_PHP_CHECKOUT_FILE,
    REFERENCE_PHP_RETRY_POLICY_FILE,
)


PHP_CASE_PATH = Path("tasks/coding/dev/php-payment-result-migration/case.json")
ASYNC_CASE_PATH = Path("tasks/coding/dev/async-cache-coalescing/case.json")
PAGINATION_CASE_PATH = Path(
    "tasks/coding/dev/pagination-cycle-guard/case-whole-file-v1.2.json"
)
MINI_V01_PATH = Path("tasks/coding/track-b/mini-v0.1.json")


class MiniAgentContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path.cwd().resolve()

    def test_v02_harness_selects_two_cases_and_defers_pagination(self) -> None:
        loaded = load_mini_harness(self.repo_root)
        selected = loaded["protocol"]["task_subset"]

        self.assertEqual(loaded["harness"]["harness_id"], "mini-v0.2")
        self.assertEqual(
            loaded["harness"]["status"], "qualified_for_capability_sweep"
        )
        self.assertEqual(
            loaded["protocol"]["status"], "frozen_for_capability_sweep"
        )
        self.assertNotIn("maximum_agent_turns", loaded["protocol"]["budgets"])
        self.assertIsNotNone(loaded["action_schema"])
        self.assertEqual(len(selected), 2)
        self.assertEqual(
            {item["case_id"] for item in selected},
            {
                "coding.dev.async-cache-coalescing",
                "coding.dev.php-payment-result-migration",
            },
        )
        load_track_b_case(self.repo_root, PHP_CASE_PATH)
        load_track_b_case(self.repo_root, ASYNC_CASE_PATH)
        with self.assertRaisesRegex(RunnerError, "outside the selected Track B pilot"):
            load_track_b_case(self.repo_root, PAGINATION_CASE_PATH)

    def test_v01_harness_remains_loadable_with_its_frozen_turn_limit(self) -> None:
        loaded = load_mini_harness(self.repo_root, MINI_V01_PATH)

        self.assertEqual(loaded["harness"]["harness_id"], "mini-v0.1")
        self.assertEqual(loaded["protocol"]["budgets"]["maximum_agent_turns"], 12)
        self.assertIsNone(loaded["action_schema"])

    def test_action_parser_is_strict_and_never_repairs_markdown(self) -> None:
        valid = parse_mini_agent_action(
            '{"action":"read_file","path":"src/CheckoutService.php"}'
        )
        fenced = parse_mini_agent_action(
            '```json\n{"action":"run_public_tests"}\n```'
        )
        extra = parse_mini_agent_action(
            '{"action":"run_public_tests","command":"php tests/run.php"}'
        )

        self.assertEqual(valid["status"], "valid")
        self.assertEqual(fenced["failure_code"], "malformed_action")
        self.assertEqual(extra["failure_code"], "malformed_action")

    def test_track_b_accepts_only_loopback_ollama_origins(self) -> None:
        self.assertEqual(
            validate_local_ollama_host("http://127.0.0.1:11434/"),
            "http://127.0.0.1:11434",
        )
        self.assertEqual(
            validate_local_ollama_host("http://localhost:11434"),
            "http://localhost:11434",
        )
        with self.assertRaisesRegex(RunnerError, "non-loopback"):
            validate_local_ollama_host("http://example.com:11434")
        with self.assertRaisesRegex(RunnerError, "without path"):
            validate_local_ollama_host("http://127.0.0.1:11434/api")

    def test_tools_enforce_read_write_and_public_test_boundaries(self) -> None:
        loaded = load_track_b_case(self.repo_root, PHP_CASE_PATH)
        metrics = {
            "agent_turns": 0,
            "tool_calls": 0,
            "failed_tool_calls": 0,
            "protocol_errors": 0,
            "file_reads": 0,
            "file_writes": 0,
            "public_test_runs": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "active_wall_time_seconds": 0.0,
            "time_to_first_successful_public_verification_seconds": None,
        }
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "fixture"
            import shutil

            shutil.copytree(loaded["fixture_root"], workspace)
            visible = execute_mini_agent_action(
                self.repo_root,
                loaded,
                workspace,
                {"action": "read_file", "path": "src/CheckoutService.php"},
                metrics,
            )
            hidden = execute_mini_agent_action(
                self.repo_root,
                loaded,
                workspace,
                {
                    "action": "read_file",
                    "path": "verifier/hidden_tests.php",
                },
                metrics,
            )
            protected = execute_mini_agent_action(
                self.repo_root,
                loaded,
                workspace,
                {
                    "action": "write_file",
                    "path": "src/PaymentStatus.php",
                    "content": "<?php\n",
                },
                metrics,
            )
            public = execute_mini_agent_action(
                self.repo_root,
                loaded,
                workspace,
                {"action": "run_public_tests"},
                metrics,
            )

        self.assertTrue(visible["ok"])
        self.assertEqual(hidden["failure_code"], "tool_scope_violation")
        self.assertEqual(protected["failure_code"], "tool_scope_violation")
        self.assertFalse(public["ok"])
        self.assertFalse(public["hidden_tests_executed"])
        self.assertEqual(metrics["tool_calls"], 4)
        self.assertEqual(metrics["file_reads"], 1)
        self.assertEqual(metrics["file_writes"], 0)
        self.assertEqual(metrics["public_test_runs"], 1)

    def test_final_verifier_rejects_a_created_workspace_path(self) -> None:
        loaded = load_track_b_case(self.repo_root, PHP_CASE_PATH)
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "fixture"
            import shutil

            shutil.copytree(loaded["fixture_root"], workspace)
            (workspace / "src" / "unexpected.php").write_text("<?php\n", encoding="utf-8")
            result = verify_coding_workspace(
                self.repo_root,
                PHP_CASE_PATH,
                workspace,
            )

        self.assertFalse(result["verified_success"])
        self.assertEqual(result["failure_code"], "workspace_scope_violation")
        self.assertEqual(result["integrity"]["new_paths"], ["src/unexpected.php"])
        self.assertEqual(
            result["integrity"]["structure_violations"],
            ["src/unexpected.php"],
        )


class MiniAgentStateMachineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path.cwd().resolve()

    @staticmethod
    def _stream_for(action: dict[str, object]) -> list[dict[str, object]]:
        content = json.dumps(action, ensure_ascii=False, separators=(",", ":"))
        return [
            {
                "message": {"role": "assistant", "content": content},
                "done": False,
            },
            {
                "message": {"role": "assistant", "content": ""},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 200,
                "prompt_eval_duration": 1_000_000_000,
                "eval_count": 50,
                "eval_duration": 1_000_000_000,
                "load_duration": 1_000_000,
            },
        ]

    @staticmethod
    def _configure_client(client: object, stream: list[dict[str, object]]) -> None:
        client.version.return_value = {"version": "test"}
        client.list_models.return_value = {
            "models": [
                {
                    "name": "test-model:latest",
                    "digest": "test-digest",
                    "size": 1,
                    "details": {},
                }
            ]
        }
        client.show_model.return_value = {
            "capabilities": ["completion"],
            "parameters": "",
            "template": "test",
        }
        client.stream_chat.return_value = stream

    def test_split_model_and_action_steps_reach_verified_php_success(self) -> None:
        actions = [
            {
                "action": "write_file",
                "path": "src/CheckoutService.php",
                "content": REFERENCE_PHP_CHECKOUT_FILE,
            },
            {
                "action": "write_file",
                "path": "src/RetryPolicy.php",
                "content": REFERENCE_PHP_RETRY_POLICY_FILE,
            },
            {"action": "run_public_tests"},
            {"action": "finish", "summary": "Implemented and verified."},
        ]
        streams = [self._stream_for(action) for action in actions]

        with tempfile.TemporaryDirectory() as temporary:
            started = start_mini_agent_run(
                self.repo_root,
                MiniAgentStartConfig(
                    model="test-model:latest",
                    case_path=PHP_CASE_PATH,
                    results_dir=Path(temporary),
                ),
            )
            run_dir = Path(started["run_dir"])
            request = json.loads(
                (run_dir / "turns" / "001-request.json").read_text(encoding="utf-8")
            )
            schema = json.loads(
                Path("tasks/coding/track-b/schemas/mini-action-v0.2.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(request["format"], schema)
            with patch("local_llm_benchmark.agentic.OllamaClient") as client_type:
                client = client_type.return_value
                self._configure_client(client, streams[0])
                client.stream_chat.side_effect = streams

                for position, action in enumerate(actions, start=1):
                    model_result = call_mini_agent_model(self.repo_root, run_dir)
                    self.assertEqual(model_result["turn"], position)
                    step_result = step_mini_agent_action(self.repo_root, run_dir)
                    self.assertEqual(step_result.get("action", action["action"]), action["action"])

                client.version.assert_called_once()
                client.list_models.assert_called_once()
                client.show_model.assert_called_once()

            self.assertEqual(step_result["state"], "complete")
            self.assertEqual(step_result["termination_reason"], "finish_action")
            self.assertTrue(step_result["verifier_success"])
            self.assertTrue(step_result["verified_success"])
            self.assertEqual(step_result["trajectory_metrics"]["agent_turns"], 4)
            self.assertEqual(step_result["trajectory_metrics"]["tool_calls"], 3)
            self.assertEqual(step_result["trajectory_metrics"]["file_writes"], 2)
            self.assertEqual(step_result["trajectory_metrics"]["public_test_runs"], 1)

            record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(record["state"], "complete")
            self.assertTrue(record["outcome"]["verified_success"])
            self.assertIsNotNone(record["artifacts"]["candidate_files_manifest"])
            self.assertIsNotNone(record["artifacts"]["trajectory_sha256"])
            self.assertIsNotNone(record["artifacts"]["final_verification_sha256"])
            self.assertEqual(len(record["turns"]), 4)

    def test_v02_records_high_turn_count_without_using_it_as_a_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            started = start_mini_agent_run(
                self.repo_root,
                MiniAgentStartConfig(
                    model="test-model:latest",
                    case_path=PHP_CASE_PATH,
                    results_dir=Path(temporary),
                ),
            )
            run_dir = Path(started["run_dir"])
            record_path = run_dir / "run.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["trajectory_metrics"]["agent_turns"] = 99
            record_path.write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with patch("local_llm_benchmark.agentic.OllamaClient") as client_type:
                self._configure_client(
                    client_type.return_value,
                    self._stream_for({"action": "finish", "summary": "done"}),
                )
                model_result = call_mini_agent_model(self.repo_root, run_dir)

            self.assertEqual(model_result["turn"], 100)
            result = step_mini_agent_action(self.repo_root, run_dir)
            self.assertEqual(result["termination_reason"], "finish_action")

    def test_v01_still_enforces_its_historical_turn_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            started = start_mini_agent_run(
                self.repo_root,
                MiniAgentStartConfig(
                    model="test-model:latest",
                    case_path=PHP_CASE_PATH,
                    harness_path=MINI_V01_PATH,
                    results_dir=Path(temporary),
                ),
            )
            run_dir = Path(started["run_dir"])
            request = json.loads(
                (run_dir / "turns" / "001-request.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("format", request)
            record_path = run_dir / "run.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["trajectory_metrics"]["agent_turns"] = 12
            record_path.write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            with patch("local_llm_benchmark.agentic.OllamaClient") as client_type:
                with self.assertRaisesRegex(RunnerError, "turn budget"):
                    call_mini_agent_model(self.repo_root, run_dir)
                client_type.assert_not_called()

    def test_definition_drift_blocks_inference_before_contacting_ollama(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            started = start_mini_agent_run(
                self.repo_root,
                MiniAgentStartConfig(
                    model="test-model:latest",
                    case_path=PHP_CASE_PATH,
                    results_dir=Path(temporary),
                ),
            )
            run_dir = Path(started["run_dir"])
            record_path = run_dir / "run.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["harness"]["protocol_sha256"] = "0" * 64
            record_path.write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            with patch("local_llm_benchmark.agentic.OllamaClient") as client_type:
                with self.assertRaisesRegex(RunnerError, "definition changed"):
                    call_mini_agent_model(self.repo_root, run_dir)
                client_type.assert_not_called()

    def test_ollama_probe_failure_is_persisted_as_infrastructure_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            started = start_mini_agent_run(
                self.repo_root,
                MiniAgentStartConfig(
                    model="test-model:latest",
                    case_path=PHP_CASE_PATH,
                    results_dir=Path(temporary),
                ),
            )
            run_dir = Path(started["run_dir"])
            with patch("local_llm_benchmark.agentic.OllamaClient") as client_type:
                client_type.return_value.version.side_effect = OllamaError("offline")
                with self.assertRaisesRegex(OllamaError, "offline"):
                    call_mini_agent_model(self.repo_root, run_dir)

            record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            failure = json.loads(
                (run_dir / "failure.json").read_text(encoding="utf-8")
            )
            self.assertEqual(record["state"], "infrastructure_failed")
            self.assertEqual(record["outcome"]["runtime_failure_code"], "runtime_failure")
            self.assertEqual(failure["failure_phase"], "ollama_version")

    def test_message_tampering_blocks_action_before_workspace_change(self) -> None:
        action = {
            "action": "write_file",
            "path": "src/CheckoutService.php",
            "content": "<?php // should-not-be-installed\n",
        }
        with tempfile.TemporaryDirectory() as temporary:
            started = start_mini_agent_run(
                self.repo_root,
                MiniAgentStartConfig(
                    model="test-model:latest",
                    case_path=PHP_CASE_PATH,
                    results_dir=Path(temporary),
                ),
            )
            run_dir = Path(started["run_dir"])
            target = run_dir / "workspace" / "src" / "CheckoutService.php"
            original = target.read_text(encoding="utf-8")
            with patch("local_llm_benchmark.agentic.OllamaClient") as client_type:
                self._configure_client(client_type.return_value, self._stream_for(action))
                call_mini_agent_model(self.repo_root, run_dir)

            messages_path = run_dir / "messages.json"
            messages_path.write_text("[]\n", encoding="utf-8")
            with self.assertRaisesRegex(RunnerError, "messages hash mismatch"):
                step_mini_agent_action(self.repo_root, run_dir)
            self.assertEqual(target.read_text(encoding="utf-8"), original)

    def test_deleted_allowed_file_finishes_as_scope_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            started = start_mini_agent_run(
                self.repo_root,
                MiniAgentStartConfig(
                    model="test-model:latest",
                    case_path=PHP_CASE_PATH,
                    results_dir=Path(temporary),
                ),
            )
            run_dir = Path(started["run_dir"])
            with patch("local_llm_benchmark.agentic.OllamaClient") as client_type:
                self._configure_client(
                    client_type.return_value,
                    self._stream_for({"action": "finish", "summary": "done"}),
                )
                call_mini_agent_model(self.repo_root, run_dir)

            (run_dir / "workspace" / "src" / "CheckoutService.php").unlink()
            result = step_mini_agent_action(self.repo_root, run_dir)

            self.assertEqual(result["state"], "complete")
            self.assertFalse(result["verified_success"])
            self.assertEqual(result["failure_code"], "workspace_scope_violation")


if __name__ == "__main__":
    unittest.main()
