from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_llm_benchmark import multi_format_pi as base
from local_llm_benchmark.macos_sandbox import SeatbeltCommandResult
from local_llm_benchmark.multi_format_pi_v02 import (
    HARNESS_ID,
    finalize,
    prepare,
    python_worker_executable,
    sandbox_check,
)
from local_llm_benchmark.runner import load_json, sha256_file


REPO_ROOT = Path(__file__).resolve().parents[1]


class PiMultiFormatV02Tests(unittest.TestCase):
    def _prepare(self, parent: Path) -> Path:
        result = prepare(
            REPO_ROOT,
            base.PiMultiFormatPrepareConfig(
                model="not-contacted:test", results_dir=parent
            ),
        )
        self.assertEqual(result["inference_requests_made"], 0)
        return Path(result["run_dir"])

    def test_worker_is_real_python_app_executable(self) -> None:
        worker = python_worker_executable()
        self.assertEqual(worker.name, "Python")
        self.assertIn("Resources/Python.app/Contents/MacOS", str(worker))
        self.assertTrue(worker.is_file())

    def test_prepare_freezes_worker_and_preserves_v01_core(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._prepare(Path(temporary))
            record = load_json(run_dir / "run.json")
            policy = load_json(run_dir / "pi-policy.json")
            sandbox = load_json(run_dir / "pi-multi-format-sandbox.json")
            worker = python_worker_executable()
            self.assertEqual(record["harness"]["harness_id"], HARNESS_ID)
            self.assertEqual(policy["python_path"], str(worker))
            self.assertEqual(policy["python_sha256"], sha256_file(worker))
            self.assertIn(str(worker), sandbox["allowed_processes"])
            self.assertNotIn(str(Path(base.sys.executable).resolve()), sandbox["allowed_processes"])
            self.assertTrue(record["execution_boundary"]["python_launcher_bypassed"])
            self.assertEqual(
                record["harness"]["adapter_wrapper_sha256"],
                sha256_file(REPO_ROOT / "local_llm_benchmark/multi_format_pi_v02.py"),
            )

    def test_mocked_acceptance_still_covers_all_eleven_checks(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._prepare(Path(temporary))
            with (
                patch(
                    "local_llm_benchmark.macos_sandbox_multi_format.run_seatbelt_command",
                    return_value=SeatbeltCommandResult(0, "", ""),
                ),
                patch(
                    "local_llm_benchmark.macos_sandbox_multi_format._temporary_loopback_probe",
                    return_value=(None, None),
                ),
            ):
                result = sandbox_check(run_dir)
            self.assertTrue(result["passed"])
            self.assertEqual(len(result["checks"]), 11)
            self.assertEqual(result["inference_requests_made"], 0)
            self.assertFalse(result["candidate_code_executed"])


if __name__ == "__main__":
    unittest.main()
