"""
AAROGYA — Comprehensive Code Review Package Generator
======================================================
Generates 4 detailed, customized PDF documents (one for each team member)
plus 1 Master Team Code Review Map PDF.

Uses ReportLab with custom NumberedCanvas, professional styling,
flow diagrams, code deconstructions, and honest implementation statuses.
"""

import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, Preformatted
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas for total page count and professional header/footer."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        # Suppress running header on cover page (page 1)
        if self._pageNumber > 1:
            self.setFont("Helvetica", 7.5)
            self.setFillColor(colors.HexColor("#64748B"))
            self.drawString(36, 756, "AAROGYA — Final-Year Project Code Review Package | Confidential Engineering Document")
            self.drawRightString(612 - 36, 756, getattr(self, "doc_subtitle_short", "Technical Reference"))
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(36, 750, 612 - 36, 750)

        # Running Footer on all pages
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))
        self.drawString(36, 22, "AAROGYA Multi-Agent Embodied AI Hospital Platform | National Institute of Technology / Final Year Engineering")
        self.drawRightString(612 - 36, 22, f"Page {self._pageNumber} of {page_count}")
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(36, 32, 612 - 36, 32)
        self.restoreState()


def get_custom_styles():
    base = getSampleStyleSheet()
    styles = {}

    styles["DocTitle"] = ParagraphStyle(
        "DocTitle",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=6,
    )
    styles["DocSubtitle"] = ParagraphStyle(
        "DocSubtitle",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#0284C7"),
        spaceAfter=4,
    )
    styles["DocMeta"] = ParagraphStyle(
        "DocMeta",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#475569"),
        spaceAfter=14,
    )
    styles["SecHeader1"] = ParagraphStyle(
        "SecHeader1",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#0F172A"),
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True,
    )
    styles["SecHeader2"] = ParagraphStyle(
        "SecHeader2",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=13,
        textColor=colors.HexColor("#1E3A8A"),
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True,
    )
    styles["SecHeader3"] = ParagraphStyle(
        "SecHeader3",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=11.5,
        textColor=colors.HexColor("#0369A1"),
        spaceBefore=6,
        spaceAfter=2,
        keepWithNext=True,
    )
    styles["Body"] = ParagraphStyle(
        "Body",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor("#1E293B"),
        spaceAfter=5,
    )
    styles["BodyBold"] = ParagraphStyle(
        "BodyBold",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=5,
    )
    styles["Bullet"] = ParagraphStyle(
        "Bullet",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor("#1E293B"),
        leftIndent=12,
        firstLineIndent=-8,
        spaceAfter=3,
    )
    styles["Callout"] = ParagraphStyle(
        "Callout",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#0F172A"),
    )
    styles["Code"] = ParagraphStyle(
        "Code",
        parent=base["Normal"],
        fontName="Courier",
        fontSize=7,
        leading=8.5,
        textColor=colors.HexColor("#0F172A"),
    )
    styles["TableHead"] = ParagraphStyle(
        "TableHead",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9.5,
        textColor=colors.white,
    )
    styles["TableBody"] = ParagraphStyle(
        "TableBody",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#1E293B"),
    )
    styles["TableBodyBold"] = ParagraphStyle(
        "TableBodyBold",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#0F172A"),
    )
    styles["TableBodyCode"] = ParagraphStyle(
        "TableBodyCode",
        parent=base["Normal"],
        fontName="Courier",
        fontSize=7,
        leading=8.5,
        textColor=colors.HexColor("#0F172A"),
    )
    return styles


def build_callout(text, title="KEY TAKEAWAY", border_color="#0284C7", bg_color="#F0F9FF"):
    styles = get_custom_styles()
    p_title = Paragraph(f"<b>{title}:</b> {text}", styles["Callout"])
    t = Table([[p_title]], colWidths=[540])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(bg_color)),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LINELEFT', (0, 0), (0, -1), 3.5, colors.HexColor(border_color)),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
    ]))
    return t


def build_code_block(code_str, filename=""):
    styles = get_custom_styles()
    title_p = Paragraph(f"<b>SOURCE FILE: {filename}</b>", styles["TableHead"])
    code_p = Preformatted(code_str, styles["Code"])
    t = Table([[title_p], [code_p]], colWidths=[540])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor("#1E293B")),
        ('BACKGROUND', (0, 1), (0, 1), colors.HexColor("#F8FAFC")),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#94A3B8")),
    ]))
    return t


print("Helper modules defined successfully.")
