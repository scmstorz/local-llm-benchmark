"""Versioned Mini adapter for the supplier-award transfer case v0.2.

The stable v0.1 action-loop kernel is reused under an explicit configuration
boundary. The wrapper replaces only the case, schema, prompt, inventory and
shared artifact backend, then records both wrapper and kernel identities.
"""

from __future__ import annotations

import argparse
import json
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterator

from . import multi_format_mini as base
from . import multi_format_transfer_artifacts as artifact_backend
from .agentic import _normalized_relative_path
from .log_incident_mini import _artifact, _positive_integer
from .multi_format_transfer import (
    load_multi_format_transfer_case,
    verify_multi_format_transfer_report,
)
from .runner import RunnerError, load_json, sha256_file, write_json


HARNESS_ID = "mini-multi-format-v0.2"
PROTOCOL_ID = "agentic-multi-format-transfer-v0.2"
DEFAULT_HARNESS_PATH = Path("tasks/agentic/track-b/mini-multi-format-v0.2.json")
DEFAULT_CASE_PATH = Path(
    "tasks/agentic/multi-format-document-analysis/"
    "supplier-award-reconciliation/case-v0.2.json"
)
EXPECTED_ACTIONS = [
    "list_artifacts",
    "read_docx",
    "read_pdf",
    "read_xlsx",
    "finish_report",
]
BACKEND_RELATIVE = Path("local_llm_benchmark/multi_format_transfer_artifacts.py")
WRAPPER_RELATIVE = Path("local_llm_benchmark/multi_format_mini_v02.py")
KERNEL_RELATIVE = Path("local_llm_benchmark/multi_format_mini.py")


def load_mini_multi_format_v02_harness(
    repo_root: Path, harness_path: Path = DEFAULT_HARNESS_PATH
) -> dict[str, Any]:
    """Load the complete frozen Mini transfer definition."""
    path = base.resolve_repo_path(repo_root, harness_path)
    harness = load_json(path)
    if (
        harness.get("schema_version") != "1.0.0"
        or harness.get("harness_id") != HARNESS_ID
        or harness.get("harness_family") != "project_mini_harness"
        or harness.get("status") != "qualification_candidate"
        or harness.get("actions") != EXPECTED_ACTIONS
        or harness.get("action_protocol")
        != "ollama_json_schema_action_per_turn"
    ):
        raise RunnerError("Unexpected Mini transfer harness definition")
    protocol_path = _artifact(repo_root, harness, "protocol_path", "protocol")
    prompt_path = _artifact(
        repo_root, harness, "system_prompt_path", "system prompt"
    )
    schema_path = _artifact(repo_root, harness, "action_schema_path", "action schema")
    inventory_path = _artifact(
        repo_root, harness, "capability_inventory_path", "capability inventory"
    )
    isolation_path = _artifact(
        repo_root, harness, "isolation_profile_path", "isolation profile"
    )
    protocol = load_json(protocol_path)
    schema = load_json(schema_path)
    inventory = load_json(inventory_path)
    isolation = load_json(isolation_path)
    artifact_api = protocol.get("artifact_api", {})
    completion = protocol.get("completion_operation", {})
    if (
        protocol.get("protocol_id") != PROTOCOL_ID
        or protocol.get("track") != "B"
        or protocol.get("study_mode") != "development_qualification"
        or protocol.get("status") != harness["status"]
        or artifact_api.get("version") != artifact_backend.API_VERSION
        or artifact_api.get("implementation_path") != BACKEND_RELATIVE.as_posix()
        or artifact_api.get("operations") != EXPECTED_ACTIONS[:-1]
        or artifact_api.get("maximum_response_bytes")
        != artifact_backend.MAX_RESPONSE_BYTES
        or completion.get("name") != "finish_report"
        or completion.get("free_text_fallback_admitted") is not False
    ):
        raise RunnerError("Unexpected Mini transfer protocol")
    subset = protocol.get("task_subset")
    if not isinstance(subset, list) or len(subset) != 1:
        raise RunnerError("Mini transfer requires exactly one case")
    if (
        inventory.get("inventory_id") != HARNESS_ID
        or [item.get("name") for item in inventory.get("actions", [])]
        != EXPECTED_ACTIONS
        or inventory.get("shared_backend") != BACKEND_RELATIVE.as_posix()
    ):
        raise RunnerError("Mini transfer capability inventory differs")
    if (
        isolation.get("isolation_profile_id") != HARNESS_ID
        or isolation.get("workspace", {}).get("fresh_artifact_only_copy_per_run")
        is not True
        or isolation.get("evaluation", {}).get(
            "canonical_extraction_outside_workspace"
        )
        is not True
        or isolation.get("evaluation", {}).get("candidate_code_executed")
        is not False
    ):
        raise RunnerError("Unexpected Mini transfer isolation profile")
    if not isinstance(schema.get("oneOf"), list) or len(schema["oneOf"]) != 5:
        raise RunnerError("Mini transfer action schema must define five actions")
    limits = protocol.get("normal_capability_limits")
    safeguards = protocol.get("runaway_operation_safeguards")
    inference = protocol.get("inference_defaults")
    if not all(isinstance(value, dict) for value in (limits, safeguards, inference)):
        raise RunnerError("Mini transfer limit objects are incomplete")
    for key in ("maximum_active_wall_time_seconds", "provider_request_timeout_seconds"):
        _positive_integer(limits.get(key), key)
    for key in (
        "maximum_agent_turns",
        "maximum_total_output_tokens",
        "maximum_protocol_errors",
    ):
        if limits.get(key) is not None:
            raise RunnerError(f"Mini transfer must keep {key} measurement-only")
    _positive_integer(
        safeguards.get("maximum_artifact_tool_calls"),
        "maximum_artifact_tool_calls",
    )
    for key in ("num_ctx", "num_predict_per_turn", "request_timeout_seconds"):
        _positive_integer(inference.get(key), key)
    if inference["request_timeout_seconds"] != limits["provider_request_timeout_seconds"]:
        raise RunnerError("Mini transfer provider timeouts differ")
    return {
        "harness": harness,
        "harness_path": path,
        "protocol": protocol,
        "protocol_path": protocol_path,
        "system_prompt": prompt_path.read_text(encoding="utf-8").strip(),
        "system_prompt_path": prompt_path,
        "action_schema": schema,
        "action_schema_path": schema_path,
        "capability_inventory": inventory,
        "capability_inventory_path": inventory_path,
        "isolation_profile": isolation,
        "isolation_profile_path": isolation_path,
    }


def _validated_definition(repo_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    loaded = base.load_mini_multi_format_case(
        repo_root,
        Path(_normalized_relative_path(record["case"]["case_path"], "run case")),
        Path(
            _normalized_relative_path(
                record["harness"]["harness_path"], "run harness"
            )
        ),
    )
    paths = {
        "harness": loaded["harness_path"],
        "protocol": loaded["protocol_path"],
        "system_prompt": loaded["system_prompt_path"],
        "action_schema": loaded["action_schema_path"],
        "capability_inventory": loaded["capability_inventory_path"],
        "isolation_profile": loaded["isolation_profile_path"],
        "implementation": repo_root / WRAPPER_RELATIVE,
        "adapter_kernel": repo_root / KERNEL_RELATIVE,
        "artifact_backend": repo_root / BACKEND_RELATIVE,
    }
    mismatches = [
        f"{key}_sha256"
        for key, path in paths.items()
        if record["harness"].get(f"{key}_sha256") != sha256_file(path)
    ]
    case_hashes = {
        "case_definition_sha256": sha256_file(loaded["case_path"]),
        "task_sha256": sha256_file(loaded["task_path"]),
        "report_schema_sha256": sha256_file(loaded["schema_path"]),
        "ground_truth_sha256": sha256_file(loaded["truth_path"]),
        "reference_report_sha256": sha256_file(loaded["reference_report_path"]),
    }
    mismatches += [
        key for key, value in case_hashes.items() if record["case"].get(key) != value
    ]
    if mismatches:
        raise RunnerError("Mini transfer definition changed: " + ", ".join(mismatches))
    return loaded


@contextmanager
def _configured_base() -> Iterator[None]:
    replacements = {
        "HARNESS_ID": HARNESS_ID,
        "PROTOCOL_ID": PROTOCOL_ID,
        "ARTIFACTS": artifact_backend.ARTIFACTS,
        "ArtifactToolError": artifact_backend.ArtifactToolError,
        "execute_artifact_request": artifact_backend.execute_artifact_request,
        "verify_workspace": artifact_backend.verify_workspace,
        "load_multi_format_case": load_multi_format_transfer_case,
        "verify_multi_format_report": verify_multi_format_transfer_report,
        "load_mini_multi_format_harness": load_mini_multi_format_v02_harness,
        "_validated_definition": _validated_definition,
    }
    previous = {name: getattr(base, name) for name in replacements}
    for name, value in replacements.items():
        setattr(base, name, value)
    try:
        yield
    finally:
        for name, value in previous.items():
            setattr(base, name, value)


def load_mini_multi_format_v02_case(
    repo_root: Path,
    case_path: Path = DEFAULT_CASE_PATH,
    harness_path: Path = DEFAULT_HARNESS_PATH,
) -> dict[str, Any]:
    with _configured_base():
        return base.load_mini_multi_format_case(repo_root, case_path, harness_path)


def _rewrite_next_action(result: dict[str, Any]) -> dict[str, Any]:
    next_action = result.get("next_action")
    if isinstance(next_action, str):
        result["next_action"] = next_action.replace(
            "local_llm_benchmark.multi_format_mini",
            "local_llm_benchmark.multi_format_mini_v02",
        )
    return result


def start(
    repo_root: Path, config: base.MiniMultiFormatStartConfig
) -> dict[str, Any]:
    corrected = replace(
        config, case_path=DEFAULT_CASE_PATH, harness_path=DEFAULT_HARNESS_PATH
    )
    with _configured_base():
        result = base.start_mini_multi_format_run(repo_root, corrected)
    run_dir = Path(result["run_dir"])
    record_path = run_dir / "run.json"
    record = load_json(record_path)
    identity = {
        "implementation": repo_root / WRAPPER_RELATIVE,
        "adapter_kernel": repo_root / KERNEL_RELATIVE,
        "artifact_backend": repo_root / BACKEND_RELATIVE,
    }
    for key, path in identity.items():
        record["harness"][f"{key}_path"] = path.relative_to(repo_root).as_posix()
        record["harness"][f"{key}_sha256"] = sha256_file(path)
    write_json(record_path, record)
    return _rewrite_next_action(result)


def call(repo_root: Path, run_dir: Path) -> dict[str, Any]:
    with _configured_base():
        return _rewrite_next_action(
            base.call_mini_multi_format_model(repo_root, run_dir)
        )


def step(repo_root: Path, run_dir: Path) -> dict[str, Any]:
    with _configured_base():
        return _rewrite_next_action(
            base.step_mini_multi_format_action(repo_root, run_dir)
        )


def finalize(repo_root: Path, run_dir: Path) -> dict[str, Any]:
    with _configured_base():
        return base.finalize_mini_multi_format_run(repo_root, run_dir)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    start_parser = subparsers.add_parser("start")
    start_parser.add_argument("--model", required=True)
    start_parser.add_argument("--results-dir", type=Path, default=Path("results/agentic-runs"))
    start_parser.add_argument("--host", default="http://127.0.0.1:11434")
    for name in ("call", "step", "finalize"):
        command = subparsers.add_parser(name)
        command.add_argument("--run-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    if args.command == "start":
        result = start(
            repo_root,
            base.MiniMultiFormatStartConfig(
                model=args.model, results_dir=args.results_dir, host=args.host
            ),
        )
    elif args.command == "call":
        result = call(repo_root, args.run_dir)
    elif args.command == "step":
        result = step(repo_root, args.run_dir)
    else:
        result = finalize(repo_root, args.run_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
