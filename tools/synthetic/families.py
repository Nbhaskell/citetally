"""The 15 invented invoice and receipt layouts ("template families").

Ten are used to build and tune the system. Five are held out and use layouts the tuned set
never shows, including three renderer kinds (sidebar, statement, pos_page) that no tuned family
uses. Which vendors may use which family is fixed here, so every vendor appears in the tuned set.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tools.synthetic.model import Style


@dataclass(frozen=True)
class Family:
    id: str
    name: str
    split: str  # "tuned" or "heldout"
    kind: str  # table, roll, stacked, sidebar, statement, pos_page
    vendors: tuple[str, ...]
    entry_types: tuple[str, ...]
    style: Style
    font: str = "Helvetica"
    page: str = "letter"  # letter, a4, landscape, roll
    header: str = "left"  # left, two_col, centered, boxed, banner
    table: str = "grid"  # grid, ruled, zebra, none
    columns: tuple[str, ...] = ("description", "qty", "unit_price", "amount")
    accent: tuple[float, float, float] = (0.15, 0.25, 0.45)
    labels: dict[str, str] = field(default_factory=dict)


def _labels(**overrides: str) -> dict[str, str]:
    base = {
        "invoice": "INVOICE", "receipt": "RECEIPT", "credit_note": "CREDIT NOTE",
        "number": "Invoice No.", "date": "Date", "due": "Due date", "po": "PO number",
        "subtotal": "Subtotal", "shipping": "Shipping", "discount": "Less discount",
        "tax": "Sales tax", "total": "Total", "credit_total": "Total credit",
        "description": "Description", "qty": "Qty", "unit_price": "Unit price",
        "amount": "Amount", "line_tax": "Tax", "bill_to": "Bill to",
    }  # fmt: skip
    return {**base, **overrides}


FAMILIES: tuple[Family, ...] = (
    Family(
        "T01",
        "single-table invoice",
        "tuned",
        "table",
        ("V01", "V05", "V09"),
        ("invoice",),
        Style(money="us_symbol", date="long"),
        header="left",
        table="grid",
        labels=_labels(),
    ),
    Family(
        "T02",
        "two-column header invoice",
        "tuned",
        "table",
        ("V02", "V07", "V08", "V13"),
        ("invoice",),
        Style(money="us_plain", date="dmy_mon"),
        font="Helvetica",
        page="a4",
        header="two_col",
        table="ruled",
        accent=(0.1, 0.45, 0.35),
        labels=_labels(number="Invoice #", date="Invoice date", total="Amount due", tax="Tax"),
    ),
    Family(
        "T03",
        "receipt on a narrow roll",
        "tuned",
        "roll",
        ("V10", "V15"),
        ("receipt",),
        Style(money="us_symbol", date="mdy_mon", prints_tax_rate=False),
        font="Courier",
        page="roll",
        header="centered",
        table="none",
        labels=_labels(total="TOTAL", tax="TAX"),
    ),
    Family(
        "T04",
        "credit note",
        "tuned",
        "table",
        ("V01", "V14", "V16"),
        ("credit_note",),
        Style(money="us_symbol", date="iso", credit_style="paren"),
        font="Times-Roman",
        header="boxed",
        table="ruled",
        accent=(0.5, 0.15, 0.15),
        labels=_labels(number="Credit note no.", total="Total credit", date="Issued"),
    ),
    Family(
        "T05",
        "invoice with shipping and discount",
        "tuned",
        "table",
        ("V01", "V12", "V16"),
        ("invoice",),
        Style(money="us_code", date="mdy_mon", has_shipping=True, has_discount=True),
        header="banner",
        table="zebra",
        accent=(0.35, 0.2, 0.5),
        labels=_labels(shipping="Freight", discount="Volume discount", total="Balance due"),
    ),
    Family(
        "T06",
        "tax shown on every line",
        "tuned",
        "table",
        ("V05", "V11", "V12"),
        ("invoice",),
        Style(money="us_symbol", date="long", tax_mode="per_line"),
        header="left",
        table="grid",
        columns=("description", "qty", "unit_price", "line_tax", "amount"),
        accent=(0.45, 0.3, 0.1),
        labels=_labels(number="Order no."),
    ),
    Family(
        "T07",
        "no subtotal printed",
        "tuned",
        "table",
        ("V06", "V09", "V13"),
        ("invoice",),
        Style(money="us_nocomma", date="iso", prints_subtotal=False),
        font="Helvetica",
        header="two_col",
        table="none",
        accent=(0.2, 0.2, 0.2),
        labels=_labels(number="Reference", total="Please pay"),
    ),
    Family(
        "T08",
        "stacked utility bill",
        "tuned",
        "stacked",
        ("V03", "V04"),
        ("invoice",),
        Style(money="us_symbol", date="mdy_mon"),
        font="Helvetica",
        header="boxed",
        table="none",
        accent=(0.1, 0.35, 0.55),
        labels=_labels(number="Account bill no.", total="Total due", tax="State utility tax"),
    ),
    Family(
        "T09",
        "plain letter-style invoice",
        "tuned",
        "table",
        ("V06", "V09", "V14"),
        ("invoice",),
        Style(money="us_symbol", date="long", prints_tax_rate=False),
        font="Times-Roman",
        header="left",
        table="ruled",
        accent=(0.0, 0.0, 0.0),
        labels=_labels(number="Invoice Number", tax="Tax", total="Total Due"),
    ),
    Family(
        "T10",
        "dense repair order",
        "tuned",
        "table",
        ("V05", "V11"),
        ("invoice",),
        Style(money="us_plain", date="dmy_mon", tax_mode="per_line"),
        font="Courier",
        header="boxed",
        table="grid",
        columns=("qty", "description", "unit_price", "line_tax", "amount"),
        accent=(0.25, 0.25, 0.25),
        labels=_labels(number="RO No.", total="TOTAL DUE", tax="Tax"),
    ),
    Family(
        "T11",
        "sidebar invoice",
        "heldout",
        "sidebar",
        ("V01", "V07", "V16"),
        ("invoice",),
        Style(money="us_symbol", date="mdy_mon", has_shipping=True),
        font="Vera",
        header="left",
        table="ruled",
        accent=(0.0, 0.4, 0.4),
        labels=_labels(number="Inv. no", total="Total due"),
    ),
    Family(
        "T12",
        "billing statement with summary box",
        "heldout",
        "statement",
        ("V02", "V03", "V04"),
        ("invoice",),
        Style(money="us_symbol", date="dmy_mon"),
        font="Times-Roman",
        header="boxed",
        table="ruled",
        accent=(0.55, 0.25, 0.0),
        labels=_labels(number="Statement no.", total="Amount due now", tax="Taxes"),
    ),
    Family(
        "T13",
        "point-of-sale receipt on a full page",
        "heldout",
        "pos_page",
        ("V10", "V15"),
        ("receipt",),
        Style(money="us_plain", date="long", prints_tax_rate=False),
        font="Helvetica",
        page="a4",
        header="centered",
        table="none",
        labels=_labels(total="TOTAL", tax="Sales tax"),
    ),
    Family(
        "T14",
        "landscape invoice with wide columns",
        "heldout",
        "table",
        ("V05", "V09", "V12", "V13"),
        ("invoice",),
        Style(money="us_code", date="iso", has_discount=True),
        font="Helvetica",
        page="landscape",
        header="banner",
        table="zebra",
        accent=(0.5, 0.1, 0.3),
        labels=_labels(number="Document no.", total="Amount payable", discount="Less discount"),
    ),
    Family(
        "T15",
        "credit note in a statement layout",
        "heldout",
        "statement",
        ("V01", "V14", "V16"),
        ("credit_note",),
        Style(money="us_symbol", date="long", credit_style="paren"),
        font="Vera",
        header="boxed",
        table="ruled",
        accent=(0.3, 0.1, 0.1),
        labels=_labels(number="Credit memo", total="Credit due to you", date="Memo date"),
    ),
)

TUNED_FAMILIES = tuple(f for f in FAMILIES if f.split == "tuned")
HELDOUT_FAMILIES = tuple(f for f in FAMILIES if f.split == "heldout")


def family(family_id: str) -> Family:
    return next(f for f in FAMILIES if f.id == family_id)
