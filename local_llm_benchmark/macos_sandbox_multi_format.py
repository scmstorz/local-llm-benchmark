"""Deny-by-default macOS Seatbelt for the pinned Pi multi-format adapter."""

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
from .runner import RunnerError, load_json, sha256_file, utc_now, write_json


PROFILE_VERSION = "pi-multi-format-macos-seatbelt-v0.1"


def build_pi_multi_format_seatbelt_profile(
    repo_root: Path,
    run_dir: Path,
    invocation: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Build a profile limited to Pi and the exact shared parser executables."""
    if platform.system() != "Darwin" or not SEATBELT_EXECUTABLE.is_file():
        raise RunnerError("The Pi multi-format Seatbelt backend requires macOS")
    resolved_repo = repo_root.resolve()
    resolved_run = run_dir.resolve()
    workspace = Path(policy["workspace_root"]).resolve()
    agent_dir = Path(invocation["environment"]["PI_CODING_AGENT_DIR"]).resolve()
    audit_log = Path(policy["audit_log_path"]).resolve()
    backend = Path(policy["backend_path"]).resolve()
    python = Path(policy["python_path"]).resolve()
    pdftotext = Path(policy["pdftotext_path"]).resolve()
    integration_root = (resolved_repo / "integrations" / "pi").resolve()
    profile_path = resolved_run / "pi-multi-format-sandbox.sb"
    tmp_dir = resolved_run / "sandbox-tmp"
    for path in (workspace, agent_dir, audit_log, backend):
        try:
            path.relative_to(resolved_run)
        except ValueError as exc:
            raise RunnerError(f"Pi multi-format artifact escapes its run: {path}") from exc
    node = _node_binary()
    executable_roots = [node.parents[1], python.parents[1], pdftotext.parents[1]]
    home = Path.home().resolve()
    metadata_ancestors = [
        ancestor
        for allowed_root in (*executable_roots, integration_root, resolved_run)
        for ancestor in _metadata_ancestors(allowed_root, home)
    ]
    lines = [
        "(version 1)",
        "(deny default)",
        _literal_rule("process-exec", [node, python, pdftotext]),
        "(allow process-fork)",
        "(allow signal (target same-sandbox))",
        "(allow process-info* (target same-sandbox))",
        "(allow file-read*)",
        f"(deny file-read* (subpath {_sbpl_string(home)}))",
        f"(deny file-read* (subpath {_sbpl_string(resolved_repo)}))",
        _literal_rule("file-read-metadata", metadata_ancestors),
        *[
            f"(allow file-read* (subpath {_sbpl_string(root)}))"
            for root in executable_roots
        ],
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
        "node_binary": str(node),
        "python_binary": str(python),
        "pdftotext_binary": str(pdftotext),
        "allowed_processes": [str(node), str(python), str(pdftotext)],
        "shell_processes_allowed": False,
        "readable_roots": [
            str(integration_root),
            *(str(root) for root in executable_roots),
            str(resolved_run),
        ],
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


def write_pi_multi_format_seatbelt_artifacts(
    repo_root: Path,
    run_dir: Path,
    invocation: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    profile, metadata = build_pi_multi_format_seatbelt_profile(
        repo_root, run_dir, invocation, policy
    )
    Path(metadata["temporary_directory"]).mkdir()
    Path(metadata["audit_log_path"]).touch()
    profile_path = Path(metadata["profile_path"])
    profile_path.write_text(profile, encoding="utf-8")
    metadata["profile_sha256"] = sha256_file(profile_path)
    write_json(run_dir / "pi-multi-format-sandbox.json", metadata)
    return metadata


class _ProbeHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
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


def validate_pi_multi_format_seatbelt(run_dir: Path) -> dict[str, Any]:
    """Run adversarial checks immediately before live Pi execution."""
    resolved = run_dir.resolve()
    invocation = load_json(resolved / "pi-invocation.json")
    metadata = load_json(resolved / "pi-multi-format-sandbox.json")
    policy = load_json(resolved / "pi-policy.json")
    record = load_json(resolved / "run.json")
    profile = Path(metadata["profile_path"])
    if sha256_file(profile) != metadata["profile_sha256"]:
        raise RunnerError("Pi multi-format Seatbelt profile hash mismatch")
    environment = pi_sandbox_environment(metadata, invocation)
    workspace = Path(policy["workspace_root"])
    node = metadata["node_binary"]
    hidden = Path(metadata["repository_root"]) / record["case"]["ground_truth_path"]
    canonical = Path(metadata["repository_root"]) / record["case"]["canonical_path"]
    if sha256_file(hidden) != record["case"]["ground_truth_sha256"]:
        raise RunnerError("Pi multi-format hidden ground-truth identity mismatch")
    if sha256_file(canonical) != record["case"]["canonical_sha256"]:
        raise RunnerError("Pi multi-format canonical identity mismatch")
    visible = workspace / "rollout-policy.docx"
    symlink = resolved / "sandbox-tmp" / "hidden-link"
    symlink.symlink_to(hidden)
    private_write = resolved / "sandbox-tmp" / "runtime-write.txt"
    checks: list[dict[str, Any]] = []

    def check(check_id: str, command: list[str], expected: int, detail: str) -> None:
        result = run_seatbelt_command(
            profile, command, cwd=workspace, environment=environment, timeout_seconds=20.0
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

    denied_read = 'try{require("fs").openSync(process.argv[1],"r");process.exit(1)}catch(e){process.exit(["EPERM","EACCES"].includes(e.code)?0:2)}'
    denied_write = 'try{require("fs").appendFileSync(process.argv[1],"x");process.exit(1)}catch(e){process.exit(["EPERM","EACCES"].includes(e.code)?0:2)}'
    check("allowed_workspace_read", [node, "-e", 'require("fs").openSync(process.argv[1],"r")', str(visible)], 0, "A frozen artifact is readable.")
    check("candidate_workspace_write_denied", [node, "-e", denied_write, str(visible)], 0, "Candidate artifacts are OS-level read-only.")
    check("hidden_ground_truth_read_denied", [node, "-e", denied_read, str(hidden)], 0, "Ground truth is outside the sandbox.")
    check("canonical_extraction_read_denied", [node, "-e", denied_read, str(canonical)], 0, "Track A canonical evidence is outside Track B.")
    check("symlink_escape_read_denied", [node, "-e", denied_read, str(symlink)], 0, "Readable-run symlinks cannot escape.")
    check("private_runtime_write_allowed", [node, "-e", 'require("fs").writeFileSync(process.argv[1],"ok")', str(private_write)], 0, "Private runtime writes remain available.")
    check("unlisted_process_denied", [node, "-e", 'try{require("child_process").execFile("/usr/bin/id",e=>process.exit(e?0:1))}catch(e){process.exit(e.code==="EPERM"?0:2)}'], 0, "Unlisted processes cannot start.")
    request_script = (
        'const c=require("child_process");const requests=['
        '{operation:"list_artifacts"},'
        '{operation:"read_docx",anchor:"heading=Decision-rule"},'
        '{operation:"read_pdf",page:3,element:"table=Final-validation&row=North"},'
        '{operation:"read_xlsx",sheet:"Capacity",range:"B4:E4"}];'
        'for(const q of requests){const o=c.execFileSync(process.argv[1],'
        '["-I","-B",process.argv[2],"--workspace",process.argv[3],"--pdftotext",process.argv[4]],'
        '{input:JSON.stringify(q),encoding:"utf8"});if(JSON.parse(o).ok!==true)process.exit(2)}'
    )
    check(
        "shared_backend_all_formats",
        [node, "-e", request_script, policy["python_path"], policy["backend_path"], policy["workspace_root"], policy["pdftotext_path"]],
        0,
        "The exact shared backend reads DOCX, PDF and XLSX under Seatbelt.",
    )
    check("pinned_pi_starts_offline", [node, invocation["executable"], "--offline", "--list-models"], 0, "Pinned Pi loads offline without inference.")
    check("external_network_denied", [node, "-e", 'const s=require("net").connect(443,"1.1.1.1");s.on("connect",()=>process.exit(1));s.on("error",()=>process.exit(0));s.setTimeout(1500,()=>process.exit(2));'], 0, "External TCP is denied.")
    probe_server, probe_thread = _temporary_loopback_probe()
    try:
        check("ollama_loopback_allowed", [node, "-e", 'require("http").get("http://127.0.0.1:11434/",r=>{r.resume();r.on("end",()=>process.exit(0))}).on("error",()=>process.exit(2));'], 0, "Only local port 11434 is reachable.")
    finally:
        if probe_server is not None:
            probe_server.shutdown()
            probe_server.server_close()
        if probe_thread is not None:
            probe_thread.join(timeout=2.0)
    symlink.unlink(missing_ok=True)
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
        "checks": checks,
    }
    acceptance = resolved / "pi-sandbox-acceptance.json"
    write_json(acceptance, result)
    if not passed:
        failures = ", ".join(item["check_id"] for item in checks if not item["passed"])
        raise RunnerError(f"Pi multi-format Seatbelt acceptance failed: {failures}")
    record["execution_boundary"]["sandbox_acceptance_passed"] = True
    record["execution_boundary"]["sandbox_acceptance_sha256"] = sha256_file(acceptance)
    record["execution_boundary"]["sandbox_validated_at"] = result["validated_at"]
    write_json(resolved / "run.json", record)
    return result
