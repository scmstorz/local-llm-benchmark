from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_llm_benchmark import multi_format_pi as base
from local_llm_benchmark.macos_sandbox import SeatbeltCommandResult
from local_llm_benchmark.multi_format_pi_v03 import HARNESS_ID, prepare, sandbox_check
from local_llm_benchmark.runner import load_json, sha256_file


REPO_ROOT = Path(__file__).resolve().parents[1]


class PiMultiFormatV03Tests(unittest.TestCase):
    def _prepare(self, parent: Path) -> Path:
        result = prepare(
            REPO_ROOT,
            base.PiMultiFormatPrepareConfig(
                model="not-contacted:test", results_dir=parent
            ),
        )
        self.assertEqual(result["inference_requests_made"], 0)
        return Path(result["run_dir"])

    def test_prepare_freezes_corrected_extension_and_worker(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._prepare(Path(temporary))
            record = load_json(run_dir / "run.json")
            invocation = load_json(run_dir / "pi-invocation.json")
            policy = load_json(run_dir / "pi-policy.json")
            self.assertEqual(record["harness"]["harness_id"], HARNESS_ID)
            self.assertEqual(
                record["harness"]["extension_path"],
                "integrations/pi/multi-format-readonly-v0.2.mjs",
            )
            self.assertEqual(Path(policy["python_path"]).name, "Python")
            self.assertIn("--no-builtin-tools", invocation["argv"])
            self.assertEqual(
                record["harness"]["adapter_wrapper_sha256"],
                sha256_file(REPO_ROOT / "local_llm_benchmark/multi_format_pi_v03.py"),
            )

    def test_acceptance_includes_explicit_extension_load(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._prepare(Path(temporary))
            success = SeatbeltCommandResult(0, "", "")
            with (
                patch(
                    "local_llm_benchmark.macos_sandbox_multi_format.run_seatbelt_command",
                    return_value=success,
                ),
                patch(
                    "local_llm_benchmark.macos_sandbox_multi_format._temporary_loopback_probe",
                    return_value=(None, None),
                ),
                patch(
                    "local_llm_benchmark.multi_format_pi_v03.run_seatbelt_command",
                    return_value=success,
                ),
            ):
                result = sandbox_check(run_dir)
            self.assertTrue(result["passed"])
            self.assertEqual(len(result["checks"]), 12)
            self.assertEqual(
                result["checks"][-1]["check_id"],
                "explicit_extension_loads_under_seatbelt",
            )
            record = load_json(run_dir / "run.json")
            self.assertTrue(
                record["execution_boundary"]["explicit_extension_acceptance_passed"]
            )


if __name__ == "__main__":
    unittest.main()
