import hashlib
import io
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from local_llm_benchmark import calibration_run as cr
from local_llm_benchmark.external_cli_native import NativeResponse
from local_llm_benchmark.model_profiles import condition


def event(**fields):
    return json.dumps({"model": "qwen3.8:27b-mlx", "message": {"role": "assistant", "content": ""}, **fields}).encode()+b"\n"


class CalibrationWatchdogTests(unittest.TestCase):
    def test_clean_worker_is_not_a_timeout(self):
        with tempfile.TemporaryDirectory() as temp:
            r = cr.bounded_process([sys.executable, "-c", "print('completed')"], Path(temp), 3)
            self.assertFalse(r["timed_out"])
            self.assertEqual(r["returncode"], 0)
            self.assertEqual((Path(temp)/"worker.stdout").read_text().strip(), "completed")

    def test_hard_deadline_cannot_be_extended_by_a_blocking_monitor(self):
        with tempfile.TemporaryDirectory() as temp:
            r = cr.bounded_process([sys.executable, "-c", "import time; time.sleep(60)"],
                                   Path(temp), 0.3, lambda: time.sleep(1))
            self.assertTrue(r["timed_out"])
            self.assertLess(r["deadline_signal_elapsed_seconds"], 0.8)
            self.assertTrue(r["cleanup_finished"])
            self.assertLess(r["elapsed_seconds"], 3)

    def test_trickling_worker_and_term_ignoring_child_are_killed_and_partial_bytes_survive(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            code = """import os,signal,subprocess,sys,time
from pathlib import Path
signal.signal(signal.SIGTERM,signal.SIG_IGN)
child=subprocess.Popen([sys.executable,'-c','import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)'])
Path(sys.argv[1]).write_text(str(child.pid))
while True:
 os.write(1,b'partial-stream\\n')
 time.sleep(.02)
"""
            r = cr.bounded_process([sys.executable, "-c", code, str(directory/"child.pid")], directory, 0.8)
            self.assertTrue(r["timed_out"])
            self.assertIn(b"partial-stream", (directory/"worker.stdout").read_bytes())
            child = int((directory/"child.pid").read_text())
            observed = subprocess.run(["ps", "-p", str(child), "-o", "stat="], capture_output=True, text=True)
            self.assertTrue(not observed.stdout.strip() or observed.stdout.strip().startswith("Z"))

    def test_monitor_failure_stops_only_the_owned_worker(self):
        with tempfile.TemporaryDirectory() as temp:
            def fail():
                raise ValueError("Competing consumer")
            r = cr.bounded_process([sys.executable, "-c", "import time; time.sleep(60)"], Path(temp), 5, fail)
            self.assertFalse(r["timed_out"])
            self.assertEqual(r["monitor_error"]["type"], "ValueError")
            self.assertTrue(r["cleanup_finished"])


class CalibrationWireTests(unittest.TestCase):
    def setUp(self):
        self.payload = {"model": "qwen3.8:27b-mlx", "stream": False, "messages": [{"role": "user", "content": "probe"}]}

    def test_native_finish_length_and_thinking_are_retained(self):
        raw = event(message={"role": "assistant", "content": "answer", "thinking": "thinking"}, done=True,
                    done_reason="length", prompt_eval_count=100, eval_count=1)
        converter = NativeResponse(self.payload, 1)
        sink = io.BytesIO()
        cr.collect(io.BytesIO(raw), converter, sink)
        self.assertEqual(sink.getvalue(), raw)
        self.assertEqual(converter.finish_reason, "length")
        self.assertEqual(converter.message["reasoning_content"], "thinking")

    def test_backend_error_is_preserved_and_not_called_a_completed_response(self):
        raw = event(message={"role": "assistant", "content": "partial"}, done=False)+b'{"error":"EOF"}\n'
        converter = NativeResponse(self.payload, 1)
        sink = io.BytesIO()
        with self.assertRaisesRegex(RuntimeError, "EOF"):
            cr.collect(io.BytesIO(raw), converter, sink)
        self.assertEqual(sink.getvalue(), raw)
        self.assertEqual(converter.message["content"], "partial")
        self.assertFalse(converter.done)

    def test_partial_framing_is_written_before_rejection_and_recoverable(self):
        complete = event(message={"role": "assistant", "content": "retained"}, done=False)
        raw = complete+b'{"model":'
        converter = NativeResponse(self.payload, 1)
        sink = io.BytesIO()
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            cr.collect(io.BytesIO(raw), converter, sink)
        self.assertEqual(sink.getvalue(), raw)
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory/"response.native.ndjson").write_bytes(raw)
            self.assertEqual(cr.recover(directory, self.payload)["content"], "retained")

    def test_worker_uses_the_full_approved_socket_budget_and_metadata_admission(self):
        class Response(io.BytesIO):
            pass
        c = condition("qwen38-27b-xhigh-v1", num_ctx=65536, num_predict=32768, seed=42)
        raw = event(message={"role": "assistant", "content": "usable", "thinking": "reason"}, done=True,
                    done_reason="stop", prompt_eval_count=200, eval_count=20)
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            cr.save(directory/"spec.json", {"condition": c, "request": self.payload, "budget_seconds": 1800})
            with patch.object(cr, "LocalClient") as ctor:
                client = ctor.return_value
                client.version.return_value = {"version": "0.40.5"}
                client.list_models.return_value = {"models": [{"name": c["candidate"]["model"], "digest": c["candidate"]["model_digest"]}]}
                client.show_model.return_value = {"capabilities": ["completion", "thinking", "tools"],
                                                  "thinking": {"values": [False, "xhigh"]},
                                                  "model_info": {"test.context_length": 262144}}
                client.list_running_models.side_effect = [{"models": []}, {"models": [{"name": c["candidate"]["model"], "digest": c["candidate"]["model_digest"], "context_length": 65536}]}]
                client.opener.open.return_value = Response(raw)
                self.assertEqual(cr.worker(directory/"spec.json"), 0)
                request = client.opener.open.call_args.args[0]
                body = json.loads(request.data)
                self.assertEqual(body["options"]["num_predict"], 32768)
                self.assertEqual(body["options"]["num_ctx"], 65536)
                self.assertEqual(body["think"], "xhigh")
                self.assertEqual(client.opener.open.call_args.kwargs["timeout"], 1810)
            result = json.loads((directory/"worker-result.json").read_text())
            self.assertTrue(result["context_conformant"])
            self.assertTrue(result["output_reserve_fits"])

    def test_missing_live_authorization_cannot_prepare_a_run(self):
        with tempfile.TemporaryDirectory(dir=cr.ROOT/"results") as temp:
            with patch.object(cr, "load_json", return_value={"authorization": {}}):
                with self.assertRaisesRegex(ValueError, "approved pilot execution"):
                    cr.prepare(Path(temp), Path("unused"))

    def test_prepare_freezes_exactly_twenty_requests_and_six_owner_texts_without_inference(self):
        gate = {"resource_gate": {"blocking_process_rules": [], "empty_state_observation_seconds": 30}}
        with tempfile.TemporaryDirectory(dir=cr.ROOT/"results") as temp:
            directory = Path(temp)
            cr.save(directory/"gate.json", gate)
            with patch.object(cr, "check_sources"), patch.object(cr, "LocalClient") as client:
                result = cr.prepare(directory, directory/"gate.json")
                client.assert_not_called()
                self.assertEqual(result["generation_requests"], 20)
                plan = json.loads((directory/"plan.json").read_text())
                units = [u for b in plan["blocks"] for u in b["units"]]
                self.assertEqual(len({u["unit_id"] for u in units}), 20)
                self.assertEqual(len({u["candidate_id"] for u in units}), 20)
                self.assertTrue(all(u["condition"]["limits"]["num_ctx"] == 65536 for u in units))
                self.assertTrue(all(u["condition"]["limits"]["num_predict"] == 32768 for u in units))
                self.assertNotIn("expected_fraction", json.dumps([u["request"] for u in units]))
                layout = json.loads((directory/"owner-layout.private.json").read_text())
                self.assertEqual(len(layout["pairs"]), 3)
                with self.assertRaisesRegex(ValueError, "already exists"):
                    cr.prepare(directory, directory/"gate.json")


if __name__ == "__main__":
    unittest.main()
