"""Pinned Pi adapter for the three-case log-incident v0.5 protocol."""

from __future__ import annotations

import argparse
import json
import os
import platform
import secrets
import shutil
import signal
import subprocess
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
    _verify_workspace,
    build_pi_log_settings,
    summarize_pi_log_trajectory,
)
from .log_incident_v05 import (
    load_log_incident_case_v05,
    parse_incident_report_response_v05,
    verify_incident_report_v05,
)
from .macos_sandbox import SEATBELT_EXECUTABLE, pi_sandbox_environment
from .macos_sandbox_log import (
    validate_pi_log_seatbelt,
    write_pi_log_seatbelt_artifacts,
)
from .runner import (
    RunnerError,
    git_commit,
    load_json,
    resolve_repo_path,
    sha256_file,
    utc_now,
    write_json,
)


DEFAULT_HARNESS_PATH = Path("tasks/agentic/track-b/pi-log-v0.5.json")
HARNESS_ID = "pi-log-v0.5"
PROTOCOL_ID = "agentic-log-incident-v0.5"


@dataclass(frozen=True)
class PiLogV05PrepareConfig:
    """Inputs captured during no-inference Pi Log v0.5 preparation."""

    model: str
    case_path: Path
    harness_path: Path = DEFAULT_HARNESS_PATH
    results_dir: Path = Path("results/agentic-runs")
    host: str = "http://127.0.0.1:11434"


def load_pi_log_v05_harness(
    repo_root: Path, harness_path: Path = DEFAULT_HARNESS_PATH
) -> dict[str, Any]:
    """Validate Pi Log v0.5 definitions and the installed pinned package."""
    resolved_harness = resolve_repo_path(repo_root, harness_path)
    harness = load_json(resolved_harness)
    if (
        harness.get("schema_version") != "1.0.0"
        or harness.get("harness_id") != HARNESS_ID
        or harness.get("harness_family") != "pinned_pi"
        or harness.get("status") != "qualification_candidate"
    ):
        raise RunnerError("Unexpected Pi Log v0.5 harness identity or status")
    integration = harness.get("integration")
    package = harness.get("package")
    if not isinstance(integration, dict) or not isinstance(package, dict):
        raise RunnerError("Pi Log v0.5 integration or package identity is missing")
    if integration.get("tools") != ["read"]:
        raise RunnerError("Pi Log v0.5 must expose exactly the native read tool")
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
        raise RunnerError("Pi Log v0.5 discovered state or capabilities are enabled")

    protocol_path = _artifact(repo_root, harness, "protocol_path", "Pi Log protocol")
    prompt_path = _artifact(repo_root, harness, "system_prompt_path", "Pi Log system prompt")
    inventory_path = _artifact(
        repo_root, harness, "capability_inventory_path", "Pi Log capability inventory"
    )
    isolation_path = _artifact(
        repo_root, harness, "isolation_profile_path", "Pi Log isolation profile"
    )
    extension_path = _artifact(
        repo_root, integration, "explicit_extension", "Pi Log policy extension"
    )
    protocol = load_json(protocol_path)
    inventory = load_json(inventory_path)
    isolation = load_json(isolation_path)
    if (
        protocol.get("protocol_id") != PROTOCOL_ID
        or protocol.get("track") != "B"
        or protocol.get("study_mode") != "development_qualification"
        or protocol.get("status") != harness["status"]
        or protocol.get("task_representation_version") != "0.5"
        or protocol.get("report_contract_version") != "2.0.0"
        or protocol.get("outcome_model", {}).get("primary")
        != "semantic_verified_success"
        or protocol.get("outcome_model", {}).get(
            "supplemental_free_text_claim_review_required"
        )
        is not True
    ):
        raise RunnerError("Unexpected Pi Log v0.5 protocol identity")
    subset = protocol.get("task_subset")
    if not isinstance(subset, list) or len(subset) != 3:
        raise RunnerError("Pi Log v0.5 requires exactly three selected cases")
    identities = {
        (item.get("case_id"), item.get("case_version"), item.get("case_path"))
        for item in subset
        if isinstance(item, dict)
    }
    if len(identities) != 3:
        raise RunnerError("Pi Log v0.5 task identities must be unique")
    if (
        inventory.get("inventory_id") != HARNESS_ID
        or inventory.get("status") != harness["status"]
        or inventory.get("task_subset_size") != 3
        or [item.get("name") for item in inventory.get("model_visible_tools", [])]
        != ["read"]
    ):
        raise RunnerError("Pi Log v0.5 capability inventory differs")
    if (
        isolation.get("isolation_profile_id") != HARNESS_ID
        or isolation.get("status") != harness["status"]
        or isolation.get("workspace", {}).get("other_case_fixtures_absent") is not True
        or isolation.get("process", {}).get("candidate_code_executed") is not False
    ):
        raise RunnerError("Unexpected Pi Log v0.5 isolation profile")

    limits = protocol.get("normal_capability_limits")
    safeguards = protocol.get("runaway_operation_safeguards")
    inference = protocol.get("inference_defaults")
    if not all(isinstance(item, dict) for item in (limits, safeguards, inference)):
        raise RunnerError("Pi Log v0.5 limit objects are incomplete")
    for key in ("maximum_active_wall_time_seconds", "provider_request_timeout_seconds"):
        _positive_integer(limits.get(key), key)
    for key in (
        "maximum_agent_turns",
        "maximum_total_output_tokens",
        "maximum_protocol_errors",
    ):
        if limits.get(key) is not None:
            raise RunnerError(f"Pi Log v0.5 must keep {key} measurement-only")
    _positive_integer(safeguards.get("maximum_file_reads"), "maximum_file_reads")
    for key in ("num_ctx", "num_predict_per_turn", "request_timeout_seconds"):
        _positive_integer(inference.get(key), key)
    if inference["request_timeout_seconds"] != limits["provider_request_timeout_seconds"]:
        raise RunnerError("Pi Log v0.5 provider timeouts differ")

    integration_root = resolve_repo_path(repo_root, PI_INTEGRATION_ROOT)
    package_json_path = integration_root / "package.json"
    package_lock_path = integration_root / "package-lock.json"
    package_json = load_json(package_json_path)
    package_lock = load_json(package_lock_path)
    name = package.get("name")
    version = package.get("version")
    if package_json.get("dependencies", {}).get(name) != version:
        raise RunnerError("Pi package.json does not use the frozen exact version")
    locked = package_lock.get("packages", {}).get(f"node_modules/{name}")
    if not isinstance(locked, dict) or locked.get("version") != version:
        raise RunnerError("Pi package-lock version mismatch")
    if locked.get("integrity") != package.get("npm_integrity"):
        raise RunnerError("Pi package-lock integrity mismatch")
    binary = integration_root / "node_modules" / ".bin" / "pi"
    if not binary.exists():
        raise RunnerError("Pinned Pi is not installed in integrations/pi")
    observed_version = _package_version(binary, integration_root)
    if observed_version != version:
        raise RunnerError(
            f"Installed Pi version mismatch: expected {version}, found {observed_version}"
        )
    return {
        "harness": harness,
        "harness_path": resolved_harness,
        "protocol": protocol,
        "protocol_path": protocol_path,
        "system_prompt": prompt_path.read_text(encoding="utf-8").strip(),
        "system_prompt_path": prompt_path,
        "capability_inventory": inventory,
        "capability_inventory_path": inventory_path,
        "isolation_profile": isolation,
        "isolation_profile_path": isolation_path,
        "extension_path": extension_path,
        "integration_root": integration_root,
        "package_json_path": package_json_path,
        "package_lock_path": package_lock_path,
        "binary": binary,
        "observed_version": observed_version,
        "node_version": _node_version(integration_root),
    }


def load_pi_log_v05_case(
    repo_root: Path,
    case_path: Path,
    harness_path: Path = DEFAULT_HARNESS_PATH,
) -> dict[str, Any]:
    """Bind exactly one selected v0.5 case to the pinned Pi condition."""
    pi = load_pi_log_v05_harness(repo_root, harness_path)
    loaded = load_log_incident_case_v05(repo_root, case_path)
    relative_case = loaded["case_path"].relative_to(repo_root).as_posix()
    selected = {
        item.get("case_path"): (item.get("case_id"), item.get("case_version"))
        for item in pi["protocol"]["task_subset"]
        if isinstance(item, dict)
    }
    if selected.get(relative_case) != (
        loaded["case"]["case_id"],
        loaded["case"]["case_version"],
    ):
        raise RunnerError("Incident case is outside the Pi Log v0.5 subset")
    return {**loaded, **pi, "relative_case_path": relative_case}


def build_pi_log_v05_policy(
    loaded: dict[str, Any], workspace: Path, audit_path: Path
) -> dict[str, Any]:
    """Build a selected-case one-tool policy without normal effort caps."""
    return {
        "schema_version": "1.0.0",
        "policy_id": "pi-log-readonly-v0.2",
        "workspace_root": str(workspace.resolve()),
        "audit_log_path": str(audit_path.resolve()),
        "readable_paths": loaded["case"]["candidate_context"]["files"],
        "allowed_tools": ["read"],
        "maximum_file_reads": loaded["protocol"]["runaway_operation_safeguards"][
            "maximum_file_reads"
        ],
        "parent_maximum_active_wall_time_seconds": loaded["protocol"][
            "normal_capability_limits"
        ]["maximum_active_wall_time_seconds"],
    }


def _pi_user_message(loaded: dict[str, Any]) -> str:
    task = loaded["task_path"].read_text(encoding="utf-8").strip()
    files = "\n".join(f"- {path}" for path in loaded["case"]["candidate_context"]["files"])
    schema = json.dumps(loaded["schema"], ensure_ascii=False, indent=2, sort_keys=True)
    limits = loaded["protocol"]["normal_capability_limits"]
    reads = loaded["protocol"]["runaway_operation_safeguards"]["maximum_file_reads"]
    return (
        f"# Task\n\n{task}\n\n"
        f"# Candidate-visible files\n\n{files}\n\n"
        f"# Final JSON Schema\n\n{schema}\n\n"
        "# Run boundary\n\n"
        f"- Active agent time: {limits['maximum_active_wall_time_seconds']} seconds.\n"
        "- Turns and tokens have no normal cap.\n"
        f"- Emergency read safeguard: {reads}.\n"
        "- Only the selected case is present; other fixtures are unavailable.\n"
        "- Return exactly the final JSON object after completing the investigation."
    )


def prepare_pi_log_v05_run(
    repo_root: Path, config: PiLogV05PrepareConfig
) -> dict[str, Any]:
    """Prepare Pi v0.5 and a selected-case sandbox without inference."""
    host = validate_local_ollama_host(config.host)
    if not isinstance(config.model, str) or not config.model.strip():
        raise RunnerError("Pi Log v0.5 model name must be non-empty")
    loaded = load_pi_log_v05_case(repo_root, config.case_path, config.harness_path)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"pi-log-v05-run-{timestamp}-{secrets.token_hex(4)}"
    results_dir = resolve_repo_path(repo_root, config.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    run_dir = results_dir / run_id
    run_dir.mkdir(parents=False, exist_ok=False)
    workspace = run_dir / "workspace"
    shutil.copytree(loaded["fixture_root"], workspace)
    contamination = _verify_workspace(workspace, loaded)
    if not contamination["passed"]:
        raise RunnerError("Fresh Pi Log v0.5 workspace differs from the manifest")
    agent_dir = run_dir / "pi-agent"
    agent_dir.mkdir()

    protocol = loaded["protocol"]
    inference = protocol["inference_defaults"]
    integration = loaded["harness"]["integration"]
    provider_base_url = host + "/v1"
    write_json(
        agent_dir / "models.json",
        {
            "providers": {
                "ollama": {
                    "baseUrl": provider_base_url,
                    "api": "openai-completions",
                    "apiKey": "ollama",
                    "compat": {
                        "supportsDeveloperRole": False,
                        "supportsReasoningEffort": False,
                    },
                    "models": [
                        {
                            "id": config.model,
                            "name": config.model,
                            "reasoning": False,
                            "input": ["text"],
                            "contextWindow": inference["num_ctx"],
                            "maxTokens": inference["num_predict_per_turn"],
                            "samplingParams": {
                                "temperature": inference["temperature"],
                                "seed": inference["seed"],
                            },
                            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                        }
                    ],
                }
            }
        },
    )
    write_json(agent_dir / "settings.json", build_pi_log_settings(config.model, protocol))
    policy_path = run_dir / "pi-policy.json"
    policy = build_pi_log_v05_policy(
        loaded, workspace, run_dir / "pi-policy-audit.jsonl"
    )
    write_json(policy_path, policy)
    timeout_seconds = protocol["normal_capability_limits"]["maximum_active_wall_time_seconds"]
    invocation = {
        "schema_version": "1.0.0",
        "cwd": str(workspace.resolve()),
        "executable": str(loaded["binary"].resolve()),
        "argv": [
            "--mode",
            "json",
            "--print",
            "--provider",
            integration["provider"],
            "--model",
            config.model,
            "--api-key",
            "ollama",
            "--thinking",
            "off",
            "--tools",
            "read",
            "--no-session",
            "--no-extensions",
            "--extension",
            str(loaded["extension_path"].resolve()),
            "--no-skills",
            "--no-prompt-templates",
            "--no-themes",
            "--no-context-files",
            "--no-approve",
            "--offline",
            "--system-prompt",
            loaded["system_prompt"],
            "--",
            _pi_user_message(loaded),
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
        "timeout_seconds": timeout_seconds,
        "timeout_clock": "parent_process_monotonic_wait",
        "requires_os_sandbox": True,
    }
    invocation_path = run_dir / "pi-invocation.json"
    write_json(invocation_path, invocation)
    sandbox = write_pi_log_seatbelt_artifacts(repo_root, run_dir, invocation, policy)

    package = loaded["harness"]["package"]
    artifact_paths = {
        "harness": loaded["harness_path"],
        "protocol": loaded["protocol_path"],
        "system_prompt": loaded["system_prompt_path"],
        "capability_inventory": loaded["capability_inventory_path"],
        "isolation_profile": loaded["isolation_profile_path"],
        "extension": loaded["extension_path"],
    }
    record: dict[str, Any] = {
        "schema_version": "1.0.0",
        "run_id": run_id,
        "track": "B",
        "study_mode": "development_qualification",
        "state": "prepared_not_executed",
        "prepared_at": utc_now(),
        "harness": {
            "harness_id": HARNESS_ID,
            "harness_family": loaded["harness"]["harness_family"],
            "harness_status": loaded["harness"]["status"],
            **{
                f"{key}_path": path.relative_to(repo_root).as_posix()
                for key, path in artifact_paths.items()
            },
            **{f"{key}_sha256": sha256_file(path) for key, path in artifact_paths.items()},
            "adapter_path": "local_llm_benchmark/log_incident_pi_v05.py",
            "adapter_sha256": sha256_file(Path(__file__)),
            "sandbox_adapter_path": "local_llm_benchmark/macos_sandbox_log.py",
            "sandbox_adapter_sha256": sha256_file(
                repo_root / "local_llm_benchmark/macos_sandbox_log.py"
            ),
            "verifier_path": "local_llm_benchmark/log_incident_v05.py",
            "verifier_sha256": sha256_file(
                repo_root / "local_llm_benchmark/log_incident_v05.py"
            ),
            "package_name": package["name"],
            "package_version": package["version"],
            "package_integrity": package["npm_integrity"],
            "package_lock_sha256": sha256_file(loaded["package_lock_path"]),
            "git_commit": git_commit(repo_root),
        },
        "case": {
            "case_id": loaded["case"]["case_id"],
            "case_version": loaded["case"]["case_version"],
            "case_path": loaded["relative_case_path"],
            "case_definition_sha256": sha256_file(loaded["case_path"]),
            "task_family": loaded["case"]["task_family"],
            "fixture_manifest_sha256": loaded["manifest_sha256"],
            "task_sha256": loaded["task_sha256"],
            "visible_criteria_sha256": sha256_file(loaded["criteria_path"]),
            "response_normalization_sha256": sha256_file(
                loaded["normalization_path"]
            ),
            "report_schema_sha256": sha256_file(loaded["schema_path"]),
            "benchmark_card_sha256": sha256_file(loaded["card_path"]),
            "ground_truth_sha256": sha256_file(loaded["ground_truth_path"]),
            "reference_report_sha256": sha256_file(loaded["reference_report_path"]),
            "verifier_version": loaded["case"]["verification"]["version"],
            "candidate_visible_files": loaded["case"]["candidate_context"]["files"],
        },
        "deployment": {
            "requested_model": config.model,
            "ollama_base_url": provider_base_url,
            "options": inference,
        },
        "capability_boundary": {
            "maximum_active_wall_time_seconds": timeout_seconds,
            "provider_request_timeout_seconds": inference["request_timeout_seconds"],
            "agent_turns": "measurement_only",
            "total_output_tokens": "measurement_only",
            "maximum_file_reads_emergency": policy["maximum_file_reads"],
        },
        "execution_boundary": {
            "selected_case_only": True,
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
        "contamination_check": {**contamination, "earlier_run_artifacts_visible": False},
        "environment": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "node_version": loaded["node_version"],
        },
        "artifacts": {
            "workspace": "workspace",
            "pi_agent_dir": "pi-agent",
            "policy": "pi-policy.json",
            "invocation": "pi-invocation.json",
            "sandbox_profile": "pi-log-sandbox.sb",
            "sandbox_metadata": "pi-log-sandbox.json",
            "candidate_response": None,
            "candidate_response_sha256": None,
            "candidate_report": None,
            "candidate_report_sha256": None,
            "prepared_sha256": {
                "invocation": sha256_file(invocation_path),
                "policy": sha256_file(policy_path),
                "sandbox_profile": sandbox["profile_sha256"],
                "sandbox_metadata": sha256_file(run_dir / "pi-log-sandbox.json"),
                "settings": sha256_file(agent_dir / "settings.json"),
                "models": sha256_file(agent_dir / "models.json"),
            },
        },
    }
    write_json(run_dir / "run.json", record)
    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "state": record["state"],
        "model": config.model,
        "case_id": loaded["case"]["case_id"],
        "case_version": loaded["case"]["case_version"],
        "pi_version": loaded["observed_version"],
        "inference_requests_made": 0,
        "candidate_code_executed": False,
        "next_requirement": "Run the no-inference Pi Log v0.5 Seatbelt acceptance.",
    }


def _load_prepared(
    repo_root: Path, run_dir: Path, allowed_states: set[str]
) -> dict[str, Any]:
    resolved = resolve_repo_path(repo_root, run_dir)
    record_path = resolved / "run.json"
    record = load_json(record_path)
    if record.get("harness", {}).get("harness_id") != HARNESS_ID:
        raise RunnerError("Run does not belong to Pi Log v0.5")
    if record.get("state") not in allowed_states:
        raise RunnerError(
            f"Pi Log v0.5 state must be one of {sorted(allowed_states)}, "
            f"found {record.get('state')!r}"
        )
    loaded = load_pi_log_v05_case(
        repo_root,
        Path(record["case"]["case_path"]),
        Path(record["harness"]["harness_path"]),
    )
    harness_record = record["harness"]
    case_record = record["case"]
    current = {
        "harness_sha256": sha256_file(loaded["harness_path"]),
        "protocol_sha256": sha256_file(loaded["protocol_path"]),
        "system_prompt_sha256": sha256_file(loaded["system_prompt_path"]),
        "capability_inventory_sha256": sha256_file(loaded["capability_inventory_path"]),
        "isolation_profile_sha256": sha256_file(loaded["isolation_profile_path"]),
        "extension_sha256": sha256_file(loaded["extension_path"]),
        "adapter_sha256": sha256_file(Path(__file__)),
        "sandbox_adapter_sha256": sha256_file(
            repo_root / "local_llm_benchmark/macos_sandbox_log.py"
        ),
        "verifier_sha256": sha256_file(repo_root / "local_llm_benchmark/log_incident_v05.py"),
        "package_lock_sha256": sha256_file(loaded["package_lock_path"]),
        "case_definition_sha256": sha256_file(loaded["case_path"]),
        "fixture_manifest_sha256": loaded["manifest_sha256"],
        "task_sha256": loaded["task_sha256"],
        "report_schema_sha256": sha256_file(loaded["schema_path"]),
        "benchmark_card_sha256": sha256_file(loaded["card_path"]),
        "ground_truth_sha256": sha256_file(loaded["ground_truth_path"]),
        "reference_report_sha256": sha256_file(loaded["reference_report_path"]),
    }
    mismatches = []
    for key, observed in current.items():
        owner = harness_record if key in harness_record else case_record
        if owner.get(key) != observed:
            mismatches.append(key)
    if mismatches:
        raise RunnerError(
            "Pi Log v0.5 definition changed after preparation: "
            + ", ".join(sorted(mismatches))
        )
    artifacts = record["artifacts"]
    paths = {
        "invocation": resolved / artifacts["invocation"],
        "policy": resolved / artifacts["policy"],
        "sandbox_profile": resolved / artifacts["sandbox_profile"],
        "sandbox_metadata": resolved / artifacts["sandbox_metadata"],
        "settings": resolved / artifacts["pi_agent_dir"] / "settings.json",
        "models": resolved / artifacts["pi_agent_dir"] / "models.json",
    }
    for key, path in paths.items():
        _require_hash(path, artifacts["prepared_sha256"][key], key)
    sandbox = load_json(paths["sandbox_metadata"])
    if sandbox["profile_sha256"] != artifacts["prepared_sha256"]["sandbox_profile"]:
        raise RunnerError("Pi Log v0.5 sandbox metadata/profile mismatch")
    return {
        **loaded,
        "run_dir": resolved,
        "record_path": record_path,
        "record": record,
        "invocation": load_json(paths["invocation"]),
        "policy": load_json(paths["policy"]),
        "sandbox": sandbox,
        "profile_path": paths["sandbox_profile"],
    }


def execute_pi_log_v05_run(repo_root: Path, run_dir: Path) -> dict[str, Any]:
    """Run accepted Pi under Seatbelt and defer hidden verification."""
    loaded = _load_prepared(repo_root, run_dir, {"prepared_not_executed"})
    resolved = loaded["run_dir"]
    record = loaded["record"]
    acceptance_path = resolved / "pi-sandbox-acceptance.json"
    acceptance = load_json(acceptance_path)
    if not acceptance.get("passed") or not record["execution_boundary"].get(
        "sandbox_acceptance_passed"
    ):
        raise RunnerError("Pi Log v0.5 execution requires sandbox acceptance")
    _require_hash(
        acceptance_path,
        record["execution_boundary"]["sandbox_acceptance_sha256"],
        "sandbox acceptance",
    )
    if acceptance.get("profile_sha256") != loaded["sandbox"]["profile_sha256"]:
        raise RunnerError("Pi Log v0.5 acceptance belongs to another profile")
    pre_execution = _verify_workspace(
        resolved / record["artifacts"]["workspace"], loaded
    )
    if not pre_execution["passed"]:
        raise RunnerError("Pi Log v0.5 workspace drifted before execution")

    invocation = loaded["invocation"]
    events_path = Path(invocation["stdout_path"])
    stderr_path = Path(invocation["stderr_path"])
    audit_path = Path(loaded["policy"]["audit_log_path"])
    for path in (events_path, stderr_path):
        if path.exists() and path.stat().st_size:
            raise RunnerError(f"Prepared Pi Log v0.5 output is non-empty: {path.name}")
    if audit_path.stat().st_size:
        raise RunnerError("Prepared Pi Log v0.5 policy audit is non-empty")
    command = [
        str(SEATBELT_EXECUTABLE),
        "-f",
        str(loaded["profile_path"]),
        loaded["sandbox"]["node_binary"],
        invocation["executable"],
        *invocation["argv"],
    ]
    environment = pi_sandbox_environment(loaded["sandbox"], invocation)
    timeout_seconds = int(invocation["timeout_seconds"])
    record["state"] = "running"
    record["execution"] = {
        "started_at": utc_now(),
        "command_shape": "sandbox-exec -f PROFILE NODE PINNED_PI_ENTRYPOINT ARGS",
        "timeout_seconds": timeout_seconds,
        "timeout_clock": invocation["timeout_clock"],
    }
    write_json(loaded["record_path"], record)

    started = time.monotonic()
    timed_out = False
    returncode: int | None = None
    launch_error: str | None = None
    with events_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr_handle:
        try:
            process = subprocess.Popen(
                command,
                cwd=invocation["cwd"],
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=True,
                preexec_fn=_resource_limits(timeout_seconds),
            )
            try:
                returncode = process.wait(timeout=timeout_seconds)
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
    response_path = resolved / "candidate-response.txt"
    response_path.write_text((final_text or "") + "\n", encoding="utf-8")
    parsed = parse_incident_report_response_v05(final_text)
    report_path: Path | None = None
    if parsed["status"] == "valid":
        report_path = resolved / "candidate-report.json"
        write_json(report_path, parsed["report"])
    post_execution = _verify_workspace(
        resolved / record["artifacts"]["workspace"], loaded
    )
    trajectory["final_report_parse_status"] = parsed["status"]
    trajectory["final_report_parse_failure"] = parsed.get("failure_code")
    trajectory["strict_transport_compliance"] = parsed[
        "strict_transport_compliance"
    ]
    trajectory["response_normalization_applied"] = parsed[
        "normalization_applied"
    ]
    trajectory["response_normalization_kind"] = parsed["normalization_kind"]
    termination_reason = _termination_reason(
        timed_out=timed_out,
        launch_error=launch_error,
        returncode=returncode,
        trajectory=trajectory,
        workspace_unchanged=post_execution["passed"],
    )
    trajectory["termination_reason"] = termination_reason
    runtime_success = (
        launch_error is None
        and not timed_out
        and not trajectory["provider_request_timed_out"]
        and returncode == 0
        and trajectory["malformed_event_lines"] == 0
        and trajectory["malformed_audit_lines"] == 0
        and post_execution["passed"]
    )
    agent_valid = runtime_success and trajectory["agent_end_valid"]

    record = load_json(loaded["record_path"])
    record["state"] = "execution_complete_verification_pending"
    record["execution"].update(
        {
            "finished_at": utc_now(),
            "returncode": returncode,
            "timed_out": timed_out,
            "launch_error": launch_error,
            "runtime_success": runtime_success,
            "agent_termination_valid": agent_valid,
            "wall_time_seconds": wall_time,
            "workspace_integrity": post_execution,
        }
    )
    record["trajectory"] = trajectory
    record["execution_boundary"].update(
        {
            "inference_requests_made": trajectory["agent_turns"],
            "candidate_code_executed": False,
            "candidate_commands_executed": False,
            "candidate_workspace_changed": not post_execution["passed"],
            "hidden_verification_executed": False,
        }
    )
    record["artifacts"].update(
        {
            "candidate_response": "candidate-response.txt",
            "candidate_response_sha256": sha256_file(response_path),
            "candidate_report": "candidate-report.json" if report_path else None,
            "candidate_report_sha256": sha256_file(report_path) if report_path else None,
            "execution_sha256": {
                "events": sha256_file(events_path),
                "stderr": sha256_file(stderr_path),
                "policy_audit": sha256_file(audit_path),
            },
        }
    )
    write_json(loaded["record_path"], record)
    return {
        "run_id": record["run_id"],
        "state": record["state"],
        "runtime_success": runtime_success,
        "agent_termination_valid": agent_valid,
        "termination_reason": termination_reason,
        "final_report_parse_status": parsed["status"],
        "strict_transport_compliance": parsed["strict_transport_compliance"],
        "response_normalization_applied": parsed["normalization_applied"],
        "trajectory": trajectory,
        "hidden_verification_executed": False,
        "next_action": "python3 -m local_llm_benchmark.log_incident_pi_v05 finalize",
    }


def finalize_pi_log_v05_run(repo_root: Path, run_dir: Path) -> dict[str, Any]:
    """Verify one strict or deterministically normalized report after Pi exits."""
    loaded = _load_prepared(
        repo_root, run_dir, {"execution_complete_verification_pending"}
    )
    record = loaded["record"]
    for key, expected in record["artifacts"]["execution_sha256"].items():
        filename = {
            "events": "pi-events.jsonl",
            "stderr": "pi-stderr.txt",
            "policy_audit": "pi-policy-audit.jsonl",
        }[key]
        _require_hash(loaded["run_dir"] / filename, expected, filename)
    _require_hash(
        loaded["run_dir"] / record["artifacts"]["candidate_response"],
        record["artifacts"]["candidate_response_sha256"],
        "candidate response",
    )
    report: dict[str, Any] | None = None
    if record["artifacts"].get("candidate_report"):
        report_path = loaded["run_dir"] / record["artifacts"]["candidate_report"]
        _require_hash(
            report_path,
            record["artifacts"]["candidate_report_sha256"],
            "candidate report",
        )
        report = load_json(report_path)
    started = time.monotonic()
    verification = verify_incident_report_v05(
        repo_root, Path(record["case"]["case_path"]), report
    )
    verification_duration = time.monotonic() - started
    verification_path = loaded["run_dir"] / "final-verification.json"
    write_json(verification_path, verification)
    runtime_success = bool(record["execution"]["runtime_success"])
    agent_valid = bool(record["execution"]["agent_termination_valid"])
    semantic_verifier_success = bool(verification["semantic_verified_success"])
    semantic_verified_success = (
        runtime_success and agent_valid and semantic_verifier_success
    )
    strict_transport_compliance = bool(
        record["trajectory"].get("strict_transport_compliance")
    )
    if not runtime_success:
        failure_category = "infrastructure_or_runtime_failure"
        failure_type = record["trajectory"]["termination_reason"]
    elif not agent_valid:
        failure_category = "agent_failure"
        failure_type = record["trajectory"]["termination_reason"]
    elif not semantic_verifier_success:
        failure_category = "task_or_verification_failure"
        failure_type = verification.get("failure_code") or "verification_failed"
    else:
        failure_category = None
        failure_type = None
    record["state"] = "complete"
    record["completed_at"] = utc_now()
    record["trajectory"]["final_verification_wall_time_seconds"] = verification_duration
    record["outcome"] = {
        "runtime_success": runtime_success,
        "agent_termination_valid": agent_valid,
        "semantic_verifier_success": semantic_verifier_success,
        "semantic_verified_success": semantic_verified_success,
        "verified_success": semantic_verified_success,
        "strict_transport_compliance": strict_transport_compliance,
        "failure_category": failure_category,
        "failure_type": failure_type,
        "trajectory_termination_reason": record["trajectory"]["termination_reason"],
    }
    record["verification"] = verification
    record["execution_boundary"]["hidden_verification_executed"] = True
    record["artifacts"]["final_verification"] = "final-verification.json"
    record["artifacts"]["final_verification_sha256"] = sha256_file(verification_path)
    write_json(loaded["record_path"], record)
    return {
        "run_id": record["run_id"],
        "state": record["state"],
        **record["outcome"],
        "verification": {
            "essential_pass_count": verification.get("essential_pass_count", 0),
            "essential_check_count": verification.get("essential_check_count", 0),
        },
        "trajectory": record["trajectory"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare", help="Prepare without inference")
    prepare.add_argument("--model", required=True)
    prepare.add_argument("--case", type=Path, required=True)
    prepare.add_argument("--harness", type=Path, default=DEFAULT_HARNESS_PATH)
    prepare.add_argument("--results-dir", type=Path, default=Path("results/agentic-runs"))
    prepare.add_argument("--host", default="http://127.0.0.1:11434")
    sandbox = subparsers.add_parser("sandbox-check", help="Run no-inference Seatbelt checks")
    sandbox.add_argument("--run-dir", type=Path, required=True)
    execute = subparsers.add_parser("run", help="Execute one accepted live run")
    execute.add_argument("--run-dir", type=Path, required=True)
    finalize = subparsers.add_parser("finalize", help="Run deterministic verification")
    finalize.add_argument("--run-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    if args.command == "prepare":
        result = prepare_pi_log_v05_run(
            repo_root,
            PiLogV05PrepareConfig(
                model=args.model,
                case_path=args.case,
                harness_path=args.harness,
                results_dir=args.results_dir,
                host=args.host,
            ),
        )
    elif args.command == "sandbox-check":
        result = validate_pi_log_seatbelt(args.run_dir)
    elif args.command == "run":
        result = execute_pi_log_v05_run(repo_root, args.run_dir)
    else:
        result = finalize_pi_log_v05_run(repo_root, args.run_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
