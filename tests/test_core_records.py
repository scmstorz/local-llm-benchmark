from __future__ import annotations

import copy
from datetime import datetime, timedelta
from pathlib import Path
import unittest

from local_llm_benchmark import core_records
from local_llm_benchmark.runner import RunnerError, load_json, sha256_file, write_json
from tests import test_core_suite as fixtures

ROOT = fixtures.ROOT


class CoreRecordsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CoreSuiteTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.plan = self.fixture._plan()
        self.plan_path = (self.fixture.directory / "prepared/plan.json").relative_to(ROOT)
        self.cell, self.run_path, self.run = self.fixture._record(self.plan, "pi-supplier")
        entry = next(item for item in self.plan["deployments"] if item["deployment_id"] == self.cell["deployment_id"])
        start = datetime.fromisoformat(self.plan["created_at"].replace("Z", "+00:00"))
        stamp = lambda seconds: (start + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")
        self.run.pop("started_at")
        self.run["prepared_at"] = stamp(.1)
        self.run["execution"] = {"started_at": stamp(32)}
        self.run["case"]["case_path"] = self.cell["case_path"]
        # Actual frozen Pi supplier shape: requested model only, no native
        # digest/version observation, unlike Mini's fully populated deployment.
        self.run["deployment"] = {"requested_model": entry["resolved_name"]}
        write_json(self.run_path, self.run)
        self.study = {
            "plan_sha256": sha256_file(ROOT / self.plan_path),
            "units": [{"status": "complete", "run_dir": str(self.run_path.parent.relative_to(ROOT)),
                       "run_sha256": sha256_file(self.run_path),
                       "resource_evidence": {"passed": True, "inference_requests_made": 0,
                                             "model": entry["resolved_name"], "digest": entry["digest"],
                                             "ollama_version": entry["runtime"]["version"],
                                             "observed_at": stamp(1), "completed_at": stamp(31)}}],
        }
        self.study_path = (self.fixture.directory / "admission-study.json").relative_to(ROOT)
        write_json(ROOT / self.study_path, self.study)

    def _row(self, study=True):
        result = core_records.coverage(ROOT, self.plan_path, self.study_path if study else None)
        return next(row for row in result["cells"] if row["cell_id"] == self.cell["cell_id"])

    def test_missing_native_identity_remains_unknown_without_external_evidence(self):
        self.assertEqual(self._row(study=False)["status"], "identity_unrecorded")

    def test_actual_pi_shape_uses_bound_pre_inference_gate_without_mutating_run(self):
        before = self.run_path.read_bytes()
        row = self._row()
        self.assertEqual(row["status"], "complete")
        self.assertEqual(row["identity_basis"], "verified_pre_inference_resource_gate")
        self.assertFalse(row["outcome"]["verified_success"])
        self.assertEqual(self.run_path.read_bytes(), before)

    def test_wrong_gate_identity_or_nonpassing_gate_cannot_fill_identity(self):
        for change in ({"digest": "f" * 64}, {"ollama_version": "other-runtime"},
                       {"passed": False}, {"inference_requests_made": 1}):
            with self.subTest(change=change):
                study = copy.deepcopy(self.study)
                study["units"][0]["resource_evidence"].update(change)
                write_json(ROOT / self.study_path, study)
                self.assertEqual(self._row()["status"], "identity_unrecorded")

    def test_stale_raw_hash_cannot_fill_identity(self):
        self.run["outcome"]["verified_success"] = True
        write_json(self.run_path, self.run)
        self.assertEqual(self._row()["status"], "identity_unrecorded")

    def test_admission_for_another_plan_rejected(self):
        self.study["plan_sha256"] = "0" * 64
        write_json(ROOT / self.study_path, self.study)
        with self.assertRaisesRegex(RunnerError, "another plan"):
            self._row()

    def test_observation_after_execution_start_is_not_preflight_evidence(self):
        started = datetime.fromisoformat(self.run["execution"]["started_at"].replace("Z", "+00:00"))
        self.study["units"][0]["resource_evidence"]["completed_at"] = (started + timedelta(seconds=1)).isoformat()
        write_json(ROOT / self.study_path, self.study)
        self.assertEqual(self._row()["status"], "identity_unrecorded")

    def test_external_gate_does_not_override_contradictory_native_runtime(self):
        self.run["deployment"]["ollama_version"] = "contradictory-runtime"
        write_json(self.run_path, self.run)
        self.study["units"][0]["run_sha256"] = sha256_file(self.run_path)
        write_json(ROOT / self.study_path, self.study)
        self.assertEqual(self._row()["status"], "identity_mismatch")

    def test_wrong_harness_cannot_be_repaired_by_an_external_gate(self):
        self.run["harness"]["harness_id"] = "another-harness"
        write_json(self.run_path, self.run)
        self.study["units"][0]["run_sha256"] = sha256_file(self.run_path)
        write_json(ROOT / self.study_path, self.study)
        self.assertEqual(self._row()["status"], "identity_mismatch")


if __name__ == "__main__":
    unittest.main()
