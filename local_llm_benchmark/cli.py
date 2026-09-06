"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .agentic import (
    DEFAULT_MINI_HARNESS_PATH,
    MiniAgentStartConfig,
    call_mini_agent_model,
    start_mini_agent_run,
    step_mini_agent_action,
)
from .challenger import ChallengerBundleConfig, assemble_challenger_bundle_batch
from .coding import (
    DEFAULT_CODING_CASE_PATH,
    CodingRunConfig,
    audit_coding_case,
    diagnose_fenced_file_transport,
    finalize_deferred_track_a_run,
    run_track_a_once,
    verify_candidate_artifact,
)
from .ollama import OllamaError
from .macos_sandbox import validate_pi_seatbelt
from .model_catalog import (
    DEFAULT_MODEL_CATALOG_PATH,
    ModelRegistrationConfig,
    register_models,
)
from .pi_adapter import (
    DEFAULT_PI_HARNESS_PATH,
    PiAgentPrepareConfig,
    execute_pi_agent_run,
    finalize_pi_agent_run,
    prepare_pi_agent_run,
)
from .pi_sweep import (
    DEFAULT_PI_SWEEP_PLAN_PATH,
    PiSweepConfig,
    PiSweepResumeConfig,
    resume_pi_sweep,
    start_pi_sweep,
)
from .report import (
    DEFAULT_COMPARISONS_DIR,
    DEFAULT_INDEX_OUTPUT,
    DEFAULT_MARKDOWN_OUTPUT,
    DEFAULT_SELECTION_PATH,
    write_report,
)
from .runner import (
    DEFAULT_CASE_PATH,
    DEFAULT_SUITE_PATH,
    ComparisonConfig,
    RunConfig,
    RunnerError,
    SuiteConfig,
    SuiteResumeConfig,
    add_warm_repeats,
    run_completion_result,
    run_cold_warm_comparison,
    run_model_suite,
    run_once,
    resume_model_suite,
    resolve_repo_path,
)


def parse_think(value: str) -> bool | str:
    normalized = value.casefold()
    if normalized == "false":
        return False
    if normalized == "true":
        return True
    if normalized in {"low", "medium", "high", "max"}:
        return normalized
    raise argparse.ArgumentTypeError("think must be false, true, low, medium, high, or max")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="local-llm-benchmark")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="Run one case with one Ollama model")
    run_parser.add_argument("--model", required=True, help="Exact installed Ollama model name")
    run_parser.add_argument("--case", type=Path, default=DEFAULT_CASE_PATH)
    run_parser.add_argument(
        "--host",
        default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
    )
    run_parser.add_argument("--results-dir", type=Path, default=Path("results/runs"))
    run_parser.add_argument("--temperature", type=float, default=0.0)
    run_parser.add_argument("--seed", type=int, default=42)
    run_parser.add_argument("--num-ctx", type=int, default=8192)
    run_parser.add_argument("--num-predict", type=int, default=2600)
    run_parser.add_argument("--think", type=parse_think, default=False)
    run_parser.add_argument("--keep-alive", default="5m")
    run_parser.add_argument("--timeout", type=float, default=600.0)

    compare_parser = subparsers.add_parser(
        "compare",
        help="Run one explicit cold and one immediate warm request per model",
    )
    compare_parser.add_argument(
        "--models",
        nargs="+",
        required=True,
        help="Two or more exact installed Ollama model names",
    )
    compare_parser.add_argument("--case", type=Path, default=DEFAULT_CASE_PATH)
    compare_parser.add_argument(
        "--host",
        default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
    )
    compare_parser.add_argument("--results-dir", type=Path, default=Path("results/runs"))
    compare_parser.add_argument(
        "--comparisons-dir",
        type=Path,
        default=Path("results/comparisons"),
    )
    compare_parser.add_argument("--temperature", type=float, default=0.0)
    compare_parser.add_argument("--seed", type=int, default=42)
    compare_parser.add_argument("--num-ctx", type=int, default=8192)
    compare_parser.add_argument("--num-predict", type=int, default=2600)
    compare_parser.add_argument("--think", type=parse_think, default=False)
    compare_parser.add_argument("--keep-alive", default="10m")
    compare_parser.add_argument("--timeout", type=float, default=600.0)

    repeat_parser = subparsers.add_parser(
        "repeat-warm",
        help="Append preloaded warm measurements to a completed comparison",
    )
    repeat_parser.add_argument("--comparison-dir", type=Path, required=True)
    repeat_parser.add_argument("--model", required=True)
    repeat_parser.add_argument("--runs", type=int, default=2)
    repeat_parser.add_argument("--reason", required=True)
    repeat_parser.add_argument("--case", type=Path, default=DEFAULT_CASE_PATH)
    repeat_parser.add_argument(
        "--host",
        default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
    )
    repeat_parser.add_argument("--results-dir", type=Path, default=Path("results/runs"))
    repeat_parser.add_argument("--timeout", type=float, default=600.0)

    suite_parser = subparsers.add_parser(
        "suite",
        help="Run one Ollama model cold and warm across a suite manifest",
    )
    suite_parser.add_argument("--model", required=True)
    suite_parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE_PATH)
    suite_parser.add_argument(
        "--host",
        default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
    )
    suite_parser.add_argument("--results-dir", type=Path, default=Path("results/runs"))
    suite_parser.add_argument("--sweeps-dir", type=Path, default=Path("results/sweeps"))
    suite_parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Override the per-request timeout declared by the suite manifest",
    )

    suite_resume_parser = subparsers.add_parser(
        "suite-resume",
        help="Resume only unfinished cases in an append-only capability sweep",
    )
    suite_resume_parser.add_argument("--sweep-dir", type=Path, required=True)
    suite_resume_parser.add_argument(
        "--host",
        default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
    )
    suite_resume_parser.add_argument(
        "--results-dir", type=Path, default=Path("results/runs")
    )
    suite_resume_parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Override the original suite's per-request timeout",
    )

    model_register_parser = subparsers.add_parser(
        "model-register",
        help="Register exact installed Ollama deployments without inference",
    )
    model_register_parser.add_argument(
        "--models",
        nargs="+",
        required=True,
        help="One or more exact installed Ollama model names",
    )
    model_register_parser.add_argument(
        "--catalog", type=Path, default=DEFAULT_MODEL_CATALOG_PATH
    )
    model_register_parser.add_argument(
        "--host",
        default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
    )
    model_register_parser.add_argument("--timeout", type=float, default=30.0)

    challenger_parser = subparsers.add_parser(
        "challenger-bundles",
        help="Assemble blinded joint-evaluation bundles for completed late challengers",
    )
    challenger_parser.add_argument(
        "--sweep-dir",
        type=Path,
        action="append",
        required=True,
        help="Completed sweep directory; repeat once for every new deployment",
    )
    challenger_parser.add_argument(
        "--selection",
        type=Path,
        default=Path("reports/comparison-selection.json"),
    )
    challenger_parser.add_argument(
        "--comparisons-dir",
        type=Path,
        default=Path("results/comparisons"),
    )
    challenger_parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("results/runs"),
    )
    challenger_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/challenger-evaluations"),
    )
    challenger_parser.add_argument(
        "--allow-late-baseline",
        action="store_true",
        help=(
            "Allow an explicit completed comparison to supply baseline evidence "
            "for a case that had no baseline when the challenger sweep ran"
        ),
    )

    report_parser = subparsers.add_parser(
        "report",
        help="Build sanitized aggregate JSON and Markdown reports",
    )
    report_parser.add_argument(
        "--selection",
        type=Path,
        default=DEFAULT_SELECTION_PATH,
    )
    report_parser.add_argument(
        "--comparisons-dir",
        type=Path,
        default=DEFAULT_COMPARISONS_DIR,
    )
    report_parser.add_argument(
        "--index-output",
        type=Path,
        default=DEFAULT_INDEX_OUTPUT,
    )
    report_parser.add_argument(
        "--markdown-output",
        type=Path,
        default=DEFAULT_MARKDOWN_OUTPUT,
    )

    coding_check_parser = subparsers.add_parser(
        "coding-check",
        help="Validate a frozen Track A coding fixture and its red baseline",
    )
    coding_check_parser.add_argument(
        "--case", type=Path, default=DEFAULT_CODING_CASE_PATH
    )

    coding_verify_parser = subparsers.add_parser(
        "coding-verify",
        help="Install and deterministically verify one existing Track A artifact",
    )
    coding_verify_input = coding_verify_parser.add_mutually_exclusive_group(
        required=True
    )
    coding_verify_input.add_argument(
        "--artifact",
        type=Path,
        help="Candidate response in the artifact format declared by the case",
    )
    coding_verify_input.add_argument(
        "--patch",
        type=Path,
        help="Backward-compatible alias for a unified-diff candidate",
    )
    coding_verify_parser.add_argument(
        "--case", type=Path, default=DEFAULT_CODING_CASE_PATH
    )

    coding_run_parser = subparsers.add_parser(
        "coding-run",
        help="Run and verify one direct non-agentic Ollama coding attempt",
    )
    coding_run_parser.add_argument("--model", required=True)
    coding_run_parser.add_argument(
        "--case", type=Path, default=DEFAULT_CODING_CASE_PATH
    )
    coding_run_parser.add_argument(
        "--host",
        default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
    )
    coding_run_parser.add_argument(
        "--results-dir", type=Path, default=Path("results/coding-runs")
    )
    coding_run_parser.add_argument("--temperature", type=float, default=None)
    coding_run_parser.add_argument("--seed", type=int, default=None)
    coding_run_parser.add_argument("--num-ctx", type=int, default=None)
    coding_run_parser.add_argument("--num-predict", type=int, default=None)
    coding_run_parser.add_argument("--think", type=parse_think, default=None)
    coding_run_parser.add_argument("--keep-alive", default=None)
    coding_run_parser.add_argument("--timeout", type=float, default=None)
    coding_run_parser.add_argument(
        "--defer-verification",
        action="store_true",
        help="Persist generation first and execute candidate code in a later command",
    )

    coding_complete_parser = subparsers.add_parser(
        "coding-complete",
        help="Execute verifier checks for one deferred Track A run",
    )
    coding_complete_parser.add_argument("--run-dir", type=Path, required=True)

    coding_diagnostic_parser = subparsers.add_parser(
        "coding-diagnose-transport",
        help="Run a frozen, secondary fence-only transport diagnostic",
    )
    coding_diagnostic_parser.add_argument("--artifact", type=Path, required=True)
    coding_diagnostic_parser.add_argument("--protocol", type=Path, required=True)
    coding_diagnostic_parser.add_argument(
        "--case", type=Path, default=DEFAULT_CODING_CASE_PATH
    )

    mini_start_parser = subparsers.add_parser(
        "coding-agent-mini-start",
        help="Create a sandbox-friendly Track B mini-agent run without inference",
    )
    mini_start_parser.add_argument("--model", required=True)
    mini_start_parser.add_argument("--case", type=Path, required=True)
    mini_start_parser.add_argument(
        "--harness", type=Path, default=DEFAULT_MINI_HARNESS_PATH
    )
    mini_start_parser.add_argument(
        "--host",
        default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
    )
    mini_start_parser.add_argument(
        "--results-dir", type=Path, default=Path("results/agentic-runs")
    )

    mini_call_parser = subparsers.add_parser(
        "coding-agent-mini-call",
        help="Execute only the pending Ollama turn for a Track B mini-agent run",
    )
    mini_call_parser.add_argument("--run-dir", type=Path, required=True)

    mini_step_parser = subparsers.add_parser(
        "coding-agent-mini-step",
        help="Apply one saved mini-agent action and execute bounded tools if requested",
    )
    mini_step_parser.add_argument("--run-dir", type=Path, required=True)

    pi_prepare_parser = subparsers.add_parser(
        "coding-agent-pi-prepare",
        help="Prepare a pinned Pi Track B run without inference or candidate execution",
    )
    pi_prepare_parser.add_argument("--model", required=True)
    pi_prepare_parser.add_argument("--case", type=Path, required=True)
    pi_prepare_parser.add_argument(
        "--harness", type=Path, default=DEFAULT_PI_HARNESS_PATH
    )
    pi_prepare_parser.add_argument(
        "--host",
        default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
    )
    pi_prepare_parser.add_argument(
        "--results-dir", type=Path, default=Path("results/agentic-runs")
    )
    pi_sandbox_parser = subparsers.add_parser(
        "coding-agent-pi-sandbox-check",
        help="Run no-inference adversarial checks against a prepared Pi Seatbelt profile",
    )
    pi_sandbox_parser.add_argument("--run-dir", type=Path, required=True)
    pi_run_parser = subparsers.add_parser(
        "coding-agent-pi-run",
        help="Execute prepared Pi under an accepted sandbox without hidden verification",
    )
    pi_run_parser.add_argument("--run-dir", type=Path, required=True)
    pi_finalize_parser = subparsers.add_parser(
        "coding-agent-pi-finalize",
        help="Run separate final verification for an executed Pi trajectory",
    )
    pi_finalize_parser.add_argument("--run-dir", type=Path, required=True)
    pi_sweep_parser = subparsers.add_parser(
        "coding-agent-pi-sweep",
        help="Execute a frozen resumable multi-model Pi capability sweep",
    )
    pi_sweep_parser.add_argument(
        "--plan", type=Path, default=DEFAULT_PI_SWEEP_PLAN_PATH
    )
    pi_sweep_parser.add_argument(
        "--host",
        default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
    )
    pi_sweep_parser.add_argument(
        "--results-dir", type=Path, default=Path("results/agentic-sweeps")
    )
    pi_sweep_parser.add_argument(
        "--agent-results-dir", type=Path, default=Path("results/agentic-runs")
    )
    pi_sweep_resume_parser = subparsers.add_parser(
        "coding-agent-pi-sweep-resume",
        help="Resume an existing Pi capability sweep without repeating outcomes",
    )
    pi_sweep_resume_parser.add_argument("--sweep-dir", type=Path, required=True)
    pi_sweep_resume_parser.add_argument(
        "--host",
        default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    if args.command == "run":
        config = RunConfig(
            model=args.model,
            case_path=args.case,
            host=args.host,
            results_dir=args.results_dir,
            temperature=args.temperature,
            seed=args.seed,
            num_ctx=args.num_ctx,
            num_predict=args.num_predict,
            think=args.think,
            keep_alive=args.keep_alive,
            timeout_seconds=args.timeout,
        )
        try:
            result = run_once(repo_root, config)
        except (RunnerError, OllamaError) as exc:
            print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(
            json.dumps(
                run_completion_result(result),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.command == "compare":
        config = ComparisonConfig(
            models=tuple(args.models),
            case_path=args.case,
            host=args.host,
            results_dir=args.results_dir,
            comparisons_dir=args.comparisons_dir,
            temperature=args.temperature,
            seed=args.seed,
            num_ctx=args.num_ctx,
            num_predict=args.num_predict,
            think=args.think,
            keep_alive=args.keep_alive,
            timeout_seconds=args.timeout,
        )
        try:
            result = run_cold_warm_comparison(repo_root, config)
        except (RunnerError, OllamaError) as exc:
            print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "repeat-warm":
        try:
            result = add_warm_repeats(
                repo_root,
                comparison_dir=args.comparison_dir,
                model=args.model,
                count=args.runs,
                reason=args.reason,
                case_path=args.case,
                host=args.host,
                results_dir=args.results_dir,
                timeout_seconds=args.timeout,
            )
        except (RunnerError, OllamaError) as exc:
            print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "suite":
        try:
            result = run_model_suite(
                repo_root,
                SuiteConfig(
                    model=args.model,
                    suite_path=args.suite,
                    host=args.host,
                    results_dir=args.results_dir,
                    sweeps_dir=args.sweeps_dir,
                    timeout_seconds=args.timeout,
                ),
            )
        except (RunnerError, OllamaError) as exc:
            print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "suite-resume":
        try:
            result = resume_model_suite(
                repo_root,
                SuiteResumeConfig(
                    sweep_dir=args.sweep_dir,
                    host=args.host,
                    results_dir=args.results_dir,
                    timeout_seconds=args.timeout,
                ),
            )
        except (RunnerError, OllamaError) as exc:
            print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "model-register":
        try:
            result = register_models(
                repo_root,
                ModelRegistrationConfig(
                    models=tuple(args.models),
                    catalog_path=args.catalog,
                    host=args.host,
                    timeout_seconds=args.timeout,
                ),
            )
        except (RunnerError, OllamaError) as exc:
            print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "challenger-bundles":
        try:
            result = assemble_challenger_bundle_batch(
                repo_root,
                ChallengerBundleConfig(
                    sweep_dirs=tuple(args.sweep_dir),
                    selection_path=args.selection,
                    comparisons_dir=args.comparisons_dir,
                    results_dir=args.results_dir,
                    output_dir=args.output_dir,
                    allow_late_baseline=args.allow_late_baseline,
                ),
            )
        except RunnerError as exc:
            print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "report":
        try:
            result = write_report(
                repo_root,
                selection_path=args.selection,
                comparisons_dir=args.comparisons_dir,
                index_output=args.index_output,
                markdown_output=args.markdown_output,
            )
        except RunnerError as exc:
            print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "coding-check":
        try:
            result = audit_coding_case(repo_root, args.case)
        except RunnerError as exc:
            print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result["status"] == "complete" else 1
    if args.command == "coding-verify":
        try:
            artifact_path = resolve_repo_path(
                repo_root, args.artifact if args.artifact is not None else args.patch
            )
            result = verify_candidate_artifact(
                repo_root,
                args.case,
                artifact_path.read_text(encoding="utf-8"),
            )
        except (OSError, RunnerError) as exc:
            print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result["verified_success"] else 1
    if args.command == "coding-run":
        try:
            result = run_track_a_once(
                repo_root,
                CodingRunConfig(
                    model=args.model,
                    case_path=args.case,
                    host=args.host,
                    results_dir=args.results_dir,
                    temperature=args.temperature,
                    seed=args.seed,
                    num_ctx=args.num_ctx,
                    num_predict=args.num_predict,
                    think=args.think,
                    keep_alive=args.keep_alive,
                    timeout_seconds=args.timeout,
                    defer_verification=args.defer_verification,
                ),
            )
        except (RunnerError, OllamaError) as exc:
            print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "coding-complete":
        try:
            result = finalize_deferred_track_a_run(repo_root, args.run_dir)
        except (OSError, RunnerError) as exc:
            print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result["verified_success"] else 1
    if args.command == "coding-diagnose-transport":
        try:
            artifact_path = resolve_repo_path(repo_root, args.artifact)
            result = diagnose_fenced_file_transport(
                repo_root,
                args.case,
                args.protocol,
                artifact_path.read_text(encoding="utf-8"),
            )
        except (OSError, RunnerError) as exc:
            print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        verification = result.get("verification")
        return 0 if verification and verification["verified_success"] else 1
    if args.command == "coding-agent-mini-start":
        try:
            result = start_mini_agent_run(
                repo_root,
                MiniAgentStartConfig(
                    model=args.model,
                    case_path=args.case,
                    harness_path=args.harness,
                    results_dir=args.results_dir,
                    host=args.host,
                ),
            )
        except (OSError, RunnerError) as exc:
            print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "coding-agent-mini-call":
        try:
            result = call_mini_agent_model(repo_root, args.run_dir)
        except (OSError, RunnerError, OllamaError) as exc:
            print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "coding-agent-mini-step":
        try:
            result = step_mini_agent_action(repo_root, args.run_dir)
        except (OSError, RunnerError) as exc:
            print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        if result["state"] != "complete":
            return 0
        return 0 if result["verified_success"] else 1
    if args.command == "coding-agent-pi-prepare":
        try:
            result = prepare_pi_agent_run(
                repo_root,
                PiAgentPrepareConfig(
                    model=args.model,
                    case_path=args.case,
                    harness_path=args.harness,
                    results_dir=args.results_dir,
                    host=args.host,
                ),
            )
        except (OSError, RunnerError) as exc:
            print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "coding-agent-pi-sandbox-check":
        try:
            result = validate_pi_seatbelt(args.run_dir)
        except (OSError, RunnerError) as exc:
            print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "coding-agent-pi-run":
        try:
            result = execute_pi_agent_run(repo_root, args.run_dir)
        except (OSError, RunnerError) as exc:
            print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result["runtime_success"] else 1
    if args.command == "coding-agent-pi-finalize":
        try:
            result = finalize_pi_agent_run(repo_root, args.run_dir)
        except (OSError, RunnerError) as exc:
            print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result["verified_success"] else 1
    if args.command == "coding-agent-pi-sweep":
        try:
            result = start_pi_sweep(
                repo_root,
                PiSweepConfig(
                    plan_path=args.plan,
                    results_dir=args.results_dir,
                    agent_results_dir=args.agent_results_dir,
                    host=args.host,
                ),
            )
        except (OSError, RunnerError, OllamaError) as exc:
            print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.command == "coding-agent-pi-sweep-resume":
        try:
            result = resume_pi_sweep(
                repo_root,
                PiSweepResumeConfig(sweep_dir=args.sweep_dir, host=args.host),
            )
        except (OSError, RunnerError, OllamaError) as exc:
            print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    return 2
