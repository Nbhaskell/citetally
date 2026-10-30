"""Dates: every printed form is read exactly, and anything that reads two ways is flagged."""

import random
from datetime import date

import pytest

from citetally.dates import ParsedDate, parse_date
from tools.synthetic.fmt import DATE_STYLES, format_date


def one(text: str, locale: str = "en-US") -> date | None:
    parsed = parse_date(text, locale)
    return None if parsed is None else parsed.value


@pytest.mark.parametrize(
    "text",
    [
        "2026-03-14", "2026-3-14", "2026/03/14", "14 Mar 2026", "14 March 2026", "Mar 14, 2026",
        "March 14, 2026", "March 14 2026", "Mar. 14, 2026", "14-Mar-2026", "14 mar 2026",
        "MARCH 14, 2026", "14th March 2026", "March 14th, 2026", "03/14/2026",
        "14/03/2026", "14.03.2026", "3/14/26", "14/3/26", "  2026-03-14  ", "14\xa0Mar\xa02026",
    ],
)  # fmt: skip
def test_forms_with_no_ambiguity_all_read_as_the_fourteenth_of_march(text: str) -> None:
    parsed = parse_date(text)
    assert parsed is not None and parsed.value == date(2026, 3, 14), text
    assert parsed.ambiguous is False and parsed.readings == (date(2026, 3, 14),)


def test_ordinals_and_first_of_the_month() -> None:
    assert one("1st Mar 2026") == date(2026, 3, 1)
    assert one("March 2nd, 2026") == date(2026, 3, 2)
    assert one("23rd of March 2026") is None  # words that are not part of a date are not skipped


@pytest.mark.parametrize(
    ("text", "locale", "first", "second"),
    [
        ("03/04/2026", "en-US", date(2026, 3, 4), date(2026, 4, 3)),  # the docs' own example
        ("03/04/2026", "en-GB", date(2026, 4, 3), date(2026, 3, 4)),
        ("03-04-2026", "en-US", date(2026, 3, 4), date(2026, 4, 3)),
        ("3/4/26", "en-US", date(2026, 3, 4), date(2026, 4, 3)),
        ("12/11/2026", "de-DE", date(2026, 11, 12), date(2026, 12, 11)),
        ("01/02/2026", "fr-FR", date(2026, 2, 1), date(2026, 1, 2)),
    ],
)
def test_numeric_dates_that_read_two_ways_are_flagged_and_resolved_by_locale(
    text: str, locale: str, first: date, second: date
) -> None:
    parsed = parse_date(text, locale)
    assert parsed is not None
    assert parsed.ambiguous is True
    assert parsed.value == first
    assert parsed.readings == (first, second)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("03/03/2026", date(2026, 3, 3)),  # the same either way
        ("12/12/2026", date(2026, 12, 12)),
        ("13/01/2026", date(2026, 1, 13)),  # 13 cannot be a month
        ("01/13/2026", date(2026, 1, 13)),
        ("31/12/2026", date(2026, 12, 31)),
        ("12/31/2026", date(2026, 12, 31)),
        ("2026-04-03", date(2026, 4, 3)),  # year first is always year-month-day
        ("2026/04/03", date(2026, 4, 3)),
        ("03.04.2026", date(2026, 4, 3)),  # dots are day.month.year
    ],
)
def test_numeric_dates_with_one_possible_reading_are_not_flagged(text: str, expected: date) -> None:
    parsed = parse_date(text)
    assert parsed is not None and parsed.value == expected and parsed.ambiguous is False


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1/1/00", date(2000, 1, 1)),
        ("1/1/69", date(2069, 1, 1)),
        ("1/1/70", date(1970, 1, 1)),
        ("13/1/99", date(1999, 1, 13)),
    ],
)
def test_two_digit_years_pivot_at_seventy(text: str, expected: date) -> None:
    parsed = parse_date(text)
    assert parsed is not None and parsed.value == expected


@pytest.mark.parametrize(
    "text",
    [
        "", "  ", "N/A", "yesterday", "2026-02-30", "2026-13-01", "13/13/2026", "00/10/2026",
        "32/01/2026", "02/30/2026", "March 32, 2026", "Foo 14, 2026", "14 Marc 2026", "2026-03",
        "March 2026", "14 March", "2026", "14/03", "03/04/20266", "2026-03-14 10:30",
        "Date 2026-03-14",
        "14/03/2026 and more", "2026-03-14T10:00:00", "0000-01-01", "1899-12-31x", "2026.03.14.",
        "20260314", "14-03-26-1", "١٤/٠٣/٢٠٢٦",
    ],
)  # fmt: skip
def test_text_that_is_not_a_single_real_date_is_not_parsed(text: str) -> None:
    assert parse_date(text) is None


def test_leap_days_are_checked() -> None:
    assert one("2028-02-29") == date(2028, 2, 29)
    assert one("2026-02-29") is None
    assert one("29 Feb 2028") == date(2028, 2, 29)
    assert one("29 Feb 2026") is None


def test_unknown_locales_are_an_error() -> None:
    with pytest.raises(ValueError, match="locale"):
        parse_date("03/04/2026", "xx-XX")


def test_a_parsed_date_is_a_plain_date_object() -> None:
    parsed = parse_date("2026-03-14")
    assert isinstance(parsed, ParsedDate) and type(parsed.value) is date


@pytest.mark.parametrize("style", DATE_STYLES)
def test_everything_the_test_data_prints_parses_back_exactly(style: str) -> None:
    """Round trip against the independent printer used to make the golden set."""
    rng = random.Random(5)
    for _ in range(2000):
        original = date(2026, 1, 1).fromordinal(
            date(2026, 1, 1).toordinal() + rng.randint(-400, 400)
        )
        parsed = parse_date(format_date(original, style))
        assert parsed is not None and parsed.value == original, (style, original)
        assert parsed.ambiguous is False
