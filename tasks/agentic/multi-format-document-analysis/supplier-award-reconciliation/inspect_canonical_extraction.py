#!/usr/bin/env python3
"""Validate the supplier canonical extraction against all frozen binaries."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from build_canonical_extraction import build_extraction, load_json, sha256_file
from local_llm_benchmark.json_schema import validate_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--extraction", required=True, type=Path)
    parser.add_argument("--schema", required=True, type=Path)
    return parser.parse_args()


def field_map(record: dict[str, object]) -> dict[str, dict[str, object]]:
    return {item["name"]: item for item in record["fields"]}


def main() -> None:
    args = parse_args()
    extraction = load_json(args.extraction)
    schema = load_json(args.schema)
    validate_json(extraction, schema)
    rebuilt = build_extraction(args.repo_root)
    if extraction != rebuilt:
        raise AssertionError("Frozen extraction differs from a fresh binary extraction")
    records = {item["fact_code"]: item for item in extraction["evidence_records"]}
    if len(records) != 16:
        raise AssertionError("Canonical extraction must contain 16 unique facts")

    gates = records["POL-ELIGIBILITY"]["text"]
    for fragment in (
        "Signed-final rating is A or B.",
        "Unresolved critical finding count equals 0.",
        "Available / required capacity - 1 is at least 15%.",
        "Adjusted first-year cost is at most EUR 1,200,000.",
    ):
        if fragment not in gates:
            raise AssertionError(f"Missing policy extraction: {fragment}")
    if "First exclude every ineligible supplier" not in records["POL-SELECTION"]["text"] or "next-lowest eligible supplier as reserve" not in records["POL-SELECTION"]["text"]:
        raise AssertionError("Filter-then-rank selection sequence was not extracted")
    if "supersedes drafts" not in records["POL-AUTHORITY"]["text"] or "cannot waive" not in records["POL-AUTHORITY"]["text"]:
        raise AssertionError("Evidence authority was not extracted")
    if "2026-09-08 16:00 UTC" not in records["POL-CUTOFF"]["text"]:
        raise AssertionError("Policy cutoff was not extracted")

    draft = field_map(records["ASSUR-DRAFT"])
    if draft["Atlas"]["value"] != "Atlas | C | 0 | Unsigned draft" or draft["Cedar"]["value"] != "Cedar | A | 0 | Unsigned draft":
        raise AssertionError("Unsigned-draft values are wrong")
    final_note = field_map(records["ASSUR-FINAL"])
    if final_note["supersedes_page"]["value"] != 2 or final_note["finalized_at"]["value"] != "2026-09-08 14:30 UTC" or final_note["decision_cutoff"]["value"] != "2026-09-08 16:00 UTC":
        raise AssertionError("Signed-final authority or cutoff is wrong")
    expected_assurance = {
        "ASSUR-ATLAS": ("B", 0), "ASSUR-BOREAL": ("A", 0),
        "ASSUR-CEDAR": ("A", 1), "ASSUR-DELTA": ("B", 0),
    }
    for fact_code, expected in expected_assurance.items():
        fields = field_map(records[fact_code])
        observed = (fields["assurance_rating"]["value"], fields["unresolved_critical_findings"]["value"])
        if observed != expected or fields["evidence_status"]["value"] != "Signed final":
            raise AssertionError(f"{fact_code}: signed-final extraction mismatch")

    expected_bids = {
        "BID-ATLAS": (1080000, 120000, 60000, 1140000, 116, 100, 0.16, "PASS", "PASS", 5),
        "BID-BOREAL": (1120000, 80000, 35000, 1165000, 125, 100, 0.25, "PASS", "PASS", 6),
        "BID-CEDAR": (1030000, 90000, 40000, 1080000, 120, 100, 0.2, "PASS", "PASS", 7),
        "BID-DELTA": (1020000, 120000, 10000, 1130000, 112, 100, 0.12, "PASS", "HOLD", 8),
    }
    for fact_code, expected in expected_bids.items():
        fields = field_map(records[fact_code])
        observed = tuple(fields[name]["value"] for name in (
            "base_annual_fee_eur", "mobilization_eur", "transition_credit_eur",
            "adjusted_first_year_cost_eur", "available_units", "required_units",
            "capacity_headroom", "cost_gate", "capacity_gate",
        ))
        if observed != expected[:9]:
            raise AssertionError(f"{fact_code}: commercial extraction mismatch")
        row = expected[9]
        expected_formulas = {
            "adjusted_first_year_cost_eur": f"=B{row}+C{row}-D{row}",
            "capacity_headroom": f"=IFERROR(F{row}/G{row}-1,0)",
            "cost_gate": f'=IF(E{row}<=$M$3,"PASS","HOLD")',
            "capacity_gate": f'=IF(H{row}>=$M$4,"PASS","HOLD")',
        }
        for name, formula in expected_formulas.items():
            if fields[name]["formula"] != formula:
                raise AssertionError(f"{fact_code}: wrong {name} formula")

    recommendation = field_map(records["DASH-RECOMMENDATION"])
    if recommendation["recommended_supplier"]["value"] != "Cedar" or recommendation["lowest_adjusted_first_year_cost_eur"]["value"] != 1080000 or recommendation["recommendation_basis"]["value"] != "Lowest adjusted first-year cost":
        raise AssertionError("Commercial dashboard recommendation mismatch")
    scope = field_map(records["DASH-SCOPE"])
    if scope["ranking_scope"]["value"] != "Commercial ranking only" or scope["assurance_scope"]["value"] != "Assurance findings are not incorporated":
        raise AssertionError("Commercial dashboard scope mismatch")

    serialized = json.dumps(extraction, sort_keys=True)
    prohibited_answer_fragments = (
        '"primary_supplier"', '"reserve_supplier"', '"rejected_suppliers"',
        '"blocker_code"', '"recommended_actions"', '"uncertainties"',
        "award_with_reserve", "award_atlas", "designate_boreal_reserve", "exclude_ineligible_suppliers",
    )
    leaked = [value for value in prohibited_answer_fragments if value in serialized]
    if leaked:
        raise AssertionError(f"Canonical extraction leaks answer fields: {leaked}")
    counts = Counter(item["artifact_format"] for item in extraction["evidence_records"])
    result = {
        "status": "passed", "extraction": str(args.extraction.resolve()), "sha256": sha256_file(args.extraction),
        "size_bytes": args.extraction.stat().st_size, "artifact_count": len(extraction["artifact_inputs"]),
        "record_count": len(extraction["evidence_records"]), "record_counts_by_format": dict(sorted(counts.items())),
        "source_refs": [item["source_ref"] for item in extraction["evidence_records"]],
        "schema_valid": True,
        "fresh_binary_rebuild_exact_match": True,
        "answer_leakage_fragments": [],
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
