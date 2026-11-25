"""Frozen A/B/Pi pilot plans, separate approval and one-shot trial execution.

Preparing and offline replay never construct an Ollama client. Measured execution
requires an approval receipt for this exact plan hash. No automatic trial retries,
rescued drafts, downloads, consumer stops, core registration or public exports.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
from contextlib import ExitStack

from .calibration_run import LocalClient, activity, once, save
from .generation_budget import GenerationBudget
from .external_cli_native import NativeResponse
from .log_incident_smokes import run_resource_gate
from .model_profiles import condition, binding_sha256
from .runner import utc_now
from .workflow_context import ArtifactTokenizer
from .workflow_watchdog import run_bounded
from .writing_workflow import CASE_DIR, candidate_bundle, prepare_workspace, ToolBackend
from .writing_workflow_native import NativeForwarder, StudyGateway
from .writing_workflow_offline import OfflineGateway, complete_via_gateway, fixed_workflow
from .writing_workflow_sandbox import acceptance, build_profile, command
from .writing_workflow_delivery import PROTOCOL

ROOT=Path(__file__).resolve().parents[1]
REGISTRY=Path('models/offline-writing-profiles-v0.1.json')
PROFILE='gemma4-31b-thinking-ollama04017-workflow-v1'
QUALIFICATION=Path('results/agentic-dry-runs/offline-writing-workflow-v0.1/live-preparation-20261125T063844Z')
CONDITIONS=CASE_DIR/'conditions.draft.json'
ORDER=[('A',42),('B',42),('C',42),('C',314159),('B',314159),('A',314159)]
SCHEMA='offline-writing-frozen-study-v2'


def load(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def study_path(path: Path) -> Path:
    path=path.resolve()
    if not path.is_relative_to(ROOT/'results'):
        raise ValueError('A private study below repository results is required')
    return path


def verify_files(mapping):
    for name,expected in mapping.items():
        path=Path(name)
        if not path.is_absolute():path=ROOT/path
        if not path.is_file() or path.is_symlink() or sha(path)!=expected:
            raise ValueError('Frozen artifact drift: '+name)


def approval(study: Path, digest: str) -> dict:
    value=load(study/'execution-approval.json')
    if (value.get('schema_version')!='writing-study-owner-approval-v1'
            or value.get('study_plan_sha256')!=digest
            or value.get('owner_approved') is not True
            or not isinstance(value.get('owner_reply'),str) or not value['owner_reply'].strip()):
        raise ValueError('Explicit owner approval for this exact plan is required')
    return value


def verify_plan(study: Path, digest: str, *, require_approval=False) -> dict:
    study=study_path(study)
    if sha(study/'plan.json')!=digest:
        raise ValueError('Frozen plan hash mismatch')
    plan=load(study/'plan.json')
    if plan.get('schema_version')!=SCHEMA or plan.get('mode') not in ('live_study','offline_validation'):
        raise ValueError('Unsupported study protocol')
    if plan.get('delivery_protocol')!=PROTOCOL:raise ValueError('Prospective delivery rule required')
    if plan.get('python_version')!=sys.version:
        raise ValueError('Python runtime identity drift')
    if plan['trial_seconds']!=3600 or plan['aggregate_generated_token_cap'] is not None:
        raise ValueError('Owner token/time policy drift')
    if [(t['condition'],t['seed']) for t in plan['trials']]!=ORDER:
        raise ValueError('Frozen trial order/count drift')
    if [t['trial_id'] for t in plan['trials']]!=['t'+str(i).zfill(2) for i in range(1,7)]:
        raise ValueError('Trial identity drift')
    if [t['maximum_model_requests'] for t in plan['trials']]!=[1,4,12,12,4,1]:
        raise ValueError('Frozen model-call guard drift')
    verify_files(plan['source_sha256'])
    verify_files(plan['dependencies_sha256'])
    if sha(study/'pi-runtime-files.json')!=plan['pi_runtime_manifest_sha256']:
        raise ValueError('Pi runtime manifest drift')
    verify_files(load(study/'pi-runtime-files.json'))
    imports=plan.get('reused_trials',{})
    if imports:
        if plan['mode']!='live_study' or set(imports)!={'t01','t02'}:raise ValueError('Only the complete prior A/B pair may be reused')
        for item in imports.values():verify_files(item['artifacts_sha256'])
    if require_approval:
        if plan['mode']!='live_study':raise ValueError('Synthetic validation cannot become measured execution')
        approval(study,digest)
    return plan


def reuse_pair(prior: Path,bundle: dict,trials: list) -> dict:
    """Import both valid A42/B42 results, never select by observed quality."""
    prior=study_path(prior);old=load(prior/'plan.json');frozen=load(prior/'execution-frozen.json')
    verify_files({str(prior/p):v for p,v in frozen['artifacts_sha256'].items()})
    if (old.get('schema_version')!='offline-writing-frozen-study-v1' or old.get('mode')!='live_study'
            or frozen['study_plan_sha256']!=sha(prior/'plan.json')
            or old['common_candidate_sha256']!=bundle['sha256']):raise ValueError('Prior study/material mismatch')
    approval(prior,sha(prior/'plan.json'))
    if old.get('python_version')!=sys.version:raise ValueError('Prior A/B Python runtime drift')
    verify_files(old['dependencies_sha256'])
    if sha(prior/'pi-runtime-files.json')!=old['pi_runtime_manifest_sha256']:raise ValueError('Prior runtime manifest drift')
    verify_files(load(prior/'pi-runtime-files.json'))
    # Compare A/B-relevant definitions with the frozen old sources. Pi delivery
    # and shared accounting wrappers may change; A/B generation semantics may not.
    checks={'local_llm_benchmark/writing_workflow_offline.py':['fixed_workflow'],
            'local_llm_benchmark/writing_workflow_native.py':['NativeForwarder'],
            'local_llm_benchmark/profiled_native.py':['native_request'],
            'local_llm_benchmark/workflow_context.py':['ContextAdmission','ArtifactTokenizer'],
            'local_llm_benchmark/generation_budget.py':['GenerationBudget']}
    for name,definitions in checks.items():
        trees=[ast.parse(p.read_text()) for p in (prior/'source-snapshot'/name,ROOT/name)]
        for definition in definitions:
            nodes=[next(n for n in tree.body if getattr(n,'name',None)==definition) for tree in trees]
            if ast.dump(nodes[0])!=ast.dump(nodes[1]):raise ValueError('A/B execution semantics changed: '+definition)
    paths=[REGISTRY,*[CASE_DIR/'prompts'/f'B{i}-{name}.md' for i,name in enumerate(['orient','draft','review','revise'],1)]]
    for relative in paths:
        if sha(ROOT/relative)!=old['source_sha256'][str(relative)]:raise ValueError('Prior A/B prompt/profile drift')
    result={}
    for trial in trials[:2]:
        tid=trial['trial_id'];d=prior/'trials'/tid;record=load(d/'record.json')
        previous=next(t for t in old['trials'] if t['trial_id']==tid)
        if (trial!=previous or record['status']!='complete' or not record['final_available']
                or not record['usage_complete'] or record['final_sha256']!=sha(d/'delivered-article.md')):
            raise ValueError('Only unchanged complete A42/B42 trials may be reused')
        artifacts={str(prior/p):v for p,v in frozen['artifacts_sha256'].items() if p.startswith('trials/'+tid+'/')}
        artifacts.update({str(prior/'plan.json'):sha(prior/'plan.json'),str(prior/'execution-frozen.json'):sha(prior/'execution-frozen.json')})
        result[tid]={'prior_study':str(prior),'prior_plan_sha256':sha(prior/'plan.json'),
                     'artifacts_sha256':artifacts,'historical_generation_attempts':record['generation_attempts'],
                     'final_sha256':record['final_sha256'],'compatibility':'Same common input, A/B prompts, profile/seed and generation/context/budget definitions; prospective Pi delivery wrapper changed.',
                     'timing_caveat':'Original UTC/monotonic gaps remain unexplained; reuse for quality, do not pool as clean timing repetitions.'}
    return result


def prepare(study: Path, *, mode='live_study', validated_replay: Path | None=None, reuse_from: Path | None=None) -> dict:
    if mode not in ('live_study','offline_validation'):raise ValueError('Explicit preparation mode required')
    if mode=='live_study' and validated_replay is None:
        raise ValueError('A completed bound offline replay is required before a live plan')
    if reuse_from and mode!='live_study':raise ValueError('Real imports cannot enter synthetic validation')
    study=study_path(study);study.mkdir(parents=True,exist_ok=False)
    bundle=candidate_bundle(ROOT);q=ROOT/QUALIFICATION
    completion=load(q/'completion.json');validation=load(q/'validation.json')
    if not validation['passed'] or not completion['native_backend_cancellation_verified']:
        raise ValueError('Native/context/watchdog qualification is incomplete')
    binding=load(q/'tokenizer-artifact-binding.json');wheel=load(q/'tokenizer-wheel.json')
    dependencies={binding['tokenizer_path']:binding['tokenizer_sha256'],
                  binding['manifest_path']:binding['manifest_sha256_verified']}
    runtime=q/'tokenizer-runtime'
    dependencies.update({str(runtime/name):value for name,value in wheel['files_sha256'].items()})
    node=Path(shutil.which('node')).resolve()
    if subprocess.check_output([str(node),'--version'],text=True).strip()!='v22.22.1':
        raise ValueError('Node runtime differs from the qualified version')
    dependencies[str(node)]=sha(node)
    python=Path(sys.executable).resolve()
    dependencies[str(python)]=sha(python)
    verify_files(dependencies)
    pi_files={str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'integrations/pi/node_modules').rglob('*')) if p.is_file() and not p.is_symlink()}
    once(study/'pi-runtime-files.json',pi_files)
    sources={*ROOT.glob('local_llm_benchmark/*.py'),*(ROOT/CASE_DIR).rglob('*'),
             ROOT/REGISTRY,ROOT/'integrations/pi/writing-workflow-v0.1.mjs',
             ROOT/'integrations/pi/package-lock.json',ROOT/'integrations/pi/package.json',
             ROOT/'tasks/calibration/practical-profiles-v0.1/rubric.json',
             q/'completion.json',q/'validation.json',q/'tokenizer-artifact-binding.json',q/'tokenizer-wheel.json'}
    sources={p for p in sources if p.is_file() and '__pycache__'not in p.parts}
    replay_binding=None
    if mode=='live_study':
        replay=study_path(validated_replay);rp=load(replay/'plan.json');rc=load(replay/'execution-closeout.json')
        verify_plan(replay,sha(replay/'plan.json'))
        if (rp['mode']!='offline_validation' or rc['status']!='complete' or rc['trials_consumed']!=6
                or rc['finals_available']!=6 or rc['actual_ollama_generations']!=0
                or rp['source_sha256']!={str(p.relative_to(ROOT)):sha(p) for p in sorted(sources)}
                or rp['common_candidate_sha256']!=bundle['sha256']
                or rp['dependencies_sha256']!=dependencies
                or rp['pi_runtime_manifest_sha256']!=sha(study/'pi-runtime-files.json')):
            raise ValueError('Offline replay does not qualify this exact source/runtime/material set')
        frozen=load(replay/'execution-frozen.json')
        verify_files({str(replay/p):v for p,v in frozen['artifacts_sha256'].items()})
        replay_binding={'path':str(replay),'plan_sha256':sha(replay/'plan.json'),
                        'closeout_sha256':sha(replay/'execution-closeout.json'),
                        'frozen_sha256':sha(replay/'execution-frozen.json')}
        sources.update([replay/'plan.json',replay/'execution-closeout.json',replay/'execution-frozen.json'])
    old=load(ROOT/'results/agentic-dry-runs/inkling-text-pilot-v0.1/pilot-20261124T184328Z/plan.json')
    old['resource_gate']['blocking_process_rules'].append({
        'rule_id':'chess_coach_application','pattern':r'(?i)(?:chess-opening-coach|chess-coach)'})
    trials=[]
    for i,(cid,seed) in enumerate(ORDER,1):
        c=condition(PROFILE,num_ctx=131072,num_predict=131071,seed=seed,registry_path=ROOT/REGISTRY)
        trials.append({'trial_id':'t'+str(i).zfill(2),'condition':cid,'seed':seed,
                       'maximum_model_requests':{'A':1,'B':4,'C':12}[cid],
                       'maximum_tool_attempts':48 if cid=='C' else 0,'profile':c})
    imports=reuse_pair(reuse_from,bundle,trials) if reuse_from else {}
    maximum_generations=sum(t['maximum_model_requests'] for t in trials if t['trial_id'] not in imports)
    plan={'schema_version':SCHEMA,'delivery_protocol':PROTOCOL,'reused_trials':imports,'study_id':study.name,'prepared_at':utc_now(),'mode':mode,
          'status':'awaiting_owner_execution_approval' if mode=='live_study' else 'synthetic_validation_only',
          'case_id':bundle['case_id'],'trials':trials,'trial_seconds':3600,
          'aggregate_generated_token_cap':None,'maximum_generation_attempts':maximum_generations,
          'maximum_active_seconds':3600*(6-len(imports)),'repetitions':2,'whole_trial_retries':0,'warmups':0,
          'qualification_path':str(QUALIFICATION),'orchestration_replay':replay_binding,'tokenizer_runtime':str(runtime),
          'tokenizer_artifact':binding,'node_binary':str(node),'python_binary':str(python),
          'python_version':sys.version,'common_candidate_sha256':bundle['sha256'],
          'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sorted(sources)},
          'dependencies_sha256':dependencies,'pi_runtime_manifest_sha256':sha(study/'pi-runtime-files.json'),
          'resource_gate':old['resource_gate'],'initial_state':'Fresh conversation/workspace/notes/harness per trial; empty Ollama30s before every live trial. This is process residency, not an OS disk-cache reset.',
          'termination':'A: completed direct text. B: completed fourth-stage final. C: timely accepted submit_article OR actual last regular nonempty assistant text, stop only, no pending tools/error, exact native match. No earlier-draft rescue, extra reminder or retry. Old C remains a protocol failure; C42 is a new prospective v2 measurement.',
          'timing_policy':'Record both UTC and monotonic timing. Scope caffeinate -i to this executor to inhibit idle sleep; no permanent settings. Imported A/B timing gaps remain unexplained and cannot be pooled into clean speed estimates.',
          'continue_policy':'Continue only after clean backend/process postflight, stable sources, and a completed or explicitly resource-limited trial. Other errors stop the study; no re-execution of consumed trials.',
          'evaluation':'Frozen existing rubric plus v0.2 reading/editing split and source-bound judge instructions; no evaluation during generation. Exploratory two repeats, no significance claim.'}
    once(study/'plan.json',plan)
    for p in sorted(sources):
        target=study/'source-snapshot'/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes())
    digest=sha(study/'plan.json')
    text=f'''# Konkreter Schreibworkflow-Vergleich\n\nPlan: `{digest}`\n\nModus: `{mode}`. Einfrieren ist keine Ausführungsfreigabe.\n\nEin fiktiver Dokumentenfall, Gemma4 31B MLX unter Ollama0.40.17, Thinking an, Temperatur1 / top_p0,95 / top_k64.131.072 Kontext je Anfrage; Ausgabe nur durch verfügbaren Kontext/technische Grenzen beschränkt. Kein Token-Gesamtlimit.\n\n| Versuch | Ablauf | Seed | Höchstens Modellaufrufe |\n|---|---|---:|---:|\n'''
    for t in trials:text+=f"| {t['trial_id']}{' (übernehmen)' if t['trial_id'] in imports else ' (neu)'} | {t['condition']} | {t['seed']} | {0 if t['trial_id'] in imports else t['maximum_model_requests']} |\n"
    text+=f'\nA: direkt. B: Sondieren → Entwurf → Review → Endfassung. C: Pi, höchstens48 Werkzeugversuche. Ziel: zwei Ergebnisse je Bedingung. {len(imports)} bestehende gültige A/B-Ergebnisse werden mit Herkunft und unveränderten Originalkosten übernommen, {6-len(imports)} Versuche neu ausgeführt. Höchstens{maximum_generations} neue Generierungen;60 Minuten je neuem Versuch, höchstens{6-len(imports)} Stunden aktive Sicherheitszeit, keine Laufzeitprognose. Vorabkontrollen/Aufräumen separat.\n\n**Vorab festgelegte Abgabe v2:** Pi darf submit_article oder seine tatsächliche letzte reguläre, nichtleere Textantwort abgeben. Nur normaler Abschluss ohne offene Tools/Fehler; SDK-Text und letzte native Antwort müssen exakt übereinstimmen. Kein zusätzlicher Modellaufruf, kein Nachfordern, kein früherer Entwurf. Der alte C42 bleibt ein Protokollfehler; der neue C42 ist ein gesonderter Versuch unter der geänderten Regel.\n\nAlle erhalten denselben Auftrag und dieselben zwölf Quellen. A/B-Prompts und Modellprofile unverändert; nur die Pi-Abgabeanweisung/Adapterregel ändert sich. Frischer Zustand und leeres Backend30s vor jedem neuen Versuch. Quellen/Code/Modell/Tokenizer/Pi sind per Hash gebunden. Keine automatischen Wiederholungen.\n\n**Übernahme und Zeiten:** Vorhandene A42/B42 werden beide übernommen, ohne Qualitätsauswahl. Die Originalmessung bleibt unangetastet. Ihre ungeklärten UTC-/Monotonie-Abweichungen bleiben sichtbar; keine gemischten sauberen Geschwindigkeitsmittelwerte. Bei neuen Versuchen verhindert ein temporäres, an den Executor gebundenes caffeinate -i automatischen Idle-Schlaf; beide Uhren werden erhalten.\n\nTeilantworten und sämtliche tatsächlichen Kosten bleiben erhalten. Technische Ausfälle bekommen keinen erfundenen Qualitätswert. Nahezu voller131k-Speicherbedarf wurde nicht belastet. Anschließend separate Qualitätsbewertung; explorativ, keine allgemeine Harness-/Modellaussage.\n'
    (study/'PLAN.md').write_text(text)
    return {'study':str(study),'plan_sha256':digest,'mode':mode,'trials':6,'reused_trials':len(imports),'maximum_generations':maximum_generations}


def fixture_response(trial, payload, sequence):
    text='SYNTHETISCH – KEINE BENCHMARKANTWORT – '+trial['trial_id']+' – Stufe '+str(sequence)
    message={'content':text,'reasoning_content':'SYNTHETISCHE DENKSPUR'}
    if trial['condition']=='C':
        if trial['seed']==42:
            if sequence==1:
                return {'message':{'content':'','tool_calls':[{'id':'fixture-1','type':'function','function':{'name':'calculate','arguments':'{"expression":"7*8"}'}}]},'usage':{'prompt_tokens':100,'completion_tokens':40000}}
            return {'message':message,'usage':{'prompt_tokens':100,'completion_tokens':40000}}
        steps=[('list_documents',{}),('read_document',{'source_id':'S01','max_chars':100}),
               ('search_documents',{'query':'Nacharbeit'}),('calculate',{'expression':'7*8'}),
               ('write_note',{'name':'probe.md','text':'SYNTHETISCH'}),('read_note',{'name':'probe.md'}),
               ('submit_article',{'article':text})]
        name,args=steps[sequence-1]
        message={'content':'','reasoning_content':'SYNTHETISCHE DENKSPUR',
                 'tool_calls':[{'id':'fixture-'+str(sequence),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
    return {'message':message,'usage':{'prompt_tokens':100,'completion_tokens':10000}}


def worker(study: Path, digest: str, trial_id: str) -> int:
    plan=verify_plan(study,digest,require_approval=load(study/'plan.json')['mode']=='live_study')
    trial=next(t for t in plan['trials'] if t['trial_id']==trial_id)
    directory=study/'trials'/trial_id
    marker=load(directory/'started.json')
    if marker['study_plan_sha256']!=digest or os.getpgrp()!=os.getpid():
        raise ValueError('Worker must belong to its independently watched group')
    deadline=float(os.environ['LOCAL_LLM_WORKFLOW_DEADLINE_MONOTONIC'])
    if not math.isfinite(deadline) or not 0<deadline-time.monotonic()<=3600:
        raise ValueError('Invalid inherited parent deadline')
    once(directory/'worker-started.json',{'at':utc_now(),'deadline_monotonic':deadline})
    profile=trial['profile'];model=profile['candidate']['model'];budget=GenerationBudget(None,trial['maximum_model_requests'],deadline)
    result={'mode':plan['mode'],'condition':trial['condition'],'status':'setup','final_available':False}
    try:
        bundle=candidate_bundle(ROOT)
        if bundle['sha256']!=plan['common_candidate_sha256']:raise ValueError('Candidate bundle drift')
        view=prepare_workspace(directory/'workspace',bundle)
        tools=ToolBackend(view,directory/'tools.jsonl',maximum_calls=trial['maximum_tool_attempts'] or 1,deadline=deadline)
        with ExitStack() as stack:
            if plan['mode']=='offline_validation':
                gateway=stack.enter_context(OfflineGateway(directory/'wire',profile,budget,tools,
                    lambda p,n:fixture_response(trial,p,n),registry_path=ROOT/REGISTRY,
                    study_binding={'study_plan_sha256':digest,'trial_id':trial_id},delivery_protocol=plan['delivery_protocol']))
                complete=lambda messages,cap:complete_via_gateway(gateway.url,model,messages,cap)
            else:
                sys.path.insert(0,plan['tokenizer_runtime'])
                binding=plan['tokenizer_artifact'];count=ArtifactTokenizer(Path(binding['tokenizer_path']),binding['tokenizer_sha256'])
                forwarder=NativeForwarder(directory/'wire',profile,ROOT/REGISTRY,budget,count)
                gateway=stack.enter_context(StudyGateway(forwarder,tools,plan_sha256=digest,trial_id=trial_id,delivery_protocol=plan['delivery_protocol']))
                def complete(messages,cap):
                    data=json.loads(forwarder.execute({'model':model,'messages':messages,'max_tokens':cap,'stream':False}))
                    choice=data['choices'][0]
                    if choice['finish_reason']!='stop' or choice['message'].get('tool_calls') or not choice['message'].get('content','').strip():
                        raise ValueError('No completed text artifact')
                    return choice['message']
            if trial['condition'] in ('A','B'):
                prompts={name:(ROOT/CASE_DIR/'prompts'/file).read_text() for name,file in [('orient_and_extract','B1-orient.md'),('draft','B2-draft.md'),('review','B3-review.md'),('revise','B4-revise.md')]}
                output=fixed_workflow(bundle,trial['condition'],prompts,directory/'stages',complete,request_output_ceiling=profile['limits']['num_predict'])
                article=output['article']
            else:
                policy={'mode':'study_replay' if plan['mode']=='offline_validation' else 'scored_trial',
                        'delivery_protocol':plan['delivery_protocol'],
                        'study_plan_sha256':digest,'trial_id':trial_id,'profile_binding_sha256':binding_sha256(profile),
                        'run_root':str(directory),'workspace':str(directory/'workspace'),'gateway':gateway.url,
                        'controller_nonce':gateway.nonce,'model':model,'context_tokens':profile['limits']['num_ctx'],
                        'request_output_ceiling':profile['limits']['num_predict'],'messages':bundle['messages'],
                        'control_prompt':(ROOT/CASE_DIR/'prompts/C-tools.md').read_text()}
                once(directory/'policy.json',policy);node=Path(plan['node_binary'])
                (directory/'sandbox.sb').write_text(build_profile(ROOT,directory,node,int(gateway.url.rsplit(':',1)[1])))
                env={'PATH':str(node.parent)+':/usr/bin:/bin','HOME':str(directory/'pi-state'),
                     'TMPDIR':str(directory/'pi-state'),'LANG':'en_US.UTF-8','PI_CODING_AGENT_DIR':str(directory/'pi-state'),'NO_COLOR':'1'}
                acceptance(ROOT,directory,node,gateway.url,gateway.nonce,env)
                # Recheck the candidate view after adversarial OS probes.
                ToolBackend(view,directory/'unused-audit',maximum_calls=1,deadline=deadline)
                ran=subprocess.run(command(directory,node,str(ROOT/'integrations/pi/writing-workflow-v0.1.mjs'),str(directory/'policy.json')),
                                   cwd=directory/'workspace',env=env,capture_output=True,text=True,
                                   timeout=max(.001,deadline-time.monotonic()))
                (directory/'pi.stdout').write_text(ran.stdout);(directory/'pi.stderr').write_text(ran.stderr)
                if ran.returncode or not tools.submitted:raise ValueError('Pi did not deliver an accepted final article')
                result['delivery_kind']=tools.delivery_kind
                article=(directory/'workspace/output/article.md').read_text()
            if budget.poisoned or time.monotonic()>=deadline:raise ValueError('Controller closed before final delivery')
            with (directory/'article.md').open('x') as out:out.write(article)
            result.update(status='complete',final_available=True,article_sha256=sha(directory/'article.md'))
    except Exception as exc:
        result.update(status='failed',error={'type':type(exc).__name__,'message':str(exc)})
    finally:
        result.update(budget=budget.snapshot(),finished_at=utc_now())
        save(directory/'worker-result.json',result)
    return 0 if result['status']=='complete' else 1


def journal_rows(directory: Path) -> list:
    rows=[]
    for file in sorted((directory/'wire').glob('request-*.json')):
        if file.name.endswith('.partial-message.json'):continue
        row=load(file);row['journal_file']=file.name
        raw=file.with_suffix('.native.ndjson')
        if not raw.exists():raw=file.with_suffix('.native-response')
        if raw.exists():
            converter=NativeResponse(row['request'],row['sequence'])
            for line in raw.read_bytes().splitlines(keepends=True):
                if not line.endswith(b'\n'):break
                try:converter.feed(json.loads(line))
                except (ValueError,KeyError,TypeError):break
            row['recovered_message']=converter.message
            if converter.done and converter.usage:
                row['usage']=converter.usage
                row['recovered_finish_reason']=converter.finish_reason
        rows.append(row)
    return rows


def delivered_final(directory: Path, trial: dict, rows: list, tools: list, deadline: float):
    """Only the designated final response/submission; never rank saved drafts."""
    if trial['condition']=='C':
        accepted=[t for t in tools if t['tool']=='submit_article' and t.get('ok')
                  and t.get('result',{}).get('accepted') is True
                  and t.get('finished_monotonic',float('inf'))<=deadline]
        file=directory/'workspace/output/article.md'
        receipt_path=directory/'final-delivery.json';policy_path=directory/'policy.json'
        if receipt_path.exists() and policy_path.exists() and load(policy_path).get('delivery_protocol')==PROTOCOL:
            receipt=load(receipt_path)
            if (accepted or not rows or not file.is_file() or receipt.get('delivery_protocol')!=PROTOCOL
                    or receipt.get('delivery_kind')!='assistant_final_text' or receipt.get('accepted') is not True
                    or receipt.get('accepted_monotonic',float('inf'))>=deadline
                    or receipt.get('sha256')!=sha(file)):return None
            last=rows[-1];message=last.get('recovered_message',{})
            journal=directory/'wire'/last['journal_file']
            native=journal.with_suffix('.native.ndjson')
            if not native.exists():native=journal.with_suffix('.native-response')
            if (last.get('status')!='complete' or last.get('finish_reason')!='stop' or message.get('tool_calls')
                    or last.get('finished_monotonic',float('inf'))>=deadline
                    or receipt.get('response_id')!='ollama-native-'+str(last['sequence'])
                    or receipt.get('request_sequence')!=last['sequence']
                    or receipt.get('request_journal_sha256')!=sha(journal)
                    or not native.is_file() or receipt.get('native_response_sha256')!=sha(native)
                    or message.get('content','').encode()!=file.read_bytes()):return None
            return file.read_bytes()
        if len(accepted)!=1 or not file.is_file() or sha(file)!=accepted[0]['result']['sha256']:return None
        return file.read_bytes()
    expected=1 if trial['condition']=='A' else 4
    if len(rows)!=expected:return None
    last=rows[-1]
    if (last.get('status')!='complete' or last.get('finish_reason')!='stop'
            or last.get('finished_monotonic',float('inf'))>deadline):return None
    content=last.get('recovered_message',{}).get('content','')
    return content.encode() if isinstance(content,str) and content.strip() else None


def tool_rows(path: Path):
    rows=[]
    if not path.exists():return rows,True
    for line in path.read_bytes().splitlines(keepends=True):
        if not line.endswith(b'\n'):return rows,False
        try:rows.append(json.loads(line))
        except (ValueError,TypeError):return rows,False
    return rows,True


def inspect_trial(directory: Path, trial: dict, watch: dict, *, mode: str) -> dict:
    result=load(directory/'worker-result.json') if (directory/'worker-result.json').exists() else {'status':'interrupted','final_available':False}
    rows=journal_rows(directory)
    # Recovery preserves both usage and diagnostic content; only the specified
    # final request or accepted submission can supply an evaluation artifact.
    save(directory/'recovered-journal.json',{'requests':rows})
    limit=[]
    if watch['timed_out']:limit.append('time')
    for row in rows:
        error=row.get('error',{}).get('type') or row.get('error_type')
        if error=='ContextExhausted':limit.append('context')
        if error=='BudgetExhausted':limit.append('model_call_guard')
        if row.get('finish_reason')=='length' or row.get('recovered_finish_reason')=='length':limit.append('request_output')
    tools,tools_complete=tool_rows(directory/'tools.jsonl')
    if trial['condition']=='C' and result['status']=='interrupted':tools_complete=False
    if trial['maximum_tool_attempts'] and len(tools)>trial['maximum_tool_attempts']:limit.append('tool_guard')
    actual=[r for r in rows if r.get('forwarded') or r.get('status') in ('responding','complete') or 'effective_request'in r]
    known=[r['usage'] for r in actual if isinstance(r.get('usage'),dict)]
    complete_usage=len(known)==len(actual)
    healthy=watch['cleanup_finished'] and not watch.get('monitor_error') and not watch.get('deadline_cleanup_error')
    final=delivered_final(directory,trial,rows,tools,watch['deadline_monotonic'])
    if final is not None:
        destination=directory/'delivered-article.md'
        if destination.exists():
            if destination.read_bytes()!=final:raise ValueError('Delivered artifact drift')
        else:
            with destination.open('xb') as out:out.write(final)
    completed=result['status']=='complete' and final is not None and watch['returncode']==0 and not watch['timed_out'] and healthy
    return {'trial_id':trial['trial_id'],'condition':trial['condition'],'seed':trial['seed'],'mode':mode,
            'status':'complete' if completed else 'resource_limited' if limit else 'technical_failure',
            'limit_flags':sorted(set(limit)),'watchdog':watch,'worker':result,
            'final_available':final is not None,'final_sha256':hashlib.sha256(final).hexdigest() if final is not None else None,
            'generation_attempts':len(actual),'tool_attempts':len(tools) if tools_complete else None,
            'known_tool_attempts':len(tools),'tool_audit_complete':tools_complete,
            'tool_admitted_attempts':min(len(tools),trial['maximum_tool_attempts']),
            'tool_rejected_after_guard':max(0,len(tools)-trial['maximum_tool_attempts']),
            'usage_complete':complete_usage,
            'known_generated_tokens':sum(x['completion_tokens'] for x in known),
            'actual_generated_tokens':sum(x['completion_tokens'] for x in known) if complete_usage else None,
            'actual_input_tokens':sum(x['prompt_tokens'] for x in known) if complete_usage else None,
            'allow_continuation':healthy and (completed or bool(limit))}


def postflight(profile: dict) -> dict:
    client=LocalClient(timeout_seconds=15);before=client.list_running_models();unloads=[]
    for model in before.get('models',[]):
        if model['name']==profile['candidate']['model'] and model['digest']==profile['candidate']['model_digest']:
            unloads.append(client.unload_model(model['name']))
    after=client.list_running_models()
    return {'before':before,'unloads':unloads,'after':after,'clean':after.get('models')==[]}


def execute(study: Path, digest: str, *, offline=False) -> dict:
    study=study_path(study);plan=verify_plan(study,digest,require_approval=not offline)
    if offline!=(plan['mode']=='offline_validation'):raise ValueError('Execution mode mismatch')
    once(study/'execution-started.json',{'at':utc_now(),'study_plan_sha256':digest,'mode':plan['mode']})
    state={'mode':plan['mode'],'status':'running','study_plan_sha256':digest,'trials':[],'actual_ollama_generations':0 if offline else None}
    awake=None
    try:
        if not offline:
            awake=subprocess.Popen(['/usr/bin/caffeinate','-i','-w',str(os.getpid())],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            once(study/'awake-helper.json',{'executor_pid':os.getpid(),'helper_pid':awake.pid,'command':['/usr/bin/caffeinate','-i','-w',str(os.getpid())],'temporary':True,'started_at':utc_now()})
        for trial in plan['trials']:
            verify_plan(study,digest,require_approval=not offline)
            directory=study/'trials'/trial['trial_id'];directory.mkdir(parents=True,exist_ok=False)
            imported=plan['reused_trials'].get(trial['trial_id'])
            if imported:
                prior=Path(imported['prior_study'])/'trials'/trial['trial_id']
                article=(prior/'delivered-article.md').read_bytes()
                if hashlib.sha256(article).hexdigest()!=imported['final_sha256']:raise ValueError('Imported final drift')
                (directory/'delivered-article.md').write_bytes(article)
                once(directory/'import.json',imported)
                record={'trial_id':trial['trial_id'],'condition':trial['condition'],'seed':trial['seed'],
                        'mode':plan['mode'],'status':'reused_complete','final_available':True,
                        'final_sha256':imported['final_sha256'],'generation_attempts':0,'allow_continuation':True,
                        'historical_generation_attempts':imported['historical_generation_attempts'],'provenance':imported,
                        'costs':'No new generation. Original tokens/timing/tool counts remain in prior record; not zero-cost original evidence.'}
                once(directory/'record.json',record);state['trials'].append(record);save(study/'progress.json',state)
                continue
            if not offline:
                profile=trial['profile'];client=LocalClient(timeout_seconds=5)
                gate=run_resource_gate({'resource_gate':plan['resource_gate'],
                    'runtime':{'version':profile['candidate']['ollama_version']},
                    'deployment':{'name':profile['candidate']['model'],'digest':profile['candidate']['model_digest']}},client=client)
                save(directory/'resource-gate.json',gate)
            once(directory/'started.json',{'at':utc_now(),'study_plan_sha256':digest,'trial_id':trial['trial_id']})
            monitor=None
            if not offline:
                def monitor():
                    observation=activity(client,trial['profile']['candidate']['model'],plan['resource_gate']['blocking_process_rules'],tolerate_transport=True)
                    with (directory/'resource-monitor.jsonl').open('a') as out:out.write(json.dumps(observation)+'\n')
            watch=None
            try:
                watch=run_bounded([plan['python_binary'],'-B','-m','local_llm_benchmark.writing_workflow_study','worker','--study',str(study),'--plan-sha256',digest,'--trial',trial['trial_id']],
                                  directory/'watchdog',seconds=plan['trial_seconds'],monitor=monitor)
            finally:
                if not offline:
                    try:cleanup=postflight(trial['profile'])
                    except Exception as exc:cleanup={'clean':False,'error':{'type':type(exc).__name__,'message':str(exc)}}
                    save(directory/'backend-postflight.json',cleanup)
            record=inspect_trial(directory,trial,watch,mode=plan['mode'])
            if not offline and not cleanup['clean']:record['allow_continuation']=False
            save(directory/'record.json',record);state['trials'].append(record);save(study/'progress.json',state)
            verify_plan(study,digest,require_approval=not offline)
            if not record['allow_continuation']:raise RuntimeError('Trial failed safely; study stopped without retry')
        state['status']='complete'
    except Exception as exc:
        state.update(status='stopped',error={'type':type(exc).__name__,'message':str(exc)})
    finally:
        if awake is not None:
            awake.terminate();awake.wait(timeout=5)
            once(study/'awake-helper-ended.json',{'at':utc_now(),'returncode':awake.returncode})
        recorded={r['trial_id'] for r in state['trials']}
        for trial in plan['trials']:
            directory=study/'trials'/trial['trial_id']
            if trial['trial_id'] not in recorded and (directory/'started.json').exists():
                path=directory/'watchdog/watchdog.json'
                watch=load(path) if path.exists() else {'timed_out':False,'cleanup_finished':False,'returncode':None,'deadline_monotonic':0}
                recovered=inspect_trial(directory,trial,watch,mode=plan['mode'])
                recovered['allow_continuation']=False
                save(directory/'record.json',recovered);state['trials'].append(recovered)
        state.update(finished_at=utc_now(),trials_consumed=len(state['trials']),
            reused_trials=sum(r['status']=='reused_complete' for r in state['trials']),
            newly_executed_trials=sum(r['status']!='reused_complete' for r in state['trials']),
            historical_reused_generation_attempts=sum(r.get('historical_generation_attempts',0) for r in state['trials']),
            finals_available=sum(x['final_available'] for x in state['trials']),
            generation_attempts=sum(x['generation_attempts'] for x in state['trials']))
        if not offline:state['actual_ollama_generations']=state['generation_attempts']
        save(study/'execution-closeout.json',state)
        once(study/'execution-frozen.json',{'at':utc_now(),'study_plan_sha256':digest,
            'artifacts_sha256':{str(p.relative_to(study)):sha(p) for p in sorted((study/'trials').rglob('*')) if p.is_file()}})
    return state


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--study',type=Path,required=True);p.add_argument('--offline-validation',action='store_true');p.add_argument('--validated-replay',type=Path);p.add_argument('--reuse-from',type=Path)
    for name in ['execute','replay','worker']:
        p=sub.add_parser(name);p.add_argument('--study',type=Path,required=True);p.add_argument('--plan-sha256',required=True)
        if name=='worker':p.add_argument('--trial',required=True)
    args=parser.parse_args(argv)
    if args.command=='prepare':result=prepare(args.study,mode='offline_validation' if args.offline_validation else 'live_study',validated_replay=args.validated_replay,reuse_from=args.reuse_from)
    elif args.command=='worker':return worker(args.study,args.plan_sha256,args.trial)
    else:result=execute(args.study,args.plan_sha256,offline=args.command=='replay')
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result.get('status','complete')=='complete' else 1

if __name__=='__main__':raise SystemExit(main())
