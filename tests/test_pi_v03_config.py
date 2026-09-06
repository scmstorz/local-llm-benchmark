import tempfile
import unittest
from pathlib import Path

from local_llm_benchmark.pi_v03_config import (
    build_pi_v03_candidate_configuration,
    load_pi_v03_candidate,
)


class PiV03ConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path.cwd().resolve()

    def test_candidate_uses_a_new_protocol_and_extension(self) -> None:
        loaded = load_pi_v03_candidate(self.repo_root)

        self.assertEqual(loaded["protocol"]["protocol_id"], "coding-track-b-v0.3")
        self.assertEqual(
            loaded["extension_path"].name, "benchmark-policy-v0.3.mjs"
        )

    def test_configuration_applies_timeouts_but_not_token_or_turn_limits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            configuration = build_pi_v03_candidate_configuration(
                self.repo_root,
                model="ornith-1.5:35b",
                workspace_root=root,
                audit_log_path=root / "audit.jsonl",
                readable_paths=["src/example.php"],
                writable_paths=["src/example.php"],
                public_test_command="php tests/run.php",
                maximum_write_bytes=131072,
            )

        settings = configuration["settings"]
        policy = configuration["policy"]
        self.assertEqual(settings["retry"]["provider"]["timeoutMs"], 300_000)
        self.assertEqual(settings["httpIdleTimeoutMs"], 300_000)
        self.assertEqual(configuration["parent_timeout_seconds"], 900)
        self.assertNotIn("maximum_agent_turns", policy)
        self.assertNotIn("maximum_total_output_tokens", policy)
        self.assertNotIn("maximum_wall_time_seconds", policy)
        self.assertEqual(policy["parent_maximum_active_wall_time_seconds"], 900)
        self.assertEqual(policy["maximum_public_test_runs"], 30)
        self.assertEqual(configuration["inference_requests_made"], 0)
        self.assertFalse(configuration["candidate_code_executed"])


if __name__ == "__main__":
    unittest.main()
