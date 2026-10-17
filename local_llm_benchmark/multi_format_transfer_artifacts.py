"""Bounded read-only artifact API for the supplier transfer case v0.2.

The module is deliberately self-contained so complete-system adapters can use
the exact same parser bytes without access to reference answers.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any


API_VERSION = "0.2.0"
MAX_RESPONSE_BYTES = 8192
SUPPLIERS = ("Atlas", "Boreal", "Cedar", "Delta")
ARTIFACTS = {
    "supplier-selection-policy.docx": {
        "format": "docx",
        "sha256": "46142aed4eaa15601252f7dc60756154c1eace4100109a8ab78162e3ea102708",
        "size_bytes": 40404,
        "queries": [
            {"anchor": "table=Eligibility-gates"},
            {"anchor": "heading=Selection-sequence"},
            {"anchor": "heading=Evidence-authority"},
            {"anchor": "heading=Decision-cutoff"},
        ],
    },
    "supplier-assurance-review.pdf": {
        "format": "pdf",
        "sha256": "c25a322efb3e2433787f3f95343f5855c8f05218d287ac310dc19abbdd0c38df",
        "size_bytes": 7678,
        "queries": [
            {"page": 2, "element": "table=Unsigned-draft"},
            {"page": 3, "element": "note=Signed-final"},
            *[
                {"page": 3, "element": f"table=Final-assurance&row={supplier}"}
                for supplier in SUPPLIERS
            ],
        ],
    },
    "bid-evaluation.xlsx": {
        "format": "xlsx",
        "sha256": "f5753b208f79ea8758fe3a35c3fbbb514468bc7372efe0c59623dc2670c5b42c",
        "size_bytes": 14872,
        "queries": [
            *[
                {"sheet": "Bid Analysis", "range": f"B{row}:J{row}"}
                for row in range(5, 9)
            ],
            {"sheet": "Dashboard", "range": "B3:B5"},
            {"sheet": "Dashboard", "range": "B7:B8"},
        ],
    },
}
OPERATIONS = ("list_artifacts", "read_docx", "read_pdf", "read_xlsx")


class ArtifactToolError(ValueError):
    """A stable, candidate-visible artifact-tool failure."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_path(workspace: Path, filename: str) -> Path:
    if not workspace.is_absolute() or not workspace.is_dir():
        raise ArtifactToolError("invalid_workspace", "The artifact workspace is invalid.")
    path = workspace / filename
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise ArtifactToolError("artifact_missing", f"Required artifact is missing: {filename}") from exc
    if not path.is_file() or path.is_symlink():
        raise ArtifactToolError("unsafe_artifact", f"Artifact is not a regular non-symlink file: {filename}")
    expected = ARTIFACTS[filename]
    if metadata.st_size != expected["size_bytes"] or _sha256_file(path) != expected["sha256"]:
        raise ArtifactToolError("artifact_identity_mismatch", f"Frozen artifact identity changed: {filename}")
    return path


def verify_workspace(workspace: Path) -> dict[str, Any]:
    root = workspace.resolve()
    observed = sorted(item.name for item in root.iterdir() if item.is_file() or item.is_symlink())
    expected = sorted(ARTIFACTS)
    if observed != expected:
        raise ArtifactToolError("workspace_inventory_mismatch", "The workspace must contain exactly the three candidate-visible artifacts.")
    for filename in expected:
        _artifact_path(root, filename)
    return {"passed": True, "file_count": 3, "symlinks_present": False}


def _xml_text(fragment: bytes, tag: bytes) -> str:
    pattern = rb"<" + tag + rb"(?:\s[^>]*)?>(.*?)</" + tag + rb">"
    return "".join(html.unescape(value.decode("utf-8")) for value in re.findall(pattern, fragment, re.DOTALL))


def _field(name: str, value: object, formula: str | None = None) -> dict[str, object]:
    return {"name": name, "value": value, "formula": formula}


def _record(
    fact_code: str, source_ref: str, artifact_format: str, record_type: str,
    authority: str, text: str, fields: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "fact_code": fact_code, "source_ref": source_ref, "artifact_format": artifact_format,
        "record_type": record_type, "authority": authority, "text": text, "fields": fields or [],
    }


def _extract_docx(path: Path) -> list[dict[str, object]]:
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise ArtifactToolError("invalid_docx", "DOCX ZIP integrity check failed.")
            document_xml = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile) as exc:
        raise ArtifactToolError("invalid_docx", "DOCX package cannot be parsed.") from exc
    paragraphs = [_xml_text(fragment, b"w:t") for fragment in re.findall(rb"<w:p(?:\s[^>]*)?>(.*?)</w:p>", document_xml, re.DOTALL)]

    def paragraph(prefix: str) -> str:
        matches = [value for value in paragraphs if value.startswith(prefix)]
        if len(matches) != 1:
            raise ArtifactToolError("invalid_docx", "Expected DOCX anchor is not unique.")
        return matches[0]

    tables = re.findall(rb"<w:tbl(?:\s[^>]*)?>(.*?)</w:tbl>", document_xml, re.DOTALL)
    if len(tables) != 1:
        raise ArtifactToolError("invalid_docx", "Expected exactly one DOCX table.")
    rows = [
        [_xml_text(cell, b"w:t") for cell in re.findall(rb"<w:tc(?:\s[^>]*)?>(.*?)</w:tc>", row, re.DOTALL)]
        for row in re.findall(rb"<w:tr(?:\s[^>]*)?>(.*?)</w:tr>", tables[0], re.DOTALL)
    ]
    if len(rows) != 5 or rows[0] != ["Gate", "Passing criterion", "Evaluation", "Authoritative evidence"]:
        raise ArtifactToolError("invalid_docx", "Eligibility gate table structure changed.")
    return [
        _record(
            "POL-ELIGIBILITY", "supplier-selection-policy.docx#table=Eligibility-gates", "docx", "table", "governing_policy",
            "\n".join(" | ".join(row) for row in rows),
            [_field(row[0], " | ".join(row[1:])) for row in rows[1:]],
        ),
        _record("POL-SELECTION", "supplier-selection-policy.docx#heading=Selection-sequence", "docx", "paragraph", "governing_policy", paragraph("First exclude every ineligible supplier")),
        _record("POL-AUTHORITY", "supplier-selection-policy.docx#heading=Evidence-authority", "docx", "paragraph", "governing_policy", paragraph("The signed-final assurance appendix")),
        _record("POL-CUTOFF", "supplier-selection-policy.docx#heading=Decision-cutoff", "docx", "paragraph", "governing_policy", paragraph("The award decision uses evidence finalized")),
    ]


def _collapse_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _pdf_rows(page: str, status: str) -> list[tuple[str, str, int, str]]:
    pattern = re.compile(r"^\s*(Atlas|Boreal|Cedar|Delta)\s+([A-C])\s+(\d+)\s+" + re.escape(status) + r"\s*$", re.MULTILINE)
    rows = [(supplier, rating, int(findings), status) for supplier, rating, findings in pattern.findall(page)]
    if [row[0] for row in rows] != list(SUPPLIERS):
        raise ArtifactToolError("invalid_pdf", f"Unexpected {status} table rows.")
    return rows


def _row_text(row: tuple[str, str, int, str]) -> str:
    return " | ".join(str(value) for value in row)


def _extract_pdf(path: Path, pdftotext_path: Path | None) -> list[dict[str, object]]:
    if pdftotext_path is None or not pdftotext_path.is_absolute() or not pdftotext_path.is_file():
        raise ArtifactToolError("pdf_backend_unavailable", "Frozen PDF text backend is unavailable.")
    if pdftotext_path.name != "pdftotext":
        raise ArtifactToolError("invalid_pdf_backend", "PDF backend must be pdftotext.")
    try:
        completed = subprocess.run(
            [str(pdftotext_path), "-layout", str(path), "-"], check=True, capture_output=True,
            text=True, timeout=15, env={"LC_ALL": "C", "PATH": os.defpath},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ArtifactToolError("pdf_extraction_failed", "PDF text extraction failed.") from exc
    pages = completed.stdout.rstrip("\f\n").split("\f")
    if len(pages) != 3:
        raise ArtifactToolError("invalid_pdf", "Expected exactly three PDF pages.")
    draft = _pdf_rows(pages[1], "Unsigned draft")
    final = _pdf_rows(pages[2], "Signed final")
    final_note = re.search(
        r"This signed-final appendix supersedes the Unsigned draft on page 2\. It was finalized at "
        r"2026-09-08 14:30 UTC, before the 16:00 UTC decision cutoff\.",
        _collapse_whitespace(pages[2]),
    )
    if final_note is None:
        raise ArtifactToolError("invalid_pdf", "Signed-final authority note is missing.")
    records = [
        _record(
            "ASSUR-DRAFT", "supplier-assurance-review.pdf#page=2&table=Unsigned-draft", "pdf", "table", "unsigned_draft_superseded",
            "\n".join(["Supplier | Assurance rating | Unresolved critical findings | Evidence status"] + [_row_text(row) for row in draft]),
            [_field(row[0], _row_text(row)) for row in draft],
        ),
        _record(
            "ASSUR-FINAL", "supplier-assurance-review.pdf#page=3&note=Signed-final", "pdf", "note", "signed_final_at_cutoff", final_note.group(0),
            [_field("supersedes_page", 2), _field("finalized_at", "2026-09-08 14:30 UTC"), _field("decision_cutoff", "2026-09-08 16:00 UTC")],
        ),
    ]
    for row in final:
        records.append(
            _record(
                f"ASSUR-{row[0].upper()}", f"supplier-assurance-review.pdf#page=3&table=Final-assurance&row={row[0]}",
                "pdf", "row", "signed_final_at_cutoff", _row_text(row),
                [_field("assurance_rating", row[1]), _field("unresolved_critical_findings", row[2]), _field("evidence_status", row[3])],
            )
        )
    return records


def _parse_number(value: str) -> int | float:
    parsed = float(value)
    return int(parsed) if parsed.is_integer() else parsed


def _xlsx_cells(sheet_xml: bytes, shared: list[str]) -> dict[str, dict[str, object]]:
    cells: dict[str, dict[str, object]] = {}
    for match in re.finditer(rb"<c\s+([^>]*?)(?:/>|>(.*?)</c>)", sheet_xml, re.DOTALL):
        attributes, body = match.groups()
        body = body or b""
        reference = re.search(rb'\br="([A-Z]+[0-9]+)"', attributes)
        if reference is None:
            continue
        address = reference.group(1).decode("ascii")
        type_match = re.search(rb'\bt="([^"]+)"', attributes)
        cell_type = type_match.group(1).decode("ascii") if type_match else "n"
        value_match = re.search(rb"<v>(.*?)</v>", body, re.DOTALL)
        formula_match = re.search(rb"<f(?:\s[^>]*)?>(.*?)</f>", body, re.DOTALL)
        raw = html.unescape(value_match.group(1).decode("utf-8")) if value_match else ""
        if cell_type == "s":
            value: object = shared[int(raw)]
        elif cell_type == "str":
            value = raw
        elif cell_type == "inlineStr":
            value = _xml_text(body, b"t")
        elif raw:
            value = _parse_number(raw)
        else:
            value = None
        formula = "=" + html.unescape(formula_match.group(1).decode("utf-8")) if formula_match else None
        cells[address] = {"value": value, "formula": formula}
    return cells


def _extract_xlsx(path: Path) -> list[dict[str, object]]:
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise ArtifactToolError("invalid_xlsx", "XLSX ZIP integrity check failed.")
            shared_xml = archive.read("xl/sharedStrings.xml")
            shared = [_xml_text(fragment, b"t") for fragment in re.findall(rb"<si(?:\s[^>]*)?>(.*?)</si>", shared_xml, re.DOTALL)]
            dashboard = _xlsx_cells(archive.read("xl/worksheets/sheet1.xml"), shared)
            analysis = _xlsx_cells(archive.read("xl/worksheets/sheet2.xml"), shared)
    except (KeyError, zipfile.BadZipFile) as exc:
        raise ArtifactToolError("invalid_xlsx", "XLSX package cannot be parsed.") from exc

    def cell_field(cells: dict[str, dict[str, object]], address: str, name: str):
        cell = cells[address]
        return _field(name, cell["value"], cell["formula"])

    records = []
    for row, supplier in enumerate(SUPPLIERS, start=5):
        if analysis[f"A{row}"]["value"] != supplier:
            raise ArtifactToolError("invalid_xlsx", f"Unexpected Bid Analysis row {row}.")
        fields = [
            cell_field(analysis, f"B{row}", "base_annual_fee_eur"), cell_field(analysis, f"C{row}", "mobilization_eur"),
            cell_field(analysis, f"D{row}", "transition_credit_eur"), cell_field(analysis, f"E{row}", "adjusted_first_year_cost_eur"),
            cell_field(analysis, f"F{row}", "available_units"), cell_field(analysis, f"G{row}", "required_units"),
            cell_field(analysis, f"H{row}", "capacity_headroom"), cell_field(analysis, f"I{row}", "cost_gate"),
            cell_field(analysis, f"J{row}", "capacity_gate"),
        ]
        records.append(
            _record(
                f"BID-{supplier.upper()}", f"bid-evaluation.xlsx#sheet=Bid Analysis&range=B{row}:J{row}",
                "xlsx", "range", "commercial_analysis",
                supplier + "; " + "; ".join(f"{item['name']}={item['value']}" for item in fields), fields,
            )
        )
    recommendation = [cell_field(dashboard, "B3", "recommended_supplier"), cell_field(dashboard, "B4", "lowest_adjusted_first_year_cost_eur"), cell_field(dashboard, "B5", "recommendation_basis")]
    scope = [cell_field(dashboard, "B7", "ranking_scope"), cell_field(dashboard, "B8", "assurance_scope")]
    records.extend([
        _record("DASH-RECOMMENDATION", "bid-evaluation.xlsx#sheet=Dashboard&range=B3:B5", "xlsx", "range", "commercial_dashboard", "; ".join(f"{item['name']}={item['value']}" for item in recommendation), recommendation),
        _record("DASH-SCOPE", "bid-evaluation.xlsx#sheet=Dashboard&range=B7:B8", "xlsx", "range", "commercial_dashboard", "; ".join(f"{item['name']}={item['value']}" for item in scope), scope),
    ])
    return records


def _request_shape(request: Any, keys: set[str]) -> bool:
    return isinstance(request, dict) and set(request) == keys


def _bounded(result: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_RESPONSE_BYTES:
        raise ArtifactToolError("response_too_large", "Artifact response exceeds the byte limit.")
    return result


def execute_artifact_request(workspace: Path, request: Any, *, pdftotext_path: Path | None = None) -> dict[str, Any]:
    root = workspace.resolve()
    if not isinstance(request, dict) or request.get("operation") not in OPERATIONS:
        raise ArtifactToolError("unsupported_operation", "Unsupported artifact operation.")
    operation = request["operation"]
    if operation == "list_artifacts":
        if not _request_shape(request, {"operation"}):
            raise ArtifactToolError("invalid_arguments", "list_artifacts accepts no arguments.")
        verify_workspace(root)
        return _bounded({
            "ok": True, "api_version": API_VERSION, "operation": operation,
            "artifacts": [
                {"filename": filename, "format": definition["format"], "sha256": definition["sha256"], "size_bytes": definition["size_bytes"], "available_queries": definition["queries"]}
                for filename, definition in ARTIFACTS.items()
            ],
        })
    if operation == "read_docx":
        if not _request_shape(request, {"operation", "anchor"}) or not isinstance(request["anchor"], str):
            raise ArtifactToolError("invalid_arguments", "read_docx requires one string anchor.")
        filename = "supplier-selection-policy.docx"
        if {"anchor": request["anchor"]} not in ARTIFACTS[filename]["queries"]:
            raise ArtifactToolError("unknown_anchor", "DOCX anchor is not available.")
        records = _extract_docx(_artifact_path(root, filename))
        source_ref = f"{filename}#{request['anchor']}"
    elif operation == "read_pdf":
        if not _request_shape(request, {"operation", "page", "element"}) or isinstance(request["page"], bool) or not isinstance(request["page"], int) or not isinstance(request["element"], str):
            raise ArtifactToolError("invalid_arguments", "read_pdf requires integer page and string element.")
        filename = "supplier-assurance-review.pdf"
        query = {"page": request["page"], "element": request["element"]}
        if query not in ARTIFACTS[filename]["queries"]:
            raise ArtifactToolError("unknown_anchor", "PDF page element is not available.")
        records = _extract_pdf(_artifact_path(root, filename), pdftotext_path)
        source_ref = f"{filename}#page={request['page']}&{request['element']}"
    else:
        if not _request_shape(request, {"operation", "sheet", "range"}) or not isinstance(request["sheet"], str) or not isinstance(request["range"], str):
            raise ArtifactToolError("invalid_arguments", "read_xlsx requires string sheet and range.")
        filename = "bid-evaluation.xlsx"
        query = {"sheet": request["sheet"], "range": request["range"]}
        if query not in ARTIFACTS[filename]["queries"]:
            raise ArtifactToolError("unknown_anchor", "XLSX range is not available.")
        records = _extract_xlsx(_artifact_path(root, filename))
        source_ref = f"{filename}#sheet={request['sheet']}&range={request['range']}"
    matches = [item for item in records if item["source_ref"] == source_ref]
    if len(matches) != 1:
        raise ArtifactToolError("extraction_identity_mismatch", "Artifact anchor did not resolve uniquely.")
    return _bounded({"ok": True, "api_version": API_VERSION, "operation": operation, "record": matches[0]})


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--pdftotext", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        request = json.loads(sys.stdin.read())
        result = execute_artifact_request(args.workspace, request, pdftotext_path=args.pdftotext)
    except json.JSONDecodeError:
        result = {"ok": False, "error_code": "invalid_json", "reason": "Request must be JSON."}
        status = 2
    except ArtifactToolError as exc:
        result = {"ok": False, "error_code": exc.code, "reason": str(exc)}
        status = 2
    else:
        status = 0
    sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
