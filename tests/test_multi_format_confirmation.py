from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from local_llm_benchmark.multi_format_confirmation import (
    CONDITION_IDS,
    DEFAULT_PLAN,
    MODEL,
    MultiFormatConfirmationConfig,
    load_execution_authorization,
    load_multi_format_confirmation_plan,
    run_multi_format_confirmation_live,
    start_multi_format_confirmation,
)
from local_llm_benchmark.multi_format_confirmation_report import (
    build_multi_format_confirmation_report,
)
from local_llm_benchmark.runner import RunnerError, load_json, sha256_file, write_json


REPO_ROOT = Path(__file__).resolve().parents[1]
DIGEST = "5642e97495e1a088883805981563dcdc4a040c2f53388b7a41d1f24d3622cf7e"


class MultiFormatConfirmationTests(unittest.TestCase):
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

    def _authorization(self, root: Path, plan_path: Path = DEFAULT_PLAN) -> Path:
        loaded = load_multi_format_confirmation_plan(REPO_ROOT, plan_path)
        path = root / "temporary-confirmation-authorization.json"
        write_json(
            path,
            {
                "schema_version": "1.0.0",
                "authorization_id": (
                    "multi-format-qwen38-confirmation-v0.1-execution-authorization"
                ),
                "status": "authorized_pending_resource_gate",
                "plan_id": loaded["plan"]["plan_id"],
                "plan_sha256": loaded["sha256"],
                "live_execution_authorized": True,
                "cell_count": 9,
                "scheduled_repetitions_per_condition": 3,
                "automatic_retries": 0,
                "authorized_models": [MODEL],
                "authorized_conditions": list(CONDITION_IDS),
                "resource_gate_still_required": True,
            },
        )
        return path.relative_to(REPO_ROOT)

    def _start(self, root: Path) -> dict[str, object]:
        return start_multi_format_confirmation(
            REPO_ROOT,
            MultiFormatConfirmationConfig(
                authorization_path=self._authorization(root),
                results_dir=(root / "confirmations").relative_to(REPO_ROOT),
                agent_results_dir=(root / "runs").relative_to(REPO_ROOT),
            ),
        )

    def test_plan_is_exact_balanced_three_by_three_repetition_matrix(self) -> None:
        loaded = load_multi_format_confirmation_plan(REPO_ROOT)
        order = loaded["plan"]["execution_order"]
        self.assertEqual(len(order), 9)
        self.assertEqual({item["model"] for item in order}, {MODEL})
        self.assertEqual([item["position"] for item in order], list(range(1, 10)))
        for condition in CONDITION_IDS:
            cells = [item for item in order if item["condition_id"] == condition]
            self.assertEqual([item["repeat"] for item in cells], [1, 2, 3])
            self.assertEqual(sum(item["position"] for item in cells), 15)
        self.assertTrue(
            all(
                left["condition_id"] != right["condition_id"]
                for left, right in zip(order, order[1:])
            )
        )

    def test_plan_is_frozen_against_phase_94_without_live_authorization(self) -> None:
        loaded = load_multi_format_confirmation_plan(REPO_ROOT)
        plan = loaded["plan"]
        self.assertFalse(plan["authorization"]["live_execution_authorized"])
        self.assertFalse(plan["baseline_evidence"]["historical_cells_reused"])
        self.assertTrue(plan["deployment_selection"]["selection_is_post_hoc_to_capability_sweep"])
        commit = plan["frozen_inputs"]["phase_94_baseline_git_commit"]
        self.assertEqual(
            commit,
            "01baa7cce99e9445c80a4783e188ebb39db5807f",
        )
        qualification = load_json(
            REPO_ROOT
            / "tasks/agentic/multi-format-qwen38-confirmation-v0.1-controller-qualification.json"
        )
        self.assertFalse(
            qualification["qualification_evidence"][
                "repository_live_authorization_present"
            ]
        )

    def test_phase_94_commit_exists_in_private_research_history(self) -> None:
        if not (REPO_ROOT / "PROJECT_STATUS.md").is_file():
            self.skipTest("Private research history is not distributed in public snapshots")
        plan = load_multi_format_confirmation_plan(REPO_ROOT)["plan"]
        commit = plan["frozen_inputs"]["phase_94_baseline_git_commit"]
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0)

    def test_plan_rejects_comparison_or_order_drift(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            root = Path(temporary)
            for mutation, message in (
                (lambda plan: plan["comparison_rules"].update({"automatic_retries": 1}), "comparison rules"),
                (lambda plan: plan["execution_order"][0].update({"repeat": 2}), "balanced freeze"),
            ):
                with self.subTest(message=message):
                    plan = load_json(REPO_ROOT / DEFAULT_PLAN)
                    mutation(plan)
                    path = root / f"drift-{message.replace(' ', '-')}.json"
                    write_json(path, plan)
                    with self.assertRaisesRegex(RunnerError, message):
                        load_multi_format_confirmation_plan(
                            REPO_ROOT, path.relative_to(REPO_ROOT)
                        )

    def test_authorization_is_separate_and_hash_bound_after_freeze(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            root = Path(temporary)
            loaded = load_multi_format_confirmation_plan(REPO_ROOT)
            path = self._authorization(root)
            authorized = load_execution_authorization(REPO_ROOT, path, loaded)
            self.assertEqual(authorized["authorization"]["cell_count"], 9)
            document = load_json(REPO_ROOT / path)
            document["plan_sha256"] = "0" * 64
            write_json(REPO_ROOT / path, document)
            with self.assertRaisesRegex(RunnerError, "execution authorization"):
                load_execution_authorization(REPO_ROOT, path, loaded)

    def test_start_prepares_first_canonical_cell_without_inference(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            result = self._start(Path(temporary))
            self.assertEqual(result["unit_count"], 9)
            self.assertEqual(result["waiting"]["condition_id"], CONDITION_IDS[0])
            self.assertEqual(result["waiting"]["unit_status"], "awaiting_model")
            run = load_json(REPO_ROOT / result["waiting"]["run_dir"] / "run.json")
            self.assertEqual(run["execution_boundary"]["inference_requests_made"], 0)

    def test_live_boundary_requires_explicit_exclusive_window(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            result = self._start(Path(temporary))
            with self.assertRaisesRegex(RunnerError, "exclusive-window"):
                run_multi_format_confirmation_live(
                    REPO_ROOT, Path(result["study_dir"]), client=self._client()
                )

    def test_mocked_live_boundary_checkpoints_without_real_ollama(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            result = self._start(Path(temporary))

            def complete(_repo_root: Path, run_dir: Path) -> dict[str, str]:
                path = run_dir / "run.json"
                run = load_json(path)
                run["state"] = "execution_complete_verification_pending"
                write_json(path, run)
                return {"state": run["state"]}

            with patch(
                "local_llm_benchmark.multi_format_study.execute_canonical_run",
                side_effect=complete,
            ):
                advanced = run_multi_format_confirmation_live(
                    REPO_ROOT,
                    Path(result["study_dir"]),
                    client=self._client(),
                    process_reader=lambda: [],
                    sleep=lambda _seconds: None,
                    exclusive_window_confirmed=True,
                )
            self.assertEqual(advanced["waiting"]["unit_status"], "verification_pending")

    def test_public_report_separates_conditions_and_private_content(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            root = Path(temporary)
            study_dir = root / "terminal-confirmation"
            study_dir.mkdir()
            plan = load_json(REPO_ROOT / DEFAULT_PLAN)
            units = []
            for item in plan["execution_order"]:
                semantic = item["condition_id"] != CONDITION_IDS[0]
                units.append(
                    {
                        **item,
                        "track": "A" if item["condition_id"] == CONDITION_IDS[0] else "B",
                        "deployment_id": "safe-qwen38-deployment",
                        "run_id": f"safe-run-{item['position']}",
                        "status": "complete",
                        "private_candidate_marker": "must not become public",
                        "outcome": {
                            "runtime_success": True,
                            "agent_termination_valid": True,
                            "semantic_verified_success": semantic,
                            "strict_transport_compliance": True,
                            "failure_category": None if semantic else "task_or_verification_failure",
                            "failure_type": None if semantic else "deterministic_checks_failed",
                        },
                        "verification": {
                            "essential_pass_count": 11 if semantic else 10,
                            "essential_check_count": 11,
                            "failed_check_ids": [] if semantic else ["decision"],
                        },
                        "trajectory": {"active_wall_time_seconds": float(item["position"])},
                        "sandbox_acceptance": None,
                    }
                )
            write_json(
                study_dir / "study.json",
                {
                    "schema_version": "1.0.0",
                    "study_id": "safe-qwen38-confirmation",
                    "status": "complete",
                    "evidence_class": "measured_targeted_confirmation",
                    "plan": {
                        "path": DEFAULT_PLAN.as_posix(),
                        "sha256": sha256_file(REPO_ROOT / DEFAULT_PLAN),
                    },
                    "units": units,
                },
            )
            report = build_multi_format_confirmation_report(
                REPO_ROOT, study_dir.relative_to(REPO_ROOT)
            )
            serialized = json.dumps(report)
            by_condition = {
                item["condition_id"]: item for item in report["by_condition"]
            }
            self.assertEqual(report["cell_count"], 9)
            self.assertEqual(
                by_condition[CONDITION_IDS[0]]["semantic_verified_success_count"], 0
            )
            self.assertEqual(
                by_condition[CONDITION_IDS[1]]["semantic_verified_success_count"], 3
            )
            self.assertNotIn("private_candidate_marker", serialized)
            self.assertNotIn(str(REPO_ROOT), serialized)


if __name__ == "__main__":
    unittest.main()
