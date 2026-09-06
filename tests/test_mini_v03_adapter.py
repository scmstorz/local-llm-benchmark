import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_llm_benchmark.mini_v03_adapter import (
    MINI_V03_HARNESS_PATH,
    MiniV03StartConfig,
    call_mini_v03_model,
    finalize_mini_v03_run,
    load_mini_v03_case,
    load_mini_v03_harness,
    start_mini_v03_run,
    step_mini_v03_action,
)
from local_llm_benchmark.agentic import parse_mini_agent_action
from local_llm_benchmark.runner import RunnerError
from tests.test_coding import (
    REFERENCE_PHP_CHECKOUT_FILE,
    REFERENCE_PHP_RETRY_POLICY_FILE,
)


PHP_CASE = Path("tasks/coding/dev/php-payment-result-migration/case.json")
JS_CASE = Path("tasks/coding/dev/async-cache-coalescing/case.json")
PYTHON_CASE = Path(
    "tasks/coding/dev/pagination-cycle-guard/case-whole-file-v1.2.json"
)


def stream(content: str) -> list[dict[str, object]]:
    return [
        {"message": {"role": "assistant", "content": content}, "done": False},
        {
            "message": {"role": "assistant", "content": ""},
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 100,
            "prompt_eval_duration": 1_000_000_000,
            "eval_count": 20,
            "eval_duration": 1_000_000_000,
            "load_duration": 1_000_000,
        },
    ]


def action_stream(action: dict[str, object]) -> list[dict[str, object]]:
    return stream(json.dumps(action, ensure_ascii=False, separators=(",", ":")))


def configure_client(client: object, streams: list[list[dict[str, object]]]) -> None:
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
    client.stream_chat.side_effect = streams


class MiniV03ContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path.cwd().resolve()

    def test_protocol_matches_pi_time_boundary_and_selects_three_cases(self) -> None:
        loaded = load_mini_v03_harness(self.repo_root)
        limits = loaded["protocol"]["normal_capability_limits"]

        self.assertEqual(loaded["harness"]["harness_id"], "mini-v0.3")
        self.assertEqual(limits["maximum_active_wall_time_seconds"], 900)
        self.assertEqual(limits["provider_request_timeout_seconds"], 300)
        self.assertIsNone(limits["maximum_total_output_tokens"])
        self.assertIsNone(limits["maximum_agent_turns"])
        self.assertIsNone(limits["maximum_protocol_errors"])
        self.assertEqual(len(loaded["action_schema"]["oneOf"]), 5)
        for case in (PHP_CASE, JS_CASE, PYTHON_CASE):
            load_mini_v03_case(self.repo_root, case)

    def test_action_schema_covers_all_strict_protocol_variants(self) -> None:
        loaded = load_mini_v03_harness(self.repo_root)
        schema = loaded["action_schema"]
        observed = {
            branch["properties"]["action"]["const"] for branch in schema["oneOf"]
        }
        self.assertEqual(
            observed,
            {"read_file", "write_file", "replace_text", "run_public_tests", "finish"},
        )
        self.assertTrue(
            all(branch["additionalProperties"] is False for branch in schema["oneOf"])
        )

    def test_parser_accepts_all_actions_and_repairs_nothing(self) -> None:
        valid = [
            {"action": "read_file", "path": "src/file.py"},
            {"action": "write_file", "path": "src/file.py", "content": "x"},
            {
                "action": "replace_text",
                "path": "src/file.py",
                "old": "x",
                "new": "y",
            },
            {"action": "run_public_tests"},
            {"action": "finish", "summary": "done"},
        ]
        for action in valid:
            parsed = parse_mini_agent_action(json.dumps(action))
            self.assertEqual(parsed["status"], "valid")
        invalid = [
            "",
            '```json\n{"action":"run_public_tests"}\n```',
            '{"action":"run_public_tests","command":"pytest"}',
            '{"action":"unknown"}',
            "leading prose {\"action\":\"finish\",\"summary\":\"x\"}",
        ]
        for response in invalid:
            self.assertEqual(parse_mini_agent_action(response)["status"], "invalid")


class MiniV03StateMachineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path.cwd().resolve()

    def _start(self, temporary: str) -> Path:
        result = start_mini_v03_run(
            self.repo_root,
            MiniV03StartConfig(
                model="test-model:latest",
                case_path=PHP_CASE,
                results_dir=Path(temporary),
            ),
        )
        return Path(result["run_dir"])

    def test_reference_actions_reach_layered_verified_success(self) -> None:
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
            {"action": "finish", "summary": "done"},
        ]
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self._start(temporary)
            with patch(
                "local_llm_benchmark.mini_v03_adapter.OllamaClient"
            ) as client_type:
                configure_client(
                    client_type.return_value,
                    [action_stream(action) for action in actions],
                )
                for _action in actions:
                    call_mini_v03_model(self.repo_root, run_dir)
                    result = step_mini_v03_action(self.repo_root, run_dir)

            self.assertEqual(result["state"], "trajectory_complete_verification_pending")
            outcome = finalize_mini_v03_run(self.repo_root, run_dir)
            self.assertTrue(outcome["runtime_success"])
            self.assertTrue(outcome["agent_termination_valid"])
            self.assertTrue(outcome["verifier_success"])
            self.assertTrue(outcome["verified_success"])
            self.assertEqual(outcome["trajectory"]["model_requests"], 4)
            self.assertEqual(outcome["trajectory"]["file_writes"], 2)
            self.assertEqual(outcome["trajectory"]["public_test_runs"], 1)

    def test_malformed_action_is_preserved_and_can_be_corrected(self) -> None:
        malformed = '```json\n{"action":"run_public_tests"}\n```'
        finish = {"action": "finish", "summary": "corrected protocol"}
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self._start(temporary)
            with patch(
                "local_llm_benchmark.mini_v03_adapter.OllamaClient"
            ) as client_type:
                configure_client(
                    client_type.return_value,
                    [stream(malformed), action_stream(finish)],
                )
                call_mini_v03_model(self.repo_root, run_dir)
                first = step_mini_v03_action(self.repo_root, run_dir)
                self.assertEqual(first["action_status"], "protocol_error")
                call_mini_v03_model(self.repo_root, run_dir)
                second = step_mini_v03_action(self.repo_root, run_dir)

            self.assertEqual(second["termination_reason"], "finish_action")
            outcome = finalize_mini_v03_run(self.repo_root, run_dir)
            self.assertEqual(outcome["trajectory"]["protocol_errors"], 1)
            self.assertFalse(outcome["verifier_success"])
            self.assertEqual(outcome["failure_category"], "task_or_verification_failure")

    def test_turn_token_and_protocol_counts_do_not_terminate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self._start(temporary)
            record_path = run_dir / "run.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["trajectory"]["agent_turns"] = 500
            record["trajectory"]["output_tokens"] = 1_000_000
            record["trajectory"]["protocol_errors"] = 500
            record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
            with patch(
                "local_llm_benchmark.mini_v03_adapter.OllamaClient"
            ) as client_type:
                configure_client(
                    client_type.return_value,
                    [action_stream({"action": "finish", "summary": "done"})],
                )
                model = call_mini_v03_model(self.repo_root, run_dir)
                result = step_mini_v03_action(self.repo_root, run_dir)

            self.assertEqual(model["turn"], 501)
            self.assertEqual(result["termination_reason"], "finish_action")

    def test_active_time_terminates_before_another_model_request(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self._start(temporary)
            record_path = run_dir / "run.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["trajectory"]["active_wall_time_seconds"] = 900.0
            record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
            with patch(
                "local_llm_benchmark.mini_v03_adapter.OllamaClient"
            ) as client_type:
                result = call_mini_v03_model(self.repo_root, run_dir)
                client_type.assert_not_called()

            self.assertEqual(result["termination_reason"], "maximum_active_wall_time_exceeded")
            outcome = finalize_mini_v03_run(self.repo_root, run_dir)
            self.assertFalse(outcome["runtime_success"])
            self.assertEqual(outcome["failure_category"], "infrastructure_or_runtime_failure")

    def test_operation_ceiling_has_causal_precedence_over_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self._start(temporary)
            record_path = run_dir / "run.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["trajectory"]["public_test_runs"] = 30
            record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
            with patch(
                "local_llm_benchmark.mini_v03_adapter.OllamaClient"
            ) as client_type:
                configure_client(
                    client_type.return_value,
                    [action_stream({"action": "run_public_tests"})],
                )
                call_mini_v03_model(self.repo_root, run_dir)
                result = step_mini_v03_action(self.repo_root, run_dir)

            self.assertEqual(
                result["termination_reason"],
                "emergency_operation_safeguard_exceeded",
            )
            outcome = finalize_mini_v03_run(self.repo_root, run_dir)
            self.assertEqual(outcome["failure_category"], "agent_failure")
            self.assertEqual(
                outcome["failure_type"], "emergency_operation_safeguard_exceeded"
            )

    def test_provider_timeout_remains_primary_after_red_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self._start(temporary)
            with patch(
                "local_llm_benchmark.mini_v03_adapter.OllamaClient"
            ) as client_type:
                client_type.return_value.version.side_effect = TimeoutError("timed out")
                result = call_mini_v03_model(self.repo_root, run_dir)

            self.assertEqual(result["termination_reason"], "provider_request_timeout")
            outcome = finalize_mini_v03_run(self.repo_root, run_dir)
            self.assertFalse(outcome["verifier_success"])
            self.assertEqual(outcome["failure_type"], "provider_request_timeout")
            self.assertEqual(outcome["failure_category"], "infrastructure_or_runtime_failure")

    def test_incomplete_provider_stream_is_classified_separately(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self._start(temporary)
            with patch(
                "local_llm_benchmark.mini_v03_adapter.OllamaClient"
            ) as client_type:
                configure_client(
                    client_type.return_value,
                    [[{"message": {"role": "assistant", "content": "partial"}}]],
                )
                result = call_mini_v03_model(self.repo_root, run_dir)

            self.assertEqual(result["termination_reason"], "provider_stream_incomplete")
            outcome = finalize_mini_v03_run(self.repo_root, run_dir)
            self.assertEqual(outcome["failure_type"], "provider_stream_incomplete")
            self.assertEqual(outcome["trajectory"]["model_requests"], 1)

    def test_interrupted_model_call_is_checkpointed_before_contact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self._start(temporary)
            with patch(
                "local_llm_benchmark.mini_v03_adapter.OllamaClient"
            ) as client_type:
                configure_client(
                    client_type.return_value,
                    [action_stream({"action": "finish", "summary": "unused"})],
                )
                client_type.return_value.version.side_effect = KeyboardInterrupt()
                with self.assertRaises(KeyboardInterrupt):
                    call_mini_v03_model(self.repo_root, run_dir)

            record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(record["state"], "model_call_running")
            self.assertEqual(record["trajectory"]["model_requests"], 1)
            self.assertEqual(record["active_model_request"]["request_index"], 1)
            with self.assertRaisesRegex(RunnerError, "not awaiting"):
                call_mini_v03_model(self.repo_root, run_dir)

    def test_definition_drift_blocks_work(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self._start(temporary)
            record_path = run_dir / "run.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["harness"]["action_schema_sha256"] = "0" * 64
            record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(RunnerError, "definition changed"):
                call_mini_v03_model(self.repo_root, run_dir)

    def test_model_call_and_final_verification_are_separate_states(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self._start(temporary)
            with patch(
                "local_llm_benchmark.mini_v03_adapter.OllamaClient"
            ) as client_type:
                configure_client(
                    client_type.return_value,
                    [action_stream({"action": "finish", "summary": "done"})],
                )
                call_mini_v03_model(self.repo_root, run_dir)
                result = step_mini_v03_action(self.repo_root, run_dir)

            record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(result["state"], "trajectory_complete_verification_pending")
            self.assertFalse(record["execution_boundary"]["hidden_verification_executed"])
            finalize_mini_v03_run(self.repo_root, run_dir)
            record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            self.assertTrue(record["execution_boundary"]["hidden_verification_executed"])

    def test_default_path_is_stable(self) -> None:
        self.assertEqual(
            MINI_V03_HARNESS_PATH,
            Path("tasks/coding/track-b/mini-v0.3.json"),
        )


if __name__ == "__main__":
    unittest.main()
