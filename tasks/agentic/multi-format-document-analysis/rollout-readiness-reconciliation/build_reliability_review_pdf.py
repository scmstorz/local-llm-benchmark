#!/usr/bin/env python3
"""Build the synthetic reliability-review PDF fixture."""

from __future__ import annotations

import argparse
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


PAGE_WIDTH, PAGE_HEIGHT = letter
LEFT_MARGIN = 0.75 * inch
RIGHT_MARGIN = 0.75 * inch
TOP_MARGIN = 0.86 * inch
BOTTOM_MARGIN = 0.72 * inch
CONTENT_WIDTH = PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN
TOTAL_PAGES = 3

NAVY = colors.HexColor("#17365D")
BLUE = colors.HexColor("#2E74B5")
DARK_BLUE = colors.HexColor("#1F4D78")
GREEN = colors.HexColor("#2E6B4F")
GREEN_LIGHT = colors.HexColor("#EAF4EF")
AMBER = colors.HexColor("#9A6700")
AMBER_LIGHT = colors.HexColor("#FFF4D6")
RED = colors.HexColor("#9B1C1C")
RED_LIGHT = colors.HexColor("#FDECEC")
GRAY = colors.HexColor("#5F6B76")
LIGHT_GRAY = colors.HexColor("#F2F4F7")
BORDER = colors.HexColor("#B7C9D6")
WHITE = colors.white
BLACK = colors.HexColor("#111111")


class Bookmark(Flowable):
    """Create a stable named PDF destination without visible content."""

    def __init__(self, name: str):
        super().__init__()
        self.name = name
        self.width = 0
        self.height = 0

    def draw(self) -> None:
        self.canv.bookmarkPage(self.name)


class ReviewDocTemplate(BaseDocTemplate):
    def afterFlowable(self, flowable) -> None:
        bookmark_name = getattr(flowable, "bookmark_name", None)
        outline_title = getattr(flowable, "outline_title", None)
        if bookmark_name and outline_title:
            self.canv.bookmarkPage(bookmark_name)
            self.canv.addOutlineEntry(
                outline_title,
                bookmark_name,
                level=0,
                closed=False,
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def footer_and_header(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.55)
    canvas.line(LEFT_MARGIN, PAGE_HEIGHT - 0.55 * inch, PAGE_WIDTH - RIGHT_MARGIN, PAGE_HEIGHT - 0.55 * inch)
    canvas.setFont("Helvetica-Bold", 8.2)
    canvas.setFillColor(NAVY)
    canvas.drawString(LEFT_MARGIN, PAGE_HEIGHT - 0.42 * inch, "REGIONAL RELIABILITY REVIEW")
    canvas.setFont("Helvetica", 8.2)
    canvas.setFillColor(GRAY)
    canvas.drawRightString(
        PAGE_WIDTH - RIGHT_MARGIN,
        PAGE_HEIGHT - 0.42 * inch,
        "Atlas regional launch",
    )

    canvas.setStrokeColor(BORDER)
    canvas.line(LEFT_MARGIN, 0.52 * inch, PAGE_WIDTH - RIGHT_MARGIN, 0.52 * inch)
    canvas.setFont("Helvetica", 8.2)
    canvas.setFillColor(GRAY)
    canvas.drawString(LEFT_MARGIN, 0.34 * inch, "Synthetic benchmark fixture")
    canvas.drawRightString(
        PAGE_WIDTH - RIGHT_MARGIN,
        0.34 * inch,
        f"Page {doc.page} of {TOTAL_PAGES}",
    )
    canvas.restoreState()


def styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "kicker": ParagraphStyle(
            "Kicker",
            parent=sample["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=11,
            textColor=BLUE,
            spaceAfter=8,
            alignment=TA_LEFT,
        ),
        "title": ParagraphStyle(
            "Title",
            parent=sample["Title"],
            fontName="Helvetica-Bold",
            fontSize=25,
            leading=29,
            textColor=NAVY,
            spaceBefore=0,
            spaceAfter=7,
            alignment=TA_LEFT,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=sample["Normal"],
            fontName="Helvetica",
            fontSize=12.5,
            leading=16,
            textColor=GRAY,
            spaceAfter=18,
        ),
        "h1": ParagraphStyle(
            "Heading1",
            parent=sample["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=NAVY,
            spaceBefore=2,
            spaceAfter=9,
            keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "Heading2",
            parent=sample["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=DARK_BLUE,
            spaceBefore=12,
            spaceAfter=6,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=14.5,
            textColor=BLACK,
            spaceAfter=8,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=8.7,
            leading=11.5,
            textColor=GRAY,
            spaceAfter=5,
        ),
        "caption": ParagraphStyle(
            "Caption",
            parent=sample["BodyText"],
            fontName="Helvetica-Oblique",
            fontSize=8.7,
            leading=11,
            textColor=GRAY,
            spaceBefore=4,
            spaceAfter=5,
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8.4,
            leading=10.5,
            textColor=DARK_BLUE,
        ),
        "table_cell": ParagraphStyle(
            "TableCell",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=8.6,
            leading=11,
            textColor=BLACK,
        ),
        "callout": ParagraphStyle(
            "Callout",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=BLACK,
        ),
        "callout_final": ParagraphStyle(
            "CalloutFinal",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=GREEN,
        ),
    }


def anchored_heading(text: str, style: ParagraphStyle, bookmark: str) -> Paragraph:
    paragraph = Paragraph(text, style)
    paragraph.bookmark_name = bookmark
    paragraph.outline_title = text
    return paragraph


def metadata_table(style_map: dict[str, ParagraphStyle]) -> Table:
    data = [
        [
            Paragraph("<b>Report status</b><br/>FINAL", style_map["body"]),
            Paragraph("<b>Evidence cutoff</b><br/>2026-08-31 18:00 UTC", style_map["body"]),
        ],
        [
            Paragraph("<b>Owner</b><br/>Reliability Engineering", style_map["body"]),
            Paragraph("<b>Decision scope</b><br/>Regional validation evidence", style_map["body"]),
        ],
    ]
    table = Table(data, colWidths=[CONTENT_WIDTH / 2, CONTENT_WIDTH / 2])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
                ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def callout(text: str, style: ParagraphStyle, *, fill, border) -> Table:
    table = Table([[Paragraph(text, style)]], colWidths=[CONTENT_WIDTH])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), fill),
                ("BOX", (0, 0), (-1, -1), 0.8, border),
                ("LINEBEFORE", (0, 0), (0, -1), 4, border),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    return table


def evidence_table(
    rows: list[tuple[str, str, str, str, str]],
    style_map: dict[str, ParagraphStyle],
    *,
    final: bool,
) -> Table:
    headers = (
        "Region",
        "Completion",
        "Open Sev-1",
        "Open Sev-2",
        "Evidence status",
    )
    data = [
        [Paragraph(value, style_map["table_header"]) for value in headers]
    ]
    for row in rows:
        data.append(
            [Paragraph(value, style_map["table_cell"]) for value in row]
        )
    table = Table(
        data,
        colWidths=[82, 82, 72, 72, CONTENT_WIDTH - 308],
        repeatRows=1,
        hAlign="LEFT",
    )
    body_fill = WHITE if final else colors.HexColor("#FFFDF7")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GRAY),
                ("BACKGROUND", (0, 1), (-1, -1), body_fill),
                ("BOX", (0, 0), (-1, -1), 0.65, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 1), (3, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def page_one(style_map: dict[str, ParagraphStyle]) -> list:
    reading_rows = [
        [
            Paragraph("<b>Page 2</b>", style_map["table_cell"]),
            Paragraph(
                "Preliminary validation retained only to show evidence evolution. It is superseded and must not drive the decision.",
                style_map["table_cell"],
            ),
        ],
        [
            Paragraph("<b>Page 3</b>", style_map["table_cell"]),
            Paragraph(
                "Final validation evidence at the cutoff. This is the authoritative reliability source for the rollout decision.",
                style_map["table_cell"],
            ),
        ],
    ]
    reading_table = Table(reading_rows, colWidths=[70, CONTENT_WIDTH - 70])
    reading_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.55, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, BORDER),
                ("BACKGROUND", (0, 0), (0, -1), LIGHT_GRAY),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return [
        Spacer(1, 20),
        Paragraph("FINAL RELIABILITY EVIDENCE", style_map["kicker"]),
        Paragraph("Regional Reliability Review", style_map["title"]),
        Paragraph(
            "Atlas service rollout - validation evidence through 2026-08-31 18:00 UTC",
            style_map["subtitle"],
        ),
        metadata_table(style_map),
        Spacer(1, 14),
        callout(
            "<b>Authoritative-use rule.</b> The final table on page 3 supersedes the preliminary table on page 2 and is the only reliability evidence finalized at the decision cutoff.",
            style_map["callout"],
            fill=GREEN_LIGHT,
            border=GREEN,
        ),
        Spacer(1, 16),
        anchored_heading("Purpose and authority", style_map["h1"], "Review-scope"),
        Paragraph(
            "This review records regional completion and open severity counts for the Atlas rollout. It preserves the preliminary snapshot for traceability while identifying the final evidence that governs the cutoff review.",
            style_map["body"],
        ),
        Paragraph("How to read the evidence", style_map["h2"]),
        reading_table,
        Paragraph("Scope boundary", style_map["h2"]),
        Paragraph(
            "This document reports reliability validation only. The rollout policy and regional capacity workbook remain separate, mutually necessary sources for the final launch decision.",
            style_map["body"],
        ),
    ]


def page_two(style_map: dict[str, ParagraphStyle]) -> list:
    preliminary_rows = [
        ("North", "97%", "0", "1", "Preliminary"),
        ("Central", "96%", "0", "2", "Preliminary"),
        ("West", "94%", "0", "0", "Preliminary"),
        ("East", "98%", "0", "0", "Preliminary"),
    ]
    return [
        Paragraph("PRELIMINARY - SUPERSEDED", style_map["kicker"]),
        anchored_heading(
            "Preliminary validation",
            style_map["h1"],
            "Preliminary-validation-heading",
        ),
        Paragraph(
            "Snapshot recorded 2026-08-29 18:00 UTC",
            style_map["subtitle"],
        ),
        callout(
            "<b>Do not use for rollout authorization.</b> This snapshot was replaced by the final evidence on page 3 and is retained only to document evidence evolution.",
            style_map["callout"],
            fill=AMBER_LIGHT,
            border=AMBER,
        ),
        Spacer(1, 15),
        Bookmark("Preliminary-validation"),
        Paragraph(
            "Table 1. Preliminary validation - superseded",
            style_map["caption"],
        ),
        KeepTogether(
            [
                evidence_table(preliminary_rows, style_map, final=False),
                Spacer(1, 8),
                Paragraph(
                    "At this preliminary snapshot, Central had two open Sev-2 issues and East had zero open Sev-1 issues.",
                    style_map["small"],
                ),
            ]
        ),
        Paragraph("Change-control status", style_map["h2"]),
        Paragraph(
            "Superseded. Subsequent validation changed the Central and East issue counts before the decision cutoff. Page 3 records those final values.",
            style_map["body"],
        ),
        callout(
            "Traceability note: preliminary values remain visible to test whether an analyst follows source authority instead of selecting the most favorable table.",
            style_map["small"],
            fill=RED_LIGHT,
            border=RED,
        ),
    ]


def page_three(style_map: dict[str, ParagraphStyle]) -> list:
    final_rows = [
        ("North", "97%", "0", "1", "Final at cutoff"),
        ("Central", "96%", "0", "3", "Final at cutoff"),
        ("West", "94%", "0", "0", "Final at cutoff"),
        ("East", "98%", "1", "0", "Final at cutoff"),
    ]
    changes = Table(
        [
            [
                Paragraph("Region", style_map["table_header"]),
                Paragraph("Preliminary", style_map["table_header"]),
                Paragraph("Final at cutoff", style_map["table_header"]),
            ],
            [
                Paragraph("Central", style_map["table_cell"]),
                Paragraph("2 open Sev-2", style_map["table_cell"]),
                Paragraph("3 open Sev-2", style_map["table_cell"]),
            ],
            [
                Paragraph("East", style_map["table_cell"]),
                Paragraph("0 open Sev-1", style_map["table_cell"]),
                Paragraph("1 open Sev-1", style_map["table_cell"]),
            ],
        ],
        colWidths=[100, 185, CONTENT_WIDTH - 285],
    )
    changes.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GRAY),
                ("BOX", (0, 0), (-1, -1), 0.55, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return [
        Paragraph("FINAL EVIDENCE AT CUTOFF", style_map["kicker"]),
        anchored_heading(
            "Final validation",
            style_map["h1"],
            "Final-validation-heading",
        ),
        Paragraph(
            "Evidence finalized 2026-08-31 18:00 UTC",
            style_map["subtitle"],
        ),
        Bookmark("Final-table"),
        callout(
            "This final table supersedes the Preliminary validation table on page 2. It is the only reliability evidence finalized at the decision cutoff, 2026-08-31 18:00 UTC.",
            style_map["callout_final"],
            fill=GREEN_LIGHT,
            border=GREEN,
        ),
        Spacer(1, 15),
        Bookmark("Final-validation"),
        Paragraph("Table 2. Final validation", style_map["caption"]),
        evidence_table(final_rows, style_map, final=True),
        Paragraph(
            "Evidence status: authoritative for reliability validation at the cutoff.",
            style_map["small"],
        ),
        Paragraph("Material changes from preliminary", style_map["h2"]),
        changes,
        Paragraph("Evidence cutoff", style_map["h2"]),
        Paragraph(
            "Use the final values above for the 2026-08-31 18:00 UTC decision cycle. Later observations belong to a new review and do not alter this frozen evidence set.",
            style_map["body"],
        ),
    ]


def build_pdf(output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    style_map = styles()
    document = ReviewDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=LEFT_MARGIN,
        rightMargin=RIGHT_MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN,
        title="Regional Reliability Review",
        author="Local LLM Benchmark Lab",
        subject="Synthetic multi-format benchmark fixture",
        creator="ReportLab 5.0.1",
        keywords="synthetic benchmark, reliability review, regional validation",
        invariant=1,
        pageCompression=1,
    )
    frame = Frame(
        LEFT_MARGIN,
        BOTTOM_MARGIN,
        CONTENT_WIDTH,
        PAGE_HEIGHT - TOP_MARGIN - BOTTOM_MARGIN,
        id="main",
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )
    document.addPageTemplates(
        [PageTemplate(id="review", frames=[frame], onPage=footer_and_header)]
    )
    story = [
        *page_one(style_map),
        PageBreak(),
        *page_two(style_map),
        PageBreak(),
        *page_three(style_map),
    ]
    document.build(story)


def main() -> None:
    args = parse_args()
    build_pdf(args.output)


if __name__ == "__main__":
    main()
