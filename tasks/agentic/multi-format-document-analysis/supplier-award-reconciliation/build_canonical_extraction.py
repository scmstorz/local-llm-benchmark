#!/usr/bin/env python3
"""Build the frozen Track A representation from the three supplier fixtures."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
import zipfile
from pathlib import Path
from typing import Any


CASE_RELATIVE = Path("tasks/agentic/multi-format-document-analysis/supplier-award-reconciliation")
QUALIFICATION_FILES = {
    "docx": "docx-artifact-qualification-v0.2.json",
    "pdf": "pdf-artifact-qualification-v0.2.json",
    "xlsx": "xlsx-artifact-qualification-v0.2.json",
}
SUPPLIERS = ("Atlas", "Boreal", "Cedar", "Delta")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"Expected a JSON object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def xml_text(fragment: bytes, tag: bytes) -> str:
    pattern = rb"<" + tag + rb"(?:\s[^>]*)?>(.*?)</" + tag + rb">"
    return "".join(html.unescape(value.decode("utf-8")) for value in re.findall(pattern, fragment, re.DOTALL))


def field(name: str, value: object, formula: str | None = None) -> dict[str, object]:
    return {"name": name, "value": value, "formula": formula}


def record(
    fact_code: str, source_ref: str, artifact_format: str, record_type: str,
    authority: str, text: str, fields: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "fact_code": fact_code, "source_ref": source_ref, "artifact_format": artifact_format,
        "record_type": record_type, "authority": authority, "text": text, "fields": fields or [],
    }


def extract_docx(document_path: Path) -> list[dict[str, object]]:
    with zipfile.ZipFile(document_path) as archive:
        if archive.testzip() is not None:
            raise AssertionError("DOCX ZIP integrity check failed")
        document_xml = archive.read("word/document.xml")
    paragraphs = [xml_text(fragment, b"w:t") for fragment in re.findall(rb"<w:p(?:\s[^>]*)?>(.*?)</w:p>", document_xml, re.DOTALL)]

    def paragraph_starting(prefix: str) -> str:
        matches = [value for value in paragraphs if value.startswith(prefix)]
        if len(matches) != 1:
            raise AssertionError(f"DOCX paragraph prefix {prefix!r}: found {len(matches)} matches")
        return matches[0]

    tables = re.findall(rb"<w:tbl(?:\s[^>]*)?>(.*?)</w:tbl>", document_xml, re.DOTALL)
    if len(tables) != 1:
        raise AssertionError(f"Expected one DOCX table, found {len(tables)}")
    gate_rows = [
        [xml_text(cell, b"w:t") for cell in re.findall(rb"<w:tc(?:\s[^>]*)?>(.*?)</w:tc>", row, re.DOTALL)]
        for row in re.findall(rb"<w:tr(?:\s[^>]*)?>(.*?)</w:tr>", tables[0], re.DOTALL)
    ]
    expected_header = ["Gate", "Passing criterion", "Evaluation", "Authoritative evidence"]
    if not gate_rows or gate_rows[0] != expected_header or len(gate_rows) != 5:
        raise AssertionError(f"Unexpected Eligibility-gates table: {gate_rows!r}")
    return [
        record(
            "POL-ELIGIBILITY", "supplier-selection-policy.docx#table=Eligibility-gates", "docx", "table", "governing_policy",
            "\n".join(" | ".join(row) for row in gate_rows),
            [field(row[0], " | ".join(row[1:])) for row in gate_rows[1:]],
        ),
        record(
            "POL-SELECTION", "supplier-selection-policy.docx#heading=Selection-sequence", "docx", "paragraph", "governing_policy",
            paragraph_starting("First exclude every ineligible supplier"),
        ),
        record(
            "POL-AUTHORITY", "supplier-selection-policy.docx#heading=Evidence-authority", "docx", "paragraph", "governing_policy",
            paragraph_starting("The signed-final assurance appendix"),
        ),
        record(
            "POL-CUTOFF", "supplier-selection-policy.docx#heading=Decision-cutoff", "docx", "paragraph", "governing_policy",
            paragraph_starting("The award decision uses evidence finalized"),
        ),
    ]


def collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def pdf_rows(page: str, status: str) -> list[tuple[str, str, int, str]]:
    pattern = re.compile(
        r"^\s*(Atlas|Boreal|Cedar|Delta)\s+([A-C])\s+(\d+)\s+" + re.escape(status) + r"\s*$",
        re.MULTILINE,
    )
    rows = [(supplier, rating, int(findings), status) for supplier, rating, findings in pattern.findall(page)]
    if [row[0] for row in rows] != list(SUPPLIERS):
        raise AssertionError(f"Unexpected {status} PDF rows: {rows!r}")
    return rows


def row_text(row: tuple[str, str, int, str]) -> str:
    return " | ".join(str(value) for value in row)


def extract_pdf(document_path: Path) -> list[dict[str, object]]:
    completed = subprocess.run(["pdftotext", "-layout", str(document_path), "-"], check=True, capture_output=True, text=True)
    pages = completed.stdout.rstrip("\f\n").split("\f")
    if len(pages) != 3:
        raise AssertionError(f"Expected three extracted PDF pages, found {len(pages)}")
    draft = pdf_rows(pages[1], "Unsigned draft")
    final = pdf_rows(pages[2], "Signed final")
    final_note = re.search(
        r"This signed-final appendix supersedes the Unsigned draft on page 2\. It was finalized at "
        r"2026-09-08 14:30 UTC, before the 16:00 UTC decision cutoff\.",
        collapse_whitespace(pages[2]),
    )
    if final_note is None:
        raise AssertionError("Signed-final PDF authority note is missing")
    records = [
        record(
            "ASSUR-DRAFT", "supplier-assurance-review.pdf#page=2&table=Unsigned-draft", "pdf", "table", "unsigned_draft_superseded",
            "\n".join(["Supplier | Assurance rating | Unresolved critical findings | Evidence status"] + [row_text(row) for row in draft]),
            [field(row[0], row_text(row)) for row in draft],
        ),
        record(
            "ASSUR-FINAL", "supplier-assurance-review.pdf#page=3&note=Signed-final", "pdf", "note", "signed_final_at_cutoff",
            final_note.group(0),
            [field("supersedes_page", 2), field("finalized_at", "2026-09-08 14:30 UTC"), field("decision_cutoff", "2026-09-08 16:00 UTC")],
        ),
    ]
    for row in final:
        records.append(
            record(
                f"ASSUR-{row[0].upper()}",
                f"supplier-assurance-review.pdf#page=3&table=Final-assurance&row={row[0]}",
                "pdf", "row", "signed_final_at_cutoff", row_text(row),
                [field("assurance_rating", row[1]), field("unresolved_critical_findings", row[2]), field("evidence_status", row[3])],
            )
        )
    return records


def parse_number(value: str) -> int | float:
    parsed = float(value)
    return int(parsed) if parsed.is_integer() else parsed


def xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    shared_xml = archive.read("xl/sharedStrings.xml")
    return [xml_text(fragment, b"t") for fragment in re.findall(rb"<si(?:\s[^>]*)?>(.*?)</si>", shared_xml, re.DOTALL)]


def xlsx_cells(sheet_xml: bytes, shared: list[str]) -> dict[str, dict[str, object]]:
    cells: dict[str, dict[str, object]] = {}
    for match in re.finditer(
        rb"<c\s+([^>]*?)(?:/>|>(.*?)</c>)", sheet_xml, re.DOTALL
    ):
        attributes, body = match.groups()
        body = body or b""
        reference_match = re.search(rb'\br="([A-Z]+[0-9]+)"', attributes)
        if reference_match is None:
            continue
        reference = reference_match.group(1).decode("ascii")
        type_match = re.search(rb'\bt="([^"]+)"', attributes)
        cell_type = type_match.group(1).decode("ascii") if type_match else "n"
        value_match = re.search(rb"<v>(.*?)</v>", body, re.DOTALL)
        formula_match = re.search(rb"<f(?:\s[^>]*)?>(.*?)</f>", body, re.DOTALL)
        raw_value = html.unescape(value_match.group(1).decode("utf-8")) if value_match is not None else ""
        if cell_type == "s":
            value: object = shared[int(raw_value)]
        elif cell_type in {"str", "inlineStr"}:
            value = raw_value if cell_type == "str" else xml_text(body, b"t")
        elif raw_value:
            value = parse_number(raw_value)
        else:
            value = None
        formula = "=" + html.unescape(formula_match.group(1).decode("utf-8")) if formula_match is not None else None
        cells[reference] = {"value": value, "formula": formula}
    return cells


def extract_xlsx(workbook_path: Path) -> list[dict[str, object]]:
    with zipfile.ZipFile(workbook_path) as archive:
        if archive.testzip() is not None:
            raise AssertionError("XLSX ZIP integrity check failed")
        shared = xlsx_shared_strings(archive)
        dashboard = xlsx_cells(archive.read("xl/worksheets/sheet1.xml"), shared)
        analysis = xlsx_cells(archive.read("xl/worksheets/sheet2.xml"), shared)

    def cell_field(cells: dict[str, dict[str, object]], address: str, name: str):
        cell = cells[address]
        return field(name, cell["value"], cell["formula"])

    records = []
    for row_number, supplier in enumerate(SUPPLIERS, start=5):
        if analysis[f"A{row_number}"]["value"] != supplier:
            raise AssertionError(f"Unexpected Bid Analysis row {row_number}")
        row_fields = [
            cell_field(analysis, f"B{row_number}", "base_annual_fee_eur"),
            cell_field(analysis, f"C{row_number}", "mobilization_eur"),
            cell_field(analysis, f"D{row_number}", "transition_credit_eur"),
            cell_field(analysis, f"E{row_number}", "adjusted_first_year_cost_eur"),
            cell_field(analysis, f"F{row_number}", "available_units"),
            cell_field(analysis, f"G{row_number}", "required_units"),
            cell_field(analysis, f"H{row_number}", "capacity_headroom"),
            cell_field(analysis, f"I{row_number}", "cost_gate"),
            cell_field(analysis, f"J{row_number}", "capacity_gate"),
        ]
        records.append(
            record(
                f"BID-{supplier.upper()}", f"bid-evaluation.xlsx#sheet=Bid Analysis&range=B{row_number}:J{row_number}",
                "xlsx", "range", "commercial_analysis",
                supplier + "; " + "; ".join(f"{item['name']}={item['value']}" for item in row_fields), row_fields,
            )
        )
    recommendation_fields = [
        cell_field(dashboard, "B3", "recommended_supplier"),
        cell_field(dashboard, "B4", "lowest_adjusted_first_year_cost_eur"),
        cell_field(dashboard, "B5", "recommendation_basis"),
    ]
    scope_fields = [cell_field(dashboard, "B7", "ranking_scope"), cell_field(dashboard, "B8", "assurance_scope")]
    return records + [
        record(
            "DASH-RECOMMENDATION", "bid-evaluation.xlsx#sheet=Dashboard&range=B3:B5", "xlsx", "range", "commercial_dashboard",
            "; ".join(f"{item['name']}={item['value']}" for item in recommendation_fields), recommendation_fields,
        ),
        record(
            "DASH-SCOPE", "bid-evaluation.xlsx#sheet=Dashboard&range=B7:B8", "xlsx", "range", "commercial_dashboard",
            "; ".join(f"{item['name']}={item['value']}" for item in scope_fields), scope_fields,
        ),
    ]


def build_extraction(repo_root: Path) -> dict[str, object]:
    root = repo_root.resolve()
    case_dir = root / CASE_RELATIVE
    blueprint = load_json(case_dir / "source-blueprint-v0.2.json")
    artifacts: dict[str, Path] = {}
    artifact_inputs = []
    for blueprint_artifact in blueprint["artifacts"]:
        artifact_format = blueprint_artifact["format"]
        qualification = load_json(case_dir / QUALIFICATION_FILES[artifact_format])
        if qualification.get("status") != "qualified":
            raise AssertionError(f"{artifact_format} artifact is not qualified")
        artifact = qualification["artifact"]
        artifact_path = root / artifact["path"]
        observed_hash = sha256_file(artifact_path)
        if observed_hash != artifact["sha256"] or artifact_path.stat().st_size != artifact["size_bytes"]:
            raise AssertionError(f"{artifact_format} artifact identity mismatch")
        if artifact_path.name != blueprint_artifact["filename"]:
            raise AssertionError(f"{artifact_format} artifact filename mismatch")
        artifacts[artifact_format] = artifact_path
        artifact_inputs.append({"filename": artifact_path.name, "format": artifact_format, "sha256": observed_hash, "size_bytes": artifact_path.stat().st_size})
    evidence_records = extract_docx(artifacts["docx"]) + extract_pdf(artifacts["pdf"]) + extract_xlsx(artifacts["xlsx"])
    expected_identity = [(item["fact_code"], item["source_ref"], item["artifact"]) for item in blueprint["facts"]]
    observed_identity = [(item["fact_code"], item["source_ref"], item["artifact_format"]) for item in evidence_records]
    if observed_identity != expected_identity:
        raise AssertionError("Canonical record identity does not match the source blueprint")
    return {
        "schema_version": "1.0.0", "case_id": blueprint["case_id"], "extraction_version": "0.2.0",
        "representation": "canonical_artifact_evidence", "artifact_inputs": artifact_inputs, "evidence_records": evidence_records,
    }


def main() -> None:
    args = parse_args()
    result = build_extraction(args.repo_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
