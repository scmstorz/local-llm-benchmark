from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_llm_benchmark.log_incident_pi_v05 import (
    PiLogV05PrepareConfig,
    build_pi_log_v05_policy,
    execute_pi_log_v05_run,
    finalize_pi_log_v05_run,
    load_pi_log_v05_case,
    load_pi_log_v05_harness,
    prepare_pi_log_v05_run,
)
from local_llm_benchmark.macos_sandbox import SeatbeltCommandResult
from local_llm_benchmark.macos_sandbox_log import validate_pi_log_seatbelt
from local_llm_benchmark.runner import RunnerError, load_json, sha256_file, write_json


REPO_ROOT = Path(__file__).resolve().parents[1]
V1_CASE = Path(
    "tasks/agentic/log-incident-analysis/checkout-pool-regression/case.json"
)


class PiLogV05HarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        harness = load_pi_log_v05_harness(REPO_ROOT)
        self.cases = [Path(item["case_path"]) for item in harness["protocol"]["task_subset"]]

    def _prepare(self, directory: Path, case_path: Path) -> Path:
        result = prepare_pi_log_v05_run(
            REPO_ROOT,
            PiLogV05PrepareConfig(
                model="not-contacted:test",
                case_path=case_path,
                results_dir=directory,
            ),
        )
        self.assertEqual(result["inference_requests_made"], 0)
        return Path(result["run_dir"])

    def test_harness_pins_pi_and_three_unique_cases(self) -> None:
        loaded = load_pi_log_v05_harness(REPO_ROOT)
        subset = loaded["protocol"]["task_subset"]
        self.assertEqual(loaded["observed_version"], "0.84.4")
        self.assertEqual(loaded["harness"]["integration"]["tools"], ["read"])
        self.assertEqual(len(subset), 3)
        self.assertEqual(len({item["case_id"] for item in subset}), 3)
        self.assertTrue(
            loaded["protocol"]["outcome_model"][
                "supplemental_free_text_claim_review_required"
            ]
        )

    def test_every_case_prepares_selected_only_read_policy(self) -> None:
        expected_counts = [6, 6, 7]
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            for case_path, expected_count in zip(self.cases, expected_counts, strict=True):
                with self.subTest(case=case_path):
                    run_dir = self._prepare(Path(temporary), case_path)
                    record = load_json(run_dir / "run.json")
                    policy = load_json(run_dir / "pi-policy.json")
                    invocation = load_json(run_dir / "pi-invocation.json")
                    self.assertEqual(policy["policy_id"], "pi-log-readonly-v0.2")
                    self.assertEqual(policy["readable_paths"], record["case"]["candidate_visible_files"])
                    self.assertEqual(record["contamination_check"]["file_count"], expected_count)
                    self.assertEqual(record["execution_boundary"]["inference_requests_made"], 0)
                    self.assertTrue(record["execution_boundary"]["selected_case_only"])
                    tools_index = invocation["argv"].index("--tools")
                    self.assertEqual(invocation["argv"][tools_index + 1], "read")
                    self.assertNotIn("ground-truth", invocation["argv"][-1])

    def test_policy_has_time_boundary_and_no_effort_caps(self) -> None:
        loaded = load_pi_log_v05_case(REPO_ROOT, self.cases[0])
        policy = build_pi_log_v05_policy(
            loaded, Path("/tmp/workspace"), Path("/tmp/audit.jsonl")
        )
        self.assertEqual(policy["allowed_tools"], ["read"])
        self.assertEqual(policy["maximum_file_reads"], 40)
        for forbidden in (
            "writable_paths",
            "maximum_agent_turns",
            "maximum_total_output_tokens",
            "maximum_wall_time_seconds",
        ):
            self.assertNotIn(forbidden, policy)

    def test_mocked_seatbelt_acceptance_repeats_for_every_case(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            for case_path in self.cases:
                with self.subTest(case=case_path):
                    run_dir = self._prepare(Path(temporary), case_path)
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
                    self.assertTrue(result["passed"])
                    self.assertEqual(len(result["checks"]), 9)
                    self.assertEqual(result["inference_requests_made"], 0)

    def test_mocked_live_boundary_normalizes_report_without_candidate_code(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._prepare(Path(temporary), self.cases[2])
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
            loaded = load_pi_log_v05_case(REPO_ROOT, self.cases[2])
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
                                                "text": "```json\n"
                                                + json.dumps(report)
                                                + "\n```",
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
                                "read_paths": {"logs/time-monitor.log": 1},
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
                "local_llm_benchmark.log_incident_pi_v05.subprocess.Popen",
                side_effect=selective_popen,
            ):
                result = execute_pi_log_v05_run(REPO_ROOT, run_dir)
            record = load_json(run_dir / "run.json")

        self.assertTrue(result["runtime_success"])
        self.assertTrue(result["agent_termination_valid"])
        self.assertEqual(result["final_report_parse_status"], "valid")
        self.assertFalse(result["strict_transport_compliance"])
        self.assertTrue(result["response_normalization_applied"])
        self.assertFalse(record["execution_boundary"]["candidate_code_executed"])
        self.assertFalse(record["execution_boundary"]["candidate_workspace_changed"])

    def test_every_reference_can_finalize_with_outcomes_separate(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            for case_path in self.cases:
                with self.subTest(case=case_path):
                    run_dir = self._prepare(Path(temporary), case_path)
                    loaded = load_pi_log_v05_case(REPO_ROOT, case_path)
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
                    result = finalize_pi_log_v05_run(REPO_ROOT, run_dir)
                    self.assertTrue(result["runtime_success"])
                    self.assertTrue(result["agent_termination_valid"])
                    self.assertTrue(result["semantic_verifier_success"])
                    self.assertTrue(result["semantic_verified_success"])
                    self.assertTrue(result["verified_success"])
                    self.assertFalse(result["strict_transport_compliance"])
                    self.assertEqual(result["verification"]["essential_pass_count"], 15)

    def test_v1_case_is_not_silently_admitted(self) -> None:
        with self.assertRaisesRegex(RunnerError, "v0.5"):
            load_pi_log_v05_case(REPO_ROOT, V1_CASE)


if __name__ == "__main__":
    unittest.main()
