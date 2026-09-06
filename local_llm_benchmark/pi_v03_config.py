"""No-inference configuration builder for the Pi v0.3 candidate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .runner import RunnerError, load_json, resolve_repo_path


PI_V03_HARNESS_PATH = Path("tasks/coding/track-b/pi-v0.3.json")


def load_pi_v03_candidate(
    repo_root: Path,
    harness_path: Path = PI_V03_HARNESS_PATH,
) -> dict[str, Any]:
    """Validate candidate identity and return its protocol and static artifacts."""
    resolved_harness = resolve_repo_path(repo_root, harness_path)
    harness = load_json(resolved_harness)
    if (
        harness.get("schema_version") != "1.0.0"
        or harness.get("harness_id") != "pi-v0.3"
        or harness.get("status") != "qualified_for_capability_sweep"
    ):
        raise RunnerError("Unexpected Pi v0.3 candidate identity")
    if harness.get("implementation_status") != (
        "live_adapter_implemented_no_inference_qualified"
    ):
        raise RunnerError("Unexpected Pi v0.3 implementation status")

    protocol_path = Path(harness["protocol_path"])
    resolved_protocol = resolve_repo_path(repo_root, protocol_path)
    protocol = load_json(resolved_protocol)
    if (
        protocol.get("schema_version") != "1.0.0"
        or protocol.get("protocol_id") != "coding-track-b-v0.3"
        or protocol.get("status") != "qualified_for_sweep_planning"
    ):
        raise RunnerError("Unexpected Track B v0.3 protocol identity")

    extension_path = resolve_repo_path(
        repo_root, Path(harness["integration"]["explicit_extension"])
    )
    prompt_path = resolve_repo_path(repo_root, Path(harness["system_prompt_path"]))
    for path, description in (
        (extension_path, "Pi v0.3 policy extension"),
        (prompt_path, "Pi system prompt"),
    ):
        if not path.is_file():
            raise RunnerError(f"{description} does not exist: {path}")

    return {
        "harness": harness,
        "harness_path": resolved_harness,
        "protocol": protocol,
        "protocol_path": resolved_protocol,
        "extension_path": extension_path,
        "system_prompt_path": prompt_path,
    }


def build_pi_v03_settings(model: str, protocol: dict[str, Any]) -> dict[str, Any]:
    """Build Pi settings with an explicit per-request transport timeout."""
    if not isinstance(model, str) or not model.strip():
        raise RunnerError("Pi v0.3 model name must be non-empty")
    timeout_seconds = protocol["normal_capability_limits"][
        "provider_request_timeout_seconds"
    ]
    timeout_ms = int(timeout_seconds * 1000)
    return {
        "defaultProvider": "ollama",
        "defaultModel": model,
        "enableInstallTelemetry": False,
        "enableAnalytics": False,
        "defaultProjectTrust": "never",
        "shellPath": "/bin/bash",
        "quietStartup": True,
        "compaction": {"enabled": False},
        "retry": {
            "enabled": False,
            "maxRetries": 0,
            "provider": {
                "maxRetries": 0,
                "timeoutMs": timeout_ms,
            },
        },
        "httpIdleTimeoutMs": timeout_ms,
    }


def build_pi_v03_policy(
    protocol: dict[str, Any],
    *,
    workspace_root: Path,
    audit_log_path: Path,
    readable_paths: list[str],
    writable_paths: list[str],
    public_test_command: str,
    maximum_write_bytes: int,
) -> dict[str, Any]:
    """Build extension policy without token, turn or extension-time aborts."""
    safeguards = protocol["runaway_operation_safeguards"]
    limits = protocol["normal_capability_limits"]
    policy = {
        "schema_version": "1.1.0",
        "workspace_root": str(workspace_root.resolve()),
        "audit_log_path": str(audit_log_path.resolve()),
        "readable_paths": readable_paths,
        "writable_paths": writable_paths,
        "public_test_command": public_test_command,
        "maximum_file_reads": safeguards["maximum_file_reads"],
        "maximum_file_writes": safeguards["maximum_file_writes"],
        "maximum_public_test_runs": safeguards["maximum_public_test_runs"],
        "maximum_write_bytes": maximum_write_bytes,
        "parent_maximum_active_wall_time_seconds": limits[
            "maximum_active_wall_time_seconds"
        ],
    }
    forbidden_limits = {
        "maximum_agent_turns",
        "maximum_total_output_tokens",
        "maximum_wall_time_seconds",
    }
    if forbidden_limits.intersection(policy):
        raise RunnerError("Pi v0.3 policy unexpectedly contains a normal effort limit")
    return policy


def build_pi_v03_candidate_configuration(
    repo_root: Path,
    *,
    model: str,
    workspace_root: Path,
    audit_log_path: Path,
    readable_paths: list[str],
    writable_paths: list[str],
    public_test_command: str,
    maximum_write_bytes: int,
) -> dict[str, Any]:
    """Build the versioned settings/policy pair without inference or file writes."""
    loaded = load_pi_v03_candidate(repo_root)
    protocol = loaded["protocol"]
    return {
        "harness_id": loaded["harness"]["harness_id"],
        "protocol_id": protocol["protocol_id"],
        "settings": build_pi_v03_settings(model, protocol),
        "policy": build_pi_v03_policy(
            protocol,
            workspace_root=workspace_root,
            audit_log_path=audit_log_path,
            readable_paths=readable_paths,
            writable_paths=writable_paths,
            public_test_command=public_test_command,
            maximum_write_bytes=maximum_write_bytes,
        ),
        "parent_timeout_seconds": protocol["normal_capability_limits"][
            "maximum_active_wall_time_seconds"
        ],
        "inference_requests_made": 0,
        "candidate_code_executed": False,
    }
