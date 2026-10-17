"""Corrected pinned Pi adapter for real multi-format artifacts v0.2.

V0.1 admitted Homebrew's framework launcher as the Python executable. On
macOS that launcher spawns the Python.app worker, which the exact Seatbelt
process allowlist correctly denied. V0.2 preserves the complete V0.1 protocol
and selects that real worker directly.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Iterator

from . import multi_format_pi as base
from .runner import RunnerError, load_json, sha256_file, write_json


HARNESS_ID = "pi-multi-format-v0.2"
DEFAULT_HARNESS_PATH = Path("tasks/agentic/track-b/pi-multi-format-v0.2.json")


def python_worker_executable(executable: str | Path | None = None) -> Path:
    """Resolve Homebrew framework Python's non-spawning app executable."""
    launcher = Path(executable or sys.executable).resolve()
    if platform.system() != "Darwin":
        raise RunnerError("Pi multi-format v0.2 requires macOS Seatbelt")
    if len(launcher.parents) < 2:
        raise RunnerError("Python framework launcher path is incomplete")
    worker = (
        launcher.parents[1]
        / "Resources"
        / "Python.app"
        / "Contents"
        / "MacOS"
        / "Python"
    ).resolve()
    if not worker.is_file() or worker.name != "Python":
        raise RunnerError("Python.app worker executable is unavailable")
    return worker


@contextmanager
def _configured_base() -> Iterator[Path]:
    """Apply the V0.2 identity only for one delegated adapter operation."""
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
    """Prepare a V0.2 run with the exact Python.app worker in policy."""
    corrected = replace(config, harness_path=DEFAULT_HARNESS_PATH)
    with _configured_base() as worker:
        result = base.prepare_pi_multi_format_run(repo_root, corrected)
    run_dir = Path(result["run_dir"])
    record_path = run_dir / "run.json"
    record = load_json(record_path)
    wrapper = repo_root / "local_llm_benchmark/multi_format_pi_v02.py"
    record["harness"]["adapter_wrapper_path"] = wrapper.relative_to(repo_root).as_posix()
    record["harness"]["adapter_wrapper_sha256"] = sha256_file(wrapper)
    record["execution_boundary"]["python_launcher_bypassed"] = True
    record["execution_boundary"]["python_worker_executable"] = str(worker)
    write_json(record_path, record)
    return result


def sandbox_check(run_dir: Path) -> dict:
    with _configured_base():
        return base.validate_pi_multi_format_seatbelt(run_dir)


def run(repo_root: Path, run_dir: Path) -> dict:
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
