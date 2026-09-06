import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_llm_benchmark.macos_sandbox import SeatbeltCommandResult
from local_llm_benchmark.macos_sandbox_v03 import validate_pi_v03_seatbelt
from local_llm_benchmark.pi_v03_adapter import (
    PiV03PrepareConfig,
    _summarize_pi_trajectory,
    _termination_reason,
    execute_pi_v03_agent_run,
    finalize_pi_v03_agent_run,
    load_pi_v03_harness,
    load_pi_v03_track_b_case,
    prepare_pi_v03_agent_run,
)
from local_llm_benchmark.runner import sha256_file


PHP_CASE = Path("tasks/coding/dev/php-payment-result-migration/case.json")
JAVASCRIPT_CASE = Path("tasks/coding/dev/async-cache-coalescing/case.json")
PYTHON_CASE = Path(
    "tasks/coding/dev/pagination-cycle-guard/case-whole-file-v1.2.json"
)


class PiV03AdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path.cwd().resolve()

    def test_qualified_harness_pins_pi_and_selects_three_languages(self) -> None:
        loaded = load_pi_v03_harness(self.repo_root)

        self.assertEqual(loaded["harness"]["harness_id"], "pi-v0.3")
        self.assertEqual(
            loaded["harness"]["status"], "qualified_for_capability_sweep"
        )
        self.assertEqual(loaded["observed_version"], "0.84.4")
        self.assertEqual(len(loaded["protocol"]["task_subset"]), 3)
        self.assertEqual(
            {
                item["case_id"] for item in loaded["protocol"]["task_subset"]
            },
            {
                "coding.dev.php-payment-result-migration",
                "coding.dev.async-cache-coalescing",
                "coding.dev.pagination-cycle-guard",
            },
        )
        load_pi_v03_track_b_case(self.repo_root, PHP_CASE)
        load_pi_v03_track_b_case(self.repo_root, JAVASCRIPT_CASE)
        load_pi_v03_track_b_case(self.repo_root, PYTHON_CASE)

    def test_python_preparation_resolves_runtime_and_applies_time_first_budget(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=self.repo_root / "results"
        ) as temporary:
            prepared = prepare_pi_v03_agent_run(
                self.repo_root,
                PiV03PrepareConfig(
                    model="qwen3.6:35b-a3b-mxfp8",
                    case_path=PYTHON_CASE,
                    results_dir=Path(temporary),
                ),
            )
            run_dir = Path(prepared["run_dir"])
            record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            policy = json.loads(
                (run_dir / "pi-policy.json").read_text(encoding="utf-8")
            )
            settings = json.loads(
                (run_dir / "pi-agent" / "settings.json").read_text(
                    encoding="utf-8"
                )
            )
            invocation = json.loads(
                (run_dir / "pi-invocation.json").read_text(encoding="utf-8")
            )
            sandbox = json.loads(
                (run_dir / "pi-sandbox.json").read_text(encoding="utf-8")
            )

        python = str(Path(sys.executable).resolve())
        self.assertEqual(prepared["inference_requests_made"], 0)
        self.assertFalse(prepared["candidate_code_executed"])
        self.assertEqual(record["harness"]["harness_id"], "pi-v0.3")
        self.assertEqual(invocation["timeout_seconds"], 900)
        self.assertEqual(invocation["timeout_clock"], "parent_process_monotonic_wait")
        self.assertEqual(settings["retry"]["provider"]["timeoutMs"], 300_000)
        self.assertEqual(settings["httpIdleTimeoutMs"], 300_000)
        self.assertFalse(settings["retry"]["enabled"])
        self.assertNotIn("maximum_agent_turns", policy)
        self.assertNotIn("maximum_total_output_tokens", policy)
        self.assertNotIn("maximum_wall_time_seconds", policy)
        self.assertEqual(policy["maximum_file_reads"], 200)
        self.assertEqual(policy["maximum_file_writes"], 100)
        self.assertEqual(policy["maximum_public_test_runs"], 30)
        self.assertTrue(policy["public_test_command"].startswith(python + " "))
        self.assertEqual(sandbox["public_test_executable"], python)
        self.assertIn(python, sandbox["allowed_processes"])
        self.assertEqual(
            policy["writable_paths"],
            [
                "src/paged_sync/__init__.py",
                "src/paged_sync/errors.py",
                "src/paged_sync/models.py",
                "src/paged_sync/sync.py",
            ],
        )

    def test_no_inference_seatbelt_acceptance_adds_runtime_probe(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=self.repo_root / "results"
        ) as temporary:
            prepared = prepare_pi_v03_agent_run(
                self.repo_root,
                PiV03PrepareConfig(
                    model="qwen3.8:27b-mlx",
                    case_path=PYTHON_CASE,
                    results_dir=Path(temporary),
                ),
            )
            run_dir = Path(prepared["run_dir"])
            base_codes = [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0]
            with (
                patch(
                    "local_llm_benchmark.macos_sandbox.run_seatbelt_command",
                    side_effect=[
                        SeatbeltCommandResult(code, "", "")
                        for code in base_codes
                    ],
                ),
                patch(
                    "local_llm_benchmark.macos_sandbox_v03.run_seatbelt_command",
                    return_value=SeatbeltCommandResult(0, "Python 3", ""),
                ),
            ):
                result = validate_pi_v03_seatbelt(run_dir)

            record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

        self.assertTrue(result["passed"])
        self.assertEqual(len(result["checks"]), 12)
        self.assertEqual(
            result["checks"][-1]["check_id"],
            "selected_public_test_runtime_starts",
        )
        self.assertEqual(result["inference_requests_made"], 0)
        self.assertFalse(result["candidate_code_executed"])
        self.assertTrue(record["execution_boundary"]["sandbox_acceptance_passed"])

    def test_live_path_uses_parent_timeout_and_defers_hidden_verification(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=self.repo_root / "results"
        ) as temporary:
            prepared = prepare_pi_v03_agent_run(
                self.repo_root,
                PiV03PrepareConfig(
                    model="qwen3.8:27b-mlx",
                    case_path=JAVASCRIPT_CASE,
                    results_dir=Path(temporary),
                ),
            )
            run_dir = Path(prepared["run_dir"])
            base_codes = [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0]
            with (
                patch(
                    "local_llm_benchmark.macos_sandbox.run_seatbelt_command",
                    side_effect=[
                        SeatbeltCommandResult(code, "", "")
                        for code in base_codes
                    ],
                ),
                patch(
                    "local_llm_benchmark.macos_sandbox_v03.run_seatbelt_command",
                    return_value=SeatbeltCommandResult(0, "v24", ""),
                ),
            ):
                validate_pi_v03_seatbelt(run_dir)

            audit_path = run_dir / "pi-policy-audit.jsonl"

            class FakeProcess:
                pid = 12345

                def __init__(self, *args, **kwargs):
                    kwargs["stdout"].write(
                        '{"type":"agent_start"}\n'
                        '{"type":"turn_start"}\n'
                        '{"type":"agent_end","messages":[{"role":"assistant","content":[],"stopReason":"stop"}],"willRetry":false}\n'
                    )
                    audit_path.write_text(
                        json.dumps(
                            {
                                "kind": "agent_end",
                                "counts": {
                                    "agent_turns": 1,
                                    "tool_calls": 0,
                                    "failed_tool_calls": 0,
                                    "file_reads": 0,
                                    "file_writes": 0,
                                    "public_test_runs": 0,
                                    "input_tokens": 100,
                                    "output_tokens": 20,
                                },
                            }
                        )
                        + "\n",
                        encoding="utf-8",
                    )

                def wait(self, timeout=None):
                    self.timeout = timeout
                    return 0

            original_popen = subprocess.Popen

            def selective_popen(*args, **kwargs):
                if hasattr(kwargs.get("stdout"), "write"):
                    return FakeProcess(*args, **kwargs)
                return original_popen(*args, **kwargs)

            with patch(
                "local_llm_benchmark.pi_v03_adapter.subprocess.Popen",
                side_effect=selective_popen,
            ):
                executed = execute_pi_v03_agent_run(self.repo_root, run_dir)

            record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

        self.assertTrue(executed["runtime_success"])
        self.assertTrue(executed["agent_termination_valid"])
        self.assertFalse(executed["hidden_verification_executed"])
        self.assertEqual(record["execution"]["timeout_seconds"], 900)
        self.assertEqual(
            record["execution"]["timeout_clock"], "parent_process_monotonic_wait"
        )
        self.assertEqual(record["trajectory"]["output_tokens"], 20)
        self.assertNotIn("verification", record)

    def test_emergency_safeguard_is_a_distinct_trajectory_signal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            events = root / "events.jsonl"
            audit = root / "audit.jsonl"
            events.write_text('{"type":"agent_start"}\n', encoding="utf-8")
            audit.write_text(
                json.dumps(
                    {
                        "kind": "tool_blocked",
                        "reason": "Emergency file-read safeguard exceeded.",
                        "terminate": True,
                        "counts": {"file_reads": 200},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            trajectory = _summarize_pi_trajectory(events, audit, 12.0)

        self.assertTrue(trajectory["emergency_safeguard_triggered"])
        self.assertEqual(
            trajectory["emergency_safeguard_reasons"],
            ["Emergency file-read safeguard exceeded."],
        )
        self.assertEqual(
            _termination_reason(
                timed_out=False,
                launch_error=None,
                returncode=1,
                trajectory=trajectory,
            ),
            "emergency_operation_safeguard_exceeded",
        )

    def test_provider_timeout_is_an_infrastructure_termination(self) -> None:
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
                                "stopReason": "error",
                                "errorMessage": "Request timed out.",
                                "content": [],
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            audit.write_text("", encoding="utf-8")

            trajectory = _summarize_pi_trajectory(events, audit, 300.4)
            reason = _termination_reason(
                timed_out=False,
                launch_error=None,
                returncode=0,
                trajectory=trajectory,
            )

        self.assertTrue(trajectory["provider_request_timed_out"])
        self.assertEqual(reason, "provider_request_timeout")

    def test_finalize_keeps_runtime_agent_and_verifier_outcomes_separate(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=self.repo_root / "results"
        ) as temporary:
            prepared = prepare_pi_v03_agent_run(
                self.repo_root,
                PiV03PrepareConfig(
                    model="qwen3.6:35b-a3b-mxfp8",
                    case_path=PHP_CASE,
                    results_dir=Path(temporary),
                ),
            )
            run_dir = Path(prepared["run_dir"])
            events = run_dir / "pi-events.jsonl"
            stderr = run_dir / "pi-stderr.txt"
            audit = run_dir / "pi-policy-audit.jsonl"
            events.write_text('{"type":"agent_end"}\n', encoding="utf-8")
            stderr.write_text("", encoding="utf-8")
            audit.write_text("", encoding="utf-8")
            record_path = run_dir / "run.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["state"] = "execution_complete_verification_pending"
            record["execution"] = {
                "runtime_success": True,
                "agent_termination_valid": True,
            }
            record["trajectory"] = {"termination_reason": "agent_end"}
            record["artifacts"]["execution_sha256"] = {
                "events": sha256_file(events),
                "stderr": sha256_file(stderr),
                "policy_audit": sha256_file(audit),
            }
            record_path.write_text(
                json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            verification = {
                "verified_success": True,
                "tests": {
                    "public": {"passed": True},
                    "hidden": {"passed": True},
                },
            }

            with patch(
                "local_llm_benchmark.pi_v03_adapter.verify_coding_workspace",
                return_value=verification,
            ):
                finalized = finalize_pi_v03_agent_run(self.repo_root, run_dir)

        self.assertTrue(finalized["runtime_success"])
        self.assertTrue(finalized["agent_termination_valid"])
        self.assertTrue(finalized["verifier_success"])
        self.assertTrue(finalized["verified_success"])


if __name__ == "__main__":
    unittest.main()
