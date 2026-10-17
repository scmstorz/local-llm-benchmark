from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from local_llm_benchmark.multi_format_mini import (
    MiniMultiFormatStartConfig,
    call_mini_multi_format_model,
    finalize_mini_multi_format_run,
    load_mini_multi_format_harness,
    start_mini_multi_format_run,
    step_mini_multi_format_action,
)
from local_llm_benchmark.runner import load_json, sha256_file, write_json


REPO_ROOT = Path(__file__).resolve().parents[1]


class MiniMultiFormatHarnessTests(unittest.TestCase):
    def _start(self, parent: Path) -> Path:
        result = start_mini_multi_format_run(
            REPO_ROOT,
            MiniMultiFormatStartConfig(model="not-contacted:test", results_dir=parent),
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
        record["turns"] = [{"turn": 1, "response": "turns/001-response.txt", "response_sha256": sha256_file(path), "action": None, "action_status": "pending"}]
        write_json(run_dir / "run.json", record)

    def test_definition_exposes_only_five_structured_actions(self) -> None:
        loaded = load_mini_multi_format_harness(REPO_ROOT)
        self.assertEqual(
            loaded["harness"]["actions"],
            ["list_artifacts", "read_docx", "read_pdf", "read_xlsx", "finish_report"],
        )
        self.assertEqual(len(loaded["action_schema"]["oneOf"]), 5)

    def test_start_copies_only_three_artifacts_without_inference_or_hidden_content(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._start(Path(temporary))
            record = load_json(run_dir / "run.json")
            request = load_json(run_dir / record["artifacts"]["pending_request"])
            self.assertEqual(sorted(path.name for path in (run_dir / "workspace").iterdir()), ["regional-readiness.xlsx", "reliability-review.pdf", "rollout-policy.docx"])
            self.assertEqual(record["execution_boundary"]["inference_requests_made"], 0)
            serialized = json.dumps(request)
            self.assertNotIn("support_capacity=137", serialized)
            self.assertNotIn("Central | 96% | 0 | 3", serialized)

    def test_shared_backend_observation_and_audit_are_complete(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._start(Path(temporary))
            self._fake_response(run_dir, {"action": "read_pdf", "page": 3, "element": "table=Final-validation&row=North"})
            result = step_mini_multi_format_action(REPO_ROOT, run_dir)
            self.assertTrue(result["observation"]["ok"])
            self.assertEqual(result["observation"]["record"]["fact_code"], "REL-NORTH")
            audit = (run_dir / "trajectory.jsonl").read_text(encoding="utf-8")
            self.assertIn('"result_sha256"', audit)
            self.assertIn('"source_ref":"reliability-review.pdf#page=3&table=Final-validation&row=North"', audit)

    def test_unlisted_anchor_is_rejected_without_path_access(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._start(Path(temporary))
            self._fake_response(run_dir, {"action": "read_docx", "anchor": "../reference"})
            result = step_mini_multi_format_action(REPO_ROOT, run_dir)
            self.assertFalse(result["observation"]["ok"])
            self.assertEqual(result["observation"]["failure_code"], "unknown_anchor")

    def test_reference_report_finishes_and_verifies_separately(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._start(Path(temporary))
            case = load_json(REPO_ROOT / "tasks/agentic/multi-format-document-analysis/rollout-readiness-reconciliation/case-v0.1.json")
            report = load_json(REPO_ROOT / case["verification"]["reference_report_path"])
            self._fake_response(run_dir, {"action": "finish_report", "report": report})
            stopped = step_mini_multi_format_action(REPO_ROOT, run_dir)
            result = finalize_mini_multi_format_run(REPO_ROOT, run_dir)
            self.assertEqual(stopped["termination_reason"], "finish_report")
            self.assertTrue(result["semantic_verified_success"])
            self.assertEqual(result["verification"]["essential_pass_count"], 11)

    def test_mocked_model_boundary_records_one_request_without_network(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._start(Path(temporary))
            client = MagicMock()
            client.version.return_value = {"version": "mock"}
            client.list_models.return_value = {"models": [{"name": "not-contacted:test", "digest": "0" * 64, "size": 1, "details": {}}]}
            client.show_model.return_value = {"capabilities": ["completion"], "parameters": "", "template": "mock"}

            def fake_turn(_client, _payload, stream_path):
                stream_path.write_text('{"mock":true}\n', encoding="utf-8")
                return {"content": '{"action":"list_artifacts"}', "thinking": "", "wall_time_seconds": 0.01, "time_to_first_content_seconds": 0.005, "final_event": {"done_reason": "stop", "prompt_eval_count": 10, "eval_count": 3, "load_duration": 1, "eval_duration": 1}}

            with (
                patch("local_llm_benchmark.multi_format_mini.OllamaClient", return_value=client),
                patch("local_llm_benchmark.multi_format_mini._collect_ollama_turn", side_effect=fake_turn),
            ):
                result = call_mini_multi_format_model(REPO_ROOT, run_dir)
            self.assertEqual(result["state"], "awaiting_action")
            self.assertEqual(load_json(run_dir / "run.json")["execution_boundary"]["inference_requests_made"], 1)


if __name__ == "__main__":
    unittest.main()
