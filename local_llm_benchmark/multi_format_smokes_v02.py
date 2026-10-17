"""Validation and resource preflight for the corrected Pi multi-format smoke."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from .log_incident_smokes import _validate_artifacts, run_resource_gate
from .ollama import OllamaClient, OllamaError
from .runner import RunnerError, load_json, resolve_repo_path, sha256_file


DEFAULT_PLAN = Path(
    "tasks/agentic/track-b/pi-multi-format-qwen38-development-smoke-v0.2.json"
)


def load_pi_multi_format_v02_smoke(
    repo_root: Path, plan_path: Path = DEFAULT_PLAN
) -> dict[str, Any]:
    path = resolve_repo_path(repo_root, plan_path)
    plan = load_json(path)
    if (
        plan.get("schema_version") != "1.0.0"
        or plan.get("status") != "frozen_before_execution"
        or plan.get("track") != "B"
        or plan.get("harness_id") != "pi-multi-format-v0.2"
        or plan.get("protocol_id") != "agentic-multi-format-v0.1"
        or plan.get("evidence_class") != "excluded_development_recovery_smoke"
    ):
        raise RunnerError("Unexpected Pi multi-format v0.2 smoke identity")
    case = plan.get("case", {})
    if (
        case.get("case_id")
        != "agentic.documents.rollout-readiness-reconciliation"
        or case.get("case_version") != "1.0.0"
    ):
        raise RunnerError("Unexpected Pi multi-format v0.2 case")
    comparison = plan.get("comparison_rules", {})
    if (
        comparison.get("attempts") != 1
        or comparison.get("automatic_retries") != 0
        or comparison.get("result_excluded_from_measured_aggregates") is not True
        or comparison.get("distinct_system_identity_from_v0_1") is not True
        or comparison.get("completed_mini_smoke_repeated") is not False
    ):
        raise RunnerError("Pi multi-format v0.2 exceeds recovery scope")
    predecessor = plan.get("predecessor_outcome", {})
    if (
        predecessor.get("harness_id") != "pi-multi-format-v0.1"
        or predecessor.get("inference_requests_made") != 0
        or predecessor.get("preserved") is not True
    ):
        raise RunnerError("Pi multi-format v0.1 failure boundary is incomplete")
    authorization = plan.get("authorization", {})
    if (
        authorization.get("status") != "authorized_after_new_resource_gate"
        or authorization.get("live_execution_allowed_only_after_new_resource_gate")
        is not True
    ):
        raise RunnerError("Pi multi-format v0.2 authorization is incomplete")
    gate = plan.get("resource_gate", {})
    if (
        gate.get("empty_state_observation_seconds") != 30
        or gate.get("loaded_models_must_be_empty") is not True
        or gate.get("manual_exclusive_window_confirmation_received") is not True
        or gate.get("process_snapshots") != 2
    ):
        raise RunnerError("Pi multi-format v0.2 resource gate is incomplete")
    rules = gate.get("blocking_process_rules")
    if not isinstance(rules, list) or not rules:
        raise RunnerError("Pi multi-format v0.2 requires process rules")
    for rule in rules:
        try:
            re.compile(rule["pattern"])
        except (KeyError, TypeError, re.error) as exc:
            raise RunnerError("Invalid Pi multi-format v0.2 process rule") from exc
    frozen = plan.get("frozen_inputs", {})
    _validate_artifacts(repo_root, frozen.get("artifacts"), "Pi multi-format v0.2 smoke")
    qualification = resolve_repo_path(repo_root, Path(frozen.get("qualification_path", "")))
    if sha256_file(qualification) != frozen.get("qualification_sha256"):
        raise RunnerError("Pi multi-format v0.2 qualification drift")
    return {"plan": plan, "path": path, "sha256": sha256_file(path)}


def run_preflight(
    repo_root: Path,
    plan_path: Path = DEFAULT_PLAN,
    *,
    exclusive_window_confirmed: bool = False,
) -> dict[str, Any]:
    loaded = load_pi_multi_format_v02_smoke(repo_root, plan_path)
    if not exclusive_window_confirmed:
        raise RunnerError("Pi multi-format v0.2 requires fresh window confirmation")
    plan = loaded["plan"]
    return run_resource_gate(plan, client=OllamaClient(plan["runtime"]["host"]))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    preflight.add_argument("--exclusive-window-confirmed", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    try:
        if args.command == "validate":
            loaded = load_pi_multi_format_v02_smoke(repo_root, args.plan)
            result = {
                "status": "valid",
                "plan_id": loaded["plan"]["plan_id"],
                "plan_sha256": loaded["sha256"],
                "live_ollama_requests": 0,
            }
        else:
            result = run_preflight(
                repo_root,
                args.plan,
                exclusive_window_confirmed=args.exclusive_window_confirmed,
            )
    except (OSError, RunnerError, OllamaError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
