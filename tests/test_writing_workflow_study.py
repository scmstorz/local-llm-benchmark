import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch

from local_llm_benchmark import writing_workflow_study as s
from local_llm_benchmark.calibration_run import once
from local_llm_benchmark.workflow_watchdog import run_bounded
from local_llm_benchmark.generation_budget import GenerationBudget
from local_llm_benchmark.writing_workflow_native import NativeForwarder, StudyGateway
from local_llm_benchmark.writing_workflow import candidate_bundle,prepare_workspace,ToolBackend
from test_workflow_live import FakeClient,selected,REGISTRY


class StudyGuardTests(unittest.TestCase):
    def test_live_plan_requires_qualified_replay_before_creating_directory(self):
        with tempfile.TemporaryDirectory(dir=s.ROOT/'results') as tmp:
            path=Path(tmp)/'not-created'
            with self.assertRaisesRegex(ValueError,'offline replay'):s.prepare(path)
            self.assertFalse(path.exists())
    def test_approval_is_bound_to_exact_hash_and_actual_boolean(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);digest='a'*64
            for value in [None,1,False,True]:
                (d/'execution-approval.json').write_text(json.dumps({'schema_version':'writing-study-owner-approval-v1','study_plan_sha256':'b'*64 if value is True else digest,'owner_approved':value,'owner_reply':'test receipt'}))
                with self.assertRaises(ValueError):s.approval(d,digest)
            (d/'execution-approval.json').write_text(json.dumps({'schema_version':'writing-study-owner-approval-v1','study_plan_sha256':digest,'owner_approved':True,'owner_reply':'Explicit test fixture only'}))
            self.assertIs(s.approval(d,digest)['owner_approved'],True)

    def test_file_drift_stops_before_any_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input';p.write_text('frozen');mapping={str(p):s.sha(p)};p.write_text('changed')
            with patch.object(s,'LocalClient',side_effect=AssertionError('Backend must not be constructed')):
                with self.assertRaisesRegex(ValueError,'drift'):s.verify_files(mapping)

    def test_start_marker_cannot_be_overwritten_to_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'started.json';once(p,{'started':True})
            with self.assertRaises(FileExistsError):once(p,{'started':False})
            self.assertTrue(json.loads(p.read_text())['started'])

    def test_live_execute_without_approval_never_constructs_client(self):
        # The filesystem/plan verifier is separately exercised by the full replay.
        # This boundary test ensures parent admission precedes runtime operations.
        with tempfile.TemporaryDirectory(dir=s.ROOT/'results') as tmp:
            d=Path(tmp)
            with patch.object(s,'verify_plan',side_effect=FileNotFoundError('missing approval')),patch.object(s,'LocalClient',side_effect=AssertionError('Unexpected backend')):
                with self.assertRaises(FileNotFoundError):s.execute(d,'a'*64)
            self.assertFalse((d/'execution-started.json').exists())


class OutcomeTests(unittest.TestCase):
    def watch(self,deadline=100):return {'timed_out':False,'cleanup_finished':True,'monitor_error':None,'returncode':0,'deadline_monotonic':deadline}
    def trial(self,cid='C'):return {'trial_id':'t01','condition':cid,'seed':42,'maximum_tool_attempts':48 if cid=='C' else 0}

    def test_accepted_C_final_survives_session_cleanup_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);p=d/'workspace/output/article.md';p.parent.mkdir(parents=True);p.write_text('ACTUAL SUBMISSION')
            (d/'tools.jsonl').write_text(json.dumps({'tool':'submit_article','ok':True,'finished_monotonic':90,'result':{'accepted':True,'sha256':s.sha(p)}})+'\n')
            r=s.inspect_trial(d,self.trial(),{**self.watch(),'timed_out':True,'returncode':-15},mode='offline_validation')
            self.assertEqual(r['status'],'resource_limited');self.assertTrue(r['final_available'])
            self.assertEqual((d/'delivered-article.md').read_text(),'ACTUAL SUBMISSION')

    def test_unaccepted_or_late_C_file_is_diagnostic_only(self):
        for when in [None,101]:
            with tempfile.TemporaryDirectory() as tmp:
                d=Path(tmp);p=d/'workspace/output/article.md';p.parent.mkdir(parents=True);p.write_text('EARLIER FILE')
                if when:
                    (d/'tools.jsonl').write_text(json.dumps({'tool':'submit_article','ok':True,'finished_monotonic':when,'result':{'accepted':True,'sha256':s.sha(p)}})+'\n')
                r=s.inspect_trial(d,self.trial(),self.watch(),mode='offline_validation')
                self.assertFalse(r['final_available']);self.assertFalse((d/'delivered-article.md').exists())

    def test_truncated_tool_audit_preserves_completed_rows_without_inventing_total(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);(d/'tools.jsonl').write_bytes(b'{"tool":"calculate","ok":true}\n{"tool":')
            r=s.inspect_trial(d,self.trial(),{**self.watch(),'timed_out':True,'returncode':-15},mode='live_study')
            self.assertEqual(r['known_tool_attempts'],1);self.assertIsNone(r['tool_attempts'])
            self.assertFalse(r['tool_audit_complete']);self.assertFalse(r['final_available'])

    def test_B_cannot_rescue_a_better_earlier_draft(self):
        rows=[{'status':'complete','finish_reason':'stop','finished_monotonic':10,'recovered_message':{'content':'BETTER EARLIER DRAFT'}}]*3
        self.assertIsNone(s.delivered_final(Path('/unused'),self.trial('B'),rows,[],100))
        final={'status':'complete','finish_reason':'stop','finished_monotonic':20,'recovered_message':{'content':'ACTUAL FOURTH RESPONSE'}}
        self.assertEqual(s.delivered_final(Path('/unused'),self.trial('B'),rows+[final],[],100),b'ACTUAL FOURTH RESPONSE')
        final['finish_reason']='length';self.assertIsNone(s.delivered_final(Path('/unused'),self.trial('B'),rows+[final],[],100))

    def test_interrupted_generation_has_unknown_usage_and_no_quality_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);(d/'wire').mkdir();(d/'wire/request-0001.json').write_text(json.dumps({'sequence':1,'request':{'model':'fixture'},'status':'generating','forwarded':True}))
            r=s.inspect_trial(d,self.trial('A'),{**self.watch(),'timed_out':True,'returncode':-15},mode='live_study')
            self.assertEqual(r['generation_attempts'],1);self.assertIsNone(r['actual_generated_tokens'])
            self.assertFalse(r['final_available']);self.assertNotIn('quality_score',r)

    def test_complete_native_usage_can_be_recovered_without_promoting_partial_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);(d/'wire').mkdir();p=d/'wire/request-0001.json'
            p.write_text(json.dumps({'sequence':1,'request':{'model':'fixture'},'status':'generating','forwarded':True}))
            p.with_suffix('.native.ndjson').write_text(json.dumps({'model':'fixture','message':{'role':'assistant','content':'RECOVERED'},'done':True,'done_reason':'stop','prompt_eval_count':9,'eval_count':7})+'\n')
            r=s.inspect_trial(d,self.trial('A'),{**self.watch(),'timed_out':True,'returncode':-15},mode='live_study')
            self.assertEqual(r['actual_generated_tokens'],7);self.assertFalse(r['final_available'])


class SharedDeadlineTests(unittest.TestCase):
    def test_child_budget_receives_exact_parent_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=run_bounded([sys.executable,'-c',"import os;print(os.environ['LOCAL_LLM_WORKFLOW_DEADLINE_MONOTONIC'])"],Path(tmp)/'run',seconds=3)
            reported=float((Path(tmp)/'run/worker.stdout').read_text())
            self.assertEqual(reported,result['deadline_monotonic']);self.assertFalse(result['timed_out'])


class StudyProtocolTests(unittest.TestCase):
    def test_tool_guard_closes_controller_instead_of_admitting_more_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);view=prepare_workspace(d/'workspace',candidate_bundle(s.ROOT))
            budget=GenerationBudget(None,3,time.monotonic()+30)
            tools=ToolBackend(view,d/'tools.jsonl',maximum_calls=1,deadline=budget.deadline)
            forwarder=NativeForwarder(d/'wire',selected(),REGISTRY,budget,lambda p:13,client=FakeClient())
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with StudyGateway(forwarder,tools,plan_sha256='a'*64,trial_id='t03') as gateway:
                def call(name,args):
                    request=urllib.request.Request(gateway.url+'/tool/'+name,json.dumps(args).encode(),{'Content-Type':'application/json'})
                    return opener.open(request)
                with call('calculate',{'expression':'1+1'}) as response:self.assertEqual(json.load(response)['exact'],'2')
                for name,args in [('calculate',{'expression':'2+2'}),('submit_article',{'article':'too late'})]:
                    with self.assertRaises(urllib.error.HTTPError) as caught:call(name,args)
                    caught.exception.close()
            self.assertTrue(budget.poisoned);self.assertEqual(tools.calls,2)
            self.assertFalse(tools.submitted)

    def test_scored_gateway_binds_identity_and_streams_native_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);bundle=candidate_bundle(s.ROOT);view=prepare_workspace(d/'workspace',bundle)
            budget=GenerationBudget(None,3,time.monotonic()+30)
            tools=ToolBackend(view,d/'tools.jsonl',maximum_calls=48,deadline=budget.deadline)
            forwarder=NativeForwarder(d/'wire',selected(),REGISTRY,budget,lambda p:13,client=FakeClient())
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with StudyGateway(forwarder,tools,plan_sha256='a'*64,trial_id='t03') as gateway:
                with opener.open(gateway.url+'/offline-identity') as response:identity=json.load(response)
                self.assertEqual(identity['mode'],'local_native_study');self.assertEqual(identity['study_plan_sha256'],'a'*64);self.assertEqual(identity['trial_id'],'t03')
                for stream in [False,True]:
                    data={'model':selected()['candidate']['model'],'messages':[{'role':'user','content':'fixture'}],'stream':stream,'max_tokens':131071}
                    request=urllib.request.Request(gateway.url+'/v1/chat/completions',json.dumps(data).encode(),{'Content-Type':'application/json'})
                    with opener.open(request) as response:body=response.read()
                    if stream:self.assertIn(b'[DONE]',body)
                    else:self.assertEqual(json.loads(body)['choices'][0]['message']['content'],'fixture answer')
            self.assertEqual(budget.used_tokens,18)

    def test_scored_pi_rejects_wrong_mode_plan_trial_or_profile_before_state_creation(self):
        node=__import__('shutil').which('node')
        if not node:self.skipTest('Node unavailable')
        code="""
import assert from 'node:assert/strict';
import {run} from './integrations/pi/writing-workflow-v0.1.mjs';
const policy={mode:'scored_trial',context_tokens:131072,request_output_ceiling:131071,run_root:'/tmp/not-created-workflow',workspace:'/tmp/not-created-workflow/workspace',gateway:'http://127.0.0.1:54321',controller_nonce:'n',profile_binding_sha256:'c'.repeat(64),study_plan_sha256:'a'.repeat(64),trial_id:'t03'};
const valid={mode:'local_native_study',controller_nonce:'n',profile_binding_sha256:'c'.repeat(64),study_plan_sha256:'a'.repeat(64),trial_id:'t03'};
for(const change of [{mode:'local_native_technical'},{study_plan_sha256:'b'.repeat(64)},{trial_id:'t04'},{profile_binding_sha256:'d'.repeat(64)}]){
 globalThis.fetch=async()=>({ok:true,json:async()=>({...valid,...change})});
 await assert.rejects(run(policy),/bound controller|binding drift/);
}
"""
        result=__import__('subprocess').run([node,'--input-type=module','-e',code],cwd=s.ROOT,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
