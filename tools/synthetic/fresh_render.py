"""Draw the fresh families as PDFs with a real text layer: five engines, many realistic extras.

What is added beside a document's own values (stamps, pen notes, a second total, remittance and
account blocks, ageing figures, watermarks, barcodes) is never in the answer key. Descriptions that
are too long for their column wrap onto a second line, so a printed description can be two pieces
of text in the layer. Every page still carries the footer "SYNTHETIC TEST DATA".
"""

from __future__ import annotations

import io
import random
from datetime import timedelta

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen.canvas import Canvas

from tools.synthetic.docgen import _money_style, _plain
from tools.synthetic.fmt import format_date, format_money
from tools.synthetic.fresh_families import FreshFamily
from tools.synthetic.model import Doc
from tools.synthetic.render import (
    _ROLL_WIDTH,
    FOOTER,
    Pen,
    _column_titles,
    _draw_totals,
    _header,
    _meta,
    _notes,
    _page_size,
    _register_fonts,
    _vendor_lines,
)

GRAY = (0.38, 0.38, 0.38)
INK = (0.08, 0.12, 0.5)
RED = (0.72, 0.1, 0.1)


# ---- small drawing pieces ----------------------------------------------------------------------


def wrap(text: str, font: str, size: float, width: float) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if not current or pdfmetrics.stringWidth(trial, font, size) <= width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def stamp(c: Canvas, x: float, y: float, words: str, angle: float, size: float = 22) -> None:
    c.saveState()
    c.translate(x, y)
    c.rotate(angle)
    c.setFillAlpha(0.72)
    c.setStrokeAlpha(0.72)
    c.setStrokeColorRGB(*RED)
    c.setFillColorRGB(*RED)
    c.setLineWidth(2.2)
    width = pdfmetrics.stringWidth(words, "Helvetica-Bold", size) + 20
    c.roundRect(-width / 2, -size * 0.45, width, size * 1.35, 4, stroke=1, fill=0)
    c.setFont("Helvetica-Bold", size)
    c.drawCentredString(0, 0, words)
    c.restoreState()


def scrawl(c: Canvas, x: float, y: float, text: str, size: float, rng: random.Random) -> None:
    """Pen writing: every letter a little off the line and the angle, in blue-black ink."""
    c.saveState()
    c.setFillColorRGB(*INK)
    cursor = x
    for char in text:
        c.saveState()
        c.translate(cursor, y + rng.uniform(-1.6, 1.6))
        c.rotate(rng.uniform(-7, 7))
        font = rng.choice(["Times-Italic", "Times-BoldItalic"])
        c.setFont(font, size * rng.uniform(0.92, 1.12))
        c.drawString(0, 0, char)
        c.restoreState()
        cursor += pdfmetrics.stringWidth(char, "Times-Italic", size) * 1.02
    c.restoreState()


def barcode(c: Canvas, x: float, y: float, width: float, height: float, rng: random.Random) -> str:
    digits = "".join(str(rng.randint(0, 9)) for _ in range(12))
    c.setFillColorRGB(0, 0, 0)
    cursor = x
    while cursor < x + width - 2:
        bar = rng.choice([0.8, 1.2, 1.8, 2.6])
        c.rect(cursor, y, bar, height, stroke=0, fill=1)
        cursor += bar + rng.choice([0.8, 1.2, 1.8])
    c.setFont("Courier", 7)
    c.drawCentredString(x + width / 2, y - 9, digits)
    return digits


def watermark(c: Canvas, w: float, h: float, words: str) -> None:
    c.saveState()
    c.setFillAlpha(0.09)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.translate(w / 2, h / 2)
    c.rotate(38)
    c.setFont("Helvetica-Bold", 96)
    c.drawCentredString(0, 0, words)
    c.restoreState()


def _chance(rng: random.Random, share: float) -> bool:
    return rng.random() < share


def _extra_meta(doc: Doc, fam: FreshFamily, rng: random.Random) -> list[tuple[str, str]]:
    """Other dates and ids that sit beside the real ones, each with a label that says what it is."""
    rows: list[tuple[str, str]] = []
    style = doc.style.date
    if "order_dates" in fam.features:
        rows.append(
            ("Order date", format_date(doc.entry_date - timedelta(days=rng.randint(4, 12)), style))
        )
        rows.append(
            ("Ship date", format_date(doc.entry_date - timedelta(days=rng.randint(1, 3)), style))
        )
    if "account_box" in fam.features or "terms" in fam.features:
        rows.append(("Customer ID", f"C-{rng.randint(10000, 99999)}"))
    return rows


def _row_height(size: float) -> float:
    return size * 1.3 + 5


def _table(
    pen: Pen,
    doc: Doc,
    fam: FreshFamily,
    left: float,
    right: float,
    y: float,
    *,
    rows: list[dict[str, str]] | None = None,
    header: bool = True,
    band: bool = False,
) -> float:
    columns = fam.columns
    titles = _column_titles(fam)
    fractions = {
        "description": 0.44,
        "qty": 0.08,
        "unit_price": 0.16,
        "line_tax": 0.12,
        "amount": 0.18,
    }
    total = sum(fractions[c] for c in columns)
    span = right - left
    widths = {c: span * fractions[c] / total for c in columns}
    edges: dict[str, float] = {}
    cursor = left
    for c in columns:
        edges[c] = cursor
        cursor += widths[c]
    size = fam.size
    base = _row_height(size)
    shown = doc.line_printed if rows is None else rows

    def put(
        column: str,
        value: str,
        at: float,
        *,
        bold: bool = False,
        color: tuple[float, float, float] | None = None,
    ) -> None:
        if column == "description":
            pen.text(edges[column] + 4, at, value, size, bold=bold, color=color)
        else:
            pen.text(
                edges[column] + widths[column] - 4,
                at,
                value,
                size,
                bold=bold,
                align="r",
                max_width=widths[column] - 6,
                color=color,
            )

    top = y
    if header:
        if band:
            pen.c.setFillColorRGB(*pen.accent)
            pen.c.rect(left, y - 5, span, base, stroke=0, fill=1)
            pen.c.setFillColorRGB(0, 0, 0)
        elif fam.table in {"grid", "zebra"}:
            pen.shade(left, y - 5, span, base, 0.86)
        for column in columns:
            put(column, titles[column], y, bold=True, color=(1, 1, 1) if band else None)
        if not band:
            pen.rule(left, y - 6, right, 0.8, accent=True)
        y -= base
    for index, row in enumerate(shown):
        pieces = wrap(
            row["description"],
            fam.font,
            size,
            widths["description"] - 8,
        )
        height = base + (len(pieces) - 1) * size * 1.2
        if fam.table == "zebra" and index % 2 == 1:
            pen.shade(left, y - height + base - 5, span, height, 0.95)
        for number, piece in enumerate(pieces):
            pen.text(edges["description"] + 4, y - number * size * 1.2, piece, size)
        values = {
            "qty": row["quantity"],
            "unit_price": row["unit_price"],
            "amount": row["amount"],
            "line_tax": row.get("tax", ""),
        }
        for column in columns:
            if column != "description":
                put(column, values[column], y)
        if fam.table in {"grid", "ruled"}:
            pen.rule(left, y - height + base - 6, right, 0.3)
        y -= height
    if fam.table == "grid":
        pen.box(left, y + base - 6, span, top - y + 1 if header else top - y)
    return y - 6


def _bill_to(
    pen: Pen, fam: FreshFamily, business: list[str], x: float, y: float, title: str
) -> float:
    pen.text(x, y, title, 8, bold=True, color=pen.accent)
    for i, line in enumerate(business):
        pen.text(x, y - 12 - i * 11, line, fam.size, bold=(i == 0))
    return y - 14 - len(business) * 11


def _remit(pen: Pen, doc: Doc, x: float, y: float, rng: random.Random) -> float:
    pen.text(x, y, "Remit to", 8, bold=True, color=GRAY)
    lines = [
        doc.vendor.name,
        "Cascadia Community Bank",
        f"Acct no. {rng.randint(1000, 9999)}-{rng.randint(100, 999)}-{rng.randint(100, 999)}",
        "ABA 000-000-000",
    ]
    for i, line in enumerate(lines):
        pen.text(x, y - 11 - i * 10, line, 7.5)
    return y - 12 - len(lines) * 10


def _terms(doc: Doc, rng: random.Random) -> str:
    days = doc.vendor.terms_days or 30
    return rng.choice(
        [
            f"Terms: net {days} days",
            f"Terms: 2% 10 days, net {days}",
            "A late fee of 1.5% a month applies after the due date",
        ]
    )


def _decorate(
    c: Canvas,
    doc: Doc,
    fam: FreshFamily,
    w: float,
    h: float,
    rng: random.Random,
    spot: tuple[float, float],
) -> None:
    """Stamp and pen note, placed over the part of the page where the values are."""
    if "stamp" in fam.features and _chance(rng, 0.55):
        word = rng.choice(["PAID", "RECEIVED", "APPROVED", "COPY"])
        when = (doc.entry_date + timedelta(days=rng.randint(2, 14))).strftime("%b %d").upper()
        label = f"{word} {when}" if word in {"PAID", "RECEIVED"} else word
        stamp(
            c,
            spot[0] + rng.uniform(-30, 30),
            spot[1] + rng.uniform(-20, 20),
            label,
            rng.uniform(-18, 18),
        )
    if "scrawl" in fam.features and _chance(rng, 0.65):
        note = rng.choice(
            [
                "ck 4412 sent",
                "ok to pay - JR",
                "rec'd in full",
                "short 1 box, call",
                "approved MT",
                "see PO",
            ]
        )
        scrawl(c, w * 0.52, h - 22, note, 13, rng)


# ---- engines -----------------------------------------------------------------------------------


def _dense(c: Canvas, doc: Doc, fam: FreshFamily, business: list[str], rng: random.Random) -> None:
    w, h = _page_size(fam)
    pen = Pen(c, fam)
    m = 40.0
    y = _header(pen, doc, fam, w, h - 30)
    extras = _extra_meta(doc, fam, rng)
    for label, value in extras:
        pen.text(m, y, f"{label}:", 8, bold=True, color=GRAY)
        pen.text(m + 70, y, value, 8, color=GRAY)
        y -= 11
    y -= 4
    left_bottom = _bill_to(pen, fam, business, m, y, fam.labels["bill_to"])
    if "ship_to" in fam.features:
        _bill_to(pen, fam, [business[0], "Attn: Receiving", *business[1:3]], w / 2, y, "Ship to")
    y = left_bottom - 6
    y = _table(pen, doc, fam, m, w - m, y, band=fam.table == "zebra")
    totals_y = y - 4
    y = _draw_totals(pen, doc, fam, w - m, totals_y, w - m - 190)
    block_y = totals_y
    if "remit" in fam.features or "stub" in fam.features:
        _remit(pen, doc, m, block_y, rng)
    y -= 12
    if "terms" in fam.features:
        pen.text(m, y, _terms(doc, rng), 8, color=GRAY)
        y -= 12
    for note in _notes(doc):
        pen.text(m, y, note, 8, max_width=w - 2 * m)
        y -= 11
    if "stub" in fam.features:
        sy = 112.0
        c.setDash(3, 3)
        pen.rule(m, sy + 26, w - m, 0.6)
        c.setDash()
        pen.text(m, sy + 14, "Detach here and return with your payment", 7, color=GRAY)
        pen.text(
            m,
            sy - 4,
            f"{fam.labels['number']} {doc.printed.get('invoice_number', '')}",
            9,
            bold=True,
        )
        pen.text(m + 250, sy - 4, f"{doc.vendor_name}", 9)
        pen.text(
            w - m, sy - 4, f"{fam.labels['total']} {doc.printed['total']}", 9, bold=True, align="r"
        )
        pen.text(m, sy - 22, "Amount enclosed: ______________", 9)
    _decorate(c, doc, fam, w, h, rng, (w * 0.62, totals_y - 30))


def _airy(c: Canvas, doc: Doc, fam: FreshFamily, business: list[str], rng: random.Random) -> None:
    w, h = _page_size(fam)
    pen = Pen(c, fam)
    m = 50.0
    if "watermark" in fam.features:
        watermark(c, w, h, "ORIGINAL")
    if "due_box" in fam.features:
        pen.text(m, h - 56, doc.vendor_name, 19, bold=True, max_width=w - 2 * m - 210)
        for i, line in enumerate(_vendor_lines(doc)):
            pen.text(m, h - 74 - i * 11, line, 8.5, color=GRAY)
        pen.box(w - m - 175, h - 98, 175, 64)
        pen.text(w - m - 165, h - 52, "AMOUNT DUE", 8, bold=True, color=pen.accent)
        pen.text(w - m - 10, h - 78, doc.printed["total"], 19, bold=True, align="r")
        if "due_date" in doc.printed:
            pen.text(w - m - 165, h - 92, f"{fam.labels['due']} {doc.printed['due_date']}", 8)
        y = h - 74 - len(_vendor_lines(doc)) * 11 - 22
        rows = _meta(doc, fam) + _extra_meta(doc, fam, rng)
        for label, value in rows:
            pen.text(m, y, f"{label}", 9.5, bold=True)
            pen.text(m + 125, y, value, 9.5)
            y -= 14
        y -= 10
    else:
        y = _header(pen, doc, fam, w, h - 30)
        for label, value in _extra_meta(doc, fam, rng):
            pen.text(w / 2, y, f"{label}: {value}", 8.5, align="c", color=GRAY)
            y -= 11
        y -= 6
    y = _bill_to(pen, fam, business, m, y, fam.labels["bill_to"]) - 8
    y = _table(pen, doc, fam, m, w - m, y)
    totals_y = y - 6
    y = _draw_totals(pen, doc, fam, w - m, totals_y, w - m - 200)
    y -= 16
    for note in _notes(doc):
        pen.text(m, y, note, 9, max_width=w - 2 * m, color=GRAY)
        y -= 12
    _decorate(c, doc, fam, w, h, rng, (w * 0.62, totals_y - 20))


def _sections(
    c: Canvas, doc: Doc, fam: FreshFamily, business: list[str], rng: random.Random
) -> None:
    w, h = _page_size(fam)
    pen = Pen(c, fam)
    m = 44.0
    y = _header(pen, doc, fam, w, h - 30)
    for label, value in _extra_meta(doc, fam, rng):
        pen.text(m, y, f"{label}: {value}", 8.5, color=GRAY)
        y -= 11
    y = _bill_to(pen, fam, business, m, y - 4, fam.labels["bill_to"]) - 6
    money = _plain(_money_style(doc))
    groups = [
        ("Labour and services", [i for i, line in enumerate(doc.lines) if not line.taxable]),
        ("Parts and materials", [i for i, line in enumerate(doc.lines) if line.taxable]),
    ]
    first = True
    for title, indexes in groups:
        if not indexes:
            continue
        pen.text(m, y, title, 10, bold=True, color=pen.accent)
        y -= 14
        y = _table(
            pen, doc, fam, m, w - m, y, rows=[doc.line_printed[i] for i in indexes], header=first
        )
        first = False
        part = sum(doc.lines[i].amount_minor for i in indexes)
        pen.text(w - m - 120, y + 2, f"{title.split(' ')[0]} subtotal", 8, color=GRAY, align="r")
        pen.text(w - m, y + 2, format_money(part, money, doc.currency), 8, color=GRAY, align="r")
        y -= 10
    totals_y = y - 4
    y = _draw_totals(pen, doc, fam, w - m, totals_y, w - m - 200)
    y -= 14
    for note in _notes(doc):
        pen.text(m, y, note, 8, max_width=w - 2 * m)
        y -= 11
    _decorate(c, doc, fam, w, h, rng, (w * 0.6, totals_y - 24))


def _bill(c: Canvas, doc: Doc, fam: FreshFamily, business: list[str], rng: random.Random) -> None:
    w, h = _page_size(fam)
    pen = Pen(c, fam)
    m = 44.0
    y = _header(pen, doc, fam, w, h - 30)
    y = _bill_to(pen, fam, business, m, y, fam.labels["bill_to"]) - 6
    box_w = w - 2 * m
    rows: list[tuple[str, str]] = [
        ("Account no.", f"{rng.randint(1000000, 9999999)}"),
        ("Customer ID", f"C-{rng.randint(10000, 99999)}"),
    ]
    if "period" in fam.features:
        start = doc.entry_date - timedelta(days=30)
        rows.append(
            (
                "Service period",
                f"{format_date(start, doc.style.date)} to "
                f"{format_date(doc.entry_date - timedelta(days=1), doc.style.date)}",
            )
        )
    zero = format_money(0, _plain(_money_style(doc)), doc.currency)
    rows += [("Previous balance", zero), ("Payments received", zero)]
    pen.box(m, y - 20 - len(rows) * 12, box_w, 26 + len(rows) * 12)
    pen.text(m + 8, y - 8, "Account summary", 9, bold=True, color=pen.accent)
    for i, (label, value) in enumerate(rows):
        pen.text(m + 8, y - 22 - i * 12, label, 8.5)
        pen.text(m + 150, y - 22 - i * 12, value, 8.5)
    y -= 48 + len(rows) * 12
    if "usage_bars" in fam.features:
        pen.text(m, y, "Your use over the last six months", 8, bold=True, color=GRAY)
        base = y - 52
        for i, month in enumerate(["May", "Jun", "Jul", "Aug", "Sep", "Oct"]):
            bar = rng.uniform(14, 46)
            pen.c.setFillColorRGB(*pen.accent)
            pen.c.rect(m + 12 + i * 34, base, 20, bar, stroke=0, fill=1)
            pen.c.setFillColorRGB(0, 0, 0)
            pen.text(m + 22 + i * 34, base - 9, month, 6.5, align="c", color=GRAY)
        y = base - 26
    y = _table(pen, doc, fam, m, w - m, y)
    totals_y = y - 4
    y = _draw_totals(pen, doc, fam, w - m, totals_y, w - m - 210)
    if "ageing" in fam.features:
        y -= 10
        buckets = [
            ("Current", doc.printed["total"]),
            ("1-30 days", zero),
            ("31-60 days", zero),
            ("Over 60", zero),
        ]
        for i, (label, value) in enumerate(buckets):
            x = m + i * (box_w / 4)
            pen.box(x, y - 30, box_w / 4 - 6, 30)
            pen.text(x + 6, y - 11, label, 7.5, color=GRAY)
            pen.text(x + 6, y - 24, value, 8.5)
        y -= 44
    y -= 10
    for note in _notes(doc):
        pen.text(m, y, note, 8, max_width=w - 2 * m)
        y -= 11
    _decorate(c, doc, fam, w, h, rng, (w * 0.62, totals_y - 26))


def _till(c: Canvas, doc: Doc, fam: FreshFamily, business: list[str], rng: random.Random) -> None:
    w = _ROLL_WIDTH
    pen = Pen(c, fam)
    size = fam.size
    x0, x1 = 10.0, w - 10.0
    y = c._pagesize[1] - 22
    pen.text(w / 2, y, doc.vendor_name, 10, bold=True, align="c", max_width=w - 20)
    y -= 12
    for line in _vendor_lines(doc):
        pen.text(w / 2, y, line, size, align="c", max_width=w - 20)
        y -= size + 2
    y -= 6
    for label, value in _meta(doc, fam):
        pen.text(x0, y, f"{label}: {value}", size, max_width=w - 20)
        y -= size + 3
    pen.text(x0, y, f"Terminal {rng.randint(1, 4)}  Clerk {rng.randint(10, 99)}", size, color=GRAY)
    y -= size + 6
    pen.text(x0, y, "-" * 38, size)
    y -= size + 4
    for row in doc.line_printed:
        for number, piece in enumerate(wrap(row["description"], fam.font, size, w - 20)):
            pen.text(x0, y - number * (size + 1), piece, size)
        y -= (len(wrap(row["description"], fam.font, size, w - 20)) - 1) * (size + 1)
        y -= size + 2
        pen.text(x0 + 8, y, f"{row['quantity']} @ {row['unit_price']}", size)
        pen.text(x1, y, row["amount"], size, align="r")
        y -= size + 4
    pen.text(x0, y, "-" * 38, size)
    y -= size + 5
    for label, value, strong in _till_totals(doc, fam):
        pen.text(x0, y, label, size + (1 if strong else 0), bold=strong)
        pen.text(x1, y, value, size + (1 if strong else 0), bold=strong, align="r")
        y -= size + 5
    y -= 4
    if "card" in fam.features:
        pen.text(x0, y, f"VISA **** {rng.randint(1000, 9999)}", size)
        pen.text(x1, y, f"AUTH {rng.randint(100000, 999999)}", size, align="r")
        y -= size + 4
        pen.text(x0, y, f"REF {rng.randint(1000, 9999)} {rng.randint(100, 999)}", size, color=GRAY)
        y -= size + 8
    if "barcode" in fam.features:
        barcode(c, x0 + 10, y - 26, w - 40, 26, rng)
        y -= 50
    pen.text(w / 2, y, "THANK YOU - COME AGAIN", size, align="c")
    if doc.notes:  # extra printed lines, such as a planted instruction
        y -= size + 8
        for note in doc.notes:
            for line in wrap(note, fam.font, size, w - 2 * x0):
                pen.text(x0, y, line, size)
                y -= size + 3
    if "scrawl" in fam.features and _chance(rng, 0.5):
        scrawl(
            c,
            x0 + 6,
            y - 20,
            rng.choice(["cash back $20", "for Mon bake", "van - receipt"]),
            11,
            rng,
        )


def _till_totals(doc: Doc, fam: FreshFamily) -> list[tuple[str, str, bool]]:
    p = doc.printed
    rows: list[tuple[str, str, bool]] = []
    if "subtotal" in p:
        rows.append((fam.labels["subtotal"], p["subtotal"], False))
    if "tax_total" in p:
        label = fam.labels["tax"] + (f" {p['tax_rate']}" if "tax_rate" in p else "")
        rows.append((label, p["tax_total"], False))
    rows.append((fam.labels["total"], p["total"], True))
    return rows


def _pad(c: Canvas, doc: Doc, fam: FreshFamily, business: list[str], rng: random.Random) -> None:
    w, h = _page_size(fam)
    pen = Pen(c, fam)
    m = 56.0
    pen.text(m, h - 70, doc.vendor_name, 20, bold=True, max_width=w - 2 * m - 150)
    for i, line in enumerate(_vendor_lines(doc)):
        pen.text(m, h - 88 - i * 11, line, 9)
    number = doc.printed.get("invoice_number", "")
    pen.text(w - m, h - 66, "RECEIPT", 22, bold=True, align="r", color=pen.accent)
    pen.text(w - m, h - 86, f"{fam.labels['number']} {number}", 11, bold=True, align="r", color=RED)
    y = h - 150
    pen.text(m, y, f"Date  {doc.printed['entry_date']}", 11)
    y -= 22
    pen.text(m, y, f"Received from  {business[0]}", 11)
    pen.rule(m + 92, y - 3, w - m, 0.5)
    y -= 30
    size = fam.size
    columns = ("description", "qty", "unit_price", "amount")
    left, right = m, w - m
    base = _row_height(size) + 4
    rows = 7
    edges = {"description": left, "qty": left + 255, "unit_price": left + 310, "amount": left + 395}
    for column, title in zip(columns, ("ITEM", "QTY", "PRICE", "AMOUNT"), strict=True):
        pen.text(edges[column] + 4, y, title, 8, bold=True, color=pen.accent)
    y -= 12
    top = y + 10
    for index in range(rows):
        if index < len(doc.line_printed):
            row = doc.line_printed[index]
            pen.text(edges["description"] + 4, y - 4, row["description"], size, max_width=245)
            pen.text(edges["qty"] + 4, y - 4, row["quantity"], size)
            pen.text(edges["unit_price"] + 4, y - 4, row["unit_price"], size, max_width=80)
            pen.text(right - 4, y - 4, row["amount"], size, align="r")
        pen.rule(left, y - 10, right, 0.4)
        y -= base
    pen.box(left, y + base - 10, right - left, top - y - base + 10)
    y -= 8
    for label, value, strong in _till_totals(doc, fam):
        pen.text(right - 150, y, label, 11 if strong else 10, bold=strong)
        pen.text(right - 4, y, value, 11 if strong else 10, bold=strong, align="r")
        y -= 17
    if "barcode" in fam.features:
        barcode(c, m, y - 20, 150, 26, rng)
    if _chance(rng, 0.8):
        stamp(c, w * 0.34, y + 10, "PAID IN FULL", rng.uniform(-14, 14), 20)
    if "scrawl" in fam.features:
        scrawl(c, m, y - 70, "Rec'd by: " + rng.choice(["J. T.", "M. Ruiz", "dk"]), 14, rng)
    notes_y = 70.0  # extra printed lines, such as a planted instruction, at the foot of the page
    for note in doc.notes:
        for line in wrap(note, fam.font, 8, w - 2 * m):
            pen.text(m, notes_y, line, 8)
            notes_y -= 10


_ENGINES = {
    "dense": _dense,
    "airy": _airy,
    "sections": _sections,
    "bill": _bill,
    "till": _till,
    "pad": _pad,
}


def render_fresh_pdf(doc: Doc, fam: FreshFamily, business: list[str]) -> bytes:
    """One page, vector text, deterministic bytes."""
    _register_fonts()
    rng = random.Random(f"fresh:{doc.id}")
    if fam.engine == "till":
        extra = sum(
            len(wrap(r["description"], fam.font, fam.size, _ROLL_WIDTH - 20))
            for r in doc.line_printed
        )
        notes_lines = sum(
            len(wrap(note, fam.font, fam.size, _ROLL_WIDTH - 20)) for note in doc.notes
        )
        size = (
            _ROLL_WIDTH,
            250.0
            + len(doc.line_printed) * 24
            + extra * 9
            + (60 if "barcode" in fam.features else 0)
            + (notes_lines * (fam.size + 3) + fam.size + 8 if notes_lines else 0),
        )
    else:
        size = _page_size(fam)
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=size, invariant=1, pageCompression=0)
    canvas.setTitle(f"{doc.id} (synthetic)")
    _ENGINES[fam.engine](canvas, doc, fam, business, rng)
    Pen(canvas, fam).text(size[0] / 2, 12, FOOTER, 6, align="c", color=(0.5, 0.5, 0.5))
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()
