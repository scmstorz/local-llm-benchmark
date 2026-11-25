"""Validate two separate practical text assessments offline.

No inference, network calls, edits or file writes. A validated structure is not
proof that a semantic judgment or a proposed repair is correct.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .json_schema import validate_json
from .practical_calibration import ROOT, judgment, materials

SCHEMA = ROOT / "tasks/calibration/practical-text-review-v0.2/review.schema.json"
READING_DIMENSIONS = ("organization", "comprehensibility", "fluency", "grammar")


def check_review(value: dict, answer: str, data: dict,
                 frozen_judgment: bytes | None = None) -> dict:
    """Check bindings, preservation and repair-plan consistency; do not rescore."""
    validate_json(value, json.loads(SCHEMA.read_text(encoding="utf-8")))
    original = value["as_delivered"]
    delivered = judgment(original, answer, data)
    for key in ("case_id", "candidate_id", "answer_sha256"):
        if value[key] != original[key]:
            raise ValueError("Review and delivered judgment binding differ: " + key)

    if value["as_delivered_origin"] == "frozen_v1":
        if frozen_judgment is None:
            raise ValueError("Frozen v1 judgment bytes are required")
        if (hashlib.sha256(frozen_judgment).hexdigest() != value["v1_judgment_sha256"]
                or json.dumps(json.loads(frozen_judgment), sort_keys=True)
                != json.dumps(original, sort_keys=True)):
            raise ValueError("Frozen v1 judgment changed")
    elif value["v1_judgment_sha256"] is not None or frozen_judgment is not None:
        raise ValueError("A new review must not claim frozen v1 provenance")

    for rating in value["reading_profile"].values():
        if rating is not None and any(q not in answer for q in rating["evidence_quotes"]):
            raise ValueError("Reading-profile quote absent from answer")

    editing = value["editing_base"]
    if editing["status"] == "not_assessed":
        if (editing["verdict"] is not None or editing["rationale"] is not None
                or editing["required_repairs"] or editing["remaining_uncertainties"]):
            raise ValueError("Unassessed editing suitability must remain unknown")
    elif editing["verdict"] is None or editing["rationale"] is None:
        raise ValueError("Assessed editing suitability needs a verdict and rationale")

    fact_ids = {f["id"] for f in data["reference"]["facts"]}
    repaired_facts = set()
    for repair in editing["required_repairs"]:
        quote = repair["answer_quote"]
        if quote is not None and quote not in answer:
            raise ValueError("Repair quote absent from answer")
        if not (quote or repair["fact_ids"]):
            raise ValueError("Repair needs an answer passage or reference fact")
        if set(repair["fact_ids"]) - fact_ids:
            raise ValueError("Repair cites an unknown reference fact")
        if repair["kind"] in {"factual_correction", "source_verification"}:
            repaired_facts.update(repair["fact_ids"])

    critical = {f["fact_id"] for f in original["critical_findings"]}
    if critical and editing["verdict"] in {"good", "conditional"}:
        if editing["verdict"] != "conditional" or critical - repaired_facts:
            raise ValueError("Known critical facts need an explicit conditional repair plan")
    if editing["verdict"] == "conditional" and not editing["required_repairs"]:
        raise ValueError("A conditional editing verdict needs concrete repairs")

    return {"case_id": value["case_id"], "candidate_id": value["candidate_id"],
            "as_delivered": delivered, "reading_profile": value["reading_profile"],
            "editing_base": editing, "combined_score": None,
            "semantic_correctness_proven": False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--answer", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--v1-judgment", type=Path)
    args = parser.parse_args(argv)
    result = check_review(
        json.loads(args.review.read_text(encoding="utf-8")),
        args.answer.read_text(encoding="utf-8"), materials(ROOT, args.case),
        args.v1_judgment.read_bytes() if args.v1_judgment else None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
