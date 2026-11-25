import os
import json
from pathlib import Path
import platform
import unittest

from local_llm_benchmark.external_cli_qualification import qualify, qualify_deadline
from local_llm_benchmark.runner import load_json


@unittest.skipUnless(os.environ.get("RUN_EXTERNAL_CLI_QUALIFICATION") == "1",
                     "Explicit local stub/Seatbelt qualification; no model inference")
class ExternalCLIQualificationTests(unittest.TestCase):
    def test_both_pinned_clis_on_the_three_existing_coding_cases(self):
        if platform.system() != "Darwin" or platform.machine() != "arm64":
            self.skipTest("Pinned macOS Apple Silicon runtimes required")
        root = Path(__file__).resolve().parents[1]
        protocol = load_json(root/"tasks/coding/track-b/external-cli-v0.1.json")
        for harness in ["mirror", "vibe"]:
            for case in protocol["task_paths"]:
                with self.subTest(harness=harness, case=case):
                    result = qualify(root, harness, Path(case))
                    self.assertTrue(result["passed"], result)
                    self.assertEqual(result["model_requests"], 0)
                    if harness == "mirror":
                        events = [json.loads(line) for line in
                                  (root/result["run_dir"]/"agent-state/events.jsonl").read_text().splitlines()]
                        chats = [e.get("agent_message", {}).get("chat", {}) for e in events]
                        self.assertTrue(any("assistant" in chat for chat in chats))
                        self.assertTrue(any("tool" in chat for chat in chats))

    def test_native_tool_process_groups_stop_at_the_parent_deadline(self):
        root = Path(__file__).resolve().parents[1]
        for harness in ["mirror", "vibe"]:
            with self.subTest(harness=harness):
                result = qualify_deadline(root, harness)
                self.assertTrue(result["passed"], result)

    def test_normal_budget_condition_on_the_existing_javascript_case(self):
        root = Path(__file__).resolve().parents[1]
        for harness in ["mirror", "vibe"]:
            with self.subTest(harness=harness):
                result = qualify(root, harness, Path("tasks/coding/dev/async-cache-coalescing/case.json"),
                                 condition="v0.2")
                self.assertTrue(result["passed"], result)
                self.assertEqual(result["model_requests"], 0)
                run = root/result["run_dir"]
                request = load_json(run/"provider-wire/request-0001.json")
                user_text = "\n".join(m.get("content", "") for m in request["messages"]
                                      if m["role"] == "user")
                self.assertIn("Working directory: " + str(run/"workspace"), user_text)
                if harness == "mirror":
                    self.assertEqual(request["max_tokens"], 8192)
                invocation = load_json(run/"invocation.json")
                self.assertEqual(invocation["timeout_seconds"], 900)

    def test_normal_budget_condition_still_cleans_up_at_the_parent_deadline(self):
        root = Path(__file__).resolve().parents[1]
        for harness in ["mirror", "vibe"]:
            with self.subTest(harness=harness):
                result = qualify_deadline(root, harness, condition="v0.2")
                self.assertTrue(result["passed"], result)

    def test_explicit_backend_condition_and_native_scratch_tools(self):
        root = Path(__file__).resolve().parents[1]
        for harness in ["mirror", "vibe"]:
            with self.subTest(harness=harness):
                result = qualify(root, harness, Path("tasks/coding/dev/async-cache-coalescing/case.json"),
                                 condition="v0.3")
                self.assertTrue(result["passed"], result)
                self.assertEqual(result["stub_provider_requests"], 10)
                self.assertEqual(result["model_requests"], 0)

    def test_explicit_backend_condition_stops_owned_children(self):
        root = Path(__file__).resolve().parents[1]
        for harness in ["mirror", "vibe"]:
            with self.subTest(harness=harness):
                self.assertTrue(qualify_deadline(root, harness, condition="v0.3")["passed"])


if __name__ == "__main__":
    unittest.main()
