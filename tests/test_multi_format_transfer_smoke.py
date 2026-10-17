from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from local_llm_benchmark.multi_format_transfer_smoke import (
    DEFAULT_AUTHORIZATION,
    DEFAULT_CONTROLLER_QUALIFICATION,
    DEFAULT_PLAN,
    MODEL,
    SYSTEM_IDS,
    TransferSmokeConfig,
    load_controller_qualification,
    load_execution_authorization,
    load_transfer_smoke_plan,
    run_transfer_smoke_live,
    start_transfer_smoke,
)
from local_llm_benchmark.multi_format_transfer_smoke_report import (
    build_transfer_smoke_report,
)
from local_llm_benchmark.runner import RunnerError, load_json, sha256_file, write_json


REPO_ROOT = Path(__file__).resolve().parents[1]
DIGEST = "5642e97495e1a088883805981563dcdc4a040c2f53388b7a41d1f24d3622cf7e"


class MultiFormatTransferSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.results = REPO_ROOT / "results"
        self.results.mkdir(exist_ok=True)

    def _authorization(self, root: Path) -> Path:
        loaded = load_transfer_smoke_plan(REPO_ROOT)
        path = root / "temporary-transfer-smoke-authorization.json"
        write_json(
            path,
            {
                "schema_version": "1.0.0",
                "authorization_id": (
                    "multi-format-transfer-smoke-v0.2-execution-authorization"
                ),
                "status": "authorized_pending_resource_gate",
                "plan_id": loaded["plan"]["plan_id"],
                "plan_sha256": loaded["sha256"],
                "live_execution_authorized": True,
                "unit_count": 2,
                "attempts_per_system": 1,
                "automatic_retries": 0,
                "authorized_model": MODEL,
                "authorized_systems": list(SYSTEM_IDS),
                "resource_gate_still_required": True,
            },
        )
        return path.relative_to(REPO_ROOT)

    @staticmethod
    def _acceptance() -> dict[str, object]:
        return {
            "passed": True,
            "validated_at": "2026-09-12T10:00:00Z",
            "profile_sha256": "a" * 64,
            "checks": [{"passed": True} for _ in range(13)],
        }

    @staticmethod
    def _write_pi_run(path: Path) -> None:
        path.mkdir(parents=True)
        write_json(
            path / "run.json",
            {
                "state": "prepared_not_executed",
                "execution_boundary": {
                    "sandbox_acceptance_passed": True,
                    "explicit_extension_acceptance_passed": True,
                },
                "trajectory": {"model_requests": 0},
            },
        )

    @staticmethod
    def _write_mini_run(path: Path) -> None:
        path.mkdir(parents=True)
        write_json(
            path / "run.json",
            {"state": "awaiting_model", "trajectory": {"model_requests": 0}},
        )

    def _mocked_start(self, root: Path) -> dict[str, object]:
        agent_root = root / "runs"
        pi_run = agent_root / "pi-run"
        mini_run = agent_root / "mini-run"

        def pi_prepare(*_args: object, **_kwargs: object) -> dict[str, object]:
            self._write_pi_run(pi_run)
            return {"run_id": "pi-run", "run_dir": pi_run}

        def mini_prepare(*_args: object, **_kwargs: object) -> dict[str, object]:
            self._write_mini_run(mini_run)
            return {"run_id": "mini-run", "run_dir": mini_run}

        with (
            patch(
                "local_llm_benchmark.multi_format_transfer_smoke.prepare_pi",
                side_effect=pi_prepare,
            ),
            patch(
                "local_llm_benchmark.multi_format_transfer_smoke.prepare_mini",
                side_effect=mini_prepare,
            ),
            patch(
                "local_llm_benchmark.multi_format_transfer_smoke.check_pi_sandbox",
                return_value=self._acceptance(),
            ),
            patch(
                "local_llm_benchmark.multi_format_transfer_smoke.OllamaClient",
                side_effect=AssertionError("offline start constructed Ollama client"),
            ),
        ):
            return start_transfer_smoke(
                REPO_ROOT,
                TransferSmokeConfig(
                    results_dir=(root / "studies").relative_to(REPO_ROOT),
                    agent_results_dir=agent_root.relative_to(REPO_ROOT),
                ),
            )

    @staticmethod
    def _client() -> MagicMock:
        client = MagicMock()
        client.version.return_value = {"version": "0.33.2"}
        client.list_models.return_value = {
            "models": [{"name": MODEL, "digest": DIGEST, "size": 18174721847}]
        }
        client.list_running_models.return_value = {"models": []}
        return client

    def test_plan_freezes_one_repair_first_attempt_per_system(self) -> None:
        loaded = load_transfer_smoke_plan(REPO_ROOT)
        plan = loaded["plan"]
        self.assertEqual(
            [item["system_id"] for item in plan["execution_order"]],
            list(SYSTEM_IDS),
        )
        self.assertEqual({item["model"] for item in plan["execution_order"]}, {MODEL})
        self.assertEqual(plan["comparison_rules"]["automatic_retries"], 0)
        self.assertTrue(plan["comparison_rules"]["excluded_from_measured_aggregates"])
        self.assertFalse(plan["authorization"]["live_execution_authorized"])

    def test_plan_binds_every_declared_input(self) -> None:
        plan = load_transfer_smoke_plan(REPO_ROOT)["plan"]
        for item in plan["frozen_inputs"]["artifacts"]:
            self.assertEqual(item["sha256"], sha256_file(REPO_ROOT / item["path"]))

    def test_plan_rejects_order_retry_and_authorization_drift(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            root = Path(temporary)
            for name, mutate, message in (
                (
                    "order",
                    lambda plan: plan["execution_order"].reverse(),
                    "execution order",
                ),
                (
                    "retry",
                    lambda plan: plan["comparison_rules"].update(
                        {"automatic_retries": 1}
                    ),
                    "comparison rules",
                ),
                (
                    "authorization",
                    lambda plan: plan["authorization"].update(
                        {"live_execution_authorized": True}
                    ),
                    "must not authorize",
                ),
            ):
                with self.subTest(name=name):
                    document = load_json(REPO_ROOT / DEFAULT_PLAN)
                    mutate(document)
                    path = root / f"{name}.json"
                    write_json(path, document)
                    with self.assertRaisesRegex(RunnerError, message):
                        load_transfer_smoke_plan(
                            REPO_ROOT, path.relative_to(REPO_ROOT)
                        )

    def test_plan_records_no_execution_authorization_at_freeze(self) -> None:
        plan = load_transfer_smoke_plan(REPO_ROOT)["plan"]
        self.assertFalse(plan["authorization"]["authorization_artifact_present"])
        self.assertEqual(
            plan["authorization"]["expected_future_path"],
            DEFAULT_AUTHORIZATION.as_posix(),
        )
        self.assertTrue(
            plan["authorization"]["post_freeze_hash_bound_authorization_required"]
        )

    def test_temporary_authorization_must_bind_exact_plan(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            root = Path(temporary)
            loaded = load_transfer_smoke_plan(REPO_ROOT)
            relative = self._authorization(root)
            admitted = load_execution_authorization(REPO_ROOT, relative, loaded)
            self.assertEqual(admitted["authorization"]["unit_count"], 2)
            document = load_json(REPO_ROOT / relative)
            document["plan_sha256"] = "0" * 64
            write_json(REPO_ROOT / relative, document)
            with self.assertRaisesRegex(RunnerError, "execution authorization"):
                load_execution_authorization(REPO_ROOT, relative, loaded)

    def test_controller_qualification_binds_implementation_and_tests(self) -> None:
        loaded = load_controller_qualification(REPO_ROOT)
        self.assertFalse(
            loaded["qualification"]["qualification_evidence"][
                "repository_execution_authorization_present"
            ]
        )
        self.assertEqual(
            loaded["path"], (REPO_ROOT / DEFAULT_CONTROLLER_QUALIFICATION).resolve()
        )

    def test_start_prepares_both_systems_without_authorization_or_ollama(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            summary = self._mocked_start(Path(temporary))
            self.assertEqual(summary["unit_count"], 2)
            self.assertEqual(summary["model_requests_observed"], 0)
            self.assertEqual(
                summary["status"], "prepared_pending_post_freeze_authorization"
            )
            study = load_json(REPO_ROOT / summary["study_dir"] / "study.json")
            self.assertIsNone(study["authorization"])
            self.assertEqual(
                [item["status"] for item in study["units"]],
                ["sandbox_ready", "awaiting_model"],
            )
            self.assertEqual(
                study["units"][0]["offline_seatbelt_acceptance"]["checks_total"],
                13,
            )
            self.assertFalse(
                study["units"][0]["offline_seatbelt_acceptance"][
                    "freshness_for_live_execution"
                ]
            )

    def test_live_boundary_requires_authorization_and_exclusive_window(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            root = Path(temporary)
            summary = self._mocked_start(root)
            authorization = self._authorization(root)
            client = self._client()
            with self.assertRaisesRegex(RunnerError, "exclusive window"):
                run_transfer_smoke_live(
                    REPO_ROOT,
                    Path(summary["study_dir"]),
                    authorization,
                    client=client,
                )
            client.version.assert_not_called()

    def test_mocked_pi_live_boundary_rechecks_seatbelt_without_real_ollama(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            root = Path(temporary)
            summary = self._mocked_start(root)
            authorization = self._authorization(root)

            def complete_pi(_repo_root: Path, run_dir: Path) -> dict[str, str]:
                path = run_dir / "run.json"
                record = load_json(path)
                record["state"] = "execution_complete_verification_pending"
                record["trajectory"] = {"model_requests": 4}
                write_json(path, record)
                return {"state": record["state"]}

            with (
                patch(
                    "local_llm_benchmark.multi_format_transfer_smoke.run_resource_gate",
                    return_value={"passed": True, "inference_requests_made": 0},
                ),
                patch(
                    "local_llm_benchmark.multi_format_transfer_smoke.check_pi_sandbox",
                    return_value=self._acceptance(),
                ) as acceptance,
                patch(
                    "local_llm_benchmark.multi_format_transfer_smoke.run_pi",
                    side_effect=complete_pi,
                ),
            ):
                advanced = run_transfer_smoke_live(
                    REPO_ROOT,
                    Path(summary["study_dir"]),
                    authorization,
                    client=self._client(),
                    process_reader=lambda: [],
                    sleep=lambda _seconds: None,
                    exclusive_window_confirmed=True,
                )
            self.assertEqual(advanced["waiting"]["unit_status"], "verification_pending")
            self.assertEqual(advanced["model_requests_observed"], 4)
            acceptance.assert_called_once()

    def test_public_report_excludes_private_content_and_paths(self) -> None:
        with tempfile.TemporaryDirectory(dir=self.results) as temporary:
            root = Path(temporary)
            summary = self._mocked_start(root)
            study_path = REPO_ROOT / summary["study_dir"] / "study.json"
            study = load_json(study_path)
            for index, unit in enumerate(study["units"], start=1):
                unit.update(
                    {
                        "status": "complete",
                        "private_candidate": "must remain private",
                        "outcome": {
                            "runtime_success": True,
                            "agent_termination_valid": True,
                            "semantic_verified_success": index == 1,
                            "strict_transport_compliance": True,
                            "failure_category": None,
                            "failure_type": None,
                        },
                        "verification": {
                            "essential_pass_count": 12 if index == 1 else 11,
                            "essential_check_count": 12,
                            "failed_check_ids": [] if index == 1 else ["award_mode"],
                        },
                        "trajectory": {
                            "model_requests": index,
                            "agent_turns": index,
                            "artifact_tool_calls": index + 2,
                            "active_wall_time_seconds": float(index),
                        },
                        "postflight_running_models": [],
                    }
                )
            study.update(
                {
                    "status": "complete",
                    "terminal_unit_count": 2,
                    "complete_unit_count": 2,
                }
            )
            write_json(study_path, study)
            report = build_transfer_smoke_report(
                REPO_ROOT, Path(summary["study_dir"])
            )
            serialized = json.dumps(report)
            self.assertEqual(len(report["outcomes"]), 2)
            self.assertNotIn("private_candidate", serialized)
            self.assertNotIn("must remain private", serialized)
            self.assertNotIn(str(REPO_ROOT), serialized)


if __name__ == "__main__":
    unittest.main()
