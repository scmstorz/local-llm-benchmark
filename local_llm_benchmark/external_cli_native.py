"""Explicit, versioned text/tool bridge; never used by the frozen v0.1/v0.2 paths.

Both sides are journaled by ProviderJournal. Unsupported semantics fail closed.
This is a provider condition, not a claim about an unmodified native CLI.
"""

from __future__ import annotations

import json


PROFILE = {
    "profile_id": "ollama-native-text-tools-v1",
    "think": False,
    "temperature": 0,
    "seed": 42,
    "num_ctx": 16384,
    "num_predict": 1600,
    "keep_alive": "5m",
}


def _keys(value, allowed):
    if not isinstance(value, dict) or set(value) - set(allowed):
        raise ValueError("Unsupported native bridge fields")


def _text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(p, dict) and set(p) == {"type", "text"}
                                       and p["type"] == "text" and isinstance(p["text"], str)
                                       for p in value):
        return "".join(p["text"] for p in value)
    raise ValueError("Only text messages are qualified")


def native_request(payload: dict, profile: dict) -> dict:
    if profile != PROFILE:
        raise ValueError("Unknown generation profile")
    _keys(payload, {"model", "messages", "tools", "stream", "stream_options", "temperature",
                    "seed", "max_tokens", "max_completion_tokens", "reasoning_effort", "tool_choice"})
    if not isinstance(payload.get("stream", False), bool):
        raise ValueError("Invalid stream flag")
    if payload.get("stream_options", {}) not in ({}, {"include_usage": True}):
        raise ValueError("Unsupported stream options")
    for key in ("temperature", "seed"):
        if key in payload and payload[key] != profile[key]:
            raise ValueError("Conflicting CLI generation setting")
    if payload.get("reasoning_effort") not in (None, "none", "off"):
        raise ValueError("Conflicting thinking setting")
    if payload.get("tool_choice", "auto") != "auto":
        raise ValueError("Only automatic tool selection is qualified")
    cap = profile["num_predict"]
    for key in ("max_tokens", "max_completion_tokens"):
        if key in payload:
            value = payload[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError("Invalid completion limit")
            cap = min(cap, value)
    if not isinstance(payload.get("messages"), list):
        raise ValueError("Expected message array")
    messages, calls = [], {}
    for source in payload["messages"]:
        _keys(source, {"role", "content", "name", "tool_calls", "tool_call_id", "reasoning_content"})
        role = source.get("role")
        if role not in {"system", "user", "assistant", "tool"}:
            raise ValueError("Unsupported message role")
        message = {"role": role, "content": _text(source.get("content"))}
        if source.get("reasoning_content"):
            if role != "assistant":
                raise ValueError("Unexpected reasoning replay")
            message["thinking"] = _text(source["reasoning_content"])
        if source.get("tool_calls"):
            if role != "assistant":
                raise ValueError("Only assistants may call tools")
            message["tool_calls"] = []
            for call in source["tool_calls"]:
                _keys(call, {"id", "index", "type", "function"})
                if call.get("type") != "function" or not isinstance(call.get("id"), str):
                    raise ValueError("Unsupported tool call")
                function = call["function"]
                _keys(function, {"name", "arguments"})
                if not isinstance(function.get("name"), str):
                    raise ValueError("Missing tool name")
                arguments = function.get("arguments")
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                if not isinstance(arguments, dict) or call["id"] in calls:
                    raise ValueError("Invalid or duplicate tool arguments/correlation")
                calls[call["id"]] = function["name"]
                message["tool_calls"].append({"type": "function", "function": {
                    "name": function["name"], "arguments": arguments}})
        if role == "tool":
            call_id = source.get("tool_call_id")
            if call_id not in calls or source.get("name", calls[call_id]) != calls[call_id]:
                raise ValueError("Unmatched tool result")
            message["tool_name"] = calls[call_id]
        elif source.get("name") or source.get("tool_call_id"):
            raise ValueError("Unsupported named message")
        messages.append(message)
    result = {"model": payload["model"], "messages": messages, "stream": True,
              "think": False, "keep_alive": profile["keep_alive"], "options": {
                  "temperature": profile["temperature"], "seed": profile["seed"],
                  "num_ctx": profile["num_ctx"], "num_predict": cap}}
    if "tools" in payload:
        if not isinstance(payload["tools"], list):
            raise ValueError("Expected tool array")
        for tool in payload["tools"]:
            _keys(tool, {"type", "function"})
            if tool.get("type") != "function":
                raise ValueError("Unsupported tool type")
            _keys(tool["function"], {"name", "description", "parameters"})
        result["tools"] = payload["tools"]
    return result


class NativeResponse:
    """Incrementally emit SSE, preserving all content and unexpected thinking."""

    def __init__(self, payload: dict, sequence: int):
        self.payload, self.sequence = payload, sequence
        self.message = {"role": "assistant", "content": ""}
        self.common = {"id": f"ollama-native-{sequence}", "created": 0, "model": payload["model"]}
        self.usage = None
        self.done = False
        self.finish_reason = None
        self.thinking_characters = 0
        self.call_count = 0

    def event(self, delta, reason=None, usage=None):
        value = {**self.common, "object": "chat.completion.chunk", "choices": [
            {"index": 0, "delta": delta, "finish_reason": reason}]}
        if usage is not None:
            value["usage"] = usage
        return ("data: " + json.dumps(value) + "\n\n").encode()

    def feed(self, item: dict) -> bytes:
        if self.done or not isinstance(item, dict) or item.get("error"):
            raise ValueError("Invalid or trailing native response")
        if item.get("model") != self.payload["model"]:
            raise ValueError("Upstream model mismatch")
        message = item.get("message", {})
        _keys(message, {"role", "content", "thinking", "tool_calls"})
        if message.get("role", "assistant") != "assistant":
            raise ValueError("Unexpected response role")
        delta = {"role": "assistant"}
        for native, client in (("content", "content"), ("thinking", "reasoning_content")):
            value = message.get(native, "")
            if not isinstance(value, str):
                raise ValueError("Invalid response text")
            if value:
                delta[client] = value
                self.message[client] = self.message.get(client, "") + value
                if native == "thinking":
                    self.thinking_characters += len(value)
        for call in message.get("tool_calls", []):
            function = call.get("function", {})
            _keys(function, {"index", "name", "arguments"})
            if not isinstance(function.get("arguments"), dict) or not isinstance(function.get("name"), str):
                raise ValueError("Only complete native tool calls are qualified")
            converted = {"id": call.get("id") or f"native-{self.sequence}-{self.call_count}",
                         "type": "function", "function": {"name": function["name"],
                         "arguments": json.dumps(function["arguments"], ensure_ascii=False)}}
            self.message.setdefault("tool_calls", []).append(converted)
            delta.setdefault("tool_calls", []).append({"index": self.call_count, **converted})
            self.call_count += 1
        data = self.event(delta) if len(delta) > 1 else b""
        if item.get("done"):
            reason = item.get("done_reason")
            if reason not in {"stop", "length"}:
                raise ValueError("Unknown native termination reason")
            prompt, completion = item.get("prompt_eval_count"), item.get("eval_count")
            if any(isinstance(n, bool) or not isinstance(n, int) or n < 0 for n in (prompt, completion)):
                raise ValueError("Missing native usage")
            self.usage = {"prompt_tokens": prompt, "completion_tokens": completion,
                          "total_tokens": prompt + completion}
            self.finish_reason = "length" if reason == "length" else "tool_calls" if self.call_count else "stop"
            self.done = True
            data += self.event({}, self.finish_reason, self.usage) + b"data: [DONE]\n\n"
        return data if self.payload.get("stream") else b""

    def finish(self) -> bytes:
        if not self.done:
            raise ValueError("Native stream ended without completion")
        if self.payload.get("stream"):
            return b""
        return json.dumps({**self.common, "object": "chat.completion", "choices": [
            {"index": 0, "message": self.message, "finish_reason": self.finish_reason}],
            "usage": self.usage}).encode()


def stub_native(payload: dict, response: dict) -> bytes:
    """Offline fixtures traverse the same response converter as live traffic."""
    message = {"role": "assistant", **response.get("message", {"content": "offline transport qualified"})}
    if message.get("content") is None:
        message["content"] = ""
    if "reasoning_content" in message:
        message["thinking"] = message.pop("reasoning_content")
    for call in message.get("tool_calls", []):
        call["function"]["arguments"] = json.loads(call["function"]["arguments"])
    usage = response.get("usage", {"prompt_tokens": 10, "completion_tokens": 5})
    return (json.dumps({"model": payload["model"], "message": message, "done": True,
                        "done_reason": response.get("finish_reason", "stop"),
                        "prompt_eval_count": usage["prompt_tokens"], "eval_count": usage["completion_tokens"]}) + "\n").encode()
