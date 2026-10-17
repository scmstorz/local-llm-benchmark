"""Additive Ollama 0.40.2 execution identity for the frozen supplier smoke.

The v0.2 plan, controller, catalog and prepared study remain unchanged. This
adapter reuses the qualified state machine while admitting only the explicit
runtime amendment and fresh preparation. It never translates observed runtime
versions or relaxes the live identity gate.
"""

from __future__ import annotations

import copy
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from . import multi_format_transfer_smoke as base
from .runner import RunnerError, load_json, resolve_repo_path, sha256_file


ORIGINAL_PLAN = base.DEFAULT_PLAN
ORIGINAL_PLAN_SHA256 = "c2dd3235a8378a9f9dcced40dbb53e5d1f3a46f3a693d3dff24d5067b96d6302"
PLAN_ID = "multi-format-transfer-smoke-v0.3"
RUNTIME_VERSION = "0.40.2"
DEPLOYMENT_ID = "qwen3-8-27b-mlx-5642e97495e1-ollama-0-40-2"
DEFAULT_PLAN = Path("tasks/agentic/track-b/multi-format-transfer-smoke-v0.3.json")
DEFAULT_AUTHORIZATION = DEFAULT_PLAN.with_name(
    "multi-format-transfer-smoke-v0.3-execution-authorization.json"
)
DEFAULT_CONTROLLER_QUALIFICATION = DEFAULT_PLAN.with_name(
    "multi-format-transfer-smoke-v0.3-controller-qualification.json"
)
CATALOG = Path("models/catalog-transfer-smoke-ollama-0.40.2.json")
AMENDMENT_ARTIFACTS = (
    Path("local_llm_benchmark/multi_format_transfer_smoke_v03.py"),
    Path("tests/test_multi_format_transfer_smoke_v03.py"),
    CATALOG,
)
RUNTIME_AMENDMENT = {
    "reason": "The owner requires current Ollama updates; the original runtime is no longer installed.",
    "previous_plan_path": ORIGINAL_PLAN.as_posix(),
    "previous_plan_sha256": ORIGINAL_PLAN_SHA256,
    "previous_prepared_study_preserved": "multi-format-transfer-smoke-20260912T091336Z-2b4cdc1e",
    "new_runtime_is_separate_complete_system_condition": True,
    "fresh_preparation_required": True,
    "historical_attempts_reused": False,
    "new_model_or_harness_added": False,
    "broader_measured_sweep_authorized": False,
}
_original_plan_loader = base.load_transfer_smoke_plan


@dataclass(frozen=True)
class TransferSmokeConfig(base.TransferSmokeConfig):
    plan_path: Path = DEFAULT_PLAN


def amended_plan(repo_root: Path) -> dict[str, Any]:
    """Derive the only allowed v0.3 delta from the immutable v0.2 design."""
    original = _original_plan_loader(repo_root, ORIGINAL_PLAN)
    if original["sha256"] != ORIGINAL_PLAN_SHA256:
        raise RunnerError("Original transfer-smoke plan changed")
    plan = copy.deepcopy(original["plan"])
    plan["plan_id"] = PLAN_ID
    plan["frozen_on"] = "2026-10-17"
    plan["runtime"]["expected_version"] = RUNTIME_VERSION
    plan["deployment"]["deployment_id"] = DEPLOYMENT_ID
    plan["runtime_amendment"] = RUNTIME_AMENDMENT.copy()
    plan["reporting"].update(
        report_id=PLAN_ID,
        json_path=f"reports/agentic/{PLAN_ID}.json",
        markdown_path=f"reports/agentic/{PLAN_ID}.md",
    )
    plan["authorization"]["expected_future_path"] = DEFAULT_AUTHORIZATION.as_posix()
    plan["frozen_inputs"]["artifacts"].extend(
        {"path": path.as_posix(), "sha256": sha256_file(repo_root / path)}
        for path in AMENDMENT_ARTIFACTS
    )
    return plan


def load_transfer_smoke_plan(
    repo_root: Path, plan_path: Path = DEFAULT_PLAN
) -> dict[str, Any]:
    path = resolve_repo_path(repo_root, plan_path)
    plan = load_json(path)
    if plan != amended_plan(repo_root):
        raise RunnerError("Plan differs from the bounded Ollama 0.40.2 amendment")
    base._validate_artifacts(repo_root, plan["frozen_inputs"]["artifacts"], PLAN_ID)
    catalog = load_json(repo_root / CATALOG)
    entries = catalog.get("deployments", [])
    if len(entries) != 1:
        raise RunnerError("Runtime amendment requires exactly one registered deployment")
    deployment = entries[0]
    if (
        deployment.get("deployment_id") != DEPLOYMENT_ID
        or deployment.get("requested_name") != base.MODEL
        or deployment.get("digest") != plan["deployment"]["digest"]
        or deployment.get("size_bytes") != plan["deployment"]["size_bytes"]
        or deployment.get("runtime") != {"name": "ollama", "version": RUNTIME_VERSION}
    ):
        raise RunnerError("Current-runtime deployment registration differs")
    return {
        "plan": plan,
        "path": path,
        "sha256": sha256_file(path),
        "systems": {item["system_id"]: item for item in plan["systems"]},
        "resource_gate": {
            "empty_state_observation_seconds": 30,
            "loaded_models_must_be_empty_before_each_system": True,
            "blocking_process_rules": plan["resource_gate"]["blocking_process_rules"],
        },
    }


def load_controller_qualification(repo_root: Path) -> dict[str, Any]:
    path = resolve_repo_path(repo_root, DEFAULT_CONTROLLER_QUALIFICATION)
    qualification = load_json(path)
    evidence = qualification.get("qualification_evidence", {})
    if (
        qualification.get("qualification_id") != f"{PLAN_ID}-controller-no-inference"
        or qualification.get("status") != "qualified_for_frozen_smoke"
        or qualification.get("runtime_version") != RUNTIME_VERSION
        or evidence.get("live_ollama_requests") != 0
        or evidence.get("live_model_inference") is not False
        or evidence.get("focused_python_tests_passed", 0) < 9
    ):
        raise RunnerError("Invalid current-runtime controller qualification")
    base._validate_artifacts(repo_root, qualification.get("artifacts"), PLAN_ID)
    return {"qualification": qualification, "path": path, "sha256": sha256_file(path)}


def load_execution_authorization(
    repo_root: Path, authorization_path: Path, loaded_plan: dict[str, Any]
) -> dict[str, Any]:
    path = resolve_repo_path(repo_root, authorization_path)
    authorization = load_json(path)
    required = {
        "schema_version": "1.0.0",
        "authorization_id": f"{PLAN_ID}-execution-authorization",
        "status": "authorized_pending_resource_gate",
        "plan_id": PLAN_ID,
        "plan_sha256": loaded_plan["sha256"],
        "live_execution_authorized": True,
        "unit_count": 2,
        "attempts_per_system": 1,
        "automatic_retries": 0,
        "authorized_model": base.MODEL,
        "authorized_systems": list(base.SYSTEM_IDS),
        "resource_gate_still_required": True,
        "authorized_runtime_version": RUNTIME_VERSION,
    }
    if any(authorization.get(key) != value for key, value in required.items()):
        raise RunnerError("Invalid current-runtime execution authorization")
    return {"authorization": authorization, "path": path, "sha256": sha256_file(path)}


@contextmanager
def _configured_base() -> Iterator[None]:
    """Reuse the frozen state machine with explicit additive identity loaders."""
    replacements = {
        "DEFAULT_PLAN": DEFAULT_PLAN,
        "DEFAULT_AUTHORIZATION": DEFAULT_AUTHORIZATION,
        "DEFAULT_CONTROLLER_QUALIFICATION": DEFAULT_CONTROLLER_QUALIFICATION,
        "TransferSmokeConfig": TransferSmokeConfig,
        "load_transfer_smoke_plan": load_transfer_smoke_plan,
        "load_controller_qualification": load_controller_qualification,
        "load_execution_authorization": load_execution_authorization,
        "__file__": __file__,
    }
    previous = {name: getattr(base, name) for name in replacements}
    try:
        for name, value in replacements.items():
            setattr(base, name, value)
        yield
    finally:
        for name, value in previous.items():
            setattr(base, name, value)


def start_transfer_smoke(repo_root: Path, config: TransferSmokeConfig) -> dict[str, Any]:
    with _configured_base():
        return base.start_transfer_smoke(repo_root, config)


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    with _configured_base():
        if arguments and arguments[0] == "report":
            from .multi_format_transfer_smoke_report import main as report_main

            return report_main(arguments[1:])
        return base.main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
