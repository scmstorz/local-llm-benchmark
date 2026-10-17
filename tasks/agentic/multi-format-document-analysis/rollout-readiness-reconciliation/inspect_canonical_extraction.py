#!/usr/bin/env python3
"""Validate the frozen canonical extraction against all binary sources."""

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
    if len(records) != 15:
        raise AssertionError("Canonical extraction must contain 15 unique facts")

    gates = records["POL-GATES"]["text"]
    for fragment in (
        "Completion is at least 95%.",
        "Open Sev-1 issue count equals 0.",
        "Open Sev-2 issue count is at most 2.",
        "Support capacity / projected peak load is at least 1.25.",
    ):
        if fragment not in gates:
            raise AssertionError(f"Missing policy extraction: {fragment}")
    if "Portfolio averages" not in records["POL-REGION"]["text"]:
        raise AssertionError("Region-level authority was not extracted")
    if "at least one region" not in records["POL-PHASE"]["text"]:
        raise AssertionError("Phased-release authority was not extracted")
    if "2026-08-31 18:00 UTC" not in records["POL-CUTOFF"]["text"]:
        raise AssertionError("Policy cutoff was not extracted")

    preliminary = field_map(records["REL-PRELIMINARY"])
    if "Central | 96% | 0 | 2 | Preliminary" != preliminary["Central"]["value"]:
        raise AssertionError("Preliminary Central values are wrong")
    if "East | 98% | 0 | 0 | Preliminary" != preliminary["East"]["value"]:
        raise AssertionError("Preliminary East values are wrong")
    final_note = field_map(records["REL-FINAL"])
    if final_note["supersedes_page"]["value"] != 2:
        raise AssertionError("Final PDF note does not supersede page 2")
    if final_note["evidence_cutoff"]["value"] != "2026-08-31 18:00 UTC":
        raise AssertionError("Final PDF cutoff is wrong")

    expected_reliability = {
        "REL-NORTH": ("97%", 0, 1),
        "REL-CENTRAL": ("96%", 0, 3),
        "REL-WEST": ("94%", 0, 0),
        "REL-EAST": ("98%", 1, 0),
    }
    for fact_code, expected in expected_reliability.items():
        fields = field_map(records[fact_code])
        observed = (
            fields["completion"]["value"],
            fields["open_sev1"]["value"],
            fields["open_sev2"]["value"],
        )
        if observed != expected:
            raise AssertionError(f"{fact_code}: expected {expected}, found {observed}")

    expected_capacity = {
        "CAP-NORTH": (137, 108, 1.26851851851852, "=IFERROR(B4/C4,0)"),
        "CAP-CENTRAL": (150, 117, 1.28205128205128, "=IFERROR(B5/C5,0)"),
        "CAP-WEST": (150, 100, 1.5, "=IFERROR(B6/C6,0)"),
        "CAP-EAST": (180, 130, 1.38461538461538, "=IFERROR(B7/C7,0)"),
    }
    for fact_code, expected in expected_capacity.items():
        fields = field_map(records[fact_code])
        observed = (
            fields["support_capacity"]["value"],
            fields["projected_peak_load"]["value"],
            fields["capacity_ratio"]["value"],
            fields["capacity_ratio"]["formula"],
        )
        if observed != expected or fields["gate_check"]["value"] != "PASS":
            raise AssertionError(f"{fact_code}: capacity extraction mismatch")

    dashboard = field_map(records["DASH-STATUS"])
    if (
        dashboard["portfolio_status"]["value"] != "GO"
        or dashboard["portfolio_status"]["formula"]
        != '=IF(AND(B4>=$F$4,B5<=$F$5,B6>=$F$6),"GO","HOLD")'
        or dashboard["average_completion"]["value"] != 0.9625
        or dashboard["average_open_issues_per_region"]["value"] != 1.25
    ):
        raise AssertionError("Dashboard extraction mismatch")

    serialized = json.dumps(extraction, sort_keys=True)
    prohibited_answer_fragments = (
        "phased_go",
        "launch_north_only",
        "sev2_above_limit",
        "completion_below_threshold",
        "approved_regions",
        "blocked_regions",
        "recommended_actions",
    )
    leaked = [value for value in prohibited_answer_fragments if value in serialized]
    if leaked:
        raise AssertionError(f"Canonical extraction leaks answer fields: {leaked}")

    counts = Counter(item["artifact_format"] for item in extraction["evidence_records"])
    result = {
        "status": "passed",
        "extraction": str(args.extraction.resolve()),
        "sha256": sha256_file(args.extraction),
        "size_bytes": args.extraction.stat().st_size,
        "artifact_count": len(extraction["artifact_inputs"]),
        "record_count": len(extraction["evidence_records"]),
        "record_counts_by_format": dict(sorted(counts.items())),
        "source_refs": [
            item["source_ref"] for item in extraction["evidence_records"]
        ],
        "schema_valid": True,
        "fresh_binary_rebuild_exact_match": True,
        "answer_leakage_fragments": [],
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
