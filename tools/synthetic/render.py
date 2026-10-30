"""Draw a generated document as a one-page PDF with a real text layer (the "clean_pdf" form).

Every string that appears in the answer key (`Doc.printed`, `Doc.line_printed`) is drawn
as one piece of text, so the key can be checked against the PDF text layer. Six renderer kinds
give the families different structures. Every page carries the footer "SYNTHETIC TEST DATA".
"""

from __future__ import annotations

import io
from collections.abc import Callable

from reportlab.lib.pagesizes import A4, landscape, letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from tools.synthetic.facts import Facts
from tools.synthetic.families import Family
from tools.synthetic.model import Doc

FOOTER = "SYNTHETIC TEST DATA"
_ROLL_WIDTH = 226.0  # 80 mm
_registered = False


def _register_fonts() -> None:
    global _registered
    if not _registered:
        pdfmetrics.registerFont(TTFont("Vera", "Vera.ttf"))
        pdfmetrics.registerFont(TTFont("Vera-Bold", "VeraBd.ttf"))
        _registered = True


def _bold(font: str) -> str:
    return {
        "Helvetica": "Helvetica-Bold",
        "Times-Roman": "Times-Bold",
        "Courier": "Courier-Bold",
    }.get(font, f"{font}-Bold")


def business_block(facts: Facts) -> list[str]:
    """The bill-to address lines printed on every invoice."""
    b = facts.business
    return [
        b.name,
        b.address.street,
        f"{b.address.city}, {b.address.state} {b.address.zip}",
        f"Tel {b.phone}",
    ]


class Pen:
    """Small drawing helper: text that shrinks to fit, rules, boxes, and a moving baseline."""

    def __init__(self, canvas: Canvas, family: Family) -> None:
        self.c = canvas
        self.font = family.font
        self.accent = family.accent

    def text(
        self,
        x: float,
        y: float,
        value: str,
        size: float = 9,
        *,
        bold: bool = False,
        align: str = "l",
        max_width: float | None = None,
        color: tuple[float, float, float] | None = None,
    ) -> None:
        font = _bold(self.font) if bold else self.font
        if max_width is not None:
            while size > 5 and pdfmetrics.stringWidth(value, font, size) > max_width:
                size -= 0.5
        self.c.setFont(font, size)
        self.c.setFillColorRGB(*(color or (0, 0, 0)))
        if align == "r":
            self.c.drawRightString(x, y, value)
        elif align == "c":
            self.c.drawCentredString(x, y, value)
        else:
            self.c.drawString(x, y, value)
        self.c.setFillColorRGB(0, 0, 0)

    def rule(
        self, x1: float, y: float, x2: float, width: float = 0.6, accent: bool = False
    ) -> None:
        self.c.setStrokeColorRGB(*(self.accent if accent else (0.3, 0.3, 0.3)))
        self.c.setLineWidth(width)
        self.c.line(x1, y, x2, y)

    def box(self, x: float, y: float, w: float, h: float, fill: bool = False) -> None:
        self.c.setStrokeColorRGB(*self.accent)
        if fill:
            self.c.setFillColorRGB(*self.accent)
        self.c.setLineWidth(0.8)
        self.c.rect(x, y, w, h, stroke=1, fill=1 if fill else 0)
        self.c.setFillColorRGB(0, 0, 0)

    def shade(self, x: float, y: float, w: float, h: float, gray: float = 0.93) -> None:
        self.c.setFillColorRGB(gray, gray, gray)
        self.c.rect(x, y, w, h, stroke=0, fill=1)
        self.c.setFillColorRGB(0, 0, 0)


def _vendor_lines(doc: Doc) -> list[str]:
    v = doc.vendor
    a = v.address
    if a.country != "United States":
        lines = [a.street, f"{a.zip} {a.city}", a.country]
    else:
        lines = [a.street, f"{a.city}, {a.state} {a.zip}"]
    lines.append(f"Tel {v.phone}")
    if v.email:
        lines.append(v.email)
    return lines


def _title(doc: Doc, family: Family) -> str:
    return family.labels[doc.entry_type]


def _meta(doc: Doc, family: Family) -> list[tuple[str, str]]:
    labels = family.labels
    rows: list[tuple[str, str]] = []
    if "invoice_number" in doc.printed:
        rows.append((labels["number"], doc.printed["invoice_number"]))
    rows.append((labels["date"], doc.printed["entry_date"]))
    if "due_date" in doc.printed:
        rows.append((labels["due"], doc.printed["due_date"]))
    if "po_number" in doc.printed:
        rows.append((labels["po"], doc.printed["po_number"]))
    return rows


def _totals(doc: Doc, family: Family) -> list[tuple[str, str, bool]]:
    labels = family.labels
    p = doc.printed
    rows: list[tuple[str, str, bool]] = []
    if "subtotal" in p:
        rows.append((labels["subtotal"], p["subtotal"], False))
    if "discount" in p:
        rows.append((labels["discount"], p["discount"], False))
    if "shipping" in p:
        rows.append((labels["shipping"], p["shipping"], False))
    if "tax_total" in p and doc.style.tax_mode != "per_line":
        tax_label = labels["tax"] + (f" ({p['tax_rate']})" if "tax_rate" in p else "")
        rows.append((tax_label, p["tax_total"], False))
    elif "tax_total" in p:
        tax_label = labels["tax"] + " total" + (f" ({p['tax_rate']})" if "tax_rate" in p else "")
        rows.append((tax_label, p["tax_total"], False))
    total_label = labels["credit_total"] if doc.entry_type == "credit_note" else labels["total"]
    rows.append((total_label, p["total"], True))
    return rows


def _notes(doc: Doc) -> list[str]:
    notes = list(doc.notes)
    if doc.entry_type == "invoice" and doc.vendor.terms_days:
        notes.insert(0, f"Payment terms: net {doc.vendor.terms_days} days.")
    notes.append("Thank you for your business.")
    return notes


def _column_titles(family: Family) -> dict[str, str]:
    labels = family.labels
    return {
        "description": labels["description"],
        "qty": labels["qty"],
        "unit_price": labels["unit_price"],
        "amount": labels["amount"],
        "line_tax": labels["line_tax"],
    }


def _page_size(family: Family) -> tuple[float, float]:
    if family.page == "a4":
        return (float(A4[0]), float(A4[1]))
    if family.page == "landscape":
        wide = landscape(letter)
        return (float(wide[0]), float(wide[1]))
    return (float(letter[0]), float(letter[1]))


def _logo(pen: Pen, doc: Doc, x: float, y: float, size: float = 34) -> None:
    pen.box(x, y, size, size, fill=True)
    initials = "".join(w[0] for w in doc.vendor.name.split()[:2]).upper()
    pen.text(x + size / 2, y + size / 2 - 5, initials, 14, bold=True, align="c", color=(1, 1, 1))


def _header(pen: Pen, doc: Doc, family: Family, width: float, top: float) -> float:
    """Draw the vendor block, title and meta rows. Returns the y below the header."""
    margin = 42.0
    vendor_lines = _vendor_lines(doc)
    meta = _meta(doc, family)
    title = _title(doc, family)
    if family.header == "banner":
        pen.shade(0, top - 58, width, 58, 0.88)
        pen.text(
            margin, top - 28, doc.vendor_name, 18, bold=True, max_width=width - 2 * margin - 160
        )
        pen.text(width - margin, top - 28, title, 20, bold=True, align="r", color=pen.accent)
        pen.text(margin, top - 46, " | ".join(vendor_lines), 8, max_width=width - 2 * margin)
        y = top - 78
        for label, value in meta:
            pen.text(margin, y, f"{label}:", 9, bold=True)
            pen.text(margin + 110, y, value, 9)
            y -= 13
        return y - 6
    if family.header == "two_col":
        _logo(pen, doc, margin, top - 40)
        pen.text(margin + 46, top - 20, doc.vendor_name, 15, bold=True, max_width=width / 2 - 70)
        for i, line in enumerate(vendor_lines):
            pen.text(margin + 46, top - 34 - i * 10, line, 8, max_width=width / 2 - 60)
        pen.text(width - margin, top - 20, title, 20, bold=True, align="r", color=pen.accent)
        y = top - 40
        for label, value in meta:
            pen.text(width - margin - 130, y, f"{label}", 9, bold=True)
            pen.text(width - margin, y, value, 9, align="r")
            y -= 13
        return min(y, top - 34 - len(vendor_lines) * 10) - 14
    if family.header == "centered":
        center = width / 2
        pen.text(
            center,
            top - 24,
            doc.vendor_name,
            14,
            bold=True,
            align="c",
            max_width=width - 2 * margin,
        )
        y = top - 40
        for line in vendor_lines:
            pen.text(center, y, line, 9, align="c", max_width=width - 2 * margin)
            y -= 11
        y -= 6
        pen.text(center, y, title, 12, bold=True, align="c")
        y -= 16
        for label, value in meta:
            pen.text(center, y, f"{label}: {value}", 9, align="c", max_width=width - 2 * margin)
            y -= 12
        return y - 6
    if family.header == "boxed":
        height = 20 + max(len(vendor_lines) * 11, len(meta) * 14)
        pen.box(margin, top - height - 10, width - 2 * margin, height)
        pen.text(margin + 8, top - 24, doc.vendor_name, 13, bold=True, max_width=width / 2)
        for i, line in enumerate(vendor_lines):
            pen.text(margin + 8, top - 38 - i * 11, line, 8, max_width=width / 2 - 20)
        pen.text(width - margin - 8, top - 24, title, 15, bold=True, align="r", color=pen.accent)
        y = top - 40
        for label, value in meta:
            pen.text(width - margin - 150, y, f"{label}", 9, bold=True)
            pen.text(width - margin - 8, y, value, 9, align="r")
            y -= 13
        return top - height - 30
    # left
    _logo(pen, doc, margin, top - 44)
    pen.text(
        margin + 46, top - 26, doc.vendor_name, 16, bold=True, max_width=width - 2 * margin - 200
    )
    for i, line in enumerate(vendor_lines):
        pen.text(margin + 46, top - 40 - i * 10, line, 8)
    pen.text(width - margin, top - 26, title, 22, bold=True, align="r", color=pen.accent)
    y = top - 46
    for label, value in meta:
        pen.text(width - margin - 120, y, f"{label}:", 9, bold=True)
        pen.text(width - margin, y, value, 9, align="r")
        y -= 13
    return min(y, top - 40 - len(vendor_lines) * 10) - 16


def _draw_table(pen: Pen, doc: Doc, family: Family, left: float, right: float, y: float) -> float:
    columns = family.columns
    titles = _column_titles(family)
    span = right - left
    fractions = {
        "description": 0.46,
        "qty": 0.09,
        "unit_price": 0.17,
        "line_tax": 0.12,
        "amount": 0.16,
    }
    present = [c for c in columns]
    total = sum(fractions[c] for c in present)
    widths = {c: span * fractions[c] / total for c in present}
    x_edges: dict[str, float] = {}
    cursor = left
    for c in present:
        x_edges[c] = cursor
        cursor += widths[c]
    row_h = 15.0

    def cell(c: str, value: str, yy: float, bold: bool = False) -> None:
        if c == "description":
            pen.text(x_edges[c] + 4, yy, value, 9, bold=bold, max_width=widths[c] - 8)
        else:
            pen.text(
                x_edges[c] + widths[c] - 4,
                yy,
                value,
                9,
                bold=bold,
                align="r",
                max_width=widths[c] - 8,
            )

    pen.shade(left, y - 4, span, row_h, 0.85) if family.table in {"grid", "zebra"} else None
    for c in present:
        cell(c, titles[c], y, bold=True)
    pen.rule(left, y - 6, right, 0.8, accent=True)
    y -= row_h
    for i, row in enumerate(doc.line_printed):
        if family.table == "zebra" and i % 2 == 1:
            pen.shade(left, y - 4, span, row_h, 0.95)
        values = {
            "description": row["description"],
            "qty": row["quantity"],
            "unit_price": row["unit_price"],
            "amount": row["amount"],
            "line_tax": row.get("tax", ""),
        }
        for c in present:
            cell(c, values[c], y)
        if family.table in {"grid", "ruled"}:
            pen.rule(left, y - 5, right, 0.3)
        y -= row_h
    if family.table == "grid":
        pen.box(left, y + row_h - 6, span, (len(doc.line_printed) + 1) * row_h)
    return y - 6


def _draw_totals(
    pen: Pen, doc: Doc, family: Family, right: float, y: float, label_x: float
) -> float:
    for label, value, strong in _totals(doc, family):
        if strong:
            pen.rule(label_x, y + 11, right, 0.8)
        pen.text(label_x, y, label, 10 if strong else 9, bold=strong)
        pen.text(right, y, value, 10 if strong else 9, bold=strong, align="r")
        y -= 14
    return y


def _render_table(c: Canvas, doc: Doc, family: Family, business: list[str]) -> None:
    width, height = _page_size(family)
    pen = Pen(c, family)
    margin = 42.0
    y = _header(pen, doc, family, width, height - 30)
    pen.text(margin, y, family.labels["bill_to"], 8, bold=True, color=pen.accent)
    for i, line in enumerate(business):
        pen.text(margin, y - 12 - i * 11, line, 9, bold=(i == 0))
    y -= 14 + len(business) * 11 + 14
    y = _draw_table(pen, doc, family, margin, width - margin, y)
    y = _draw_totals(pen, doc, family, width - margin, y - 4, width - margin - 190)
    y -= 12
    for note in _notes(doc):
        pen.text(margin, y, note, 8, max_width=width - 2 * margin)
        y -= 11


def _render_roll(c: Canvas, doc: Doc, family: Family, business: list[str]) -> None:
    width = _ROLL_WIDTH
    pen = Pen(c, family)
    x0, x1 = 8.0, width - 8.0
    y = c._pagesize[1] - 20
    pen.text(width / 2, y, doc.vendor_name, 10, bold=True, align="c", max_width=width - 16)
    y -= 12
    for line in _vendor_lines(doc):
        pen.text(width / 2, y, line, 7, align="c", max_width=width - 16)
        y -= 9
    y -= 4
    pen.text(width / 2, y, _title(doc, family), 8, bold=True, align="c")
    y -= 11
    for label, value in _meta(doc, family):
        pen.text(x0, y, f"{label}: {value}", 7, max_width=width - 16)
        y -= 9
    y -= 3
    pen.text(x0, y, "-" * 44, 7)
    y -= 10
    for row in doc.line_printed:
        pen.text(x0, y, row["description"], 7, max_width=width - 16)
        y -= 9
        pen.text(x0 + 6, y, f"{row['quantity']} x {row['unit_price']}", 7, max_width=120)
        pen.text(x1, y, row["amount"], 7, align="r")
        y -= 10
    pen.text(x0, y, "-" * 44, 7)
    y -= 11
    for label, value, strong in _totals(doc, family):
        pen.text(x0, y, label, 8 if strong else 7, bold=strong)
        pen.text(x1, y, value, 8 if strong else 7, bold=strong, align="r")
        y -= 11
    y -= 4
    for note in _notes(doc):
        pen.text(width / 2, y, note, 6, align="c", max_width=width - 16)
        y -= 8


def _render_stacked(c: Canvas, doc: Doc, family: Family, business: list[str]) -> None:
    width, height = _page_size(family)
    pen = Pen(c, family)
    margin = 48.0
    y = _header(pen, doc, family, width, height - 30)
    pen.text(margin, y, family.labels["bill_to"], 8, bold=True, color=pen.accent)
    for i, line in enumerate(business):
        pen.text(margin, y - 12 - i * 11, line, 9, bold=(i == 0))
    y -= 14 + len(business) * 11 + 16
    pen.text(margin, y, "Current charges", 11, bold=True)
    pen.rule(margin, y - 4, width - margin, 0.8, accent=True)
    y -= 20
    for row in doc.line_printed:
        pen.text(margin, y, row["description"], 10, max_width=width - 2 * margin - 200)
        pen.text(
            margin + 270, y, f"{row['quantity']} @ {row['unit_price']}", 8, color=(0.35, 0.35, 0.35)
        )
        pen.text(width - margin, y, row["amount"], 10, align="r")
        y -= 17
    y -= 6
    y = _draw_totals(pen, doc, family, width - margin, y, width - margin - 210)
    y -= 14
    for note in _notes(doc):
        pen.text(margin, y, note, 8, max_width=width - 2 * margin)
        y -= 11


def _render_sidebar(c: Canvas, doc: Doc, family: Family, business: list[str]) -> None:
    width, height = _page_size(family)
    pen = Pen(c, family)
    side = 150.0
    pen.shade(0, 0, side, height, 0.92)
    _logo(pen, doc, 16, height - 60)
    pen.text(16, height - 78, doc.vendor_name, 10, bold=True, max_width=side - 28)
    y = height - 94
    for line in _vendor_lines(doc):
        pen.text(16, y, line, 7, max_width=side - 24)
        y -= 10
    y -= 14
    pen.text(16, y, family.labels["bill_to"], 8, bold=True, color=pen.accent)
    y -= 12
    for line in business:
        pen.text(16, y, line, 8, max_width=side - 24)
        y -= 10
    y -= 14
    for label, value in _meta(doc, family):
        pen.text(16, y, label, 7, bold=True)
        y -= 10
        pen.text(16, y, value, 8, max_width=side - 24)
        y -= 14
    left, right = side + 24, width - 36
    pen.text(left, height - 50, _title(doc, family), 24, bold=True, color=pen.accent)
    y = _draw_table(pen, doc, family, left, right, height - 100)
    y = _draw_totals(pen, doc, family, right, y - 4, right - 170)
    y -= 12
    for note in _notes(doc):
        pen.text(left, y, note, 8, max_width=right - left)
        y -= 11


def _render_statement(c: Canvas, doc: Doc, family: Family, business: list[str]) -> None:
    width, height = _page_size(family)
    pen = Pen(c, family)
    margin = 48.0
    pen.text(
        margin, height - 48, doc.vendor_name, 17, bold=True, max_width=width - 2 * margin - 160
    )
    pen.text(
        width - margin, height - 48, _title(doc, family), 14, bold=True, align="r", color=pen.accent
    )
    y = height - 62
    for line in _vendor_lines(doc):
        pen.text(margin, y, line, 8)
        y -= 10
    box_top = height - 70
    pen.box(width - margin - 200, box_top - 70, 200, 70)
    pen.text(width - margin - 190, box_top - 16, family.labels["total"], 8, bold=True)
    pen.text(width - margin - 8, box_top - 40, doc.printed["total"], 18, bold=True, align="r")
    if "due_date" in doc.printed:
        pen.text(
            width - margin - 190,
            box_top - 58,
            f"{family.labels['due']}: {doc.printed['due_date']}",
            8,
        )
    y = min(y, box_top - 70) - 22
    for label, value in _meta(doc, family):
        pen.text(margin, y, f"{label}:", 9, bold=True)
        pen.text(margin + 120, y, value, 9)
        y -= 13
    y -= 4
    pen.text(margin, y, family.labels["bill_to"], 8, bold=True, color=pen.accent)
    for i, line in enumerate(business):
        pen.text(margin, y - 12 - i * 11, line, 9, bold=(i == 0))
    y -= 14 + len(business) * 11 + 12
    y = _draw_table(pen, doc, family, margin, width - margin, y)
    y = _draw_totals(pen, doc, family, width - margin, y - 4, width - margin - 200)
    y -= 12
    for note in _notes(doc):
        pen.text(margin, y, note, 8, max_width=width - 2 * margin)
        y -= 11


def _render_pos_page(c: Canvas, doc: Doc, family: Family, business: list[str]) -> None:
    width, height = _page_size(family)
    pen = Pen(c, family)
    center = width / 2
    y = height - 80
    pen.text(center, y, doc.vendor_name, 20, bold=True, align="c", max_width=width - 100)
    y -= 22
    for line in _vendor_lines(doc):
        pen.text(center, y, line, 11, align="c")
        y -= 14
    y -= 14
    for label, value in _meta(doc, family):
        pen.text(center, y, f"{label}: {value}", 11, align="c")
        y -= 15
    y -= 16
    left, right = center - 190, center + 190
    for row in doc.line_printed:
        pen.text(left, y, row["description"], 12, max_width=250)
        pen.text(right, y, row["amount"], 12, align="r")
        y -= 15
        pen.text(
            left + 12, y, f"{row['quantity']} @ {row['unit_price']}", 9, color=(0.35, 0.35, 0.35)
        )
        y -= 18
    pen.rule(left, y + 8, right, 0.8)
    y -= 8
    for label, value, strong in _totals(doc, family):
        pen.text(left, y, label, 14 if strong else 11, bold=strong)
        pen.text(right, y, value, 14 if strong else 11, bold=strong, align="r")
        y -= 20
    y -= 10
    for note in _notes(doc):
        pen.text(center, y, note, 9, align="c", max_width=width - 100)
        y -= 12


_RENDERERS: dict[str, Callable[[Canvas, Doc, Family, list[str]], None]] = {
    "table": _render_table,
    "roll": _render_roll,
    "stacked": _render_stacked,
    "sidebar": _render_sidebar,
    "statement": _render_statement,
    "pos_page": _render_pos_page,
}


def render_pdf(doc: Doc, family: Family, business: list[str]) -> bytes:
    """One page, vector text, deterministic bytes. `business` is the bill-to address block."""
    _register_fonts()
    buffer = io.BytesIO()
    if family.page == "roll":
        rows = len(doc.line_printed)
        size = (_ROLL_WIDTH, 190.0 + rows * 19 + len(doc.notes) * 8)
    else:
        size = _page_size(family)
    canvas = Canvas(buffer, pagesize=size, invariant=1, pageCompression=0)
    canvas.setTitle(f"{doc.id} (synthetic)")
    _RENDERERS[family.kind](canvas, doc, family, business)
    pen = Pen(canvas, family)
    pen.text(size[0] / 2, 12, FOOTER, 6, align="c", color=(0.5, 0.5, 0.5))
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()
