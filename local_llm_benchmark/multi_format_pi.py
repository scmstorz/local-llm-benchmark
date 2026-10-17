"""Pinned Pi 0.84.4 adapter for real multi-format artifacts v0.1."""

from __future__ import annotations

import argparse
import json
import os
import platform
import secrets
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .agentic import _normalized_relative_path, validate_local_ollama_host
from .log_incident_pi import (
    PI_INTEGRATION_ROOT,
    _artifact,
    _node_version,
    _package_version,
    _positive_integer,
    _require_hash,
    _resource_limits,
    _termination_reason,
    build_pi_log_settings,
    summarize_pi_log_trajectory,
)
from .log_incident_v05 import parse_incident_report_response_v05
from .macos_sandbox import SEATBELT_EXECUTABLE, pi_sandbox_environment
from .macos_sandbox_multi_format import (
    validate_pi_multi_format_seatbelt,
    write_pi_multi_format_seatbelt_artifacts,
)
from .multi_format_artifacts import ARTIFACTS, ArtifactToolError, verify_workspace
from .multi_format_document_analysis import (
    load_multi_format_case,
    verify_multi_format_report,
)
from .multi_format_mini import _copy_workspace
from .runner import (
    RunnerError,
    git_commit,
    load_json,
    resolve_repo_path,
    sha256_file,
    utc_now,
    write_json,
)


DEFAULT_HARNESS_PATH = Path("tasks/agentic/track-b/pi-multi-format-v0.1.json")
DEFAULT_CASE_PATH = Path(
    "tasks/agentic/multi-format-document-analysis/"
    "rollout-readiness-reconciliation/case-v0.1.json"
)
HARNESS_ID = "pi-multi-format-v0.1"
PROTOCOL_ID = "agentic-multi-format-v0.1"
TOOL_NAMES = ["list_artifacts", "read_docx", "read_pdf", "read_xlsx"]


@dataclass(frozen=True)
class PiMultiFormatPrepareConfig:
    """Inputs frozen during no-inference Pi preparation."""

    model: str
    case_path: Path = DEFAULT_CASE_PATH
    harness_path: Path = DEFAULT_HARNESS_PATH
    results_dir: Path = Path("results/agentic-runs")
    host: str = "http://127.0.0.1:11434"


def load_pi_multi_format_harness(
    repo_root: Path, harness_path: Path = DEFAULT_HARNESS_PATH
) -> dict[str, Any]:
    """Validate the Pi definition and exact installed package without inference."""
    path = resolve_repo_path(repo_root, harness_path)
    harness = load_json(path)
    if (
        harness.get("schema_version") != "1.0.0"
        or harness.get("harness_id") != HARNESS_ID
        or harness.get("harness_family") != "pinned_pi"
        or harness.get("status") != "qualification_candidate"
    ):
        raise RunnerError("Unexpected Pi multi-format harness definition")
    integration = harness.get("integration")
    package = harness.get("package")
    if not isinstance(integration, dict) or not isinstance(package, dict):
        raise RunnerError("Pi multi-format integration identity is missing")
    if integration.get("tools") != TOOL_NAMES:
        raise RunnerError("Pi multi-format tool surface changed")
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
        raise RunnerError("Pi multi-format discovered state is enabled")
    protocol_path = _artifact(repo_root, harness, "protocol_path", "protocol")
    prompt_path = _artifact(repo_root, harness, "system_prompt_path", "system prompt")
    inventory_path = _artifact(repo_root, harness, "capability_inventory_path", "capability inventory")
    isolation_path = _artifact(repo_root, harness, "isolation_profile_path", "isolation profile")
    extension_path = _artifact(repo_root, integration, "explicit_extension", "policy extension")
    protocol = load_json(protocol_path)
    inventory = load_json(inventory_path)
    isolation = load_json(isolation_path)
    if (
        protocol.get("protocol_id") != PROTOCOL_ID
        or protocol.get("track") != "B"
        or protocol.get("status") != harness["status"]
        or protocol.get("artifact_api", {}).get("operations") != TOOL_NAMES
    ):
        raise RunnerError("Unexpected Pi multi-format protocol")
    if not isinstance(protocol.get("task_subset"), list) or len(protocol["task_subset"]) != 1:
        raise RunnerError("Pi multi-format requires exactly one case")
    if (
        inventory.get("inventory_id") != HARNESS_ID
        or [item.get("name") for item in inventory.get("model_visible_tools", [])]
        != TOOL_NAMES
        or isolation.get("isolation_profile_id") != HARNESS_ID
        or isolation.get("evaluation", {}).get("canonical_extraction_outside_workspace")
        is not True
        or isolation.get("process", {}).get("candidate_code_executed") is not False
    ):
        raise RunnerError("Pi multi-format capability or isolation definition differs")
    limits = protocol.get("normal_capability_limits")
    safeguards = protocol.get("runaway_operation_safeguards")
    inference = protocol.get("inference_defaults")
    if not all(isinstance(value, dict) for value in (limits, safeguards, inference)):
        raise RunnerError("Pi multi-format limit objects are incomplete")
    for key in ("maximum_active_wall_time_seconds", "provider_request_timeout_seconds"):
        _positive_integer(limits.get(key), key)
    _positive_integer(safeguards.get("maximum_artifact_tool_calls"), "maximum_artifact_tool_calls")
    for key in ("num_ctx", "num_predict_per_turn", "request_timeout_seconds"):
        _positive_integer(inference.get(key), key)
    integration_root = resolve_repo_path(repo_root, PI_INTEGRATION_ROOT)
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
        raise RunnerError("Pinned Pi package identity differs")
    binary = integration_root / "node_modules" / ".bin" / "pi"
    if not binary.exists() or _package_version(binary, integration_root) != version:
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
        "node_version": _node_version(integration_root),
    }


def load_pi_multi_format_case(
    repo_root: Path,
    case_path: Path = DEFAULT_CASE_PATH,
    harness_path: Path = DEFAULT_HARNESS_PATH,
) -> dict[str, Any]:
    harness = load_pi_multi_format_harness(repo_root, harness_path)
    loaded = load_multi_format_case(repo_root, case_path)
    relative_case = loaded["case_path"].relative_to(repo_root).as_posix()
    selected = harness["protocol"]["task_subset"][0]
    if (
        selected.get("case_path") != relative_case
        or selected.get("case_id") != loaded["case"]["case_id"]
        or selected.get("case_version") != loaded["case"]["case_version"]
    ):
        raise RunnerError("Case is outside the Pi multi-format subset")
    fixture_root = resolve_repo_path(repo_root, Path(loaded["case"]["planned_artifact_root"]))
    return {**loaded, **harness, "relative_case_path": relative_case, "fixture_root": fixture_root}


def build_pi_multi_format_policy(
    loaded: dict[str, Any],
    workspace: Path,
    audit_path: Path,
    backend_path: Path,
    python_path: Path,
    pdftotext_path: Path,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "policy_id": "pi-multi-format-readonly-v0.1",
        "workspace_root": str(workspace.resolve()),
        "audit_log_path": str(audit_path.resolve()),
        "backend_path": str(backend_path.resolve()),
        "backend_sha256": sha256_file(backend_path),
        "python_path": str(python_path.resolve()),
        "python_sha256": sha256_file(python_path),
        "pdftotext_path": str(pdftotext_path.resolve()),
        "pdftotext_sha256": sha256_file(pdftotext_path),
        "allowed_tools": TOOL_NAMES,
        "maximum_tool_calls": loaded["protocol"]["runaway_operation_safeguards"]["maximum_artifact_tool_calls"],
        "parent_maximum_active_wall_time_seconds": loaded["protocol"]["normal_capability_limits"]["maximum_active_wall_time_seconds"],
    }


def _user_message(loaded: dict[str, Any]) -> str:
    task = loaded["task_path"].read_text(encoding="utf-8").strip()
    schema = json.dumps(loaded["schema"], ensure_ascii=False, indent=2, sort_keys=True)
    calls = loaded["protocol"]["runaway_operation_safeguards"]["maximum_artifact_tool_calls"]
    return (
        f"# Task\n\n{task}\n\n# Final JSON Schema\n\n{schema}\n\n"
        "# Run boundary\n\n"
        "- Artifact contents are initially hidden; call list_artifacts first.\n"
        f"- Emergency artifact-call safeguard: {calls}.\n"
        "- Hidden references, canonical extraction and verifier are unavailable.\n"
        "- Return exactly the final JSON object after the investigation."
    )


def prepare_pi_multi_format_run(
    repo_root: Path, config: PiMultiFormatPrepareConfig
) -> dict[str, Any]:
    """Prepare Pi, the shared backend and Seatbelt without inference."""
    host = validate_local_ollama_host(config.host)
    if not isinstance(config.model, str) or not config.model.strip():
        raise RunnerError("Pi multi-format model name must be non-empty")
    loaded = load_pi_multi_format_case(repo_root, config.case_path, config.harness_path)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"pi-multiformat-run-{timestamp}-{secrets.token_hex(4)}"
    results_dir = resolve_repo_path(repo_root, config.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    run_dir = results_dir / run_id
    run_dir.mkdir()
    workspace = run_dir / "workspace"
    contamination = _copy_workspace(loaded["fixture_root"], workspace)
    agent_dir = run_dir / "pi-agent"
    agent_dir.mkdir()
    source_backend = repo_root / "local_llm_benchmark/multi_format_artifacts.py"
    backend = run_dir / "artifact-backend.py"
    shutil.copyfile(source_backend, backend)
    python = Path(sys.executable).resolve()
    pdftotext_name = shutil.which("pdftotext")
    if pdftotext_name is None:
        raise RunnerError("pdftotext is required for Pi multi-format reads")
    pdftotext = Path(pdftotext_name).resolve()
    protocol = loaded["protocol"]
    inference = protocol["inference_defaults"]
    provider_url = host + "/v1"
    write_json(
        agent_dir / "models.json",
        {"providers": {"ollama": {"baseUrl": provider_url, "api": "openai-completions", "apiKey": "ollama", "compat": {"supportsDeveloperRole": False, "supportsReasoningEffort": False}, "models": [{"id": config.model, "name": config.model, "reasoning": False, "input": ["text"], "contextWindow": inference["num_ctx"], "maxTokens": inference["num_predict_per_turn"], "samplingParams": {"temperature": inference["temperature"], "seed": inference["seed"]}, "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}]}}},
    )
    write_json(agent_dir / "settings.json", build_pi_log_settings(config.model, protocol))
    policy_path = run_dir / "pi-policy.json"
    policy = build_pi_multi_format_policy(
        loaded, workspace, run_dir / "pi-policy-audit.jsonl", backend, python, pdftotext
    )
    write_json(policy_path, policy)
    integration = loaded["harness"]["integration"]
    timeout = protocol["normal_capability_limits"]["maximum_active_wall_time_seconds"]
    invocation = {
        "schema_version": "1.0.0",
        "cwd": str(workspace.resolve()),
        "executable": str(loaded["binary"].resolve()),
        "argv": [
            "--mode", "json", "--print", "--provider", "ollama", "--model", config.model,
            "--api-key", "ollama", "--thinking", "off", "--tools", ",".join(TOOL_NAMES),
            "--no-builtin-tools", "--no-session", "--no-extensions", "--extension", str(loaded["extension_path"].resolve()),
            "--no-skills", "--no-prompt-templates", "--no-themes", "--no-context-files",
            "--no-approve", "--offline", "--system-prompt", loaded["system_prompt"], "--", _user_message(loaded),
        ],
        "environment": {
            "PI_CODING_AGENT_DIR": str(agent_dir.resolve()),
            "PI_OFFLINE": "1",
            "PI_SKIP_VERSION_CHECK": "1",
            "PI_TELEMETRY": "0",
            "LOCAL_LLM_BENCHMARK_POLICY_PATH": str(policy_path.resolve()),
        },
        "stdout_path": str((run_dir / "pi-events.jsonl").resolve()),
        "stderr_path": str((run_dir / "pi-stderr.txt").resolve()),
        "timeout_seconds": timeout,
        "timeout_clock": "parent_process_monotonic_wait",
        "requires_os_sandbox": True,
    }
    invocation_path = run_dir / "pi-invocation.json"
    write_json(invocation_path, invocation)
    sandbox = write_pi_multi_format_seatbelt_artifacts(repo_root, run_dir, invocation, policy)
    definitions = {
        "harness": loaded["harness_path"],
        "protocol": loaded["protocol_path"],
        "system_prompt": loaded["system_prompt_path"],
        "capability_inventory": loaded["capability_inventory_path"],
        "isolation_profile": loaded["isolation_profile_path"],
        "extension": loaded["extension_path"],
        "adapter": repo_root / "local_llm_benchmark/multi_format_pi.py",
        "sandbox_adapter": repo_root / "local_llm_benchmark/macos_sandbox_multi_format.py",
        "artifact_backend": source_backend,
    }
    record = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "track": "B",
        "study_mode": "development_qualification",
        "state": "prepared_not_executed",
        "prepared_at": utc_now(),
        "harness": {
            "harness_id": HARNESS_ID,
            "harness_family": "pinned_pi",
            **{f"{key}_path": path.relative_to(repo_root).as_posix() for key, path in definitions.items()},
            **{f"{key}_sha256": sha256_file(path) for key, path in definitions.items()},
            "package_version": loaded["harness"]["package"]["version"],
            "package_integrity": loaded["harness"]["package"]["npm_integrity"],
            "package_lock_sha256": sha256_file(loaded["package_lock_path"]),
            "git_commit": git_commit(repo_root),
        },
        "case": {
            "case_id": loaded["case"]["case_id"],
            "case_version": loaded["case"]["case_version"],
            "case_path": loaded["relative_case_path"],
            "case_definition_sha256": sha256_file(loaded["case_path"]),
            "task_sha256": sha256_file(loaded["task_path"]),
            "report_schema_sha256": sha256_file(loaded["schema_path"]),
            "ground_truth_path": loaded["truth_path"].relative_to(repo_root).as_posix(),
            "ground_truth_sha256": sha256_file(loaded["truth_path"]),
            "canonical_path": loaded["canonical_path"].relative_to(repo_root).as_posix(),
            "canonical_sha256": sha256_file(loaded["canonical_path"]),
            "reference_report_sha256": sha256_file(loaded["reference_report_path"]),
            "candidate_visible_files": list(ARTIFACTS),
        },
        "deployment": {"requested_model": config.model, "ollama_base_url": provider_url, "options": inference},
        "execution_boundary": {
            "artifact_only_workspace": True,
            "inference_requests_made": 0,
            "candidate_code_executed": False,
            "candidate_commands_executed": False,
            "candidate_workspace_writable": False,
            "requires_os_sandbox": True,
            "sandbox_backend": sandbox["backend"],
            "sandbox_profile_sha256": sandbox["profile_sha256"],
            "sandbox_acceptance_passed": False,
            "hidden_verification_executed": False,
        },
        "contamination_check": contamination,
        "environment": {"system": platform.system(), "release": platform.release(), "machine": platform.machine(), "python_version": platform.python_version(), "node_version": loaded["node_version"]},
        "artifacts": {
            "workspace": "workspace",
            "pi_agent_dir": "pi-agent",
            "policy": policy_path.name,
            "invocation": invocation_path.name,
            "sandbox_profile": "pi-multi-format-sandbox.sb",
            "sandbox_metadata": "pi-multi-format-sandbox.json",
            "backend_copy": backend.name,
            "candidate_response": None,
            "candidate_report": None,
            "prepared_sha256": {
                "invocation": sha256_file(invocation_path),
                "policy": sha256_file(policy_path),
                "sandbox_profile": sandbox["profile_sha256"],
                "sandbox_metadata": sha256_file(run_dir / "pi-multi-format-sandbox.json"),
                "settings": sha256_file(agent_dir / "settings.json"),
                "models": sha256_file(agent_dir / "models.json"),
                "backend_copy": sha256_file(backend),
            },
        },
    }
    write_json(run_dir / "run.json", record)
    return {"run_id": run_id, "run_dir": str(run_dir), "state": record["state"], "pi_version": loaded["harness"]["package"]["version"], "inference_requests_made": 0, "next_requirement": "Run fresh no-inference Seatbelt acceptance."}


def _load_prepared(repo_root: Path, run_dir: Path, states: set[str]) -> dict[str, Any]:
    resolved = resolve_repo_path(repo_root, run_dir)
    record_path = resolved / "run.json"
    record = load_json(record_path)
    if record.get("harness", {}).get("harness_id") != HARNESS_ID or record.get("state") not in states:
        raise RunnerError("Unexpected Pi multi-format run identity or state")
    loaded = load_pi_multi_format_case(
        repo_root,
        Path(_normalized_relative_path(record["case"]["case_path"], "run case")),
        Path(_normalized_relative_path(record["harness"]["harness_path"], "run harness")),
    )
    definition_paths = {
        "harness": loaded["harness_path"],
        "protocol": loaded["protocol_path"],
        "system_prompt": loaded["system_prompt_path"],
        "capability_inventory": loaded["capability_inventory_path"],
        "isolation_profile": loaded["isolation_profile_path"],
        "extension": loaded["extension_path"],
        "adapter": repo_root / "local_llm_benchmark/multi_format_pi.py",
        "sandbox_adapter": repo_root / "local_llm_benchmark/macos_sandbox_multi_format.py",
        "artifact_backend": repo_root / "local_llm_benchmark/multi_format_artifacts.py",
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
        raise RunnerError("Pi multi-format definition changed: " + ", ".join(mismatches))
    if record["harness"].get("package_lock_sha256") != sha256_file(
        loaded["package_lock_path"]
    ):
        raise RunnerError("Pi multi-format package lock changed")
    try:
        verify_workspace(resolved / record["artifacts"]["workspace"])
    except ArtifactToolError as exc:
        raise RunnerError(f"Pi multi-format workspace drifted: {exc}") from exc
    paths = {
        "invocation": resolved / record["artifacts"]["invocation"],
        "policy": resolved / record["artifacts"]["policy"],
        "sandbox_profile": resolved / record["artifacts"]["sandbox_profile"],
        "sandbox_metadata": resolved / record["artifacts"]["sandbox_metadata"],
        "settings": resolved / record["artifacts"]["pi_agent_dir"] / "settings.json",
        "models": resolved / record["artifacts"]["pi_agent_dir"] / "models.json",
        "backend_copy": resolved / record["artifacts"]["backend_copy"],
    }
    for key, path in paths.items():
        _require_hash(path, record["artifacts"]["prepared_sha256"][key], key)
    policy = load_json(paths["policy"])
    if policy["backend_sha256"] != record["harness"]["artifact_backend_sha256"]:
        raise RunnerError("Pi copied artifact backend differs from the shared source")
    return {**loaded, "run_dir": resolved, "record_path": record_path, "record": record, "invocation": load_json(paths["invocation"]), "policy": policy, "sandbox": load_json(paths["sandbox_metadata"]), "profile_path": paths["sandbox_profile"]}


def _artifact_counts(audit_path: Path) -> dict[str, Any]:
    counts: dict[str, Any] = {}
    query_counts: dict[str, int] = {}
    if audit_path.is_file():
        for line in audit_path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event.get("counts"), dict):
                counts = event["counts"]
            if isinstance(event.get("query_counts"), dict):
                query_counts = event["query_counts"]
    return {**counts, "queries": query_counts}


def execute_pi_multi_format_run(repo_root: Path, run_dir: Path) -> dict[str, Any]:
    """Execute accepted Pi under Seatbelt; verification remains separate."""
    loaded = _load_prepared(repo_root, run_dir, {"prepared_not_executed"})
    resolved = loaded["run_dir"]
    record = loaded["record"]
    acceptance_path = resolved / "pi-sandbox-acceptance.json"
    if not record["execution_boundary"].get("sandbox_acceptance_passed"):
        raise RunnerError("Pi multi-format execution requires fresh Seatbelt acceptance")
    _require_hash(acceptance_path, record["execution_boundary"]["sandbox_acceptance_sha256"], "sandbox acceptance")
    acceptance = load_json(acceptance_path)
    if (
        acceptance.get("passed") is not True
        or acceptance.get("profile_sha256") != loaded["sandbox"]["profile_sha256"]
    ):
        raise RunnerError("Pi multi-format acceptance belongs to another profile")
    invocation = loaded["invocation"]
    events_path = Path(invocation["stdout_path"])
    stderr_path = Path(invocation["stderr_path"])
    audit_path = Path(loaded["policy"]["audit_log_path"])
    for path in (events_path, stderr_path, audit_path):
        if path.exists() and path.stat().st_size:
            raise RunnerError(f"Prepared Pi output is non-empty: {path.name}")
    command = [str(SEATBELT_EXECUTABLE), "-f", str(loaded["profile_path"]), loaded["sandbox"]["node_binary"], invocation["executable"], *invocation["argv"]]
    environment = pi_sandbox_environment(loaded["sandbox"], invocation)
    timeout = int(invocation["timeout_seconds"])
    record["state"] = "running"
    record["execution"] = {"started_at": utc_now(), "timeout_seconds": timeout, "command_shape": "sandbox-exec NODE PINNED_PI ARGS"}
    write_json(loaded["record_path"], record)
    started = time.monotonic()
    timed_out = False
    returncode = None
    launch_error = None
    with events_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        try:
            process = subprocess.Popen(command, cwd=invocation["cwd"], env=environment, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, start_new_session=True, preexec_fn=_resource_limits(timeout))
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    returncode = process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    returncode = process.wait(timeout=5)
        except (OSError, subprocess.SubprocessError) as exc:
            launch_error = f"{type(exc).__name__}: {exc}"
    wall_time = time.monotonic() - started
    trajectory, final_text = summarize_pi_log_trajectory(events_path, audit_path, wall_time)
    trajectory.update(_artifact_counts(audit_path))
    response_path = resolved / "candidate-response.txt"
    response_path.write_text((final_text or "") + "\n", encoding="utf-8")
    parsed = parse_incident_report_response_v05(final_text)
    report_path = None
    if parsed["status"] == "valid":
        report_path = resolved / "candidate-report.json"
        write_json(report_path, parsed["report"])
    workspace_unchanged = verify_workspace(resolved / "workspace")["passed"]
    trajectory.update({"final_report_parse_status": parsed["status"], "final_report_parse_failure": parsed.get("failure_code"), "strict_transport_compliance": parsed["strict_transport_compliance"], "response_normalization_applied": parsed["normalization_applied"], "response_normalization_kind": parsed["normalization_kind"]})
    reason = _termination_reason(timed_out=timed_out, launch_error=launch_error, returncode=returncode, trajectory=trajectory, workspace_unchanged=workspace_unchanged)
    trajectory["termination_reason"] = reason
    runtime_success = launch_error is None and not timed_out and returncode == 0 and not trajectory["provider_request_timed_out"] and trajectory["malformed_event_lines"] == 0 and trajectory["malformed_audit_lines"] == 0 and workspace_unchanged
    record = load_json(loaded["record_path"])
    record["state"] = "execution_complete_verification_pending"
    record["execution"].update({"finished_at": utc_now(), "returncode": returncode, "timed_out": timed_out, "launch_error": launch_error, "runtime_success": runtime_success, "agent_termination_valid": runtime_success and trajectory["agent_end_valid"], "wall_time_seconds": wall_time})
    record["trajectory"] = trajectory
    record["execution_boundary"].update({"inference_requests_made": trajectory["agent_turns"], "candidate_workspace_changed": not workspace_unchanged})
    record["artifacts"].update({"candidate_response": response_path.name, "candidate_response_sha256": sha256_file(response_path), "candidate_report": report_path.name if report_path else None, "candidate_report_sha256": sha256_file(report_path) if report_path else None, "execution_sha256": {"events": sha256_file(events_path), "stderr": sha256_file(stderr_path), "policy_audit": sha256_file(audit_path)}})
    write_json(loaded["record_path"], record)
    return {"run_id": record["run_id"], "state": record["state"], "runtime_success": runtime_success, "agent_termination_valid": record["execution"]["agent_termination_valid"], "termination_reason": reason, "final_report_parse_status": parsed["status"], "next_action": "python3 -m local_llm_benchmark.multi_format_pi finalize"}


def finalize_pi_multi_format_run(repo_root: Path, run_dir: Path) -> dict[str, Any]:
    """Verify one strict or deterministically normalized Pi report."""
    loaded = _load_prepared(repo_root, run_dir, {"execution_complete_verification_pending"})
    record = loaded["record"]
    report = None
    if record["artifacts"].get("candidate_report"):
        report_path = loaded["run_dir"] / record["artifacts"]["candidate_report"]
        _require_hash(report_path, record["artifacts"]["candidate_report_sha256"], "candidate report")
        report = load_json(report_path)
    started = time.monotonic()
    verification = verify_multi_format_report(repo_root, Path(record["case"]["case_path"]), report)
    duration = time.monotonic() - started
    verification_path = loaded["run_dir"] / "final-verification.json"
    write_json(verification_path, verification)
    runtime = bool(record["execution"]["runtime_success"])
    agent_valid = bool(record["execution"]["agent_termination_valid"])
    semantic = bool(verification["semantic_verified_success"])
    success = runtime and agent_valid and semantic
    record["state"] = "complete"
    record["completed_at"] = utc_now()
    record["trajectory"]["final_verification_wall_time_seconds"] = duration
    record["outcome"] = {"runtime_success": runtime, "agent_termination_valid": agent_valid, "semantic_verifier_success": semantic, "semantic_verified_success": success, "verified_success": success, "strict_transport_compliance": bool(record["trajectory"].get("strict_transport_compliance")), "failure_category": None if success else ("infrastructure_or_runtime_failure" if not runtime else "agent_failure" if not agent_valid else "task_or_verification_failure"), "trajectory_termination_reason": record["trajectory"]["termination_reason"]}
    record["verification"] = verification
    record["execution_boundary"]["hidden_verification_executed"] = True
    record["artifacts"]["final_verification"] = verification_path.name
    record["artifacts"]["final_verification_sha256"] = sha256_file(verification_path)
    write_json(loaded["record_path"], record)
    return {"run_id": record["run_id"], "state": "complete", **record["outcome"], "verification": {"essential_pass_count": verification["essential_pass_count"], "essential_check_count": verification["essential_check_count"]}, "trajectory": record["trajectory"]}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--model", required=True)
    prepare.add_argument("--case", type=Path, default=DEFAULT_CASE_PATH)
    prepare.add_argument("--harness", type=Path, default=DEFAULT_HARNESS_PATH)
    prepare.add_argument("--results-dir", type=Path, default=Path("results/agentic-runs"))
    prepare.add_argument("--host", default="http://127.0.0.1:11434")
    for name in ("sandbox-check", "run", "finalize"):
        command = subparsers.add_parser(name)
        command.add_argument("--run-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    if args.command == "prepare":
        result = prepare_pi_multi_format_run(repo_root, PiMultiFormatPrepareConfig(model=args.model, case_path=args.case, harness_path=args.harness, results_dir=args.results_dir, host=args.host))
    elif args.command == "sandbox-check":
        result = validate_pi_multi_format_seatbelt(args.run_dir)
    elif args.command == "run":
        result = execute_pi_multi_format_run(repo_root, args.run_dir)
    else:
        result = finalize_pi_multi_format_run(repo_root, args.run_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
