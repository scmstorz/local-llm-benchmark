"""Sanitized reports for completed Pi capability sweeps."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .runner import RunnerError, load_json, resolve_repo_path, sha256_file, utc_now


@dataclass(frozen=True)
class PiSweepReportConfig:
    """Inputs for one tracked, public-safe Pi sweep report."""

    sweep_dir: Path
    json_output: Path
    markdown_output: Path


def _json_lines(path: Path) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            values.append(value)
    return values


def _provider_error_type(events: list[dict[str, Any]]) -> str | None:
    error_message = None
    for event in events:
        message = event.get("message")
        if (
            event.get("type") == "message_end"
            and isinstance(message, dict)
            and message.get("role") == "assistant"
            and isinstance(message.get("errorMessage"), str)
        ):
            error_message = message["errorMessage"].casefold()
    if error_message is None:
        return None
    if "request timed out" in error_message:
        return "provider_request_timeout"
    if "stream ended without finish_reason" in error_message:
        return "provider_stream_incomplete"
    if "operation was aborted" in error_message:
        return "provider_operation_aborted"
    return "provider_error"


def _check_count(test: dict[str, Any], expected_total: int) -> int:
    stdout = test.get("stdout")
    if isinstance(stdout, str):
        explicit = re.search(
            r"(\d+)/(\d+) (?:public|hidden) checks passed", stdout
        )
        if explicit:
            return int(explicit.group(1))
        tap = re.search(r"^# pass (\d+)$", stdout, flags=re.MULTILINE)
        if tap:
            return int(tap.group(1))
    return expected_total if test.get("passed") else 0


def diagnose_pi_outcome(
    *,
    raw_outcome: dict[str, Any],
    trajectory: dict[str, Any],
    verification: dict[str, Any],
    audit_events: list[dict[str, Any]],
    provider_error: str | None,
    active_wall_limit: int,
) -> dict[str, Any]:
    """Derive a more specific label without mutating the frozen raw outcome."""
    kinds = [event.get("kind") for event in audit_events]
    if raw_outcome.get("verified_success"):
        return {
            "category": "verified_success",
            "type": "verified_success",
            "evidence_status": "conclusive_success",
        }
    if "output_token_budget_exceeded" in kinds:
        return {
            "category": "agent_budget_failure",
            "type": "maximum_total_output_tokens_exceeded",
            "evidence_status": "conclusive_bounded_failure",
        }
    if "agent_budget_exceeded" in kinds:
        active_seconds = trajectory.get("active_wall_time_seconds")
        if isinstance(active_seconds, (int, float)) and active_seconds < active_wall_limit:
            return {
                "category": "timing_confound",
                "type": "policy_wall_clock_included_standby",
                "evidence_status": "inconclusive_negative",
            }
        return {
            "category": "agent_budget_failure",
            "type": "maximum_wall_time_exceeded",
            "evidence_status": "conclusive_bounded_failure",
        }
    if trajectory.get("termination_reason") == "maximum_wall_time_exceeded":
        return {
            "category": "agent_budget_failure",
            "type": "maximum_wall_time_exceeded",
            "evidence_status": "conclusive_bounded_failure",
        }
    if provider_error:
        return {
            "category": "provider_or_transport_failure",
            "type": provider_error,
            "evidence_status": "inconclusive_negative",
        }
    if raw_outcome.get("agent_termination_valid") and not verification.get(
        "verified_success"
    ):
        return {
            "category": "task_or_verification_failure",
            "type": verification.get("failure_code") or "verification_failed",
            "evidence_status": "conclusive_task_failure",
        }
    return {
        "category": raw_outcome.get("failure_category") or "unclassified_failure",
        "type": raw_outcome.get("failure_type") or "unclassified_failure",
        "evidence_status": "inconclusive_negative",
    }


def _observation(
    repo_root: Path,
    unit: dict[str, Any],
    *,
    active_wall_limit: int,
) -> dict[str, Any]:
    run_dir = resolve_repo_path(repo_root, Path(unit["run_dir"]))
    record_path = run_dir / "run.json"
    verification_path = run_dir / "final-verification.json"
    record = load_json(record_path)
    verification = load_json(verification_path)
    if record.get("run_id") != unit.get("run_id") or record.get("state") != "complete":
        raise RunnerError("Pi report source unit is not a complete matching run")
    expected_verification_hash = record.get("artifacts", {}).get(
        "final_verification_sha256"
    )
    if expected_verification_hash != sha256_file(verification_path):
        raise RunnerError("Pi final-verification hash mismatch")
    execution_hashes = record.get("artifacts", {}).get("execution_sha256", {})
    execution_paths = {
        "events": run_dir / "pi-events.jsonl",
        "stderr": run_dir / "pi-stderr.txt",
        "policy_audit": run_dir / "pi-policy-audit.jsonl",
    }
    for key, path in execution_paths.items():
        if execution_hashes.get(key) != sha256_file(path):
            raise RunnerError(f"Pi {key} hash mismatch")
    events = _json_lines(execution_paths["events"])
    audit_events = _json_lines(execution_paths["policy_audit"])
    raw_outcome = record["outcome"]
    trajectory = record["trajectory"]
    diagnosis = diagnose_pi_outcome(
        raw_outcome=raw_outcome,
        trajectory=trajectory,
        verification=verification,
        audit_events=audit_events,
        provider_error=_provider_error_type(events),
        active_wall_limit=active_wall_limit,
    )
    tests = verification.get("tests") or {}
    public = tests.get("public") or {}
    hidden = tests.get("hidden") or {}
    return {
        "position": unit["position"],
        "model": unit["model"],
        "deployment_id": unit["deployment_id"],
        "digest": unit["digest"],
        "case_id": unit["case_id"],
        "run_id": unit["run_id"],
        "run_record_sha256": sha256_file(record_path),
        "final_verification_sha256": sha256_file(verification_path),
        "raw_outcome": {
            key: raw_outcome.get(key)
            for key in (
                "runtime_success",
                "agent_termination_valid",
                "verifier_success",
                "verified_success",
                "failure_category",
                "failure_type",
            )
        },
        "diagnostic_interpretation": diagnosis,
        "verification": {
            "integrity_passed": (verification.get("integrity") or {}).get("passed"),
            "changed_paths": (verification.get("integrity") or {}).get(
                "changed_paths", []
            ),
            "public_checks_passed": _check_count(public, 4),
            "public_checks_total": 4,
            "hidden_checks_passed": _check_count(hidden, 8),
            "hidden_checks_total": 8,
        },
        "trajectory": {
            key: trajectory.get(key)
            for key in (
                "active_wall_time_seconds",
                "agent_turns",
                "tool_calls",
                "failed_tool_calls",
                "file_reads",
                "file_writes",
                "public_test_runs",
                "input_tokens",
                "output_tokens",
                "time_to_first_successful_public_verification_seconds",
                "termination_reason",
            )
        },
    }


def build_pi_sweep_report(repo_root: Path, sweep_dir: Path) -> dict[str, Any]:
    """Build one public-safe report while revalidating ignored raw artifacts."""
    resolved_sweep = resolve_repo_path(repo_root, sweep_dir)
    sweep_path = resolved_sweep / "sweep.json"
    sweep = load_json(sweep_path)
    if sweep.get("status") != "complete":
        raise RunnerError("Primary Pi capability report requires a complete sweep")
    plan_path = resolve_repo_path(repo_root, Path(sweep["plan"]["path"]))
    if sweep["plan"]["sha256"] != sha256_file(plan_path):
        raise RunnerError("Pi sweep plan changed before reporting")
    plan = load_json(plan_path)
    active_wall_limit = int(
        plan["shared_inference"]["maximum_active_wall_time_seconds"]
    )
    observations = [
        _observation(repo_root, unit, active_wall_limit=active_wall_limit)
        for unit in sweep["units"]
    ]
    case_summary: list[dict[str, Any]] = []
    for case in plan["cases"]:
        selected = [
            item for item in observations if item["case_id"] == case["case_id"]
        ]
        case_summary.append(
            {
                **case,
                "attempts": len(selected),
                "verified_successes": sum(
                    bool(item["raw_outcome"]["verified_success"])
                    for item in selected
                ),
                "conclusive_bounded_or_task_failures": sum(
                    item["diagnostic_interpretation"]["evidence_status"]
                    in {"conclusive_bounded_failure", "conclusive_task_failure"}
                    for item in selected
                ),
                "inconclusive_negatives": sum(
                    item["diagnostic_interpretation"]["evidence_status"]
                    == "inconclusive_negative"
                    for item in selected
                ),
            }
        )
    model_summary: list[dict[str, Any]] = []
    for deployment in plan["deployments"]:
        selected = [
            item for item in observations if item["model"] == deployment["name"]
        ]
        model_summary.append(
            {
                "model": deployment["name"],
                "deployment_id": deployment["deployment_id"],
                "verified_successes": sum(
                    bool(item["raw_outcome"]["verified_success"])
                    for item in selected
                ),
                "attempts": len(selected),
                "inconclusive_negatives": sum(
                    item["diagnostic_interpretation"]["evidence_status"]
                    == "inconclusive_negative"
                    for item in selected
                ),
            }
        )
    evidence_counts: dict[str, int] = {}
    for item in observations:
        status = item["diagnostic_interpretation"]["evidence_status"]
        evidence_counts[status] = evidence_counts.get(status, 0) + 1
    return {
        "schema_version": "1.0.0",
        "report_id": "track-b-pi-capability-sweep-v0.2",
        "report_type": "measured_capability_sweep_with_diagnostic_corrections",
        "generated_at": utc_now(),
        "track": "B",
        "study_mode": "capability_sweep",
        "evidence_class": "measured_n1_with_partial_infrastructure_confounds",
        "source": {
            "sweep_id": sweep["sweep_id"],
            "sweep_sha256": sha256_file(sweep_path),
            "plan_path": sweep["plan"]["path"],
            "plan_sha256": sweep["plan"]["sha256"],
            "implementation_git_commit": plan["frozen_inputs"][
                "implementation_git_commit"
            ],
        },
        "configuration": {
            "ollama_version": sweep["ollama_version"],
            "harness_id": plan["harness_id"],
            "pi_package": "@earendil-works/pi-coding-agent@0.84.4",
            "deployment_count": len(plan["deployments"]),
            "case_count": len(plan["cases"]),
            "attempts": len(observations),
            "runs_per_configuration": 1,
            "automatic_retries": 0,
            "maximum_active_wall_time_seconds": active_wall_limit,
            "maximum_total_output_tokens": plan["shared_inference"][
                "maximum_total_output_tokens"
            ],
            "normal_agent_turn_limit": None,
        },
        "summary": {
            "verified_successes": sum(
                bool(item["raw_outcome"]["verified_success"])
                for item in observations
            ),
            "attempts": len(observations),
            "evidence_status_counts": evidence_counts,
            "case_summary": case_summary,
            "model_summary": model_summary,
        },
        "method_deviations_discovered_after_execution": [
            {
                "id": "pi_provider_timeout_not_explicitly_applied",
                "impact": "The frozen 300-second request timeout was present in run metadata but absent from Pi's retry.provider.timeoutMs setting. Provider timeout outcomes are inconclusive negatives.",
            },
            {
                "id": "policy_wall_clock_counted_standby",
                "impact": "The Pi extension used wall-clock time while the parent used monotonic active time. Qwen 3.6 JavaScript was aborted after standby despite only 31.90 active seconds and is an inconclusive negative.",
            },
            {
                "id": "coarse_raw_invalid_agent_end_taxonomy",
                "impact": "The raw v0.2 outcome collapsed provider errors and budget aborts into invalid_agent_end. This report derives a non-destructive diagnostic taxonomy from immutable event and audit artifacts.",
            },
        ],
        "observations": observations,
        "findings": [
            "Six of sixteen model-task systems reached valid agent termination and passed all twelve deterministic checks; all six were PHP runs.",
            "PHP produced six verified successes, one conclusive active-time budget failure with verifier-complete code, and one inconclusive provider-timeout outcome.",
            "JavaScript produced no verified success in this sweep. One run was a conclusive hidden-test failure, four were conclusive budget failures, and three were inconclusive transport or standby outcomes.",
            "A verified success is strong positive evidence for that exact configuration. An inconclusive negative is not evidence that the model lacks the underlying coding capability.",
            "Trajectory cost varied sharply even among PHP successes, supporting separate reporting of outcome, time, turns and tool effort rather than a single score.",
        ],
        "claims_not_supported": [
            "No reliability probability or tail-latency claim is supported because every model-task configuration has n=1.",
            "The report does not rank model quality from inconclusive transport outcomes.",
            "The report does not treat the six PHP successes as evidence that Pi v0.2 is equally compatible with every task or model.",
            "The report does not merge the interrupted Ollama 0.32.15 sweep with this Ollama 0.33.2 cohort.",
        ],
        "next_step": {
            "harness_candidate": "pi-v0.3",
            "action": "Integrate the implemented v0.3 configuration and policy into a new live adapter, then qualify explicit provider timeout, monotonic parent time and measurement-only trajectory tokens before preregistering any rerun. Preserve this v0.2 sweep unchanged.",
        },
    }


def render_pi_sweep_markdown(report: dict[str, Any]) -> str:
    """Render the human-readable companion to the structured report."""
    configuration = report["configuration"]
    summary = report["summary"]
    lines = [
        "# Coding Track B Pi capability sweep v0.2",
        "",
        "The frozen eight-model by two-case Pi sweep completed all 16 planned",
        "configurations under Ollama 0.33.2. Six systems reached a valid agent end",
        "and passed all 12 deterministic checks. The remaining ten outcomes must",
        "not be collapsed into ten model-capability failures: four are inconclusive",
        "transport or standby observations, while six are bounded or verified task",
        "failures.",
        "",
        "## Frozen scope",
        "",
        "| Dimension | Value |",
        "| --- | --- |",
        f"| Harness | `{configuration['harness_id']}` with `{configuration['pi_package']}` |",
        f"| Runtime | Ollama {configuration['ollama_version']} |",
        f"| Deployments × cases | {configuration['deployment_count']} × {configuration['case_count']} = {configuration['attempts']} |",
        "| Attempts | one per configuration; no retry |",
        f"| Active wall-time ceiling | {configuration['maximum_active_wall_time_seconds']} s |",
        f"| Total output ceiling | {configuration['maximum_total_output_tokens']:,} tokens |",
        "| Normal turn ceiling | none; turns are measured |",
        "",
        "## Outcome matrix",
        "",
        "| # | Model | Case | Verified | Diagnostic outcome | Checks | Active time | Turns / tools |",
        "| ---: | --- | --- | :---: | --- | ---: | ---: | ---: |",
    ]
    labels = {
        "verified_success": "verified success",
        "maximum_wall_time_exceeded": "active-time budget",
        "maximum_total_output_tokens_exceeded": "output-token budget",
        "hidden_tests_failed": "hidden-test failure",
        "provider_request_timeout": "provider request timeout (inconclusive)",
        "provider_stream_incomplete": "provider stream incomplete (inconclusive)",
        "provider_operation_aborted": "provider operation aborted (inconclusive)",
        "policy_wall_clock_included_standby": "standby timing confound (inconclusive)",
    }
    for item in report["observations"]:
        verify = item["verification"]
        trajectory = item["trajectory"]
        outcome_type = item["diagnostic_interpretation"]["type"]
        case_label = "PHP" if "php-" in item["case_id"] else "JavaScript"
        cells = [
            str(item["position"]),
            f"`{item['model']}`",
            case_label,
            "yes" if item["raw_outcome"]["verified_success"] else "no",
            labels.get(outcome_type, outcome_type),
            f"{verify['public_checks_passed']}/4 + {verify['hidden_checks_passed']}/8",
            f"{trajectory['active_wall_time_seconds']:.2f} s",
            f"{trajectory['agent_turns']} / {trajectory['tool_calls']}",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.extend(
        [
            "",
            "## What is conclusive",
            "",
            f"The primary frozen outcome is **{summary['verified_successes']}/{summary['attempts']} verified successes**.",
            "Each success is strong positive evidence for that exact model, runtime,",
            "task and Pi configuration. PHP accounted for all six successes. GPT-OSS",
            "also left PHP code that passed 12/12 checks, but it never terminated within",
            "the 900-second budget; it is a bounded overall failure, not a success.",
            "",
            "The JavaScript case produced one clean task-level near miss: Gemma ended",
            "normally, passed all public checks and 7/8 hidden checks. Nemotron, Granite",
            "and Ornith exhausted the output budget. Glimmer exhausted active wall time.",
            "Those five are valid bounded negative outcomes for the tested system.",
            "",
            "## What is inconclusive",
            "",
            "Glimmer/PHP and Qwen 3.8/JavaScript encountered provider request timeouts;",
            "GPT-OSS/JavaScript ended with an incomplete provider stream. The adapter",
            "recorded a 300-second request timeout but did not explicitly pass it into",
            "Pi's provider settings, so these outcomes cannot support a capability claim.",
            "",
            "Qwen 3.6/JavaScript was aborted by the extension's wall-clock check after",
            "notebook standby, although the parent measured only 31.90 active seconds.",
            "That result is also inconclusive. Raw files remain immutable; this report",
            "adds a derived diagnostic taxonomy rather than rewriting history.",
            "",
            "## Why this is Track B",
            "",
            "The experimental unit is the deployed system, not the model alone:",
            "`task × model × Ollama × pinned Pi × tools × budgets × verifier × run`.",
            "Tool behavior, agent termination and transport compatibility therefore count",
            "alongside final-code verification. Track A results remain separate.",
            "",
            "## Interpretation limits",
            "",
            "Every configuration has `n=1`. Times, turns and tool counts are descriptive",
            "trajectory observations, not performance distributions or reliability",
            "estimates. No P90/P95 claim and no universal ranking is justified. The earlier",
            "interrupted Ollama 0.32.15 sweep is retained separately and is not pooled.",
            "",
            "## Next correction",
            "",
            "Candidate `pi-v0.3` requires an explicit 300-second provider timeout and makes",
            "the parent's monotonic timer the sole 900-second authority. It also records",
            "trajectory tokens and turns without using either as a normal abort condition.",
            "Its separate configuration builder and policy extension are implemented without",
            "modifying the frozen v0.2 adapter. The live adapter must still pass no-inference,",
            "Seatbelt and transport qualification and be frozen as a new experimental",
            "configuration before any rerun. The v0.2 observations will not be repaired or",
            "silently repeated.",
            "",
        ]
    )
    return "\n".join(lines)


def write_pi_sweep_report(repo_root: Path, config: PiSweepReportConfig) -> dict[str, Any]:
    """Write JSON and Markdown reports and reject accidental private paths."""
    report = build_pi_sweep_report(repo_root, config.sweep_dir)
    json_output = resolve_repo_path(repo_root, config.json_output)
    markdown_output = resolve_repo_path(repo_root, config.markdown_output)
    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    markdown = render_pi_sweep_markdown(report)
    for content in (serialized, markdown):
        if "/Users/" in content or "results/agentic-runs/" in content:
            raise RunnerError("Sanitized Pi report contains a private raw path")
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(serialized, encoding="utf-8")
    markdown_output.write_text(markdown, encoding="utf-8")
    return {
        "status": "complete",
        "report_id": report["report_id"],
        "json_output": str(json_output),
        "markdown_output": str(markdown_output),
        "verified_successes": report["summary"]["verified_successes"],
        "attempts": report["summary"]["attempts"],
    }


def main(argv: list[str] | None = None) -> int:
    """Build a report without modifying the CLI frozen by the measured sweep."""
    parser = argparse.ArgumentParser(
        description="Build a sanitized report from a completed Pi sweep"
    )
    parser.add_argument("--sweep-dir", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = write_pi_sweep_report(
            Path.cwd().resolve(),
            PiSweepReportConfig(
                sweep_dir=args.sweep_dir,
                json_output=args.json_output,
                markdown_output=args.markdown_output,
            ),
        )
    except (OSError, RunnerError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
