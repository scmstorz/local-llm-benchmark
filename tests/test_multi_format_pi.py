from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_llm_benchmark.macos_sandbox import SeatbeltCommandResult
from local_llm_benchmark.macos_sandbox_multi_format import validate_pi_multi_format_seatbelt
from local_llm_benchmark.multi_format_pi import (
    PiMultiFormatPrepareConfig,
    execute_pi_multi_format_run,
    finalize_pi_multi_format_run,
    load_pi_multi_format_harness,
    prepare_pi_multi_format_run,
)
from local_llm_benchmark.runner import load_json, sha256_file


REPO_ROOT = Path(__file__).resolve().parents[1]


class PiMultiFormatHarnessTests(unittest.TestCase):
    def _prepare(self, parent: Path) -> Path:
        result = prepare_pi_multi_format_run(
            REPO_ROOT,
            PiMultiFormatPrepareConfig(model="not-contacted:test", results_dir=parent),
        )
        self.assertEqual(result["inference_requests_made"], 0)
        return Path(result["run_dir"])

    def test_definition_pins_pi_and_four_custom_tools(self) -> None:
        loaded = load_pi_multi_format_harness(REPO_ROOT)
        self.assertEqual(loaded["harness"]["package"]["version"], "0.84.4")
        self.assertEqual(loaded["harness"]["integration"]["tools"], ["list_artifacts", "read_docx", "read_pdf", "read_xlsx"])

    def test_prepare_copies_exact_backend_and_builds_read_only_invocation(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._prepare(Path(temporary))
            record = load_json(run_dir / "run.json")
            policy = load_json(run_dir / "pi-policy.json")
            invocation = load_json(run_dir / "pi-invocation.json")
            self.assertEqual(policy["backend_sha256"], sha256_file(REPO_ROOT / "local_llm_benchmark/multi_format_artifacts.py"))
            self.assertEqual(policy["allowed_tools"], ["list_artifacts", "read_docx", "read_pdf", "read_xlsx"])
            self.assertEqual(record["execution_boundary"]["inference_requests_made"], 0)
            tools_index = invocation["argv"].index("--tools")
            self.assertEqual(invocation["argv"][tools_index + 1], "list_artifacts,read_docx,read_pdf,read_xlsx")
            self.assertIn("--no-builtin-tools", invocation["argv"])
            self.assertFalse(record["execution_boundary"]["candidate_workspace_writable"])
            profile = (run_dir / "pi-multi-format-sandbox.sb").read_text(encoding="utf-8")
            self.assertIn("(deny default)", profile)
            self.assertEqual(profile.count("(allow network-outbound"), 1)
            self.assertIn('localhost:11434', profile)
            self.assertNotIn("network-inbound", profile)
            self.assertEqual(
                load_json(run_dir / "pi-multi-format-sandbox.json")["allowed_processes"],
                [policy_path for policy_path in (
                    load_json(run_dir / "pi-multi-format-sandbox.json")["node_binary"],
                    policy["python_path"],
                    policy["pdftotext_path"],
                )],
            )

    def test_mocked_seatbelt_acceptance_covers_hidden_and_all_formats(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._prepare(Path(temporary))
            with (
                patch("local_llm_benchmark.macos_sandbox_multi_format.run_seatbelt_command", return_value=SeatbeltCommandResult(0, "", "")),
                patch("local_llm_benchmark.macos_sandbox_multi_format._temporary_loopback_probe", return_value=(None, None)),
            ):
                result = validate_pi_multi_format_seatbelt(run_dir)
            self.assertTrue(result["passed"])
            self.assertEqual(len(result["checks"]), 11)
            ids = {item["check_id"] for item in result["checks"]}
            self.assertIn("canonical_extraction_read_denied", ids)
            self.assertIn("shared_backend_all_formats", ids)
            self.assertEqual(result["inference_requests_made"], 0)

    def test_mocked_pi_execution_and_hidden_finalization(self) -> None:
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "results") as temporary:
            run_dir = self._prepare(Path(temporary))
            with (
                patch("local_llm_benchmark.macos_sandbox_multi_format.run_seatbelt_command", return_value=SeatbeltCommandResult(0, "", "")),
                patch("local_llm_benchmark.macos_sandbox_multi_format._temporary_loopback_probe", return_value=(None, None)),
            ):
                validate_pi_multi_format_seatbelt(run_dir)
            case = load_json(REPO_ROOT / "tasks/agentic/multi-format-document-analysis/rollout-readiness-reconciliation/case-v0.1.json")
            report = load_json(REPO_ROOT / case["verification"]["reference_report_path"])
            audit_path = run_dir / "pi-policy-audit.jsonl"

            class FakeProcess:
                pid = 12345

                def __init__(self, *args, **kwargs):
                    kwargs["stdout"].write(json.dumps({"type": "agent_end", "messages": [{"role": "assistant", "content": [{"type": "text", "text": json.dumps(report)}], "stopReason": "stop"}], "willRetry": False}) + "\n")
                    audit_path.write_text(json.dumps({"kind": "agent_end", "counts": {"agent_turns": 3, "tool_calls": 10, "failed_tool_calls": 0, "list_calls": 1, "docx_reads": 3, "pdf_reads": 4, "xlsx_reads": 2, "repeated_queries": 0, "input_tokens": 100, "output_tokens": 50}, "query_counts": {"q": 1}}) + "\n", encoding="utf-8")

                def wait(self, timeout=None):
                    return 0

            original_popen = subprocess.Popen

            def selective_popen(*args, **kwargs):
                if hasattr(kwargs.get("stdout"), "write"):
                    return FakeProcess(*args, **kwargs)
                return original_popen(*args, **kwargs)

            with patch("local_llm_benchmark.multi_format_pi.subprocess.Popen", side_effect=selective_popen):
                executed = execute_pi_multi_format_run(REPO_ROOT, run_dir)
            final = finalize_pi_multi_format_run(REPO_ROOT, run_dir)
            self.assertTrue(executed["runtime_success"])
            self.assertTrue(final["semantic_verified_success"])
            self.assertTrue(final["strict_transport_compliance"])
            self.assertEqual(final["verification"]["essential_pass_count"], 11)


if __name__ == "__main__":
    unittest.main()
