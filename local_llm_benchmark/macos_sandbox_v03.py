"""Language-aware macOS Seatbelt boundary for the Pi v0.3 harness."""

from __future__ import annotations

import json
import os
import platform
import shlex
import shutil
from pathlib import Path
from typing import Any

from .macos_sandbox import (
    SEATBELT_EXECUTABLE,
    _literal_rule,
    _metadata_ancestors,
    _node_binary,
    _sbpl_string,
    pi_sandbox_environment,
    run_seatbelt_command,
    validate_pi_seatbelt,
)
from .runner import RunnerError, sha256_file, utc_now, write_json


SEATBELT_V03_PROFILE_VERSION = "pi-macos-seatbelt-v0.2"


def resolve_public_test_executable(command: str) -> Path:
    """Resolve the exact language runtime named by a frozen test command."""
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        raise RunnerError(f"Cannot parse the frozen public-test command: {exc}") from exc
    if not tokens:
        raise RunnerError("The frozen public-test command is empty")
    candidate = Path(tokens[0])
    if candidate.is_absolute():
        executable = candidate.resolve()
    else:
        observed = shutil.which(tokens[0])
        if not observed:
            raise RunnerError(
                f"Public-test executable is not installed: {tokens[0]}"
            )
        executable = Path(observed).resolve()
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise RunnerError(
            f"Public-test executable is not an executable file: {executable}"
        )
    return executable


def _runtime_processes(executable: Path) -> list[Path]:
    """Return the executable and any fixed launcher child needed on macOS."""
    processes = [executable]
    if executable.name.startswith("python3") and executable.parent.name == "bin":
        version_root = executable.parent.parent
        python_app = (
            version_root
            / "Resources"
            / "Python.app"
            / "Contents"
            / "MacOS"
            / "Python"
        )
        if python_app.is_file() and os.access(python_app, os.X_OK):
            processes.append(python_app.resolve())
    return processes


def build_pi_v03_seatbelt_profile(
    repo_root: Path,
    run_dir: Path,
    invocation: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Build a deny-by-default profile with one case-specific test runtime."""
    if platform.system() != "Darwin":
        raise RunnerError("The Pi v0.3 Seatbelt backend is available only on macOS")
    if not SEATBELT_EXECUTABLE.is_file():
        raise RunnerError("macOS sandbox-exec is not available")

    resolved_repo = repo_root.resolve()
    resolved_run = run_dir.resolve()
    workspace = Path(policy["workspace_root"]).resolve()
    agent_dir = Path(invocation["environment"]["PI_CODING_AGENT_DIR"]).resolve()
    audit_log = Path(policy["audit_log_path"]).resolve()
    integration_root = (resolved_repo / "integrations" / "pi").resolve()
    profile_path = resolved_run / "pi-sandbox.sb"
    tmp_dir = resolved_run / "sandbox-tmp"
    probe_dir = resolved_run / "sandbox-probe"
    probe_allowed_write = probe_dir / "allowed-write.txt"

    for path, parent in (
        (workspace, resolved_run),
        (agent_dir, resolved_run),
        (audit_log, resolved_run),
    ):
        try:
            path.relative_to(parent)
        except ValueError as exc:
            raise RunnerError(
                f"Pi sandbox artifact escapes its run directory: {path}"
            ) from exc

    writable_paths = [
        workspace / relative_path for relative_path in policy["writable_paths"]
    ]
    for path in writable_paths:
        if not path.is_file() or path.is_symlink():
            raise RunnerError(f"Pi writable target is not a regular fixture file: {path}")

    node_binary = _node_binary()
    node_root = node_binary.parents[1]
    public_test_executable = resolve_public_test_executable(
        policy["public_test_command"]
    )
    candidates = [
        node_binary,
        Path("/bin/bash"),
        Path("/bin/sh"),
        Path("/bin/zsh"),
        *_runtime_processes(public_test_executable),
    ]
    allowed_processes = sorted(
        {path.resolve() for path in candidates if path.exists()}, key=str
    )
    home = Path.home().resolve()
    if (
        public_test_executable != node_binary
        and (public_test_executable == home or home in public_test_executable.parents)
    ):
        raise RunnerError(
            "Pi v0.3 public-test runtimes must not reside in the user's home directory"
        )
    if (
        public_test_executable == resolved_repo
        or resolved_repo in public_test_executable.parents
    ):
        raise RunnerError(
            "Pi v0.3 public-test runtimes must not reside in the benchmark repository"
        )

    metadata_ancestors = [
        ancestor
        for allowed_root in (node_root, integration_root, resolved_run)
        for ancestor in _metadata_ancestors(allowed_root, home)
    ]
    lines = [
        "(version 1)",
        "(deny default)",
        _literal_rule("process-exec", allowed_processes),
        "(allow process-fork)",
        "(allow signal (target same-sandbox))",
        "(allow process-info* (target same-sandbox))",
        "(allow file-read*)",
        f"(deny file-read* (subpath {_sbpl_string(home)}))",
        f"(deny file-read* (subpath {_sbpl_string(resolved_repo)}))",
        _literal_rule("file-read-metadata", metadata_ancestors),
        f"(allow file-read* (subpath {_sbpl_string(node_root)}))",
        f"(allow file-read* (subpath {_sbpl_string(integration_root)}))",
        f"(allow file-read* (subpath {_sbpl_string(resolved_run)}))",
        _literal_rule(
            "file-write*", [*writable_paths, audit_log, probe_allowed_write]
        ),
        f"(allow file-write* (subpath {_sbpl_string(agent_dir)}))",
        f"(allow file-write* (subpath {_sbpl_string(tmp_dir)}))",
        '(allow file-write-data (literal "/dev/null"))',
        "(allow sysctl-read)",
        '(allow iokit-open (iokit-registry-entry-class "RootDomainUserClient"))',
        '(allow mach-lookup (global-name "com.apple.system.opendirectoryd.libinfo"))',
        '(allow mach-lookup (global-name "com.apple.bsd.dirhelper"))',
        '(allow mach-lookup (global-name "com.apple.system.opendirectoryd.membership"))',
        '(allow mach-lookup (global-name "com.apple.SystemConfiguration.DNSConfiguration"))',
        '(allow mach-lookup (global-name "com.apple.SystemConfiguration.configd"))',
        "(allow ipc-posix-sem)",
        "(allow system-socket (require-all (socket-domain AF_SYSTEM) (socket-protocol 2)))",
        '(allow network-outbound (remote ip "localhost:11434"))',
    ]
    profile = "\n".join(lines) + "\n"
    metadata = {
        "schema_version": "1.0.0",
        "backend": SEATBELT_V03_PROFILE_VERSION,
        "sandbox_executable": str(SEATBELT_EXECUTABLE),
        "repository_root": str(resolved_repo),
        "profile_path": str(profile_path),
        "node_binary": str(node_binary),
        "node_root": str(node_root),
        "allowed_processes": [str(path) for path in allowed_processes],
        "public_test_executable": str(public_test_executable),
        "readable_roots": [str(integration_root), str(node_root), str(resolved_run)],
        "denied_read_roots": [str(home), str(resolved_repo)],
        "metadata_traversal_paths": sorted({str(path) for path in metadata_ancestors}),
        "writable_paths": [str(path.resolve()) for path in writable_paths],
        "audit_log_path": str(audit_log),
        "writable_run_roots": [str(agent_dir), str(tmp_dir)],
        "temporary_directory": str(tmp_dir),
        "probe_allowed_write_path": str(probe_allowed_write),
        "network_allowlist": ["localhost:11434"],
        "external_network": False,
    }
    return profile, metadata


def write_pi_v03_seatbelt_artifacts(
    repo_root: Path,
    run_dir: Path,
    invocation: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    """Persist one Pi v0.3 profile and its non-secret metadata."""
    profile, metadata = build_pi_v03_seatbelt_profile(
        repo_root, run_dir, invocation, policy
    )
    profile_path = Path(metadata["profile_path"])
    tmp_dir = Path(metadata["temporary_directory"])
    probe_allowed_write = Path(metadata["probe_allowed_write_path"])
    tmp_dir.mkdir()
    probe_allowed_write.parent.mkdir()
    probe_allowed_write.write_text("before\n", encoding="utf-8")
    Path(metadata["audit_log_path"]).touch()
    profile_path.write_text(profile, encoding="utf-8")
    metadata["profile_sha256"] = sha256_file(profile_path)
    write_json(run_dir / "pi-sandbox.json", metadata)
    return metadata


def validate_pi_v03_seatbelt(run_dir: Path) -> dict[str, Any]:
    """Run the inherited adversarial checks plus the selected runtime probe."""
    resolved_run = run_dir.resolve()
    result = validate_pi_seatbelt(resolved_run)
    invocation = json.loads(
        (resolved_run / "pi-invocation.json").read_text(encoding="utf-8")
    )
    metadata = json.loads(
        (resolved_run / "pi-sandbox.json").read_text(encoding="utf-8")
    )
    runtime_result = run_seatbelt_command(
        Path(metadata["profile_path"]),
        [metadata["public_test_executable"], "--version"],
        cwd=Path(invocation["cwd"]),
        environment=pi_sandbox_environment(metadata, invocation),
        timeout_seconds=10.0,
    )
    runtime_check = {
        "check_id": "selected_public_test_runtime_starts",
        "passed": runtime_result.returncode == 0,
        "expected_returncode": 0,
        "observed_returncode": runtime_result.returncode,
        "detail": (
            "The exact case-specific public-test runtime starts inside Seatbelt "
            "without executing candidate code."
        ),
        "stderr_nonempty": bool(runtime_result.stderr),
    }
    result["backend"] = SEATBELT_V03_PROFILE_VERSION
    result["validated_at"] = utc_now()
    result["checks"].append(runtime_check)
    result["passed"] = all(item["passed"] for item in result["checks"])
    result["candidate_code_executed"] = False
    acceptance_path = resolved_run / "pi-sandbox-acceptance.json"
    write_json(acceptance_path, result)

    record_path = resolved_run / "run.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["execution_boundary"]["sandbox_acceptance_passed"] = result["passed"]
    record["execution_boundary"]["sandbox_acceptance_sha256"] = sha256_file(
        acceptance_path
    )
    record["execution_boundary"]["sandbox_validated_at"] = result["validated_at"]
    write_json(record_path, record)
    if not result["passed"]:
        raise RunnerError("Pi v0.3 selected public-test runtime failed inside Seatbelt")
    return result
