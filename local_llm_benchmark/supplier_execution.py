"""Future supplier runs with evaluation 0.3 and metrics 0.2, selected at preparation.

The model-facing Mini v0.2 and Pi v0.4 systems remain unchanged. This adapter
binds a separate evaluation identity before inference and cannot adopt an old
run or re-evaluate a completed attempt. Lifecycle commands remain sequential.
"""

from __future__ import annotations

import argparse
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from . import multi_format_mini_v02 as mini
from . import multi_format_pi_v04 as pi
from .multi_format_metrics_v02 import CONTRACT_PATH as METRICS_CONTRACT, normalize_run
from .multi_format_transfer_v021 import (
    DEFAULT_CONTRACT, load_evaluation_contract, verify_multi_format_transfer_report,
)
from .runner import RunnerError, load_json, sha256_file, write_json


CONFIG_PATH = Path("tasks/agentic/supplier-execution-v0.3.json")
CONFIG_ID = "supplier-execution-v0.3"
IMPLEMENTATION_PATH = Path("local_llm_benchmark/supplier_execution.py")


def evaluation_identity(root: Path) -> dict[str, Any]:
    load_evaluation_contract(root)
    config = load_json(root / CONFIG_PATH)
    if config != {
        "schema_version": "1.0.0", "configuration_id": CONFIG_ID,
        "evaluation_contract_path": DEFAULT_CONTRACT.as_posix(),
        "verifier_version": "2.1.0", "metrics_contract_path": METRICS_CONTRACT.as_posix(),
        "metrics_version": "0.2.0", "existing_runs_adoptable": False,
        "model_facing_harnesses": [mini.HARNESS_ID, pi.HARNESS_ID],
        "execution_authorized": False,
    }:
        raise RunnerError("Unexpected supplier execution configuration")
    paths = [
        CONFIG_PATH, IMPLEMENTATION_PATH, DEFAULT_CONTRACT, METRICS_CONTRACT,
        Path("local_llm_benchmark/multi_format_transfer_v021.py"),
        Path("local_llm_benchmark/multi_format_transfer.py"),
        Path("local_llm_benchmark/multi_format_metrics_v02.py"),
    ]
    return {
        "configuration_id": CONFIG_ID, "verifier_version": "2.1.0",
        "metrics_version": "0.2.0",
        "artifacts": [{"path": str(path), "sha256": sha256_file(root / path)} for path in paths],
    }


def prepare(root: Path, *, system: str, model: str, results_dir: Path,
            host: str = "http://127.0.0.1:11434") -> dict[str, Any]:
    """Create a fresh run and bind evaluation before any inference request."""
    if system not in {"mini", "pi"}:
        raise RunnerError("Supplier system must be mini or pi")
    identity = evaluation_identity(root)
    if system == "mini":
        result = mini.start(root, mini.base.MiniMultiFormatStartConfig(
            model=model, results_dir=results_dir, host=host))
    else:
        result = pi.prepare(root, pi.base.PiMultiFormatPrepareConfig(
            model=model, results_dir=results_dir, host=host))
    run_dir = Path(result["run_dir"])
    record = load_json(run_dir / "run.json")
    expected = "awaiting_model" if system == "mini" else "prepared_not_executed"
    if record.get("state") != expected or record.get("verification"):
        raise RunnerError("Supplier evaluation can only bind a fresh prepared run")
    record["evaluation_configuration"] = identity
    record["system_configuration_id"] = record["harness"]["harness_id"] + "+" + CONFIG_ID
    write_json(run_dir / "run.json", record)
    return _next_action({**result, "evaluation_configuration": identity}, system)


def _next_action(result: dict[str, Any], system: str) -> dict[str, Any]:
    if isinstance(result.get("next_action"), str):
        module = "multi_format_mini_v02" if system == "mini" else "multi_format_pi_v04"
        result["next_action"] = result["next_action"].replace(
            "local_llm_benchmark." + module, "local_llm_benchmark.supplier_execution")
    return result


@contextmanager
def _evaluation(adapter: Any) -> Iterator[None]:
    old = adapter.verify_multi_format_transfer_report
    adapter.verify_multi_format_transfer_report = verify_multi_format_transfer_report
    try:
        yield
    finally:
        adapter.verify_multi_format_transfer_report = old


def advance(root: Path, run_dir: Path, action: str) -> dict[str, Any]:
    """Dispatch through the original lifecycle with the prepared evaluator."""
    run_dir = run_dir.resolve()
    record = load_json(run_dir / "run.json")
    if record.get("evaluation_configuration") != evaluation_identity(root):
        raise RunnerError("Run lacks the prepared supplier evaluation identity or it drifted")
    harness = record.get("harness", {}).get("harness_id")
    adapter = {mini.HARNESS_ID: mini, pi.HARNESS_ID: pi}.get(harness)
    if adapter is None or record.get("system_configuration_id") != harness + "+" + CONFIG_ID:
        raise RunnerError("Supplier complete-system identity differs")
    if record.get("state") == "complete":
        raise RunnerError("A completed supplier attempt cannot be advanced or rescored")
    actions = ({"call": mini.call, "step": mini.step, "finalize": mini.finalize}
               if adapter is mini else
               {"sandbox-check": lambda root, path: pi.sandbox_check(path),
                "run": pi.run, "finalize": pi.finalize})
    if action not in actions:
        raise RunnerError(f"Action {action!r} is not available for {harness}")
    # Both adapters select their verifier inside their existing scoped kernel
    # configuration. Replace that input only, then restore it even on failure.
    with _evaluation(adapter):
        result = actions[action](root, run_dir)
    if action == "finalize":
        completed = load_json(run_dir / "run.json")
        if completed.get("verification", {}).get("verifier_version") != "2.1.0":
            raise RunnerError("Supplier finalization did not select verifier 2.1.0")
        metrics = {"version": "0.2.0", **normalize_run(completed)}
        completed["normalized_metrics"] = metrics
        write_json(run_dir / "run.json", completed)
        result["normalized_metrics"] = metrics
    return _next_action(result, "mini" if adapter is mini else "pi")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("prepare")
    start.add_argument("--system", choices=("mini", "pi"), required=True)
    start.add_argument("--model", required=True)
    start.add_argument("--results-dir", type=Path, default=Path("results/agentic-runs"))
    start.add_argument("--host", default="http://127.0.0.1:11434")
    for name in ("call", "step", "sandbox-check", "run", "finalize"):
        commands.add_parser(name).add_argument("--run-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path.cwd().resolve()
    try:
        result = (prepare(root, system=args.system, model=args.model,
                          results_dir=args.results_dir, host=args.host)
                  if args.command == "prepare" else advance(root, args.run_dir, args.command))
    except RunnerError as exc:
        parser.exit(1, f"{exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
