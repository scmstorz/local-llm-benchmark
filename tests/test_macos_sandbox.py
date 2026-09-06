import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_llm_benchmark.macos_sandbox import (
    SEATBELT_PROFILE_VERSION,
    SeatbeltCommandResult,
    build_pi_seatbelt_profile,
    validate_pi_seatbelt,
)
from local_llm_benchmark.pi_adapter import PiAgentPrepareConfig, prepare_pi_agent_run


PHP_CASE_PATH = Path("tasks/coding/dev/php-payment-result-migration/case.json")
ASYNC_CASE_PATH = Path("tasks/coding/dev/async-cache-coalescing/case.json")


class MacOSSandboxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path.cwd().resolve()

    def test_profile_is_deny_by_default_and_network_is_loopback_only(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.repo_root / "results") as temporary:
            run_dir = Path(temporary)
            workspace = run_dir / "workspace"
            agent_dir = run_dir / "pi-agent"
            workspace.mkdir()
            agent_dir.mkdir()
            writable = workspace / "src.php"
            writable.write_text("<?php\n", encoding="utf-8")
            audit = run_dir / "audit.jsonl"
            invocation = {
                "environment": {"PI_CODING_AGENT_DIR": str(agent_dir)},
            }
            policy = {
                "workspace_root": str(workspace),
                "audit_log_path": str(audit),
                "writable_paths": ["src.php"],
            }

            profile, metadata = build_pi_seatbelt_profile(
                self.repo_root, run_dir, invocation, policy
            )

        self.assertIn("(deny default)", profile)
        self.assertIn('(remote ip "localhost:11434")', profile)
        self.assertNotIn("(allow network-outbound)", profile)
        self.assertIn(str(Path.home().resolve()), profile)
        self.assertIn(str(self.repo_root), profile)
        self.assertEqual(metadata["backend"], SEATBELT_PROFILE_VERSION)
        self.assertEqual(metadata["external_network"], False)

    def test_acceptance_requires_every_adversarial_check(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.repo_root / "results") as temporary:
            prepared = prepare_pi_agent_run(
                self.repo_root,
                PiAgentPrepareConfig(
                    model="ornith-1.5:35b",
                    case_path=PHP_CASE_PATH,
                    results_dir=Path(temporary),
                ),
            )
            run_dir = Path(prepared["run_dir"])
            with patch(
                "local_llm_benchmark.macos_sandbox.run_seatbelt_command",
                return_value=SeatbeltCommandResult(0, "", ""),
            ):
                with self.assertRaisesRegex(Exception, "repository_write_denied"):
                    validate_pi_seatbelt(run_dir)

    def test_acceptance_probes_the_prepared_cases_exact_hidden_verifier(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.repo_root / "results") as temporary:
            prepared = prepare_pi_agent_run(
                self.repo_root,
                PiAgentPrepareConfig(
                    model="qwen3.8:27b-mlx",
                    case_path=ASYNC_CASE_PATH,
                    results_dir=Path(temporary),
                ),
            )
            run_dir = Path(prepared["run_dir"])
            expected_hidden_sha256 = json.loads(
                (run_dir / "run.json").read_text(encoding="utf-8")
            )["case"]["hidden_test_sha256"]
            observed_commands: list[list[str]] = []

            def accepted(
                _profile_path: Path,
                command: list[str],
                **_kwargs: object,
            ) -> SeatbeltCommandResult:
                observed_commands.append(command)
                returncode = 1 if any(
                    "pi-seatbelt-denied-write.tmp" in token for token in command
                ) else 0
                return SeatbeltCommandResult(returncode, "", "")

            with patch(
                "local_llm_benchmark.macos_sandbox.run_seatbelt_command",
                side_effect=accepted,
            ):
                result = validate_pi_seatbelt(run_dir)

        hidden_path = str(
            self.repo_root
            / "tasks/coding/dev/async-cache-coalescing/verifier/hidden_tests.mjs"
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["hidden_verifier_sha256"], expected_hidden_sha256)
        self.assertTrue(
            any(hidden_path in token for command in observed_commands for token in command)
        )


if __name__ == "__main__":
    unittest.main()
