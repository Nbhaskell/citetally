"""Grounding: finding each extracted value on the page, and parsing it. Invented words only."""

import random
import time
from datetime import date
from decimal import Decimal

import pytest

from citetally.grounding import GroundedValue, Grounding, ground
from citetally.models import ExtractedFields, HeaderField, LineField, Word


def page(*rows: str) -> list[Word]:
    """Words laid out left to right, one row per string, 0.04 of the page apart (or closer)."""
    words = []
    step = min(0.04, 0.9 / max(len(rows), 1))
    for r, row in enumerate(rows):
        x = 0.02
        for token in row.split():
            y = 0.02 + step * r
            words.append(Word(t=token, x0=x, y0=y, x1=x + 0.012 * len(token), y1=y + 0.02, c=None))
            x += 0.012 * len(token) + 0.01
    return words


def fields(**kwargs: object) -> ExtractedFields:
    return ExtractedFields.model_validate({"entry_type": "invoice", **kwargs})


def one(
    result: Grounding, field: HeaderField | LineField, line_index: int | None = None
) -> GroundedValue:
    (match,) = [v for v in result.values if v.field == field and v.line_index == line_index]
    return match


# --- locating ----------------------------------------------------------------------------------


def test_a_multi_word_value_is_found_as_a_run_and_its_box_is_the_union_of_the_words() -> None:
    words = page("Bill from", "Northfield Pet Supply Co.", "Invoice INV-1")
    result = ground(fields(vendor_name="Northfield Pet Supply Co."), [words])
    vendor = one(result, HeaderField.VENDOR_NAME)
    assert (vendor.found, vendor.method, vendor.match_score, vendor.page_number) == (
        True,
        "exact",
        1.0,
        1,
    )
    run = words[2:6]
    assert (vendor.x0, vendor.y0) == (min(w.x0 for w in run), min(w.y0 for w in run))
    assert (vendor.x1, vendor.y1) == (max(w.x1 for w in run), max(w.y1 for w in run))


def test_words_stored_out_of_order_are_still_read_in_reading_order() -> None:
    words = page("Total due", "Copper pipe 3/4 in", "x")
    random.Random(1).shuffle(words)
    assert ground(fields(lines=[{"description": "Copper pipe 3/4 in"}]), [words]).values[0].found


def test_a_value_is_found_on_the_page_it_is_printed_on() -> None:
    result = ground(fields(invoice_number="INV-77"), [page("nothing"), page("No. INV-77")])
    assert one(result, HeaderField.INVOICE_NUMBER).page_number == 2


def test_a_letter_slip_in_the_page_words_is_tolerated_and_scored_below_one() -> None:
    result = ground(fields(vendor_name="Northfield Supply"), [page("Northfieid Supply")])
    vendor = one(result, HeaderField.VENDOR_NAME)
    assert vendor.found and vendor.method == "fuzzy" and 0.85 <= (vendor.match_score or 0) < 1


def test_a_changed_digit_is_never_found_by_fuzzy_matching() -> None:
    result = ground(
        fields(total="$1,208.31", invoice_number="INV-20112"), [page("$1,208.30 INV-20113")]
    )
    for field in (HeaderField.TOTAL, HeaderField.INVOICE_NUMBER):
        value = one(result, field)
        assert not value.found and value.match_score is None and value.page_number is None


def test_a_value_that_is_not_on_the_page_is_not_found_but_is_still_parsed() -> None:
    value = one(ground(fields(total="$99.00"), [page("Total $12.50")]), HeaderField.TOTAL)
    assert not value.found and (value.x0, value.x1) == (None, None)
    assert value.value == Decimal("99.00") and value.amount_minor == 9900


def test_a_weaker_threshold_setting_changes_what_is_accepted() -> None:
    words = [page("Northfeld Supply")]
    assert not one(
        ground(fields(vendor_name="Northfield Supply"), words, threshold=0.99),
        HeaderField.VENDOR_NAME,
    ).found
    assert one(
        ground(fields(vendor_name="Northfield Supply"), words, threshold=0.85),
        HeaderField.VENDOR_NAME,
    ).found


def test_the_currency_symbol_is_found_inside_an_amount_word() -> None:
    assert one(ground(fields(currency="$"), [page("Total $12.50")]), HeaderField.CURRENCY).found


# --- the numeric fallback ----------------------------------------------------------------------


def test_the_same_amount_printed_without_the_symbol_is_found_with_a_lower_score() -> None:
    total = one(ground(fields(total="$1,208.30"), [page("Total 1208.30")]), HeaderField.TOTAL)
    assert total.found and total.method == "numeric" and total.match_score == 0.75


def test_the_same_date_printed_another_way_is_found_with_a_lower_score() -> None:
    result = ground(fields(entry_date="03/14/2026"), [page("Date: March 14, 2026")])
    entry = one(result, HeaderField.ENTRY_DATE)
    assert entry.found and entry.method == "numeric" and entry.value == date(2026, 3, 14)


def test_a_different_amount_is_not_rescued_by_the_fallback() -> None:
    assert not one(ground(fields(total="$12.51"), [page("Total 12.50")]), HeaderField.TOTAL).found


# --- parsing -----------------------------------------------------------------------------------


def test_amounts_become_minor_units_and_quantities_stay_exact_decimals() -> None:
    result = ground(
        fields(
            currency="$",
            lines=[
                {"description": "Pipe", "quantity": "2.5", "unit_price": "$3.10", "amount": "$7.75"}
            ],
            total="$7.75",
        ),
        [page("Pipe 2.5 $3.10 $7.75 $7.75")],
    )
    assert one(result, LineField.AMOUNT, 0).amount_minor == 775
    assert one(result, LineField.QUANTITY, 0).value == Decimal("2.5")
    assert one(result, LineField.UNIT_PRICE, 0).value == Decimal("3.10")
    assert one(result, HeaderField.TOTAL).amount_minor == 775
    assert result.currency == "USD"


def test_a_credit_notes_printed_negative_is_kept_as_printed() -> None:
    value = one(
        ground(fields(entry_type="credit_note", total="($350.00)"), [page("($350.00)")]),
        HeaderField.TOTAL,
    )
    assert value.found and value.amount_minor == -35000


def test_currencies_without_minor_units_and_the_default_dollar_are_respected() -> None:
    yen = one(ground(fields(total="¥1,500"), [page("¥1,500")]), HeaderField.TOTAL)
    assert yen.amount_minor == 1500
    cad = ground(fields(total="$10.00"), [page("$10.00")], currency="CAD")
    assert cad.currency == "CAD"


def test_an_ambiguous_date_and_an_ambiguous_amount_are_flagged_and_the_locale_chooses() -> None:
    us = one(
        ground(fields(entry_date="03/04/2026", total="1.234"), [page("03/04/2026 1.234")]),
        HeaderField.ENTRY_DATE,
    )
    assert us.ambiguous and us.value == date(2026, 3, 4)
    assert set(us.readings) == {"2026-03-04", "2026-04-03"}
    uk = one(
        ground(fields(entry_date="03/04/2026"), [page("03/04/2026")], locale="en-GB"),
        HeaderField.ENTRY_DATE,
    )
    assert uk.value == date(2026, 4, 3)
    amount = one(ground(fields(total="1.234"), [page("1.234")]), HeaderField.TOTAL)
    assert amount.ambiguous and len(amount.readings) == 2


def test_a_value_that_cannot_be_parsed_is_marked_and_may_still_be_found() -> None:
    value = one(ground(fields(total="see below"), [page("Total see below")]), HeaderField.TOTAL)
    assert value.found and not value.parsed and value.value is None and value.amount_minor is None


def test_tax_rates_are_parsed_but_not_located() -> None:
    result = ground(fields(lines=[{"tax_rate": "7%"}, {"tax_rate": "n/a"}, {}]), [page("7%")])
    assert result.line_tax_rates == [Decimal("0.07"), None, None]
    assert result.values == []  # no other fields were printed


# --- which values get evidence -----------------------------------------------------------------


def test_null_and_blank_fields_get_no_evidence_and_line_values_carry_their_line() -> None:
    result = ground(
        fields(
            vendor_name="  ",
            invoice_number=None,
            lines=[{"description": "Pipe"}, {"amount": "$5.00"}],
        ),
        [page("Pipe $5.00")],
    )
    assert [(v.field, v.line_index) for v in result.values] == [
        (LineField.DESCRIPTION, 0),
        (LineField.AMOUNT, 1),
    ]


def test_two_fields_with_the_same_text_point_at_different_words_when_the_page_has_two() -> None:
    line = {"quantity": "1", "unit_price": "$38.00", "amount": "$38.00"}
    result = ground(fields(lines=[line]), [page("1 $38.00 $38.00")])
    price, amount = one(result, LineField.UNIT_PRICE, 0), one(result, LineField.AMOUNT, 0)
    assert price.found and amount.found and price.x0 != amount.x0


def test_coverage_counts_found_values() -> None:
    result = ground(fields(invoice_number="INV-1", total="$9.00"), [page("INV-1")])
    assert (result.found_count, len(result.values), result.coverage) == (1, 2, 0.5)
    assert ground(fields(), [page("x")]).coverage == 1.0  # nothing was printed, nothing is missing


def test_a_busy_page_with_long_values_is_grounded_quickly() -> None:
    rows = [f"item{n} widget {n * 7} $1{n % 10}.50 filler text here" for n in range(150)]
    long_words = [f"word{n}" for n in range(30)]
    long_text = " ".join(long_words)  # printed on a page over five lines
    start = time.perf_counter()
    result = ground(
        fields(lines=[{"description": long_text}, {"description": "absent " * 25}]),
        [page(*rows[:40]), page(*(" ".join(long_words[i : i + 6]) for i in range(0, 30, 6)))],
    )
    assert time.perf_counter() - start < 5
    assert (
        one(result, LineField.DESCRIPTION, 0).found
        and not one(result, LineField.DESCRIPTION, 1).found
    )


@pytest.mark.parametrize("pages", [[], [[]]])
def test_a_document_with_no_words_finds_nothing_and_does_not_fail(pages: list[list[Word]]) -> None:
    assert not one(ground(fields(total="$1.00"), pages), HeaderField.TOTAL).found
