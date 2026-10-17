from __future__ import annotations

import copy
import unittest
from pathlib import Path
from unittest.mock import patch

from local_llm_benchmark import core_records_v03 as reader
from local_llm_benchmark.runner import load_json, utc_now, write_json
from tests import test_core_suite as fixtures

ROOT = Path(__file__).resolve().parents[1]


class CoreRecordsV03Tests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.CoreSuiteTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.plan = fixture._plan()
        self.plan_path = (fixture.directory / "prepared/plan.json").relative_to(ROOT)
        self.catalog = fixture.catalog
        cell = next(row for row in self.plan["cells"] if row["system"] == "direct-coding")
        self.cell_id = cell["cell_id"]
        block = next(row for row in self.plan["blocks"] if row["block_id"] == cell["block_id"])
        deployment = next(row for row in self.plan["deployments"] if row["deployment_id"] == cell["deployment_id"])
        self.record = {
            "track": "A", "harness": {"name": "local_llm_benchmark.direct_files", "version": "1.1.0"},
            "started_at": utc_now(), "case": {"case_id": cell["case_id"]},
            "deployment": {"ollama_version": deployment["runtime"]["version"], "model": {
                "resolved_name": deployment["resolved_name"], "digest": deployment["digest"]}},
            "execution": {"execution_status": "completed"},
            "verification_execution": {"mode": "immediate", "completed_at": utc_now()},
            "outcome": {"verified_success": False}, "completed_at": utc_now(),
        }
        self.run_path = ROOT / block["results_dir"] / "native-direct-run/run.json"
        self.run_path.parent.mkdir(parents=True)

    def row(self, record=None):
        write_json(self.run_path, self.record if record is None else record)
        with patch("local_llm_benchmark.ollama.OllamaClient", side_effect=AssertionError("Read-only coverage")):
            result = reader.coverage(ROOT, self.plan_path)
        return next(row for row in result["cells"] if row["cell_id"] == self.cell_id)

    def test_native_completion_preserves_observed_task_failure_and_raw_bytes(self):
        row = self.row()
        before = self.run_path.read_bytes()
        self.assertEqual(row["status"], "complete")
        self.assertFalse(row["outcome"]["verified_success"])
        self.assertEqual(self.row()["status"], "complete")
        self.assertEqual(self.run_path.read_bytes(), before)

    def test_native_dictionary_timestamp_order_is_accepted(self):
        record = copy.deepcopy(self.record)
        record["completed_at"] = record["started_at"]
        self.assertEqual(self.row(record)["status"], "complete")

    def test_deferred_or_missing_verification_stays_in_progress(self):
        for change in ({"mode": "deferred"}, {"completed_at": None}):
            record = copy.deepcopy(self.record)
            record["verification_execution"].update(change)
            self.assertEqual(self.row(record)["status"], "in_progress")

    def test_invalid_or_reversed_timestamps_stay_in_progress(self):
        for value in ("invalid", "2000-01-01T00:00:00Z", "2026-01-01T00:00:00"):
            record = copy.deepcopy(self.record)
            record["completed_at"] = value
            self.assertEqual(self.row(record)["status"], "in_progress")

    def test_native_deployment_contradiction_cannot_be_overridden(self):
        record = copy.deepcopy(self.record)
        record["deployment"]["model"]["digest"] = "0" * 64
        self.assertEqual(self.row(record)["status"], "identity_mismatch")

    def test_changed_plan_source_prevents_completion_promotion(self):
        catalog = load_json(self.catalog)
        catalog["extra"] = "source changed"
        write_json(self.catalog, catalog)
        self.assertEqual(self.row()["status"], "in_progress")

    def test_unrecognized_or_nonterminal_execution_stays_in_progress(self):
        for key, value in (("track", "B"), ("execution", {"execution_status": "running"}),
                           ("harness", {"name": "other-runner"}), ("outcome", {"verified_success": None})):
            record = copy.deepcopy(self.record)
            record[key] = value
            self.assertEqual(self.row(record)["status"], "in_progress")
