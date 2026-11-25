"""Versioned, artifact-bound starting profiles; no implicit run budgets or inference.

These are technical candidates. Calibration and performance selection are
separate owner decisions. The historical external CLI v0.3 profile is untouched.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import re


REGISTRY = Path(__file__).resolve().parents[1]/"models/practical-profiles-v0.1.json"
CONDITION_ID = "ollama-native-model-profile-v1"
SAMPLING_KEYS = {"temperature", "top_p", "top_k", "min_p", "presence_penalty", "repeat_penalty"}


def _integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def _finite(value):
    return type(value) in {int, float} and math.isfinite(value)


def candidate(profile_id: str, *, registry_path: Path = REGISTRY) -> dict:
    registry = json.loads(registry_path.read_text())
    if registry.get("schema_version") != "model-starting-profiles-v1":
        raise ValueError("Unknown model-profile registry")
    profiles = registry["profiles"]
    matches = [p for p in profiles if p.get("profile_id") == profile_id]
    if len(matches) != 1:
        raise ValueError("Unknown or duplicate model profile")
    profile = matches[0]
    if not re.fullmatch(r"[a-f0-9]{64}", profile.get("model_digest", "")):
        raise ValueError("A full artifact digest is required")
    think = profile.get("think")
    if type(think) is not bool and think not in {"low", "medium", "xhigh"}:
        raise ValueError("Unsupported candidate thinking value")
    if profile.get("history_policy") not in {"preserve_supplied", "current_turn_tool_calls_only"}:
        raise ValueError("Unknown reasoning-history policy")
    if profile.get("reasoning_replay_encoding", "native_thinking") not in {"native_thinking", "content_think_tags"}:
        raise ValueError("Unknown reasoning replay encoding")
    sampling = profile.get("sampling")
    if not isinstance(sampling, dict) or not sampling or set(sampling)-SAMPLING_KEYS:
        raise ValueError("Unknown sampling fields")
    for key, value in sampling.items():
        if key == "top_k":
            valid = _integer(value, 0, 100000)
        elif key in {"top_p", "min_p"}:
            valid = _finite(value) and 0 <= value <= 1
        elif key == "presence_penalty":
            valid = _finite(value) and -2 <= value <= 2
        else:
            valid = _finite(value) and 0 <= value <= 10
        if not valid:
            raise ValueError("Invalid sampling value")
    return copy.deepcopy(profile)


def condition(profile_id: str, *, num_ctx: int, num_predict: int, seed: int,
              keep_alive: str = "5m", registry_path: Path = REGISTRY) -> dict:
    """All capacity decisions are explicit; this does not choose a performance profile."""
    profile = candidate(profile_id, registry_path=registry_path)
    value = {"profile_id": CONDITION_ID, "candidate": profile, "limits": {
        "num_ctx": num_ctx, "num_predict": num_predict, "seed": seed, "keep_alive": keep_alive}}
    validate_condition(value, profile["model"], registry_path=registry_path)
    return value


def validate_condition(value: dict, model: str, *, registry_path: Path = REGISTRY) -> dict:
    if not isinstance(value, dict) or set(value) != {"profile_id", "candidate", "limits"}:
        raise ValueError("Invalid model-profile condition")
    if value["profile_id"] != CONDITION_ID or not isinstance(value["candidate"], dict):
        raise ValueError("Unknown model-profile condition")
    supplied = value["candidate"]
    expected = candidate(supplied.get("profile_id"), registry_path=registry_path)
    # JSON booleans and numbers must not compare equal as Python dictionaries do.
    if json.dumps(supplied, sort_keys=True) != json.dumps(expected, sort_keys=True) or expected["model"] != model:
        raise ValueError("Model/profile binding changed")
    limits = value["limits"]
    if not isinstance(limits, dict) or set(limits) != {"num_ctx", "num_predict", "seed", "keep_alive"}:
        raise ValueError("Explicit context, output, seed and keep-alive limits are required")
    if not _integer(limits["num_ctx"], 1024, expected["maximum_context_tokens"]):
        raise ValueError("Invalid context capacity")
    if not _integer(limits["num_predict"], 1, limits["num_ctx"]-1):
        raise ValueError("Output capacity must leave room for input")
    if not _integer(limits["seed"], 0, 2**32-1):
        raise ValueError("Invalid seed")
    if not isinstance(limits["keep_alive"], str) or not re.fullmatch(r"[1-9][0-9]*[sm]", limits["keep_alive"]):
        raise ValueError("A finite positive keep-alive is required")
    return expected


def binding_sha256(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_deployment(value: dict, *, tag: dict, show: dict, runtime: dict,
                        registry_path: Path = REGISTRY) -> dict:
    profile = validate_condition(value, value["candidate"]["model"], registry_path=registry_path)
    if (tag.get("name") != profile["model"] or tag.get("digest") != profile["model_digest"]
        or runtime.get("version") != profile["ollama_version"]):
        raise ValueError("Deployment or runtime identity drift")
    if not {"completion", "thinking", "tools"}.issubset(show.get("capabilities", [])):
        raise ValueError("Required backend capabilities are absent")
    info = show.get("model_info", {})
    contexts = [n for key, n in info.items() if key.endswith(".context_length") and type(n) is int]
    if not contexts or value["limits"]["num_ctx"] > max(contexts):
        raise ValueError("Requested context exceeds advertised model capacity")
    metadata = show.get("thinking")
    if metadata is not None:
        if not isinstance(metadata, dict) or not any(type(v) is type(profile["think"]) and v == profile["think"]
                                                    for v in metadata.get("values", [])):
            raise ValueError("Thinking value is not explicitly supported")
        status = "advertised_supported"
    elif profile.get("unadvertised_boolean_probe") is True and profile["think"] is True:
        status = "unadvertised_boolean_requires_positive_technical_probe"
    else:
        raise ValueError("Missing thinking-control metadata")
    return {"profile_binding_sha256": binding_sha256(value), "thinking_control_status": status,
            "requested_think": profile["think"], "requested_context": value["limits"]["num_ctx"],
            "architecture_context_maximum": max(contexts), "observed_runtime_context": None,
            "model_parameters": show.get("parameters")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    build = commands.add_parser("build")
    build.add_argument("--profile", required=True)
    build.add_argument("--context", type=int, required=True)
    build.add_argument("--output", type=int, required=True)
    build.add_argument("--seed", type=int, required=True)
    args = parser.parse_args(argv)
    if args.command == "list":
        value = json.loads(REGISTRY.read_text())
    else:
        value = condition(args.profile, num_ctx=args.context, num_predict=args.output, seed=args.seed)
    print(json.dumps(value, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
