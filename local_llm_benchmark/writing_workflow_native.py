"""Native forwarding for bounded technical writing-workflow qualification.

No scored-study entrypoint. Only a pinned local Ollama deployment is admitted.
The caller must supply a qualified exact context oracle and own a parent process
watchdog and resource gate. Metadata/rendering requests are recorded separately.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import threading
import time
import urllib.request
from contextlib import AbstractContextManager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import secrets
import re

from .calibration_run import LocalClient, UPSTREAM, save
from .external_cli_native import NativeResponse
from .model_profiles import validate_deployment, binding_sha256
from .profiled_native import native_request
from .workflow_context import ContextAdmission
from .writing_workflow_delivery import LEGACY, PROTOCOL, accept_regular_final


class NativeForwarder:
    def __init__(self, directory: Path, profile: dict, registry: Path, budget, count,
                 *, client=None):
        directory.mkdir(parents=True, exist_ok=False)
        self.directory, self.profile, self.registry = directory, copy.deepcopy(profile), registry
        self.budget, self.client = budget, client or LocalClient(timeout_seconds=120)
        self.context = ContextAdmission(self.render, count, context_tokens=profile['limits']['num_ctx'])
        self.sequence = 0
        self.lock = threading.Lock()
        self.generation_attempts = 0

    def render(self, request):
        return self.client._request_json('POST', '/api/chat', request)

    def verify_deployment(self):
        model = self.profile['candidate']['model']
        meta = {'runtime': self.client.version(),
                'tag': next((t for t in self.client.list_models()['models'] if t['name'] == model), {}),
                'show': self.client.show_model(model), 'running': self.client.list_running_models()}
        receipt = validate_deployment(self.profile, tag=meta['tag'], show=meta['show'],
                                      runtime=meta['runtime'], registry_path=self.registry)
        expected = self.profile['candidate']
        if (meta['show'].get('renderer') != expected.get('renderer')
                or meta['show'].get('parser') != expected.get('parser')
                or expected.get('renderer') != 'gemma4-large' or expected.get('parser') != 'gemma4'):
            raise ValueError('Bound Gemma renderer/parser identity drift')
        if any(m.get('name') != model or m.get('digest') != self.profile['candidate']['model_digest']
               for m in meta['running'].get('models', [])):
            raise ValueError('Unexpected model residency; resource gate required')
        return meta, receipt

    def execute(self, payload: dict, *, start_stream=None, send_chunk=None):
        # One whole request includes metadata/rendering and generation. No hidden
        # compaction or extra generation may enter concurrently through this port.
        if not self.lock.acquire(blocking=False):
            raise ValueError('Concurrent model request is not admitted')
        self.sequence += 1
        path = self.directory/f'request-{self.sequence:04d}'
        entry = {'sequence': self.sequence, 'request': payload, 'status': 'admission',
                 'profile_binding_sha256': binding_sha256(self.profile), 'forwarded': False}
        reserved = False
        converter = NativeResponse(payload, self.sequence)
        started = time.monotonic()
        entry['started_monotonic'] = started
        terminal = None
        terminal_data = b''
        try:
            if self.budget.poisoned or time.monotonic() >= self.budget.deadline:
                raise ValueError('Whole-trial controller closed')
            native, profile_audit = native_request(payload, self.profile, registry_path=self.registry)
            meta, deployment = self.verify_deployment()
            entry.update(metadata=meta, deployment=deployment, profile_audit=profile_audit)
            native, context = self.context.admit(native)
            # Debug rendering can load a runner, so check actual residency/window
            # again before sending a generation, not just architecture metadata.
            running = self.client.list_running_models()
            expected = self.profile['candidate']
            observed = [m.get('context_length') for m in running.get('models', [])
                        if m.get('name') == expected['model'] and m.get('digest') == expected['model_digest']]
            if observed != [self.profile['limits']['num_ctx']] or len(running.get('models', [])) != 1:
                raise ValueError('Configured runner context/residency drift')
            cap = self.budget.begin(native['options']['num_predict'], self.sequence)
            reserved = True
            native['options']['num_predict'] = cap
            entry.update(effective_request=native, context=context, status='generating', forwarded=True)
            save(path.with_suffix('.json'), entry)
            request = urllib.request.Request(UPSTREAM+'/api/chat', json.dumps(native).encode(),
                                             {'Content-Type': 'application/json'})
            self.generation_attempts += 1
            with self.client.opener.open(request, timeout=max(1, self.budget.deadline-time.monotonic())) as response:
                if payload.get('stream') and start_stream:
                    start_stream()
                with path.with_suffix('.native.ndjson').open('xb', buffering=0) as sink, path.with_suffix('.client-wire').open('xb', buffering=0) as wire:
                    pending = b''
                    while chunk := response.read1(65536):
                        sink.write(chunk)
                        pending += chunk
                        while b'\n' in pending:
                            line, pending = pending.split(b'\n', 1)
                            if not line.strip():
                                continue
                            if len(line) > 8*1024*1024:
                                raise ValueError('Oversized native event')
                            item = json.loads(line)
                            data = converter.feed(item)
                            if item.get('done'):
                                terminal = item
                                # Finish accounting before the terminal frame can
                                # trigger Pi's next tool/model turn.
                                self.budget.finish(self.sequence, converter.usage, complete=True)
                                reserved = False
                                entry['usage'] = converter.usage
                                if converter.usage['prompt_tokens'] != context['input_tokens']:
                                    raise ValueError('Actual prompt count differs from exact admission')
                                if converter.usage['prompt_tokens']+converter.usage['completion_tokens'] > self.profile['limits']['num_ctx']:
                                    raise ValueError('Backend exceeded admitted context')
                                if self.budget.poisoned:
                                    raise ValueError('Backend violated request/deadline bound')
                                terminal_data = data
                            else:
                                wire.write(data)
                                if data and send_chunk:
                                    send_chunk(data)
                        if len(pending) > 8*1024*1024:
                            raise ValueError('Oversized partial native event')
                    if pending.strip():
                        raise ValueError('Incomplete native NDJSON')
                    final = converter.finish()
                    final = terminal_data+final
                    wire.write(final)
            if terminal is None:
                raise ValueError('Missing terminal native event')
            entry.update(status='complete', finish_reason=converter.finish_reason,
                         thinking_characters=converter.thinking_characters,
                         terminal=terminal)
            return final
        except Exception as exc:
            entry.update(status='failed', error={'type': type(exc).__name__, 'message': str(exc)})
            if reserved:
                self.budget.finish(self.sequence, None, complete=False)
            # A context/transport/measurement failure cannot be silently retried.
            with self.budget.lock:
                self.budget.poisoned = True
            raise
        finally:
            entry.update(elapsed_seconds=time.monotonic()-started, finished_monotonic=time.monotonic(), budget_after=self.budget.snapshot())
            save(path.with_suffix('.partial-message.json'), converter.message)
            save(path.with_suffix('.json'), entry)
            self.lock.release()


class TechnicalGateway(AbstractContextManager):
    """Loopback API for explicit Pi technical probes, never a scored live trial."""
    def __init__(self, forwarder: NativeForwarder, tools, *, _study_binding=None, delivery_protocol=LEGACY):
        if delivery_protocol not in (LEGACY,PROTOCOL):raise ValueError('Unsupported delivery protocol')
        self.delivery_protocol=delivery_protocol
        self.forwarder, self.tools = forwarder, tools
        self.study_binding = _study_binding or {}
        self.identity_mode = 'local_native_study' if _study_binding else 'local_native_technical'
        self.nonce = secrets.token_hex(24)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass

            def reply(self, status, body):
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path != '/offline-identity':
                    self.reply(404, b'{}'); return
                self.reply(200, json.dumps({'mode': owner.identity_mode,
                    'controller_nonce': owner.nonce,
                    'delivery_protocol': owner.delivery_protocol,
                    'profile_binding_sha256': binding_sha256(owner.forwarder.profile),
                    **owner.study_binding}).encode())

            def do_POST(self):
                streaming = False
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 4*1024*1024:
                        raise ValueError('Invalid request size')
                    payload = json.loads(self.rfile.read(size))
                    if self.path=='/final-response' and owner.delivery_protocol==PROTOCOL:
                        with owner.forwarder.lock:
                            result=accept_regular_final(owner.forwarder.directory,owner.tools,owner.forwarder.budget,payload)
                        self.reply(200,json.dumps(result).encode());return
                    if self.path.startswith('/tool/'):
                        if owner.forwarder.budget.poisoned:
                            raise ValueError('Controller closed after an earlier failure')
                        try:
                            result = owner.tools.execute(self.path.removeprefix('/tool/'), payload)
                        except Exception:
                            if owner.tools.calls>owner.tools.maximum_calls or time.monotonic()>=owner.tools.deadline:
                                with owner.forwarder.budget.lock:owner.forwarder.budget.poisoned=True
                            raise
                        self.reply(200, json.dumps(result, ensure_ascii=False).encode()); return
                    if self.path != '/v1/chat/completions':
                        raise ValueError('Unsupported controller endpoint')
                    if owner.tools.submitted:raise ValueError('Final article already delivered')

                    def start():
                        nonlocal streaming
                        self.send_response(200)
                        self.send_header('Content-Type', 'text/event-stream')
                        self.send_header('Connection', 'close')
                        self.end_headers()
                        streaming = True

                    def send(data):
                        self.wfile.write(data); self.wfile.flush()

                    result = owner.forwarder.execute(payload, start_stream=start, send_chunk=send)
                    if streaming:
                        send(result)
                    else:
                        self.reply(200, result)
                except Exception:
                    if not streaming:
                        self.reply(400, b'{"error":{"message":"Technical controller rejected request"}}')
                    # A streaming failure ends without a fabricated DONE/success.
                    self.close_connection = True

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self): return f'http://127.0.0.1:{self.server.server_address[1]}'
    def __enter__(self): self.thread.start(); return self
    def __exit__(self, *args):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=5)


class StudyGateway(TechnicalGateway):
    """Study transport; caller must first verify the frozen plan and approval."""
    def __init__(self, forwarder, tools, *, plan_sha256: str, trial_id: str, delivery_protocol=LEGACY):
        if not re.fullmatch(r'[a-f0-9]{64}',plan_sha256) or not re.fullmatch(r't[0-9]{2}',trial_id):
            raise ValueError('Explicit frozen study/trial binding required')
        super().__init__(forwarder,tools,_study_binding={'study_plan_sha256':plan_sha256,'trial_id':trial_id},delivery_protocol=delivery_protocol)
