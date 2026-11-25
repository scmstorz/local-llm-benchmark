"""Pinned Mirror and Mistral Vibe coding adapters with offline qualification.

Native CLI tool loops remain separate complete systems. Preparation, OS
acceptance, execution and hidden verification are independent state transitions.
Nothing is added to an existing measured suite or historical study.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import shlex
import shutil
import signal
import subprocess
import sys
import time
import tomllib
from typing import Any, Callable

from .coding import load_coding_case, verify_coding_workspace
from .external_cli_provider import ProviderJournal
from .external_cli_sandbox import build_profile, check_sandbox, sandbox_command
from .pi_v03_adapter import _public_test_command
from .runner import RunnerError, load_json, sha256_file, utc_now, write_json


PROTOCOL = Path("tasks/coding/track-b/external-cli-v0.1.json")
PROTOCOLS = {
    "v0.1": PROTOCOL,
    "v0.2": Path("tasks/coding/track-b/external-cli-v0.2.json"),
    "v0.3": Path("tasks/coding/track-b/external-cli-v0.3.json"),
}
DEFAULT_RESULTS = Path("results/agentic-dry-runs/external-cli-v0.1")


def _safe(root: Path, path: Path) -> Path:
    resolved = (root/path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise RunnerError("Artifact must remain inside the repository")
    return resolved


def _files(directory: Path) -> dict[str, str]:
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise RunnerError(f"Symlink in frozen artifact tree: {path.name}")
        if path.is_file():
            result[str(path.relative_to(directory))] = sha256_file(path)
    return result


def _port(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1024 <= value <= 65535 or value == 11434:
        raise RunnerError("Choose a non-Ollama loopback port between 1024 and 65535")
    return value


def runtime_identity(root: Path, name: str, *, condition: str = "v0.1") -> dict:
    protocol = load_json(root/PROTOCOLS[condition])
    if name not in protocol["harnesses"]:
        raise RunnerError("Unknown external CLI harness")
    spec = protocol["harnesses"][name]
    if sha256_file(root/spec["lock_path"]) != spec["lock_sha256"]:
        raise RunnerError("External CLI dependency lock changed")
    python = root / "integrations" / name / ".venv/bin/python"
    if not python.exists():
        raise RunnerError(f"Install the pinned {name} runtime with uv sync --locked first")
    # Inspect without importing the harness, starting its CLI or loading user
    # configuration. Validate the installed files against wheel RECORD hashes.
    code = '''import base64,hashlib,importlib.metadata as m,json,pathlib,sys
packages=[]
fingerprints=[]
for dist in m.distributions():
    packages.append([dist.metadata['Name'].lower().replace('_','-').replace('.','-'),dist.version])
    for item in dist.files or []:
        if item.hash is None: continue
        p=pathlib.Path(dist.locate_file(item))
        actual=hashlib.new(item.hash.mode,p.read_bytes()).digest()
        assert base64.urlsafe_b64encode(actual).decode().rstrip('=')==item.hash.value, str(item)
        fingerprints.append([dist.metadata['Name'],str(item),actual.hex()])
print(json.dumps(dict(python_version=sys.version,base_prefix=sys.base_prefix,python_binary=str(pathlib.Path(sys.executable).resolve()),packages=sorted(packages),installed_files_sha256=hashlib.sha256(json.dumps(sorted(fingerprints)).encode()).hexdigest(),verified_installed_files=len(fingerprints))))'''
    completed = subprocess.run([str(python), "-I", "-c", code], capture_output=True,
                               text=True, timeout=60)
    if completed.returncode:
        raise RunnerError("Installed runtime integrity failed: " + completed.stderr[-1500:])
    observed = json.loads(completed.stdout)
    if not observed["python_version"].startswith(spec["python"] + "."):
        raise RunnerError("External CLI Python version differs from the pinned minor version")
    locked = {(p["name"], p["version"]) for p in tomllib.loads((root/spec["lock_path"]).read_text())["package"]}
    if not set(map(tuple, observed["packages"])) <= locked:
        raise RunnerError("Installed dependencies differ from uv.lock")
    if [spec["package"], spec["version"]] not in observed["packages"]:
        raise RunnerError("Pinned CLI package identity differs")
    observed.update(package=spec["package"], version=spec["version"], lock_sha256=spec["lock_sha256"])
    return observed


def _environment(run: Path, python: Path, name: str, rpc_port: int) -> dict[str, str]:
    state = run/"agent-state"
    home = state/"home"
    # This is a fresh child-process environment. No account credentials,
    # proxies, user Python paths or existing harness settings are inherited.
    return {
        "HOME": str(home), "USER": "benchmark", "LOGNAME": "benchmark",
        "PATH": os.pathsep.join([str(python.parent), "/usr/bin", "/bin", "/opt/homebrew/bin", "/usr/local/bin"]),
        "TMPDIR": str(state/"tmp"), "XDG_CONFIG_HOME": str(home/".config"),
        "XDG_DATA_HOME": str(home/".local/share"), "XDG_CACHE_HOME": str(home/".cache"),
        "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8", "TERM": "dumb",
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": str(run/"workspace/src"),
        "MIRROR_SKIP_UPDATE": "1", "GRPC_ENABLE_FORK_SUPPORT": "0",
        "BENCHMARK_EVENTS": str(state/"events.jsonl"),
        "BENCHMARK_WORKER_PID": str(state/"worker.pid"),
        "BENCHMARK_MIRROR_RPC_PORT": str(rpc_port),
        "VIBE_HOME": str(home/".vibe"), "VIBE_CLI": "python",
        "PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring",
        "VIBE_TEST_DISABLE_KEYRING": "1",
        "NO_COLOR": "1",
    }


def _configure(root: Path, run: Path, name: str, model: str, gateway: int, rpc: int,
               protocol: dict) -> tuple[list[str], dict]:
    python = root/"integrations"/name/".venv/bin/python"
    state = run/"agent-state"
    environment = _environment(run, python, name, rpc)
    for path in [state/"tmp", Path(environment["HOME"]), Path(environment["XDG_CACHE_HOME"])]:
        path.mkdir(parents=True, exist_ok=True)
    base = f"http://127.0.0.1:{gateway}/v1"
    spec = protocol["harnesses"][name]
    if name == "mirror":
        config = Path(environment["HOME"])/".mirror"
        config.mkdir()
        write_json(config/"config.json", {"analytics": False, "usage_warning_acknowledged": True,
                   "trusted_directories": [str(run/"workspace")],
                   "extensions": {"builtin/memory": {"config": {"enabled": False}}}})
        argv = [str(python), "-I", str(root/"integrations/mirror/capture.py"),
                "--api", "openai-chat-completions", "--base-url", base,
                "--model", model, "--approval-mode", "auto", "--reasoning-effort", "none",
                "--context-window", str(spec["context_window"]),
                "--max-tokens", str(spec["max_tokens_per_request"]),
                "--database", str(state/"agent.db"), "exec"]
    else:
        config = Path(environment["VIBE_HOME"])
        config.mkdir()
        settings = f'''active_model = "benchmark"
allowed_models = [{json.dumps(model)}]
enable_telemetry = false
enable_otel = false
enable_connectors = false
include_project_context = false
disabled_skills = ["*"]
enabled_tools = ["read_file", "write_file", "edit", "grep", "bash"]
api_timeout = 300.0
api_retry_max_elapsed_time = 0.0
[experiments]
enable = false
[session_logging]
generate_titles = false
[[providers]]
name = "benchmark-local"
api_base = {json.dumps(base)}
api_key_env_var = ""
api_style = "openai"
backend = "generic"
[[models]]
name = {json.dumps(model)}
provider = "benchmark-local"
alias = "benchmark"
temperature = 0.0
max_context_length = 16384
thinking = "off"
thinking_levels = ["off"]
input_price = 0.0
output_price = 0.0
'''
        (config/"config.toml").write_text(settings)
        argv = [str(python), "-I", str(root/"integrations/vibe/.venv/bin/vibe"), "--legacy-harness", "--trust",
                "--auto-approve", "--output", "streaming", "--output-dir", str(state/"export"),
                "-p"]
    return argv, environment


def prepare(root: Path, *, harness: str, model: str, case_path: Path,
            results_dir: Path = DEFAULT_RESULTS, gateway_port: int = 18741,
            rpc_port: int = 18742, wall_seconds: int | None = None,
            condition: str = "v0.1") -> dict:
    root = root.resolve()
    if condition not in PROTOCOLS:
        raise RunnerError("Unknown external CLI condition")
    protocol_path = PROTOCOLS[condition]
    protocol = load_json(root/protocol_path)
    if condition == "v0.3" and results_dir == DEFAULT_RESULTS:
        results_dir = Path("results/agentic-dry-runs/external-cli-v0.3")
    if harness not in protocol["harnesses"]:
        raise RunnerError("Unknown external CLI harness")
    relative = str(_safe(root, case_path).relative_to(root))
    if relative not in protocol["task_paths"]:
        raise RunnerError("Case is outside the versioned external CLI coding subset")
    if not isinstance(model, str) or not model.strip() or model.startswith("-") or "\n" in model:
        raise RunnerError("Specify an exact nonempty model identifier")
    _port(gateway_port); _port(rpc_port)
    if gateway_port == rpc_port:
        raise RunnerError("Provider and AgentRPC ports must differ")
    if wall_seconds is not None and (isinstance(wall_seconds, bool) or not isinstance(wall_seconds, int)
                                    or not 1 <= wall_seconds <= protocol["normal_wall_time_seconds"]):
        raise RunnerError("Development-smoke wall budget must be between 1 and the protocol maximum")
    identity = runtime_identity(root, harness, condition=condition)
    rg = next((p.resolve() for p in [Path("/opt/homebrew/bin/rg"), Path("/usr/local/bin/rg"),
                                   Path(shutil.which("rg") or "/nonexistent")]
               if p.is_file() and os.access(p, os.X_OK)), None)
    if harness == "mirror" and rg is None:
        raise RunnerError("Mirror requires an exact pinned ripgrep executable")
    loaded = load_coding_case(root, Path(relative))
    run_id = harness + "-" + condition.replace(".", "") + "-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(4)
    run = _safe(root, results_dir)/run_id
    run.mkdir(parents=True)
    shutil.copytree(loaded["fixture_root"], run/"workspace")
    readable = loaded["case"]["candidate_context"]["files"]
    writable = sorted(p for p in loaded["baseline_inventory"]
                      if any(PurePosixPath(p).match(g) for g in loaded["artifact_contract"]["allowed_path_globs"]))
    public_command = _public_test_command(loaded)
    from .macos_sandbox_v03 import resolve_public_test_executable
    test_runtime = resolve_public_test_executable(public_command)
    public_command = shlex.join([str(test_runtime), *shlex.split(public_command)[1:]])
    policy = {"readable_paths": readable, "writable_paths": writable,
              "public_test_command": public_command,
              "hidden_test_path": str(loaded["hidden_test_path"]),
              "maximum_write_bytes": loaded["artifact_contract"]["maximum_bytes"]}
    task = loaded["task_path"].read_text()
    prompt = (task + "\n\nWork in this disposable repository fixture. Read the files using your tools.\n"
              "Edit the existing source files directly; do not return a patch or file envelope.\n"
              "Allowed source targets:\n" + "\n".join(writable) +
              "\nProtected tests and configuration must remain unchanged.\n"
              "Public test command: " + public_command + "\n"
              "Finish with a brief account of the changes and observed tests.\n")
    if protocol.get("explicit_workspace_hint"):
        prompt += ("\nWorking directory: " + str(run/"workspace") + "\n"
                   "Task paths are relative to this directory. Work here; parent directories are outside the task.\n")
    if protocol.get("declared_scratch"):
        scratch = run/"agent-state/scratch"
        scratch.mkdir(parents=True)
        policy["scratch_directory"] = str(scratch)
        prompt += ("\nWritable scratch directory: " + str(scratch) + "\n"
                   "Create any temporary tests here. Keep fixture paths unchanged except for the allowed source targets.\n"
                   "Write scratch scripts as files with your write tool, then execute their absolute paths.\n"
                   "Bash here-docs are unsupported by this OS sandbox; use a scratch file instead.\n"
                   "After running the public tests and any scratch checks, finish with a brief final summary.\n")
    argv, environment = _configure(root, run, harness, model, gateway_port, rpc_port, protocol)
    if harness == "mirror":
        environment["MIRROR_RG_PATH"] = str(rg)
    if harness == "vibe":
        argv.append(prompt)
        stdin = ""
    else:
        stdin = prompt
    candidates = [Path(identity["python_binary"]), test_runtime, *[
        Path(p) for p in ["/bin/bash", "/bin/sh", "/bin/cat", "/bin/ls", "/usr/bin/env",
                         "/usr/bin/grep", "/usr/bin/sed", "/usr/bin/head", "/usr/bin/tail",
                         "/usr/bin/wc", "/usr/bin/find", "/usr/bin/stat", "/usr/bin/uname", "/usr/bin/which"]]]
    if harness == "mirror":
        site = root/"integrations/mirror/.venv/lib/python3.12/site-packages/mirror/bin"
        candidates.extend(p for p in site.rglob("*") if p.name in {"mirror-agent", "rg"} and p.is_file())
    if rg is not None:
        candidates.append(rg)
    # Some framework Python launchers exec Python.app before running a test.
    from .macos_sandbox_v03 import _runtime_processes
    candidates.extend(_runtime_processes(test_runtime))
    invocation = {"harness": harness, "model": model, "argv": argv, "stdin": stdin,
                  "python": str(root/"integrations"/harness/".venv/bin/python"),
                  "runtime": identity, "environment": environment,
                  "gateway_port": gateway_port, "rpc_port": rpc_port,
                  "allowed_processes": sorted({str(p.resolve()) for p in candidates if p.exists()}),
                  "timeout_seconds": wall_seconds or protocol["normal_wall_time_seconds"]}
    if protocol.get("provider_profile"):
        invocation["provider_profile"] = protocol["provider_profile"]
    invocation["executable_hashes"] = {p: sha256_file(Path(p)) for p in invocation["allowed_processes"]}
    write_json(run/"policy.json", policy)
    write_json(run/"invocation.json", invocation)
    (run/"sandbox.sb").write_text(build_profile(root, run, invocation, policy))
    sources = {str(protocol_path), "local_llm_benchmark/external_cli.py",
               "local_llm_benchmark/external_cli_sandbox.py", "local_llm_benchmark/external_cli_provider.py",
               f"integrations/{harness}/pyproject.toml", f"integrations/{harness}/uv.lock"}
    if harness == "mirror":
        sources.update({"integrations/mirror/capture.py", "integrations/mirror/worker.py"})
    sources.update(str(p.relative_to(root)) for p in (root/"local_llm_benchmark").glob("*.py"))
    sources.update(str(p.relative_to(root)) for p in loaded["case_path"].parent.rglob("*") if p.is_file())
    record = {"schema_version": "external-cli-run-v0.1", "run_id": run_id,
              "condition": condition, "protocol_path": str(protocol_path),
              "state": "prepared", "created_at": utc_now(), "case_path": relative,
              "case_id": loaded["case"]["case_id"], "harness_id": protocol["harnesses"][harness]["harness_id"],
              "qualification_only": True, "measured_admission": False,
              "prepared_hashes": {p: sha256_file(run/p) for p in ["policy.json", "invocation.json", "sandbox.sb"]},
              "source_hashes": {p: sha256_file(root/p) for p in sorted(sources)},
              "initial_workspace": _files(run/"workspace"),
              "model_requests": 0, "candidate_code_executed": False,
              "hidden_verification_executed": False}
    write_json(run/"run.json", record)
    return {"run_dir": str(run), "run_id": run_id, "state": "prepared", "model_requests": 0}


def _load(root: Path, run: Path, states: set[str]) -> tuple[Path, dict, dict]:
    run = _safe(root, run)
    record = load_json(run/"run.json")
    if record.get("schema_version") != "external-cli-run-v0.1" or record.get("state") not in states:
        raise RunnerError("Run is consumed or has an unexpected lifecycle state")
    for name, expected in record["prepared_hashes"].items():
        if sha256_file(run/name) != expected:
            raise RunnerError(f"Prepared artifact changed: {name}")
    for name, expected in record["source_hashes"].items():
        if sha256_file(root/name) != expected:
            raise RunnerError(f"Bound source changed: {name}")
    invocation = load_json(run/"invocation.json")
    if any(sha256_file(Path(p)) != expected for p, expected in invocation["executable_hashes"].items()):
        raise RunnerError("A pinned runtime/tool executable changed")
    if runtime_identity(root, invocation["harness"], condition=record.get("condition", "v0.1")) != invocation["runtime"]:
        raise RunnerError("Installed external CLI runtime changed")
    return run, record, invocation


def _live_gate(root: Path, run: Path, invocation: dict, authorization: Path) -> dict:
    """Require an exact frozen-run approval and fresh existing resource gate."""
    from .log_incident_smokes import run_resource_gate
    from .ollama import OllamaClient
    from .runner import git_commit

    permission = load_json(_safe(root, authorization))
    if (permission.get("schema_version") != "external-cli-live-authorization-v0.1"
        or permission.get("live_execution_authorized") is not True
        or permission.get("run_manifest_sha256") != sha256_file(run/"run.json")
        or permission.get("source_commit") != git_commit(root)
        or permission.get("deployment", {}).get("name") != invocation["model"]
        or permission.get("resource_gate", {}).get("empty_state_observation_seconds") != 30
        or not permission.get("resource_gate", {}).get("blocking_process_rules")):
        raise RunnerError("Live execution needs exact post-freeze run/deployment authorization and a 30-second resource gate")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True):
        raise RunnerError("Commit the reviewed integration before a live development smoke")
    gate = run_resource_gate(permission, client=OllamaClient("http://127.0.0.1:11434", timeout_seconds=30))
    write_json(run/"live-admission.json", {"authorization_sha256": sha256_file(_safe(root, authorization)), **gate})
    return gate


def _kill_group(pid: int, sig: int) -> None:
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        pass


def _process_snapshot() -> dict[int, dict]:
    """Read OS ownership metadata, never account process command lines."""
    result = subprocess.run(["/bin/ps", "-axo", "pid=,ppid=,pgid=,stat=,lstart="],
                            capture_output=True, text=True, timeout=5)
    if result.returncode:
        raise RunnerError("Cannot inspect harness child-process ownership")
    rows = {}
    for line in result.stdout.splitlines():
        values = line.split(maxsplit=4)
        if len(values) == 5:
            pid, parent, group, state, start = values
            rows[int(pid)] = {"parent": int(parent), "group": int(group),
                              "state": state, "start": start}
    return rows


def _terminate_tree(process: subprocess.Popen) -> dict:
    """Terminate current descendants, including native tools' detached groups.

    No writable worker PID receipt is trusted to select a process to signal.
    OS ancestry and start metadata bind the cleanup to this launched job.
    """
    before = _process_snapshot()
    owned = {process.pid}
    while True:
        children = {pid for pid, row in before.items() if row["parent"] in owned}
        if children <= owned:
            break
        owned.update(children)
    observed = {pid: before[pid] for pid in owned if pid in before}
    groups = {row["group"] for row in observed.values() if row["group"] in owned}
    groups.add(process.pid)
    for group in sorted(groups, reverse=True):
        _kill_group(group, signal.SIGTERM)
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass
    current = _process_snapshot()
    for pid, old in observed.items():
        row = current.get(pid)
        if row and row["start"] == old["start"] and "Z" not in row["state"]:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    _kill_group(process.pid, signal.SIGKILL)
    process.wait(timeout=5)
    after = _process_snapshot()
    remaining = [pid for pid, old in observed.items()
                 if pid in after and after[pid]["start"] == old["start"] and "Z" not in after[pid]["state"]]
    return {"passed": not remaining, "owned_processes_observed": len(observed),
            "remaining_owned_processes": remaining,
            "ownership_source": "OS ancestry and process start metadata"}


def execute(root: Path, run: Path, *, responder: Callable | None = None,
            authorization: Path | None = None, offline_timeout: float = 60) -> dict:
    root = root.resolve()
    run, record, invocation = _load(root, run, {"prepared"})
    if _files(run/"workspace") != record["initial_workspace"]:
        raise RunnerError("Workspace changed after preparation")
    acceptance = load_json(run/"sandbox-acceptance.json")
    if (not acceptance.get("passed")
        or sha256_file(run/"sandbox-acceptance.json") != record.get("sandbox_acceptance_sha256")
        or acceptance["profile_sha256"] != sha256_file(run/"sandbox.sb")
        or acceptance["invocation_sha256"] != sha256_file(run/"invocation.json")):
        raise RunnerError("An unchanged passing OS sandbox acceptance is required")
    if (responder is None) == (authorization is None):
        raise RunnerError("Select exactly one offline responder or explicit live authorization")
    if authorization is not None:
        _live_gate(root, run, invocation, authorization)
    timeout = invocation["timeout_seconds"] if authorization is not None else offline_timeout
    journal = ProviderJournal(run/"provider-wire", model=invocation["model"],
                              port=invocation["gateway_port"],
                              upstream="http://127.0.0.1:11434" if authorization is not None else None,
                              responder=responder, timeout=300,
                              deadline=time.monotonic()+timeout,
                              profile=invocation.get("provider_profile"))
    record.update(state="running", started_at=utc_now(), offline_transport=responder is not None)
    write_json(run/"run.json", record)
    timed_out = False
    returncode = None
    failure = None
    process = None
    cleanup = None
    started = time.monotonic()
    with journal:
        with (run/"stdout.txt").open("w") as stdout, (run/"stderr.txt").open("w") as stderr:
            try:
                process = subprocess.Popen(
                    sandbox_command(run, invocation, invocation["argv"]),
                    cwd=run/"workspace", env=invocation["environment"],
                    stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                    text=True, start_new_session=True,
                )
                process.communicate(input=invocation["stdin"], timeout=timeout)
                returncode = process.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
            except (OSError, subprocess.SubprocessError) as exc:
                failure = type(exc).__name__ + ": " + str(exc)
            finally:
                if process is not None:
                    try:
                        cleanup = _terminate_tree(process)
                    except (RunnerError, OSError, subprocess.SubprocessError) as exc:
                        _kill_group(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
                        cleanup = {"passed": False, "error_type": type(exc).__name__}
                    returncode = process.returncode
    wall = time.monotonic()-started
    postflight = None
    if authorization is not None:
        from .ollama import OllamaClient
        from .runner import running_model_names
        client = OllamaClient("http://127.0.0.1:11434", timeout_seconds=30)
        try:
            loaded = running_model_names(client.list_running_models())
            if invocation["model"] in loaded:
                client.unload_model(invocation["model"])
            remaining = running_model_names(client.list_running_models())
            postflight = {"running_models": remaining, "passed": not remaining}
        except Exception as exc:
            postflight = {"passed": False, "error_type": type(exc).__name__}
        write_json(run/"postflight.json", postflight)
    complete = sum(r["status"] == "complete" for r in journal.requests)
    events_path = run/"agent-state/events.jsonl" if invocation["harness"] == "mirror" else run/"stdout.txt"
    malformed = 0
    event_count = 0
    if events_path.exists():
        for line in events_path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                if not isinstance(json.loads(line), dict):
                    raise ValueError("Expected event object")
                event_count += 1
            except ValueError:
                malformed += 1
    success = returncode == 0 and not timed_out and failure is None and bool(journal.requests) and complete == len(journal.requests) and event_count > 0 and malformed == 0
    success = success and cleanup is not None and cleanup["passed"]
    if invocation.get("provider_profile"):
        success = success and all(r.get("generation_conformant") is True for r in journal.requests)
    if postflight is not None:
        success = success and postflight["passed"]
    execution = {"returncode": returncode, "timed_out": timed_out, "launch_error": failure,
                 "wall_time_seconds": wall, "parent_timeout_seconds": timeout,
                 "runtime_success": success, "provider_requests": len(journal.requests),
                 "completed_provider_requests": complete, "native_event_count": event_count,
                 "malformed_event_lines": malformed,
                 "provider_token_usage": [r.get("usage") for r in journal.requests],
                 "postflight": postflight,
                 "process_cleanup": cleanup,
                 "termination_reason": "parent_timeout" if timed_out else "completed" if success else "harness_or_transport_failure"}
    try:
        frozen_workspace = _files(run/"workspace")
        frozen_agent_state = _files(run/"agent-state")
    except RunnerError as exc:
        execution["runtime_success"] = False
        record.update(state="execution_capture_failed", finished_at=utc_now(), execution=execution,
                      capture_error=str(exc), hidden_verification_executed=False)
        write_json(run/"run.json", record)
        return {"run_dir": str(run), "state": record["state"], **execution,
                "model_requests": 0 if responder is not None else sum(bool(r.get("forwarded_to_ollama")) for r in journal.requests),
                "hidden_verification_executed": False}
    record.update(state="execution_complete_verification_pending", finished_at=utc_now(),
                  execution=execution, model_requests=0 if responder is not None else sum(bool(r.get("forwarded_to_ollama")) for r in journal.requests),
                  stub_provider_requests=len(journal.requests) if responder is not None else 0,
                  candidate_code_executed="unknown_until_native_tool_review",
                  frozen_workspace=frozen_workspace,
                  frozen_agent_state=frozen_agent_state,
                  frozen_wire=_files(run/"provider-wire"),
                  frozen_outputs={p: sha256_file(run/p) for p in ["stdout.txt", "stderr.txt"]})
    write_json(run/"run.json", record)
    return {"run_dir": str(run), "state": record["state"], **execution,
            "model_requests": record["model_requests"], "hidden_verification_executed": False}


def finalize(root: Path, run: Path) -> dict:
    root = root.resolve()
    run, record, invocation = _load(root, run, {"execution_complete_verification_pending"})
    if (_files(run/"workspace") != record["frozen_workspace"]
        or _files(run/"agent-state") != record["frozen_agent_state"]
        or _files(run/"provider-wire") != record["frozen_wire"]
        or any(sha256_file(run/p) != sha for p, sha in record["frozen_outputs"].items())):
        raise RunnerError("Execution evidence or workspace changed before hidden verification")
    verification_workspace = run/"verification-workspace"
    shutil.copytree(run/"workspace", verification_workspace)
    if _files(verification_workspace) != record["frozen_workspace"]:
        raise RunnerError("Workspace changed while creating the private verification copy")
    verification = verify_coding_workspace(root, Path(record["case_path"]), verification_workspace)
    hidden_ran = (verification.get("tests") or {}).get("hidden", {}).get("status") in {"complete", "timeout"}
    record.update(state="complete", verification_completed_at=utc_now(),
                  hidden_verification_executed=hidden_ran, verification=verification,
                  verified_success=bool(record["execution"]["runtime_success"] and verification["verified_success"]))
    write_json(run/"verification.json", verification)
    record["verification_sha256"] = sha256_file(run/"verification.json")
    write_json(run/"run.json", record)
    return {"run_dir": str(run), "state": "complete", "verified_success": record["verified_success"],
            "verification": verification, "offline_transport": record["offline_transport"],
            "measured_admission": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("prepare", help="Prepare one coding case without inference")
    create.add_argument("--harness", choices=["mirror", "vibe"], required=True)
    create.add_argument("--condition", choices=sorted(PROTOCOLS), default="v0.1")
    create.add_argument("--model", required=True)
    create.add_argument("--case", type=Path, required=True)
    create.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    create.add_argument("--gateway-port", type=int, default=18741)
    create.add_argument("--rpc-port", type=int, default=18742)
    create.add_argument("--wall-seconds", type=int, help="Shorter excluded development-smoke budget")
    for command in ["sandbox-check", "qualify", "run", "finalize"]:
        child = sub.add_parser(command)
        child.add_argument("--run-dir", type=Path, required=True)
        if command == "run":
            child.add_argument("--authorization", type=Path, required=True)
    args = parser.parse_args(argv)
    root = Path.cwd()
    try:
        if args.command == "prepare":
            result = prepare(root, harness=args.harness, model=args.model, case_path=args.case,
                             results_dir=args.results_dir, gateway_port=args.gateway_port, rpc_port=args.rpc_port,
                             wall_seconds=args.wall_seconds, condition=args.condition)
        elif args.command == "sandbox-check":
            result = check_sandbox(_safe(root, args.run_dir))
        elif args.command == "qualify":
            result = execute(root, args.run_dir, responder=lambda payload, sequence: {})
        elif args.command == "run":
            result = execute(root, args.run_dir, authorization=args.authorization)
        else:
            result = finalize(root, args.run_dir)
        print(json.dumps(result, indent=2))
        if args.command in {"run", "qualify"}:
            return 0 if result["runtime_success"] else 1
        if args.command == "sandbox-check":
            return 0 if result["passed"] else 1
        # A stub does not solve a task; failed coding verification is expected
        # qualification evidence and remains distinct from process completion.
        return 0
    except (RunnerError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
