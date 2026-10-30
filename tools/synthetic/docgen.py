"""Build one invented document: choose lines, compute every figure exactly, print the strings.

`generate` always produces consistent arithmetic. Planting a problem (see planting.py) changes
numbers afterwards and calls `reprint`, so the truth always equals what is printed.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from tools.synthetic.arith import line_amount_minor, tax_minor
from tools.synthetic.facts import Facts, Item, Vendor
from tools.synthetic.fmt import format_date, format_money, format_qty
from tools.synthetic.model import Doc, Line, Style

_CODE_STYLES = {"us_code"}


def _quantity(rng: random.Random, item: Item) -> Decimal:
    low, high = item.qty
    if item.description.endswith(", gal"):  # fuel is sold by the thousandth of a gallon
        return Decimal(rng.randint(low * 1000, high * 1000)) / 1000
    return Decimal(rng.randint(low, high))


def invoice_number(vendor: Vendor, serial: int, credit: bool = False) -> str:
    number = vendor.invoice_start + serial * 3 + (serial % 2)
    return f"{'CN-' if credit else vendor.invoice_prefix}{number}"


def generate(
    rng: random.Random,
    facts: Facts,
    vendor: Vendor,
    doc_id: str,
    entry_date: date,
    serial: int,
    style: Style,
    entry_type: str | None = None,
    currency: str | None = None,
) -> Doc:
    kind = entry_type or vendor.entry_type
    if kind == "credit_note" and not vendor.credit_notes:
        raise ValueError(f"{vendor.id} does not issue credit notes")
    if kind not in {"invoice", "receipt", "credit_note"}:
        raise ValueError(f"unknown entry type {kind!r}")

    catalog = vendor.items
    if kind == "receipt":
        count = rng.randint(1, min(4, len(catalog)))
    else:
        count = rng.randint(min(2, len(catalog)), min(5, len(catalog)))
    items = rng.sample(catalog, count)

    rate = vendor.tax_rate(facts.business)
    lines: list[Line] = []
    for item in items:
        qty = _quantity(rng, item)
        amount = line_amount_minor(qty, item.unit_price)
        lines.append(Line(item.description, qty, item.unit_price, amount, item.taxable))

    subtotal = sum(line.amount_minor for line in lines)
    taxable = sum(line.amount_minor for line in lines if line.taxable)
    if style.tax_mode == "per_line":
        for line in lines:
            line.tax_minor = tax_minor(line.amount_minor, rate) if line.taxable else 0
        tax_total = sum(line.tax_minor for line in lines)
    else:
        tax_total = tax_minor(taxable, rate)

    shipping = rng.randint(800, 3500) if style.has_shipping else 0
    discount = 0
    if style.has_discount:
        discount = min(subtotal // 2, tax_minor(subtotal, Decimal(rng.choice(["0.05", "0.10"]))))

    variant = vendor.name if rng.random() < 0.6 else rng.choice(vendor.aliases)
    has_number = kind != "receipt"
    doc = Doc(
        id=doc_id,
        entry_type=kind,
        vendor=vendor,
        vendor_name=variant,
        invoice_number=invoice_number(vendor, serial, kind == "credit_note")
        if has_number
        else None,
        po_number=(
            f"PO-{rng.randint(1000, 9999)}" if kind == "invoice" and rng.random() < 0.3 else None
        ),
        entry_date=entry_date,
        due_date=(
            entry_date + timedelta(days=vendor.terms_days)
            if kind == "invoice" and vendor.terms_days > 0
            else None
        ),
        currency=currency or vendor.currency,
        lines=lines,
        tax_rate=rate,
        style=style,
        subtotal_minor=subtotal,
        shipping_minor=shipping,
        discount_minor=discount,
        tax_total_minor=tax_total,
        total_minor=subtotal + tax_total + shipping - discount,
    )
    reprint(doc)
    return doc


def _money_style(doc: Doc) -> str:
    if doc.currency == "EUR":
        return "eu_symbol"
    if doc.entry_type == "credit_note" and doc.style.credit_style == "paren":
        return "paren"
    return doc.style.money


def _plain(style: str) -> str:
    """Line amounts do not repeat a currency code on every row."""
    return "us_plain" if style in _CODE_STYLES else style


def _unit_price(price: Decimal, style: str, currency: str) -> str:
    number = f"{price:,f}"
    if currency == "EUR":
        number = number.replace(",", "\0").replace(".", ",").replace("\0", ".")
        return number
    if style in {"us_symbol", "us_nocomma", "paren"}:
        symbol = "CA$" if currency == "CAD" else "$"
        number = f"{symbol}{number}"
        if style == "us_nocomma":
            number = number.replace(",", "")
    return number


def _percent(rate: Decimal) -> str:
    return f"{(rate * 100).normalize():f}%"


def reprint(doc: Doc) -> None:
    """Rebuild every printed string from the current numbers."""
    money = _money_style(doc)
    line_money = _plain(money)
    printed: dict[str, str] = {
        "vendor_name": doc.vendor_name,
        "entry_date": format_date(doc.entry_date, doc.style.date),
        "currency": doc.currency if money in _CODE_STYLES else _currency_mark(doc.currency),
        "total": format_money(doc.total_minor, money, doc.currency),
    }
    if doc.invoice_number is not None:
        printed["invoice_number"] = doc.invoice_number
    if doc.due_date is not None:
        printed["due_date"] = format_date(doc.due_date, doc.style.date)
    if doc.po_number is not None:
        printed["po_number"] = doc.po_number
    if doc.style.prints_subtotal:
        printed["subtotal"] = format_money(doc.subtotal_minor, money, doc.currency)
    if any(line.taxable for line in doc.lines):
        printed["tax_total"] = format_money(doc.tax_total_minor, money, doc.currency)
        if doc.style.prints_tax_rate:
            printed["tax_rate"] = _percent(doc.tax_rate)
    if doc.shipping_minor:
        printed["shipping"] = format_money(doc.shipping_minor, money, doc.currency)
    if doc.discount_minor:
        printed["discount"] = format_money(doc.discount_minor, money, doc.currency)
    doc.printed = printed

    doc.line_printed = []
    for line in doc.lines:
        row = {
            "description": line.description,
            "quantity": format_qty(line.quantity),
            "unit_price": _unit_price(line.unit_price, money, doc.currency),
            "amount": format_money(line.amount_minor, line_money, doc.currency),
        }
        if doc.style.tax_mode == "per_line" and line.taxable:
            row["tax"] = format_money(line.tax_minor, line_money, doc.currency)
        doc.line_printed.append(row)


def _currency_mark(currency: str) -> str:
    return {"USD": "$", "EUR": "€", "CAD": "CA$"}.get(currency, currency)


def arithmetic_problems(doc: Doc, tolerance_minor: int = 1) -> list[str]:
    """Which of the document's own arithmetic rules are broken (the rules in docs/TRD.md 4.6).

    Written here from the rules, not imported from the product, so it can verify the generator
    and, later, the planted problems independently of the code under evaluation.
    """
    problems: list[str] = []
    if any(
        abs(line.amount_minor - line_amount_minor(line.quantity, line.unit_price)) > tolerance_minor
        for line in doc.lines
    ):
        problems.append("LINE_MATH")
    line_sum = sum(line.amount_minor for line in doc.lines)
    if doc.style.prints_subtotal and abs(line_sum - doc.subtotal_minor) > tolerance_minor:
        problems.append("SUBTOTAL_MATCH")
    if doc.style.prints_tax_rate and any(line.taxable for line in doc.lines):
        taxable = [line for line in doc.lines if line.taxable]
        expected = tax_minor(sum(line.amount_minor for line in taxable), doc.tax_rate)
        if abs(doc.tax_total_minor - expected) > max(tolerance_minor, len(taxable)):
            problems.append("TAX_MATCH")
    base = doc.subtotal_minor if doc.style.prints_subtotal else line_sum
    expected_total = base + doc.tax_total_minor + doc.shipping_minor - doc.discount_minor
    if abs(doc.total_minor - expected_total) > tolerance_minor:
        problems.append("TOTAL_MATCH")
    return problems


def truth(doc: Doc) -> dict[str, Any]:
    """The golden-set `truth` block: values as printed, plus the strings that were printed."""
    printed = doc.printed
    result: dict[str, Any] = {
        "entry_type": doc.entry_type,
        "vendor_name": doc.vendor_name,
        "invoice_number": doc.invoice_number,
        "entry_date": doc.entry_date.isoformat(),
        "due_date": doc.due_date.isoformat() if doc.due_date else None,
        "po_number": doc.po_number,
        "currency": doc.currency,
        "subtotal_minor": doc.subtotal_minor if "subtotal" in printed else None,
        "tax_total_minor": doc.tax_total_minor if "tax_total" in printed else None,
        "shipping_minor": doc.shipping_minor if "shipping" in printed else None,
        "discount_minor": doc.discount_minor if "discount" in printed else None,
        "total_minor": doc.total_minor,
        "lines": [],
        "printed": dict(printed),
    }
    for line, shown in zip(doc.lines, doc.line_printed, strict=True):
        row: dict[str, Any] = {
            "description": line.description,
            "quantity": format_qty(line.quantity),
            "unit_price": f"{line.unit_price:f}",
            "amount_minor": line.amount_minor,
            "printed": shown,
        }
        if doc.style.tax_mode == "per_line" and line.taxable:
            row["tax_minor"] = line.tax_minor
        result["lines"].append(row)
    return result
