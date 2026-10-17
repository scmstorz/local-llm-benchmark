#!/usr/bin/env python3
"""Build the synthetic supplier-assurance-review PDF fixture."""

from __future__ import annotations

import argparse
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import BaseDocTemplate, Flowable, Frame, KeepTogether, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle


PAGE_WIDTH, PAGE_HEIGHT = letter
LEFT_MARGIN = RIGHT_MARGIN = 0.75 * inch
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
    def __init__(self, name: str):
        super().__init__()
        self.name = name
        self.width = self.height = 0

    def draw(self) -> None:
        self.canv.bookmarkPage(self.name)


class AssuranceDocTemplate(BaseDocTemplate):
    def afterFlowable(self, flowable) -> None:
        bookmark_name = getattr(flowable, "bookmark_name", None)
        outline_title = getattr(flowable, "outline_title", None)
        if bookmark_name and outline_title:
            self.canv.bookmarkPage(bookmark_name)
            self.canv.addOutlineEntry(outline_title, bookmark_name, level=0, closed=False)


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
    canvas.drawString(LEFT_MARGIN, PAGE_HEIGHT - 0.42 * inch, "SUPPLIER ASSURANCE REVIEW")
    canvas.setFont("Helvetica", 8.2)
    canvas.setFillColor(GRAY)
    canvas.drawRightString(PAGE_WIDTH - RIGHT_MARGIN, PAGE_HEIGHT - 0.42 * inch, "Critical service sourcing")
    canvas.line(LEFT_MARGIN, 0.52 * inch, PAGE_WIDTH - RIGHT_MARGIN, 0.52 * inch)
    canvas.drawString(LEFT_MARGIN, 0.34 * inch, "Synthetic benchmark fixture")
    canvas.drawRightString(PAGE_WIDTH - RIGHT_MARGIN, 0.34 * inch, f"Page {doc.page} of {TOTAL_PAGES}")
    canvas.restoreState()


def styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "kicker": ParagraphStyle("Kicker", parent=sample["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=11, textColor=BLUE, spaceAfter=8, alignment=TA_LEFT),
        "title": ParagraphStyle("Title", parent=sample["Title"], fontName="Helvetica-Bold", fontSize=25, leading=29, textColor=NAVY, spaceAfter=7, alignment=TA_LEFT),
        "subtitle": ParagraphStyle("Subtitle", parent=sample["Normal"], fontName="Helvetica", fontSize=12.5, leading=16, textColor=GRAY, spaceAfter=18),
        "h1": ParagraphStyle("Heading1", parent=sample["Heading1"], fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=NAVY, spaceBefore=2, spaceAfter=9, keepWithNext=True),
        "h2": ParagraphStyle("Heading2", parent=sample["Heading2"], fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=DARK_BLUE, spaceBefore=12, spaceAfter=6, keepWithNext=True),
        "body": ParagraphStyle("Body", parent=sample["BodyText"], fontName="Helvetica", fontSize=10.5, leading=14.5, textColor=BLACK, spaceAfter=8),
        "small": ParagraphStyle("Small", parent=sample["BodyText"], fontName="Helvetica", fontSize=8.7, leading=11.5, textColor=GRAY, spaceAfter=5),
        "caption": ParagraphStyle("Caption", parent=sample["BodyText"], fontName="Helvetica-Oblique", fontSize=8.7, leading=11, textColor=GRAY, spaceBefore=4, spaceAfter=5),
        "table_header": ParagraphStyle("TableHeader", parent=sample["BodyText"], fontName="Helvetica-Bold", fontSize=8.4, leading=10.5, textColor=DARK_BLUE),
        "table_cell": ParagraphStyle("TableCell", parent=sample["BodyText"], fontName="Helvetica", fontSize=8.6, leading=11, textColor=BLACK),
        "callout": ParagraphStyle("Callout", parent=sample["BodyText"], fontName="Helvetica", fontSize=10, leading=14, textColor=BLACK),
        "callout_final": ParagraphStyle("CalloutFinal", parent=sample["BodyText"], fontName="Helvetica-Bold", fontSize=10, leading=14, textColor=GREEN),
    }


def anchored_heading(text: str, style: ParagraphStyle, bookmark: str) -> Paragraph:
    paragraph = Paragraph(text, style)
    paragraph.bookmark_name = bookmark
    paragraph.outline_title = text
    return paragraph


def metadata_table(style_map: dict[str, ParagraphStyle]) -> Table:
    rows = [
        [Paragraph("<b>Report status</b><br/>SIGNED FINAL", style_map["body"]), Paragraph("<b>Decision cutoff</b><br/>2026-09-08 16:00 UTC", style_map["body"])],
        [Paragraph("<b>Signed-final timestamp</b><br/>2026-09-08 14:30 UTC", style_map["body"]), Paragraph("<b>Owner</b><br/>Supplier Assurance", style_map["body"])],
    ]
    table = Table(rows, colWidths=[CONTENT_WIDTH / 2, CONTENT_WIDTH / 2])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY), ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, BORDER), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def callout(text: str, style: ParagraphStyle, *, fill, border) -> Table:
    table = Table([[Paragraph(text, style)]], colWidths=[CONTENT_WIDTH])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), fill), ("BOX", (0, 0), (-1, -1), 0.8, border),
        ("LINEBEFORE", (0, 0), (0, -1), 4, border), ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    return table


def assurance_table(rows: list[tuple[str, str, str, str]], style_map: dict[str, ParagraphStyle], *, final: bool) -> Table:
    headers = ("Supplier", "Assurance rating", "Unresolved critical findings", "Evidence status")
    data = [[Paragraph(value, style_map["table_header"]) for value in headers]]
    data.extend([[Paragraph(value, style_map["table_cell"]) for value in row] for row in rows])
    table = Table(data, colWidths=[86, 104, 142, CONTENT_WIDTH - 332], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GRAY),
        ("BACKGROUND", (0, 1), (-1, -1), WHITE if final else colors.HexColor("#FFFDF7")),
        ("BOX", (0, 0), (-1, -1), 0.65, BORDER), ("INNERGRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 1), (2, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return table


def page_one(style_map: dict[str, ParagraphStyle]) -> list:
    guide = Table([
        [Paragraph("<b>Page 2</b>", style_map["table_cell"]), Paragraph("Unsigned draft retained for traceability. It is not decision evidence.", style_map["table_cell"])],
        [Paragraph("<b>Page 3</b>", style_map["table_cell"]), Paragraph("Signed-final assurance appendix completed before the cutoff. This is authoritative.", style_map["table_cell"])],
    ], colWidths=[70, CONTENT_WIDTH - 70])
    guide.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.55, BORDER), ("INNERGRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GRAY), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return [
        Spacer(1, 20), Paragraph("SIGNED ASSURANCE EVIDENCE", style_map["kicker"]),
        Paragraph("Supplier Assurance Review", style_map["title"]),
        Paragraph("Critical service sourcing - assurance evidence for the 2026-09-08 award decision", style_map["subtitle"]),
        metadata_table(style_map), Spacer(1, 14),
        callout("<b>Authoritative-use rule.</b> The signed-final appendix on page 3 supersedes the unsigned draft on page 2 and was finalized before the decision cutoff.", style_map["callout"], fill=GREEN_LIGHT, border=GREEN),
        Spacer(1, 16), anchored_heading("Purpose and authority", style_map["h1"], "Review-scope"),
        Paragraph("This review records assurance ratings and unresolved critical findings for the four bidding suppliers. The draft remains visible only to test correct evidence precedence.", style_map["body"]),
        Paragraph("How to read the evidence", style_map["h2"]), guide,
        Paragraph("Scope boundary", style_map["h2"]),
        Paragraph("This document reports assurance evidence only. Eligibility and commercial ranking also require the selection policy and bid workbook.", style_map["body"]),
    ]


def page_two(style_map: dict[str, ParagraphStyle]) -> list:
    rows = [("Atlas", "C", "0", "Unsigned draft"), ("Boreal", "A", "0", "Unsigned draft"), ("Cedar", "A", "0", "Unsigned draft"), ("Delta", "B", "0", "Unsigned draft")]
    return [
        Paragraph("UNSIGNED DRAFT - SUPERSEDED", style_map["kicker"]),
        anchored_heading("Unsigned draft", style_map["h1"], "Unsigned-draft-heading"),
        Paragraph("Draft snapshot recorded 2026-09-06 12:00 UTC", style_map["subtitle"]),
        callout("<b>Do not use for award authorization.</b> This appendix was unsigned and was replaced by the signed-final evidence on page 3.", style_map["callout"], fill=AMBER_LIGHT, border=AMBER),
        Spacer(1, 15), Bookmark("Unsigned-draft"),
        Paragraph("Table 1. Unsigned draft assurance - superseded", style_map["caption"]),
        KeepTogether([assurance_table(rows, style_map, final=False), Spacer(1, 8), Paragraph("The unsigned draft lists Cedar with zero unresolved critical findings and Atlas with assurance rating C.", style_map["small"])]),
        Paragraph("Change-control status", style_map["h2"]),
        Paragraph("Superseded. Review completion changed Atlas's rating and identified a Cedar critical finding before the decision cutoff.", style_map["body"]),
        callout("Traceability note: draft values remain visible to test whether an analyst follows signed-final authority instead of selecting favorable stale evidence.", style_map["small"], fill=RED_LIGHT, border=RED),
    ]


def page_three(style_map: dict[str, ParagraphStyle]) -> list:
    rows = [("Atlas", "B", "0", "Signed final"), ("Boreal", "A", "0", "Signed final"), ("Cedar", "A", "1", "Signed final"), ("Delta", "B", "0", "Signed final")]
    changes = Table([
        [Paragraph("Supplier", style_map["table_header"]), Paragraph("Unsigned draft", style_map["table_header"]), Paragraph("Signed final", style_map["table_header"])],
        [Paragraph("Atlas", style_map["table_cell"]), Paragraph("Rating C", style_map["table_cell"]), Paragraph("Rating B", style_map["table_cell"])],
        [Paragraph("Cedar", style_map["table_cell"]), Paragraph("0 critical findings", style_map["table_cell"]), Paragraph("1 critical finding", style_map["table_cell"])],
    ], colWidths=[100, 185, CONTENT_WIDTH - 285])
    changes.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GRAY), ("BOX", (0, 0), (-1, -1), 0.55, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, BORDER), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return [
        Paragraph("SIGNED FINAL BEFORE CUTOFF", style_map["kicker"]),
        anchored_heading("Signed-final assurance", style_map["h1"], "Signed-final-heading"),
        Paragraph("Signed and finalized 2026-09-08 14:30 UTC", style_map["subtitle"]),
        Bookmark("Signed-final"),
        callout("This signed-final appendix supersedes the Unsigned draft on page 2. It was finalized at 2026-09-08 14:30 UTC, before the 16:00 UTC decision cutoff.", style_map["callout_final"], fill=GREEN_LIGHT, border=GREEN),
        Spacer(1, 15), Bookmark("Final-assurance"),
        Paragraph("Table 2. Final assurance", style_map["caption"]), assurance_table(rows, style_map, final=True),
        Paragraph("Evidence status: signed final and authoritative for the award decision.", style_map["small"]),
        Paragraph("Material changes from draft", style_map["h2"]), changes,
        Paragraph("Sign-off", style_map["h2"]),
        Paragraph("Signed by: Assurance Review Board | Finalized: 2026-09-08 14:30 UTC | Decision cutoff: 2026-09-08 16:00 UTC", style_map["body"]),
    ]


def build_pdf(output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    style_map = styles()
    document = AssuranceDocTemplate(
        str(output_path), pagesize=letter, leftMargin=LEFT_MARGIN, rightMargin=RIGHT_MARGIN,
        topMargin=TOP_MARGIN, bottomMargin=BOTTOM_MARGIN, title="Supplier Assurance Review",
        author="Local LLM Benchmark Lab", subject="Synthetic multi-format benchmark fixture",
        creator="ReportLab 5.0.1", keywords="synthetic benchmark, supplier assurance, signed final",
        invariant=1, pageCompression=1,
    )
    frame = Frame(LEFT_MARGIN, BOTTOM_MARGIN, CONTENT_WIDTH, PAGE_HEIGHT - TOP_MARGIN - BOTTOM_MARGIN, id="main", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    document.addPageTemplates([PageTemplate(id="assurance", frames=[frame], onPage=footer_and_header)])
    document.build([*page_one(style_map), PageBreak(), *page_two(style_map), PageBreak(), *page_three(style_map)])


def main() -> None:
    args = parse_args()
    build_pdf(args.output)


if __name__ == "__main__":
    main()
