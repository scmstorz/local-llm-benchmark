import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_llm_benchmark.macos_sandbox import SeatbeltCommandResult, validate_pi_seatbelt
from local_llm_benchmark.pi_adapter import (
    PiAgentPrepareConfig,
    execute_pi_agent_run,
    finalize_pi_agent_run,
    load_pi_harness,
    load_pi_track_b_case,
    prepare_pi_agent_run,
)
from local_llm_benchmark.runner import sha256_file
from tests.test_coding import (
    REFERENCE_PHP_CHECKOUT_FILE,
    REFERENCE_PHP_RETRY_POLICY_FILE,
)


PHP_CASE_PATH = Path("tasks/coding/dev/php-payment-result-migration/case.json")
PI_V01_PATH = Path("tasks/coding/track-b/pi-v0.1.json")


class PiAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path.cwd().resolve()

    def test_exact_pi_package_and_policy_extension_are_pinned(self) -> None:
        loaded = load_pi_harness(self.repo_root)

        self.assertEqual(loaded["harness"]["harness_id"], "pi-v0.2")
        self.assertEqual(
            loaded["harness"]["status"], "qualified_for_capability_sweep"
        )
        self.assertEqual(
            loaded["protocol"]["status"], "frozen_for_capability_sweep"
        )
        self.assertEqual(loaded["observed_version"], "0.84.4")
        self.assertEqual(
            loaded["harness"]["package"]["name"],
            "@earendil-works/pi-coding-agent",
        )
        self.assertEqual(
            loaded["harness"]["integration"]["explicit_extension"],
            "integrations/pi/benchmark-policy.mjs",
        )
        load_pi_track_b_case(self.repo_root, PHP_CASE_PATH)

    def test_prepare_creates_reproducible_private_invocation_without_inference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = prepare_pi_agent_run(
                self.repo_root,
                PiAgentPrepareConfig(
                    model="ornith-1.5:35b",
                    case_path=PHP_CASE_PATH,
                    results_dir=Path(temporary),
                ),
            )
            run_dir = Path(result["run_dir"])
            record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            invocation = json.loads(
                (run_dir / "pi-invocation.json").read_text(encoding="utf-8")
            )
            policy = json.loads(
                (run_dir / "pi-policy.json").read_text(encoding="utf-8")
            )

            self.assertEqual(result["state"], "prepared_not_executed")
            self.assertEqual(result["inference_requests_made"], 0)
            self.assertFalse(result["candidate_code_executed"])
            self.assertEqual(record["harness"]["package_version"], "0.84.4")
            self.assertTrue(record["environment"]["node_version"].startswith("v"))
            self.assertTrue(invocation["requires_os_sandbox"])
            self.assertIn("--no-session", invocation["argv"])
            self.assertIn("--no-extensions", invocation["argv"])
            self.assertIn("--offline", invocation["argv"])
            settings = json.loads(
                (run_dir / "pi-agent" / "settings.json").read_text(encoding="utf-8")
            )
            self.assertFalse(settings["retry"]["enabled"])
            self.assertFalse(settings["compaction"]["enabled"])
            self.assertEqual(
                record["execution_boundary"]["sandbox_backend"],
                "pi-macos-seatbelt-v0.1",
            )
            self.assertEqual(
                policy["writable_paths"],
                ["src/CheckoutService.php", "src/RetryPolicy.php"],
            )
            self.assertEqual(policy["public_test_command"], "php tests/run.php")
            self.assertNotIn("maximum_agent_turns", policy)
            serialized_invocation = json.dumps(invocation)
            self.assertNotIn("verifier/", serialized_invocation)
            self.assertNotIn("hidden_tests.php", serialized_invocation)
            self.assertNotIn(record["case"]["hidden_test_sha256"], serialized_invocation)

    def test_v01_prepare_retains_the_historical_turn_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = prepare_pi_agent_run(
                self.repo_root,
                PiAgentPrepareConfig(
                    model="ornith-1.5:35b",
                    case_path=PHP_CASE_PATH,
                    harness_path=PI_V01_PATH,
                    results_dir=Path(temporary),
                ),
            )
            policy = json.loads(
                (Path(result["run_dir"]) / "pi-policy.json").read_text(encoding="utf-8")
            )

        self.assertEqual(policy["maximum_agent_turns"], 12)

    def test_finalize_keeps_runtime_agent_and_verifier_outcomes_separate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = prepare_pi_agent_run(
                self.repo_root,
                PiAgentPrepareConfig(
                    model="ornith-1.5:35b",
                    case_path=PHP_CASE_PATH,
                    results_dir=Path(temporary),
                ),
            )
            run_dir = Path(result["run_dir"])
            workspace = run_dir / "workspace"
            (workspace / "src" / "CheckoutService.php").write_text(
                REFERENCE_PHP_CHECKOUT_FILE,
                encoding="utf-8",
            )
            (workspace / "src" / "RetryPolicy.php").write_text(
                REFERENCE_PHP_RETRY_POLICY_FILE,
                encoding="utf-8",
            )
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

            finalized = finalize_pi_agent_run(self.repo_root, run_dir)

            self.assertTrue(finalized["runtime_success"])
            self.assertTrue(finalized["agent_termination_valid"])
            self.assertTrue(finalized["verifier_success"])
            self.assertTrue(finalized["verified_success"])

    def test_live_execution_persists_trajectory_but_defers_hidden_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = prepare_pi_agent_run(
                self.repo_root,
                PiAgentPrepareConfig(
                    model="ornith-1.5:35b",
                    case_path=PHP_CASE_PATH,
                    results_dir=Path(temporary),
                ),
            )
            run_dir = Path(result["run_dir"])
            acceptance_codes = [0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0]
            with patch(
                "local_llm_benchmark.macos_sandbox.run_seatbelt_command",
                side_effect=[
                    SeatbeltCommandResult(code, "", "")
                    for code in acceptance_codes
                ],
            ):
                validate_pi_seatbelt(run_dir)

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
                    return 0

            original_popen = subprocess.Popen

            def selective_popen(*args, **kwargs):
                if hasattr(kwargs.get("stdout"), "write"):
                    return FakeProcess(*args, **kwargs)
                return original_popen(*args, **kwargs)

            with patch(
                "local_llm_benchmark.pi_adapter.subprocess.Popen",
                side_effect=selective_popen,
            ):
                executed = execute_pi_agent_run(self.repo_root, run_dir)

            self.assertTrue(executed["runtime_success"])
            self.assertTrue(executed["agent_termination_valid"])
            self.assertFalse(executed["hidden_verification_executed"])
            self.assertEqual(
                executed["state"], "execution_complete_verification_pending"
            )
            record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            self.assertFalse(record["execution_boundary"]["hidden_verification_executed"])
            self.assertNotIn("verification", record)


if __name__ == "__main__":
    unittest.main()
