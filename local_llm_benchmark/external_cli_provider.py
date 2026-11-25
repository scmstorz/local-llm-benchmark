"""Loopback-only OpenAI transport journal for external CLI qualification.

Every request, including compaction or retries, crosses the same recorder.
The default gateway forwards inference settings unchanged. The opt-in native
profile explicitly translates and records both sides; it never substitutes a
model. Private wire artifacts stay outside candidate access.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
import copy
import hashlib
import http.client
import io
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import threading
import time
from typing import Any, Callable
import urllib.error
import urllib.request

from .runner import utc_now
from .external_cli_native import PROFILE, NativeResponse, native_request, stub_native
from .model_profiles import CONDITION_ID, validate_condition, validate_deployment
from .profiled_native import native_request as profiled_request


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ProviderJournal(AbstractContextManager):
    def __init__(self, directory: Path, *, model: str, port: int,
                 upstream: str | None = None,
                 responder: Callable[[dict, int], dict] | None = None,
                 timeout: float = 300, deadline: float | None = None,
                 profile: dict | None = None):
        if (upstream is None) == (responder is None):
            raise ValueError("Choose exactly one real upstream or offline responder")
        if upstream is not None and upstream != "http://127.0.0.1:11434":
            raise ValueError("Only the fixed local Ollama upstream is supported")
        self.model_profile = isinstance(profile, dict) and profile.get("profile_id") == CONDITION_ID
        if self.model_profile:
            validate_condition(profile, model)
        elif profile is not None and profile != PROFILE:
            raise ValueError("Unknown native provider profile")
        self.profile = copy.deepcopy(profile)
        self.directory, self.model = directory, model
        self.upstream, self.responder, self.timeout = upstream, responder, timeout
        self.deadline = deadline
        self.requests: list[dict[str, Any]] = []
        self.lock = threading.Lock()
        self.connections: set[Any] = set()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(5)

            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path != "/v1/models":
                    self.send_error(404)
                    return
                self.reply(200, {"object": "list", "data": [
                    {"id": owner.model, "object": "model", "owned_by": "local"}
                ]})

            def reply(self, status, value):
                body = json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                with owner.lock:
                    sequence = len(owner.requests) + 1
                    entry = {"sequence": sequence, "path": self.path,
                             "started_at": utc_now(), "status": "started"}
                    owner.requests.append(entry)
                prefix = owner.directory / f"request-{sequence:04d}"
                response_started = False
                upstream_response = None
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 8 * 1024 * 1024:
                        raise ValueError("Invalid request length")
                    raw = self.rfile.read(length)
                    prefix.with_suffix(".json").write_bytes(raw)
                    payload = json.loads(raw)
                    if not isinstance(payload, dict):
                        raise ValueError("Expected a JSON object")
                    entry["request_sha256"] = hashlib.sha256(raw).hexdigest()
                    entry["model"] = payload.get("model")
                    entry["stream"] = payload.get("stream", False)
                    entry["settings"] = {k: v for k, v in payload.items()
                                         if k not in {"messages", "tools", "functions"}}
                    if self.path != "/v1/chat/completions" or payload.get("model") != owner.model:
                        entry["status"] = "rejected_model_or_endpoint"
                        self.reply(403, {"error": {"message": "Unbound model or endpoint"}})
                        return
                    upstream_raw, upstream_path = raw, self.path
                    if owner.profile is not None:
                        if owner.model_profile:
                            effective, audit = profiled_request(payload, owner.profile)
                            entry["profile_audit"] = audit
                        else:
                            effective = native_request(payload, owner.profile)
                        upstream_raw = json.dumps(effective, ensure_ascii=False).encode()
                        upstream_path = "/api/chat"
                        prefix.with_suffix(".upstream.json").write_bytes(upstream_raw)
                        entry.update(provider_profile=owner.profile["profile_id"],
                                     upstream_path=upstream_path,
                                     upstream_request_sha256=hashlib.sha256(upstream_raw).hexdigest(),
                                     effective_settings={k: v for k, v in effective.items()
                                                         if k not in {"messages", "tools"}})
                    started = time.monotonic()
                    if owner.responder is not None:
                        response = owner.responder(payload, sequence)
                        if owner.profile is not None:
                            native = stub_native(payload, response)
                            data = owner._translate_native(io.BytesIO(native), payload, sequence, prefix, entry)
                        else:
                            data = owner._encode_response(payload, response)
                        content_type = "text/event-stream" if payload.get("stream") else "application/json"
                        self.send_response(200)
                        self.send_header("Content-Type", content_type)
                        self.send_header("Content-Length", str(len(data)))
                        self.end_headers()
                        response_started = True
                        self.wfile.write(data)
                        prefix.with_suffix(".response").write_bytes(data)
                        entry["usage"] = owner._usage(prefix.with_suffix(".response"))
                    else:
                        remaining = owner.timeout if owner.deadline is None else owner.deadline-time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError("Parent deadline reached before upstream request")
                        request = urllib.request.Request(owner.upstream + upstream_path, upstream_raw,
                                                         {"Content-Type": "application/json"})
                        entry["forwarded_to_ollama"] = True
                        try:
                            response = owner.opener.open(request, timeout=min(owner.timeout, remaining))
                            upstream_response = response
                        except urllib.error.HTTPError as exc:
                            body = exc.read()
                            prefix.with_suffix(".response").write_bytes(body)
                            if owner.profile is not None:
                                prefix.with_suffix(".upstream.response").write_bytes(body)
                            entry.update(status="upstream_http_error", upstream_status=exc.code)
                            self.send_response(exc.code)
                            self.send_header("Content-Type", "application/json")
                            self.send_header("Content-Length", str(len(body)))
                            self.end_headers()
                            response_started = True
                            self.wfile.write(body)
                            exc.close()
                            return
                        with response:
                            with owner.lock:
                                owner.connections.add(response)
                            self.send_response(response.status)
                            content_type = ("text/event-stream" if payload.get("stream") else "application/json") if owner.profile is not None else response.headers.get("Content-Type", "application/json")
                            self.send_header("Content-Type", content_type)
                            self.end_headers()
                            response_started = True
                            if owner.profile is not None:
                                def emit(chunk):
                                    self.wfile.write(chunk)
                                    self.wfile.flush()
                                owner._translate_native(response, payload, sequence, prefix, entry, emit)
                            else:
                                with prefix.with_suffix(".response").open("wb") as sink:
                                    while chunk := response.read1(8192):
                                        sink.write(chunk)
                                        self.wfile.write(chunk)
                                        self.wfile.flush()
                        entry["usage"] = owner._usage(prefix.with_suffix(".response"))
                    entry.update(status="complete", wall_time_seconds=time.monotonic()-started)
                except (ValueError, TypeError, KeyError, OSError, urllib.error.URLError, http.client.HTTPException) as exc:
                    entry.update(status="transport_error", error=type(exc).__name__)
                    if response_started:
                        self.close_connection = True
                    else:
                        try:
                            self.reply(502, {"error": {"message": "Local provider transport failed"}})
                        except OSError:
                            pass
                finally:
                    entry["finished_at"] = utc_now()
                    with owner.lock:
                        if upstream_response is not None:
                            owner.connections.discard(upstream_response)
                        owner._save()

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.server.daemon_threads = False
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @staticmethod
    def _translate_native(response, payload, sequence, prefix, entry, emit=None):
        converter = NativeResponse(payload, sequence)
        collected = []
        with prefix.with_suffix(".upstream.response").open("wb") as native_sink, prefix.with_suffix(".response").open("wb") as client_sink:
            def output(data):
                client_sink.write(data)
                if emit is None:
                    collected.append(data)
                elif data:
                    emit(data)
            while True:
                try:
                    line = response.readline(8 * 1024 * 1024 + 1)
                except http.client.IncompleteRead as exc:
                    native_sink.write(exc.partial)
                    raise
                if not line:
                    break
                native_sink.write(line)
                if len(line) > 8 * 1024 * 1024 or not line.endswith(b"\n"):
                    raise ValueError("Invalid native NDJSON framing")
                item = json.loads(line)
                if "profile_audit" in entry and isinstance(item, dict) and item.get("error"):
                    entry["backend_error"] = item["error"]
                output(converter.feed(item))
            output(converter.finish())
        entry.update(usage=converter.usage, backend_done=True,
                     backend_finish_reason=converter.finish_reason,
                     observed_thinking_characters=converter.thinking_characters,
                     generation_conformant=(entry["effective_settings"]["think"] is not False
                                            or converter.thinking_characters == 0)
                     and converter.usage["completion_tokens"] <= entry["effective_settings"]["options"]["num_predict"])
        if "profile_audit" in entry:
            options = entry["effective_settings"]["options"]
            margin = options["num_ctx"]-converter.usage["prompt_tokens"]-options["num_predict"]
            entry["capacity_audit"] = {"observed_prompt_tokens": converter.usage["prompt_tokens"],
                                       "reserved_output_tokens": options["num_predict"],
                                       "context_tokens": options["num_ctx"],
                                       "reserve_margin_tokens": margin,
                                       "output_reserve_fits": margin >= 0}
        return b"".join(collected)

    @staticmethod
    def _encode_response(payload: dict, response: dict) -> bytes:
        message = {"role": "assistant", **response.get("message", {"content": "offline transport qualified"})}
        reason = "tool_calls" if message.get("tool_calls") else "stop"
        common = {"id": "offline-qualification", "created": 0, "model": payload["model"]}
        usage = response.get("usage", {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})
        if not payload.get("stream"):
            return json.dumps({**common, "object": "chat.completion", "choices": [
                {"index": 0, "message": message, "finish_reason": reason}], "usage": usage}).encode()
        delta = dict(message)
        if "tool_calls" in delta:
            delta["tool_calls"] = [{"index": i, **call} for i, call in enumerate(delta["tool_calls"])]
        events = [
            {**common, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
            {**common, "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {}, "finish_reason": reason}], "usage": usage},
        ]
        return ("".join("data: " + json.dumps(event) + "\n\n" for event in events) + "data: [DONE]\n\n").encode()

    @staticmethod
    def _usage(path: Path) -> dict | None:
        raw = path.read_text(errors="replace")
        try:
            return json.loads(raw).get("usage")
        except ValueError:
            usage = None
            for line in raw.splitlines():
                if line.startswith("data: ") and line[6:] != "[DONE]":
                    try:
                        usage = json.loads(line[6:]).get("usage") or usage
                    except ValueError:
                        pass
            return usage

    def _save(self):
        (self.directory / "journal.json").write_text(json.dumps(self.requests, indent=2) + "\n")

    def __enter__(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.model_profile:
            (self.directory/"provider-condition.json").write_text(json.dumps(self.profile, indent=2)+"\n")
            if self.upstream is not None:
                try:
                    self._admit_model_profile()
                except Exception:
                    self.server.server_close()
                    raise
        self.thread.start()
        return self

    def _admit_model_profile(self):
        """Metadata only: reject drift/unsupported thinking before a generation."""
        def query(path, value=None):
            remaining = self.timeout if self.deadline is None else self.deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Parent deadline reached before metadata admission")
            request = urllib.request.Request(self.upstream+path,
                json.dumps(value).encode() if value is not None else None,
                {"Content-Type": "application/json"})
            with self.opener.open(request, timeout=min(10, remaining)) as response:
                result = json.load(response)
            if not isinstance(result, dict) or result.get("error"):
                raise ValueError("Invalid metadata response")
            return result
        runtime = query("/api/version")
        tags = query("/api/tags")
        tag = next((m for m in tags.get("models", []) if m.get("name") == self.model), {})
        show = query("/api/show", {"model": self.model})
        proof = {"runtime": runtime, "tag": tag, "show": show}
        (self.directory/"deployment-metadata.json").write_text(json.dumps(proof, indent=2)+"\n")
        proof = validate_deployment(self.profile, tag=tag, show=show, runtime=runtime)
        (self.directory/"deployment-admission.json").write_text(json.dumps(proof, indent=2)+"\n")

    def __exit__(self, *exc):
        self.server.shutdown()
        # Closing a timed-out CLI must also interrupt an outstanding local
        # provider read before its wire evidence is frozen.
        with self.lock:
            for response in list(self.connections):
                try:
                    response.fp.raw._sock.shutdown(socket.SHUT_RDWR)
                except (AttributeError, OSError):
                    pass
        self.server.server_close()
        self.thread.join(timeout=5)
        self._save()
