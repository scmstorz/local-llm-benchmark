"""Deny-by-default macOS Seatbelt boundary for read-only Pi log analysis."""

from __future__ import annotations

import json
import platform
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
)
from .runner import RunnerError, sha256_file, utc_now, write_json


PROFILE_VERSION = "pi-log-macos-seatbelt-v0.1"


def build_pi_log_seatbelt_profile(
    repo_root: Path,
    run_dir: Path,
    invocation: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Build a profile with no candidate workspace writes or shell process."""
    if platform.system() != "Darwin":
        raise RunnerError("The Pi Log Seatbelt backend is available only on macOS")
    if not SEATBELT_EXECUTABLE.is_file():
        raise RunnerError("macOS sandbox-exec is not available")

    resolved_repo = repo_root.resolve()
    resolved_run = run_dir.resolve()
    workspace = Path(policy["workspace_root"]).resolve()
    agent_dir = Path(invocation["environment"]["PI_CODING_AGENT_DIR"]).resolve()
    audit_log = Path(policy["audit_log_path"]).resolve()
    integration_root = (resolved_repo / "integrations" / "pi").resolve()
    profile_path = resolved_run / "pi-log-sandbox.sb"
    tmp_dir = resolved_run / "sandbox-tmp"

    for path, parent in (
        (workspace, resolved_run),
        (agent_dir, resolved_run),
        (audit_log, resolved_run),
    ):
        try:
            path.relative_to(parent)
        except ValueError as exc:
            raise RunnerError(f"Pi Log sandbox artifact escapes its run: {path}") from exc

    node_binary = _node_binary()
    node_root = node_binary.parents[1]
    home = Path.home().resolve()
    metadata_ancestors = [
        ancestor
        for allowed_root in (node_root, integration_root, resolved_run)
        for ancestor in _metadata_ancestors(allowed_root, home)
    ]
    lines = [
        "(version 1)",
        "(deny default)",
        _literal_rule("process-exec", [node_binary]),
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
        _literal_rule("file-write*", [audit_log]),
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
        "backend": PROFILE_VERSION,
        "sandbox_executable": str(SEATBELT_EXECUTABLE),
        "repository_root": str(resolved_repo),
        "profile_path": str(profile_path),
        "node_binary": str(node_binary),
        "node_root": str(node_root),
        "allowed_processes": [str(node_binary)],
        "shell_processes_allowed": False,
        "readable_roots": [str(integration_root), str(node_root), str(resolved_run)],
        "denied_read_roots": [str(home), str(resolved_repo)],
        "metadata_traversal_paths": sorted({str(path) for path in metadata_ancestors}),
        "candidate_workspace_writable": False,
        "audit_log_path": str(audit_log),
        "writable_run_roots": [str(agent_dir), str(tmp_dir)],
        "temporary_directory": str(tmp_dir),
        "network_allowlist": ["localhost:11434"],
        "external_network": False,
    }
    return profile, metadata


def write_pi_log_seatbelt_artifacts(
    repo_root: Path,
    run_dir: Path,
    invocation: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    """Persist one run-specific profile and its non-secret metadata."""
    profile, metadata = build_pi_log_seatbelt_profile(
        repo_root, run_dir, invocation, policy
    )
    Path(metadata["temporary_directory"]).mkdir()
    Path(metadata["audit_log_path"]).touch()
    profile_path = Path(metadata["profile_path"])
    profile_path.write_text(profile, encoding="utf-8")
    metadata["profile_sha256"] = sha256_file(profile_path)
    write_json(run_dir / "pi-log-sandbox.json", metadata)
    return metadata


class _ProbeHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"probe":true}')

    def log_message(self, format: str, *args: object) -> None:
        return


def _temporary_loopback_probe() -> tuple[ThreadingHTTPServer | None, threading.Thread | None]:
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 11434), _ProbeHandler)
    except OSError:
        return None, None
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def validate_pi_log_seatbelt(run_dir: Path) -> dict[str, Any]:
    """Run adversarial isolation checks without model inference."""
    resolved_run = run_dir.resolve()
    invocation = json.loads((resolved_run / "pi-invocation.json").read_text())
    metadata = json.loads((resolved_run / "pi-log-sandbox.json").read_text())
    policy = json.loads((resolved_run / "pi-policy.json").read_text())
    record = json.loads((resolved_run / "run.json").read_text())
    profile_path = Path(metadata["profile_path"])
    if sha256_file(profile_path) != metadata["profile_sha256"]:
        raise RunnerError("Pi Log Seatbelt profile hash mismatch")
    environment = pi_sandbox_environment(metadata, invocation)
    workspace = Path(invocation["cwd"])
    node = metadata["node_binary"]
    repo_root = Path(metadata["repository_root"])
    case_path = (repo_root / record["case"]["case_path"]).resolve()
    case = json.loads(case_path.read_text(encoding="utf-8"))
    hidden_path = (repo_root / case["verification"]["ground_truth_path"]).resolve()
    if sha256_file(hidden_path) != record["case"]["ground_truth_sha256"]:
        raise RunnerError("Pi Log hidden ground-truth identity mismatch")
    visible_path = workspace / policy["readable_paths"][0]
    symlink_path = resolved_run / "sandbox-tmp" / "hidden-link"
    symlink_path.symlink_to(hidden_path)
    runtime_write = resolved_run / "sandbox-tmp" / "runtime-write.txt"

    checks: list[dict[str, Any]] = []

    def check(check_id: str, command: list[str], expected: int, detail: str) -> None:
        result = run_seatbelt_command(
            profile_path,
            command,
            cwd=workspace,
            environment=environment,
            timeout_seconds=7.0,
        )
        checks.append(
            {
                "check_id": check_id,
                "passed": result.returncode == expected,
                "expected_returncode": expected,
                "observed_returncode": result.returncode,
                "detail": detail,
                "stderr_nonempty": bool(result.stderr),
            }
        )

    denied_read = (
        'try{require("fs").openSync(process.argv[1],"r");process.exit(1)}'
        'catch(e){process.exit(["EPERM","EACCES"].includes(e.code)?0:2)}'
    )
    denied_write = (
        'try{require("fs").appendFileSync(process.argv[1],"x");process.exit(1)}'
        'catch(e){process.exit(["EPERM","EACCES"].includes(e.code)?0:2)}'
    )
    check(
        "allowed_workspace_read",
        [node, "-e", 'require("fs").openSync(process.argv[1],"r")', str(visible_path)],
        0,
        "A declared log file is readable.",
    )
    check(
        "candidate_workspace_write_denied",
        [node, "-e", denied_write, str(visible_path)],
        0,
        "Candidate-visible log files are OS-level read-only.",
    )
    check(
        "hidden_ground_truth_read_denied",
        [node, "-e", denied_read, str(hidden_path)],
        0,
        "The hidden ground truth is outside the readable sandbox.",
    )
    check(
        "symlink_escape_read_denied",
        [node, "-e", denied_read, str(symlink_path)],
        0,
        "A readable-run-root symlink cannot escape to hidden ground truth.",
    )
    check(
        "private_runtime_write_allowed",
        [node, "-e", 'require("fs").writeFileSync(process.argv[1],"ok")', str(runtime_write)],
        0,
        "Pi may write only to its private runtime area.",
    )
    check(
        "unlisted_process_denied",
        [
            node,
            "-e",
            'try{require("child_process").execFile("/usr/bin/id",e=>process.exit(e?0:1))}'
            'catch(e){process.exit(e.code==="EPERM"?0:2)}',
        ],
        0,
        "A process other than the resolved Node executable cannot start.",
    )
    check(
        "pinned_pi_starts_offline",
        [node, invocation["executable"], "--offline", "--list-models"],
        0,
        "Pinned Pi loads the run-local configuration without inference.",
    )
    check(
        "external_network_denied",
        [
            node,
            "-e",
            'const s=require("net").connect(443,"1.1.1.1");'
            's.on("connect",()=>process.exit(1));s.on("error",()=>process.exit(0));'
            's.setTimeout(1500,()=>process.exit(2));',
        ],
        0,
        "Direct external TCP is denied.",
    )
    probe_server, probe_thread = _temporary_loopback_probe()
    try:
        check(
            "ollama_loopback_allowed",
            [
                node,
                "-e",
                'require("http").get("http://127.0.0.1:11434/",r=>{'
                'r.resume();r.on("end",()=>process.exit(0))}).on("error",()=>process.exit(2));',
            ],
            0,
            "The only permitted network destination is local port 11434.",
        )
    finally:
        if probe_server is not None:
            probe_server.shutdown()
            probe_server.server_close()
        if probe_thread is not None:
            probe_thread.join(timeout=2.0)
    symlink_path.unlink(missing_ok=True)
    passed = all(item["passed"] for item in checks)
    result = {
        "schema_version": "1.0.0",
        "backend": metadata["backend"],
        "profile_sha256": metadata["profile_sha256"],
        "validated_at": utc_now(),
        "passed": passed,
        "inference_requests_made": 0,
        "candidate_code_executed": False,
        "candidate_workspace_writes": 0,
        "hidden_ground_truth_sha256": sha256_file(hidden_path),
        "checks": checks,
    }
    acceptance_path = resolved_run / "pi-sandbox-acceptance.json"
    write_json(acceptance_path, result)
    if not passed:
        failures = ", ".join(item["check_id"] for item in checks if not item["passed"])
        raise RunnerError(f"Pi Log Seatbelt acceptance failed: {failures}")
    record_path = resolved_run / "run.json"
    record["execution_boundary"]["sandbox_acceptance_passed"] = True
    record["execution_boundary"]["sandbox_acceptance_sha256"] = sha256_file(
        acceptance_path
    )
    record["execution_boundary"]["sandbox_validated_at"] = result["validated_at"]
    write_json(record_path, record)
    return result
