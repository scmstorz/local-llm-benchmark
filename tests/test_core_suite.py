from __future__ import annotations

import copy
import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_llm_benchmark import core_suite as core
from local_llm_benchmark.runner import RunnerError, load_json, utc_now, write_json


ROOT = Path(__file__).resolve().parents[1]


class CoreSuiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.loaded = core.load_catalog(ROOT)
        original = load_json(ROOT / "models/catalog-transfer-smoke-ollama-0.40.2.json")["deployments"][0]
        other = copy.deepcopy(original)
        other.update(deployment_id="arbitrary-future-deployment", resolved_name="future-model:any-tag", digest="a" * 64)
        self.catalog = self.directory / "models.json"
        write_json(self.catalog, {"deployments": [original, other]})
        self.ids = [original["deployment_id"], other["deployment_id"]]

    def _plan(self, profile="first-comparison"):
        return core.prepare_plan(ROOT, self.loaded, catalog_path=self.catalog.relative_to(ROOT),
                                 deployment_ids=self.ids, profile=profile, output=self.directory / "prepared")

    def _record(self, plan, system="mini-supplier", *, complete=True):
        cell = next(cell for cell in plan["cells"] if cell["system"] == system)
        block = next(block for block in plan["blocks"] if block["block_id"] == cell["block_id"])
        entry = next(entry for entry in plan["deployments"] if entry["deployment_id"] == cell["deployment_id"])
        definition = self.loaded["registry"]["systems"][system]
        record = {"case": {"case_id": cell["case_id"]}, "started_at": utc_now(),
                  "state": "complete" if complete else "prepared_not_executed",
                  "harness": {"harness_id": definition.get("expected_harness_id")},
                  "deployment": {"ollama_version": entry["runtime"]["version"],
                                 "model": {"digest": entry["digest"], "resolved_name": entry["resolved_name"]}},
                  "verification": {"verifier_version": "2.1.0", "essential_pass_count": 11, "essential_check_count": 12},
                  "outcome": {"verified_success": False, "runtime_success": True, "strict_transport_compliance": True},
                  "evaluation_configuration": {"configuration_id": "supplier-execution-v0.3"},
                  "normalized_metrics": {"version": "0.2.0"}}
        path = ROOT / block["results_dir"] / "synthetic-run" / "run.json"
        path.parent.mkdir(parents=True)
        write_json(path, record)
        return cell, path, record

    def test_inventory_counts_tasks_separately_from_systems(self):
        result = core.overview(ROOT, self.loaded)
        self.assertEqual(result["task_count"], 23)
        self.assertEqual(result["task_system_variant_count"], 35)
        self.assertEqual(len(result["families"]), 6)
        self.assertFalse(result["model_set_fixed"])
        self.assertEqual(result["deferred_task_families"][0]["target"], "next_suite_version")

    def test_first_comparison_keeps_candidate_and_runtime_unbound(self):
        result = core.first_comparison(self.loaded)
        self.assertEqual(result, load_json(ROOT / "tasks/core-first-comparison-v0.1.json"))
        self.assertIsNone(result["candidate_model"])
        self.assertIsNone(result["runtime_version"])
        self.assertEqual(result["tasks"], 6)
        self.assertEqual(result["task_system_cells_per_deployment"], 10)
        self.assertFalse(result["execution_authorized"])

    def test_unseen_model_generates_bound_plan_without_any_model_client(self):
        with patch("local_llm_benchmark.ollama.OllamaClient", side_effect=AssertionError("No runtime access")):
            plan = self._plan()
            result = core.coverage(ROOT, plan)
        self.assertEqual(len(plan["cells"]), 20)
        self.assertEqual(result["counts"], {"not_run": 20})
        self.assertFalse(plan["execution_authorized"])
        self.assertEqual(plan["automatic_retries"], 0)
        self.assertEqual(result["source_drift"], [])
        self.assertIn("future-model:any-tag", str(plan["blocks"]))

    def test_full_profile_has_70_cells_for_two_arbitrary_deployments(self):
        self.assertEqual(len(self._plan("full")["cells"]), 70)

    def test_runtime_mismatch_rejected_before_creating_plan(self):
        catalog = load_json(self.catalog)
        catalog["deployments"][1]["runtime"]["version"] = "future-runtime"
        write_json(self.catalog, catalog)
        with self.assertRaisesRegex(RunnerError, "shared Ollama"):
            self._plan()
        self.assertFalse((self.directory / "prepared").exists())

    def test_unknown_or_duplicate_deployments_rejected(self):
        for ids in (["missing"], [self.ids[0], self.ids[0]]):
            with self.subTest(ids=ids), self.assertRaises(RunnerError):
                core.prepare_plan(ROOT, self.loaded, catalog_path=self.catalog.relative_to(ROOT),
                                  deployment_ids=ids, profile="full", output=self.directory / "prepared")

    def test_plan_output_cannot_overwrite(self):
        self._plan()
        with self.assertRaisesRegex(RunnerError, "new directory"):
            self._plan()

    def test_emitted_commands_parse_with_all_existing_runner_clis(self):
        plan = self._plan("full")
        for block in plan["blocks"]:
            argv = block["argv"]
            module = importlib.import_module("local_llm_benchmark.cli" if argv[2] == "local_llm_benchmark" else argv[2])
            with self.subTest(system=block["system"]):
                if hasattr(module, "build_parser"):
                    module.build_parser().parse_args(argv[3:])
                elif block["system"].endswith("supplier"):
                    # main is deliberately not called: it would prepare a run.
                    self.assertEqual(argv[3:6], ["prepare", "--system", block["system"].split("-")[0]])
                else:
                    self.fail(f"No parser qualification for {block['system']}")

    def test_completed_failure_is_retained_separately_from_missing(self):
        plan = self._plan()
        cell, _, _ = self._record(plan)
        result = core.coverage(ROOT, plan)
        observed = next(row for row in result["cells"] if row["cell_id"] == cell["cell_id"])
        self.assertEqual(observed["status"], "complete")
        self.assertFalse(observed["outcome"]["verified_success"])
        self.assertEqual(result["counts"], {"not_run": 19, "complete": 1})
        self.assertFalse(result["quality_comparison_ready"])

    def test_command_export_does_not_restart_a_completed_failure(self):
        plan = self._plan()
        cell, _, _ = self._record(plan)
        block = next(block for block in core.command_blocks(ROOT, plan)["blocks"]
                     if block["block_id"] == cell["block_id"])
        self.assertFalse(block["start_command_available"])
        self.assertIsNone(block["command"])
        self.assertIn("Do not restart", block["continuation"])

    def test_wrong_runtime_old_attempt_and_old_verifier_cannot_fill_cell(self):
        plan = self._plan()
        cell, path, record = self._record(plan)
        for mutate in (
            lambda row: row["deployment"].update(ollama_version="0.33.2"),
            lambda row: row.update(started_at="2000-01-01T00:00:00Z"),
            lambda row: row["verification"].update(verifier_version="2.0.0"),
        ):
            changed = copy.deepcopy(record)
            mutate(changed)
            write_json(path, changed)
            result = core.coverage(ROOT, plan)
            row = next(row for row in result["cells"] if row["cell_id"] == cell["cell_id"])
            self.assertEqual(row["status"], "identity_mismatch")

    def test_prepared_pi_is_not_mislabeled_for_missing_deployment_metadata(self):
        plan = self._plan()
        cell, path, record = self._record(plan, "pi-supplier", complete=False)
        record["prepared_at"] = record.pop("started_at")
        record["deployment"]["model"] = None
        record["deployment"]["ollama_version"] = None
        record["verification"] = None
        record.pop("normalized_metrics")
        write_json(path, record)
        row = next(row for row in core.coverage(ROOT, plan)["cells"] if row["cell_id"] == cell["cell_id"])
        self.assertEqual(row["status"], "prepared_not_executed")

    def test_multiple_attempts_are_ambiguous_instead_of_best_selected(self):
        plan = self._plan()
        cell, path, record = self._record(plan)
        other_path = path.parent.parent / "other-attempt" / "run.json"
        other_path.parent.mkdir()
        write_json(other_path, record)
        row = next(row for row in core.coverage(ROOT, plan)["cells"] if row["cell_id"] == cell["cell_id"])
        self.assertEqual(row["status"], "ambiguous_multiple_attempts")

    def test_new_harness_registry_can_map_tasks_without_changing_task_catalog(self):
        registry = copy.deepcopy(self.loaded["registry"])
        registry["systems"]["future-harness"] = {**registry["systems"]["mini-log"],
            "additional_case_ids": ["agentic.ops.clock-skew-partial-recovery"]}
        path = self.directory / "registry.json"
        write_json(path, registry)
        loaded = core.load_catalog(ROOT, systems_path=path.relative_to(ROOT))
        self.assertEqual(core.overview(ROOT, loaded)["task_count"], 23)
        self.assertEqual(core.overview(ROOT, loaded)["task_system_variant_count"], 36)

    def test_supplier_smoke_does_not_claim_current_measured_coverage(self):
        case = next(row for row in core.overview(ROOT, self.loaded)["cases"]
                    if row["case_id"].endswith("supplier-award-reconciliation"))
        self.assertEqual(case["historical_evidence"][0]["class"], "excluded_development_smoke")
        self.assertFalse(case["historical_evidence"][0]["current_evaluation"])
        self.assertIn("direct", case["unsupported_conditions"])

    def test_text_execution_failure_without_warm_answer_is_retained(self):
        plan = self._plan()
        cell = next(cell for cell in plan["cells"] if cell["system"] == "direct-text")
        block = next(block for block in plan["blocks"] if block["block_id"] == cell["block_id"])
        entry = next(entry for entry in plan["deployments"] if entry["deployment_id"] == cell["deployment_id"])
        path = ROOT / block["sweeps_dir"] / "synthetic-sweep" / "sweep.json"
        path.parent.mkdir(parents=True)
        write_json(path, {"started_at": utc_now(), "deployment": {"digest": entry["digest"], "ollama_version": entry["runtime"]["version"]},
                          "cases": [{"case_id": cell["case_id"], "status": "failed"}]})
        result = core.coverage(ROOT, plan)
        self.assertEqual(next(row for row in result["cells"] if row["cell_id"] == cell["cell_id"])["status"], "execution_failed")
        self.assertEqual(result["counts"]["not_run"], 19)

    def test_partial_attempt_without_terminal_record_is_visible(self):
        plan = self._plan()
        cell = next(cell for cell in plan["cells"] if cell["system"] == "direct-coding")
        block = next(block for block in plan["blocks"] if block["block_id"] == cell["block_id"])
        path = ROOT / block["results_dir"] / "synthetic-partial" / "response.md"
        path.parent.mkdir(parents=True)
        path.write_text("interrupted fixture output\n")
        self.assertEqual(next(row for row in core.coverage(ROOT, plan)["cells"]
                              if row["cell_id"] == cell["cell_id"])["status"], "unrecorded_partial_attempt")


if __name__ == "__main__":
    unittest.main()
