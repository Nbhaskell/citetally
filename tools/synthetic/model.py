"""The generated document as data: numbers first, then the strings printed from them.

What is printed is the truth. When a problem is planted, the numbers are changed and the strings
are printed again, so the answer key always holds what is on the page, not what it should be.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from tools.synthetic.facts import Vendor


@dataclass(frozen=True)
class Style:
    """Choices a template family makes about what a document shows and how it prints values."""

    money: str = "us_symbol"
    date: str = "long"
    tax_mode: str = "document"  # "document": one tax figure; "per_line": tax shown on each line
    prints_subtotal: bool = True
    prints_tax_rate: bool = True
    has_shipping: bool = False
    has_discount: bool = False
    credit_style: str = "plain"  # "plain" or "paren" amounts on credit notes


@dataclass
class Line:
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount_minor: int
    taxable: bool
    tax_minor: int = 0  # per-line tax, used when tax_mode is "per_line"


@dataclass
class Doc:
    id: str
    entry_type: str  # invoice, receipt or credit_note
    vendor: Vendor
    vendor_name: str  # as printed: the real name or a printed variant
    invoice_number: str | None
    po_number: str | None
    entry_date: date
    due_date: date | None
    currency: str
    lines: list[Line]
    tax_rate: Decimal
    style: Style
    subtotal_minor: int
    shipping_minor: int
    discount_minor: int
    tax_total_minor: int
    total_minor: int
    notes: list[str] = field(default_factory=list)  # extra printed lines (footers, remarks)
    printed: dict[str, str] = field(default_factory=dict)
    line_printed: list[dict[str, str]] = field(default_factory=list)
