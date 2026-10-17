from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from local_llm_benchmark import multi_format_transfer_smoke as original
from local_llm_benchmark import multi_format_transfer_smoke_v03 as current
from local_llm_benchmark.log_incident_smokes import ResourceGatePause, run_resource_gate
from local_llm_benchmark.runner import RunnerError, load_json, sha256_file, write_json


ROOT = Path(__file__).resolve().parents[1]


class TransferSmokeRuntimeAmendmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / "results")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def _plan(self, value: dict) -> Path:
        path = self.directory / "plan.json"
        write_json(path, value)
        return path.relative_to(ROOT)

    def test_only_runtime_and_additive_provenance_change(self) -> None:
        loaded = current.load_transfer_smoke_plan(ROOT)
        old = current._original_plan_loader(ROOT, current.ORIGINAL_PLAN)
        self.assertEqual(old["sha256"], current.ORIGINAL_PLAN_SHA256)
        self.assertEqual(loaded["plan"]["runtime"]["expected_version"], "0.40.2")
        for key in ("case", "systems", "execution_order", "shared_inference", "resource_gate", "comparison_rules", "success_gate"):
            self.assertEqual(loaded["plan"][key], old["plan"][key], key)
        self.assertEqual(loaded["plan"]["deployment"]["digest"], old["plan"]["deployment"]["digest"])

    def test_other_runtime_is_rejected(self) -> None:
        plan = current.amended_plan(ROOT)
        plan["runtime"]["expected_version"] = "0.33.2"
        with self.assertRaisesRegex(RunnerError, "bounded"):
            current.load_transfer_smoke_plan(ROOT, self._plan(plan))

    def test_sampling_retry_and_order_drift_are_rejected(self) -> None:
        for key, value in (("seed", 43), ("automatic_retries", 1)):
            plan = current.amended_plan(ROOT)
            plan["shared_inference"][key] = value
            with self.subTest(key=key), self.assertRaises(RunnerError):
                current.load_transfer_smoke_plan(ROOT, self._plan(plan))
        plan = current.amended_plan(ROOT)
        plan["execution_order"].reverse()
        with self.assertRaises(RunnerError):
            current.load_transfer_smoke_plan(ROOT, self._plan(plan))

    def test_historical_authorization_is_rejected(self) -> None:
        loaded = current.load_transfer_smoke_plan(ROOT)
        path = self.directory / "authorization.json"
        write_json(path, {"authorization_id": "multi-format-transfer-smoke-v0.2-execution-authorization", "plan_sha256": current.ORIGINAL_PLAN_SHA256})
        with self.assertRaisesRegex(RunnerError, "authorization"):
            current.load_execution_authorization(ROOT, path.relative_to(ROOT), loaded)

    def test_current_authorization_requires_exact_plan_and_runtime(self) -> None:
        loaded = current.load_transfer_smoke_plan(ROOT)
        path = self.directory / "authorization.json"
        authorization = {
            "schema_version": "1.0.0", "authorization_id": f"{current.PLAN_ID}-execution-authorization",
            "status": "authorized_pending_resource_gate", "plan_id": current.PLAN_ID,
            "plan_sha256": loaded["sha256"], "live_execution_authorized": True,
            "unit_count": 2, "attempts_per_system": 1, "automatic_retries": 0,
            "authorized_model": original.MODEL, "authorized_systems": list(original.SYSTEM_IDS),
            "resource_gate_still_required": True, "authorized_runtime_version": "0.40.2",
        }
        write_json(path, authorization)
        self.assertEqual(current.load_execution_authorization(ROOT, path.relative_to(ROOT), loaded)["authorization"], authorization)
        for key, value in (("plan_sha256", current.ORIGINAL_PLAN_SHA256), ("authorized_runtime_version", "0.33.2")):
            altered = {**authorization, key: value}
            write_json(path, altered)
            with self.subTest(key=key), self.assertRaises(RunnerError):
                current.load_execution_authorization(ROOT, path.relative_to(ROOT), loaded)

    def test_original_controller_configuration_is_restored(self) -> None:
        loader, source, plan = original.load_transfer_smoke_plan, original.__file__, original.DEFAULT_PLAN
        with current._configured_base():
            self.assertIs(original.load_transfer_smoke_plan, current.load_transfer_smoke_plan)
            self.assertEqual(original.__file__, current.__file__)
        self.assertIs(original.load_transfer_smoke_plan, loader)
        self.assertEqual(original.__file__, source)
        self.assertEqual(original.DEFAULT_PLAN, plan)

    def test_real_gate_still_rejects_runtime_drift_before_inference(self) -> None:
        loaded = current.load_transfer_smoke_plan(ROOT)
        client = MagicMock()
        client.version.return_value = {"version": "0.33.2"}
        with self.assertRaisesRegex(ResourceGatePause, "version drift"):
            run_resource_gate({"runtime": {"version": "0.40.2"}, "deployment": loaded["plan"]["deployment"], "resource_gate": loaded["resource_gate"]}, client=client, process_reader=lambda: [], sleep=lambda _: None)
        client.list_models.assert_not_called()
        client.stream_chat.assert_not_called()

    def test_fresh_preparation_does_not_contact_ollama_or_reuse_old_runs(self) -> None:
        pi = self.directory / "pi"
        mini = self.directory / "mini"
        pi.mkdir()
        mini.mkdir()
        write_json(pi / "run.json", {"state": "prepared_not_executed", "execution_boundary": {"sandbox_acceptance_passed": True, "explicit_extension_acceptance_passed": True}, "trajectory": {"model_requests": 0}})
        write_json(mini / "run.json", {"state": "awaiting_model", "trajectory": {"model_requests": 0}})
        acceptance = {"passed": True, "validated_at": "2026-10-17T00:00:00Z", "profile_sha256": "a" * 64, "checks": [{"passed": True} for _ in range(13)]}
        qualification = {"path": ROOT / current.DEFAULT_CONTROLLER_QUALIFICATION, "sha256": "a" * 64}
        with patch.object(current, "load_controller_qualification", return_value=qualification), patch.object(original, "prepare_pi", return_value={"run_id": "new-pi", "run_dir": str(pi)}), patch.object(original, "prepare_mini", return_value={"run_id": "new-mini", "run_dir": str(mini)}), patch.object(original, "check_pi_sandbox", return_value=acceptance), patch.object(original, "OllamaClient", side_effect=AssertionError("offline preparation contacted Ollama")):
            result = current.start_transfer_smoke(ROOT, current.TransferSmokeConfig(results_dir=(self.directory / "studies").relative_to(ROOT)))
        study = load_json(Path(result["study_dir"]) / "study.json")
        self.assertEqual(study["ollama_version"], "0.40.2")
        self.assertEqual(study["model_requests_observed"], 0)
        self.assertEqual(study["controller"]["implementation_sha256"], sha256_file(Path(current.__file__)))
        self.assertTrue(all(unit["deployment_id"] == current.DEPLOYMENT_ID for unit in study["units"]))
        self.assertFalse(study["units"][0]["offline_seatbelt_acceptance"]["freshness_for_live_execution"])

    def test_prepared_historical_study_is_unchanged(self) -> None:
        path = ROOT / "results/agentic-transfer-smokes/multi-format-transfer-smoke-20260912T091336Z-2b4cdc1e/study.json"
        if not path.exists():
            self.skipTest("Private historical preparation is unavailable")
        self.assertEqual(sha256_file(path), "4e05d104143fe2d3dc6551385834b134dab8b7fb7ea2a997559745c21c27a4b9")


if __name__ == "__main__":
    unittest.main()
