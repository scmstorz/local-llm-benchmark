import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from local_llm_benchmark.log_incident_sweep import (
    HARNESS_IDS,
    LogIncidentSweepConfig,
    advance_log_incident_sweep,
    cleanup_log_incident_sweep_unit,
    load_log_incident_sweep_plan,
    run_log_incident_sweep_live,
    start_log_incident_sweep,
)
from local_llm_benchmark.log_incident_report import build_log_incident_sweep_report
from local_llm_benchmark.log_incident_sweep_analysis import (
    _embedded_json_object,
    build_log_incident_sweep_analysis,
)
from local_llm_benchmark.runner import RunnerError, sha256_file


MODEL = "test-model:latest"
DIGEST = "d" * 64
CASES = [
    (
        "agentic.ops.checkout-pool-regression",
        "2.0.0",
        "tasks/agentic/log-incident-analysis/checkout-pool-regression/case-v2.json",
    ),
    (
        "agentic.ops.retry-queue-amplification",
        "1.0.0",
        "tasks/agentic/log-incident-analysis/retry-queue-amplification/case.json",
    ),
    (
        "agentic.ops.clock-skew-partial-recovery",
        "1.0.0",
        "tasks/agentic/log-incident-analysis/clock-skew-partial-recovery/case.json",
    ),
]


class LogIncidentSweepTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path.cwd().resolve()
        self.results = self.repo_root / "results"
        self.results.mkdir(exist_ok=True)

    @staticmethod
    def _client() -> MagicMock:
        client = MagicMock()
        client.version.return_value = {"version": "test-version"}
        client.list_models.return_value = {
            "models": [{"name": MODEL, "digest": DIGEST, "size": 123}]
        }
        client.list_running_models.return_value = {"models": []}
        client.unload_model.return_value = {}
        return client

    def _plan(self, root: Path) -> Path:
        mini_qualification = Path(
            "tasks/agentic/track-b/mini-log-v0.2-qualification.json"
        )
        pi_qualification = Path(
            "tasks/agentic/track-b/pi-log-v0.2-qualification.json"
        )
        smoke_report = Path(
            "reports/agentic/log-incident-qualification-smokes-v0.2.json"
        )
        artifacts = [
            Path("tasks/agentic/track-b/mini-log-v0.2.json"),
            Path("tasks/agentic/track-b/pi-log-v0.2.json"),
            mini_qualification,
            pi_qualification,
            smoke_report,
            *(Path(path) for _case_id, _version, path in CASES),
        ]
        order = []
        position = 1
        for case_id, _version, _path in CASES:
            for harness_id in HARNESS_IDS:
                order.append(
                    {
                        "position": position,
                        "harness_id": harness_id,
                        "model": MODEL,
                        "case_id": case_id,
                    }
                )
                position += 1
        plan = {
            "schema_version": "1.0.0",
            "plan_id": "test-log-incident-capability-sweep",
            "status": "frozen_before_execution",
            "track": "B",
            "protocol_id": "agentic-log-incident-v0.2",
            "evidence_class": "measured_capability_sweep",
            "runtime": {
                "name": "ollama",
                "version": "test-version",
                "host": "http://127.0.0.1:11434",
            },
            "qualification_gate": {
                "smoke_report_path": smoke_report.as_posix(),
                "smoke_report_sha256": sha256_file(smoke_report),
                "excluded_smoke_reused_as_measured": False,
            },
            "harnesses": [
                {
                    "harness_id": "mini-log-v0.2",
                    "harness_path": "tasks/agentic/track-b/mini-log-v0.2.json",
                    "qualification_path": mini_qualification.as_posix(),
                    "qualification_sha256": sha256_file(mini_qualification),
                },
                {
                    "harness_id": "pi-log-v0.2",
                    "harness_path": "tasks/agentic/track-b/pi-log-v0.2.json",
                    "qualification_path": pi_qualification.as_posix(),
                    "qualification_sha256": sha256_file(pi_qualification),
                },
            ],
            "deployments": [
                {
                    "name": MODEL,
                    "deployment_id": "test-model-deployment",
                    "digest": DIGEST,
                }
            ],
            "cases": [
                {
                    "case_id": case_id,
                    "case_version": version,
                    "case_path": path,
                }
                for case_id, version, path in CASES
            ],
            "execution_order": order,
            "comparison_rules": {
                "runs_per_configuration": 1,
                "automatic_retries": 0,
                "performance_distribution_claims": False,
                "one_factor_causal_harness_claim_allowed": False,
            },
            "resource_gate": {
                "empty_state_observation_seconds": 0,
                "loaded_models_must_be_empty_before_each_unit": True,
                "blocking_process_rules": [
                    {"rule_id": "test", "pattern": "never-match-this"}
                ],
            },
            "reporting": {
                "json_path": (root.relative_to(self.repo_root) / "public.json").as_posix(),
                "markdown_path": (
                    root.relative_to(self.repo_root) / "public.md"
                ).as_posix(),
            },
            "frozen_inputs": {
                "artifacts": [
                    {"path": path.as_posix(), "sha256": sha256_file(path)}
                    for path in artifacts
                ]
            },
        }
        path = root / "plan.json"
        path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        return path

    def test_plan_requires_complete_two_harness_three_case_product(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            plan_path = self._plan(Path(temporary))
            loaded = load_log_incident_sweep_plan(self.repo_root, plan_path)
            self.assertEqual(len(loaded["plan"]["execution_order"]), 6)
            self.assertEqual(set(loaded["harnesses"]), set(HARNESS_IDS))

            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["execution_order"].pop()
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaisesRegex(RunnerError, "full harness/model/case"):
                load_log_incident_sweep_plan(self.repo_root, plan_path)

    def test_start_prepares_first_mini_unit_without_inference(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            root = Path(temporary)
            started = start_log_incident_sweep(
                self.repo_root,
                LogIncidentSweepConfig(
                    plan_path=self._plan(root),
                    results_dir=root / "sweeps",
                    agent_results_dir=root / "runs",
                ),
            )
            self.assertEqual(started["waiting"]["unit_status"], "awaiting_model")
            run_path = (
                self.repo_root / started["waiting"]["run_dir"] / "run.json"
            )
            run = json.loads(run_path.read_text(encoding="utf-8"))
            self.assertEqual(run["execution_boundary"]["inference_requests_made"], 0)

    def test_live_boundary_checkpoints_completed_model_call(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            root = Path(temporary)
            started = start_log_incident_sweep(
                self.repo_root,
                LogIncidentSweepConfig(
                    plan_path=self._plan(root),
                    results_dir=root / "sweeps",
                    agent_results_dir=root / "runs",
                ),
            )
            sweep_dir = Path(started["sweep_dir"])

            def complete_model_call(_repo_root: Path, run_dir: Path) -> dict:
                run_path = run_dir / "run.json"
                run = json.loads(run_path.read_text(encoding="utf-8"))
                run["state"] = "awaiting_action"
                run_path.write_text(json.dumps(run), encoding="utf-8")
                return {"state": "awaiting_action"}

            with patch(
                "local_llm_benchmark.log_incident_sweep.call_mini_log_v02_model",
                side_effect=complete_model_call,
            ):
                result = run_log_incident_sweep_live(
                    self.repo_root,
                    sweep_dir,
                    client=self._client(),
                    process_reader=lambda: [],
                    sleep=lambda _seconds: None,
                    exclusive_window_confirmed=True,
                )

            self.assertEqual(result["waiting"]["unit_status"], "awaiting_action")

    def test_resume_marks_interrupted_live_state_and_never_retries(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            root = Path(temporary)
            started = start_log_incident_sweep(
                self.repo_root,
                LogIncidentSweepConfig(
                    plan_path=self._plan(root),
                    results_dir=root / "sweeps",
                    agent_results_dir=root / "runs",
                ),
            )
            sweep_dir = Path(started["sweep_dir"])
            run_path = self.repo_root / started["waiting"]["run_dir"] / "run.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["state"] = "model_call_running"
            run_path.write_text(json.dumps(run), encoding="utf-8")

            resumed = advance_log_incident_sweep(self.repo_root, sweep_dir)
            self.assertEqual(
                resumed["waiting"]["unit_status"], "failed_needs_cleanup"
            )
            with patch(
                "local_llm_benchmark.log_incident_sweep.validate_pi_log_seatbelt",
                return_value={
                    "passed": True,
                    "validated_at": "2026-09-06T00:00:00Z",
                    "profile_sha256": "p" * 64,
                },
            ):
                cleaned = cleanup_log_incident_sweep_unit(
                    self.repo_root, sweep_dir, client=self._client()
                )
            sweep = json.loads((sweep_dir / "sweep.json").read_text(encoding="utf-8"))
            self.assertEqual(sweep["units"][0]["status"], "failed")
            self.assertEqual(sweep["units"][0]["error"]["type"], "interrupted_live_process")
            self.assertEqual(cleaned["failed_unit_count"], 1)
            self.assertIsNotNone(cleaned["waiting"])

    def test_public_report_excludes_candidate_content_and_absolute_paths(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            root = Path(temporary)
            started = start_log_incident_sweep(
                self.repo_root,
                LogIncidentSweepConfig(
                    plan_path=self._plan(root),
                    results_dir=root / "sweeps",
                    agent_results_dir=root / "runs",
                ),
            )
            sweep_dir = Path(started["sweep_dir"])
            sweep_path = sweep_dir / "sweep.json"
            sweep = json.loads(sweep_path.read_text(encoding="utf-8"))
            for index, unit in enumerate(sweep["units"], start=1):
                run_dir = root / f"terminal-{index}"
                run_dir.mkdir()
                raw = {
                    "run_id": f"safe-run-{index}",
                    "state": "complete",
                    "case": {"case_id": unit["case_id"]},
                    "candidate_report": "private marker must not become public",
                    "outcome": {
                        "runtime_success": True,
                        "agent_termination_valid": True,
                        "verifier_success": index % 2 == 0,
                        "verified_success": index % 2 == 0,
                        "failure_category": None
                        if index % 2 == 0
                        else "task_or_verification_failure",
                        "failure_type": None
                        if index % 2 == 0
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
                    },
                    "verification": {
                        "essential_pass_count": 14 if index % 2 == 0 else 13,
                        "essential_check_count": 14,
                        "checks": [
                            {
                                "check_id": "root_cause",
                                "essential": True,
                                "passed": index % 2 == 0,
                            }
                        ],
                    },
                }
                (run_dir / "run.json").write_text(
                    json.dumps(raw, indent=2) + "\n", encoding="utf-8"
                )
                unit["status"] = "complete"
                unit["run_id"] = raw["run_id"]
                unit["run_dir"] = run_dir.relative_to(self.repo_root).as_posix()
                unit["outcome"] = raw["outcome"]
                unit["trajectory"] = raw["trajectory"]
            sweep["status"] = "complete"
            sweep["complete_unit_count"] = len(sweep["units"])
            sweep["completed_at"] = "2026-09-06T00:00:00Z"
            sweep_path.write_text(json.dumps(sweep, indent=2) + "\n", encoding="utf-8")

            result = build_log_incident_sweep_report(self.repo_root, sweep_dir)
            public = (root / "public.json").read_text(encoding="utf-8")
            self.assertEqual(result["run_count"], 6)
            self.assertEqual(result["verified_success_count"], 3)
            self.assertNotIn("private marker", public)
            self.assertNotIn("/Users/", public)
            self.assertIn("complete_system", public)

            analysis_result = build_log_incident_sweep_analysis(
                self.repo_root,
                sweep_dir,
                root / "public.json",
                root / "analysis.json",
                root / "analysis.md",
            )
            analysis_public = (root / "analysis.json").read_text(encoding="utf-8")
            self.assertEqual(analysis_result["run_count"], 6)
            self.assertNotIn("private marker", analysis_public)
            self.assertNotIn("/Users/", analysis_public)
            analysis = json.loads(analysis_public)
            self.assertFalse(analysis["method"]["primary_outcomes_changed"])
            self.assertEqual(analysis["summary"]["schema_valid_report_count"], 6)

    def test_post_hoc_envelope_extraction_does_not_repair_inner_json(self) -> None:
        report, envelope = _embedded_json_object('```json\n{"ok": true}\n```')
        self.assertEqual(report, {"ok": True})
        self.assertEqual(envelope, "markdown_code_fence")

        report, envelope = _embedded_json_object('Result: {"ok": true}')
        self.assertEqual(report, {"ok": True})
        self.assertEqual(envelope, "surrounding_text")

        report, envelope = _embedded_json_object('```json\n{"ok": }\n```')
        self.assertIsNone(report)
        self.assertIsNone(envelope)


if __name__ == "__main__":
    unittest.main()
