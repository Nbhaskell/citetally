"""Money: exact decimals in, integer minor units out, half up, and nothing is ever guessed."""

import random
import re
from decimal import Decimal
from pathlib import Path

import pytest

from citetally import money
from citetally.money import ParsedAmount, parse_decimal, parse_money, parse_rate
from tools.synthetic import arith as generator_arith
from tools.synthetic.fmt import MONEY_STYLES, format_money


def amount(text: str, locale: str = "en-US") -> Decimal | None:
    parsed = parse_money(text, locale)
    return None if parsed is None else parsed.value


# ---- rounding and minor units -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "places", "expected"),
    [
        ("0.004", 2, "0.00"),
        ("0.005", 2, "0.01"),  # half rounds up, not to even
        ("0.015", 2, "0.02"),
        ("0.025", 2, "0.03"),
        ("2.675", 2, "2.68"),
        ("-0.005", 2, "-0.01"),  # and away from zero for negatives
        ("1234.5", 0, "1235"),
        ("1.2345", 3, "1.235"),
    ],
)
def test_rounding_is_half_up(value: str, places: int, expected: str) -> None:
    assert money.round_half_up(Decimal(value), places) == Decimal(expected)


@pytest.mark.parametrize(
    ("value", "currency", "minor"),
    [
        ("211.55", "USD", 21155),
        ("0.005", "USD", 1),
        ("1234", "JPY", 1234),  # no minor unit
        ("1234.5", "JPY", 1235),
        ("1.2345", "KWD", 1235),  # three decimal places
        ("64", "EUR", 6400),
        ("-45", "CAD", -4500),
    ],
)
def test_to_minor_uses_the_currency_exponent(value: str, currency: str, minor: int) -> None:
    assert money.to_minor(Decimal(value), currency) == minor


def test_minor_units_round_trip_exactly() -> None:
    for minor in (0, 1, 5, 99, 100, 21155, 123456789, -250):
        assert money.to_minor(money.from_minor(minor, "USD"), "USD") == minor
    assert money.from_minor(5, "USD") == Decimal("0.05")
    assert money.from_minor(1234, "JPY") == Decimal("1234")
    assert str(money.from_minor(21155, "USD")) == "211.55"


def test_floats_are_refused_everywhere() -> None:
    with pytest.raises(TypeError):
        money.to_minor(2.5, "USD")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        money.from_minor(2.5, "USD")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        money.round_half_up(2.5, 2)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        money.from_minor(True, "USD")  # a bool is not an amount
    with pytest.raises(TypeError):
        money.line_amount_minor(Decimal("2"), 1.5, "USD")  # type: ignore[arg-type]


def test_no_floating_point_exists_in_the_module() -> None:
    """Rule: money is never a float. The module neither calls float() nor annotates with it."""
    source = Path(money.__file__).read_text(encoding="utf-8")
    assert not re.search(r"\bfloat\b", source.split('"""', 2)[2].replace("never a float", ""))


def test_line_amount_multiplies_exactly_and_rounds_once() -> None:
    assert money.line_amount_minor(Decimal("4"), Decimal("38.00"), "USD") == 15200
    assert money.line_amount_minor(Decimal("1342"), Decimal("0.1475"), "USD") == 19795
    assert money.line_amount_minor(Decimal("11.699"), Decimal("4.159"), "USD") == 4866
    assert money.line_amount_minor(Decimal("0"), Decimal("9.99"), "USD") == 0


def test_tax_is_rate_times_base_rounded_half_up() -> None:
    assert money.tax_minor(19450, Decimal("0.07")) == 1362  # 1361.5
    assert money.tax_minor(10000, Decimal("0")) == 0
    assert money.tax_minor(1, Decimal("0.5")) == 1
    assert money.tax_minor(-19450, Decimal("0.07")) == -1362


def test_the_product_arithmetic_agrees_with_the_independent_test_data_arithmetic() -> None:
    """Two separate implementations must give the same answer on random inputs."""
    rng = random.Random(7)
    for _ in range(3000):
        qty = Decimal(rng.randint(1, 5000)) / Decimal(rng.choice([1, 10, 100, 1000]))
        price = Decimal(rng.randint(1, 900000)) / Decimal(rng.choice([100, 1000, 10000]))
        assert money.line_amount_minor(qty, price, "USD") == generator_arith.line_amount_minor(
            qty, price
        )
        base = rng.randint(0, 5_000_000)
        rate = Decimal(rng.randint(0, 2500)) / Decimal(10000)
        assert money.tax_minor(base, rate) == generator_arith.tax_minor(base, rate)


# ---- parsing amounts --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("$211.55", "211.55"),
        ("211.55", "211.55"),
        ("$1,234.56", "1234.56"),
        ("1,234,567.89", "1234567.89"),
        ("$1234.56", "1234.56"),
        ("USD 1,234.56", "1234.56"),
        ("1,234.56 USD", "1234.56"),
        ("  $ 5.00  ", "5.00"),
        ("$0.05", "0.05"),
        (".5", "0.5"),
        ("5.", "5"),
        ("$5", "5"),
        ("1,000", "1000"),
        ("0", "0"),
        ("$0.00", "0.00"),
    ],
)
def test_us_style_amounts(text: str, expected: str) -> None:
    assert amount(text) == Decimal(expected)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.234,56", "1234.56"),
        ("64,00 €", "64.00"),
        ("€64,00", "64.00"),
        ("1 234,56", "1234.56"),
        ("1\xa0234,56", "1234.56"),
        ("1\u202f234,56", "1234.56"),
        ("1'234.56", "1234.56"),
        ("1.234.567,89", "1234567.89"),
        ("12,50", "12.50"),
        ("1.234.567", "1234567"),
    ],
)
def test_european_and_swiss_style_amounts_parse_whatever_the_locale(
    text: str, expected: str
) -> None:
    assert amount(text, "en-US") == Decimal(expected)
    assert amount(text, "de-DE") == Decimal(expected)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("($45.00)", "-45.00"),
        ("(45.00)", "-45.00"),
        ("-$5.00", "-5.00"),
        ("$-5.00", "-5.00"),
        ("\u2212$5.00", "-5.00"),  # a true minus sign
        ("5.00-", "-5.00"),
        ("-1,234.56", "-1234.56"),
        ("(1.234,56 €)", "-1234.56"),
        ("+5.00", "5.00"),
    ],
)
def test_negatives_in_parentheses_or_with_a_minus(text: str, expected: str) -> None:
    assert amount(text) == Decimal(expected)


@pytest.mark.parametrize(
    ("text", "currency"),
    [
        ("$5.00", "USD"),
        ("US$5.00", "USD"),
        ("CA$5.00", "CAD"),
        ("C$5.00", "CAD"),
        ("€5,00", "EUR"),
        ("5,00 €", "EUR"),
        ("£5.00", "GBP"),
        ("EUR 5,00", "EUR"),
        ("5.00 CAD", "CAD"),
        ("USD5.00", "USD"),
        ("5.00", None),
    ],
)
def test_currency_symbols_and_codes_are_recognised(text: str, currency: str | None) -> None:
    parsed = parse_money(text)
    assert parsed is not None and parsed.currency == currency


def test_a_bare_dollar_sign_means_the_configured_dollar() -> None:
    parsed = parse_money("$5.00", dollar="CAD")
    assert parsed is not None and parsed.currency == "CAD"
    explicit = parse_money("US$5.00", dollar="CAD")
    assert explicit is not None and explicit.currency == "USD"


@pytest.mark.parametrize(
    "text",
    [
        "", "   ", "N/A", "none", "abc", "$", "--5", "5..00", "1,23,456", "12.34.56",
        "5 5", "$5.00 and more", "1O0.00", "l00", "1,234,56", "1.234.56", "5,00,00", "(5.00",
        "5.00)", "$-(5)", "0x10", "1e3", "NaN", "Infinity", "1_000",
    ],
)  # fmt: skip
def test_text_that_is_not_a_clean_amount_is_not_parsed_or_corrected(text: str) -> None:
    assert parse_money(text) is None


def test_a_lookalike_letter_is_never_silently_fixed() -> None:
    assert parse_money("1O0.00") is None  # letter O for zero
    assert parse_money("l00.00") is None  # letter l for one


@pytest.mark.parametrize(
    ("text", "locale", "chosen", "other"),
    [
        ("1.234", "en-US", "1.234", "1234"),  # the example in docs/TRD.md section 4.4
        ("1,234", "en-US", "1234", "1.234"),
        ("1.234", "de-DE", "1234", "1.234"),
        ("1,234", "de-DE", "1.234", "1234"),
        ("$5.000", "en-US", "5.000", "5000"),
        ("999,999", "en-US", "999999", "999.999"),
    ],
)
def test_a_lone_separator_before_three_digits_is_flagged_and_read_by_locale(
    text: str, locale: str, chosen: str, other: str
) -> None:
    parsed = parse_money(text, locale)
    assert parsed is not None
    assert parsed.ambiguous is True
    assert parsed.value == Decimal(chosen)
    assert parsed.readings == (Decimal(chosen), Decimal(other))


@pytest.mark.parametrize(
    "text",
    ["1,234.56", "1.234,56", "12.50", "12,50", "1,234,567", "$5.5", "0.123", "1 234", "12.5"],
)
def test_unambiguous_amounts_are_not_flagged(text: str) -> None:
    parsed = parse_money(text)
    assert parsed is not None and parsed.ambiguous is False and len(parsed.readings) == 1


def test_leading_zero_fractions_are_decimals_not_thousands() -> None:
    parsed = parse_money("0.123")
    assert parsed is not None and parsed.ambiguous is False and parsed.value == Decimal("0.123")


def test_unknown_locales_are_an_error() -> None:
    with pytest.raises(ValueError, match="locale"):
        parse_money("5.00", "xx-XX")


def test_parsed_amounts_carry_exact_decimals_only() -> None:
    parsed = parse_money("$1,234.56")
    assert isinstance(parsed, ParsedAmount) and isinstance(parsed.value, Decimal)
    assert str(parsed.value) == "1234.56"
    zeros = parse_money("5.10")
    assert zeros is not None and str(zeros.value) == "5.10"  # keeps its trailing zero


def test_to_minor_from_a_parsed_amount() -> None:
    parsed = parse_money("$211.55")
    assert parsed is not None
    assert money.to_minor(parsed.value, parsed.currency or "USD") == 21155
    credit = parse_money("($45.00)")
    assert credit is not None and money.to_minor(credit.value, "USD") == -4500


@pytest.mark.parametrize("style", MONEY_STYLES)
def test_everything_the_test_data_prints_parses_back_exactly(style: str) -> None:
    """Round trip against the independent printer used to make the golden set."""
    rng = random.Random(11)
    currency = "EUR" if style == "eu_symbol" else "USD"
    for _ in range(1500):
        minor = rng.choice([rng.randint(0, 999), rng.randint(0, 99_999_999)])
        printed = format_money(minor, style, currency)
        parsed = parse_money(printed)
        assert parsed is not None, printed
        expected = -minor if style == "paren" else minor
        assert money.to_minor(parsed.value, currency) == expected, printed
        assert parsed.ambiguous is False, printed


# ---- quantities, unit prices, rates -----------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("4", "4"),
        ("11.699", "11.699"),  # fuel is sold by the thousandth of a gallon
        ("1,500", "1500"),
        ("0.1475", "0.1475"),
        ("2.50", "2.50"),
        ("1.234,5", "1234.5"),
        ("-3", "-3"),
        ("(3)", "-3"),
    ],
)
def test_quantities_and_unit_prices_keep_every_digit(text: str, expected: str) -> None:
    parsed = parse_decimal(text)
    assert parsed is not None and parsed.value == Decimal(expected)
    assert str(parsed.value) == expected


def test_a_lone_separator_in_a_quantity_follows_the_locale_without_a_flag() -> None:
    en = parse_decimal("11.699", "en-US")
    de = parse_decimal("11.699", "de-DE")
    assert en is not None and en.value == Decimal("11.699") and en.ambiguous is False
    assert de is not None and de.value == Decimal("11699") and de.ambiguous is False


def test_quantities_may_carry_a_currency_symbol_when_they_are_prices() -> None:
    parsed = parse_decimal("$4.159")
    assert parsed is not None and parsed.value == Decimal("4.159") and parsed.currency == "USD"


@pytest.mark.parametrize("text", ["", "two", "1.2.3.4", "5%%", "1,23,456", "NaN"])
def test_bad_quantities_are_not_parsed(text: str) -> None:
    assert parse_decimal(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("7%", "0.07"),
        ("7.00%", "0.0700"),
        ("8.25 %", "0.0825"),
        ("8,25 %", "0.0825"),
        ("19%", "0.19"),
        ("0%", "0"),
        ("0.5%", "0.005"),
    ],
)
def test_percentages_become_exact_fractions(text: str, expected: str) -> None:
    assert parse_rate(text) == Decimal(expected)


@pytest.mark.parametrize("text", ["7", "0.07", "", "%", "seven %", "-%", "7%%", "1,2,3%"])
def test_a_rate_without_a_percent_sign_is_not_guessed(text: str) -> None:
    assert parse_rate(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Pay this amount     CAD  548.50", {"CAD"}),
        ("CA$13.75 and CA$11.34", {"CAD"}),
        ("548.50 CAD", {"CAD"}),
        ("US$12.00", {"USD"}),
        ("USD 5.00 and CAD 4.00", {"USD", "CAD"}),
        ("Total $548.50", set()),
        ("All amounts are shown in USD", set()),
        ("ABA 000-000-000", set()),
        ("SCAD 5", set()),
        ("£12.50 and ¥300 and €4,00", set()),  # a scan often reads a "$" as one of these
    ],
)
def test_currencies_beside_amounts_reads_codes_and_prefixed_symbols_only(
    text: str, expected: set[str]
) -> None:
    assert money.currencies_beside_amounts(text) == expected
