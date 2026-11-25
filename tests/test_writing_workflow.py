import copy,json,math,os,shutil,subprocess,tempfile,time,unittest,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
from local_llm_benchmark.writing_workflow import candidate_bundle,prepare_workspace,ToolBackend,calculate,CASE_DIR
from local_llm_benchmark.generation_budget import GenerationBudget,BudgetExhausted
from local_llm_benchmark.writing_workflow_offline import OfflineGateway,complete_via_gateway,fixed_workflow,_NoRedirect
from local_llm_benchmark.model_profiles import condition
ROOT=Path(__file__).resolve().parents[1]

class WritingToolsTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  self.bundle=candidate_bundle(ROOT);self.view=prepare_workspace(self.root/'workspace',self.bundle)
  self.tools=ToolBackend(self.view,self.root/'tools.jsonl',maximum_calls=48,deadline=time.monotonic()+60)
 def test_only_candidate_artifacts_are_compiled(self):
  original=Path.read_text
  def read(path,*a,**kw):
   if 'judge'in path.parts:raise AssertionError('Judge material opened')
   return original(path,*a,**kw)
  with patch.object(Path,'read_text',read):bundle=candidate_bundle(ROOT)
  self.assertEqual(len(bundle['documents']),12)
  self.assertFalse(any('judge'in p or 'reference'in p for p in bundle['files']))
  self.assertEqual(bundle['messages'][1]['content'],bundle['files']['brief.md']+'\n\n'+bundle['files']['source-packet.md'])
 def test_extra_text_in_packet_is_rejected_without_judge_access(self):
  shutil.copytree(ROOT/CASE_DIR,self.root/'case')
  packet=self.root/'case/candidate/source-packet.md'
  with packet.open('a') as out:out.write('\nHIDDEN ANSWER HINT\n')
  with self.assertRaisesRegex(ValueError,'packet differs'):candidate_bundle(self.root,Path('case'))
 def test_document_source_ids_and_explicit_paging(self):
  ids=self.tools.execute('list_documents',{})['documents'];self.assertEqual(len(ids),12)
  first=self.tools.execute('read_document',{'source_id':'S01','max_chars':20})
  self.assertFalse(first['complete']);self.assertEqual(first['next_offset'],20)
  rest=self.tools.execute('read_document',{'source_id':'S01','offset':20})
  self.assertEqual(first['text']+rest['text'],self.bundle['files']['sources/01-pilotauftrag.md'])
 def test_literal_search_has_source_locations(self):
  r=self.tools.execute('search_documents',{'query':'32','max_hits':1})
  self.assertEqual(len(r['hits']),1);self.assertIn('line',r['hits'][0]);self.assertGreater(r['total_matches'],0)
  self.assertEqual(self.tools.execute('search_documents',{'query':'[not a regex'})['total_matches'],0)
 def test_private_paths_and_unknown_arguments_are_denied(self):
  for name,p in [('read_document',{'source_id':'../judge/reference.json'}),('read_document',{'source_id':'S01','path':'/etc/passwd'}),('read_note',{'name':'../ref.md'}),('bash',{'command':'pwd'})]:
   with self.subTest(name=name,p=p),self.assertRaises(ValueError):self.tools.execute(name,p)
 def test_source_drift_and_source_symlink_are_denied(self):
  p=self.root/'workspace/sources/01-pilotauftrag.md';p.write_text('changed')
  with self.assertRaises(ValueError):self.tools.execute('read_document',{'source_id':'S01'})
  p.unlink();outside=self.root/'outside';outside.write_text('private');p.symlink_to(outside)
  with self.assertRaises(ValueError):self.tools.execute('read_document',{'source_id':'S01'})
 def test_notes_update_and_read_are_exact(self):
  self.tools.execute('write_note',{'name':'check.md','text':'first'})
  self.tools.execute('write_note',{'name':'check.md','text':'next'})
  self.assertEqual(self.tools.execute('read_note',{'name':'check.md'})['text'],'next')
 def test_note_symlink_and_hardlink_cannot_mutate_outside_file(self):
  outside=self.root/'private';outside.write_text('unchanged');p=self.root/'workspace/notes/check.md';p.symlink_to(outside)
  with self.assertRaises(ValueError):self.tools.execute('write_note',{'name':'check.md','text':'bad'})
  p.unlink();self.tools.execute('write_note',{'name':'check.md','text':'initial'});p.unlink();os.link(outside,p)
  with self.assertRaises(ValueError):self.tools.execute('write_note',{'name':'check.md','text':'bad'})
  self.assertEqual(outside.read_text(),'unchanged')
 def test_failed_calls_are_charged_and_deadline_is_global(self):
  t=ToolBackend(self.view,self.root/'limits.jsonl',maximum_calls=1,deadline=time.monotonic()+60)
  with self.assertRaises(ValueError):t.execute('read_document',{'source_id':'missing'})
  with self.assertRaises(ValueError):t.execute('list_documents',{})
  self.assertEqual(t.calls,2);self.assertEqual(t.failed_calls,2)
  t.deadline=0
  with self.assertRaises(ValueError):t.execute('submit_article',{'article':'final'})
  self.assertFalse((self.root/'workspace/output/article.md').exists())
 def test_submission_is_once_and_terminal(self):
  text='# Artikel\nExact text\n';self.tools.execute('submit_article',{'article':text})
  self.assertEqual((self.root/'workspace/output/article.md').read_text(),text)
  for name,p in [('submit_article',{'article':'replacement'}),('read_document',{'source_id':'S01'})]:
   with self.assertRaises(ValueError):self.tools.execute(name,p)
 def test_calculator_is_exact_and_does_not_claim_source_validation(self):
  r=calculate('(new/old-1)*100',{'new':6720,'old':6400});self.assertEqual(r['exact'],'5');self.assertFalse(r['source_values_verified'])
  self.assertEqual(calculate('1/3',{})['exact'],'1/3')
  for expr,values in [('__import__("os")',{}),('2**100',{}),('x',{'x':True}),('x',{'x':1.5}),('x',{'x':10**13}),('1/0',{})]:
   with self.subTest(expr=expr),self.assertRaises((ValueError,ZeroDivisionError)):calculate(expr,values)

class SharedBudgetTests(unittest.TestCase):
 def test_no_aggregate_cap_counts_beyond_65536_without_clamping(self):
  b=GenerationBudget(None,5,100,clock=lambda:0)
  for seq in range(1,5):
   self.assertEqual(b.begin(20000,seq),20000)
   b.finish(seq,{'prompt_tokens':100,'completion_tokens':20000},complete=True)
  self.assertEqual(b.begin(20000,5),20000)
  b.finish(5,{'prompt_tokens':100,'completion_tokens':1},complete=True)
  s=b.snapshot();self.assertEqual(s['actual_generated_tokens'],80001);self.assertEqual(s['actual_input_tokens'],500)
  self.assertIsNone(s['maximum_generated_tokens']);self.assertIsNone(s['remaining_generated_tokens'])
  self.assertFalse(s['aggregate_token_cap_enabled']);self.assertFalse(s['poisoned'])
 def test_no_aggregate_cap_still_enforces_other_guards(self):
  for usage in [None,{'prompt_tokens':1,'completion_tokens':4}]:
   b=GenerationBudget(None,3,100,clock=lambda:0);b.begin(3,1)
   b.finish(1,usage,complete=usage is not None)
   with self.assertRaises(BudgetExhausted):b.begin(3,2)
   if usage is None:self.assertIsNone(b.snapshot()['actual_generated_tokens'])
  b=GenerationBudget(None,1,100,clock=lambda:0);b.begin(3,1);b.finish(1,{'prompt_tokens':1,'completion_tokens':1},complete=True)
  with self.assertRaises(BudgetExhausted):b.begin(3,2)
  b=GenerationBudget(None,3,100,clock=lambda:100)
  with self.assertRaises(BudgetExhausted):b.begin(3,1)
 def test_invalid_aggregate_caps_are_not_interpreted_as_unlimited(self):
  for cap in [False,True,0,-1,1.5,float('inf')]:
   with self.subTest(cap=cap),self.assertRaises(ValueError):GenerationBudget(cap,2,100,clock=lambda:0)
 def test_unused_reserve_is_released_and_total_clamps_next_call(self):
  b=GenerationBudget(10,3,100,clock=lambda:0);self.assertEqual(b.begin(8,1),8)
  b.finish(1,{'prompt_tokens':20,'completion_tokens':3},complete=True)
  self.assertEqual(b.begin(20,2),7);b.finish(2,{'prompt_tokens':25,'completion_tokens':7},complete=True)
  with self.assertRaises(BudgetExhausted):b.begin(1,3)
  self.assertEqual(b.snapshot()['actual_input_tokens'],45)
 def test_unknown_usage_does_not_become_zero_cost(self):
  b=GenerationBudget(10,3,100,clock=lambda:0);b.begin(8,1);b.finish(1,None,complete=False)
  self.assertTrue(b.poisoned);self.assertIsNone(b.snapshot()['actual_generated_tokens'])
  with self.assertRaises(BudgetExhausted):b.begin(1,2)
 def test_backend_excess_closes_budget(self):
  b=GenerationBudget(10,3,100,clock=lambda:0);b.begin(3,1);b.finish(1,{'prompt_tokens':2,'completion_tokens':4},complete=True)
  self.assertTrue(b.poisoned);self.assertEqual(b.snapshot()['actual_generated_tokens'],4)
 def test_request_limit_concurrency_and_shared_deadline(self):
  now=[0];b=GenerationBudget(20,1,10,clock=lambda:now[0]);b.begin(8,1)
  with self.assertRaises(BudgetExhausted):b.begin(8,2)
  b.finish(1,{'prompt_tokens':2,'completion_tokens':1},complete=True)
  with self.assertRaises(BudgetExhausted):b.begin(8,2)
  b=GenerationBudget(20,4,10,clock=lambda:now[0]);now[0]=10
  with self.assertRaises(BudgetExhausted):b.begin(8,1)
 def test_nonfinite_deadlines_are_rejected(self):
  for value in [True,float('nan'),float('inf')]:
   with self.assertRaises(ValueError):GenerationBudget(10,2,value)

class FixedWorkflowTests(unittest.TestCase):
 def test_fixed_stages_keep_original_sources_and_select_last_artifact(self):
  b=candidate_bundle(ROOT);seen=[]
  prompts={x:x for x in ['orient_and_extract','draft','review','revise']}
  outputs=['notes','better draft','review','last actual final']
  def complete(messages,cap):seen.append((messages,cap));return {'content':outputs[len(seen)-1]}
  with tempfile.TemporaryDirectory() as temp:
   r=fixed_workflow(b,'B',prompts,Path(temp)/'out',complete,request_output_ceiling=48000)
  self.assertEqual(r['article'],'last actual final');self.assertEqual([x[1] for x in seen],[48000]*4)
  for msgs,_ in seen:self.assertEqual(msgs[:2],b['messages'])
  self.assertIn('better draft',seen[3][0][-1]['content']);self.assertIn('review',seen[3][0][-1]['content'])
 def test_direct_call_has_no_stage_hint(self):
  b=candidate_bundle(ROOT);seen=[]
  with tempfile.TemporaryDirectory() as temp:fixed_workflow(b,'A',{},Path(temp)/'out',lambda m,c:seen.append(m) or {'content':'article'},request_output_ceiling=48000)
  self.assertEqual(seen,[b['messages']])
 def test_failed_review_does_not_rescue_a_previous_draft(self):
  b=candidate_bundle(ROOT);calls=[]
  def complete(messages,cap):
   calls.append(messages)
   if len(calls)==3:raise BudgetExhausted('no remaining budget')
   return {'content':'earlier artifact'}
  with tempfile.TemporaryDirectory() as temp:
   output=Path(temp)/'out'
   with self.assertRaises(BudgetExhausted):fixed_workflow(b,'B',{x:x for x in ['orient_and_extract','draft','review','revise']},output,complete,request_output_ceiling=48000)
   self.assertTrue((output/'draft.md').is_file());self.assertFalse((output/'article-final.md').exists())

class OfflineGatewayTests(unittest.TestCase):
 def test_fixed_workflow_can_finish_above_65536_generated_tokens(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);bundle=candidate_bundle(ROOT);view=prepare_workspace(root/'workspace',bundle)
   tools=ToolBackend(view,root/'tools.jsonl',maximum_calls=48,deadline=time.monotonic()+60)
   budget=GenerationBudget(None,4,time.monotonic()+60);profile=condition('gemma4-31b-thinking-v1',num_ctx=65536,num_predict=32768,seed=42)
   with OfflineGateway(root/'wire',profile,budget,tools,lambda p,n:{'message':{'content':'SYNTHETIC stage '+str(n)},'usage':{'prompt_tokens':100,'completion_tokens':20000}}) as g:
    r=fixed_workflow(bundle,'B',{x:x for x in ['orient_and_extract','draft','review','revise']},root/'stages',lambda m,c:complete_via_gateway(g.url,profile['candidate']['model'],m,c),request_output_ceiling=32768)
   self.assertEqual(r['article'],'SYNTHETIC stage 4');self.assertEqual(budget.snapshot()['actual_generated_tokens'],80000)
   self.assertEqual([q['effective_request']['options']['num_predict'] for q in g.requests],[32768]*4)
   self.assertTrue(all(q['effective_request']['messages'][:2]==bundle['messages'] for q in g.requests))
   self.assertFalse(budget.poisoned)
 def test_nonfixture_urls_are_rejected_before_any_io(self):
  with patch('urllib.request.build_opener',side_effect=AssertionError('Unexpected network setup')):
   for url in ['http://127.0.0.1:11434','https://127.0.0.1:56789','http://localhost:56789','http://127.0.0.1:56789/v1','http://user@127.0.0.1:56789','http://127.0.0.1:56789?x=1']:
    with self.subTest(url=url),self.assertRaises(ValueError):complete_via_gateway(url,'model',[],1)
 def test_redirects_cannot_reach_another_endpoint(self):
  with self.assertRaisesRegex(ValueError,'redirects are forbidden'):_NoRedirect().redirect_request(None,None,302,'',{},'http://127.0.0.1:11434')
 def test_two_calls_share_effective_caps_and_preserve_controls(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);bundle=candidate_bundle(ROOT);view=prepare_workspace(root/'workspace',bundle)
   tools=ToolBackend(view,root/'tools.jsonl',maximum_calls=48,deadline=time.monotonic()+60)
   budget=GenerationBudget(10,4,time.monotonic()+60);profile=condition('gemma4-31b-thinking-v1',num_ctx=65536,num_predict=32768,seed=42)
   with OfflineGateway(root/'wire',profile,budget,tools,lambda p,n:{'message':{'content':'ok'},'usage':{'prompt_tokens':2,'completion_tokens':6 if n==1 else 4}}) as g:
    for _ in range(2):complete_via_gateway(g.url,profile['candidate']['model'],bundle['messages'],32768)
    with self.assertRaises(urllib.error.HTTPError):complete_via_gateway(g.url,profile['candidate']['model'],bundle['messages'],32768)
   self.assertEqual([x['effective_request']['options']['num_predict'] for x in g.requests[:2]],[10,4])
   for row in g.requests[:2]:self.assertIs(row['effective_request']['think'],True);self.assertEqual(row['effective_request']['options']['temperature'],1.0)
 def test_missing_usage_poison_stops_further_synthetic_generation(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);b=candidate_bundle(ROOT);v=prepare_workspace(root/'workspace',b);tools=ToolBackend(v,root/'t.jsonl',maximum_calls=48,deadline=time.monotonic()+30);budget=GenerationBudget(None,4,time.monotonic()+30);profile=condition('gemma4-31b-thinking-v1',num_ctx=65536,num_predict=32768,seed=42);calls=[]
   with OfflineGateway(root/'wire',profile,budget,tools,lambda *a:calls.append(1) or {'message':{'content':'unmetered'}}) as g:
    for _ in range(2):
     with self.assertRaises(urllib.error.HTTPError):complete_via_gateway(g.url,profile['candidate']['model'],b['messages'],32768)
   self.assertEqual(len(calls),1);self.assertTrue(budget.poisoned)

class PiLimitsTests(unittest.TestCase):
 def test_sdk_limits_are_explicit_instead_of_hardcoded(self):
  node=shutil.which('node')
  if not node:self.skipTest('Node is not installed')
  code="""
import assert from 'node:assert/strict';
import { modelLimits } from './integrations/pi/writing-workflow-v0.1.mjs';
assert.deepEqual(modelLimits({context_tokens:131072,request_output_ceiling:60000}),{contextWindow:131072,maxTokens:60000});
for(const policy of [{},{context_tokens:65536},{context_tokens:65536,request_output_ceiling:0},{context_tokens:65536,request_output_ceiling:65536},{context_tokens:65536,request_output_ceiling:true}])assert.throws(()=>modelLimits(policy));
"""
  r=subprocess.run([node,'--input-type=module','-e',code],cwd=ROOT,capture_output=True,text=True,timeout=15)
  self.assertEqual(r.returncode,0,r.stderr)

if __name__=='__main__':unittest.main()
