"""Money: exact decimals in, integer minor units out, rounding half up. Never a float.

Printed amounts are parsed from the text on the page. A string that cannot be read exactly is not
parsed (nothing is guessed or corrected), and a string that reads two ways is flagged so the
reviewer can confirm it; the business's locale decides which reading is used meanwhile.
See docs/TRD.md section 4.4 and docs/BACKEND_SCHEMA.md ("Money is never a float").

Reading rules, in short:
  * Both "." and "," present: the last one is the decimal mark, the other groups thousands.
  * One of them repeated ("1.234.567"): grouping only, whole number.
  * One of them once, followed by a number of digits other than three: a decimal mark.
  * One of them once, followed by exactly three digits ("1.234"): reads two ways. Amounts are
    flagged ambiguous and the locale picks; quantities and unit prices follow the locale quietly,
    because three decimals are normal there (fuel is sold by the thousandth of a gallon).
  * Spaces, no-break spaces and apostrophes group thousands only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

_ONE = Decimal(1)
_EXPONENTS = {"JPY": 0, "KRW": 0, "VND": 0, "BHD": 3, "KWD": 3, "JOD": 3, "OMR": 3, "TND": 3}

# (decimal mark, grouping mark)
LOCALES: dict[str, tuple[str, str]] = {
    "en-US": (".", ","), "en-CA": (".", ","), "en-GB": (".", ","), "en-AU": (".", ","),
    "de-DE": (",", "."), "es-ES": (",", "."), "it-IT": (",", "."), "nl-NL": (",", "."),
    "pt-BR": (",", "."), "fr-FR": (",", " "),
}  # fmt: skip

_CODES = {"USD", "EUR", "CAD", "GBP", "AUD", "JPY", "CHF", "MXN", "NZD", "KWD", "BHD"}
_SYMBOLS = {
    "US$": "USD", "CA$": "CAD", "C$": "CAD", "AU$": "AUD", "A$": "AUD",
    "€": "EUR", "£": "GBP", "¥": "JPY",
}  # fmt: skip
_TOKEN = r"(?:US\$|CA\$|C\$|AU\$|A\$|\$|€|£|¥|[A-Z]{3})"
_MINUS = r"[\-\u2212]"
_SEPARATORS = ".,' \xa0\u202f"
_NUMBER = r"(?:[0-9][0-9.,' \xa0\u202f]*[0-9]|[0-9]|\.[0-9]+|[0-9]+\.)"
_AMOUNT = re.compile(
    rf"^\s*(?P<open>\()?\s*(?P<s1>[+]|{_MINUS})?\s*(?P<c1>{_TOKEN})?\s*(?P<s2>[+]|{_MINUS})?\s*"
    rf"(?P<num>{_NUMBER})\s*(?P<s3>{_MINUS})?\s*(?P<c2>{_TOKEN})?\s*(?P<close>\))?\s*$"
)
_RATE = re.compile(rf"^\s*(?P<num>{_NUMBER})\s*%\s*$")


@dataclass(frozen=True)
class ParsedAmount:
    """A printed number read exactly. `readings` lists every plausible value, chosen one first."""

    value: Decimal
    currency: str | None
    ambiguous: bool
    readings: tuple[Decimal, ...]


# ---- rounding and minor units -----------------------------------------------------------------


def _check_decimal(value: object, what: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, Decimal | int):
        raise TypeError(f"{what} must be a Decimal or an integer, not {type(value).__name__}")
    return Decimal(value)


def exponent(currency: str) -> int:
    """How many decimal places the currency's minor unit has (2 for dollars and euros)."""
    return _EXPONENTS.get(currency, 2)


def round_half_up(value: Decimal, places: int) -> Decimal:
    exact = _check_decimal(value, "value")
    return exact.quantize(_ONE.scaleb(-places), rounding=ROUND_HALF_UP)


def to_minor(amount: Decimal, currency: str = "USD") -> int:
    """Major units to whole minor units (cents), half up."""
    exact = _check_decimal(amount, "amount")
    return int(exact.scaleb(exponent(currency)).quantize(_ONE, rounding=ROUND_HALF_UP))


def from_minor(minor: int, currency: str = "USD") -> Decimal:
    if isinstance(minor, bool) or not isinstance(minor, int):
        raise TypeError(f"minor units must be an integer, not {type(minor).__name__}")
    return Decimal(minor).scaleb(-exponent(currency))


def line_amount_minor(quantity: Decimal, unit_price: Decimal, currency: str = "USD") -> int:
    """Quantity times unit price, rounded once, half up, to the currency's minor unit."""
    product = _check_decimal(quantity, "quantity") * _check_decimal(unit_price, "unit price")
    return to_minor(product, currency)


def tax_minor(base_minor: int, rate: Decimal) -> int:
    """Tax on a base amount in minor units: base times rate, half up."""
    if isinstance(base_minor, bool) or not isinstance(base_minor, int):
        raise TypeError("the tax base must be an integer number of minor units")
    exact = Decimal(base_minor) * _check_decimal(rate, "rate")
    return int(exact.quantize(_ONE, rounding=ROUND_HALF_UP))


# ---- reading printed numbers ------------------------------------------------------------------


def _locale(name: str) -> tuple[str, str]:
    if name not in LOCALES:
        raise ValueError(f"unknown locale {name!r}; known: {', '.join(sorted(LOCALES))}")
    return LOCALES[name]


def _grouped(groups: list[str]) -> bool:
    """Thousands groups: the first has one to three digits (no leading zero), the rest three."""
    first, rest = groups[0], groups[1:]
    if not (1 <= len(first) <= 3) or (len(first) > 1 and first[0] == "0"):
        return False
    if first == "0" and rest:
        return False
    return all(len(group) == 3 for group in rest)


def _split(text: str) -> tuple[list[str], list[str]]:
    groups = re.split(f"[{re.escape(_SEPARATORS)}]", text)
    marks = re.findall(f"[{re.escape(_SEPARATORS)}]", text)
    return groups, marks


def _read_number(text: str, decimal_mark: str) -> tuple[Decimal, tuple[Decimal, ...], bool] | None:
    """Read digits and separators exactly. Returns (value, all readings, lone-separator flag)."""
    if text.startswith("."):
        text = "0" + text
    if text.endswith(".") and text.count(".") == 1 and "," not in text:
        text = text[:-1]
    groups, marks = _split(text)
    if any(not group.isdigit() or not group.isascii() for group in groups):
        return None
    if not marks:
        value = Decimal(groups[0])
        return value, (value,), False

    dots_commas = [m for m in marks if m in ".,"]
    spacers = [m for m in marks if m not in ".,"]
    if len(set(spacers)) > 1:
        return None

    if not dots_commas:  # only spaces or apostrophes
        if not _grouped(groups):
            return None
        value = Decimal("".join(groups))
        return value, (value,), False

    kinds = set(dots_commas)
    if len(kinds) == 2:
        mark = dots_commas[-1]  # the last mark is the decimal mark
        if dots_commas.count(mark) != 1 or marks[-1] != mark:
            return None
        other = ({".", ","} - {mark}).pop()
        before_marks = marks[:-1]
        if any(m != other and m in ".," for m in before_marks) or len(set(before_marks)) > 1:
            return None
        if not _grouped(groups[:-1]):
            return None
        value = Decimal("".join(groups[:-1]) + "." + groups[-1])
        return value, (value,), False

    mark = dots_commas[0]
    if len(dots_commas) >= 2:  # a repeated mark can only group thousands
        if spacers or not _grouped(groups):
            return None
        value = Decimal("".join(groups))
        return value, (value,), False

    # one decimal-or-grouping mark, once
    index = marks.index(mark)
    before, after = groups[: index + 1], groups[index + 1]
    if len(groups) != index + 2:  # more digits after a space or apostrophe: not a known layout
        return None
    before_ok = (
        _grouped(before) and before[0][0] != "0" and all(m not in ".," for m in marks[:index])
    )
    if len(after) == 3 and before_ok:
        grouping_reading = Decimal("".join(before) + after)
        decimal_reading = Decimal("".join(before) + "." + after)
        if mark == decimal_mark:
            return decimal_reading, (decimal_reading, grouping_reading), True
        return grouping_reading, (grouping_reading, decimal_reading), True
    value = Decimal("".join(before) + "." + after)
    return value, (value,), False


def _resolve_currency(token: str | None, dollar: str) -> str | bool | None:
    """The currency a symbol or code names; False when the token is not a currency."""
    if token is None:
        return None
    if token == "$":
        return dollar
    if token in _SYMBOLS:
        return _SYMBOLS[token]
    return token if token in _CODES else False


def _parse(text: str, locale: str, dollar: str, flag_lone_marks: bool) -> ParsedAmount | None:
    decimal_mark, _ = _locale(locale)
    match = _AMOUNT.match(text)
    if match is None:
        return None
    if (match["open"] is None) != (match["close"] is None):
        return None
    if match["c1"] and match["c2"]:
        return None
    currency = _resolve_currency(match["c1"] or match["c2"], dollar)
    if currency is False:
        return None
    signs = [match[name] for name in ("s1", "s2", "s3") if match[name]]
    negatives = sum(1 for s in signs if s != "+") + (1 if match["open"] else 0)
    if negatives > 1 or (negatives and "+" in signs):
        return None
    read = _read_number(match["num"], decimal_mark)
    if read is None:
        return None
    value, readings, lone = read
    if negatives:
        value, readings = -value, tuple(-r for r in readings)
    ambiguous = lone and flag_lone_marks
    return ParsedAmount(
        value=value,
        currency=currency if isinstance(currency, str) else None,
        ambiguous=ambiguous,
        readings=readings if ambiguous else (value,),
    )


def parse_money(text: str, locale: str = "en-US", dollar: str = "USD") -> ParsedAmount | None:
    """An amount as printed: "$1,234.56", "1.234,56 EUR", "(45.00)". None if it is not one.

    A bare "$" means `dollar` (the business's dollar). A lone separator before exactly three
    digits ("1.234") reads two ways: the result is flagged and the locale picks the value.
    """
    return _parse(text, locale, dollar, flag_lone_marks=True)


def parse_decimal(text: str, locale: str = "en-US", dollar: str = "USD") -> ParsedAmount | None:
    """A quantity or unit price as printed, keeping every digit ("11.699", "0.1475")."""
    return _parse(text, locale, dollar, flag_lone_marks=False)


def parse_rate(text: str, locale: str = "en-US") -> Decimal | None:
    """A printed percentage as an exact fraction ("7%" is 0.07). Without a % sign: not guessed."""
    decimal_mark, _ = _locale(locale)
    match = _RATE.match(text)
    if match is None:
        return None
    read = _read_number(match["num"], decimal_mark)
    if read is None:
        return None
    return read[0].scaleb(-2)
