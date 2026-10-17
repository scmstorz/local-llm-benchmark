"""Coverage 0.2: distinguish missing native identity from conflicting identity.

Some frozen Pi adapters record deployment identity in their controller's fresh
resource gate, not in run.json. This additive reader can validate that separate
evidence without writing to a run or changing historical verifier outcomes.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from . import core_suite as original
from .runner import RunnerError, load_json, sha256_file


VERSION = "0.2.0"


def _time(value: str) -> datetime:
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise RunnerError("Invalid admission timestamp") from exc
    if stamp.tzinfo is None:
        raise RunnerError("Admission timestamps must include a timezone")
    return stamp


def coverage(root: Path, plan_path: Path, admission_study: Path | None = None) -> dict[str, Any]:
    plan_path = original._source(root, str(plan_path))
    plan = load_json(plan_path)
    result = original.coverage(root, plan)
    result["coverage_version"] = VERSION
    loaded = original.load_catalog(root, Path(plan["suite_path"]), Path(plan["systems_path"]))
    deployments = {item["deployment_id"]: item for item in plan["deployments"]}
    study = None
    if admission_study:
        path = original._source(root, str(admission_study))
        study = load_json(path)
        if study.get("plan_sha256") != sha256_file(plan_path):
            raise RunnerError("Admission study belongs to another plan")
        result["admission_source"] = {"path": str(admission_study), "sha256": sha256_file(path)}
    for row in result["cells"]:
        if row["status"] != "identity_mismatch" or not row.get("evidence"):
            continue
        path = original._source(root, row["evidence"]["path"])
        record = load_json(path)
        deployment = record.get("deployment") or {}
        # Native contradictory observations always win over external metadata.
        if deployment.get("model") or deployment.get("ollama_version") is not None:
            continue
        system = loaded["registry"]["systems"][row["system"]]
        expected = deployments[row["deployment_id"]]
        if record.get("state") != "complete" or not system.get("expected_harness_id"):
            continue
        identity = record.get("case") or {}
        if (record.get("harness", {}).get("harness_id") != system["expected_harness_id"]
                or deployment.get("requested_model") != expected["resolved_name"]
                or identity.get("case_id") != row["case_id"]
                or identity.get("case_path") != row["case_path"]
                or record.get("prepared_at", "") < plan["created_at"]):
            continue
        if system.get("evaluation_configuration_id"):
            if (record.get("evaluation_configuration", {}).get("configuration_id") != system["evaluation_configuration_id"]
                    or record.get("verification", {}).get("verifier_version") != "2.1.0"
                    or record.get("normalized_metrics", {}).get("version") != "0.2.0"):
                continue
        # Absence alone does not establish the wrong model/runtime.
        row.update(status="identity_unrecorded", identity_basis="native_run_record_has_no_deployment_observation")
        if not study:
            continue
        run_dir = str(path.parent.relative_to(root))
        units = [unit for unit in study.get("units", []) if unit.get("run_dir") == run_dir]
        if len(units) != 1:
            row["identity_evidence_error"] = "missing_or_ambiguous_admission_unit"
            continue
        unit = units[0]
        gate = unit.get("resource_evidence") or {}
        if (unit.get("status") != "complete" or unit.get("run_sha256") != sha256_file(path)
                or gate.get("passed") is not True or gate.get("inference_requests_made") != 0
                or gate.get("model") != expected["resolved_name"] or gate.get("digest") != expected["digest"]
                or gate.get("ollama_version") != expected["runtime"]["version"]
                or result["source_drift"]):
            row["identity_evidence_error"] = "admission_identity_hash_or_source_mismatch"
            continue
        completed = _time(gate.get("completed_at"))
        started = _time(record.get("execution", {}).get("started_at"))
        if not (_time(plan["created_at"]) <= _time(gate.get("observed_at")) <= completed <= started):
            row["identity_evidence_error"] = "admission_is_not_a_pre_inference_observation"
            continue
        row.update(status="complete", identity_basis="verified_pre_inference_resource_gate",
                   verified_deployment={"model": gate["model"], "digest": gate["digest"],
                                        "ollama_version": gate["ollama_version"],
                                        "source": result["admission_source"]})
    result["counts"] = dict(Counter(row["status"] for row in result["cells"]))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--admission-study", type=Path)
    args = parser.parse_args(argv)
    try:
        result = coverage(Path.cwd().resolve(), args.plan, args.admission_study)
    except RunnerError as exc:
        parser.exit(1, str(exc) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
