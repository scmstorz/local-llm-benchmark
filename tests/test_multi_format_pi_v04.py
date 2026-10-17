from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_llm_benchmark import multi_format_pi as base
from local_llm_benchmark.macos_sandbox import SeatbeltCommandResult
from local_llm_benchmark.multi_format_pi_v04 import (
    HARNESS_ID,
    TOOL_NAMES,
    _admit_structured_report_transport,
    _load_prepared,
    finalize,
    load_pi_multi_format_v04_case,
    load_pi_multi_format_v04_harness,
    prepare,
    sandbox_check,
)
from local_llm_benchmark.runner import load_json, sha256_file, write_json


REPO_ROOT = Path(__file__).resolve().parents[1]


class PiMultiFormatV04Tests(unittest.TestCase):
    def _prepare(self, parent: Path) -> Path:
        result = prepare(
            REPO_ROOT,
            base.PiMultiFormatPrepareConfig(
                model="not-contacted:test", results_dir=parent
            ),
        )
        self.assertEqual(result["inference_requests_made"], 0)
        return Path(result["run_dir"])

    def test_definition_binds_five_tools_and_supplier_case(self) -> None:
        harness = load_pi_multi_format_v04_harness(REPO_ROOT)
        loaded = load_pi_multi_format_v04_case(REPO_ROOT)
        self.assertEqual(harness["harness"]["harness_id"], HARNESS_ID)
        self.assertEqual(harness["harness"]["integration"]["tools"], TOOL_NAMES)
        self.assertEqual(
            loaded["case"]["case_id"],
            "agentic.documents.supplier-award-reconciliation",
        )
        self.assertEqual(
            loaded["protocol"]["artifact_api"]["implementation_path"],
            "local_llm_benchmark/multi_format_transfer_artifacts.py",
        )

    def test_prepare_freezes_new_backend_schema_extension_and_worker(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._prepare(Path(temporary))
            record = load_json(run_dir / "run.json")
            policy = load_json(run_dir / "pi-policy.json")
            invocation = load_json(run_dir / "pi-invocation.json")
            self.assertEqual(record["harness"]["harness_id"], HARNESS_ID)
            self.assertEqual(
                record["harness"]["extension_path"],
                "integrations/pi/multi-format-readonly-v0.3.mjs",
            )
            self.assertEqual(
                record["harness"]["artifact_backend_path"],
                "local_llm_benchmark/multi_format_transfer_artifacts.py",
            )
            self.assertEqual(
                sha256_file(run_dir / "artifact-backend.py"),
                sha256_file(
                    REPO_ROOT
                    / "local_llm_benchmark/multi_format_transfer_artifacts.py"
                ),
            )
            self.assertEqual(policy["allowed_tools"], TOOL_NAMES)
            self.assertEqual(policy["policy_id"], "pi-multi-format-readonly-v0.2")
            self.assertEqual(Path(policy["python_path"]).name, "Python")
            self.assertIn("finish_report", invocation["argv"][invocation["argv"].index("--tools") + 1])
            self.assertFalse(Path(policy["final_report_path"]).exists())

    def test_acceptance_contains_thirteen_checks_including_transport(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._prepare(Path(temporary))
            success = SeatbeltCommandResult(0, "", "")
            with (
                patch(
                    "local_llm_benchmark.macos_sandbox_multi_format_v02.run_seatbelt_command",
                    return_value=success,
                ),
                patch(
                    "local_llm_benchmark.macos_sandbox_multi_format_v02._temporary_loopback_probe",
                    return_value=(None, None, "127.0.0.2"),
                ),
                patch(
                    "local_llm_benchmark.multi_format_pi_v04.run_seatbelt_command",
                    return_value=success,
                ),
            ):
                result = sandbox_check(run_dir)
            self.assertTrue(result["passed"])
            self.assertEqual(len(result["checks"]), 13)
            self.assertIn(
                "structured_report_write_allowed",
                [item["check_id"] for item in result["checks"]],
            )
            self.assertEqual(
                result["checks"][-1]["check_id"],
                "explicit_extension_loads_under_seatbelt",
            )

    def test_structured_capture_is_strict_and_verifies_twelve_checks(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._prepare(Path(temporary))
            record_path = run_dir / "run.json"
            record = load_json(record_path)
            report = load_json(
                REPO_ROOT
                / "tasks/agentic/multi-format-document-analysis/supplier-award-reconciliation/reference/reference-report-v0.2.json"
            )
            (run_dir / "captured-report.json").write_text(
                json.dumps(report, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            record["state"] = "execution_complete_verification_pending"
            record["execution"] = {
                "runtime_success": True,
                "agent_termination_valid": True,
            }
            record["trajectory"] = {
                "finish_report_calls": 1,
                "termination_reason": "structured_finish_report",
            }
            write_json(record_path, record)
            admitted = _admit_structured_report_transport(
                REPO_ROOT, run_dir, {"state": record["state"]}
            )
            result = finalize(REPO_ROOT, run_dir)
            self.assertTrue(admitted["strict_transport_compliance"])
            self.assertEqual(admitted["report_transport"], "structured_finish_report_tool")
            self.assertTrue(result["semantic_verified_success"])
            self.assertTrue(result["strict_transport_compliance"])
            self.assertEqual(result["verification"]["essential_pass_count"], 12)

    def test_surrounding_free_text_is_not_admitted_without_finish_report(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._prepare(Path(temporary))
            record_path = run_dir / "run.json"
            record = load_json(record_path)
            reference = load_json(
                REPO_ROOT
                / "tasks/agentic/multi-format-document-analysis/supplier-award-reconciliation/reference/reference-report-v0.2.json"
            )
            (run_dir / "candidate-response.txt").write_text(
                "Here is the report.\n" + json.dumps(reference) + "\n",
                encoding="utf-8",
            )
            record["state"] = "execution_complete_verification_pending"
            record["trajectory"] = {"finish_report_calls": 0}
            write_json(record_path, record)
            result = _admit_structured_report_transport(
                REPO_ROOT, run_dir, {"state": record["state"]}
            )
            updated = load_json(record_path)
            self.assertFalse(result["strict_transport_compliance"])
            self.assertEqual(result["final_report_parse_status"], "invalid")
            self.assertIsNone(updated["artifacts"]["candidate_report"])
            self.assertFalse(updated["trajectory"]["free_text_fallback_admitted"])

    def test_prepared_hashes_reject_backend_drift(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._prepare(Path(temporary))
            with (run_dir / "artifact-backend.py").open("ab") as stream:
                stream.write(b"mutation")
            with self.assertRaisesRegex(Exception, "backend_copy"):
                _load_prepared(REPO_ROOT, run_dir, {"prepared_not_executed"})


if __name__ == "__main__":
    unittest.main()
