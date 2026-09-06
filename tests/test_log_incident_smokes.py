import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from local_llm_benchmark.log_incident_smokes import (
    DEFAULT_PAIR_PLAN,
    LogSmokeStudyConfig,
    ResourceGatePause,
    advance_log_smoke_study,
    build_log_smoke_report,
    cleanup_log_smoke_unit,
    load_log_smoke_pair_plan,
    run_resource_gate,
    run_log_smoke_live_step,
    start_log_smoke_study,
)
from local_llm_benchmark.runner import RunnerError, sha256_file


class LogIncidentSmokeControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path.cwd().resolve()
        self.plan = json.loads(DEFAULT_PAIR_PLAN.read_text(encoding="utf-8"))
        self.results = self.repo_root / "results"
        self.results.mkdir(exist_ok=True)

    def _client(self) -> MagicMock:
        client = MagicMock()
        client.version.return_value = {"version": self.plan["runtime"]["version"]}
        client.list_models.return_value = {
            "models": [
                {
                    "name": self.plan["deployment"]["name"],
                    "digest": self.plan["deployment"]["digest"],
                    "size": self.plan["deployment"]["size_bytes"],
                }
            ]
        }
        client.list_running_models.return_value = {"models": []}
        client.unload_model.return_value = {}
        return client

    def _temporary_pair_plan(self, root: Path) -> Path:
        plan = json.loads(DEFAULT_PAIR_PLAN.read_text(encoding="utf-8"))
        plan["plan_id"] = "test-log-incident-smoke-pair"
        relative = root.relative_to(self.repo_root)
        plan["reporting"]["json_path"] = (relative / "public.json").as_posix()
        plan["reporting"]["markdown_path"] = (relative / "public.md").as_posix()
        path = root / "pair.json"
        path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        return path

    def test_frozen_pair_is_hash_complete_and_orders_mini_before_pi(self) -> None:
        loaded = load_log_smoke_pair_plan(self.repo_root, DEFAULT_PAIR_PLAN)

        self.assertEqual(
            [item["harness_id"] for item in loaded["plan"]["execution_order"]],
            ["mini-log-v0.1", "pi-log-v0.1"],
        )
        self.assertFalse(
            loaded["plan"]["comparison_rules"][
                "one_factor_causal_harness_claim_allowed"
            ]
        )
        self.assertEqual(loaded["plan"]["comparison_rules"]["automatic_retries"], 0)
        for unit in loaded["plan"]["execution_order"]:
            self.assertEqual(
                sha256_file(Path(unit["smoke_plan_path"])),
                unit["smoke_plan_sha256"],
            )

    def test_resource_gate_blocks_behat_before_contacting_ollama(self) -> None:
        client = self._client()
        process = {
            "pid": 123,
            "cpu_percent": 42.0,
            "elapsed": "00:10",
            "command": "php bin/console queue:consume --env=behat_test",
        }

        with self.assertRaises(ResourceGatePause) as raised:
            run_resource_gate(
                self.plan,
                client=client,
                process_reader=lambda: [process],
                sleep=lambda _seconds: None,
            )

        client.version.assert_not_called()
        serialized = json.dumps(raised.exception.evidence)
        self.assertNotIn(process["command"], serialized)
        self.assertIn("behat_environment_worker", serialized)
        self.assertEqual(raised.exception.evidence["inference_requests_made"], 0)

    def test_resource_gate_requires_two_clean_snapshots_and_exact_identity(self) -> None:
        client = self._client()
        sleeps = []

        result = run_resource_gate(
            self.plan,
            client=client,
            process_reader=lambda: [],
            sleep=sleeps.append,
        )

        self.assertTrue(result["passed"])
        self.assertEqual(sleeps, [30])
        self.assertEqual(client.list_running_models.call_count, 2)
        self.assertEqual(result["inference_requests_made"], 0)

    def test_resource_gate_does_not_confuse_idle_helpers_with_active_tests(self) -> None:
        client = self._client()
        idle_infrastructure = [
            {
                "pid": 12,
                "cpu_percent": 0.0,
                "elapsed": "01:00:00",
                "command": "php /project/dev/behat/router.php",
            },
            {
                "pid": 13,
                "cpu_percent": 0.0,
                "elapsed": "01:00:00",
                "command": "python /project/mnemosyn_mcp.py",
            },
        ]

        result = run_resource_gate(
            self.plan,
            client=client,
            process_reader=lambda: idle_infrastructure,
            sleep=lambda _seconds: None,
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["blocking_processes"], [])

    def test_start_and_first_advance_prepare_mini_without_inference(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            root = Path(temporary)
            started = start_log_smoke_study(
                self.repo_root,
                LogSmokeStudyConfig(
                    plan_path=DEFAULT_PAIR_PLAN,
                    results_dir=root / "studies",
                    agent_results_dir=root / "runs",
                ),
            )
            self.assertEqual(started["waiting"]["unit_status"], "pending")

            advanced = advance_log_smoke_study(
                self.repo_root, Path(started["study_dir"])
            )
            self.assertEqual(advanced["waiting"]["harness_id"], "mini-log-v0.1")
            self.assertEqual(advanced["waiting"]["unit_status"], "awaiting_model")
            run = json.loads(
                (self.repo_root / advanced["waiting"]["run_dir"] / "run.json").read_text()
            )
            self.assertEqual(run["execution_boundary"]["inference_requests_made"], 0)

    def test_interrupted_live_boundary_is_preserved_without_retry(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            root = Path(temporary)
            started = start_log_smoke_study(
                self.repo_root,
                LogSmokeStudyConfig(
                    plan_path=DEFAULT_PAIR_PLAN,
                    results_dir=root / "studies",
                    agent_results_dir=root / "runs",
                ),
            )
            study_dir = Path(started["study_dir"])
            advanced = advance_log_smoke_study(self.repo_root, study_dir)
            run_path = self.repo_root / advanced["waiting"]["run_dir"] / "run.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["state"] = "model_call_running"
            run_path.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")

            result = advance_log_smoke_study(self.repo_root, study_dir)
            study = json.loads((study_dir / "study.json").read_text(encoding="utf-8"))

            self.assertEqual(result["status"], "paused_inconclusive_needs_cleanup")
            self.assertEqual(
                study["units"][0]["status"],
                "interrupted_inconclusive_needs_cleanup",
            )
            self.assertFalse(study["units"][0]["interruption"]["automatic_retry"])
            self.assertIsNone(study["units"][1]["run_id"])

            cleaned = cleanup_log_smoke_unit(
                self.repo_root, study_dir, client=self._client()
            )
            study = json.loads((study_dir / "study.json").read_text(encoding="utf-8"))
            self.assertEqual(study["units"][0]["status"], "interrupted_inconclusive")
            self.assertEqual(cleaned["waiting"]["harness_id"], "pi-log-v0.1")
            self.assertEqual(cleaned["waiting"]["unit_status"], "pending")

    def test_live_boundary_requires_confirmed_exclusive_window(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            root = Path(temporary)
            started = start_log_smoke_study(
                self.repo_root,
                LogSmokeStudyConfig(
                    plan_path=DEFAULT_PAIR_PLAN,
                    results_dir=root / "studies",
                    agent_results_dir=root / "runs",
                ),
            )
            study_dir = Path(started["study_dir"])
            advance_log_smoke_study(self.repo_root, study_dir)
            client = self._client()

            with self.assertRaisesRegex(RunnerError, "explicit confirmation"):
                run_log_smoke_live_step(
                    self.repo_root,
                    study_dir,
                    client=client,
                    process_reader=lambda: [],
                    sleep=lambda _seconds: None,
                )

            client.version.assert_not_called()
            study = json.loads((study_dir / "study.json").read_text(encoding="utf-8"))
            self.assertEqual(study["units"][0]["exclusive_window_confirmations"], [])

    def test_report_is_public_safe_and_requires_terminal_pair(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            root = Path(temporary)
            plan_path = self._temporary_pair_plan(root)
            started = start_log_smoke_study(
                self.repo_root,
                LogSmokeStudyConfig(
                    plan_path=plan_path,
                    results_dir=root / "studies",
                    agent_results_dir=root / "runs",
                ),
            )
            study_dir = Path(started["study_dir"])
            study_path = study_dir / "study.json"
            study = json.loads(study_path.read_text(encoding="utf-8"))
            for position, unit in enumerate(study["units"], start=1):
                run_dir = root / f"raw-{position}"
                run_dir.mkdir()
                run = {
                    "run_id": f"safe-run-{position}",
                    "candidate_response": "must not become public",
                    "outcome": {
                        "runtime_success": True,
                        "agent_termination_valid": True,
                        "verifier_success": position == 1,
                        "verified_success": position == 1,
                        "failure_category": None
                        if position == 1
                        else "task_or_verification_failure",
                        "failure_type": None
                        if position == 1
                        else "verification_failed",
                    },
                    "trajectory": {
                        "active_wall_time_seconds": 12.5 * position,
                        "agent_turns": 3 * position,
                        "file_reads": 2 * position,
                        "repeated_file_reads": 0,
                        "input_tokens": 100 * position,
                        "output_tokens": 20 * position,
                    },
                }
                (run_dir / "run.json").write_text(
                    json.dumps(run, indent=2) + "\n", encoding="utf-8"
                )
                unit["status"] = "complete"
                unit["run_id"] = run["run_id"]
                unit["run_dir"] = run_dir.relative_to(self.repo_root).as_posix()
            study["status"] = "complete"
            study_path.write_text(json.dumps(study, indent=2) + "\n", encoding="utf-8")

            result = build_log_smoke_report(self.repo_root, study_dir)
            serialized = Path(result["json_path"]).read_text(encoding="utf-8")

            self.assertEqual(result["unit_count"], 2)
            self.assertNotIn("must not become public", serialized)
            self.assertNotIn("/Users/", serialized)
            self.assertIn("complete_system", serialized)


if __name__ == "__main__":
    unittest.main()
