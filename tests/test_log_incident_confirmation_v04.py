from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from local_llm_benchmark.log_incident_confirmation_report_v04 import (
    build_log_incident_sweep_report,
)
from local_llm_benchmark.log_incident_confirmation_v04 import (
    DEFAULT_AUTHORIZATION,
    DEFAULT_SWEEP_PLAN,
    HARNESS_IDS,
    LogIncidentSweepConfig,
    load_execution_authorization,
    load_log_incident_sweep_plan,
    run_log_incident_sweep_live,
    start_log_incident_sweep,
)
from local_llm_benchmark.runner import load_json


REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL = "qwen3.8:27b-mlx"
DIGEST = "5642e97495e1a088883805981563dcdc4a040c2f53388b7a41d1f24d3622cf7e"


class LogIncidentV04ConfirmationControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.results = REPO_ROOT / "results"
        self.results.mkdir(exist_ok=True)

    @staticmethod
    def _client() -> MagicMock:
        client = MagicMock()
        client.version.return_value = {"version": "0.33.2"}
        client.list_models.return_value = {
            "models": [{"name": MODEL, "digest": DIGEST, "size": 18174721847}]
        }
        client.list_running_models.return_value = {"models": []}
        client.unload_model.return_value = {}
        return client

    def _start(self, root: Path) -> dict[str, object]:
        return start_log_incident_sweep(
            REPO_ROOT,
            LogIncidentSweepConfig(
                plan_path=DEFAULT_SWEEP_PLAN,
                authorization_path=DEFAULT_AUTHORIZATION,
                results_dir=root / "confirmations",
                agent_results_dir=root / "runs",
            ),
        )

    def test_plan_and_post_freeze_authorization_are_bound(self) -> None:
        loaded = load_log_incident_sweep_plan(REPO_ROOT, DEFAULT_SWEEP_PLAN)
        authorization = load_execution_authorization(
            REPO_ROOT, DEFAULT_AUTHORIZATION, loaded
        )
        self.assertEqual(len(loaded["plan"]["execution_order"]), 6)
        self.assertEqual(set(loaded["harnesses"]), set(HARNESS_IDS))
        self.assertEqual(list(loaded["models"]), [MODEL])
        self.assertTrue(authorization["authorization"]["live_execution_authorized"])
        self.assertEqual(
            authorization["authorization"]["plan_sha256"], loaded["sha256"]
        )

    def test_start_prepares_first_cell_without_inference(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            result = self._start(Path(temporary))
            self.assertEqual(result["unit_count"], 6)
            self.assertEqual(result["waiting"]["unit_status"], "awaiting_model")
            run = load_json(REPO_ROOT / result["waiting"]["run_dir"] / "run.json")
            self.assertEqual(run["execution_boundary"]["inference_requests_made"], 0)
            self.assertEqual(run["case"]["case_version"], "4.0.0")

    def test_live_boundary_requires_explicit_runtime_confirmation(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            result = self._start(Path(temporary))
            with self.assertRaisesRegex(Exception, "exclusive-window"):
                run_log_incident_sweep_live(
                    REPO_ROOT,
                    Path(result["sweep_dir"]),
                    client=self._client(),
                    process_reader=lambda: [],
                    sleep=lambda _seconds: None,
                )

    def test_mocked_live_boundary_checkpoints_without_real_ollama(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            result = self._start(Path(temporary))

            def complete_model_call(_repo_root: Path, run_dir: Path) -> dict[str, str]:
                path = run_dir / "run.json"
                run = load_json(path)
                run["state"] = "awaiting_action"
                path.write_text(json.dumps(run), encoding="utf-8")
                return {"state": "awaiting_action"}

            with patch(
                "local_llm_benchmark.log_incident_confirmation_v04."
                "call_mini_log_v04_model",
                side_effect=complete_model_call,
            ):
                advanced = run_log_incident_sweep_live(
                    REPO_ROOT,
                    Path(result["sweep_dir"]),
                    client=self._client(),
                    process_reader=lambda: [],
                    sleep=lambda _seconds: None,
                    exclusive_window_confirmed=True,
                )
            self.assertEqual(advanced["waiting"]["unit_status"], "awaiting_action")

    def test_public_report_separates_semantics_transport_and_private_data(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            root = Path(temporary)
            result = self._start(root)
            sweep_dir = Path(result["sweep_dir"])
            sweep_path = sweep_dir / "sweep.json"
            sweep = load_json(sweep_path)
            for index, unit in enumerate(sweep["units"], start=1):
                raw_dir = root / f"raw-{index}"
                raw_dir.mkdir()
                semantic = index % 2 == 0
                strict = index <= 4
                raw = {
                    "run_id": f"safe-v04-run-{index}",
                    "state": "complete",
                    "case": {"case_id": unit["case_id"]},
                    "private_candidate_marker": "must not become public",
                    "outcome": {
                        "runtime_success": True,
                        "agent_termination_valid": True,
                        "semantic_verifier_success": semantic,
                        "semantic_verified_success": semantic,
                        "verified_success": semantic,
                        "strict_transport_compliance": strict,
                        "failure_category": None
                        if semantic
                        else "task_or_verification_failure",
                        "failure_type": None
                        if semantic
                        else "deterministic_checks_failed",
                    },
                    "trajectory": {
                        "active_wall_time_seconds": float(index),
                        "agent_turns": index,
                        "model_requests": index,
                        "tool_calls": index,
                        "file_reads": index,
                        "repeated_file_reads": 0,
                        "failed_tool_calls": 0,
                        "protocol_errors": 0,
                        "input_tokens": index * 100,
                        "output_tokens": index * 10,
                        "response_normalization_applied": not strict,
                    },
                    "verification": {
                        "essential_pass_count": 15 if semantic else 14,
                        "essential_check_count": 15,
                        "checks": [
                            {
                                "check_id": "incident_start_utc",
                                "essential": True,
                                "passed": semantic,
                            }
                        ],
                    },
                }
                (raw_dir / "run.json").write_text(
                    json.dumps(raw, indent=2) + "\n", encoding="utf-8"
                )
                unit["status"] = "complete"
                unit["run_id"] = raw["run_id"]
                unit["run_dir"] = raw_dir.relative_to(REPO_ROOT).as_posix()
                unit["outcome"] = raw["outcome"]
                unit["trajectory"] = raw["trajectory"]
            sweep["status"] = "complete"
            sweep["completed_at"] = "2026-09-06T00:00:00Z"
            sweep_path.write_text(json.dumps(sweep, indent=2) + "\n", encoding="utf-8")

            json_output = root / "public.json"
            markdown_output = root / "public.md"
            built = build_log_incident_sweep_report(
                REPO_ROOT,
                sweep_dir,
                json_output=json_output,
                markdown_output=markdown_output,
            )
            public_text = json_output.read_text(encoding="utf-8")
            public = json.loads(public_text)
            self.assertEqual(built["semantic_verified_success_count"], 3)
            self.assertEqual(built["strict_transport_compliance_count"], 4)
            self.assertNotIn("must not become public", public_text)
            self.assertNotIn("/Users/", public_text)
            self.assertEqual(
                public["summary"]["response_normalization_applied_count"], 2
            )


if __name__ == "__main__":
    unittest.main()
