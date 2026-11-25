import hashlib
import http.client
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from local_llm_benchmark.external_cli import execute, finalize, prepare
from local_llm_benchmark.external_cli_provider import ProviderJournal
from local_llm_benchmark.external_cli_qualification import public_test_ran
from local_llm_benchmark.runner import RunnerError, sha256_file, write_json


ROOT = Path(__file__).resolve().parents[1]
CASE = Path("tasks/coding/dev/async-cache-coalescing/case.json")
FAKE_RUNTIME = {"base_prefix": sys.base_prefix, "python_binary": str(Path(sys.executable).resolve())}


class ExternalLifecycleTests(unittest.TestCase):
    def setUp(self):
        (ROOT/"results/agentic-dry-runs").mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/"results/agentic-dry-runs")
        self.addCleanup(self.temp.cleanup)
        self.identity = patch("local_llm_benchmark.external_cli.runtime_identity", return_value=FAKE_RUNTIME)
        self.identity.start()
        self.addCleanup(self.identity.stop)
        self.platform = patch("local_llm_benchmark.external_cli_sandbox.platform.system", return_value="Darwin")
        self.machine = patch("local_llm_benchmark.external_cli_sandbox.platform.machine", return_value="arm64")
        self.platform.start(); self.machine.start()
        self.addCleanup(self.platform.stop); self.addCleanup(self.machine.stop)
        self.sandbox = patch("local_llm_benchmark.external_cli_sandbox.SEATBELT_EXECUTABLE", Path(sys.executable))
        self.sandbox.start(); self.addCleanup(self.sandbox.stop)
        self.resolver = patch("local_llm_benchmark.macos_sandbox_v03.resolve_public_test_executable",
                              return_value=Path(sys.executable).resolve())
        self.resolver.start(); self.addCleanup(self.resolver.stop)
        self.search = patch("local_llm_benchmark.external_cli.shutil.which", return_value=sys.executable)
        self.search.start(); self.addCleanup(self.search.stop)

    def prepared(self, name="mirror"):
        return Path(prepare(ROOT, harness=name, model="exact-local-model", case_path=CASE,
                            results_dir=Path(self.temp.name))["run_dir"])

    def acceptance(self, run, passed=True):
        value = {"passed": passed, "profile_sha256": sha256_file(run/"sandbox.sb"),
                 "invocation_sha256": sha256_file(run/"invocation.json")}
        write_json(run/"sandbox-acceptance.json", value)
        record = json.loads((run/"run.json").read_text())
        record["sandbox_acceptance_sha256"] = sha256_file(run/"sandbox-acceptance.json")
        write_json(run/"run.json", record)

    def test_preparation_isolates_account_settings_and_keeps_hidden_tests_out(self):
        with patch.dict("os.environ", {"MISTRAL_API_KEY": "private-canary", "OPENAI_API_KEY": "private-canary"}):
            for name in ["mirror", "vibe"]:
                run = self.prepared(name)
                invocation = json.loads((run/"invocation.json").read_text())
                record = json.loads((run/"run.json").read_text())
                self.assertNotIn("private-canary", json.dumps(invocation))
                self.assertEqual(record["model_requests"], 0)
                self.assertFalse(record["hidden_verification_executed"])
                self.assertEqual(record["state"], "prepared")
                self.assertFalse(list((run/"workspace").rglob("*hidden*")))
                self.assertEqual(invocation["environment"]["VIBE_TEST_DISABLE_KEYRING"], "1")
                self.assertIn(str(run/"agent-state"), invocation["environment"]["HOME"])
                self.assertNotIn("--max-turns", invocation["argv"])
                self.assertNotIn("--max-iterations", invocation["argv"])
                policy = json.loads((run/"policy.json").read_text())
                import shlex
                executable = shlex.split(policy["public_test_command"])[0]
                self.assertTrue(Path(executable).is_absolute())
                self.assertIn(executable, invocation["allowed_processes"])

    def test_unknown_case_and_unsafe_model_fail_before_runtime_inspection(self):
        with patch("local_llm_benchmark.external_cli.runtime_identity") as runtime:
            for kwargs in [{"case_path": Path("tasks/core-suite-v0.1.json"), "model": "m"},
                           {"case_path": CASE, "model": "m\ninjected"}]:
                with self.assertRaises(RunnerError):
                    prepare(ROOT, harness="mirror", results_dir=Path(self.temp.name), **kwargs)
            runtime.assert_not_called()

    def test_versioned_workspace_hint_and_output_limit_preserve_the_original_condition(self):
        for name in ["mirror", "vibe"]:
            for condition, output_limit in [("v0.1", "3000"), ("v0.2", "8192"), ("v0.3", "1600")]:
                with self.subTest(harness=name, condition=condition):
                    run = Path(prepare(ROOT, harness=name, model="exact-local-model", case_path=CASE,
                                       results_dir=Path(self.temp.name), condition=condition)["run_dir"])
                    invocation = json.loads((run/"invocation.json").read_text())
                    record = json.loads((run/"run.json").read_text())
                    prompt = invocation["stdin"] if name == "mirror" else invocation["argv"][-1]
                    self.assertEqual("Working directory: " + str(run/"workspace") in prompt,
                                     condition != "v0.1")
                    self.assertEqual(invocation["timeout_seconds"], 900)
                    self.assertEqual(record["harness_id"], f"{name}-cli-{condition}")
                    self.assertIn(record["protocol_path"], record["source_hashes"])
                    if condition == "v0.3":
                        scratch = json.loads((run/"policy.json").read_text())["scratch_directory"]
                        self.assertIn(scratch, prompt)
                        self.assertTrue(Path(scratch).is_dir())
                        self.assertIs(invocation["provider_profile"]["think"], False)
                    if name == "mirror":
                        argv = invocation["argv"]
                        self.assertEqual(argv[argv.index("--max-tokens") + 1], output_limit)

    def test_unknown_condition_fails_before_runtime_inspection(self):
        with patch("local_llm_benchmark.external_cli.runtime_identity") as runtime:
            with self.assertRaisesRegex(RunnerError, "Unknown external CLI condition"):
                prepare(ROOT, harness="mirror", model="m", case_path=CASE, condition="unreviewed")
            runtime.assert_not_called()

    def test_workspace_tamper_cannot_start_a_provider(self):
        run = self.prepared()
        (run/"workspace/src/async-cache.mjs").write_text("altered")
        with patch("local_llm_benchmark.external_cli.ProviderJournal") as provider:
            with self.assertRaisesRegex(RunnerError, "Workspace changed"):
                execute(ROOT, run, responder=lambda *_: {})
            provider.assert_not_called()

    def test_failed_os_acceptance_cannot_start_a_provider(self):
        run = self.prepared()
        self.acceptance(run, passed=False)
        with patch("local_llm_benchmark.external_cli.ProviderJournal") as provider:
            with self.assertRaisesRegex(RunnerError, "sandbox acceptance"):
                execute(ROOT, run, responder=lambda *_: {})
            provider.assert_not_called()

    def test_missing_live_authorization_is_not_an_implicit_live_run(self):
        run = self.prepared()
        self.acceptance(run)
        with patch("local_llm_benchmark.external_cli.ProviderJournal") as provider:
            with self.assertRaisesRegex(RunnerError, "explicit live authorization"):
                execute(ROOT, run)
            provider.assert_not_called()

    def test_running_or_complete_attempt_cannot_restart(self):
        run = self.prepared()
        record = json.loads((run/"run.json").read_text())
        for state in ["running", "execution_capture_failed", "execution_complete_verification_pending", "complete"]:
            record["state"] = state
            write_json(run/"run.json", record)
            with self.assertRaisesRegex(RunnerError, "consumed"):
                execute(ROOT, run, responder=lambda *_: {})

    def test_development_budget_is_bound_before_runtime_or_execution(self):
        with patch("local_llm_benchmark.external_cli.runtime_identity") as runtime:
            for seconds in [0, -1, True, 901]:
                with self.assertRaises(RunnerError):
                    prepare(ROOT, harness="mirror", model="m", case_path=CASE,
                            results_dir=Path(self.temp.name), wall_seconds=seconds)
            runtime.assert_not_called()

    def test_changed_settings_cannot_reuse_an_acceptance(self):
        run = self.prepared()
        self.acceptance(run)
        invocation = json.loads((run/"invocation.json").read_text())
        invocation["gateway_port"] += 5
        write_json(run/"invocation.json", invocation)
        with self.assertRaisesRegex(RunnerError, "Prepared artifact changed"):
            execute(ROOT, run, responder=lambda *_: {})

    def test_hidden_verification_refuses_unfrozen_execution_artifacts(self):
        run = self.prepared()
        record = json.loads((run/"run.json").read_text())
        record.update(state="execution_complete_verification_pending", frozen_workspace={})
        write_json(run/"run.json", record)
        with patch("local_llm_benchmark.external_cli.verify_coding_workspace") as verifier:
            with self.assertRaisesRegex(RunnerError, "changed before hidden verification"):
                finalize(ROOT, run)
            verifier.assert_not_called()


class ProviderJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def request(self, journal, body):
        port = journal.server.server_address[1]
        return urllib.request.urlopen(urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/chat/completions", json.dumps(body).encode(),
            {"Content-Type": "application/json"}), timeout=3)

    def test_wrong_model_is_rejected_and_recorded_without_callback(self):
        with patch("builtins.print"):
            calls = []
            with ProviderJournal(Path(self.temp.name), model="bound", port=0,
                                 responder=lambda *args: calls.append(args)) as journal:
                with self.assertRaises(urllib.error.HTTPError) as failure:
                    self.request(journal, {"model": "other", "messages": []})
                self.assertEqual(failure.exception.code, 403)
                failure.exception.close()
            self.assertFalse(calls)
            self.assertEqual(journal.requests[0]["status"], "rejected_model_or_endpoint")

    def test_stream_and_nonstream_preserve_wire_settings_and_usage(self):
        for stream in [False, True]:
            directory = Path(self.temp.name)/str(stream)
            body = {"model": "bound", "messages": [], "stream": stream, "temperature": 0.37, "seed": 19}
            with ProviderJournal(directory, model="bound", port=0, responder=lambda *_: {}) as journal:
                with self.request(journal, body) as response:
                    raw = response.read()
            recorded = (directory/"request-0001.json").read_bytes()
            self.assertEqual(json.loads(recorded), body)
            self.assertEqual(journal.requests[0]["request_sha256"], hashlib.sha256(recorded).hexdigest())
            self.assertEqual(journal.requests[0]["settings"]["temperature"], 0.37)
            self.assertEqual(journal.requests[0]["usage"]["total_tokens"], 15)
            self.assertIn(b"offline transport qualified", raw)
            self.assertEqual(journal.requests[0]["status"], "complete")

    def test_gateway_cannot_forward_to_a_cloud_or_arbitrary_local_service(self):
        for url in ["https://api.mistral.ai", "http://127.0.0.1:12345"]:
            with self.assertRaises(ValueError):
                ProviderJournal(Path(self.temp.name), model="m", port=0, upstream=url)

    def test_upstream_http_error_body_is_preserved_without_contacting_ollama(self):
        body = b'{"error":{"message":"unsupported request option"}}'
        with ProviderJournal(Path(self.temp.name), model="bound", port=0,
                             upstream="http://127.0.0.1:11434") as journal:
            error = urllib.error.HTTPError("http://127.0.0.1:11434/v1/chat/completions",
                                           400, "Bad Request", {}, io.BytesIO(body))
            with patch.object(journal.opener, "open", side_effect=error):
                with self.assertRaises(urllib.error.HTTPError) as failure:
                    self.request(journal, {"model": "bound", "messages": []})
                self.assertEqual(failure.exception.code, 400)
                self.assertEqual(failure.exception.read(), body)
                failure.exception.close()
        self.assertEqual((Path(self.temp.name)/"request-0001.response").read_bytes(), body)
        self.assertEqual(journal.requests[0]["status"], "upstream_http_error")

    def test_interrupted_chunked_stream_preserves_partial_bytes_and_records_failure(self):
        partial = b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'

        class InterruptedResponse(io.BytesIO):
            status = 200
            headers = {"Content-Type": "text/event-stream"}

            def read1(self, size=-1):
                data = super().read1(size)
                if data:
                    return data
                raise http.client.IncompleteRead(b"")

        with ProviderJournal(Path(self.temp.name), model="bound", port=0,
                             upstream="http://127.0.0.1:11434") as journal:
            with patch.object(journal.opener, "open", return_value=InterruptedResponse(partial)), \
                    patch.object(journal.server, "handle_error") as unhandled:
                with self.request(journal, {"model": "bound", "messages": [], "stream": True}) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.read(), partial)
            unhandled.assert_not_called()
        self.assertEqual((Path(self.temp.name)/"request-0001.response").read_bytes(), partial)
        self.assertEqual(journal.requests[0]["status"], "transport_error")
        self.assertEqual(journal.requests[0]["error"], "IncompleteRead")
        self.assertIn("finished_at", journal.requests[0])
        self.assertNotIn("usage", journal.requests[0])
        self.assertFalse(journal.connections)

    def test_expired_parent_budget_never_starts_an_upstream_request(self):
        with ProviderJournal(Path(self.temp.name), model="bound", port=0,
                             upstream="http://127.0.0.1:11434", deadline=time.monotonic()-1) as journal:
            with patch.object(journal.opener, "open") as upstream:
                with self.assertRaises(urllib.error.HTTPError) as failure:
                    self.request(journal, {"model":"bound", "messages":[]})
                failure.exception.close()
                upstream.assert_not_called()
        self.assertFalse(journal.requests[0].get("forwarded_to_ollama", False))
        self.assertEqual(journal.requests[0]["error"], "TimeoutError")

    def test_wait_for_response_headers_inherits_remaining_parent_budget(self):
        with ProviderJournal(Path(self.temp.name), model="bound", port=0,
                             upstream="http://127.0.0.1:11434", timeout=300,
                             deadline=time.monotonic()+2) as journal:
            error=urllib.error.HTTPError("http://127.0.0.1:11434/v1/chat/completions",400,
                                         "stub",{},io.BytesIO(b'{}'))
            with patch.object(journal.opener, "open", side_effect=error) as upstream:
                with self.assertRaises(urllib.error.HTTPError) as failure:
                    self.request(journal, {"model":"bound", "messages":[]})
                failure.exception.close()
                self.assertGreater(upstream.call_args.kwargs["timeout"],0)
                self.assertLessEqual(upstream.call_args.kwargs["timeout"],2)


class QualificationWitnessTests(unittest.TestCase):
    def test_shell_error_cannot_count_as_executed_public_tests(self):
        for failure in ["Exit code: 127\n/bin/bash: node: command not found",
                        "edit failed: Operation not permitted",
                        "Ran 1 test\nFAILED\nModuleNotFoundError: paged_sync"]:
            self.assertFalse(public_test_ran(failure, CASE))

    def test_each_supported_language_requires_its_suite_output(self):
        self.assertTrue(public_test_ran("Subtest: cached loader\n# tests 5\n# fail 2", CASE))
        self.assertTrue(public_test_ran("not ok - migration\n0/5 public checks passed", Path("php-payment/case.json")))
        self.assertTrue(public_test_ran("CollectRecordsTest.test_cycle\nRan 8 tests\nFAILED", Path("pagination/case.json")))


if __name__ == "__main__":
    unittest.main()
