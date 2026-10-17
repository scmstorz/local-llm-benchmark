from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_llm_benchmark.multi_format_metrics_v02 import (
    aggregate_metrics,
    build_metrics_report,
    normalize_run,
    write_metrics_report,
)
from local_llm_benchmark.runner import RunnerError, load_json, sha256_file


ROOT = Path(__file__).resolve().parents[1]
STUDY = Path("results/agentic-transfer-smokes/multi-format-transfer-smoke-20261017T100311Z-551af02f")


def pi_run() -> dict:
    return {"harness": {"harness_id": "pi-multi-format-v0.4"}, "trajectory": {"tool_calls": 18, "finish_report_calls": 1, "list_calls": 1, "docx_reads": 4, "pdf_reads": 6, "xlsx_reads": 6, "agent_turns": 6}}


def mini_run() -> dict:
    actions = ["list_artifacts"] + ["read_docx"] * 4 + ["read_pdf"] * 6 + ["read_xlsx"] * 6 + ["finish_report"]
    return {"harness": {"harness_id": "mini-multi-format-v0.2"}, "trajectory": {"tool_calls": 17, "agent_turns": 18, "model_requests": 18}, "turns": [{"action": action} for action in actions]}


class SupplierMetricsV02Tests(unittest.TestCase):
    def test_pi_split_excludes_completion_and_requests_stay_unknown(self) -> None:
        result = normalize_run(pi_run())
        self.assertEqual(result["artifact_tool_calls"], 17)
        self.assertEqual(result["completion_calls"], 1)
        self.assertEqual(result["adapter_tool_calls"], 18)
        self.assertIsNone(result["model_requests"])
        self.assertEqual(result["model_requests_status"], "unknown")
        self.assertEqual(result["agent_turns"], 6)

    def test_mini_split_does_not_subtract_completion_twice(self) -> None:
        result = normalize_run(mini_run())
        self.assertEqual(result["artifact_tool_calls"], 17)
        self.assertEqual(result["completion_calls"], 1)
        self.assertEqual(result["total_tool_or_action_calls"], 18)
        self.assertEqual(result["model_requests"], 18)

    def test_missing_pi_component_does_not_become_zero(self) -> None:
        record = pi_run()
        del record["trajectory"]["docx_reads"]
        self.assertIsNone(normalize_run(record)["artifact_tool_calls"])

    def test_missing_mini_turns_keeps_completion_unknown(self) -> None:
        record = mini_run()
        del record["turns"]
        result = normalize_run(record)
        self.assertEqual(result["artifact_tool_calls"], 17)
        self.assertIsNone(result["completion_calls"])
        self.assertIsNone(result["total_tool_or_action_calls"])

    def test_mixed_known_and_unknown_requests_have_no_pair_total(self) -> None:
        totals = aggregate_metrics([normalize_run(pi_run()), normalize_run(mini_run())])
        self.assertEqual(totals["model_requests"], {"value": None, "known_subtotal": 18, "known_unit_count": 1, "unit_count": 2, "complete": False})
        self.assertEqual(totals["artifact_tool_calls"]["value"], 34)
        self.assertEqual(totals["completion_calls"]["value"], 2)

    def test_all_unknown_has_no_zero_subtotal(self) -> None:
        result = aggregate_metrics([normalize_run(pi_run())])["model_requests"]
        self.assertIsNone(result["value"])
        self.assertIsNone(result["known_subtotal"])

    def test_recorded_zero_is_distinct_from_unknown(self) -> None:
        record = mini_run()
        record["trajectory"].update(model_requests=0, tool_calls=0, agent_turns=0)
        record["turns"] = []
        result = aggregate_metrics([normalize_run(record)])["model_requests"]
        self.assertEqual(result["value"], 0)
        self.assertTrue(result["complete"])

    def test_invalid_counter_values_are_rejected(self) -> None:
        for value in (-1, True, "18", 1.5):
            with self.subTest(value=value):
                record = mini_run()
                record["trajectory"]["model_requests"] = value
                with self.assertRaises(RunnerError):
                    normalize_run(record)

    def test_inconsistent_pi_split_is_rejected(self) -> None:
        record = pi_run()
        record["trajectory"]["tool_calls"] = 17
        with self.assertRaisesRegex(RunnerError, "Pi native"):
            normalize_run(record)

    def test_inconsistent_mini_actions_are_rejected(self) -> None:
        record = mini_run()
        record["turns"].pop(0)
        with self.assertRaisesRegex(RunnerError, "Mini native"):
            normalize_run(record)

    def test_unknown_adapter_is_rejected(self) -> None:
        record = pi_run()
        record["harness"]["harness_id"] = "future-unknown-adapter"
        with self.assertRaises(RunnerError):
            normalize_run(record)

    def test_empty_aggregate_is_rejected(self) -> None:
        with self.assertRaises(RunnerError):
            aggregate_metrics([])

    def test_input_records_are_not_mutated(self) -> None:
        record = mini_run()
        previous = copy.deepcopy(record)
        normalize_run(record)
        self.assertEqual(record, previous)

    def test_private_completed_evidence_is_read_without_inference_or_mutation(self) -> None:
        if not (ROOT / STUDY).exists():
            self.skipTest("Private completed study is unavailable")
        study = load_json(ROOT / STUDY / "study.json")
        paths = [ROOT / STUDY / "study.json", ROOT / "reports/agentic/multi-format-transfer-smoke-v0.3.json"]
        paths.extend(ROOT / unit["run_dir"] / "run.json" for unit in study["units"])
        before = {path: sha256_file(path) for path in paths}
        with patch("local_llm_benchmark.ollama.OllamaClient", side_effect=AssertionError("inference forbidden")):
            report = build_metrics_report(ROOT, STUDY)
        self.assertIsNone(report["totals"]["model_requests"]["value"])
        self.assertEqual(report["totals"]["artifact_tool_calls"]["value"], 34)
        self.assertEqual(before, {path: sha256_file(path) for path in paths})
        self.assertNotIn(str(ROOT), str(report))

    def test_report_writer_does_not_overwrite_existing_outputs(self) -> None:
        if not (ROOT / STUDY).exists():
            self.skipTest("Private completed study is unavailable")
        with tempfile.TemporaryDirectory(dir=ROOT / "results") as temporary:
            output = Path(temporary).relative_to(ROOT)
            result = write_metrics_report(ROOT, STUDY, output)
            before = {path: sha256_file(Path(path)) for path in result["paths"]}
            with self.assertRaisesRegex(RunnerError, "overwrite"):
                write_metrics_report(ROOT, STUDY, output)
            self.assertEqual(before, {path: sha256_file(Path(path)) for path in result["paths"]})


if __name__ == "__main__":
    unittest.main()
