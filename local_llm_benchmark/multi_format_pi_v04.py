"""Pinned Pi 0.84.4 supplier-transfer adapter with structured completion.

Pi v0.4 preserves the direct Python.app worker and explicit-extension checks
from v0.3. It adds one schema-constrained ``finish_report`` tool and admits no
free-text fallback as candidate output.
"""

from __future__ import annotations

import argparse
import json
import shutil
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterator

from . import multi_format_pi as base
from . import multi_format_transfer_artifacts as artifact_backend
from .agentic import _normalized_relative_path
from .json_schema import JsonSchemaError, validate_json
from .macos_sandbox import pi_sandbox_environment, run_seatbelt_command
from .macos_sandbox_multi_format_v02 import (
    validate_pi_multi_format_v02_seatbelt,
    write_pi_multi_format_v02_seatbelt_artifacts,
)
from .multi_format_pi_v02 import python_worker_executable
from .multi_format_transfer import (
    load_multi_format_transfer_case,
    verify_multi_format_transfer_report,
)
from .runner import RunnerError, load_json, resolve_repo_path, sha256_file, write_json


HARNESS_ID = "pi-multi-format-v0.4"
PROTOCOL_ID = "agentic-multi-format-transfer-v0.2"
DEFAULT_HARNESS_PATH = Path("tasks/agentic/track-b/pi-multi-format-v0.4.json")
DEFAULT_CASE_PATH = Path(
    "tasks/agentic/multi-format-document-analysis/"
    "supplier-award-reconciliation/case-v0.2.json"
)
ARTIFACT_TOOL_NAMES = ["list_artifacts", "read_docx", "read_pdf", "read_xlsx"]
TOOL_NAMES = [*ARTIFACT_TOOL_NAMES, "finish_report"]
BACKEND_RELATIVE = Path("local_llm_benchmark/multi_format_transfer_artifacts.py")
WRAPPER_RELATIVE = Path("local_llm_benchmark/multi_format_pi_v04.py")
KERNEL_RELATIVE = Path("local_llm_benchmark/multi_format_pi.py")
WORKER_SELECTOR_RELATIVE = Path("local_llm_benchmark/multi_format_pi_v02.py")
SANDBOX_RELATIVE = Path("local_llm_benchmark/macos_sandbox_multi_format_v02.py")


def load_pi_multi_format_v04_harness(
    repo_root: Path, harness_path: Path = DEFAULT_HARNESS_PATH
) -> dict[str, Any]:
    """Validate the Pi v0.4 definition and exact pinned package."""
    path = resolve_repo_path(repo_root, harness_path)
    harness = load_json(path)
    if (
        harness.get("schema_version") != "1.0.0"
        or harness.get("harness_id") != HARNESS_ID
        or harness.get("harness_family") != "pinned_pi"
        or harness.get("status") != "qualification_candidate"
        or harness.get("supersedes") != "pi-multi-format-v0.3"
        or harness.get("final_output_protocol")
        != "single_schema_constrained_finish_report_tool_argument"
    ):
        raise RunnerError("Unexpected Pi v0.4 harness definition")
    integration = harness.get("integration")
    package = harness.get("package")
    if not isinstance(integration, dict) or not isinstance(package, dict):
        raise RunnerError("Pi v0.4 integration identity is missing")
    if (
        integration.get("tools") != TOOL_NAMES
        or integration.get("artifact_tools") != ARTIFACT_TOOL_NAMES
        or integration.get("completion_tool") != "finish_report"
    ):
        raise RunnerError("Pi v0.4 tool surface changed")
    if any(
        integration.get(key) is not False
        for key in (
            "session_persistence",
            "startup_network",
            "discovered_extensions",
            "skills",
            "prompt_templates",
            "themes",
            "context_files",
            "project_trust",
        )
    ):
        raise RunnerError("Pi v0.4 discovered state is enabled")
    protocol_path = base._artifact(repo_root, harness, "protocol_path", "protocol")
    prompt_path = base._artifact(
        repo_root, harness, "system_prompt_path", "system prompt"
    )
    inventory_path = base._artifact(
        repo_root, harness, "capability_inventory_path", "capability inventory"
    )
    isolation_path = base._artifact(
        repo_root, harness, "isolation_profile_path", "isolation profile"
    )
    extension_path = base._artifact(
        repo_root, integration, "explicit_extension", "policy extension"
    )
    protocol = load_json(protocol_path)
    inventory = load_json(inventory_path)
    isolation = load_json(isolation_path)
    artifact_api = protocol.get("artifact_api", {})
    completion = protocol.get("completion_operation", {})
    if (
        protocol.get("protocol_id") != PROTOCOL_ID
        or protocol.get("track") != "B"
        or protocol.get("status") != harness["status"]
        or artifact_api.get("version") != artifact_backend.API_VERSION
        or artifact_api.get("implementation_path") != BACKEND_RELATIVE.as_posix()
        or artifact_api.get("operations") != ARTIFACT_TOOL_NAMES
        or completion.get("name") != "finish_report"
        or completion.get("free_text_fallback_admitted") is not False
    ):
        raise RunnerError("Unexpected Pi v0.4 transfer protocol")
    if not isinstance(protocol.get("task_subset"), list) or len(protocol["task_subset"]) != 1:
        raise RunnerError("Pi v0.4 requires exactly one case")
    if (
        inventory.get("inventory_id") != HARNESS_ID
        or [item.get("name") for item in inventory.get("model_visible_tools", [])]
        != TOOL_NAMES
        or isolation.get("isolation_profile_id") != HARNESS_ID
        or isolation.get("backend") != "pi-multi-format-macos-seatbelt-v0.2"
        or isolation.get("evaluation", {}).get(
            "canonical_extraction_outside_workspace"
        )
        is not True
        or isolation.get("evaluation", {}).get("free_text_final_response_admitted")
        is not False
        or isolation.get("process", {}).get("candidate_code_executed") is not False
    ):
        raise RunnerError("Pi v0.4 capability or isolation definition differs")
    limits = protocol.get("normal_capability_limits")
    safeguards = protocol.get("runaway_operation_safeguards")
    inference = protocol.get("inference_defaults")
    if not all(isinstance(value, dict) for value in (limits, safeguards, inference)):
        raise RunnerError("Pi v0.4 limit objects are incomplete")
    for key in ("maximum_active_wall_time_seconds", "provider_request_timeout_seconds"):
        base._positive_integer(limits.get(key), key)
    base._positive_integer(
        safeguards.get("maximum_artifact_tool_calls"),
        "maximum_artifact_tool_calls",
    )
    for key in ("num_ctx", "num_predict_per_turn", "request_timeout_seconds"):
        base._positive_integer(inference.get(key), key)
    integration_root = resolve_repo_path(repo_root, base.PI_INTEGRATION_ROOT)
    package_json_path = integration_root / "package.json"
    package_lock_path = integration_root / "package-lock.json"
    package_json = load_json(package_json_path)
    package_lock = load_json(package_lock_path)
    name = package.get("name")
    version = package.get("version")
    locked = package_lock.get("packages", {}).get(f"node_modules/{name}")
    if (
        package_json.get("dependencies", {}).get(name) != version
        or not isinstance(locked, dict)
        or locked.get("version") != version
        or locked.get("integrity") != package.get("npm_integrity")
    ):
        raise RunnerError("Pinned Pi v0.4 package identity differs")
    binary = integration_root / "node_modules" / ".bin" / "pi"
    if not binary.exists() or base._package_version(binary, integration_root) != version:
        raise RunnerError("Pinned Pi 0.84.4 is not installed")
    return {
        "harness": harness,
        "harness_path": path,
        "protocol": protocol,
        "protocol_path": protocol_path,
        "system_prompt": prompt_path.read_text(encoding="utf-8").strip(),
        "system_prompt_path": prompt_path,
        "capability_inventory_path": inventory_path,
        "isolation_profile_path": isolation_path,
        "extension_path": extension_path,
        "integration_root": integration_root,
        "package_json_path": package_json_path,
        "package_lock_path": package_lock_path,
        "binary": binary,
        "node_version": base._node_version(integration_root),
    }


def load_pi_multi_format_v04_case(
    repo_root: Path,
    case_path: Path = DEFAULT_CASE_PATH,
    harness_path: Path = DEFAULT_HARNESS_PATH,
) -> dict[str, Any]:
    harness = load_pi_multi_format_v04_harness(repo_root, harness_path)
    loaded = load_multi_format_transfer_case(repo_root, case_path)
    relative_case = loaded["case_path"].relative_to(repo_root).as_posix()
    selected = harness["protocol"]["task_subset"][0]
    if (
        selected.get("case_path") != relative_case
        or selected.get("case_id") != loaded["case"]["case_id"]
        or selected.get("case_version") != loaded["case"]["case_version"]
    ):
        raise RunnerError("Case is outside the Pi v0.4 subset")
    fixture_root = resolve_repo_path(
        repo_root, Path(loaded["case"]["planned_artifact_root"])
    )
    canonical_path = resolve_repo_path(
        repo_root, Path(loaded["case"]["canonical_extraction"]["path"])
    )
    if not fixture_root.is_dir() or not canonical_path.is_file():
        raise RunnerError("Pi v0.4 transfer inputs are incomplete")
    return {
        **loaded,
        **harness,
        "relative_case_path": relative_case,
        "fixture_root": fixture_root,
        "canonical_path": canonical_path,
    }


def _copy_workspace(source: Path, destination: Path) -> dict[str, Any]:
    destination.mkdir()
    for filename in artifact_backend.ARTIFACTS:
        source_path = source / filename
        if not source_path.is_file() or source_path.is_symlink():
            raise RunnerError(f"Unsafe source artifact: {filename}")
        shutil.copyfile(source_path, destination / filename)
    try:
        return artifact_backend.verify_workspace(destination)
    except artifact_backend.ArtifactToolError as exc:
        raise RunnerError(str(exc)) from exc


def build_pi_multi_format_v04_policy(
    loaded: dict[str, Any],
    workspace: Path,
    audit_path: Path,
    backend_path: Path,
    python_path: Path,
    pdftotext_path: Path,
) -> dict[str, Any]:
    run_root = workspace.parent.resolve()
    report_schema_path = run_root / "report-schema.json"
    write_json(report_schema_path, loaded["schema"])
    completion = loaded["protocol"]["completion_operation"]
    return {
        "schema_version": "1.0.0",
        "policy_id": "pi-multi-format-readonly-v0.2",
        "private_run_root": str(run_root),
        "workspace_root": str(workspace.resolve()),
        "audit_log_path": str(audit_path.resolve()),
        "backend_path": str(backend_path.resolve()),
        "backend_sha256": sha256_file(backend_path),
        "python_path": str(python_path.resolve()),
        "python_sha256": sha256_file(python_path),
        "pdftotext_path": str(pdftotext_path.resolve()),
        "pdftotext_sha256": sha256_file(pdftotext_path),
        "report_schema_path": str(report_schema_path),
        "report_schema_sha256": sha256_file(report_schema_path),
        "final_report_path": str(run_root / "captured-report.json"),
        "maximum_report_bytes": completion["maximum_serialized_bytes"],
        "allowed_tools": TOOL_NAMES,
        "artifact_operations": ARTIFACT_TOOL_NAMES,
        "maximum_tool_calls": loaded["protocol"]["runaway_operation_safeguards"][
            "maximum_artifact_tool_calls"
        ],
        "parent_maximum_active_wall_time_seconds": loaded["protocol"][
            "normal_capability_limits"
        ]["maximum_active_wall_time_seconds"],
    }


def _user_message(loaded: dict[str, Any]) -> str:
    task = loaded["task_path"].read_text(encoding="utf-8").strip()
    calls = loaded["protocol"]["runaway_operation_safeguards"][
        "maximum_artifact_tool_calls"
    ]
    return (
        f"# Task\n\n{task}\n\n"
        "# Run boundary\n\n"
        "- Artifact contents are initially hidden; call list_artifacts first.\n"
        f"- Emergency artifact-call safeguard: {calls}.\n"
        "- Hidden references, canonical extraction and verifier are unavailable.\n"
        "- Submit the complete report only through finish_report.\n"
        "- Ordinary assistant text is not accepted as the final report."
    )


def _load_prepared(
    repo_root: Path, run_dir: Path, states: set[str]
) -> dict[str, Any]:
    resolved = resolve_repo_path(repo_root, run_dir)
    record_path = resolved / "run.json"
    record = load_json(record_path)
    if (
        record.get("harness", {}).get("harness_id") != HARNESS_ID
        or record.get("state") not in states
    ):
        raise RunnerError("Unexpected Pi v0.4 run identity or state")
    loaded = load_pi_multi_format_v04_case(
        repo_root,
        Path(_normalized_relative_path(record["case"]["case_path"], "run case")),
        Path(
            _normalized_relative_path(
                record["harness"]["harness_path"], "run harness"
            )
        ),
    )
    definition_paths = {
        "harness": loaded["harness_path"],
        "protocol": loaded["protocol_path"],
        "system_prompt": loaded["system_prompt_path"],
        "capability_inventory": loaded["capability_inventory_path"],
        "isolation_profile": loaded["isolation_profile_path"],
        "extension": loaded["extension_path"],
        "adapter": repo_root / WRAPPER_RELATIVE,
        "adapter_kernel": repo_root / KERNEL_RELATIVE,
        "python_worker_selector": repo_root / WORKER_SELECTOR_RELATIVE,
        "sandbox_adapter": repo_root / SANDBOX_RELATIVE,
        "artifact_backend": repo_root / BACKEND_RELATIVE,
    }
    mismatches = [
        f"{key}_sha256"
        for key, path in definition_paths.items()
        if record["harness"].get(f"{key}_sha256") != sha256_file(path)
    ]
    case_hashes = {
        "case_definition_sha256": sha256_file(loaded["case_path"]),
        "task_sha256": sha256_file(loaded["task_path"]),
        "report_schema_sha256": sha256_file(loaded["schema_path"]),
        "ground_truth_sha256": sha256_file(loaded["truth_path"]),
        "canonical_sha256": sha256_file(loaded["canonical_path"]),
        "reference_report_sha256": sha256_file(loaded["reference_report_path"]),
    }
    mismatches += [
        key for key, value in case_hashes.items() if record["case"].get(key) != value
    ]
    if mismatches:
        raise RunnerError("Pi v0.4 definition changed: " + ", ".join(mismatches))
    if record["harness"].get("package_lock_sha256") != sha256_file(
        loaded["package_lock_path"]
    ):
        raise RunnerError("Pi v0.4 package lock changed")
    try:
        artifact_backend.verify_workspace(
            resolved / record["artifacts"]["workspace"]
        )
    except artifact_backend.ArtifactToolError as exc:
        raise RunnerError(f"Pi v0.4 workspace drifted: {exc}") from exc
    paths = {
        "invocation": resolved / record["artifacts"]["invocation"],
        "policy": resolved / record["artifacts"]["policy"],
        "sandbox_profile": resolved / record["artifacts"]["sandbox_profile"],
        "sandbox_metadata": resolved / record["artifacts"]["sandbox_metadata"],
        "settings": resolved / record["artifacts"]["pi_agent_dir"] / "settings.json",
        "models": resolved / record["artifacts"]["pi_agent_dir"] / "models.json",
        "backend_copy": resolved / record["artifacts"]["backend_copy"],
        "report_schema": resolved / record["artifacts"]["report_schema"],
    }
    for key, path in paths.items():
        base._require_hash(path, record["artifacts"]["prepared_sha256"][key], key)
    policy = load_json(paths["policy"])
    if (
        policy.get("backend_sha256")
        != record["harness"]["artifact_backend_sha256"]
        or policy.get("allowed_tools") != TOOL_NAMES
        or policy.get("artifact_operations") != ARTIFACT_TOOL_NAMES
        or Path(policy.get("final_report_path", ""))
        != resolved / record["artifacts"]["captured_report"]
    ):
        raise RunnerError("Pi v0.4 prepared policy differs")
    return {
        **loaded,
        "run_dir": resolved,
        "record_path": record_path,
        "record": record,
        "invocation": load_json(paths["invocation"]),
        "policy": policy,
        "sandbox": load_json(paths["sandbox_metadata"]),
        "profile_path": paths["sandbox_profile"],
    }


@contextmanager
def _configured_base() -> Iterator[Path]:
    worker = python_worker_executable(base.sys.executable)
    replacements = {
        "HARNESS_ID": HARNESS_ID,
        "PROTOCOL_ID": PROTOCOL_ID,
        "TOOL_NAMES": TOOL_NAMES,
        "ARTIFACTS": artifact_backend.ARTIFACTS,
        "ArtifactToolError": artifact_backend.ArtifactToolError,
        "verify_workspace": artifact_backend.verify_workspace,
        "_copy_workspace": _copy_workspace,
        "load_multi_format_case": load_multi_format_transfer_case,
        "verify_multi_format_report": verify_multi_format_transfer_report,
        "load_pi_multi_format_harness": load_pi_multi_format_v04_harness,
        "load_pi_multi_format_case": load_pi_multi_format_v04_case,
        "build_pi_multi_format_policy": build_pi_multi_format_v04_policy,
        "_user_message": _user_message,
        "write_pi_multi_format_seatbelt_artifacts": write_pi_multi_format_v02_seatbelt_artifacts,
        "validate_pi_multi_format_seatbelt": validate_pi_multi_format_v02_seatbelt,
        "_load_prepared": _load_prepared,
        "sys.executable": str(worker),
    }
    previous: dict[str, Any] = {}
    for name, value in replacements.items():
        if name == "sys.executable":
            previous[name] = base.sys.executable
            base.sys.executable = value
        else:
            previous[name] = getattr(base, name)
            setattr(base, name, value)
    try:
        yield worker
    finally:
        for name, value in previous.items():
            if name == "sys.executable":
                base.sys.executable = value
            else:
                setattr(base, name, value)


def prepare(repo_root: Path, config: base.PiMultiFormatPrepareConfig) -> dict[str, Any]:
    """Prepare Pi v0.4, its shared backend and Seatbelt without inference."""
    corrected = replace(
        config, case_path=DEFAULT_CASE_PATH, harness_path=DEFAULT_HARNESS_PATH
    )
    with _configured_base() as worker:
        result = base.prepare_pi_multi_format_run(repo_root, corrected)
    run_dir = Path(result["run_dir"])
    record_path = run_dir / "run.json"
    record = load_json(record_path)
    backend_copy = run_dir / record["artifacts"]["backend_copy"]
    source_backend = repo_root / BACKEND_RELATIVE
    shutil.copyfile(source_backend, backend_copy)
    policy_path = run_dir / record["artifacts"]["policy"]
    policy = load_json(policy_path)
    policy["backend_sha256"] = sha256_file(backend_copy)
    write_json(policy_path, policy)
    identity = {
        "adapter": repo_root / WRAPPER_RELATIVE,
        "adapter_kernel": repo_root / KERNEL_RELATIVE,
        "python_worker_selector": repo_root / WORKER_SELECTOR_RELATIVE,
        "sandbox_adapter": repo_root / SANDBOX_RELATIVE,
        "artifact_backend": source_backend,
    }
    for key, path in identity.items():
        record["harness"][f"{key}_path"] = path.relative_to(repo_root).as_posix()
        record["harness"][f"{key}_sha256"] = sha256_file(path)
    record["execution_boundary"].update(
        {
            "python_launcher_bypassed": True,
            "python_worker_executable": str(worker),
            "explicit_extension_acceptance_passed": False,
            "structured_completion_required": True,
            "free_text_fallback_admitted": False,
        }
    )
    record["artifacts"]["report_schema"] = "report-schema.json"
    record["artifacts"]["captured_report"] = "captured-report.json"
    record["artifacts"]["captured_report_sha256"] = None
    record["artifacts"]["prepared_sha256"].update(
        {
            "policy": sha256_file(policy_path),
            "backend_copy": sha256_file(backend_copy),
            "report_schema": sha256_file(run_dir / "report-schema.json"),
        }
    )
    write_json(record_path, record)
    return result


def _explicit_extension_check(run_dir: Path) -> dict[str, Any]:
    resolved = run_dir.resolve()
    invocation = load_json(resolved / "pi-invocation.json")
    metadata = load_json(resolved / "pi-multi-format-sandbox.json")
    policy = load_json(resolved / "pi-policy.json")
    argv = invocation["argv"]
    extension = argv[argv.index("--extension") + 1]
    command = [
        metadata["node_binary"],
        invocation["executable"],
        "--offline",
        "--no-session",
        "--no-extensions",
        "--extension",
        extension,
        "--no-skills",
        "--no-prompt-templates",
        "--no-themes",
        "--no-context-files",
        "--no-approve",
        "--list-models",
    ]
    result = run_seatbelt_command(
        Path(metadata["profile_path"]),
        command,
        cwd=Path(policy["workspace_root"]),
        environment=pi_sandbox_environment(metadata, invocation),
        timeout_seconds=20.0,
    )
    return {
        "check_id": "explicit_extension_loads_under_seatbelt",
        "passed": result.returncode == 0,
        "expected_returncode": 0,
        "observed_returncode": result.returncode,
        "detail": "The exact five-tool extension and policy load before inference.",
        "stderr_nonempty": bool(result.stderr),
    }


def sandbox_check(run_dir: Path) -> dict[str, Any]:
    with _configured_base():
        result = validate_pi_multi_format_v02_seatbelt(run_dir)
    extension_check = _explicit_extension_check(run_dir)
    result["checks"].append(extension_check)
    result["passed"] = result["passed"] and extension_check["passed"]
    acceptance = run_dir.resolve() / "pi-sandbox-acceptance.json"
    write_json(acceptance, result)
    record_path = run_dir.resolve() / "run.json"
    record = load_json(record_path)
    record["execution_boundary"]["sandbox_acceptance_passed"] = result["passed"]
    record["execution_boundary"]["explicit_extension_acceptance_passed"] = extension_check[
        "passed"
    ]
    record["execution_boundary"]["sandbox_acceptance_sha256"] = sha256_file(acceptance)
    write_json(record_path, record)
    if not result["passed"]:
        raise RunnerError("Pi v0.4 explicit extension acceptance failed")
    return result


def _admit_structured_report_transport(
    repo_root: Path, run_dir: Path, result: dict[str, Any]
) -> dict[str, Any]:
    """Admit only one schema-valid report captured by finish_report."""
    resolved = run_dir.resolve()
    record_path = resolved / "run.json"
    record = load_json(record_path)
    policy = load_json(resolved / record["artifacts"]["policy"])
    captured = resolved / record["artifacts"]["captured_report"]
    report = None
    failure = "finish_report_not_called"
    finish_calls = record.get("trajectory", {}).get("finish_report_calls", 0)
    if captured.is_file() and not captured.is_symlink() and finish_calls == 1:
        data = captured.read_bytes()
        if len(data) <= policy["maximum_report_bytes"] + 1:
            try:
                candidate = json.loads(data)
                validate_json(candidate, load_json(resolved / "report-schema.json"))
            except (json.JSONDecodeError, JsonSchemaError):
                failure = "invalid_finish_report"
            else:
                report = candidate
                failure = None
    elif captured.exists():
        failure = "ambiguous_finish_report"
    candidate_path = resolved / "candidate-report.json"
    if report is not None:
        write_json(candidate_path, report)
        record["artifacts"]["candidate_report"] = candidate_path.name
        record["artifacts"]["candidate_report_sha256"] = sha256_file(candidate_path)
        record["artifacts"]["captured_report_sha256"] = sha256_file(captured)
    else:
        record["artifacts"]["candidate_report"] = None
        record["artifacts"]["candidate_report_sha256"] = None
        record["artifacts"]["captured_report_sha256"] = (
            sha256_file(captured) if captured.is_file() else None
        )
    trajectory = record["trajectory"]
    trajectory.update(
        {
            "final_report_parse_status": "valid" if report is not None else "invalid",
            "final_report_parse_failure": failure,
            "strict_transport_compliance": report is not None,
            "response_normalization_applied": False,
            "response_normalization_kind": "none",
            "report_transport": "structured_finish_report_tool",
            "free_text_fallback_admitted": False,
        }
    )
    write_json(record_path, record)
    result.update(
        {
            "final_report_parse_status": trajectory["final_report_parse_status"],
            "strict_transport_compliance": trajectory["strict_transport_compliance"],
            "report_transport": trajectory["report_transport"],
        }
    )
    return result


def run(repo_root: Path, run_dir: Path) -> dict[str, Any]:
    record = load_json(run_dir.resolve() / "run.json")
    boundary = record.get("execution_boundary", {})
    if (
        boundary.get("sandbox_acceptance_passed") is not True
        or boundary.get("explicit_extension_acceptance_passed") is not True
    ):
        raise RunnerError("Pi v0.4 requires fresh full Seatbelt acceptance")
    with _configured_base():
        result = base.execute_pi_multi_format_run(repo_root, run_dir)
    return _admit_structured_report_transport(repo_root, run_dir, result)


def finalize(repo_root: Path, run_dir: Path) -> dict[str, Any]:
    with _configured_base():
        return base.finalize_pi_multi_format_run(repo_root, run_dir)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--model", required=True)
    prepare_parser.add_argument("--results-dir", type=Path, default=Path("results/agentic-runs"))
    prepare_parser.add_argument("--host", default="http://127.0.0.1:11434")
    for name in ("sandbox-check", "run", "finalize"):
        command = subparsers.add_parser(name)
        command.add_argument("--run-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    if args.command == "prepare":
        result = prepare(
            repo_root,
            base.PiMultiFormatPrepareConfig(
                model=args.model, results_dir=args.results_dir, host=args.host
            ),
        )
    elif args.command == "sandbox-check":
        result = sandbox_check(args.run_dir)
    elif args.command == "run":
        result = run(repo_root, args.run_dir)
    else:
        result = finalize(repo_root, args.run_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
