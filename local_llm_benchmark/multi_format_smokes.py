"""Validation and resource preflight for excluded multi-format smokes v0.1."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from .log_incident_smokes import _validate_artifacts, run_resource_gate
from .ollama import OllamaClient, OllamaError
from .runner import RunnerError, load_json, resolve_repo_path, sha256_file


DEFAULT_PAIR_PLAN = Path(
    "tasks/agentic/track-b/multi-format-qualification-smokes-v0.1.json"
)
EXPECTED_HARNESSES = ["mini-multi-format-v0.1", "pi-multi-format-v0.1"]


def load_excluded_multi_format_smoke(
    repo_root: Path, plan_path: Path, expected_harness: str
) -> dict[str, Any]:
    """Validate one one-attempt excluded real-artifact smoke."""
    path = resolve_repo_path(repo_root, plan_path)
    plan = load_json(path)
    if (
        plan.get("schema_version") != "1.0.0"
        or plan.get("status") != "frozen_before_execution"
        or plan.get("track") != "B"
        or plan.get("harness_id") != expected_harness
        or plan.get("protocol_id") != "agentic-multi-format-v0.1"
        or plan.get("evidence_class") != "excluded_development_smoke"
    ):
        raise RunnerError("Unexpected multi-format smoke identity")
    if expected_harness not in EXPECTED_HARNESSES:
        raise RunnerError("Unadmitted multi-format complete system")
    case = plan.get("case", {})
    if (
        case.get("case_id") != "agentic.documents.rollout-readiness-reconciliation"
        or case.get("case_version") != "1.0.0"
    ):
        raise RunnerError("Unexpected multi-format smoke case")
    comparison = plan.get("comparison_rules", {})
    if (
        comparison.get("attempts") != 1
        or comparison.get("automatic_retries") != 0
        or comparison.get("result_excluded_from_measured_aggregates") is not True
        or comparison.get("no_model_or_harness_ranking_claim") is not True
    ):
        raise RunnerError("Multi-format smoke must remain one excluded attempt")
    authorization = plan.get("authorization", {})
    if (
        authorization.get("status") != "resource_window_confirmation_pending"
        or authorization.get("live_execution_allowed_only_after_fresh_confirmation")
        is not True
    ):
        raise RunnerError("Multi-format smoke resource authorization is incomplete")
    runtime = plan.get("runtime", {})
    deployment = plan.get("deployment", {})
    if (
        runtime.get("name") != "ollama"
        or not isinstance(runtime.get("version"), str)
        or not isinstance(deployment.get("name"), str)
        or not isinstance(deployment.get("digest"), str)
        or len(deployment["digest"]) != 64
    ):
        raise RunnerError("Multi-format smoke deployment identity is incomplete")
    frozen = plan.get("frozen_inputs", {})
    _validate_artifacts(repo_root, frozen.get("artifacts"), "multi-format smoke")
    qualification = resolve_repo_path(repo_root, Path(frozen.get("qualification_path", "")))
    if sha256_file(qualification) != frozen.get("qualification_sha256"):
        raise RunnerError("Multi-format smoke qualification drift")
    return {"plan": plan, "path": path, "sha256": sha256_file(path)}


def load_multi_format_smoke_pair(
    repo_root: Path, plan_path: Path = DEFAULT_PAIR_PLAN
) -> dict[str, Any]:
    """Validate the frozen Mini-then-Pi pair and its resource gate."""
    path = resolve_repo_path(repo_root, plan_path)
    plan = load_json(path)
    if (
        plan.get("schema_version") != "1.0.0"
        or plan.get("status") != "frozen_before_execution"
        or plan.get("track") != "B"
        or plan.get("evidence_class") != "excluded_qualification_smoke_pair"
    ):
        raise RunnerError("Unexpected multi-format smoke-pair identity")
    order = plan.get("execution_order")
    if (
        not isinstance(order, list)
        or [item.get("position") for item in order] != [1, 2]
        or [item.get("harness_id") for item in order] != EXPECTED_HARNESSES
    ):
        raise RunnerError("Multi-format smokes must run Mini then Pi exactly once")
    smokes = {}
    for item in order:
        loaded = load_excluded_multi_format_smoke(
            repo_root, Path(item["smoke_plan_path"]), item["harness_id"]
        )
        if loaded["sha256"] != item.get("smoke_plan_sha256"):
            raise RunnerError(f"Smoke-pair plan hash drift for {item['harness_id']}")
        smokes[item["harness_id"]] = loaded
    identities = {
        (
            item["plan"]["deployment"]["name"],
            item["plan"]["deployment"]["digest"],
            item["plan"]["runtime"]["version"],
            item["plan"]["case"]["case_id"],
        )
        for item in smokes.values()
    }
    if len(identities) != 1:
        raise RunnerError("Paired multi-format smokes do not share deployment and case")
    comparison = plan.get("comparison_rules", {})
    if (
        comparison.get("one_attempt_per_complete_system") is not True
        or comparison.get("automatic_retries") != 0
        or comparison.get("measured_capability_evidence") is not False
        or comparison.get("one_factor_causal_harness_claim_allowed") is not False
    ):
        raise RunnerError("Multi-format pair exceeds qualification scope")
    gate = plan.get("resource_gate", {})
    if (
        gate.get("empty_state_observation_seconds") != 30
        or gate.get("loaded_models_must_be_empty_before_each_system") is not True
        or gate.get("manual_exclusive_window_confirmation_required") is not True
        or gate.get("model_unloaded_after_each_system") is not True
    ):
        raise RunnerError("Multi-format pair resource gate is incomplete")
    rules = gate.get("blocking_process_rules")
    if not isinstance(rules, list) or not rules:
        raise RunnerError("Multi-format pair needs explicit process rules")
    for rule in rules:
        try:
            re.compile(rule["pattern"])
        except (KeyError, TypeError, re.error) as exc:
            raise RunnerError("Invalid multi-format process rule") from exc
    _validate_artifacts(
        repo_root, plan.get("frozen_inputs", {}).get("artifacts"), "multi-format pair"
    )
    return {"plan": plan, "path": path, "sha256": sha256_file(path), "smokes": smokes}


def run_multi_format_preflight(
    repo_root: Path,
    plan_path: Path = DEFAULT_PAIR_PLAN,
    *,
    exclusive_window_confirmed: bool = False,
) -> dict[str, Any]:
    """Contact Ollama only after a fresh human exclusive-window confirmation."""
    loaded = load_multi_format_smoke_pair(repo_root, plan_path)
    if not exclusive_window_confirmed:
        raise RunnerError(
            "Multi-format smoke preflight requires a fresh exclusive-window confirmation"
        )
    plan = loaded["plan"]
    return run_resource_gate(
        plan, client=OllamaClient(plan["runtime"]["host"])
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--plan", type=Path, default=DEFAULT_PAIR_PLAN)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--plan", type=Path, default=DEFAULT_PAIR_PLAN)
    preflight.add_argument("--exclusive-window-confirmed", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path.cwd().resolve()
    try:
        if args.command == "validate":
            loaded = load_multi_format_smoke_pair(repo_root, args.plan)
            result = {
                "status": "valid",
                "plan_id": loaded["plan"]["plan_id"],
                "plan_sha256": loaded["sha256"],
                "live_ollama_requests": 0,
            }
        else:
            result = run_multi_format_preflight(
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
