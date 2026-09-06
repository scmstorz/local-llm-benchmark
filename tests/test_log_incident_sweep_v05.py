from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from local_llm_benchmark.log_incident_report_v05 import (
    build_log_incident_sweep_report,
)
from local_llm_benchmark.log_incident_sweep_v05 import (
    HARNESS_IDS,
    LogIncidentSweepConfig,
    load_execution_authorization,
    load_log_incident_sweep_plan,
    run_log_incident_sweep_live,
    start_log_incident_sweep,
)
from local_llm_benchmark.runner import RunnerError, load_json, sha256_file, write_json


REPO_ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE = Path("models/lifecycle.json")
AUDIT = Path("reports/agentic/log-incident-v0.5-specification-audit.json")
IDENTITIES = Path("tasks/agentic/track-b/log-incident-capability-sweep-v0.2.json")


class LogIncidentV05CapabilitySweepTests(unittest.TestCase):
    def setUp(self) -> None:
        self.results = REPO_ROOT / "results"
        self.results.mkdir(exist_ok=True)

    def _plan(self, root: Path) -> Path:
        lifecycle = load_json(REPO_ROOT / LIFECYCLE)
        names = [
            item["model"]
            for item in lifecycle["models"]
            if item["include_in_default_sweeps"] is True
        ]
        identity_source = load_json(REPO_ROOT / IDENTITIES)
        identity_by_name = {
            item["name"]: item for item in identity_source["deployments"]
        }
        deployments = [identity_by_name[name] for name in names]
        cases = [
            {
                "case_id": "agentic.ops.checkout-pool-regression",
                "case_version": "5.0.0",
                "case_path": "tasks/agentic/log-incident-analysis/"
                "checkout-pool-regression/case-v0.5.json",
            },
            {
                "case_id": "agentic.ops.retry-queue-amplification",
                "case_version": "5.0.0",
                "case_path": "tasks/agentic/log-incident-analysis/"
                "retry-queue-amplification/case-v0.5.json",
            },
            {
                "case_id": "agentic.ops.clock-skew-partial-recovery",
                "case_version": "5.0.0",
                "case_path": "tasks/agentic/log-incident-analysis/"
                "clock-skew-partial-recovery/case-v0.5.json",
            },
        ]
        order = []
        position = 0
        for case in cases:
            for model in names:
                for harness_id in HARNESS_IDS:
                    position += 1
                    order.append(
                        {
                            "position": position,
                            "harness_id": harness_id,
                            "model": model,
                            "case_id": case["case_id"],
                        }
                    )
        artifacts = [
            Path("tasks/agentic/track-b/log-incident-v0.5.json"),
            Path("tasks/agentic/track-b/mini-log-v0.5.json"),
            Path("tasks/agentic/track-b/pi-log-v0.5.json"),
            AUDIT,
        ]
        v02 = load_json(REPO_ROOT / IDENTITIES)
        plan = {
            "schema_version": "1.0.0",
            "plan_id": "temporary-log-incident-capability-sweep-v0.5",
            "status": "frozen_before_execution",
            "track": "B",
            "study_mode": "capability_sweep",
            "protocol_id": "agentic-log-incident-v0.5",
            "evidence_class": "measured_capability_sweep",
            "runtime": {
                "name": "ollama",
                "expected_version": "0.33.2",
                "host": "http://127.0.0.1:11434",
                "must_be_reverified_before_execution": True,
            },
            "qualification_gate": {
                "specification_audit_path": AUDIT.as_posix(),
                "specification_audit_sha256": sha256_file(REPO_ROOT / AUDIT),
                "confirmation_runs_reused_as_measured": False,
            },
            "model_selection": {
                "source": LIFECYCLE.as_posix(),
                "source_sha256": sha256_file(REPO_ROOT / LIFECYCLE),
                "rule": "include_in_default_sweeps equals true",
                "selected_count": 5,
            },
            "harnesses": [
                {
                    "harness_id": "mini-log-v0.5",
                    "harness_path": "tasks/agentic/track-b/mini-log-v0.5.json",
                    "qualification_path": "tasks/agentic/track-b/"
                    "mini-log-v0.5-qualification.json",
                },
                {
                    "harness_id": "pi-log-v0.5",
                    "harness_path": "tasks/agentic/track-b/pi-log-v0.5.json",
                    "qualification_path": "tasks/agentic/track-b/"
                    "pi-log-v0.5-qualification.json",
                },
            ],
            "deployments": deployments,
            "cases": cases,
            "execution_order": order,
            "comparison_rules": {
                "runs_per_configuration": 1,
                "automatic_retries": 0,
                "adaptive_repetitions": False,
                "terminal_attempts_not_repeated": True,
                "performance_distribution_claims": False,
                "reliability_probability_claims": False,
                "quality_stochasticity_claims": False,
                "one_factor_causal_harness_claim_allowed": False,
            },
            "outcome_model": {
                "primary": "semantic_verified_success",
                "secondary": "strict_transport_compliance",
                "supplemental_free_text_claim_review_required": True,
                "deterministic_success_is_not_final_quality_acceptance": True,
                "composite_score": False,
            },
            "authorization": {
                "live_execution_authorized": False,
                "fresh_clean_window_confirmation_required": True,
            },
            "resource_gate": {
                "empty_state_observation_seconds": 0,
                "loaded_models_must_be_empty_before_each_unit": True,
                "behat_must_not_be_running": True,
                "blocking_process_rules": v02["resource_gate"][
                    "blocking_process_rules"
                ],
            },
            "frozen_inputs": {
                "artifacts": [
                    {"path": item.as_posix(), "sha256": sha256_file(REPO_ROOT / item)}
                    for item in artifacts
                ]
            },
        }
        path = root / "temporary-capability-plan.json"
        write_json(path, plan)
        return path.relative_to(REPO_ROOT)

    def _qualification(self, root: Path) -> Path:
        artifacts = [
            Path("local_llm_benchmark/log_incident_sweep_v05.py"),
            Path("local_llm_benchmark/log_incident_report_v05.py"),
        ]
        path = root / "temporary-controller-qualification.json"
        write_json(
            path,
            {
                "schema_version": "1.0.0",
                "qualification_id":
                "log-incident-capability-sweep-v0.5-controller-no-inference",
                "status": "qualified_for_authorized_execution",
                "qualification_evidence": {
                    "live_ollama_requests": 0,
                    "live_model_inference": False,
                },
                "artifacts": [
                    {"path": item.as_posix(), "sha256": sha256_file(REPO_ROOT / item)}
                    for item in artifacts
                ],
            },
        )
        return path.relative_to(REPO_ROOT)

    def _authorization(self, root: Path, plan_path: Path) -> Path:
        loaded = load_log_incident_sweep_plan(REPO_ROOT, plan_path)
        path = root / "temporary-capability-authorization.json"
        write_json(
            path,
            {
                "schema_version": "1.0.0",
                "authorization_id":
                "log-incident-capability-sweep-v0.5-execution-authorization",
                "status": "authorized_pending_resource_gate",
                "plan_id": loaded["plan"]["plan_id"],
                "plan_sha256": loaded["sha256"],
                "live_execution_authorized": True,
                "broad_capability_sweep_authorized": True,
                "cell_count": 30,
                "automatic_retries": 0,
                "authorized_models": list(loaded["models"]),
                "resource_gate_still_required": True,
            },
        )
        return path.relative_to(REPO_ROOT)

    @staticmethod
    def _client(model: str, digest: str) -> MagicMock:
        client = MagicMock()
        client.version.return_value = {"version": "0.33.2"}
        client.list_models.return_value = {
            "models": [{"name": model, "digest": digest, "size": 1}]
        }
        client.list_running_models.return_value = {"models": []}
        client.unload_model.return_value = {}
        return client

    def _start(self, root: Path) -> tuple[dict[str, object], Path, Path]:
        plan_path = self._plan(root)
        authorization_path = self._authorization(root, plan_path)
        qualification_path = self._qualification(root)
        with patch(
            "local_llm_benchmark.log_incident_sweep_v05."
            "DEFAULT_CONTROLLER_QUALIFICATION",
            qualification_path,
        ):
            result = start_log_incident_sweep(
                REPO_ROOT,
                LogIncidentSweepConfig(
                    plan_path=plan_path,
                    authorization_path=authorization_path,
                    results_dir=root / "sweeps",
                    agent_results_dir=root / "runs",
                ),
            )
        return result, plan_path, qualification_path

    def test_plan_is_full_active_default_product(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            loaded = load_log_incident_sweep_plan(
                REPO_ROOT, self._plan(Path(temporary))
            )
            self.assertEqual(len(loaded["models"]), 5)
            self.assertEqual(len(loaded["plan"]["execution_order"]), 30)
            self.assertEqual(set(loaded["harnesses"]), set(HARNESS_IDS))

    def test_plan_rejects_missing_active_default_model(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            root = Path(temporary)
            plan_path = self._plan(root)
            plan = load_json(REPO_ROOT / plan_path)
            plan["deployments"].pop()
            write_json(REPO_ROOT / plan_path, plan)
            with self.assertRaisesRegex(RunnerError, "active-default cohort"):
                load_log_incident_sweep_plan(REPO_ROOT, plan_path)

    def test_authorization_is_bound_to_plan_and_models(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            root = Path(temporary)
            plan_path = self._plan(root)
            loaded = load_log_incident_sweep_plan(REPO_ROOT, plan_path)
            authorization_path = self._authorization(root, plan_path)
            authorization = load_execution_authorization(
                REPO_ROOT, authorization_path, loaded
            )
            self.assertEqual(
                authorization["authorization"]["plan_sha256"], loaded["sha256"]
            )
            document = load_json(REPO_ROOT / authorization_path)
            document["authorized_models"] = document["authorized_models"][:-1]
            write_json(REPO_ROOT / authorization_path, document)
            with self.assertRaisesRegex(RunnerError, "execution authorization"):
                load_execution_authorization(REPO_ROOT, authorization_path, loaded)

    def test_start_prepares_first_of_thirty_without_inference(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            result, _plan_path, _qualification_path = self._start(Path(temporary))
            self.assertEqual(result["unit_count"], 30)
            self.assertEqual(result["waiting"]["unit_status"], "awaiting_model")
            run = load_json(REPO_ROOT / result["waiting"]["run_dir"] / "run.json")
            self.assertEqual(run["execution_boundary"]["inference_requests_made"], 0)
            self.assertEqual(run["case"]["case_version"], "5.0.0")

    def test_live_boundary_requires_explicit_runtime_confirmation(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            root = Path(temporary)
            result, _plan_path, qualification_path = self._start(root)
            with patch(
                "local_llm_benchmark.log_incident_sweep_v05."
                "DEFAULT_CONTROLLER_QUALIFICATION",
                qualification_path,
            ):
                with self.assertRaisesRegex(RunnerError, "exclusive-window"):
                    run_log_incident_sweep_live(
                        REPO_ROOT,
                        Path(result["sweep_dir"]),
                        process_reader=lambda: [],
                        sleep=lambda _seconds: None,
                    )

    def test_mocked_live_boundary_checkpoints_without_ollama(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            root = Path(temporary)
            result, _plan_path, qualification_path = self._start(root)
            sweep = load_json(Path(result["sweep_dir"]) / "sweep.json")
            first = sweep["units"][0]

            def complete_model_call(_repo_root: Path, run_dir: Path) -> dict[str, str]:
                path = run_dir / "run.json"
                run = load_json(path)
                run["state"] = "awaiting_action"
                path.write_text(json.dumps(run), encoding="utf-8")
                return {"state": "awaiting_action"}

            with patch(
                "local_llm_benchmark.log_incident_sweep_v05."
                "DEFAULT_CONTROLLER_QUALIFICATION",
                qualification_path,
            ), patch(
                "local_llm_benchmark.log_incident_sweep_v05."
                "call_mini_log_v05_model",
                side_effect=complete_model_call,
            ):
                advanced = run_log_incident_sweep_live(
                    REPO_ROOT,
                    Path(result["sweep_dir"]),
                    client=self._client(first["model"], first["digest"]),
                    process_reader=lambda: [],
                    sleep=lambda _seconds: None,
                    exclusive_window_confirmed=True,
                )
            self.assertEqual(advanced["waiting"]["unit_status"], "awaiting_action")

    def test_public_report_aggregates_models_without_private_content(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            root = Path(temporary)
            result, _plan_path, qualification_path = self._start(root)
            sweep_dir = Path(result["sweep_dir"])
            sweep_path = sweep_dir / "sweep.json"
            sweep = load_json(sweep_path)
            for index, unit in enumerate(sweep["units"], start=1):
                raw_dir = root / f"raw-{index}"
                raw_dir.mkdir()
                semantic = index % 2 == 0
                strict = index % 3 != 0
                raw = {
                    "run_id": f"safe-v05-sweep-run-{index}",
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
            write_json(sweep_path, sweep)

            json_output = root / "public.json"
            markdown_output = root / "public.md"
            with patch(
                "local_llm_benchmark.log_incident_sweep_v05."
                "DEFAULT_CONTROLLER_QUALIFICATION",
                qualification_path,
            ):
                built = build_log_incident_sweep_report(
                    REPO_ROOT,
                    sweep_dir,
                    json_output=json_output,
                    markdown_output=markdown_output,
                )
            public_text = json_output.read_text(encoding="utf-8")
            public = json.loads(public_text)
            self.assertEqual(built["run_count"], 30)
            self.assertEqual(built["semantic_verified_success_count"], 15)
            self.assertEqual(len(public["by_model"]), 5)
            self.assertEqual(len(public["by_system_model"]), 10)
            self.assertNotIn("must not become public", public_text)
            self.assertNotIn("/Users/", public_text)
            self.assertTrue(
                public["method"]["supplemental_free_text_claim_review_required"]
            )


if __name__ == "__main__":
    unittest.main()
