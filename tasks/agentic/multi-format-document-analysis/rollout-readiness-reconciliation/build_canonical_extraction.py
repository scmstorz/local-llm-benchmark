#!/usr/bin/env python3
"""Build the frozen Track A representation from the three binary fixtures."""

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


CASE_RELATIVE = Path(
    "tasks/agentic/multi-format-document-analysis/"
    "rollout-readiness-reconciliation"
)
QUALIFICATION_FILES = {
    "docx": "docx-artifact-qualification-v0.1.json",
    "pdf": "pdf-artifact-qualification-v0.1.json",
    "xlsx": "xlsx-artifact-qualification-v0.1.json",
}
REGIONS = ("North", "Central", "West", "East")


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
    return "".join(
        html.unescape(value.decode("utf-8"))
        for value in re.findall(pattern, fragment, re.DOTALL)
    )


def field(name: str, value: object, formula: str | None = None) -> dict[str, object]:
    return {"name": name, "value": value, "formula": formula}


def record(
    fact_code: str,
    source_ref: str,
    artifact_format: str,
    record_type: str,
    authority: str,
    text: str,
    fields: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "fact_code": fact_code,
        "source_ref": source_ref,
        "artifact_format": artifact_format,
        "record_type": record_type,
        "authority": authority,
        "text": text,
        "fields": fields or [],
    }


def extract_docx(document_path: Path) -> list[dict[str, object]]:
    with zipfile.ZipFile(document_path) as archive:
        if archive.testzip() is not None:
            raise AssertionError("DOCX ZIP integrity check failed")
        document_xml = archive.read("word/document.xml")

    paragraphs = [
        xml_text(fragment, b"w:t")
        for fragment in re.findall(
            rb"<w:p(?:\s[^>]*)?>(.*?)</w:p>", document_xml, re.DOTALL
        )
    ]

    def paragraph_starting(prefix: str) -> str:
        matches = [value for value in paragraphs if value.startswith(prefix)]
        if len(matches) != 1:
            raise AssertionError(
                f"DOCX paragraph prefix {prefix!r}: found {len(matches)} matches"
            )
        return matches[0]

    tables = re.findall(rb"<w:tbl(?:\s[^>]*)?>(.*?)</w:tbl>", document_xml, re.DOTALL)
    if len(tables) != 1:
        raise AssertionError(f"Expected one DOCX table, found {len(tables)}")
    gate_rows = []
    for row_fragment in re.findall(
        rb"<w:tr(?:\s[^>]*)?>(.*?)</w:tr>", tables[0], re.DOTALL
    ):
        gate_rows.append(
            [
                xml_text(cell_fragment, b"w:t")
                for cell_fragment in re.findall(
                    rb"<w:tc(?:\s[^>]*)?>(.*?)</w:tc>",
                    row_fragment,
                    re.DOTALL,
                )
            ]
        )
    expected_header = ["Gate", "Passing criterion", "Evaluation", "Evidence basis"]
    if not gate_rows or gate_rows[0] != expected_header or len(gate_rows) != 5:
        raise AssertionError(f"Unexpected Regional-gates table: {gate_rows!r}")
    gate_text = "\n".join(" | ".join(row) for row in gate_rows)
    gate_fields = [
        field(row[0], " | ".join(row[1:]))
        for row in gate_rows[1:]
    ]

    decision_rule = paragraph_starting("Apply every gate independently")
    phased_release = paragraph_starting("A phased production launch may proceed")
    evidence_cutoff = paragraph_starting("Use evidence finalized no later")
    return [
        record(
            "POL-GATES",
            "rollout-policy.docx#table=Regional-gates",
            "docx",
            "table",
            "governing_policy",
            gate_text,
            gate_fields,
        ),
        record(
            "POL-REGION",
            "rollout-policy.docx#heading=Decision-rule",
            "docx",
            "paragraph",
            "governing_policy",
            decision_rule,
        ),
        record(
            "POL-PHASE",
            "rollout-policy.docx#heading=Phased-release",
            "docx",
            "paragraph",
            "governing_policy",
            phased_release,
        ),
        record(
            "POL-CUTOFF",
            "rollout-policy.docx#heading=Evidence-cutoff",
            "docx",
            "paragraph",
            "governing_policy",
            evidence_cutoff,
        ),
    ]


def collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def pdf_table_rows(page: str, status: str) -> list[tuple[str, str, int, int, str]]:
    pattern = re.compile(
        r"^\s*(North|Central|West|East)\s+(\d+%)\s+(\d+)\s+(\d+)\s+"
        + re.escape(status)
        + r"\s*$",
        re.MULTILINE,
    )
    rows = [
        (region, completion, int(sev1), int(sev2), evidence_status)
        for region, completion, sev1, sev2, evidence_status in (
            (*match.groups(), status) for match in pattern.finditer(page)
        )
    ]
    if [row[0] for row in rows] != list(REGIONS):
        raise AssertionError(f"Unexpected {status} PDF rows: {rows!r}")
    return rows


def row_text(row: tuple[str, str, int, int, str]) -> str:
    return " | ".join(str(value) for value in row)


def extract_pdf(document_path: Path) -> list[dict[str, object]]:
    completed = subprocess.run(
        ["pdftotext", "-layout", str(document_path), "-"],
        check=True,
        capture_output=True,
        text=True,
    )
    pages = completed.stdout.rstrip("\f\n").split("\f")
    if len(pages) != 3:
        raise AssertionError(f"Expected three extracted PDF pages, found {len(pages)}")
    preliminary_rows = pdf_table_rows(pages[1], "Preliminary")
    final_rows = pdf_table_rows(pages[2], "Final at cutoff")

    preliminary_text = "\n".join(
        ["Region | Completion | Open Sev-1 | Open Sev-2 | Evidence status"]
        + [row_text(row) for row in preliminary_rows]
    )
    collapsed_final_page = collapse_whitespace(pages[2])
    final_note_match = re.search(
        r"This final table supersedes the Preliminary validation table on page 2\. "
        r"It is the only reliability evidence finalized at the decision cutoff, "
        r"2026-08-31 18:00 UTC\.",
        collapsed_final_page,
    )
    if final_note_match is None:
        raise AssertionError("Final PDF authority note is missing")

    results = [
        record(
            "REL-PRELIMINARY",
            "reliability-review.pdf#page=2&table=Preliminary-validation",
            "pdf",
            "table",
            "preliminary_superseded",
            preliminary_text,
            [field(row[0], row_text(row)) for row in preliminary_rows],
        ),
        record(
            "REL-FINAL",
            "reliability-review.pdf#page=3&note=Final-table",
            "pdf",
            "note",
            "final_at_cutoff",
            final_note_match.group(0),
            [
                field("supersedes_page", 2),
                field("evidence_cutoff", "2026-08-31 18:00 UTC"),
            ],
        ),
    ]
    for row in final_rows:
        fact_code = f"REL-{row[0].upper()}"
        results.append(
            record(
                fact_code,
                (
                    "reliability-review.pdf#page=3&table=Final-validation&row="
                    + row[0]
                ),
                "pdf",
                "row",
                "final_at_cutoff",
                row_text(row),
                [
                    field("completion", row[1]),
                    field("open_sev1", row[2]),
                    field("open_sev2", row[3]),
                    field("evidence_status", row[4]),
                ],
            )
        )
    return results


def parse_number(value: str) -> int | float:
    parsed = float(value)
    return int(parsed) if parsed.is_integer() else parsed


def xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    shared_xml = archive.read("xl/sharedStrings.xml")
    return [
        xml_text(fragment, b"t")
        for fragment in re.findall(rb"<si(?:\s[^>]*)?>(.*?)</si>", shared_xml, re.DOTALL)
    ]


def xlsx_cells(sheet_xml: bytes, shared: list[str]) -> dict[str, dict[str, object]]:
    cells: dict[str, dict[str, object]] = {}
    for match in re.finditer(
        rb"<c\s+([^>]*)>(.*?)</c>", sheet_xml, re.DOTALL
    ):
        attributes, body = match.groups()
        reference_match = re.search(rb'\br="([A-Z]+[0-9]+)"', attributes)
        if reference_match is None:
            continue
        reference = reference_match.group(1).decode("ascii")
        type_match = re.search(rb'\bt="([^"]+)"', attributes)
        cell_type = type_match.group(1).decode("ascii") if type_match else "n"
        value_match = re.search(rb"<v>(.*?)</v>", body, re.DOTALL)
        formula_match = re.search(rb"<f(?:\s[^>]*)?>(.*?)</f>", body, re.DOTALL)
        raw_value = (
            html.unescape(value_match.group(1).decode("utf-8"))
            if value_match is not None
            else ""
        )
        if cell_type == "s":
            value: object = shared[int(raw_value)]
        elif cell_type in {"str", "inlineStr"}:
            value = raw_value if cell_type == "str" else xml_text(body, b"t")
        elif raw_value:
            value = parse_number(raw_value)
        else:
            value = None
        formula = None
        if formula_match is not None:
            formula = "=" + html.unescape(formula_match.group(1).decode("utf-8"))
        cells[reference] = {"value": value, "formula": formula}
    return cells


def extract_xlsx(workbook_path: Path) -> list[dict[str, object]]:
    with zipfile.ZipFile(workbook_path) as archive:
        if archive.testzip() is not None:
            raise AssertionError("XLSX ZIP integrity check failed")
        shared = xlsx_shared_strings(archive)
        summary = xlsx_cells(archive.read("xl/worksheets/sheet1.xml"), shared)
        capacity = xlsx_cells(archive.read("xl/worksheets/sheet2.xml"), shared)

    def cell_field(cells: dict[str, dict[str, object]], address: str, name: str):
        cell = cells[address]
        return field(name, cell["value"], cell["formula"])

    dashboard_fields = [
        cell_field(summary, "B3", "portfolio_status"),
        cell_field(summary, "B4", "average_completion"),
        cell_field(summary, "B5", "average_open_issues_per_region"),
    ]
    dashboard_text = "; ".join(
        f"{item['name']}={item['value']}" for item in dashboard_fields
    )

    capacity_records = []
    for row_number, region in enumerate(REGIONS, start=4):
        if capacity[f"A{row_number}"]["value"] != region:
            raise AssertionError(f"Unexpected Capacity row {row_number}")
        row_fields = [
            cell_field(capacity, f"B{row_number}", "support_capacity"),
            cell_field(capacity, f"C{row_number}", "projected_peak_load"),
            cell_field(capacity, f"D{row_number}", "capacity_ratio"),
            cell_field(capacity, f"E{row_number}", "gate_check"),
        ]
        capacity_records.append(
            record(
                f"CAP-{region.upper()}",
                (
                    "regional-readiness.xlsx#sheet=Capacity&range="
                    f"B{row_number}:E{row_number}"
                ),
                "xlsx",
                "range",
                "regional_capacity",
                region
                + "; "
                + "; ".join(
                    f"{item['name']}={item['value']}" for item in row_fields
                ),
                row_fields,
            )
        )
    return capacity_records + [
        record(
            "DASH-STATUS",
            "regional-readiness.xlsx#sheet=Summary&range=B3:B5",
            "xlsx",
            "range",
            "aggregate_dashboard",
            dashboard_text,
            dashboard_fields,
        )
    ]


def build_extraction(repo_root: Path) -> dict[str, object]:
    root = repo_root.resolve()
    case_dir = root / CASE_RELATIVE
    blueprint = load_json(case_dir / "source-blueprint-v0.1.json")

    artifacts: dict[str, Path] = {}
    artifact_inputs = []
    for blueprint_artifact in blueprint["artifacts"]:
        artifact_format = blueprint_artifact["format"]
        qualification = load_json(
            case_dir / QUALIFICATION_FILES[artifact_format]
        )
        if qualification.get("status") != "qualified":
            raise AssertionError(f"{artifact_format} artifact is not qualified")
        artifact = qualification["artifact"]
        artifact_path = root / artifact["path"]
        observed_hash = sha256_file(artifact_path)
        if observed_hash != artifact["sha256"]:
            raise AssertionError(f"{artifact_format} artifact hash mismatch")
        if artifact_path.name != blueprint_artifact["filename"]:
            raise AssertionError(f"{artifact_format} artifact filename mismatch")
        artifacts[artifact_format] = artifact_path
        artifact_inputs.append(
            {
                "filename": artifact_path.name,
                "format": artifact_format,
                "sha256": observed_hash,
                "size_bytes": artifact_path.stat().st_size,
            }
        )

    evidence_records = (
        extract_docx(artifacts["docx"])
        + extract_pdf(artifacts["pdf"])
        + extract_xlsx(artifacts["xlsx"])
    )
    expected_identity = [
        (item["fact_code"], item["source_ref"], item["artifact"])
        for item in blueprint["facts"]
    ]
    observed_identity = [
        (item["fact_code"], item["source_ref"], item["artifact_format"])
        for item in evidence_records
    ]
    if observed_identity != expected_identity:
        raise AssertionError(
            "Canonical record identity does not match the source blueprint"
        )

    return {
        "schema_version": "1.0.0",
        "case_id": blueprint["case_id"],
        "extraction_version": "0.1.0",
        "representation": "canonical_artifact_evidence",
        "artifact_inputs": artifact_inputs,
        "evidence_records": evidence_records,
    }


def main() -> None:
    args = parse_args()
    result = build_extraction(args.repo_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
