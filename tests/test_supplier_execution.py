from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_llm_benchmark import supplier_execution as execution
from local_llm_benchmark.multi_format_transfer import (
    load_multi_format_transfer_case, verify_multi_format_transfer_report,
)
from local_llm_benchmark.runner import RunnerError, load_json, sha256_file, write_json


ROOT = Path(__file__).resolve().parents[1]
CASE = execution.mini.DEFAULT_CASE_PATH


class SupplierExecutionTests(unittest.TestCase):
    def _record(self, directory: Path, system: str) -> dict:
        harness = execution.mini.HARNESS_ID if system == "mini" else execution.pi.HARNESS_ID
        return {
            "run_id": "synthetic-future-run", "state": "awaiting_model" if system == "mini" else "prepared_not_executed",
            "harness": {"harness_id": harness}, "case": {"case_path": str(CASE)},
            "verification": None, "artifacts": {}, "execution_boundary": {},
            "trajectory": {"tool_calls": 0, "model_requests": 0}, "turns": [],
        }

    def _prepare(self, directory: Path, system: str) -> dict:
        record = self._record(directory, system)
        write_json(directory / "run.json", record)
        adapter = execution.mini if system == "mini" else execution.pi
        method = "start" if system == "mini" else "prepare"
        with patch.object(adapter, method, return_value={"run_dir": str(directory), "state": record["state"]}):
            execution.prepare(ROOT, system=system, model="fixture-only", results_dir=directory)
        return load_json(directory / "run.json")

    def test_preparation_selects_evaluation_and_distinct_system_identity(self):
        for system in ("mini", "pi"):
            with self.subTest(system=system), tempfile.TemporaryDirectory() as temp:
                record = self._prepare(Path(temp), system)
                self.assertEqual(record["evaluation_configuration"]["verifier_version"], "2.1.0")
                self.assertEqual(record["trajectory"]["model_requests"], 0)
                self.assertTrue(record["system_configuration_id"].endswith("+supplier-execution-v0.3"))

    def test_old_runs_cannot_be_adopted(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            write_json(directory / "run.json", self._record(directory, "mini"))
            before = (directory / "run.json").read_bytes()
            with self.assertRaisesRegex(RunnerError, "prepared supplier evaluation"):
                execution.advance(ROOT, directory, "finalize")
            self.assertEqual(before, (directory / "run.json").read_bytes())

    def test_completed_runs_cannot_be_rescored(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            record = self._prepare(directory, "mini")
            record["state"] = "complete"
            write_json(directory / "run.json", record)
            with self.assertRaisesRegex(RunnerError, "completed supplier"):
                execution.advance(ROOT, directory, "finalize")

    def test_identity_drift_prevents_dispatch(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            record = self._prepare(directory, "mini")
            record["evaluation_configuration"]["artifacts"][0]["sha256"] = "0" * 64
            write_json(directory / "run.json", record)
            with patch.object(execution.mini, "call") as call:
                with self.assertRaisesRegex(RunnerError, "drifted"):
                    execution.advance(ROOT, directory, "call")
                call.assert_not_called()

    def test_both_real_finalizers_select_new_verifier_and_metrics(self):
        loaded = load_multi_format_transfer_case(ROOT, CASE)
        report = copy.deepcopy(load_json(loaded["reference_report_path"]))
        extra = next(fact["source_ref"] for fact in loaded["blueprint"]["facts"]
                     if fact["source_ref"] not in report["conflicts"][0]["source_refs"])
        report["conflicts"][0]["source_refs"].append(extra)
        self.assertEqual(verify_multi_format_transfer_report(ROOT, CASE, report)["essential_pass_count"], 11)
        for system in ("mini", "pi"):
            with self.subTest(system=system), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                record = self._prepare(directory, system)
                write_json(directory / "candidate.json", report)
                record["artifacts"] = {"candidate_report": "candidate.json", "candidate_report_sha256": sha256_file(directory / "candidate.json")}
                record["termination"] = {"runtime_success": True, "agent_termination_valid": True, "reason": "finish_report"}
                record["execution"] = {"runtime_success": True, "agent_termination_valid": True}
                record["trajectory"].update({"termination_reason": "finish_report", "strict_transport_compliance": True})
                record["state"] = "trajectory_complete_verification_pending" if system == "mini" else "execution_complete_verification_pending"
                if system == "mini":
                    record["turns"] = [{"action": "finish_report"}]
                else:
                    record["trajectory"].update(tool_calls=1, list_calls=0, docx_reads=0, pdf_reads=0, xlsx_reads=0, finish_report_calls=1)
                    del record["trajectory"]["model_requests"]
                write_json(directory / "run.json", record)
                if system == "mini":
                    with patch.object(execution.mini.base, "_load_run", return_value=(directory, record)), patch.object(execution.mini, "_validated_definition", return_value={}):
                        result = execution.advance(ROOT, directory, "finalize")
                else:
                    prepared = {"record": record, "run_dir": directory, "record_path": directory / "run.json"}
                    with patch.object(execution.pi, "_load_prepared", return_value=prepared):
                        result = execution.advance(ROOT, directory, "finalize")
                completed = load_json(directory / "run.json")
                self.assertTrue(result["verified_success"])
                self.assertEqual(completed["verification"]["verifier_version"], "2.1.0")
                self.assertEqual(completed["verification"]["essential_pass_count"], 12)
                self.assertEqual(completed["normalized_metrics"]["artifact_tool_calls"], 0)
                self.assertEqual(completed["normalized_metrics"]["completion_calls"], 1)
                self.assertEqual(completed["normalized_metrics"]["model_requests"], 0 if system == "mini" else None)
        self.assertEqual(verify_multi_format_transfer_report(ROOT, CASE, report)["essential_pass_count"], 11)

    def test_evaluator_restores_on_exception(self):
        original = execution.mini.verify_multi_format_transfer_report
        with self.assertRaisesRegex(RuntimeError, "fixture error"):
            with execution._evaluation(execution.mini):
                self.assertIs(execution.mini.verify_multi_format_transfer_report, execution.verify_multi_format_transfer_report)
                raise RuntimeError("fixture error")
        self.assertIs(execution.mini.verify_multi_format_transfer_report, original)

    def test_wrong_system_action_rejected_before_inference(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            self._prepare(directory, "mini")
            with self.assertRaisesRegex(RunnerError, "not available"):
                execution.advance(ROOT, directory, "run")


if __name__ == "__main__":
    unittest.main()
