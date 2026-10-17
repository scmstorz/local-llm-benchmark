from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from local_llm_benchmark.multi_format_study import (
    CONDITION_IDS,
    MultiFormatStudyConfig,
    load_execution_authorization,
    load_multi_format_study_plan,
    run_multi_format_study_live,
    start_multi_format_study,
)
from local_llm_benchmark.multi_format_study_report import build_multi_format_study_report
from local_llm_benchmark.runner import RunnerError, load_json, sha256_file, write_json


REPO_ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE = Path("models/lifecycle.json")
IDENTITIES = Path("tasks/agentic/track-b/log-incident-capability-sweep-v0.5.json")
SMOKE_REPORT = Path("reports/agentic/multi-format-qualification-smokes-v0.1.json")
TRACK_A = Path("tasks/agentic/track-a/multi-format-canonical-v0.1.json")
TRACK_A_QUALIFICATION = Path(
    "tasks/agentic/track-a/multi-format-canonical-v0.1-qualification.json"
)
MINI = Path("tasks/agentic/track-b/mini-multi-format-v0.1.json")
MINI_QUALIFICATION = Path("tasks/agentic/track-b/mini-multi-format-v0.1-qualification.json")
PI = Path("tasks/agentic/track-b/pi-multi-format-v0.3.json")
PI_QUALIFICATION = Path("tasks/agentic/track-b/pi-multi-format-v0.3-qualification.json")


class MultiFormatStudyTests(unittest.TestCase):
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
        identities = load_json(REPO_ROOT / IDENTITIES)
        by_name = {item["name"]: item for item in identities["deployments"]}
        deployments = [by_name[name] for name in names]
        # Condition slots cycle A/Mini/Pi. This order has no adjacent model repeat.
        sequence = [
            (CONDITION_IDS[0], names[0]),
            (CONDITION_IDS[1], names[4]),
            (CONDITION_IDS[2], names[3]),
            (CONDITION_IDS[0], names[1]),
            (CONDITION_IDS[1], names[0]),
            (CONDITION_IDS[2], names[4]),
            (CONDITION_IDS[0], names[2]),
            (CONDITION_IDS[1], names[1]),
            (CONDITION_IDS[2], names[2]),
            (CONDITION_IDS[0], names[3]),
            (CONDITION_IDS[1], names[2]),
            (CONDITION_IDS[2], names[1]),
            (CONDITION_IDS[0], names[4]),
            (CONDITION_IDS[1], names[3]),
            (CONDITION_IDS[2], names[0]),
        ]
        prior = load_json(REPO_ROOT / IDENTITIES)
        plan = {
            "schema_version": "1.0.0",
            "plan_id": "multi-format-capability-sweep-v0.1",
            "status": "frozen_before_execution",
            "track": "A+B",
            "study_mode": "capability_sweep",
            "evidence_class": "measured_capability_sweep",
            "runtime": {
                "name": "ollama",
                "expected_version": "0.33.2",
                "host": "http://127.0.0.1:11434",
                "must_be_reverified_before_execution": True,
            },
            "qualification_gate": {
                "smoke_report_path": SMOKE_REPORT.as_posix(),
                "smoke_report_sha256": sha256_file(REPO_ROOT / SMOKE_REPORT),
                "smoke_runs_reused_as_measured": False,
            },
            "model_selection": {
                "source": LIFECYCLE.as_posix(),
                "source_sha256": sha256_file(REPO_ROOT / LIFECYCLE),
                "deployment_identity_source": IDENTITIES.as_posix(),
                "deployment_identity_source_sha256": sha256_file(REPO_ROOT / IDENTITIES),
                "rule": "include_in_default_sweeps equals true",
                "selected_count": 5,
            },
            "conditions": [
                {
                    "condition_id": CONDITION_IDS[0],
                    "condition_path": TRACK_A.as_posix(),
                    "qualification_id": "multi-format-canonical-v0.1-no-inference-qualification",
                    "qualification_path": TRACK_A_QUALIFICATION.as_posix(),
                    "qualification_sha256": sha256_file(REPO_ROOT / TRACK_A_QUALIFICATION),
                },
                {
                    "condition_id": CONDITION_IDS[1],
                    "harness_path": MINI.as_posix(),
                    "qualification_id": "mini-multi-format-v0.1-no-inference-qualification",
                    "qualification_path": MINI_QUALIFICATION.as_posix(),
                    "qualification_sha256": sha256_file(REPO_ROOT / MINI_QUALIFICATION),
                },
                {
                    "condition_id": CONDITION_IDS[2],
                    "harness_path": PI.as_posix(),
                    "qualification_id": "pi-multi-format-v0.3-no-inference-qualification",
                    "qualification_path": PI_QUALIFICATION.as_posix(),
                    "qualification_sha256": sha256_file(REPO_ROOT / PI_QUALIFICATION),
                },
            ],
            "deployments": deployments,
            "execution_order": [
                {"position": index, "condition_id": condition, "model": model}
                for index, (condition, model) in enumerate(sequence, start=1)
            ],
            "shared_inference": {
                "temperature": 0.0,
                "seed": 42,
                "think": False,
                "num_ctx": 16384,
                "num_predict_per_turn": 5000,
                "maximum_active_wall_time_seconds": 300,
                "provider_request_timeout_seconds": 180,
            },
            "outcome_model": {
                "primary": "semantic_verified_success",
                "secondary": "strict_transport_compliance",
                "supplemental_free_text_claim_review_required": True,
                "composite_score": False,
            },
            "comparison_rules": {
                "runs_per_configuration": 1,
                "automatic_retries": 0,
                "adaptive_repetitions": False,
                "terminal_attempts_not_repeated": True,
                "track_a_and_track_b_pooled": False,
                "one_factor_causal_harness_claim_allowed": False,
                "reliability_probability_claims": False,
                "latency_distribution_claims": False,
            },
            "resource_gate": {
                "empty_state_observation_seconds": 30,
                "loaded_models_must_be_empty_before_each_unit": True,
                "model_unloaded_after_each_unit": True,
                "blocking_process_rules": prior["resource_gate"]["blocking_process_rules"],
            },
            "authorization": {
                "live_execution_authorized": False,
                "post_freeze_authorization_required": True,
                "fresh_clean_window_confirmation_required": True,
            },
            "frozen_inputs": {
                "artifacts": [
                    {"path": TRACK_A.as_posix(), "sha256": sha256_file(REPO_ROOT / TRACK_A)}
                ]
            },
        }
        path = root / "temporary-multi-format-plan.json"
        write_json(path, plan)
        return path.relative_to(REPO_ROOT)

    def _authorization(self, root: Path, plan_path: Path) -> Path:
        loaded = load_multi_format_study_plan(REPO_ROOT, plan_path)
        path = root / "temporary-multi-format-authorization.json"
        write_json(
            path,
            {
                "schema_version": "1.0.0",
                "authorization_id": "multi-format-capability-sweep-v0.1-execution-authorization",
                "status": "authorized_pending_resource_gate",
                "plan_id": loaded["plan"]["plan_id"],
                "plan_sha256": loaded["sha256"],
                "live_execution_authorized": True,
                "cell_count": 15,
                "automatic_retries": 0,
                "authorized_models": list(loaded["models"]),
                "authorized_conditions": list(CONDITION_IDS),
                "resource_gate_still_required": True,
            },
        )
        return path.relative_to(REPO_ROOT)

    def _controller_qualification(self, root: Path) -> Path:
        artifacts = [
            Path("local_llm_benchmark/multi_format_study.py"),
            Path("local_llm_benchmark/multi_format_study_report.py"),
        ]
        path = root / "temporary-multi-format-controller-qualification.json"
        write_json(
            path,
            {
                "schema_version": "1.0.0",
                "qualification_id": "multi-format-capability-sweep-v0.1-controller-no-inference",
                "status": "qualified_for_frozen_plan",
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

    def _start(self, root: Path) -> tuple[dict, Path]:
        plan_path = self._plan(root)
        authorization = self._authorization(root, plan_path)
        qualification = self._controller_qualification(root)
        with patch(
            "local_llm_benchmark.multi_format_study.DEFAULT_CONTROLLER_QUALIFICATION",
            qualification,
        ):
            result = start_multi_format_study(
                REPO_ROOT,
                MultiFormatStudyConfig(
                    plan_path=plan_path,
                    authorization_path=authorization,
                    results_dir=(root / "studies").relative_to(REPO_ROOT),
                    agent_results_dir=(root / "runs").relative_to(REPO_ROOT),
                ),
            )
        return result, qualification

    def test_plan_is_full_three_condition_active_default_product(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            loaded = load_multi_format_study_plan(REPO_ROOT, self._plan(Path(temporary)))
            self.assertEqual(len(loaded["models"]), 5)
            self.assertEqual(len(loaded["conditions"]), 3)
            self.assertEqual(len(loaded["plan"]["execution_order"]), 15)

    def test_plan_rejects_track_pooling(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            path = self._plan(Path(temporary))
            plan = load_json(REPO_ROOT / path)
            plan["comparison_rules"]["track_a_and_track_b_pooled"] = True
            write_json(REPO_ROOT / path, plan)
            with self.assertRaisesRegex(RunnerError, "comparison rules"):
                load_multi_format_study_plan(REPO_ROOT, path)

    def test_authorization_is_hash_bound_after_plan(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            root = Path(temporary)
            plan_path = self._plan(root)
            loaded = load_multi_format_study_plan(REPO_ROOT, plan_path)
            authorization = self._authorization(root, plan_path)
            self.assertEqual(
                load_execution_authorization(REPO_ROOT, authorization, loaded)["authorization"]["cell_count"],
                15,
            )
            document = load_json(REPO_ROOT / authorization)
            document["plan_sha256"] = "0" * 64
            write_json(REPO_ROOT / authorization, document)
            with self.assertRaisesRegex(RunnerError, "execution authorization"):
                load_execution_authorization(REPO_ROOT, authorization, loaded)

    def test_start_prepares_track_a_without_inference(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            result, _qualification = self._start(Path(temporary))
            self.assertEqual(result["unit_count"], 15)
            self.assertEqual(result["waiting"]["condition_id"], CONDITION_IDS[0])
            self.assertEqual(result["waiting"]["unit_status"], "awaiting_model")
            run = load_json(REPO_ROOT / result["waiting"]["run_dir"] / "run.json")
            self.assertEqual(run["execution_boundary"]["inference_requests_made"], 0)

    def test_live_boundary_requires_explicit_confirmation(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            result, qualification = self._start(Path(temporary))
            with patch(
                "local_llm_benchmark.multi_format_study.DEFAULT_CONTROLLER_QUALIFICATION",
                qualification,
            ), self.assertRaisesRegex(RunnerError, "exclusive-window"):
                run_multi_format_study_live(REPO_ROOT, Path(result["study_dir"]))

    def test_mocked_live_boundary_checkpoints_without_ollama(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            result, qualification = self._start(Path(temporary))
            study = load_json(Path(result["study_dir"]) / "study.json")
            first = study["units"][0]

            def complete(_repo_root: Path, run_dir: Path) -> dict:
                path = run_dir / "run.json"
                run = load_json(path)
                run["state"] = "execution_complete_verification_pending"
                write_json(path, run)
                return {"state": run["state"]}

            with patch(
                "local_llm_benchmark.multi_format_study.DEFAULT_CONTROLLER_QUALIFICATION",
                qualification,
            ), patch(
                "local_llm_benchmark.multi_format_study.execute_canonical_run",
                side_effect=complete,
            ):
                advanced = run_multi_format_study_live(
                    REPO_ROOT,
                    Path(result["study_dir"]),
                    client=self._client(first["model"], first["digest"]),
                    process_reader=lambda: [],
                    sleep=lambda _seconds: None,
                    exclusive_window_confirmed=True,
                )
            self.assertEqual(advanced["waiting"]["unit_status"], "verification_pending")

    def test_public_report_excludes_private_content(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            root = Path(temporary)
            plan_path = self._plan(root)
            study_dir = root / "terminal-study"
            study_dir.mkdir()
            units = []
            for index, item in enumerate(
                load_json(REPO_ROOT / plan_path)["execution_order"], start=1
            ):
                units.append(
                    {
                        **item,
                        "track": "A" if item["condition_id"] == CONDITION_IDS[0] else "B",
                        "deployment_id": f"safe-deployment-{index}",
                        "run_id": f"safe-run-{index}",
                        "status": "complete",
                        "private_candidate_marker": "must not become public",
                        "outcome": {
                            "runtime_success": True,
                            "agent_termination_valid": True,
                            "semantic_verified_success": index % 2 == 0,
                            "strict_transport_compliance": True,
                            "failure_category": None,
                        },
                        "verification": {
                            "essential_pass_count": 10,
                            "essential_check_count": 11,
                            "failed_check_ids": ["decision"],
                        },
                        "trajectory": {"active_wall_time_seconds": float(index)},
                        "sandbox_acceptance": None,
                    }
                )
            write_json(
                study_dir / "study.json",
                {
                    "schema_version": "1.0.0",
                    "study_id": "safe-study",
                    "status": "complete",
                    "plan": {
                        "path": plan_path.as_posix(),
                        "sha256": sha256_file(REPO_ROOT / plan_path),
                    },
                    "units": units,
                },
            )
            report = build_multi_format_study_report(
                REPO_ROOT, study_dir.relative_to(REPO_ROOT)
            )
            serialized = json.dumps(report)
            self.assertEqual(report["cell_count"], 15)
            self.assertNotIn("private_candidate_marker", serialized)
            self.assertNotIn(str(REPO_ROOT), serialized)


if __name__ == "__main__":
    unittest.main()
