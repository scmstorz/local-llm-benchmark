"""Run-specific macOS containment for the external CLI coding systems."""

from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
from typing import Any

from .macos_sandbox import SEATBELT_EXECUTABLE, _literal_rule, _sbpl_string
from .runner import RunnerError, sha256_file, utc_now, write_json


def build_profile(root: Path, run: Path, invocation: dict, policy: dict) -> str:
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RunnerError("External CLI v0.1 requires macOS Apple Silicon")
    if not SEATBELT_EXECUTABLE.is_file():
        raise RunnerError("sandbox-exec is required")
    runtime = invocation["runtime"]
    integration = root / "integrations" / invocation["harness"]
    state = run / "agent-state"
    readable = [integration.resolve(), Path(runtime["base_prefix"]).resolve()]
    # Homebrew language runtimes may load sibling versioned shared libraries.
    # These are runtime installations, never the user's home or benchmark tree.
    if Path("/opt/homebrew/Cellar").exists():
        readable.append(Path("/opt/homebrew/Cellar"))
    metadata = set()
    for path in [*readable, run / "workspace", state, *map(Path, invocation["allowed_processes"])]:
        metadata.update(path.parents)
    lines = [
        "(version 1)", "(deny default)",
        "(allow process-fork)",
        "(allow signal (target same-sandbox))",
        "(allow process-info* (target same-sandbox))",
        _literal_rule("process-exec", [Path(p) for p in invocation["allowed_processes"]]),
        # Match the existing Pi runtime boundary: system/runtime files are
        # readable, while user, research and temporary data require exact
        # narrower exceptions. Restricting dyld's system paths by guesses can
        # abort a process before Python can report a useful error.
        '(allow file-read*)',
        '(deny file-read* (subpath "/Users") (subpath "/private/tmp") (subpath "/private/var/folders"))',
        f'(deny file-read* (subpath {_sbpl_string(Path.home())}) (subpath {_sbpl_string(root)}))',
        '(allow file-read* (literal "/dev/null") (literal "/dev/urandom") (literal "/dev/random") (literal "/private/etc/localtime"))',
        _literal_rule("file-read-metadata", list(metadata)),
    ]
    lines.extend(f"(allow file-read* (subpath {_sbpl_string(p)}))" for p in readable)
    lines.append(_literal_rule("file-read*", [Path(p) for p in invocation["allowed_processes"]]))
    workspace = run/"workspace"
    directories = {workspace}
    for relative in policy["readable_paths"]:
        parent = (workspace/relative).parent
        while parent.is_relative_to(workspace):
            directories.add(parent)
            if parent == workspace:
                break
            parent = parent.parent
    lines.extend([
        f"(allow file-read* file-write* (subpath {_sbpl_string(state)}))",
        _literal_rule("file-read*", [run / "workspace" / p for p in policy["readable_paths"]]),
        _literal_rule("file-read*", list(directories)),
        _literal_rule("file-write*", [run / "workspace" / p for p in policy["writable_paths"]]),
        '(allow file-write-data (literal "/dev/null"))',
        "(allow sysctl-read)",
        '(allow iokit-open (iokit-registry-entry-class "RootDomainUserClient"))',
        '(allow mach-lookup (global-name "com.apple.system.opendirectoryd.libinfo") (global-name "com.apple.bsd.dirhelper") (global-name "com.apple.system.opendirectoryd.membership") (global-name "com.apple.SystemConfiguration.DNSConfiguration") (global-name "com.apple.SystemConfiguration.configd"))',
        "(allow ipc-posix-sem)",
        '(allow system-socket (require-all (socket-domain AF_SYSTEM) (socket-protocol 2)))',
        f'(allow network-outbound (remote ip "localhost:{invocation["gateway_port"]}"))',
    ])
    if invocation["harness"] == "mirror":
        port = invocation["rpc_port"]
        lines.extend([
            f'(allow network-bind (local ip "localhost:{port}"))',
            f'(allow network-inbound (local ip "localhost:{port}"))',
            f'(allow network-outbound (remote ip "localhost:{port}"))',
        ])
    else:
        # Upstream Vibe's editor atomically replaces a target through a sibling
        # .NAME.tmp.PID.TIME_NS file. Permit exactly those temporary names for
        # existing writable targets; protected files and other new paths stay
        # denied. Final verification also rejects leftover temporary files.
        for relative in policy["writable_paths"]:
            target = run/"workspace"/relative
            prefix = str(target.parent/("." + target.name + ".tmp."))
            if any(c in prefix for c in '[]\\"\n\r'):
                raise RunnerError("Unsupported character in atomic-edit sandbox path")
            # SBPL's regex reader preserves escapes differently from ordinary
            # strings. Character classes avoid a second escape interpretation.
            escaped = "".join(c if c.isalnum() or c in "/_" else "["+c+"]" for c in prefix)
            pattern = "^" + escaped + "[0-9]+[.][0-9]+$"
            lines.append(f"(allow file-read* file-write* (regex #{json.dumps(pattern, ensure_ascii=False)}))")
    return "\n".join(lines) + "\n"


def sandbox_command(run: Path, invocation: dict, argv: list[str]) -> list[str]:
    return [str(SEATBELT_EXECUTABLE), "-f", str(run / "sandbox.sb"), *argv]


def check_sandbox(run: Path) -> dict[str, Any]:
    """Probe actual OS denials; this never calls a model or executes a fixture."""
    run = run.resolve()
    record = json.loads((run / "run.json").read_text())
    if record["state"] != "prepared":
        raise RunnerError("Sandbox acceptance requires an unconsumed preparation")
    invocation = json.loads((run / "invocation.json").read_text())
    policy = json.loads((run / "policy.json").read_text())
    for name, expected in record["prepared_hashes"].items():
        if sha256_file(run / name) != expected:
            raise RunnerError(f"Preparation changed: {name}")
    visible = run / "workspace" / policy["readable_paths"][0]
    writable = run / "workspace" / policy["writable_paths"][0]
    protected = next(run / "workspace" / p for p in policy["readable_paths"]
                     if p not in policy["writable_paths"])
    hidden = Path(policy["hidden_test_path"])
    canary = run.parent / (run.name + "-private-canary")
    canary.write_text("private controller canary\n")
    escape = run / "agent-state" / "hidden-symlink"
    escape.symlink_to(hidden)
    probes = {
        "working_directory_lookup": ("import os; print(os.getcwd())", True),
        "read_candidate_file": (f"open({str(visible)!r},'rb').read()", True),
        "write_allowed_existing_target": (f"p={str(writable)!r}; b=open(p,'rb').read(); open(p,'wb').write(b)", True),
        "write_run_state": (f"open({str(run/'agent-state'/'probe')!r},'w').write('ok')", True),
        "read_hidden_test_denied": (f"open({str(hidden)!r},'rb').read()", False),
        "read_controller_record_denied": (f"open({str(run/'run.json')!r},'rb').read()", False),
        "read_private_sibling_denied": (f"open({str(canary)!r},'rb').read()", False),
        "symlink_hidden_read_denied": (f"open({str(escape)!r},'rb').read()", False),
        "write_protected_test_denied": (f"open({str(protected)!r},'ab').write(b'')", False),
        "create_workspace_file_denied": (f"open({str(run/'workspace'/'unexpected.txt')!r},'w').write('x')", False),
        "direct_ollama_denied": ("import socket; socket.create_connection(('127.0.0.1',11434),.2)", False),
        "external_network_denied": ("import socket; socket.create_connection(('1.1.1.1',443),.2)", False),
        "unlisted_process_denied": ("import subprocess; subprocess.run(['/usr/bin/curl','--version'],check=True)", False),
    }
    test_executable = shlex.split(policy["public_test_command"])[0]
    probes["selected_public_runtime_starts"] = (
        f"import subprocess; subprocess.run([{test_executable!r},'--version'],check=True)", True)
    if invocation["harness"] == "mirror":
        rg = invocation["environment"]["MIRROR_RG_PATH"]
        probes["pinned_search_helper_starts"] = (f"import subprocess; subprocess.run([{rg!r},'--version'],check=True)", True)
    else:
        temp = writable.parent/("." + writable.name + ".tmp.123.456")
        probes["native_atomic_edit_supported"] = (
            f"import os; p={str(writable)!r}; t={str(temp)!r}; b=open(p,'rb').read(); open(t,'wb').write(b); os.replace(t,p)", True)
        protected_temp = protected.parent/("." + protected.name + ".tmp.123.456")
        probes["protected_atomic_temp_denied"] = (f"open({str(protected_temp)!r},'w').write('x')", False)
    checks = []
    try:
        for name, (code, should_pass) in probes.items():
            completed = subprocess.run(
                sandbox_command(run, invocation, [invocation["python"], "-I", "-c", code]),
                env=invocation["environment"], cwd=run/"workspace",
                capture_output=True, text=True, timeout=15,
            )
            denied = "Operation not permitted" in completed.stderr or "Permission denied" in completed.stderr
            passed = completed.returncode == 0 if should_pass else completed.returncode != 0 and denied
            checks.append({"check_id": name, "passed": passed,
                           "returncode": completed.returncode, "os_denial_observed": denied})
    finally:
        escape.unlink(missing_ok=True)
        canary.unlink(missing_ok=True)
    result = {"backend": "external-cli-macos-seatbelt-v0.1", "checked_at": utc_now(),
              "profile_sha256": sha256_file(run/"sandbox.sb"),
              "invocation_sha256": sha256_file(run/"invocation.json"),
              "checks": checks, "passed": all(c["passed"] for c in checks),
              "model_requests": 0, "candidate_code_executed": False}
    write_json(run / "sandbox-acceptance.json", result)
    record["sandbox_acceptance_sha256"] = sha256_file(run/"sandbox-acceptance.json")
    write_json(run / "run.json", record)
    return result
