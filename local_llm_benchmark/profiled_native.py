"""Text/tool request translation for explicit model-bound profile conditions.

The fixed external-cli-v0.3 converter remains unchanged. Reasoning supplied by
the caller is preserved according to the model's policy; absent history is
never fabricated. This alone does not qualify a complete CLI harness.
"""

from __future__ import annotations

import json

from .external_cli_native import _keys, _text
from .model_profiles import REGISTRY, SAMPLING_KEYS, binding_sha256, validate_condition


def native_request(payload: dict, condition: dict, *, registry_path=REGISTRY) -> tuple[dict, dict]:
    profile = validate_condition(condition, payload.get("model"), registry_path=registry_path)
    allowed = {"model", "messages", "tools", "stream", "stream_options", "seed", "max_tokens",
               "max_completion_tokens", "reasoning_effort", "tool_choice", "store", *SAMPLING_KEYS}
    _keys(payload, allowed)
    if type(payload.get("stream", False)) is not bool:
        raise ValueError("Invalid stream flag")
    if payload.get("stream_options", {}) not in ({}, {"include_usage": True}):
        raise ValueError("Unsupported stream options")
    if "store" in payload and payload["store"] is not False:
        raise ValueError("Stored completions are unsupported")
    if payload.get("tool_choice", "auto") != "auto":
        raise ValueError("Only automatic tool selection is qualified")
    for key in SAMPLING_KEYS:
        if key in payload and (key not in profile["sampling"] or type(payload[key]) is bool
                               or payload[key] != profile["sampling"][key]):
            raise ValueError("Conflicting CLI sampling setting")
    limits = condition["limits"]
    if "seed" in payload and (type(payload["seed"]) is not int or payload["seed"] != limits["seed"]):
        raise ValueError("Conflicting CLI seed")
    if "reasoning_effort" in payload:
        expected = profile["think"]
        supplied = payload["reasoning_effort"]
        if type(expected) is not str or supplied != expected:
            raise ValueError("Conflicting or ambiguous CLI reasoning effort")
    cap = limits["num_predict"]
    for key in ("max_tokens", "max_completion_tokens"):
        if key in payload:
            if type(payload[key]) is not int or payload[key] < 1:
                raise ValueError("Invalid client output ceiling")
            cap = min(cap, payload[key])
    if not isinstance(payload.get("messages"), list):
        raise ValueError("Expected message array")
    messages, calls, resolved = [], {}, set()
    audit = {"candidate_profile_id": profile["profile_id"],
             "profile_binding_sha256": binding_sha256(condition),
             "history_policy": profile["history_policy"],
             "reasoning_replay_encoding": profile.get("reasoning_replay_encoding", "native_thinking"),
             "reasoning_characters_supplied": 0, "reasoning_characters_preserved": 0,
             "reasoning_characters_dropped": 0}
    last_user = max((i for i, m in enumerate(payload["messages"])
                     if isinstance(m, dict) and m.get("role") == "user"), default=-1)
    for index, source in enumerate(payload["messages"]):
        _keys(source, {"role", "content", "name", "tool_calls", "tool_call_id", "reasoning_content"})
        role = source.get("role")
        if role not in {"system", "user", "assistant", "tool"}:
            raise ValueError("Unsupported message role")
        message = {"role": role, "content": _text(source.get("content"))}
        reasoning = _text(source.get("reasoning_content"))
        if reasoning:
            if role != "assistant":
                raise ValueError("Unexpected reasoning replay")
            audit["reasoning_characters_supplied"] += len(reasoning)
            preserve = (profile["history_policy"] == "preserve_supplied"
                        or bool(source.get("tool_calls")) and index > last_user)
            if preserve:
                if audit["reasoning_replay_encoding"] == "content_think_tags":
                    # This exact artifact's Jinja template ignores native `thinking`
                    # but explicitly extracts reasoning from this content encoding.
                    if any(tag in text for tag in ("<think>", "</think>")
                           for text in (reasoning, message["content"])):
                        raise ValueError("Ambiguous thinking delimiters in reasoning replay")
                    message["content"] = "<think>\n" + reasoning + "\n</think>\n\n" + message["content"]
                else:
                    message["thinking"] = reasoning
                audit["reasoning_characters_preserved"] += len(reasoning)
            else:
                audit["reasoning_characters_dropped"] += len(reasoning)
        if source.get("tool_calls"):
            if role != "assistant" or not isinstance(source["tool_calls"], list):
                raise ValueError("Invalid assistant tool calls")
            message["tool_calls"] = []
            for call in source["tool_calls"]:
                _keys(call, {"id", "index", "type", "function"})
                function = call.get("function")
                _keys(function, {"name", "arguments"})
                if call.get("type") != "function" or not isinstance(call.get("id"), str) or not call["id"]:
                    raise ValueError("Invalid tool-call correlation")
                if not isinstance(function.get("name"), str) or not function["name"]:
                    raise ValueError("Missing tool name")
                arguments = function.get("arguments")
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                if not isinstance(arguments, dict) or call["id"] in calls:
                    raise ValueError("Invalid tool arguments or duplicate call id")
                calls[call["id"]] = function["name"]
                message["tool_calls"].append({"id": call["id"], "type": "function", "function": {
                    "name": function["name"], "arguments": arguments}})
        if role == "tool":
            call_id = source.get("tool_call_id")
            if call_id not in calls or call_id in resolved or source.get("name", calls[call_id]) != calls[call_id]:
                raise ValueError("Unmatched or repeated tool result")
            resolved.add(call_id)
            message["tool_name"] = calls[call_id]
            message["tool_call_id"] = call_id
        elif source.get("name") or source.get("tool_call_id"):
            raise ValueError("Unsupported named message")
        messages.append(message)
    effective = {"model": profile["model"], "messages": messages, "stream": True,
                 "think": profile["think"], "keep_alive": limits["keep_alive"],
                 "options": {**profile["sampling"], "seed": limits["seed"],
                             "num_ctx": limits["num_ctx"], "num_predict": cap}}
    if "tools" in payload:
        if not isinstance(payload["tools"], list):
            raise ValueError("Expected tool array")
        for tool in payload["tools"]:
            _keys(tool, {"type", "function"})
            if tool.get("type") != "function":
                raise ValueError("Unsupported tool type")
            _keys(tool.get("function"), {"name", "description", "parameters"})
        effective["tools"] = payload["tools"]
    return effective, audit
