from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from local_llm_benchmark.multi_format_mini_v02 import (
    DEFAULT_CASE_PATH,
    HARNESS_ID,
    call,
    finalize,
    load_mini_multi_format_v02_case,
    load_mini_multi_format_v02_harness,
    start,
    step,
)
from local_llm_benchmark.multi_format_mini import MiniMultiFormatStartConfig
from local_llm_benchmark.runner import load_json, sha256_file, write_json


REPO_ROOT = Path(__file__).resolve().parents[1]


class MiniMultiFormatV02Tests(unittest.TestCase):
    def _start(self, parent: Path) -> Path:
        result = start(
            REPO_ROOT,
            MiniMultiFormatStartConfig(
                model="not-contacted:test", results_dir=parent
            ),
        )
        self.assertEqual(result["inference_requests_made"], 0)
        return Path(result["run_dir"])

    def _fake_response(self, run_dir: Path, response: dict[str, object]) -> None:
        record = load_json(run_dir / "run.json")
        path = run_dir / "turns/001-response.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(response) + "\n", encoding="utf-8")
        record["state"] = "awaiting_action"
        record["artifacts"]["pending_request"] = None
        record["artifacts"]["pending_request_sha256"] = None
        record["trajectory"]["agent_turns"] = 1
        record["turns"] = [
            {
                "turn": 1,
                "response": "turns/001-response.txt",
                "response_sha256": sha256_file(path),
                "action": None,
                "action_status": "pending",
            }
        ]
        write_json(run_dir / "run.json", record)

    def test_definition_binds_transfer_case_backend_and_report_schema(self) -> None:
        harness = load_mini_multi_format_v02_harness(REPO_ROOT)
        loaded = load_mini_multi_format_v02_case(REPO_ROOT)
        self.assertEqual(harness["harness"]["harness_id"], HARNESS_ID)
        self.assertEqual(
            harness["capability_inventory"]["shared_backend"],
            "local_llm_benchmark/multi_format_transfer_artifacts.py",
        )
        expected = {
            key: loaded["schema"][key]
            for key in ("type", "additionalProperties", "required", "properties")
        }
        self.assertEqual(
            harness["action_schema"]["$defs"]["decision_report"], expected
        )

    def test_start_copies_only_supplier_artifacts_and_freezes_new_identity(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._start(Path(temporary))
            record = load_json(run_dir / "run.json")
            request = load_json(run_dir / record["artifacts"]["pending_request"])
            self.assertEqual(record["harness"]["harness_id"], HARNESS_ID)
            self.assertEqual(
                record["harness"]["implementation_path"],
                "local_llm_benchmark/multi_format_mini_v02.py",
            )
            self.assertEqual(
                record["harness"]["artifact_backend_path"],
                "local_llm_benchmark/multi_format_transfer_artifacts.py",
            )
            self.assertEqual(
                sorted(path.name for path in (run_dir / "workspace").iterdir()),
                [
                    "bid-evaluation.xlsx",
                    "supplier-assurance-review.pdf",
                    "supplier-selection-policy.docx",
                ],
            )
            self.assertNotIn("adjusted_first_year_cost_eur=1140000", json.dumps(request))

    def test_shared_backend_observation_is_exact_and_audited(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._start(Path(temporary))
            self._fake_response(
                run_dir,
                {
                    "action": "read_pdf",
                    "page": 3,
                    "element": "table=Final-assurance&row=Cedar",
                },
            )
            result = step(REPO_ROOT, run_dir)
            self.assertEqual(result["observation"]["record"]["fact_code"], "ASSUR-CEDAR")
            audit = (run_dir / "trajectory.jsonl").read_text(encoding="utf-8")
            self.assertIn('"result_sha256"', audit)
            self.assertIn(
                "supplier-assurance-review.pdf#page=3&table=Final-assurance&row=Cedar",
                audit,
            )

    def test_unlisted_anchor_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._start(Path(temporary))
            self._fake_response(
                run_dir, {"action": "read_docx", "anchor": "../reference"}
            )
            result = step(REPO_ROOT, run_dir)
            self.assertEqual(result["observation"]["failure_code"], "unknown_anchor")

    def test_reference_report_finishes_with_twelve_checks(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._start(Path(temporary))
            case = load_json(REPO_ROOT / DEFAULT_CASE_PATH)
            report = load_json(REPO_ROOT / case["verification"]["reference_report_path"])
            self._fake_response(run_dir, {"action": "finish_report", "report": report})
            stopped = step(REPO_ROOT, run_dir)
            result = finalize(REPO_ROOT, run_dir)
            self.assertEqual(stopped["termination_reason"], "finish_report")
            self.assertTrue(result["semantic_verified_success"])
            self.assertTrue(result["strict_transport_compliance"])
            self.assertEqual(result["verification"]["essential_pass_count"], 12)

    def test_mocked_model_boundary_records_one_request_without_network(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._start(Path(temporary))
            client = MagicMock()
            client.version.return_value = {"version": "mock"}
            client.list_models.return_value = {
                "models": [
                    {
                        "name": "not-contacted:test",
                        "digest": "0" * 64,
                        "size": 1,
                        "details": {},
                    }
                ]
            }
            client.show_model.return_value = {
                "capabilities": ["completion"],
                "parameters": "",
                "template": "mock",
            }

            def fake_turn(_client, _payload, stream_path):
                stream_path.write_text('{"mock":true}\n', encoding="utf-8")
                return {
                    "content": '{"action":"list_artifacts"}',
                    "thinking": "",
                    "wall_time_seconds": 0.01,
                    "time_to_first_content_seconds": 0.005,
                    "final_event": {
                        "done_reason": "stop",
                        "prompt_eval_count": 10,
                        "eval_count": 3,
                        "load_duration": 1,
                        "eval_duration": 1,
                    },
                }

            with (
                patch(
                    "local_llm_benchmark.multi_format_mini.OllamaClient",
                    return_value=client,
                ),
                patch(
                    "local_llm_benchmark.multi_format_mini._collect_ollama_turn",
                    side_effect=fake_turn,
                ),
            ):
                result = call(REPO_ROOT, run_dir)
            self.assertEqual(result["state"], "awaiting_action")
            self.assertEqual(
                load_json(run_dir / "run.json")["execution_boundary"][
                    "inference_requests_made"
                ],
                1,
            )


if __name__ == "__main__":
    unittest.main()
