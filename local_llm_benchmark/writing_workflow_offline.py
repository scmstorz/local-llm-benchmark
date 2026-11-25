"""Offline-only gateway/driver for replay qualification of writing workflows.

There is deliberately no Ollama/upstream option. Synthetic responders test the
real Pi transport, native translation, tools and shared budget, not text quality.
"""
from __future__ import annotations
from contextlib import AbstractContextManager
import copy,json,threading,time,urllib.request,urllib.parse,urllib.error,secrets
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from .external_cli_native import NativeResponse,stub_native
from .profiled_native import native_request
from .generation_budget import GenerationBudget
from .writing_workflow import ToolBackend
from .model_profiles import REGISTRY, binding_sha256
from .writing_workflow_delivery import LEGACY, PROTOCOL, accept_regular_final


class OfflineGateway(AbstractContextManager):
    def __init__(self,directory:Path,profile:dict,budget:GenerationBudget,tools:ToolBackend,responder,*,registry_path=REGISTRY,study_binding=None,delivery_protocol=LEGACY):
        if delivery_protocol not in (LEGACY,PROTOCOL):raise ValueError('Unsupported delivery protocol')
        self.delivery_protocol=delivery_protocol
        self.directory=directory;directory.mkdir(parents=True,exist_ok=False)
        self.profile=copy.deepcopy(profile);self.budget=budget;self.tools=tools;self.responder=responder
        self.registry_path=registry_path;self.study_binding=study_binding or {}
        self.requests=[];self.lock=threading.Lock();self.nonce=secrets.token_hex(24);owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                if self.path!='/offline-identity':self.reply(404,b'{}','application/json');return
                self.reply(200,json.dumps({'mode':'synthetic_only','controller_nonce':owner.nonce,'delivery_protocol':owner.delivery_protocol,'profile_binding_sha256':binding_sha256(owner.profile),**owner.study_binding}).encode(),'application/json')
            def do_POST(self):
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=4*1024*1024:raise ValueError('Invalid body size')
                    payload=json.loads(self.rfile.read(length))
                    if self.path=='/final-response' and owner.delivery_protocol==PROTOCOL:
                        with owner.lock:result=accept_regular_final(owner.directory,owner.tools,owner.budget,payload)
                        self.reply(200,json.dumps(result).encode(),'application/json');return
                    if self.path.startswith('/tool/'):
                        if owner.budget.poisoned:raise ValueError('Controller closed')
                        try:result=owner.tools.execute(self.path.removeprefix('/tool/'),payload)
                        except Exception:
                            if owner.tools.calls>owner.tools.maximum_calls or time.monotonic()>=owner.tools.deadline:
                                with owner.budget.lock:owner.budget.poisoned=True
                            raise
                        self.reply(200,json.dumps(result,ensure_ascii=False).encode(),'application/json');return
                    if self.path!='/v1/chat/completions':raise ValueError('Unsupported endpoint')
                    with owner.lock:
                        if owner.tools.submitted:raise ValueError('Final article already delivered')
                        seq=len(owner.requests)+1;entry={'sequence':seq,'request':payload,'mode':'synthetic_only','status':'validating','started_monotonic':time.monotonic()};owner.requests.append(entry)
                        path=owner.directory/f'request-{seq:04d}'
                        path.with_suffix('.json').write_text(json.dumps(entry)+'\n')
                    path=owner.directory/f'request-{seq:04d}';reserved=False
                    try:
                        condition=copy.deepcopy(owner.profile)
                        effective,audit=native_request(payload,condition,registry_path=owner.registry_path)
                        cap=owner.budget.begin(effective['options']['num_predict'],seq);reserved=True
                        condition['limits']['num_predict']=cap;effective,audit=native_request(payload,condition,registry_path=owner.registry_path)
                        entry.update(effective_request=effective,profile_audit=audit,status='responding')
                        response=copy.deepcopy(owner.responder(payload,seq))
                        if not isinstance(response.get('usage'),dict):raise ValueError('Synthetic fixture must declare authoritative usage')
                        native=stub_native(payload,response);path.with_suffix('.native-response').write_bytes(native);converter=NativeResponse(payload,seq);output=[]
                        for line in native.splitlines():output.append(converter.feed(json.loads(line)))
                        output.append(converter.finish());wire=b''.join(output)
                        # Complete accounting before exposing a terminal frame to Pi.
                        owner.budget.finish(seq,converter.usage,complete=True);reserved=False
                        if owner.budget.poisoned:raise ValueError('Synthetic backend violated budget')
                        entry.update(status='complete',usage=converter.usage,finish_reason=converter.finish_reason)
                        path.with_suffix('.native-response').write_bytes(native);path.with_suffix('.client-response').write_bytes(wire)
                        entry['budget_after']=owner.budget.snapshot();entry['finished_monotonic']=time.monotonic()
                        path.with_suffix('.json').write_text(json.dumps(entry,ensure_ascii=False,indent=2)+'\n')
                        self.reply(200,wire,'text/event-stream' if payload.get('stream') else 'application/json')
                    except Exception as exc:
                        entry.update(status='failed',error_type=type(exc).__name__);raise
                    finally:
                        if reserved:owner.budget.finish(seq,None,complete=False)
                        if entry.get('status')!='complete':
                            entry['budget_after']=owner.budget.snapshot();entry['finished_monotonic']=time.monotonic()
                            path.with_suffix('.json').write_text(json.dumps(entry,ensure_ascii=False,indent=2)+'\n')
                except Exception as exc:
                    self.reply(400,json.dumps({'error':{'message':'Offline fixture request rejected','type':type(exc).__name__}}).encode(),'application/json')
            def reply(self,status,body,mime):
                self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)));self.end_headers()
                try:self.wfile.write(body)
                except (BrokenPipeError,ConnectionResetError):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
    @property
    def url(self):return f'http://127.0.0.1:{self.server.server_address[1]}'
    def __enter__(self):self.thread.start();return self
    def __exit__(self,*args):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)
        (self.directory/'summary.json').write_text(json.dumps({'mode':'synthetic_only','ollama_requests':0,'requests':self.requests,'budget':self.budget.snapshot()},ensure_ascii=False,indent=2)+'\n')


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,file_pointer,code,message,headers,new_url):
        raise ValueError('Offline fixture redirects are forbidden')


def complete_via_gateway(url:str,model:str,messages:list,max_tokens:int)->dict:
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment or not parsed.port or parsed.port==11434:
        raise ValueError('Only explicit loopback fixture transport supported')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),_NoRedirect())
    with opener.open(url+'/offline-identity',timeout=5) as identity:
        if json.load(identity).get('mode')!='synthetic_only':raise ValueError('Not an offline fixture controller')
    request=urllib.request.Request(url+'/v1/chat/completions',data=json.dumps({'model':model,'messages':messages,'max_tokens':max_tokens,'stream':False}).encode(),headers={'Content-Type':'application/json'})
    try:
        with opener.open(request,timeout=10) as response:result=json.load(response)
    except urllib.error.HTTPError as exc:
        exc.read();exc.close();raise
    choice=result['choices'][0]
    if choice['finish_reason']!='stop' or choice['message'].get('tool_calls') or not choice['message'].get('content','').strip():raise ValueError('No completed text artifact')
    return choice['message']


def fixed_workflow(bundle:dict,condition:str,prompts:dict,output:Path,complete,*,request_output_ceiling:int):
    """Execute A/B with an explicitly supplied profile ceiling, no stage rationing.

    Live context admission remains the transport's responsibility. This offline
    prototype neither infers a model limit nor silently trims source/history.
    """
    if condition not in ('A','B'):raise ValueError('Expected direct/fixed condition')
    if type(request_output_ceiling)is not int or request_output_ceiling<1:
        raise ValueError('Explicit qualified per-request output ceiling required')
    output.mkdir(parents=True,exist_ok=False);history={};steps=[]
    stages=['article'] if condition=='A' else ['orient_and_extract','draft','review','revise']
    dependencies={'orient_and_extract':[],'draft':['orient_and_extract'],'review':['orient_and_extract','draft'],'revise':['draft','review']}
    for stage in stages:
        messages=copy.deepcopy(bundle['messages']);cap=request_output_ceiling
        if condition=='B':
            text=prompts[stage]
            for prior in dependencies[stage]:text+='\n\nVORGÄNGERARTEFAKT '+prior+'\n'+history[prior]
            messages.append({'role':'user','content':text})
        (output/(stage+'-input.json')).write_text(json.dumps(messages,ensure_ascii=False,indent=2)+'\n')
        result=complete(messages,cap);history[stage]=result['content']
        (output/(stage+'.md')).write_text(result['content']);steps.append(stage)
    final=history[stages[-1]]
    with (output/'article-final.md').open('x') as out:out.write(final)
    return {'stages':steps,'article':final,'previous_drafts_selected':False}
