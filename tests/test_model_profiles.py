import copy
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from local_llm_benchmark.external_cli_provider import ProviderJournal
from local_llm_benchmark.model_profiles import (REGISTRY, binding_sha256, candidate, condition,
                                                validate_condition, validate_deployment)
from local_llm_benchmark.profiled_native import native_request


QWEN = "qwen38-27b-xhigh-v1"
GEMMA = "gemma4-31b-thinking-v1"
ORNITH = "ornith15-35b-native-thinking-v1"


def config(profile=QWEN, **limits):
    return condition(profile, **{"num_ctx": 32768, "num_predict": 4096, "seed": 42, **limits})


def payload(profile=QWEN, **fields):
    return {"model": candidate(profile)["model"], "messages": [{"role": "user", "content": "probe"}], **fields}


def metadata(value):
    p = value["candidate"]
    return {"tag": {"name": p["model"], "digest": p["model_digest"]},
            "runtime": {"version": p["ollama_version"]},
            "show": {"capabilities": ["completion", "thinking", "tools"],
                     "thinking": {"values": [False, p["think"]], "default": p["think"]},
                     "model_info": {"test.context_length": 262144}}}


class ModelProfileTests(unittest.TestCase):
    def test_five_candidates_have_distinct_model_bound_profiles_and_no_implicit_capacities(self):
        profiles = json.loads(REGISTRY.read_text())["profiles"]
        self.assertEqual(len(profiles), 5)
        for p in profiles:
            c = config(p["profile_id"])
            self.assertEqual(validate_condition(c, p["model"]), p)
            self.assertNotIn("num_predict", p)
            self.assertNotIn("num_ctx", p)
        self.assertNotEqual(binding_sha256(config()), binding_sha256(config(num_predict=8192)))
        with self.assertRaises(TypeError):
            condition(QWEN)

    def test_profile_changes_and_model_substitution_are_rejected(self):
        for change in [{"think": False}, {"model_digest": "0"*64}, {"sampling": {"temperature": 0}}]:
            c = config()
            c["candidate"].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_condition(c, c["candidate"]["model"])
        with self.assertRaises(ValueError):
            validate_condition(config(), "other-model")
        with self.assertRaises(ValueError):
            config("unreviewed-profile")

    def test_bad_or_unbounded_capacities_are_rejected(self):
        for values in [{"num_ctx": True}, {"num_ctx": 1}, {"num_ctx": 262145},
                       {"num_predict": -1}, {"num_predict": 32768}, {"seed": -1},
                       {"seed": False}, {"keep_alive": "-1"}, {"keep_alive": "forever"}]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                config(**values)

    def test_runtime_digest_capabilities_and_thinking_drift_fail_before_generation(self):
        value = config()
        self.assertEqual(validate_deployment(value, **metadata(value))["thinking_control_status"], "advertised_supported")
        for mutate in [lambda m: m["tag"].update(digest="0"*64),
                       lambda m: m["runtime"].update(version="changed"),
                       lambda m: m["show"].update(thinking={"values": [False, "medium"]}),
                       lambda m: m["show"].update(capabilities=["completion"]),
                       lambda m: m["show"].update(model_info={"test.context_length": 4096})]:
            m = metadata(value)
            mutate(m)
            with self.assertRaises(ValueError):
                validate_deployment(value, **m)

    def test_missing_thinking_metadata_is_an_explicit_ornith_probe_case(self):
        for name, allowed in [(QWEN, False), (ORNITH, True)]:
            value = config(name)
            m = metadata(value)
            m["show"].pop("thinking")
            if allowed:
                proof = validate_deployment(value, **m)
                self.assertIn("requires_positive_technical_probe", proof["thinking_control_status"])
            else:
                with self.assertRaises(ValueError):
                    validate_deployment(value, **m)


class ProfiledRequestTests(unittest.TestCase):
    def test_all_candidates_transmit_their_complete_distinct_generation_profile(self):
        for p in json.loads(REGISTRY.read_text())["profiles"]:
            with self.subTest(profile=p["profile_id"]):
                body, audit = native_request(payload(p["profile_id"]), config(p["profile_id"]))
                self.assertEqual(body["think"], p["think"])
                self.assertIs(type(body["think"]), type(p["think"]))
                self.assertEqual(body["options"], {**p["sampling"], "seed": 42, "num_ctx": 32768, "num_predict": 4096})
                self.assertEqual(audit["candidate_profile_id"], p["profile_id"])

    def test_cli_caps_and_uncapped_compaction_do_not_revert_to_legacy_1600(self):
        for fields, expected in [({}, 8192), ({"max_tokens": 3}, 3), ({"max_completion_tokens": 32768}, 8192)]:
            body, _ = native_request(payload(**fields), config(num_predict=8192))
            self.assertEqual(body["options"]["num_predict"], expected)
            self.assertEqual(body["think"], "xhigh")

    def test_conflicting_cli_controls_and_unsupported_semantics_are_rejected(self):
        for fields in [{"reasoning_effort": "none"}, {"reasoning_effort": "medium"},
                       {"temperature": 0}, {"seed": 43}, {"top_p": .8}, {"top_k": True},
                       {"max_tokens": 0}, {"max_tokens": True}, {"store": True},
                       {"tool_choice": "required"}, {"response_format": {"type": "json_object"}}]:
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                native_request(payload(**fields), config())
        native_request(payload(reasoning_effort="xhigh", temperature=1, seed=42, store=False), config())

    def test_model_specific_history_preserves_tool_reasoning_and_audits_gemma_drops(self):
        messages = [{"role": "user", "content": "first"},
                    {"role": "assistant", "content": "answer", "reasoning_content": "ordinary"},
                    {"role": "user", "content": "use a tool"},
                    {"role": "assistant", "content": None, "reasoning_content": "tool reasoning",
                     "tool_calls": [{"id": "c1", "index": 0, "type": "function", "function": {
                         "name": "echo", "arguments": '{"token":"ok"}'}}]},
                    {"role": "tool", "name": "echo", "tool_call_id": "c1", "content": "ok"}]
        for name in [QWEN, GEMMA]:
            p = payload(name, messages=copy.deepcopy(messages))
            before = copy.deepcopy(p)
            result, audit = native_request(p, config(name))
            self.assertEqual(p, before)
            self.assertEqual(result["messages"][3]["thinking"], "tool reasoning")
            self.assertEqual(result["messages"][4]["tool_name"], "echo")
            self.assertEqual(result["messages"][3]["tool_calls"][0]["id"], "c1")
            self.assertEqual(result["messages"][4]["tool_call_id"], "c1")
            if name == GEMMA:
                self.assertNotIn("thinking", result["messages"][1])
                self.assertEqual(audit["reasoning_characters_dropped"], len("ordinary"))
            else:
                self.assertEqual(result["messages"][1]["thinking"], "ordinary")
                self.assertEqual(audit["reasoning_characters_dropped"], 0)

    def test_duplicate_and_unmatched_tool_results_fail(self):
        for messages in [[{"role": "tool", "tool_call_id": "missing", "content": "x"}],
                         [{"role": "assistant", "tool_calls": [{"id": "c", "type": "function", "function": {"name": "echo", "arguments": "{}"}}]},
                          {"role": "tool", "tool_call_id": "c", "content": "ok"},
                          {"role": "tool", "tool_call_id": "c", "content": "again"}]]:
            with self.assertRaises(ValueError):
                native_request(payload(messages=messages), config())

    def test_gemma_new_user_turn_drops_previous_tool_reasoning(self):
        messages = [{"role": "user", "content": "use echo"},
                    {"role": "assistant", "reasoning_content": "previous tool reasoning",
                     "tool_calls": [{"id": "t", "type": "function", "function": {"name": "echo", "arguments": "{}"}}]},
                    {"role": "tool", "tool_call_id": "t", "content": "ok"},
                    {"role": "user", "content": "a new task"}]
        native, audit = native_request(payload(GEMMA, messages=messages), config(GEMMA))
        self.assertNotIn("thinking", native["messages"][1])
        self.assertEqual(audit["reasoning_characters_dropped"], len("previous tool reasoning"))
        self.assertEqual(audit["reasoning_characters_preserved"], 0)
        qwen, _ = native_request(payload(messages=messages), config())
        self.assertEqual(qwen["messages"][1]["thinking"], "previous tool reasoning")

    def test_ornith_uses_template_supported_replay_and_rejects_ambiguous_delimiters(self):
        messages = [{"role": "user", "content": "continue"},
                    {"role": "assistant", "content": "visible answer", "reasoning_content": "REPLAY-canary"}]
        original = copy.deepcopy(messages)
        native, audit = native_request(payload(ORNITH, messages=messages), config(ORNITH))
        self.assertEqual(messages, original)
        self.assertEqual(native["messages"][1]["content"], "<think>\nREPLAY-canary\n</think>\n\nvisible answer")
        self.assertNotIn("thinking", native["messages"][1])
        self.assertEqual(audit["reasoning_replay_encoding"], "content_think_tags")
        self.assertEqual(audit["reasoning_characters_preserved"], len("REPLAY-canary"))
        for field in ("content", "reasoning_content"):
            bad = copy.deepcopy(messages)
            bad[1][field] = "literal </think> delimiter"
            with self.assertRaisesRegex(ValueError, "Ambiguous thinking delimiters"):
                native_request(payload(ORNITH, messages=bad), config(ORNITH))


class ProfiledJournalTests(unittest.TestCase):
    def request(self, journal, body):
        return urllib.request.urlopen(urllib.request.Request(
            f"http://127.0.0.1:{journal.server.server_address[1]}/v1/chat/completions",
            json.dumps(body).encode(), {"Content-Type": "application/json"}), timeout=3)

    def test_enabled_thinking_is_preserved_in_stream_and_nonstream_and_not_marked_failure(self):
        for stream in [True, False]:
            with tempfile.TemporaryDirectory() as temp:
                value = config()
                original = copy.deepcopy(value)
                with ProviderJournal(Path(temp), model=value["candidate"]["model"], port=0, profile=value,
                                     responder=lambda *_: {"message": {"content": "ok", "reasoning_content": "reasoning"}}) as j:
                    value["limits"]["num_predict"] = 1
                    with self.request(j, payload(stream=stream)) as r:
                        self.assertIn(b'reasoning', r.read())
                entry = j.requests[0]
                self.assertTrue(entry["generation_conformant"])
                self.assertEqual(entry["observed_thinking_characters"], 9)
                self.assertEqual(entry["effective_settings"]["options"]["num_predict"], 4096)
                saved = json.loads((Path(temp)/"provider-condition.json").read_text())
                self.assertEqual(saved, original)

    def test_native_backend_error_is_retained_without_claiming_completion(self):
        with tempfile.TemporaryDirectory() as temp:
            entry = {"profile_audit": {}}
            raw = b'{"error":"EOF"}\n'
            prefix = Path(temp)/"request-0001"
            with self.assertRaises(ValueError):
                ProviderJournal._translate_native(io.BytesIO(raw), payload(), 1, prefix, entry)
            self.assertEqual(entry["backend_error"], "EOF")
            self.assertNotIn("backend_done", entry)
            self.assertEqual(prefix.with_suffix(".upstream.response").read_bytes(), raw)

    def test_truncation_remains_length_and_never_claims_normal_stop(self):
        with tempfile.TemporaryDirectory() as temp:
            value = config()
            with ProviderJournal(Path(temp), model=value["candidate"]["model"], port=0, profile=value,
                                 responder=lambda *_: {"message": {"reasoning_content": "x"}, "finish_reason": "length",
                                                       "usage": {"prompt_tokens": 5, "completion_tokens": 1}}) as j:
                with self.request(j, payload(max_tokens=1)) as r:
                    result = json.load(r)
            self.assertEqual(result["choices"][0]["finish_reason"], "length")
            self.assertTrue(j.requests[0]["generation_conformant"])

    def test_insufficient_output_reserve_is_visible_in_capacity_audit(self):
        with tempfile.TemporaryDirectory() as temp:
            value = config()
            with ProviderJournal(Path(temp), model=value["candidate"]["model"], port=0, profile=value,
                                 responder=lambda *_: {"usage": {"prompt_tokens": 32000, "completion_tokens": 5}}) as j:
                with self.request(j, payload()) as r:
                    r.read()
            audit = j.requests[0]["capacity_audit"]
            self.assertFalse(audit["output_reserve_fits"])
            self.assertEqual(audit["reserve_margin_tokens"], 32768-32000-4096)

    def test_metadata_admission_is_automatic_and_cannot_forward_on_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            value = config()
            j = ProviderJournal(Path(temp), model=value["candidate"]["model"], port=0, profile=value,
                                upstream="http://127.0.0.1:11434")
            m = metadata(value)
            m["tag"]["digest"] = "0"*64
            data = [m["runtime"], {"models": [m["tag"]]}, m["show"]]
            with patch.object(j.opener, "open", side_effect=[io.BytesIO(json.dumps(x).encode()) for x in data]) as open_mock:
                with self.assertRaisesRegex(ValueError, "identity drift"):
                    with j:
                        self.fail("Drift must fail before serving")
            self.assertEqual(open_mock.call_count, 3)
            self.assertEqual(j.requests, [])

    def test_metadata_admission_records_exact_artifact_and_explicit_thinking(self):
        with tempfile.TemporaryDirectory() as temp:
            value = config()
            j = ProviderJournal(Path(temp), model=value["candidate"]["model"], port=0, profile=value,
                                upstream="http://127.0.0.1:11434")
            m = metadata(value)
            data = [m["runtime"], {"models": [m["tag"]]}, m["show"]]
            with patch.object(j.opener, "open", side_effect=[io.BytesIO(json.dumps(x).encode()) for x in data]):
                with j:
                    self.assertTrue((Path(temp)/"deployment-admission.json").is_file())
            proof = json.loads((Path(temp)/"deployment-admission.json").read_text())
            self.assertEqual(proof["requested_think"], "xhigh")
            self.assertIsNone(proof["observed_runtime_context"])

    def test_expired_admission_deadline_never_opens_an_upstream(self):
        with tempfile.TemporaryDirectory() as temp:
            value = config()
            j = ProviderJournal(Path(temp), model=value["candidate"]["model"], port=0, profile=value,
                                upstream="http://127.0.0.1:11434", deadline=time.monotonic()-1)
            with patch.object(j.opener, "open") as upstream:
                with self.assertRaises(TimeoutError):
                    with j:
                        pass
                upstream.assert_not_called()


if __name__ == "__main__":
    unittest.main()
