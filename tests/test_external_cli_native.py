import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.request

from local_llm_benchmark.external_cli_native import PROFILE, NativeResponse, native_request
from local_llm_benchmark.external_cli_provider import ProviderJournal


class NativeBridgeTests(unittest.TestCase):
    def payload(self, **kwargs):
        return {"model": "bound", "messages": [{"role": "user", "content": "probe"}], **kwargs}

    def test_profile_covers_native_and_uncapped_compaction_requests(self):
        for extra, cap in [({}, 1600), ({"max_tokens": 8192}, 1600),
                           ({"max_tokens": 73}, 73), ({"max_completion_tokens": 19}, 19)]:
            result = native_request(self.payload(**extra), PROFILE)
            self.assertIs(result["think"], False)
            self.assertEqual(result["options"], {"temperature": 0, "seed": 42, "num_ctx": 16384, "num_predict": cap})
            self.assertEqual(result["keep_alive"], "5m")

    def test_parallel_tool_arguments_and_results_keep_names_and_order(self):
        body = self.payload()
        body["messages"] += [{"role": "assistant", "content": None, "tool_calls": [
            {"id": str(i), "type": "function", "function": {"name": name, "arguments": '{"x":1}'}}
            for i, name in enumerate(["read", "bash"])]}]
        body["messages"] += [{"role": "tool", "tool_call_id": str(i), "content": text}
                             for i, text in enumerate(["source", "test result"])]
        original = copy.deepcopy(body)
        messages = native_request(body, PROFILE)["messages"]
        self.assertEqual(messages[-2:],[{"role": "tool", "tool_name": "read", "content": "source"},
                                         {"role": "tool", "tool_name": "bash", "content": "test result"}])
        self.assertEqual(messages[1]["tool_calls"][0]["function"]["arguments"], {"x": 1})
        self.assertEqual(body, original)

    def test_unsupported_or_conflicting_semantics_are_rejected(self):
        invalid = [{"temperature": .8}, {"seed": 3}, {"reasoning_effort": "medium"},
                   {"tool_choice": "required"}, {"max_tokens": -1}, {"max_tokens": True},
                   {"response_format": {"type": "json_object"}},
                   {"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": "x"}]}]},
                   {"messages": [{"role": "tool", "tool_call_id": "unknown", "content": "x"}]}]
        for fields in invalid:
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                native_request(self.payload(**fields), PROFILE)

    def test_streamed_tools_text_and_unexpected_thinking_are_preserved(self):
        c = NativeResponse(self.payload(stream=True), 7)
        first = c.feed({"model": "bound", "message": {"content": "answer", "thinking": "unexpected"}})
        self.assertIn(b'"content": "answer"', first)
        self.assertIn(b'"reasoning_content": "unexpected"', first)
        second = c.feed({"model": "bound", "message": {"tool_calls": [{"function": {
            "name": "bash", "arguments": {"command": "pwd"}}}]}, "done": True,
            "done_reason": "stop", "prompt_eval_count": 4, "eval_count": 8})
        self.assertIn(b'native-7-0', second)
        self.assertIn(b'"finish_reason": "tool_calls"', second)
        self.assertTrue(second.endswith(b'data: [DONE]\n\n'))
        self.assertEqual(c.thinking_characters, 10)
        self.assertEqual(c.usage["total_tokens"], 12)
        self.assertEqual(c.finish(), b"")

    def test_length_is_not_reported_as_successful_stop(self):
        c = NativeResponse(self.payload(), 1)
        c.feed({"model": "bound", "message": {"content": "truncated"}, "done": True,
                "done_reason": "length", "prompt_eval_count": 1, "eval_count": 1600})
        self.assertEqual(json.loads(c.finish())["choices"][0]["finish_reason"], "length")

    def test_missing_usage_or_done_or_wrong_model_cannot_look_complete(self):
        for item in [{"model": "other", "message": {}},
                     {"model": "bound", "message": {}, "done": True, "done_reason": "stop"},
                     {"model": "bound", "error": "backend failed"}]:
            with self.subTest(item=item), self.assertRaises(ValueError):
                NativeResponse(self.payload(), 1).feed(item)
        with self.assertRaisesRegex(ValueError, "without completion"):
            NativeResponse(self.payload(), 1).finish()


class NativeJournalTests(unittest.TestCase):
    def request(self, journal, body):
        return urllib.request.urlopen(urllib.request.Request(
            f"http://127.0.0.1:{journal.server.server_address[1]}/v1/chat/completions",
            json.dumps(body).encode(), {"Content-Type": "application/json"}), timeout=5)

    def test_both_wire_sides_and_effective_profile_are_recorded(self):
        for stream in [True, False]:
            with tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                body = {"model": "bound", "messages": [], "stream": stream}
                with ProviderJournal(directory, model="bound", port=0, profile=PROFILE,
                                     responder=lambda *_: {"message": {"content": "ok"}}) as journal:
                    with self.request(journal, body) as r:
                        self.assertIn(b'ok', r.read())
                self.assertEqual(json.loads((directory/"request-0001.json").read_text()), body)
                effective = json.loads((directory/"request-0001.upstream.json").read_text())
                self.assertEqual(effective["options"]["num_ctx"], 16384)
                self.assertTrue((directory/"request-0001.upstream.response").is_file())
                self.assertTrue(journal.requests[0]["generation_conformant"])

    def test_live_path_uses_native_endpoint_and_journals_unsuppressed_thinking(self):
        class Response(io.BytesIO):
            status = 200
            headers = {"Content-Type": "application/x-ndjson"}
        with tempfile.TemporaryDirectory() as temp:
            body = {"model": "bound", "messages": [], "stream": True}
            response = Response((json.dumps({"model": "bound", "message": {"thinking": "unexpected"},
                                "done": True, "done_reason": "stop", "prompt_eval_count": 2, "eval_count": 1})+'\n').encode())
            with ProviderJournal(Path(temp), model="bound", port=0, profile=PROFILE,
                                 upstream="http://127.0.0.1:11434") as journal:
                with patch.object(journal.opener, "open", return_value=response) as opener:
                    with self.request(journal, body) as r:
                        self.assertIn(b'unexpected', r.read())
                request = opener.call_args.args[0]
                self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/chat")
                self.assertIs(json.loads(request.data)["think"], False)
            self.assertFalse(journal.requests[0]["generation_conformant"])
            self.assertEqual(journal.requests[0]["status"], "complete")

    def test_truncated_native_stream_retains_partial_evidence_and_fails(self):
        class Response(io.BytesIO):
            status = 200
            headers = {}
        partial = b'{"model":"bound","message":{"content":"partial"}}\n'
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            with ProviderJournal(directory, model="bound", port=0, profile=PROFILE,
                                 upstream="http://127.0.0.1:11434") as journal:
                with patch.object(journal.opener, "open", return_value=Response(partial)):
                    with self.request(journal, {"model": "bound", "messages": [], "stream": True}) as r:
                        wire = r.read()
            self.assertIn(b'partial', wire)
            self.assertNotIn(b'[DONE]', wire)
            self.assertEqual((directory/"request-0001.upstream.response").read_bytes(), partial)
            self.assertEqual(journal.requests[0]["status"], "transport_error")

    def test_backend_output_over_effective_ceiling_fails_conformance(self):
        with tempfile.TemporaryDirectory() as temp:
            with ProviderJournal(Path(temp), model="bound", port=0, profile=PROFILE,
                                 responder=lambda *_: {"usage": {"prompt_tokens": 1, "completion_tokens": 9}}) as journal:
                with self.request(journal, {"model": "bound", "messages": [], "max_tokens": 8}) as r:
                    r.read()
            self.assertFalse(journal.requests[0]["generation_conformant"])
            self.assertEqual(journal.requests[0]["usage"]["completion_tokens"], 9)


if __name__ == "__main__":
    unittest.main()
