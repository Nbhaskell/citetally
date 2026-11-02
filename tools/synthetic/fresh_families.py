"""Ten more invented layouts, for a second business (`universe/facts_ridge.json`).

These families exist so the system can be tested on documents that were not written alongside it:
other vendors and items, and layouts with the things real documents have that the first fifteen
lack: descriptions that wrap, a total printed twice, stamps, pen annotations, remittance stubs,
account summaries with other numbers and dates beside the real ones, white text on dark bands,
watermarks, barcodes.

    dev2    T16 to T20  used to develop and measure fixes
    sealed  T21 to T25  written down and hashed before any fix, run once at the end

Nothing printed beside the document's own values is in the answer key, and every distractor carries
a label that names what it is (customer ID, account, order ref), so a careful reader can tell it
from the invoice number, the date or the total.
"""

from __future__ import annotations

from dataclasses import dataclass

from tools.synthetic.families import Family, _labels
from tools.synthetic.model import Style


@dataclass(frozen=True)
class FreshFamily(Family):
    """A family plus what the new renderer needs: an engine, a type size and extras."""

    engine: str = "dense"
    size: float = 9.0
    features: tuple[str, ...] = ()


FRESH_SPLITS = ("dev2", "sealed")

FRESH_FAMILIES: tuple[FreshFamily, ...] = (
    # ---- dev2 -------------------------------------------------------------------------------
    FreshFamily(
        "T16",
        "dense invoice, dark header band",
        "dev2",
        "dense",
        ("V01", "V03", "V07", "V12"),
        ("invoice",),
        Style(money="us_symbol", date="mdy_mon", has_shipping=True, has_discount=True),
        font="Helvetica",
        header="banner",
        table="zebra",
        accent=(0.12, 0.22, 0.38),
        labels=_labels(number="Invoice #", total="Balance due", due="Payment due", tax="Tax"),
        engine="dense",
        size=8.0,
        features=("remit", "ship_to", "terms", "stamp"),
    ),
    FreshFamily(
        "T17",
        "airy invoice with an amount-due box",
        "dev2",
        "airy",
        ("V02", "V11", "V14", "V09"),
        ("invoice",),
        Style(money="us_plain", date="long", prints_tax_rate=False),
        font="Times-Roman",
        header="left",
        table="none",
        accent=(0.35, 0.2, 0.1),
        labels=_labels(number="Invoice number", total="Total due", date="Invoice date"),
        engine="airy",
        size=10.5,
        features=("due_box", "order_dates", "scrawl"),
    ),
    FreshFamily(
        "T18",
        "repair ticket in labour and parts sections",
        "dev2",
        "sections",
        ("V04", "V12", "V15", "V07"),
        ("invoice",),
        Style(money="us_nocomma", date="dmy_mon", prints_tax_rate=True),
        font="Helvetica",
        header="boxed",
        table="ruled",
        accent=(0.5, 0.1, 0.1),
        labels=_labels(number="Ticket no.", total="Amount due", date="Date of service"),
        engine="sections",
        size=9.0,
        features=("order_dates", "stamp"),
    ),
    FreshFamily(
        "T19",
        "utility bill with an account summary",
        "dev2",
        "bill",
        ("V05", "V06", "V09", "V15"),
        ("invoice",),
        Style(money="us_symbol", date="iso", prints_subtotal=False),
        font="Helvetica",
        header="banner",
        table="ruled",
        accent=(0.05, 0.35, 0.5),
        labels=_labels(
            number="Bill no.",
            total="Total amount due",
            date="Bill date",
            tax="State utility tax",
            subtotal="Current charges",
        ),
        engine="bill",
        size=9.0,
        features=("account_box", "usage_bars", "period"),
    ),
    FreshFamily(
        "T20",
        "till receipt with a barcode and card slip",
        "dev2",
        "till",
        ("V10", "V13", "V16"),
        ("receipt",),
        Style(money="us_plain", date="mdy_mon", prints_subtotal=False),
        font="Courier",
        page="roll",
        header="centered",
        accent=(0.2, 0.2, 0.2),
        labels=_labels(number="Receipt", total="TOTAL", tax="TAX", subtotal="SUBTOTAL"),
        engine="till",
        size=7.5,
        features=("barcode", "card", "scrawl"),
    ),
    # ---- sealed -----------------------------------------------------------------------------
    FreshFamily(
        "T21",
        "landscape invoice with a tax column and a tear-off stub",
        "sealed",
        "dense",
        ("V02", "V08", "V14", "V03"),
        ("invoice",),
        Style(money="us_code", date="dmy_mon", tax_mode="per_line", has_shipping=True),
        font="Helvetica",
        page="landscape",
        header="two_col",
        table="grid",
        columns=("description", "qty", "unit_price", "line_tax", "amount"),
        accent=(0.2, 0.4, 0.2),
        labels=_labels(number="Inv. ref", total="Total payable", line_tax="Tax"),
        engine="dense",
        size=8.5,
        features=("stub", "terms", "scrawl"),
    ),
    FreshFamily(
        "T22",
        "letterhead invoice with a watermark",
        "sealed",
        "airy",
        ("V01", "V09", "V11", "V07"),
        ("invoice",),
        Style(money="us_symbol", date="iso", has_discount=True),
        font="Vera",
        page="a4",
        header="centered",
        table="zebra",
        accent=(0.25, 0.25, 0.25),
        labels=_labels(number="No.", total="Please pay", due="Pay by", tax="Sales tax"),
        engine="airy",
        size=9.5,
        features=("watermark", "order_dates", "stamp"),
    ),
    FreshFamily(
        "T23",
        "monthly statement with ageing figures",
        "sealed",
        "bill",
        ("V07", "V03", "V12", "V15"),
        ("invoice",),
        Style(money="us_plain", date="mdy_mon"),
        font="Times-Roman",
        page="a4",
        header="boxed",
        table="grid",
        accent=(0.4, 0.15, 0.4),
        labels=_labels(
            number="Statement ref",
            total="Amount now due",
            date="Statement date",
            subtotal="This period",
        ),
        engine="bill",
        size=9.5,
        features=("account_box", "ageing", "period", "scrawl"),
    ),
    FreshFamily(
        "T24",
        "receipt book page with a rubber stamp",
        "sealed",
        "pad",
        ("V13", "V10", "V16"),
        ("receipt",),
        Style(money="us_symbol", date="long", prints_tax_rate=False),
        font="Courier",
        header="left",
        table="grid",
        accent=(0.6, 0.1, 0.1),
        labels=_labels(number="Receipt No.", total="Total", tax="Tax"),
        engine="pad",
        size=10.0,
        features=("stamp", "scrawl", "barcode"),
    ),
    FreshFamily(
        "T25",
        "credit memo in brackets",
        "sealed",
        "dense",
        ("V01", "V02", "V03", "V07", "V08", "V12"),
        ("credit_note",),
        Style(money="us_symbol", date="long", credit_style="paren"),
        font="Times-Roman",
        page="a4",
        header="left",
        table="ruled",
        accent=(0.1, 0.3, 0.45),
        labels=_labels(number="Credit memo", total="Credit total", date="Memo date"),
        engine="dense",
        size=9.0,
        features=("terms", "ship_to", "stamp"),
    ),
)

BY_ID = {f.id: f for f in FRESH_FAMILIES}


def families_of(split: str) -> tuple[FreshFamily, ...]:
    return tuple(f for f in FRESH_FAMILIES if f.split == split)
