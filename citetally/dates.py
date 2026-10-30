"""Dates: read exactly the forms people print, flag what reads two ways, guess nothing.

Year-first dates are always year-month-day. A numeric date with a "/" or "-" ("03/04/2026") can
be day-first or month-first: when both readings are real dates and they differ, the date is
flagged ambiguous and the locale picks the reading used meanwhile (docs/TRD.md section 4.4).
Dots mean day.month.year. Only English month names are understood. Anything that is not exactly
one real date, such as a date with extra words around it, is not parsed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

# Which order the locale reads "03/04/2026": month first (US style) or day first.
_MONTH_FIRST = {"en-US", "en-CA", "en-PH"}
_DAY_FIRST = {
    "en-GB", "en-AU", "en-IN", "en-NZ", "en-IE",
    "de-DE", "fr-FR", "es-ES", "it-IT", "nl-NL", "pt-BR",
}  # fmt: skip
LOCALES = _MONTH_FIRST | _DAY_FIRST

_MONTHS = {
    name: number
    for number, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ],
        start=1,
    )
    for name in names
}
_YEAR_RANGE = range(1900, 2100)
_FLAGS = re.ASCII | re.IGNORECASE

_ISO = re.compile(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", re.ASCII)
_DOTTED = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", re.ASCII)
_NUMERIC = re.compile(r"^(\d{1,2})([/-])(\d{1,2})\2(\d{4}|\d{2})$", re.ASCII)
_DAY_MONTH_YEAR = re.compile(
    r"^(\d{1,2})(?:st|nd|rd|th)?[ \-]([a-z]{3,9})\.?[ \-](\d{4})$", _FLAGS
)  # 14 March 2026, 14th Mar 2026, 14-Mar-2026
_MONTH_DAY_YEAR = re.compile(r"^([a-z]{3,9})\.? (\d{1,2})(?:st|nd|rd|th)?,? (\d{4})$", _FLAGS)


@dataclass(frozen=True)
class ParsedDate:
    """A printed date read exactly. `readings` lists every real reading, the chosen one first."""

    value: date
    ambiguous: bool
    readings: tuple[date, ...]


def _make(year: int, month: int, day: int) -> date | None:
    if year not in _YEAR_RANGE:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _two_digit_year(text: str) -> int:
    year = int(text)
    if len(text) == 4:
        return year
    return 2000 + year if year < 70 else 1900 + year


def _single(value: date | None) -> ParsedDate | None:
    return None if value is None else ParsedDate(value, False, (value,))


def parse_date(text: str, locale: str = "en-US") -> ParsedDate | None:
    """A printed date such as "2026-03-14", "14 Mar 2026" or "03/14/2026". None if it is not one."""
    if locale not in LOCALES:
        raise ValueError(f"unknown locale {locale!r}; known: {', '.join(sorted(LOCALES))}")
    cleaned = re.sub(r"[ \xa0\u202f]+", " ", text).strip()

    if match := _ISO.match(cleaned):
        return _single(_make(int(match[1]), int(match[2]), int(match[3])))
    if match := _DOTTED.match(cleaned):
        return _single(_make(int(match[3]), int(match[2]), int(match[1])))
    if match := _DAY_MONTH_YEAR.match(cleaned):
        month = _MONTHS.get(match[2].lower())
        return _single(_make(int(match[3]), month, int(match[1])) if month else None)
    if match := _MONTH_DAY_YEAR.match(cleaned):
        month = _MONTHS.get(match[1].lower())
        return _single(_make(int(match[3]), month, int(match[2])) if month else None)
    if match := _NUMERIC.match(cleaned):
        first, second = int(match[1]), int(match[3])
        year = _two_digit_year(match[4])
        month_first = _make(year, first, second)
        day_first = _make(year, second, first)
        if month_first and day_first and month_first != day_first:
            order = (month_first, day_first) if locale in _MONTH_FIRST else (day_first, month_first)
            return ParsedDate(order[0], True, order)
        real = month_first or day_first
        return _single(real)
    return None
