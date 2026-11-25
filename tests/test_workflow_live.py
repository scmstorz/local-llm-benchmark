import copy
import io
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

from local_llm_benchmark.generation_budget import GenerationBudget
from local_llm_benchmark.model_profiles import candidate, condition, validate_deployment
from local_llm_benchmark.profiled_native import native_request
from local_llm_benchmark.workflow_context import ContextAdmission, ContextExhausted
from local_llm_benchmark.workflow_watchdog import run_bounded
from local_llm_benchmark.writing_workflow_native import NativeForwarder

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT/'models/offline-writing-profiles-v0.1.json'
PROFILE = 'gemma4-31b-thinking-ollama04017-workflow-v1'


def selected():
    return condition(PROFILE, num_ctx=131072, num_predict=131071, seed=42, registry_path=REGISTRY)


class ContextTests(unittest.TestCase):
    def test_exact_prompt_controls_available_output_and_never_trims_messages(self):
        seen = []
        oracle = ContextAdmission(lambda r: seen.append(r) or {'model':'gemma', '_debug_info':{'rendered_template':'FULL PROMPT'}}, lambda p:17, context_tokens=100)
        original = {'model':'gemma', 'messages':[{'role':'user','content':'ALL SOURCES'}], 'options':{'num_ctx':100,'num_predict':99}}
        native, audit = oracle.admit(original)
        self.assertEqual(native['options']['num_predict'],83)
        self.assertEqual(native['messages'],original['messages'])
        self.assertFalse(native['truncate']); self.assertFalse(native['shift'])
        self.assertTrue(seen[0]['_debug_render_only'])
        self.assertEqual(audit['input_tokens'],17)
        self.assertEqual(original['options']['num_predict'],99)

    def test_no_space_is_explicit_and_does_not_truncate(self):
        oracle=ContextAdmission(lambda r:{'model':'gemma','_debug_info':{'rendered_template':'full'}},lambda p:100,context_tokens=100)
        with self.assertRaises(ContextExhausted):oracle.admit({'model':'gemma','messages':[], 'options':{'num_ctx':100,'num_predict':99}})

    def test_missing_render_or_estimated_count_is_rejected(self):
        native={'model':'gemma','messages':[], 'options':{'num_ctx':100,'num_predict':99}}
        for debug,count in [({},17),({'model':'wrong','_debug_info':{'rendered_template':'x'}},17),({'model':'gemma','_debug_info':{'rendered_template':'x','image_count':1}},17),({'model':'gemma','_debug_info':{'rendered_template':'x'}},1.5)]:
            with self.subTest(debug=debug,count=count),self.assertRaises(ValueError):
                ContextAdmission(lambda r:debug,lambda p:count,context_tokens=100).admit(native)


class ProfileTests(unittest.TestCase):
    def test_new_registry_is_explicit_and_old_registry_does_not_admit_it(self):
        c=selected(); payload={'model':c['candidate']['model'],'messages':[{'role':'user','content':'fixture'}]}
        with self.assertRaises(ValueError):native_request(payload,c)
        actual,audit=native_request(payload,c,registry_path=REGISTRY)
        self.assertIs(actual['think'],True)
        self.assertEqual(actual['options']['num_predict'],131071)
        self.assertEqual(actual['options']['num_ctx'],131072)
        self.assertEqual(c['candidate']['ollama_version'],'0.40.17')
        self.assertEqual(candidate('gemma4-31b-thinking-v1')['ollama_version'],'0.40.5')


class FakeClient:
    def __init__(self, *, prompt_tokens=13, finish=True, trailing=False):
        self.profile=selected(); self.forwarded=[]; self.debug=[]
        self.opener=Mock(); self.opener.open.side_effect=self.open
        self.prompt_tokens,self.finish,self.trailing=prompt_tokens,finish,trailing
    def version(self):return {'version':'0.40.17'}
    def list_models(self):return {'models':[{'name':self.profile['candidate']['model'],'digest':self.profile['candidate']['model_digest']}]}
    def list_running_models(self):return {'models':[{**self.list_models()['models'][0],'context_length':131072}]}
    def show_model(self,model):return {'renderer':'gemma4-large','parser':'gemma4','capabilities':['completion','thinking','tools'],'thinking':{'values':[False,True]},'model_info':{'gemma4.context_length':262144}}
    def _request_json(self,method,path,payload):
        assert payload['_debug_render_only'] is True
        self.debug.append(payload)
        return {'model':payload['model'],'_debug_info':{'rendered_template':'EXACT FIXTURE PROMPT'}}
    def open(self,request,timeout):
        payload=json.loads(request.data);self.forwarded.append(payload)
        first={'model':payload['model'],'message':{'role':'assistant','thinking':'fixture reasoning','content':'fixture answer'},'done':False}
        events=[first]
        if self.finish:events.append({'model':payload['model'],'message':{'role':'assistant','content':''},'done':True,'done_reason':'stop','prompt_eval_count':self.prompt_tokens,'eval_count':9})
        if self.trailing:events.append(first)
        return io.BytesIO(('\n'.join(json.dumps(x) for x in events)+'\n').encode())


class ForwarderTests(unittest.TestCase):
    def run_fixture(self, directory, client, *, stream=False, send=None):
        b=GenerationBudget(None,3,time.monotonic()+20)
        f=NativeForwarder(directory/'wire',selected(),REGISTRY,b,lambda p:13,client=client)
        payload={'model':selected()['candidate']['model'],'messages':[{'role':'user','content':'fixture'}],'stream':stream,'max_tokens':131071}
        return f,b,payload

    def test_forwarding_uses_available_context_and_records_reasoning_usage(self):
        with tempfile.TemporaryDirectory() as temp:
            c=FakeClient();f,b,p=self.run_fixture(Path(temp),c)
            result=json.loads(f.execute(p))
            self.assertEqual(c.forwarded[0]['options']['num_predict'],131059)
            self.assertFalse(c.forwarded[0]['truncate']);self.assertFalse(c.forwarded[0]['shift'])
            self.assertEqual(result['choices'][0]['message']['reasoning_content'],'fixture reasoning')
            self.assertEqual(b.used_tokens,9);self.assertIsNone(b.generated_tokens)
            record=json.loads((Path(temp)/'wire/request-0001.json').read_text())
            self.assertEqual(record['context']['input_tokens'],13)
            self.assertEqual(record['status'],'complete')

    def test_renderer_variant_drift_is_rejected_before_generation(self):
        with tempfile.TemporaryDirectory() as temp:
            c=FakeClient();original=c.show_model;c.show_model=lambda model:{**original(model),'renderer':'gemma4'}
            f,b,p=self.run_fixture(Path(temp),c)
            with self.assertRaisesRegex(ValueError,'renderer/parser'):f.execute(p)
            self.assertEqual(c.forwarded,[]);self.assertEqual(f.generation_attempts,0)

    def test_prompt_count_mismatch_closes_controller_but_preserves_known_usage(self):
        with tempfile.TemporaryDirectory() as temp:
            c=FakeClient(prompt_tokens=12);f,b,p=self.run_fixture(Path(temp),c)
            with self.assertRaisesRegex(ValueError,'prompt count'):f.execute(p)
            self.assertTrue(b.poisoned);self.assertEqual(b.snapshot()['actual_generated_tokens'],9)
            with self.assertRaises(ValueError):f.execute(p)
            self.assertEqual(len(c.forwarded),1)

    def test_incomplete_stream_is_unknown_and_never_gets_done(self):
        with tempfile.TemporaryDirectory() as temp:
            c=FakeClient(finish=False);f,b,p=self.run_fixture(Path(temp),c,stream=True);chunks=[]
            with self.assertRaises(ValueError):f.execute(p,start_stream=lambda:None,send_chunk=chunks.append)
            self.assertNotIn(b'[DONE]',b''.join(chunks));self.assertIsNone(b.snapshot()['actual_generated_tokens'])

    def test_terminal_frame_is_returned_after_complete_validation_and_lock_release(self):
        with tempfile.TemporaryDirectory() as temp:
            c=FakeClient();f,b,p=self.run_fixture(Path(temp),c,stream=True);chunks=[]
            tail=f.execute(p,start_stream=lambda:None,send_chunk=chunks.append)
            self.assertNotIn(b'[DONE]',b''.join(chunks));self.assertIn(b'[DONE]',tail)
            self.assertFalse(f.lock.locked());self.assertEqual(b.used_tokens,9)

    def test_trailing_native_event_cannot_expose_done(self):
        with tempfile.TemporaryDirectory() as temp:
            c=FakeClient(trailing=True);f,b,p=self.run_fixture(Path(temp),c,stream=True);chunks=[]
            with self.assertRaises(ValueError):f.execute(p,start_stream=lambda:None,send_chunk=chunks.append)
            self.assertNotIn(b'[DONE]',b''.join(chunks));self.assertTrue(b.poisoned)


class WatchdogTests(unittest.TestCase):
    def test_invalid_deadlines_are_rejected_before_any_process(self):
        for value in [0,3601,True,float('nan'),float('inf')]:
            with self.subTest(value=value),self.assertRaises(ValueError):run_bounded([],Path('/not-created'),seconds=value)

    def test_whole_worker_group_is_killed_at_deadline(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)/'run'
            code="import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);time.sleep(60)"
            result=run_bounded([sys.executable,'-c',code],directory,seconds=.4)
            self.assertTrue(result['timed_out']);self.assertTrue(result['cleanup_finished'])
            self.assertLess(result['deadline_signal_elapsed_seconds'],2)
            self.assertTrue(all(not c['result']['remaining'] for c in result['cleanup']))
            self.assertFalse(result['backend_cancellation_verified'])

    def test_independent_deadline_survives_blocked_parent_monitor(self):
        with tempfile.TemporaryDirectory() as temp:
            result=run_bounded([sys.executable,'-c','import time;time.sleep(60)'],Path(temp)/'run',seconds=.25,monitor=lambda:time.sleep(.8))
            self.assertTrue(result['timed_out']);self.assertLess(result['deadline_signal_elapsed_seconds'],.7)
            self.assertTrue(result['cleanup_finished'])


if __name__=='__main__':unittest.main()
