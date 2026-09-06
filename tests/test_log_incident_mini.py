from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from local_llm_benchmark.log_incident_mini import (
    MiniLogStartConfig,
    _validated_definition,
    finalize_mini_log_run,
    load_mini_log_case,
    parse_mini_log_action,
    start_mini_log_run,
    step_mini_log_action,
)
from local_llm_benchmark.runner import RunnerError, load_json, sha256_file, write_json


REPO_ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = Path(
    "tasks/agentic/log-incident-analysis/checkout-pool-regression/case.json"
)


class MiniLogHarnessTests(unittest.TestCase):
    def test_loads_complete_read_only_contract(self) -> None:
        loaded = load_mini_log_case(REPO_ROOT, CASE_PATH)
        self.assertEqual(loaded["harness"]["actions"], ["read_file", "finish_report"])
        self.assertFalse(
            loaded["isolation_profile"]["evaluation"]["candidate_code_executed"]
        )
        self.assertIn(
            "shell", loaded["capability_inventory"]["unavailable_capabilities"]
        )
        self.assertIsNone(
            loaded["protocol"]["normal_capability_limits"]["maximum_agent_turns"]
        )

    def test_parser_accepts_only_exact_actions(self) -> None:
        read = parse_mini_log_action(
            '{"action":"read_file","path":"logs/payment-api.log"}'
        )
        finish = parse_mini_log_action('{"action":"finish_report","report":{}}')
        write = parse_mini_log_action(
            '{"action":"write_file","path":"logs/payment-api.log","content":"x"}'
        )
        unsafe = parse_mini_log_action(
            '{"action":"read_file","path":"../reference/ground-truth.json"}'
        )
        extra = parse_mini_log_action(
            '{"action":"read_file","path":"logs/payment-api.log","extra":true}'
        )
        self.assertEqual(read["status"], "valid")
        self.assertEqual(finish["status"], "valid")
        self.assertEqual(write["status"], "invalid")
        self.assertEqual(unsafe["failure_code"], "unsafe_path")
        self.assertEqual(extra["status"], "invalid")

    def _start(self, root: Path) -> Path:
        result = start_mini_log_run(
            REPO_ROOT,
            MiniLogStartConfig(
                model="not-contacted:test",
                case_path=CASE_PATH,
                results_dir=root,
            ),
        )
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

    def test_start_creates_clean_manifest_bound_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self._start(Path(temporary))
            record = load_json(run_dir / "run.json")
            request = load_json(run_dir / record["artifacts"]["pending_request"])
            self.assertEqual(record["contamination_check"]["status"], "passed")
            self.assertEqual(record["contamination_check"]["file_count"], 6)
            self.assertFalse(record["execution_boundary"]["candidate_code_executed"])
            self.assertIn("format", request)
            serialized = json.dumps(request)
            self.assertNotIn("ground-truth.json", serialized)
            self.assertNotIn("reference-report.json", serialized)

    def test_read_action_returns_only_declared_file_and_records_telemetry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self._start(Path(temporary))
            self._fake_response(
                run_dir,
                {"action": "read_file", "path": "logs/payment-api.log"},
            )
            result = step_mini_log_action(REPO_ROOT, run_dir)
            record = load_json(run_dir / "run.json")
            self.assertTrue(result["observation"]["ok"])
            self.assertIn("PAY-", result["observation"]["content"])
            self.assertEqual(record["trajectory"]["file_reads"], 1)
            self.assertEqual(record["trajectory"]["tool_calls"], 1)
            self.assertEqual(record["state"], "awaiting_model")
            self.assertFalse(record["execution_boundary"]["candidate_writes_performed"])

    def test_non_visible_path_is_rejected_without_reading(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self._start(Path(temporary))
            self._fake_response(
                run_dir,
                {"action": "read_file", "path": "reference/ground-truth.json"},
            )
            result = step_mini_log_action(REPO_ROOT, run_dir)
            record = load_json(run_dir / "run.json")
            self.assertFalse(result["observation"]["ok"])
            self.assertEqual(
                result["observation"]["failure_code"], "path_not_candidate_visible"
            )
            self.assertEqual(record["trajectory"]["file_reads"], 0)
            self.assertEqual(record["trajectory"]["failed_tool_calls"], 1)

    def test_reference_finish_and_finalize_produce_verified_success(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self._start(Path(temporary))
            loaded = load_mini_log_case(REPO_ROOT, CASE_PATH)
            report = load_json(loaded["reference_report_path"])
            self._fake_response(
                run_dir, {"action": "finish_report", "report": report}
            )
            stopped = step_mini_log_action(REPO_ROOT, run_dir)
            result = finalize_mini_log_run(REPO_ROOT, run_dir)
            record = load_json(run_dir / "run.json")
            self.assertEqual(stopped["termination_reason"], "finish_report")
            self.assertTrue(result["verified_success"])
            self.assertEqual(result["verification"]["essential_pass_count"], 13)
            self.assertTrue(record["execution_boundary"]["hidden_verification_executed"])
            self.assertFalse(record["execution_boundary"]["candidate_code_executed"])

    def test_definition_hash_mismatch_blocks_continuation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = self._start(Path(temporary))
            record = load_json(run_dir / "run.json")
            record["harness"]["capability_inventory_sha256"] = "0" * 64
            with self.assertRaisesRegex(RunnerError, "capability_inventory_sha256"):
                _validated_definition(REPO_ROOT, record)


if __name__ == "__main__":
    unittest.main()
