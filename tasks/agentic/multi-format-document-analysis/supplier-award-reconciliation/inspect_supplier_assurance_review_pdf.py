#!/usr/bin/env python3
"""Run deterministic structural, text and table checks for supplier-assurance-review.pdf."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pdfplumber
from pypdf import PdfReader


DRAFT_TABLE = [
    ["Supplier", "Assurance rating", "Unresolved critical findings", "Evidence status"],
    ["Atlas", "C", "0", "Unsigned draft"], ["Boreal", "A", "0", "Unsigned draft"],
    ["Cedar", "A", "0", "Unsigned draft"], ["Delta", "B", "0", "Unsigned draft"],
]
FINAL_TABLE = [
    ["Supplier", "Assurance rating", "Unresolved critical findings", "Evidence status"],
    ["Atlas", "B", "0", "Signed final"], ["Boreal", "A", "0", "Signed final"],
    ["Cedar", "A", "1", "Signed final"], ["Delta", "B", "0", "Signed final"],
]
CHANGE_TABLE = [
    ["Supplier", "Unsigned draft", "Signed final"],
    ["Atlas", "Rating C", "Rating B"],
    ["Cedar", "0 critical findings", "1 critical finding"],
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
    if reader.is_encrypted or len(reader.pages) != 3:
        raise AssertionError("PDF must be unencrypted and contain exactly three pages")
    metadata = dict(reader.metadata or {})
    expected_metadata = {
        "/Author": "Local LLM Benchmark Lab", "/CreationDate": "D:20000101000000+00'00'",
        "/Creator": "ReportLab 5.0.1", "/Keywords": "synthetic benchmark, supplier assurance, signed final",
        "/ModDate": "D:20000101000000+00'00'", "/Subject": "Synthetic multi-format benchmark fixture",
        "/Title": "Supplier Assurance Review",
    }
    for key, expected in expected_metadata.items():
        if metadata.get(key) != expected:
            raise AssertionError(f"Metadata {key}: expected {expected!r}, found {metadata.get(key)!r}")

    page_texts = []
    page_geometry = []
    annotation_count = 0
    for page_number, page in enumerate(reader.pages, start=1):
        width, height, rotation = float(page.mediabox.width), float(page.mediabox.height), int(page.get("/Rotate", 0))
        if (width, height, rotation) != (612.0, 792.0, 0):
            raise AssertionError(f"Page {page_number}: unexpected geometry {(width, height, rotation)!r}")
        text = page.extract_text() or ""
        for fragment in ("SUPPLIER ASSURANCE REVIEW", f"Page {page_number} of 3", "Synthetic benchmark fixture"):
            require_fragment(text, fragment, f"page {page_number}")
        page_texts.append(text)
        page_geometry.append({"page": page_number, "width_points": width, "height_points": height, "rotation": rotation})
        annotation_count += len(page.get("/Annots") or [])

    page_one, page_two, page_three = page_texts
    require_fragment(page_one, "SIGNED ASSURANCE EVIDENCE", "page 1")
    require_fragment(page_one, "2026-09-08 14:30 UTC", "page 1")
    require_fragment(page_one, "The signed-final appendix on page 3 supersedes the unsigned draft on page 2", "page 1")
    require_fragment(page_two, "UNSIGNED DRAFT - SUPERSEDED", "page 2")
    require_fragment(page_two, "Table 1. Unsigned draft assurance - superseded", "page 2")
    require_fragment(page_two, "Cedar with zero unresolved critical findings", "page 2")
    require_fragment(page_two, "Atlas with assurance rating C", "page 2")
    require_fragment(page_three, "SIGNED FINAL BEFORE CUTOFF", "page 3")
    require_fragment(page_three, "Table 2. Final assurance", "page 3")
    require_fragment(page_three, "This signed-final appendix supersedes the Unsigned draft on page 2", "page 3")
    require_fragment(page_three, "2026-09-08 14:30 UTC", "page 3")

    outline = reader.outline
    outline_titles = [item["/Title"] for item in outline]
    outline_pages = [reader.get_destination_page_number(item) + 1 for item in outline]
    if outline_titles != ["Purpose and authority", "Unsigned draft", "Signed-final assurance"] or outline_pages != [1, 2, 3]:
        raise AssertionError(f"Unexpected outline: titles={outline_titles!r}, pages={outline_pages!r}")
    root = reader.root_object
    if any(key in root for key in ("/AcroForm", "/OpenAction", "/AA")) or annotation_count:
        raise AssertionError("PDF contains interactive or automatic content")

    with pdfplumber.open(document_path) as plumber_document:
        extracted_tables = [page.extract_tables() for page in plumber_document.pages]
    if extracted_tables[1] != [DRAFT_TABLE]:
        raise AssertionError("Page 2 draft table mismatch:\n" + json.dumps(extracted_tables[1], indent=2))
    if extracted_tables[2] != [FINAL_TABLE, CHANGE_TABLE]:
        raise AssertionError("Page 3 final/change table mismatch:\n" + json.dumps(extracted_tables[2], indent=2))

    result = {
        "status": "passed", "document": str(document_path), "sha256": sha256_file(document_path),
        "size_bytes": document_path.stat().st_size, "page_count": 3, "page_geometry": page_geometry,
        "metadata": expected_metadata, "outline_titles": outline_titles, "outline_pages": outline_pages,
        "annotation_count": annotation_count, "encrypted": reader.is_encrypted,
        "javascript_or_automatic_actions": 0, "extracted_table_counts": [len(tables) for tables in extracted_tables],
        "source_anchor_reconciliation": [
            {"fact_code": "ASSUR-DRAFT", "page": 2, "table": "Unsigned-draft", "cedar_critical_findings": 0, "atlas_rating": "C"},
            {"fact_code": "ASSUR-FINAL", "page": 3, "note": "Signed-final", "supersedes_page": 2, "finalized": "2026-09-08 14:30 UTC", "cutoff": "2026-09-08 16:00 UTC"},
            {"fact_code": "ASSUR-ATLAS", "page": 3, "row": ["Atlas", "B", "0", "Signed final"]},
            {"fact_code": "ASSUR-BOREAL", "page": 3, "row": ["Boreal", "A", "0", "Signed final"]},
            {"fact_code": "ASSUR-CEDAR", "page": 3, "row": ["Cedar", "A", "1", "Signed final"]},
            {"fact_code": "ASSUR-DELTA", "page": 3, "row": ["Delta", "B", "0", "Signed final"]},
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
