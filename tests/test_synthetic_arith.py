"""Exact arithmetic and printing for generated documents. No float ever touches an amount."""

from datetime import date
from decimal import Decimal

import pytest

from tools.synthetic.arith import line_amount_minor, minor_to_decimal, tax_minor, to_minor
from tools.synthetic.fmt import format_date, format_money, format_qty


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        ("0.004", 0),
        ("0.005", 1),  # half rounds up
        ("0.015", 2),
        ("0.025", 3),  # banker's rounding would give 2
        ("2.675", 268),
        ("1234.5", 123450),
        ("0", 0),
    ],
)
def test_to_minor_rounds_half_up(amount: str, expected: int) -> None:
    assert to_minor(Decimal(amount)) == expected


def test_line_amount_multiplies_exact_decimals() -> None:
    assert line_amount_minor(Decimal("4"), Decimal("38.00")) == 15200
    assert line_amount_minor(Decimal("1342"), Decimal("0.1475")) == 19795  # 197.945 -> 197.95
    assert line_amount_minor(Decimal("13.5"), Decimal("3.789")) == 5115  # 51.1515 -> 51.15


def test_tax_is_rate_times_base_rounded_half_up_to_the_minor_unit() -> None:
    assert tax_minor(19450, Decimal("0.07")) == 1362  # 1361.5 rounds up
    assert tax_minor(0, Decimal("0.07")) == 0
    assert tax_minor(10000, Decimal("0")) == 0
    assert tax_minor(1, Decimal("0.5")) == 1  # 0.5 rounds up


def test_minor_to_decimal_has_two_places_and_is_exact() -> None:
    assert minor_to_decimal(21155) == Decimal("211.55")
    assert str(minor_to_decimal(5)) == "0.05"
    assert isinstance(minor_to_decimal(1), Decimal)


@pytest.mark.parametrize(
    ("minor", "style", "currency", "expected"),
    [
        (21155, "us_symbol", "USD", "$211.55"),
        (123456789, "us_symbol", "USD", "$1,234,567.89"),
        (123456, "us_plain", "USD", "1,234.56"),
        (123456, "us_code", "USD", "USD 1,234.56"),
        (123456, "us_nocomma", "USD", "$1234.56"),
        (5, "us_symbol", "USD", "$0.05"),
        (123456, "us_symbol", "CAD", "CA$1,234.56"),
        (123456, "us_symbol", "EUR", "€1,234.56"),
        (123456, "eu_symbol", "EUR", "1.234,56 €"),
        (6400, "eu_symbol", "EUR", "64,00 €"),
        (4500, "paren", "USD", "($45.00)"),
    ],
)
def test_money_formats(minor: int, style: str, currency: str, expected: str) -> None:
    assert format_money(minor, style, currency) == expected


def test_unknown_money_style_is_an_error() -> None:
    with pytest.raises(ValueError, match="style"):
        format_money(100, "nope", "USD")


@pytest.mark.parametrize(
    ("style", "expected"),
    [
        ("iso", "2026-03-04"),
        ("long", "March 4, 2026"),
        ("dmy_mon", "4 Mar 2026"),
        ("mdy_mon", "Mar 4, 2026"),
    ],
)
def test_dates_are_always_printed_unambiguously(style: str, expected: str) -> None:
    assert format_date(date(2026, 3, 4), style) == expected


def test_numeric_slash_dates_are_refused_because_they_can_be_misread() -> None:
    with pytest.raises(ValueError, match="style"):
        format_date(date(2026, 3, 4), "us_numeric")


@pytest.mark.parametrize(
    ("qty", "expected"), [("4", "4"), ("1.50", "1.5"), ("0.25", "0.25"), ("12.000", "12")]
)
def test_quantities_print_without_trailing_zeros(qty: str, expected: str) -> None:
    assert format_qty(Decimal(qty)) == expected
