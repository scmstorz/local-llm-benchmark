"""Versioned macOS Seatbelt boundary for the pinned Pi coding harness."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .runner import RunnerError, sha256_file, utc_now, write_json


SEATBELT_EXECUTABLE = Path("/usr/bin/sandbox-exec")
SEATBELT_PROFILE_VERSION = "pi-macos-seatbelt-v0.1"


@dataclass(frozen=True)
class SeatbeltCommandResult:
    """Captured result of one command executed inside Seatbelt."""

    returncode: int
    stdout: str
    stderr: str


def _sbpl_string(path: Path | str) -> str:
    value = str(path)
    if not value.startswith("/") or "\n" in value or "\r" in value:
        raise RunnerError(f"Seatbelt paths must be absolute single-line paths: {value!r}")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _literal_rule(operation: str, paths: Sequence[Path]) -> str:
    unique = sorted({path.resolve() for path in paths}, key=str)
    filters = " ".join(f"(literal {_sbpl_string(path)})" for path in unique)
    return f"(allow {operation} {filters})"


def _node_binary() -> Path:
    observed = shutil.which("node")
    if not observed:
        raise RunnerError("Node.js is required for the pinned Pi harness")
    return Path(observed).resolve()


def _allowed_processes(node_binary: Path) -> list[Path]:
    candidates = [
        node_binary,
        Path("/bin/bash"),
        Path("/bin/sh"),
        Path("/bin/zsh"),
        Path("/usr/local/bin/php"),
        Path("/usr/local/bin/default-php"),
        Path("/usr/local/bin/php8.4"),
        Path("/opt/homebrew/bin/php8.4"),
    ]
    return [path for path in candidates if path.exists()]


def _metadata_ancestors(path: Path, home: Path) -> list[Path]:
    """Return exact home-relative ancestors needed to traverse an allowed root."""
    ancestors: list[Path] = []
    current = path.resolve()
    while current != current.parent:
        if current == home or home in current.parents:
            ancestors.append(current)
        if current == home:
            break
        current = current.parent
    return ancestors


def build_pi_seatbelt_profile(
    repo_root: Path,
    run_dir: Path,
    invocation: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Build a deny-by-default profile for one already prepared Pi run."""
    if platform.system() != "Darwin":
        raise RunnerError("The Pi v0.1 Seatbelt backend is available only on macOS")
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
            raise RunnerError(f"Pi sandbox artifact escapes its run directory: {path}") from exc

    writable_paths = [
        workspace / relative_path for relative_path in policy["writable_paths"]
    ]
    for path in writable_paths:
        if not path.is_file() or path.is_symlink():
            raise RunnerError(f"Pi writable target is not a regular fixture file: {path}")

    node_binary = _node_binary()
    node_root = node_binary.parents[1]
    home = Path.home().resolve()
    allowed_processes = _allowed_processes(node_binary)
    if not any(path.name.startswith("php") or path.name == "default-php" for path in allowed_processes):
        raise RunnerError("No PHP executable was found for the PHP Track B pilot")

    # Runtime libraries and system metadata are readable. The user's home and
    # the repository are then denied, with narrower exceptions for this run,
    # the pinned integration and the exact Node installation. Seatbelt applies
    # the more specific path filter, which the adversarial acceptance test
    # verifies on the target OS before live inference is permitted.
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
        _literal_rule("file-write*", [*writable_paths, audit_log, probe_allowed_write]),
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
        "backend": SEATBELT_PROFILE_VERSION,
        "sandbox_executable": str(SEATBELT_EXECUTABLE),
        "repository_root": str(resolved_repo),
        "profile_path": str(profile_path),
        "node_binary": str(node_binary),
        "node_root": str(node_root),
        "allowed_processes": [str(path.resolve()) for path in allowed_processes],
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


def write_pi_seatbelt_artifacts(
    repo_root: Path,
    run_dir: Path,
    invocation: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    """Persist one run-specific profile and its non-secret metadata."""
    profile, metadata = build_pi_seatbelt_profile(
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


def pi_sandbox_environment(
    metadata: dict[str, Any], invocation: dict[str, Any]
) -> dict[str, str]:
    """Return a small environment without inherited credentials or proxy settings."""
    node_binary = Path(metadata["node_binary"])
    environment = {
        "HOME": invocation["environment"]["PI_CODING_AGENT_DIR"],
        "PATH": os.pathsep.join(
            [str(node_binary.parent), "/usr/local/bin", "/usr/bin", "/bin"]
        ),
        "TMPDIR": metadata["temporary_directory"] + "/",
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
    }
    environment.update(invocation["environment"])
    return environment


def run_seatbelt_command(
    profile_path: Path,
    command: Sequence[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout_seconds: float = 10.0,
) -> SeatbeltCommandResult:
    """Execute one exact command under an already persisted profile."""
    try:
        completed = subprocess.run(
            [str(SEATBELT_EXECUTABLE), "-f", str(profile_path), *command],
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RunnerError(f"Seatbelt command timed out after {timeout_seconds}s") from exc
    except OSError as exc:
        raise RunnerError(f"Cannot execute macOS Seatbelt: {exc}") from exc
    return SeatbeltCommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def validate_pi_seatbelt(run_dir: Path) -> dict[str, Any]:
    """Run adversarial, no-inference acceptance checks for one Pi run."""
    resolved_run = run_dir.resolve()
    invocation = json.loads(
        (resolved_run / "pi-invocation.json").read_text(encoding="utf-8")
    )
    metadata = json.loads(
        (resolved_run / "pi-sandbox.json").read_text(encoding="utf-8")
    )
    profile_path = Path(metadata["profile_path"])
    if sha256_file(profile_path) != metadata["profile_sha256"]:
        raise RunnerError("Pi Seatbelt profile hash mismatch")
    environment = pi_sandbox_environment(metadata, invocation)
    workspace = Path(invocation["cwd"])
    node = metadata["node_binary"]
    repo_root = Path(metadata["repository_root"])
    record = json.loads((resolved_run / "run.json").read_text(encoding="utf-8"))
    case_path = (repo_root / record["case"]["case_path"]).resolve()
    try:
        case_path.relative_to(repo_root)
    except ValueError as exc:
        raise RunnerError("Prepared Pi case path escapes the repository") from exc
    case_definition = json.loads(case_path.read_text(encoding="utf-8"))
    hidden_relative = case_definition.get("verification", {}).get("hidden_test_path")
    if not isinstance(hidden_relative, str) or not hidden_relative:
        raise RunnerError("Prepared Pi case does not define a hidden verifier path")
    hidden_path = (repo_root / hidden_relative).resolve()
    try:
        hidden_path.relative_to(repo_root)
    except ValueError as exc:
        raise RunnerError("Prepared Pi hidden verifier path escapes the repository") from exc
    if (
        not hidden_path.is_file()
        or sha256_file(hidden_path) != record["case"]["hidden_test_sha256"]
    ):
        raise RunnerError("Prepared Pi hidden verifier identity mismatch")
    denied_write = repo_root / "pi-seatbelt-denied-write.tmp"
    symlink_path = resolved_run / "sandbox-probe" / "hidden-link"
    if symlink_path.exists() or symlink_path.is_symlink():
        symlink_path.unlink()
    symlink_path.symlink_to(hidden_path)

    checks: list[dict[str, Any]] = []

    def check(
        check_id: str,
        command: list[str],
        expected_returncode: int,
        detail: str,
        timeout: float = 10.0,
    ) -> None:
        result = run_seatbelt_command(
            profile_path,
            command,
            cwd=workspace,
            environment=environment,
            timeout_seconds=timeout,
        )
        checks.append(
            {
                "check_id": check_id,
                "passed": result.returncode == expected_returncode,
                "expected_returncode": expected_returncode,
                "observed_returncode": result.returncode,
                "detail": detail,
                "stderr_nonempty": bool(result.stderr),
            }
        )

    visible_path = next(iter(json.loads((resolved_run / "pi-policy.json").read_text())["readable_paths"]))
    denied_open_script = (
        'try{require("fs").openSync(process.argv[1],"r");process.exit(1)}'
        'catch(e){process.exit(["EPERM","EACCES"].includes(e.code)?0:2)}'
    )
    check(
        "allowed_workspace_read",
        [node, "-e", 'require("fs").openSync(process.argv[1],"r")', str(workspace / visible_path)],
        0,
        "A candidate-visible workspace file remains readable.",
    )
    check(
        "hidden_verifier_read_denied_in_child",
        ["/bin/sh", "-c", '"$1" -e "$2" "$3"', "seatbelt", node, denied_open_script, str(hidden_path)],
        0,
        "A child shell inherits the denial for the hidden verifier.",
    )
    check(
        "home_secret_read_denied",
        [node, "-e", denied_open_script, str(Path.home() / ".ssh" / "config")],
        0,
        "The user's SSH directory is not readable; no secret content is opened.",
    )
    check(
        "symlink_escape_read_denied",
        [node, "-e", denied_open_script, str(symlink_path)],
        0,
        "A readable-run-directory symlink cannot escape to the hidden verifier.",
    )
    check(
        "allowed_exact_write",
        [
            "/bin/sh",
            "-c",
            'printf "after\\n" > "$1"',
            "seatbelt",
            metadata["probe_allowed_write_path"],
        ],
        0,
        "The exact predeclared probe target remains writable.",
    )
    check(
        "pi_style_node_write",
        [
            node,
            "-e",
            'const fs=require("fs/promises"),p=require("path"),f=process.argv[1];fs.mkdir(p.dirname(f),{recursive:true}).then(()=>fs.writeFile(f,"node-write\\n","utf8")).then(()=>process.exit(0)).catch(()=>process.exit(1));',
            metadata["probe_allowed_write_path"],
        ],
        0,
        "Pi's recursive-parent plus Node write sequence works for one exact existing target.",
    )
    check(
        "repository_write_denied",
        ["/bin/sh", "-c", ': > "$1"', "seatbelt", str(denied_write)],
        1,
        "A write outside the exact allowlist is denied.",
    )
    check(
        "unlisted_process_denied",
        [
            node,
            "-e",
            'try{require("child_process").execFile("/usr/bin/id",e=>process.exit(e?0:1))}catch(e){process.exit(e.code==="EPERM"?0:2)}',
        ],
        0,
        "An executable outside the process allowlist cannot start.",
    )
    check(
        "pinned_pi_starts_offline",
        [
            node,
            invocation["executable"],
            "--offline",
            "--list-models",
        ],
        0,
        "The exact pinned Pi entrypoint loads its run-local configuration inside the sandbox without inference.",
    )
    check(
        "external_network_denied",
        [
            node,
            "-e",
            'const s=require("net").connect(443,"1.1.1.1");s.on("connect",()=>process.exit(1));s.on("error",()=>process.exit(0));s.setTimeout(1500,()=>process.exit(2));',
        ],
        0,
        "A direct external TCP connection is denied rather than merely discouraged.",
        timeout=5.0,
    )
    check(
        "ollama_loopback_allowed",
        [
            node,
            "-e",
            'require("http").get("http://127.0.0.1:11434/api/version",r=>{r.resume();r.on("end",()=>process.exit(r.statusCode===200?0:1))}).on("error",()=>process.exit(2));',
        ],
        0,
        "The only permitted network destination is the local Ollama API.",
        timeout=5.0,
    )
    if denied_write.exists():
        denied_write.unlink()
    symlink_path.unlink()
    passed = all(item["passed"] for item in checks)
    result = {
        "schema_version": "1.0.0",
        "backend": metadata["backend"],
        "profile_sha256": metadata["profile_sha256"],
        "validated_at": utc_now(),
        "passed": passed,
        "inference_requests_made": 0,
        "hidden_verifier_sha256": sha256_file(hidden_path),
        "checks": checks,
    }
    write_json(resolved_run / "pi-sandbox-acceptance.json", result)
    if not passed:
        failures = ", ".join(item["check_id"] for item in checks if not item["passed"])
        raise RunnerError(f"Pi Seatbelt acceptance failed: {failures}")
    record_path = resolved_run / "run.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["execution_boundary"]["sandbox_acceptance_passed"] = True
    record["execution_boundary"]["sandbox_acceptance_sha256"] = sha256_file(
        resolved_run / "pi-sandbox-acceptance.json"
    )
    record["execution_boundary"]["sandbox_validated_at"] = result["validated_at"]
    write_json(record_path, record)
    return result
