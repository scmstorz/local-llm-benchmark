from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_llm_benchmark.log_incident_pi import (
    PiLogPrepareConfig,
    _verify_workspace,
    build_pi_log_policy,
    build_pi_log_settings,
    execute_pi_log_run,
    finalize_pi_log_run,
    load_pi_log_case,
    parse_final_report_text,
    prepare_pi_log_run,
    summarize_pi_log_trajectory,
)
from local_llm_benchmark.macos_sandbox import SeatbeltCommandResult
from local_llm_benchmark.macos_sandbox_log import validate_pi_log_seatbelt
from local_llm_benchmark.runner import load_json, sha256_file, write_json


REPO_ROOT = Path(__file__).resolve().parents[1]
CASE_PATH = Path(
    "tasks/agentic/log-incident-analysis/checkout-pool-regression/case.json"
)


class PiLogHarnessTests(unittest.TestCase):
    def _prepare(self, directory: Path) -> Path:
        result = prepare_pi_log_run(
            REPO_ROOT,
            PiLogPrepareConfig(
                model="not-contacted:test",
                case_path=CASE_PATH,
                results_dir=directory,
            ),
        )
        return Path(result["run_dir"])

    def test_harness_pins_pi_and_exposes_only_read(self) -> None:
        loaded = load_pi_log_case(REPO_ROOT, CASE_PATH)

        self.assertEqual(loaded["harness"]["harness_id"], "pi-log-v0.1")
        self.assertEqual(loaded["observed_version"], "0.84.4")
        self.assertEqual(loaded["harness"]["integration"]["tools"], ["read"])
        self.assertEqual(
            loaded["capability_inventory"]["unavailable_capabilities"][:3],
            ["filesystem_write", "shell", "code_execution"],
        )

    def test_settings_and_policy_have_time_boundary_but_no_effort_caps(self) -> None:
        loaded = load_pi_log_case(REPO_ROOT, CASE_PATH)
        settings = build_pi_log_settings("example:model", loaded["protocol"])
        policy = build_pi_log_policy(
            loaded, Path("/tmp/workspace"), Path("/tmp/audit.jsonl")
        )

        self.assertEqual(settings["retry"]["provider"]["timeoutMs"], 180_000)
        self.assertFalse(settings["retry"]["enabled"])
        self.assertEqual(policy["allowed_tools"], ["read"])
        self.assertEqual(policy["maximum_file_reads"], 40)
        for forbidden in (
            "writable_paths",
            "public_test_command",
            "maximum_file_writes",
            "maximum_public_test_runs",
            "maximum_agent_turns",
            "maximum_total_output_tokens",
        ):
            self.assertNotIn(forbidden, policy)

    def test_prepare_is_no_inference_and_creates_read_only_invocation(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._prepare(Path(temporary))
            record = load_json(run_dir / "run.json")
            invocation = load_json(run_dir / "pi-invocation.json")
            policy = load_json(run_dir / "pi-policy.json")
            sandbox = load_json(run_dir / "pi-log-sandbox.json")
            profile = (run_dir / "pi-log-sandbox.sb").read_text(encoding="utf-8")

        tools_index = invocation["argv"].index("--tools")
        self.assertEqual(invocation["argv"][tools_index + 1], "read")
        self.assertNotIn("write", invocation["argv"])
        self.assertNotIn("edit", invocation["argv"])
        self.assertNotIn("bash", invocation["argv"])
        self.assertEqual(policy["allowed_tools"], ["read"])
        self.assertTrue(record["contamination_check"]["passed"])
        self.assertEqual(record["contamination_check"]["file_count"], 6)
        self.assertEqual(record["execution_boundary"]["inference_requests_made"], 0)
        self.assertFalse(record["execution_boundary"]["candidate_code_executed"])
        self.assertFalse(sandbox["candidate_workspace_writable"])
        self.assertEqual(len(sandbox["allowed_processes"]), 1)
        self.assertNotIn("/bin/bash", profile)
        self.assertIn("Final JSON Schema", invocation["argv"][-1])

    def test_mocked_seatbelt_acceptance_has_nine_no_inference_checks(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._prepare(Path(temporary))
            with (
                patch(
                    "local_llm_benchmark.macos_sandbox_log.run_seatbelt_command",
                    return_value=SeatbeltCommandResult(0, "", ""),
                ),
                patch(
                    "local_llm_benchmark.macos_sandbox_log._temporary_loopback_probe",
                    return_value=(None, None),
                ),
            ):
                result = validate_pi_log_seatbelt(run_dir)
            record = load_json(run_dir / "run.json")

        self.assertTrue(result["passed"])
        self.assertEqual(len(result["checks"]), 9)
        self.assertEqual(result["inference_requests_made"], 0)
        self.assertTrue(record["execution_boundary"]["sandbox_acceptance_passed"])
        self.assertIn(
            "candidate_workspace_write_denied",
            {item["check_id"] for item in result["checks"]},
        )
        self.assertIn(
            "external_network_denied",
            {item["check_id"] for item in result["checks"]},
        )

    def test_final_report_parser_does_not_repair_fences_or_prose(self) -> None:
        self.assertEqual(parse_final_report_text('{"x":1}')["status"], "valid")
        self.assertEqual(parse_final_report_text("[]")["failure_code"], "final_json_not_object")
        self.assertEqual(
            parse_final_report_text('```json\n{"x":1}\n```')["failure_code"],
            "malformed_final_json",
        )
        self.assertEqual(
            parse_final_report_text('Result: {"x":1}')["failure_code"],
            "malformed_final_json",
        )

    def test_trajectory_extracts_final_text_and_read_telemetry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            events = root / "events.jsonl"
            audit = root / "audit.jsonl"
            events.write_text(
                json.dumps(
                    {
                        "type": "agent_end",
                        "willRetry": False,
                        "messages": [
                            {
                                "role": "assistant",
                                "content": [{"type": "text", "text": '{"x":1}'}],
                                "stopReason": "stop",
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            audit.write_text(
                json.dumps(
                    {
                        "kind": "agent_end",
                        "counts": {
                            "agent_turns": 3,
                            "tool_calls": 2,
                            "failed_tool_calls": 0,
                            "file_reads": 2,
                            "repeated_file_reads": 1,
                            "input_tokens": 123,
                            "output_tokens": 45,
                        },
                        "read_paths": {"logs/payment-api.log": 2},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            trajectory, final_text = summarize_pi_log_trajectory(events, audit, 12.5)

        self.assertTrue(trajectory["agent_end_valid"])
        self.assertEqual(trajectory["agent_turns"], 3)
        self.assertEqual(trajectory["repeated_file_reads"], 1)
        self.assertEqual(trajectory["read_paths"], {"logs/payment-api.log": 2})
        self.assertEqual(final_text, '{"x":1}')

    def test_mocked_live_path_extracts_report_without_executing_candidate_code(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._prepare(Path(temporary))
            with (
                patch(
                    "local_llm_benchmark.macos_sandbox_log.run_seatbelt_command",
                    return_value=SeatbeltCommandResult(0, "", ""),
                ),
                patch(
                    "local_llm_benchmark.macos_sandbox_log._temporary_loopback_probe",
                    return_value=(None, None),
                ),
            ):
                validate_pi_log_seatbelt(run_dir)
            loaded = load_pi_log_case(REPO_ROOT, CASE_PATH)
            report = load_json(loaded["reference_report_path"])
            audit_path = run_dir / "pi-policy-audit.jsonl"

            class FakeProcess:
                pid = 12345

                def __init__(self, *args, **kwargs):
                    kwargs["stdout"].write(
                        json.dumps(
                            {
                                "type": "agent_end",
                                "messages": [
                                    {
                                        "role": "assistant",
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": json.dumps(report),
                                            }
                                        ],
                                        "stopReason": "stop",
                                    }
                                ],
                                "willRetry": False,
                            }
                        )
                        + "\n"
                    )
                    audit_path.write_text(
                        json.dumps(
                            {
                                "kind": "agent_end",
                                "counts": {
                                    "agent_turns": 2,
                                    "tool_calls": 1,
                                    "failed_tool_calls": 0,
                                    "file_reads": 1,
                                    "repeated_file_reads": 0,
                                    "input_tokens": 100,
                                    "output_tokens": 20,
                                },
                                "read_paths": {"logs/payment-api.log": 1},
                            }
                        )
                        + "\n",
                        encoding="utf-8",
                    )

                def wait(self, timeout=None):
                    return 0

            original_popen = subprocess.Popen

            def selective_popen(*args, **kwargs):
                if hasattr(kwargs.get("stdout"), "write"):
                    return FakeProcess(*args, **kwargs)
                return original_popen(*args, **kwargs)

            with patch(
                "local_llm_benchmark.log_incident_pi.subprocess.Popen",
                side_effect=selective_popen,
            ):
                result = execute_pi_log_run(REPO_ROOT, run_dir)
            record = load_json(run_dir / "run.json")

        self.assertTrue(result["runtime_success"])
        self.assertTrue(result["agent_termination_valid"])
        self.assertEqual(result["final_report_parse_status"], "valid")
        self.assertEqual(record["trajectory"]["file_reads"], 1)
        self.assertFalse(record["execution_boundary"]["candidate_code_executed"])
        self.assertFalse(record["execution_boundary"]["candidate_commands_executed"])
        self.assertFalse(record["execution_boundary"]["candidate_workspace_changed"])

    def test_workspace_integrity_detects_a_candidate_file_change(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._prepare(Path(temporary))
            loaded = load_pi_log_case(REPO_ROOT, CASE_PATH)
            workspace = run_dir / "workspace"
            self.assertTrue(_verify_workspace(workspace, loaded)["passed"])
            (workspace / "logs/payment-api.log").write_text("changed\n", encoding="utf-8")
            self.assertFalse(_verify_workspace(workspace, loaded)["passed"])

    def test_finalize_reference_report_keeps_outcomes_separate(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._prepare(Path(temporary))
            loaded = load_pi_log_case(REPO_ROOT, CASE_PATH)
            report = load_json(loaded["reference_report_path"])
            response_path = run_dir / "candidate-response.txt"
            report_path = run_dir / "candidate-report.json"
            events_path = run_dir / "pi-events.jsonl"
            stderr_path = run_dir / "pi-stderr.txt"
            audit_path = run_dir / "pi-policy-audit.jsonl"
            response_path.write_text(json.dumps(report) + "\n", encoding="utf-8")
            write_json(report_path, report)
            events_path.write_text('{"type":"agent_end"}\n', encoding="utf-8")
            stderr_path.write_text("", encoding="utf-8")
            audit_path.write_text("", encoding="utf-8")
            record = load_json(run_dir / "run.json")
            record["state"] = "execution_complete_verification_pending"
            record["execution"] = {
                "runtime_success": True,
                "agent_termination_valid": True,
            }
            record["trajectory"] = {"termination_reason": "agent_end"}
            record["artifacts"].update(
                {
                    "candidate_response": response_path.name,
                    "candidate_response_sha256": sha256_file(response_path),
                    "candidate_report": report_path.name,
                    "candidate_report_sha256": sha256_file(report_path),
                    "execution_sha256": {
                        "events": sha256_file(events_path),
                        "stderr": sha256_file(stderr_path),
                        "policy_audit": sha256_file(audit_path),
                    },
                }
            )
            write_json(run_dir / "run.json", record)
            result = finalize_pi_log_run(REPO_ROOT, run_dir)

        self.assertTrue(result["runtime_success"])
        self.assertTrue(result["agent_termination_valid"])
        self.assertTrue(result["verifier_success"])
        self.assertTrue(result["verified_success"])
        self.assertEqual(result["verification"]["essential_pass_count"], 13)


if __name__ == "__main__":
    unittest.main()
