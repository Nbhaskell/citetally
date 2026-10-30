"""Exact money arithmetic for the generator. Decimal only, rounding half up.

Deliberately separate from the product's own money code (see docs/DECISIONS.md, D-017).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_CENT = Decimal("0.01")


def to_minor(amount: Decimal) -> int:
    """Major units (dollars) to integer minor units (cents), half up."""
    return int((amount / _CENT).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def minor_to_decimal(minor: int) -> Decimal:
    return (Decimal(minor) * _CENT).quantize(_CENT)


def line_amount_minor(qty: Decimal, unit_price: Decimal) -> int:
    return to_minor(qty * unit_price)


def tax_minor(base_minor: int, rate: Decimal) -> int:
    return int((Decimal(base_minor) * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
