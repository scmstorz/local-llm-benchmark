#!/usr/bin/env python3
"""Run deterministic structural, formula and cached-value checks for the XLSX fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import zipfile
from pathlib import Path

import openpyxl
from openpyxl import load_workbook


ERROR_VALUES = {"#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NUM!", "#NULL!"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workbook", required=True, type=Path)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assert_close(actual: object, expected: float, address: str) -> None:
    if not isinstance(actual, (int, float)) or not math.isclose(actual, expected, rel_tol=0, abs_tol=1e-12):
        raise AssertionError(f"{address}: expected {expected!r}, found {actual!r}")


def main() -> None:
    args = parse_args()
    workbook_path = args.workbook.resolve()

    with zipfile.ZipFile(workbook_path) as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise AssertionError(f"Corrupt ZIP member: {bad_member}")
        members = set(archive.namelist())
        if any(name.startswith("xl/externalLinks/") for name in members):
            raise AssertionError("Workbook contains an external link")
        if "xl/vbaProject.bin" in members:
            raise AssertionError("Workbook contains a VBA project")

    formula_book = load_workbook(workbook_path, data_only=False)
    value_book = load_workbook(workbook_path, data_only=True)
    if formula_book.sheetnames != ["Summary", "Capacity"]:
        raise AssertionError(f"Unexpected worksheets: {formula_book.sheetnames!r}")
    if any(sheet.sheet_state != "visible" for sheet in formula_book.worksheets):
        raise AssertionError("Every worksheet must be visible")

    expected_formulas = {
        "Summary!B3": '=IF(AND(B4>=$F$4,B5<=$F$5,B6>=$F$6),"GO","HOLD")',
        "Summary!B6": "=SUM(Capacity!B4:B7)/SUM(Capacity!C4:C7)",
        "Summary!F6": "=Capacity!H3",
        "Capacity!D4": "=IFERROR(B4/C4,0)",
        "Capacity!E4": '=IF(D4>=$H$3,"PASS","HOLD")',
        "Capacity!D5": "=IFERROR(B5/C5,0)",
        "Capacity!E5": '=IF(D5>=$H$3,"PASS","HOLD")',
        "Capacity!D6": "=IFERROR(B6/C6,0)",
        "Capacity!E6": '=IF(D6>=$H$3,"PASS","HOLD")',
        "Capacity!D7": "=IFERROR(B7/C7,0)",
        "Capacity!E7": '=IF(D7>=$H$3,"PASS","HOLD")',
    }
    observed_formulas: dict[str, str] = {}
    formula_count = 0
    formula_errors: list[str] = []
    cached_errors: list[str] = []
    for sheet in formula_book.worksheets:
        cached_sheet = value_book[sheet.title]
        for row in sheet.iter_rows():
            for cell in row:
                address = f"{sheet.title}!{cell.coordinate}"
                if cell.data_type == "f":
                    formula_count += 1
                    observed_formulas[address] = cell.value
                    if any(error in str(cell.value) for error in ERROR_VALUES):
                        formula_errors.append(address)
                cached_value = cached_sheet[cell.coordinate].value
                if cached_value in ERROR_VALUES:
                    cached_errors.append(address)

    if observed_formulas != expected_formulas:
        raise AssertionError(
            "Formula mismatch:\n" + json.dumps(observed_formulas, indent=2, sort_keys=True)
        )
    if formula_count != 11:
        raise AssertionError(f"Expected 11 formulas, found {formula_count}")
    if formula_errors or cached_errors:
        raise AssertionError(
            f"Formula errors={formula_errors!r}; cached value errors={cached_errors!r}"
        )

    summary_values = value_book["Summary"]
    if summary_values["B3"].value != "GO":
        raise AssertionError(f"Summary!B3: expected GO, found {summary_values['B3'].value!r}")
    assert_close(summary_values["B4"].value, 0.9625, "Summary!B4")
    assert_close(summary_values["B5"].value, 1.25, "Summary!B5")
    assert_close(summary_values["B6"].value, 617 / 455, "Summary!B6")
    assert_close(summary_values["F6"].value, 1.25, "Summary!F6")

    capacity_formulas = formula_book["Capacity"]
    capacity_values = value_book["Capacity"]
    expected_rows = [
        (4, "North", 137, 108, 137 / 108),
        (5, "Central", 150, 117, 150 / 117),
        (6, "West", 150, 100, 1.5),
        (7, "East", 180, 130, 180 / 130),
    ]
    observed_rows = []
    for row_number, region, support, peak, ratio in expected_rows:
        row_values = [capacity_values.cell(row_number, column).value for column in range(1, 6)]
        if row_values[:3] != [region, support, peak]:
            raise AssertionError(f"Capacity row {row_number}: {row_values!r}")
        assert_close(row_values[3], ratio, f"Capacity!D{row_number}")
        if row_values[4] != "PASS":
            raise AssertionError(f"Capacity!E{row_number}: expected PASS, found {row_values[4]!r}")
        observed_rows.append(
            {
                "range": f"B{row_number}:E{row_number}",
                "region": region,
                "support_capacity": support,
                "projected_peak_load": peak,
                "capacity_ratio": row_values[3],
                "gate_check": row_values[4],
            }
        )

    if capacity_formulas.tables["RegionalCapacityTable"].ref != "A3:E7":
        raise AssertionError("RegionalCapacityTable must cover A3:E7")
    if str(formula_book["Summary"].print_area) != "'Summary'!$A$1:$F$11":
        raise AssertionError(f"Unexpected Summary print area: {formula_book['Summary'].print_area}")
    if str(formula_book["Capacity"].print_area) != "'Capacity'!$A$1:$H$10":
        raise AssertionError(f"Unexpected Capacity print area: {formula_book['Capacity'].print_area}")
    if any(sheet.page_setup.orientation != "landscape" for sheet in formula_book.worksheets):
        raise AssertionError("Every worksheet must render in landscape orientation")

    result = {
        "status": "passed",
        "workbook": str(workbook_path),
        "sha256": sha256_file(workbook_path),
        "size_bytes": workbook_path.stat().st_size,
        "openpyxl_version": openpyxl.__version__,
        "worksheets": formula_book.sheetnames,
        "formula_count": formula_count,
        "formula_error_count": 0,
        "cached_value_error_count": 0,
        "summary_anchor": {
            "range": "B3:B5",
            "portfolio_status": summary_values["B3"].value,
            "average_completion": summary_values["B4"].value,
            "average_open_issues_per_region": summary_values["B5"].value,
        },
        "portfolio_capacity_ratio": summary_values["B6"].value,
        "capacity_rows": observed_rows,
        "formulas": observed_formulas,
        "print_areas": {
            "Summary": str(formula_book["Summary"].print_area),
            "Capacity": str(formula_book["Capacity"].print_area),
        },
        "external_links": 0,
        "vba_projects": 0,
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
