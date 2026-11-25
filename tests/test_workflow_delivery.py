import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch

from local_llm_benchmark import writing_workflow_study as s
from local_llm_benchmark.generation_budget import GenerationBudget
from local_llm_benchmark.writing_workflow import candidate_bundle,prepare_workspace,ToolBackend
from local_llm_benchmark.writing_workflow_delivery import PROTOCOL
from local_llm_benchmark.writing_workflow_native import NativeForwarder,StudyGateway
from local_llm_benchmark.writing_workflow_offline import OfflineGateway,complete_via_gateway
from test_workflow_live import FakeClient,selected,REGISTRY

OLD=s.ROOT/'results/agentic-dry-runs/offline-writing-workflow-v0.1/study-preparation-20261125T071848Z/study-v0.1'


class FinalDeliveryTests(unittest.TestCase):
    def test_actual_sdk_selector_normal_only_no_earlier_draft_rescue(self):
        code=r"""
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {regularFinalResponse as select} from './integrations/pi/writing-workflow-v0.1.mjs';
const answer={role:'assistant',stopReason:'stop',responseId:'ollama-native-2',content:[{type:'thinking',thinking:'PRIVATE'},{type:'text',text:'  FINAL\n'}]};
const end=messages=>({type:'agent_end',willRetry:false,messages});
assert.deepEqual(select([end([answer])]),{article:'  FINAL\n',response_id:'ollama-native-2'});
assert.ok(select([end([answer]),{type:'agent_settled'}]));
for(const change of [{stopReason:'length'},{stopReason:'aborted'},{stopReason:'error'}, {errorMessage:'failed'}, {content:[]},{content:[{type:'thinking',thinking:'PRIVATE'}]},{responseId:'other'}])assert.equal(select([end([answer,{...answer,...change}])]),null);
assert.equal(select([end([answer]),{type:'message_start'}]),null);
assert.equal(select([{...end([answer]),willRetry:true}]),null);
const call={role:'assistant',stopReason:'toolUse',content:[{type:'toolCall',id:'x'}]};
assert.equal(select([end([call,answer])]),null);
assert.ok(select([end([call,{role:'toolResult',toolCallId:'x',isError:true},answer])]));
assert.equal(select([end([answer,call])]),null);
// Regression for the real old event shape only. Never modify/regrade old output.
const old=JSON.parse(readFileSync(process.argv[1],'utf8'));
const result=select(old.events);assert.ok(result);assert.equal(result.response_id,'ollama-native-1');assert.equal(result.article.length,6326);
"""
        node=shutil.which('node')
        if not node:self.skipTest('Node unavailable')
        ran=subprocess.run([node,'--input-type=module','-e',code,str(OLD/'trials/t03/pi-state/pi-events.json')],cwd=s.ROOT,capture_output=True,text=True,timeout=15)
        self.assertEqual(ran.returncode,0,ran.stderr)

    def test_controller_exact_last_response_no_tool_count_and_terminal_freeze(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);budget=GenerationBudget(None,4,time.monotonic()+30)
            tools=ToolBackend(prepare_workspace(d/'workspace',candidate_bundle(s.ROOT)),d/'tools.jsonl',maximum_calls=48,deadline=budget.deadline)
            forwarder=NativeForwarder(d/'wire',selected(),REGISTRY,budget,lambda p:13,client=FakeClient())
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with StudyGateway(forwarder,tools,plan_sha256='a'*64,trial_id='t03',delivery_protocol=PROTOCOL) as gateway:
                def post(path,payload):
                    with opener.open(urllib.request.Request(gateway.url+path,json.dumps(payload).encode(),{'Content-Type':'application/json'})) as response:return json.load(response)
                request={'model':selected()['candidate']['model'],'messages':[{'role':'user','content':'fixture'}]}
                post('/v1/chat/completions',request);post('/v1/chat/completions',request)
                for bad in [{'article':'fixture answer','response_id':'ollama-native-1'},{'article':'EDITED','response_id':'ollama-native-2'}]:
                    with self.assertRaises(urllib.error.HTTPError) as caught:post('/final-response',bad)
                    caught.exception.close()
                self.assertFalse(tools.submitted)
                receipt=post('/final-response',{'article':'fixture answer','response_id':'ollama-native-2'})
                self.assertEqual(receipt['delivery_kind'],'assistant_final_text');self.assertEqual(tools.calls,0)
                self.assertEqual(budget.requests,2)
                for path,payload in [('/v1/chat/completions',request),('/tool/calculate',{'expression':'1+1'}),('/final-response',{'article':'fixture answer','response_id':'ollama-native-2'})]:
                    with self.assertRaises(urllib.error.HTTPError) as caught:post(path,payload)
                    caught.exception.close()
            (d/'policy.json').write_text(json.dumps({'delivery_protocol':PROTOCOL}))
            rows=s.journal_rows(d)
            trial={'condition':'C'}
            self.assertEqual(s.delivered_final(d,trial,rows,[],budget.deadline),b'fixture answer')
            # The same receipt is not admissible under the old protocol or after a later request.
            (d/'policy.json').write_text('{}')
            self.assertIsNone(s.delivered_final(d,trial,rows,[],budget.deadline))
            (d/'policy.json').write_text(json.dumps({'delivery_protocol':PROTOCOL}))
            self.assertIsNone(s.delivered_final(d,trial,rows+[{**rows[-1],'status':'failed'}],[],budget.deadline))

    def test_actual_pi_zero_tool_regular_final_and_legacy_rejection(self):
        node=shutil.which('node')
        if not node:self.skipTest('Node unavailable')
        for protocol,expected in [(PROTOCOL,0),('submit_tool_only_v1',1)]:
            with self.subTest(protocol=protocol),tempfile.TemporaryDirectory(dir=s.ROOT/'results') as tmp:
                d=Path(tmp);budget=GenerationBudget(None,3,time.monotonic()+30)
                tools=ToolBackend(prepare_workspace(d/'workspace',candidate_bundle(s.ROOT)),d/'tools.jsonl',maximum_calls=48,deadline=budget.deadline)
                responder=lambda p,n:{'message':{'content':'  SYNTHETIC FINAL\n','reasoning_content':'SYNTHETIC THINKING'},'usage':{'prompt_tokens':10,'completion_tokens':12}}
                with OfflineGateway(d/'wire',selected(),budget,tools,responder,registry_path=REGISTRY,delivery_protocol=protocol) as gateway:
                    policy={'mode':'offline_replay','delivery_protocol':protocol,'context_tokens':131072,'request_output_ceiling':131071,'run_root':str(d),'workspace':str(d/'workspace'),'gateway':gateway.url,'controller_nonce':gateway.nonce,'model':selected()['candidate']['model'],'messages':[{'role':'system','content':'Synthetic test only'},{'role':'user','content':'Synthetic fixture'}],'control_prompt':'Finish normally'}
                    (d/'policy.json').write_text(json.dumps(policy))
                    ran=subprocess.run([node,str(s.ROOT/'integrations/pi/writing-workflow-v0.1.mjs'),str(d/'policy.json')],capture_output=True,text=True,cwd=d/'workspace',timeout=20)
                self.assertEqual(ran.returncode,expected,ran.stderr)
                events=s.load(d/'pi-state/pi-events.json')
                self.assertFalse(events['submitted']);self.assertEqual(events['delivered'],expected==0)
                self.assertEqual(tools.calls,0);self.assertEqual(budget.requests,1)
                if expected==0:self.assertEqual((d/'workspace/output/article.md').read_text(),'  SYNTHETIC FINAL\n')

    def test_controller_rejects_length_empty_tool_use_deadline_and_poison(self):
        cases=[('length',{'content':'PARTIAL'},False,False),('stop',{'content':'  '},False,False),
               ('stop',{'content':'DRAFT','tool_calls':[{'id':'t','type':'function','function':{'name':'calculate','arguments':'{"expression":"1+1"}'}}]},False,False),
               ('stop',{'content':'FINAL'},True,False),('stop',{'content':'FINAL'},False,True)]
        for finish,message,poison,late in cases:
            with self.subTest(finish=finish,message=message,poison=poison,late=late),tempfile.TemporaryDirectory() as tmp:
                d=Path(tmp);budget=GenerationBudget(None,3,time.monotonic()+30)
                tools=ToolBackend(prepare_workspace(d/'workspace',candidate_bundle(s.ROOT)),d/'tools.jsonl',maximum_calls=48,deadline=budget.deadline)
                responder=lambda p,n:{'message':message,'finish_reason':finish,'usage':{'prompt_tokens':10,'completion_tokens':12}}
                with OfflineGateway(d/'wire',selected(),budget,tools,responder,registry_path=REGISTRY,delivery_protocol=PROTOCOL) as gateway:
                    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    def post(path,payload):
                        with opener.open(urllib.request.Request(gateway.url+path,json.dumps(payload).encode(),{'Content-Type':'application/json'})) as response:return response.read()
                    post('/v1/chat/completions',{'model':selected()['candidate']['model'],'messages':[{'role':'user','content':'fixture'}],
                        'tools':[{'type':'function','function':{'name':'calculate','parameters':{'type':'object','properties':{'expression':{'type':'string'}},'required':['expression']}}}]})
                    if poison:budget.poisoned=True
                    if late:budget.deadline=tools.deadline=time.monotonic()-1
                    with self.assertRaises(urllib.error.HTTPError) as caught:post('/final-response',{'article':message['content'],'response_id':'ollama-native-1'})
                    caught.exception.close();self.assertFalse(tools.submitted)

    def test_reuse_includes_both_unchanged_AB_with_provenance_not_old_C(self):
        old=s.load(OLD/'plan.json');trials=copy.deepcopy(old['trials']);bundle=candidate_bundle(s.ROOT)
        result=s.reuse_pair(OLD,bundle,trials)
        self.assertEqual(set(result),{'t01','t02'})
        self.assertEqual(sum(r['historical_generation_attempts'] for r in result.values()),5)
        trials[1]['seed']=99
        with self.assertRaisesRegex(ValueError,'unchanged'):s.reuse_pair(OLD,bundle,trials)
        bundle['sha256']={}
        with self.assertRaisesRegex(ValueError,'mismatch'):s.reuse_pair(OLD,bundle,old['trials'])

    def test_synthetic_import_forbidden_before_directory_creation(self):
        with tempfile.TemporaryDirectory(dir=s.ROOT/'results') as tmp:
            path=Path(tmp)/'absent'
            with self.assertRaisesRegex(ValueError,'synthetic'):s.prepare(path,mode='offline_validation',reuse_from=OLD)
            self.assertFalse(path.exists())

    def test_imports_do_not_construct_backend_and_keep_historical_costs_separate(self):
        old=s.load(OLD/'plan.json');imports=s.reuse_pair(OLD,candidate_bundle(s.ROOT),old['trials'])
        plan={**old,'mode':'live_study','reused_trials':imports}
        with tempfile.TemporaryDirectory(dir=s.ROOT/'results') as tmp:
            d=Path(tmp)
            with patch.object(s,'verify_plan',return_value=plan),patch.object(s.subprocess,'Popen') as awake,patch.object(s,'LocalClient',side_effect=RuntimeError('test stops before any new backend')) as client:
                awake.return_value.returncode=0
                awake.return_value.pid=12345
                result=s.execute(d,'a'*64)
            self.assertEqual(client.call_count,1)
            self.assertEqual(result['reused_trials'],2);self.assertEqual(result['newly_executed_trials'],0)
            self.assertEqual(result['generation_attempts'],0);self.assertEqual(result['historical_reused_generation_attempts'],5)
            self.assertEqual(result['finals_available'],2);self.assertEqual(result['status'],'stopped')


if __name__=='__main__':unittest.main()
