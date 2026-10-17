#!/usr/bin/env python3
"""Run deterministic structural, text and table checks for the PDF fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pdfplumber
from pypdf import PdfReader


PRELIMINARY_TABLE = [
    ["Region", "Completion", "Open Sev-1", "Open Sev-2", "Evidence status"],
    ["North", "97%", "0", "1", "Preliminary"],
    ["Central", "96%", "0", "2", "Preliminary"],
    ["West", "94%", "0", "0", "Preliminary"],
    ["East", "98%", "0", "0", "Preliminary"],
]
FINAL_TABLE = [
    ["Region", "Completion", "Open Sev-1", "Open Sev-2", "Evidence status"],
    ["North", "97%", "0", "1", "Final at cutoff"],
    ["Central", "96%", "0", "3", "Final at cutoff"],
    ["West", "94%", "0", "0", "Final at cutoff"],
    ["East", "98%", "1", "0", "Final at cutoff"],
]
CHANGE_TABLE = [
    ["Region", "Preliminary", "Final at cutoff"],
    ["Central", "2 open Sev-2", "3 open Sev-2"],
    ["East", "0 open Sev-1", "1 open Sev-1"],
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--document", required=True, type=Path)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_fragment(text: str, fragment: str, location: str) -> None:
    if fragment not in text:
        raise AssertionError(f"{location}: missing required text {fragment!r}")


def main() -> None:
    args = parse_args()
    document_path = args.document.resolve()
    reader = PdfReader(document_path, strict=True)
    if reader.is_encrypted:
        raise AssertionError("PDF must not be encrypted")
    if len(reader.pages) != 3:
        raise AssertionError(f"Expected three pages, found {len(reader.pages)}")

    metadata = dict(reader.metadata or {})
    expected_metadata = {
        "/Author": "Local LLM Benchmark Lab",
        "/CreationDate": "D:20000101000000+00'00'",
        "/Creator": "ReportLab 5.0.1",
        "/Keywords": "synthetic benchmark, reliability review, regional validation",
        "/ModDate": "D:20000101000000+00'00'",
        "/Subject": "Synthetic multi-format benchmark fixture",
        "/Title": "Regional Reliability Review",
    }
    for key, expected in expected_metadata.items():
        if metadata.get(key) != expected:
            raise AssertionError(
                f"Metadata {key}: expected {expected!r}, found {metadata.get(key)!r}"
            )

    page_texts: list[str] = []
    page_geometry: list[dict[str, float | int]] = []
    annotation_count = 0
    for page_number, page in enumerate(reader.pages, start=1):
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        rotation = int(page.get("/Rotate", 0))
        if (width, height, rotation) != (612.0, 792.0, 0):
            raise AssertionError(
                f"Page {page_number}: unexpected geometry {(width, height, rotation)!r}"
            )
        text = page.extract_text() or ""
        require_fragment(text, "REGIONAL RELIABILITY REVIEW", f"page {page_number}")
        require_fragment(text, f"Page {page_number} of 3", f"page {page_number}")
        require_fragment(text, "Synthetic benchmark fixture", f"page {page_number}")
        page_texts.append(text)
        page_geometry.append(
            {
                "page": page_number,
                "width_points": width,
                "height_points": height,
                "rotation": rotation,
            }
        )
        annotations = page.get("/Annots") or []
        annotation_count += len(annotations)

    page_one, page_two, page_three = page_texts
    require_fragment(page_one, "FINAL RELIABILITY EVIDENCE", "page 1")
    require_fragment(page_one, "2026-08-31 18:00 UTC", "page 1")
    require_fragment(
        page_one,
        "The final table on page 3 supersedes the preliminary table on page 2",
        "page 1",
    )

    require_fragment(page_two, "PRELIMINARY - SUPERSEDED", "page 2")
    require_fragment(page_two, "Table 1. Preliminary validation - superseded", "page 2")
    require_fragment(page_two, "Central had two open Sev-2 issues", "page 2")
    require_fragment(page_two, "East had zero open Sev-1 issues", "page 2")
    require_fragment(page_two, "Do not use for rollout authorization", "page 2")

    require_fragment(page_three, "FINAL EVIDENCE AT CUTOFF", "page 3")
    require_fragment(page_three, "Table 2. Final validation", "page 3")
    require_fragment(
        page_three,
        "This final table supersedes the Preliminary validation table on page 2",
        "page 3",
    )
    require_fragment(page_three, "2026-08-31 18:00 UTC", "page 3")

    outline = reader.outline
    outline_titles = [item["/Title"] for item in outline]
    outline_pages = [reader.get_destination_page_number(item) + 1 for item in outline]
    if outline_titles != [
        "Purpose and authority",
        "Preliminary validation",
        "Final validation",
    ] or outline_pages != [1, 2, 3]:
        raise AssertionError(
            f"Unexpected outline: titles={outline_titles!r}, pages={outline_pages!r}"
        )

    root = reader.root_object
    if any(key in root for key in ("/AcroForm", "/OpenAction", "/AA")):
        raise AssertionError("PDF contains an interactive form or automatic action")
    if annotation_count:
        raise AssertionError(f"PDF contains {annotation_count} page annotations")

    with pdfplumber.open(document_path) as plumber_document:
        extracted_tables = [page.extract_tables() for page in plumber_document.pages]
    if extracted_tables[1] != [PRELIMINARY_TABLE]:
        raise AssertionError(
            "Page 2 preliminary table mismatch:\n"
            + json.dumps(extracted_tables[1], indent=2)
        )
    if extracted_tables[2] != [FINAL_TABLE, CHANGE_TABLE]:
        raise AssertionError(
            "Page 3 final/change tables mismatch:\n"
            + json.dumps(extracted_tables[2], indent=2)
        )

    result = {
        "status": "passed",
        "document": str(document_path),
        "sha256": sha256_file(document_path),
        "size_bytes": document_path.stat().st_size,
        "page_count": len(reader.pages),
        "page_geometry": page_geometry,
        "metadata": expected_metadata,
        "outline_titles": outline_titles,
        "outline_pages": outline_pages,
        "annotation_count": annotation_count,
        "encrypted": reader.is_encrypted,
        "javascript_or_automatic_actions": 0,
        "extracted_table_counts": [len(tables) for tables in extracted_tables],
        "source_anchor_reconciliation": [
            {
                "fact_code": "REL-PRELIMINARY",
                "page": 2,
                "table": "Preliminary-validation",
                "central_open_sev2": 2,
                "east_open_sev1": 0,
            },
            {
                "fact_code": "REL-FINAL",
                "page": 3,
                "note": "Final-table",
                "supersedes_page": 2,
                "cutoff": "2026-08-31 18:00 UTC",
            },
            {
                "fact_code": "REL-NORTH",
                "page": 3,
                "row": ["North", "97%", "0", "1", "Final at cutoff"],
            },
            {
                "fact_code": "REL-CENTRAL",
                "page": 3,
                "row": ["Central", "96%", "0", "3", "Final at cutoff"],
            },
            {
                "fact_code": "REL-WEST",
                "page": 3,
                "row": ["West", "94%", "0", "0", "Final at cutoff"],
            },
            {
                "fact_code": "REL-EAST",
                "page": 3,
                "row": ["East", "98%", "1", "0", "Final at cutoff"],
            },
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
