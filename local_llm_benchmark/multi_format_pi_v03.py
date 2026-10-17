"""Pinned Pi multi-format adapter v0.3 with extension-load acceptance."""

from __future__ import annotations

import argparse
import json
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Iterator

from . import multi_format_pi as base
from .macos_sandbox import pi_sandbox_environment, run_seatbelt_command
from .multi_format_pi_v02 import python_worker_executable
from .runner import RunnerError, load_json, sha256_file, write_json


HARNESS_ID = "pi-multi-format-v0.3"
DEFAULT_HARNESS_PATH = Path("tasks/agentic/track-b/pi-multi-format-v0.3.json")


@contextmanager
def _configured_base() -> Iterator[Path]:
    old_harness_id = base.HARNESS_ID
    old_executable = base.sys.executable
    worker = python_worker_executable(old_executable)
    base.HARNESS_ID = HARNESS_ID
    base.sys.executable = str(worker)
    try:
        yield worker
    finally:
        base.HARNESS_ID = old_harness_id
        base.sys.executable = old_executable


def prepare(repo_root: Path, config: base.PiMultiFormatPrepareConfig) -> dict:
    corrected = replace(config, harness_path=DEFAULT_HARNESS_PATH)
    with _configured_base() as worker:
        result = base.prepare_pi_multi_format_run(repo_root, corrected)
    run_dir = Path(result["run_dir"])
    record_path = run_dir / "run.json"
    record = load_json(record_path)
    wrapper = repo_root / "local_llm_benchmark/multi_format_pi_v03.py"
    record["harness"]["adapter_wrapper_path"] = wrapper.relative_to(repo_root).as_posix()
    record["harness"]["adapter_wrapper_sha256"] = sha256_file(wrapper)
    record["execution_boundary"]["python_launcher_bypassed"] = True
    record["execution_boundary"]["python_worker_executable"] = str(worker)
    record["execution_boundary"]["explicit_extension_acceptance_passed"] = False
    write_json(record_path, record)
    return result


def _explicit_extension_check(run_dir: Path) -> dict:
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
        "detail": "The exact explicit extension and its policy load before inference.",
        "stderr_nonempty": bool(result.stderr),
    }


def sandbox_check(run_dir: Path) -> dict:
    with _configured_base():
        result = base.validate_pi_multi_format_seatbelt(run_dir)
    extension_check = _explicit_extension_check(run_dir)
    result["checks"].append(extension_check)
    result["passed"] = result["passed"] and extension_check["passed"]
    acceptance = run_dir.resolve() / "pi-sandbox-acceptance.json"
    write_json(acceptance, result)
    record_path = run_dir.resolve() / "run.json"
    record = load_json(record_path)
    record["execution_boundary"]["sandbox_acceptance_passed"] = result["passed"]
    record["execution_boundary"]["explicit_extension_acceptance_passed"] = extension_check["passed"]
    record["execution_boundary"]["sandbox_acceptance_sha256"] = sha256_file(acceptance)
    write_json(record_path, record)
    if not result["passed"]:
        raise RunnerError("Pi multi-format v0.3 explicit extension acceptance failed")
    return result


def run(repo_root: Path, run_dir: Path) -> dict:
    record = load_json(run_dir.resolve() / "run.json")
    if record.get("execution_boundary", {}).get("explicit_extension_acceptance_passed") is not True:
        raise RunnerError("Pi multi-format v0.3 requires explicit extension acceptance")
    with _configured_base():
        return base.execute_pi_multi_format_run(repo_root, run_dir)


def finalize(repo_root: Path, run_dir: Path) -> dict:
    with _configured_base():
        return base.finalize_pi_multi_format_run(repo_root, run_dir)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--model", required=True)
    prepare_parser.add_argument("--case", type=Path, default=base.DEFAULT_CASE_PATH)
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
                model=args.model,
                case_path=args.case,
                results_dir=args.results_dir,
                host=args.host,
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
