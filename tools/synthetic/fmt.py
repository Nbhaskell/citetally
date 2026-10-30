"""How values are printed on a document. Unambiguous dates only; several money styles."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from tools.synthetic.arith import minor_to_decimal

_SYMBOLS = {"USD": "$", "EUR": "€", "CAD": "CA$"}
_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]  # fmt: skip

DATE_STYLES = ("iso", "long", "dmy_mon", "mdy_mon")
MONEY_STYLES = ("us_symbol", "us_plain", "us_code", "us_nocomma", "eu_symbol", "paren")


def format_date(value: date, style: str) -> str:
    month = _MONTHS[value.month - 1]
    if style == "iso":
        return value.isoformat()
    if style == "long":
        return f"{month} {value.day}, {value.year}"
    if style == "dmy_mon":
        return f"{value.day} {month[:3]} {value.year}"
    if style == "mdy_mon":
        return f"{month[:3]} {value.day}, {value.year}"
    # Numeric slash dates (03/04/2026) are never generated: they can be read two ways.
    raise ValueError(f"Unknown or refused date style: {style!r}")


def _grouped(minor: int, thousands: str, decimal: str) -> str:
    whole, _, cents = f"{minor_to_decimal(minor):f}".partition(".")
    groups = f"{int(whole):,}".replace(",", thousands)
    return f"{groups}{decimal}{cents}"


def format_money(minor: int, style: str, currency: str) -> str:
    symbol = _SYMBOLS.get(currency, currency + " ")
    if style == "us_symbol":
        return f"{symbol}{_grouped(minor, ',', '.')}"
    if style == "us_plain":
        return _grouped(minor, ",", ".")
    if style == "us_code":
        return f"{currency} {_grouped(minor, ',', '.')}"
    if style == "us_nocomma":
        return f"{symbol}{_grouped(minor, '', '.')}"
    if style == "eu_symbol":
        return f"{_grouped(minor, '.', ',')} {_SYMBOLS.get(currency, currency)}"
    if style == "paren":
        return f"({symbol}{_grouped(minor, ',', '.')})"
    raise ValueError(f"Unknown money style: {style!r}")


def format_qty(qty: Decimal) -> str:
    text = f"{qty.normalize():f}"
    return text
