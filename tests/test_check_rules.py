"""The 14 checks as pure functions: pass, fail and the edges (rounding, missing pieces, history)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from citetally.checks import RULES, CheckInput, History, Other, Thresholds
from citetally.checks import rules as r
from citetally.checks.inputs import Outcome
from citetally.models import (
    CheckCode,
    Entry,
    EntryLine,
    EntryType,
    Evidence,
    HeaderField,
    LineField,
    Page,
    ReadMethod,
    Vendor,
)

TODAY = date(2026, 6, 15)
NOW = "2026-06-15T00:00:00Z"


def make_entry(**kw: Any) -> Entry:
    base: dict[str, Any] = {
        "id": 1, "document_id": 1, "extraction_id": 1, "entry_type": EntryType.INVOICE,
        "vendor_id": 7, "vendor_name_raw": "Northfield Pet Supply Co.", "vendor_match_method": None,
        "vendor_match_score": None, "invoice_number": "INV-20417", "entry_date": "2026-06-01",
        "due_date": None, "po_number": None, "currency": "USD", "subtotal_minor": None,
        "tax_total_minor": None, "shipping_minor": None, "discount_minor": None,
        "total_minor": 15200, "category_id": 3, "category_source": None, "notes": None,
        "created_at": NOW, "updated_at": NOW,
    }  # fmt: skip
    return Entry.model_validate({**base, **kw})


def make_line(number: int = 1, **kw: Any) -> EntryLine:
    base: dict[str, Any] = {
        "id": number, "entry_id": 1, "line_number": number, "description": "Kibble",
        "quantity": None, "unit_price": None, "amount_minor": None, "tax_rate": None,
        "created_at": NOW,
    }  # fmt: skip
    return EntryLine.model_validate({**base, **kw})


def make_evidence(
    field: HeaderField | LineField, printed: str, *, found: bool = True, line_id: int | None = None
) -> Evidence:
    return Evidence.model_validate(
        {
            "id": 1,
            "entry_id": 1,
            "line_id": line_id,
            "field": field,
            "printed_text": printed,
            "found": found,
            "page_number": 1,
            "x0": None,
            "y0": None,
            "x1": None,
            "y1": None,
            "match_score": None,
            "created_at": NOW,
        }
    )


def make_page(**kw: Any) -> Page:
    base: dict[str, Any] = {
        "id": 1, "document_id": 1, "page_number": 1, "image_path": "p.png", "width_px": 100,
        "height_px": 100, "read_method": ReadMethod.TEXT_LAYER, "ocr_engine": None,
        "mean_confidence": None, "skew_degrees": None, "word_count": 100, "words": "[]",
        "text": "Invoice", "created_at": NOW,
    }  # fmt: skip
    return Page.model_validate({**base, **kw})


def make_vendor(**kw: Any) -> Vendor:
    base: dict[str, Any] = {
        "id": 7, "name": "Northfield", "normalized_name": "northfield", "default_category_id": None,
        "default_currency": None, "is_active": True, "is_synthetic": True, "created_at": NOW,
    }  # fmt: skip
    return Vendor.model_validate({**base, **kw})


def make_input(
    entry: Entry | None = None,
    lines: list[EntryLine] | None = None,
    **kw: Any,
) -> CheckInput:
    values: dict[str, Any] = {
        "entry": entry or make_entry(), "lines": lines or [], "evidence": [], "pages": [],
        "vendor": make_vendor(), "others": [], "history": History(), "today": TODAY,
        "thresholds": Thresholds(),
    }  # fmt: skip
    return CheckInput(**{**values, **kw})


def run(code: CheckCode, **kw: Any) -> Any:
    return RULES[code](make_input(**kw))


# --- there is one rule per code ----------------------------------------------------------------


def test_every_check_code_has_a_rule_that_reports_its_own_code() -> None:
    assert set(RULES) == set(CheckCode)
    for code, rule in RULES.items():
        assert rule(make_input()).code is code


# --- REQUIRED_FIELDS ---------------------------------------------------------------------------


def test_a_complete_invoice_has_its_required_fields() -> None:
    assert run(CheckCode.REQUIRED_FIELDS).passed


def test_missing_fields_are_listed_by_name() -> None:
    entry = make_entry(invoice_number=" ", category_id=None, total_minor=None)
    outcome = run(CheckCode.REQUIRED_FIELDS, entry=entry)
    assert not outcome.passed
    assert outcome.detail["missing"] == ["category", "invoice_number", "total"]


def test_a_receipt_needs_no_invoice_number_but_a_credit_note_does() -> None:
    assert run(
        CheckCode.REQUIRED_FIELDS,
        entry=make_entry(entry_type=EntryType.RECEIPT, invoice_number=None),
    ).passed
    outcome = run(
        CheckCode.REQUIRED_FIELDS,
        entry=make_entry(entry_type=EntryType.CREDIT_NOTE, invoice_number=None),
    )
    assert outcome.detail["missing"] == ["invoice_number"]


def test_a_printed_vendor_name_counts_even_before_the_vendor_is_matched() -> None:
    assert run(CheckCode.REQUIRED_FIELDS, entry=make_entry(vendor_id=None)).passed
    outcome = run(CheckCode.REQUIRED_FIELDS, entry=make_entry(vendor_id=None, vendor_name_raw=None))
    assert outcome.detail["missing"] == ["vendor_name"]


# --- VALUE_IN_DOCUMENT -------------------------------------------------------------------------


def test_every_value_found_on_the_page_passes_and_no_evidence_passes() -> None:
    found = [make_evidence(HeaderField.TOTAL, "$152.00")]
    assert run(CheckCode.VALUE_IN_DOCUMENT, evidence=found).passed
    assert run(CheckCode.VALUE_IN_DOCUMENT).passed


def test_a_value_not_on_the_page_fails_and_names_the_field_and_line() -> None:
    lines = [make_line(1), make_line(2)]
    evidence = [
        make_evidence(HeaderField.TOTAL, "$152.00"),
        make_evidence(LineField.AMOUNT, "$9.99", found=False, line_id=2),
        make_evidence(HeaderField.VENDOR_NAME, "Invented Ltd", found=False),
    ]
    outcome = run(CheckCode.VALUE_IN_DOCUMENT, lines=lines, evidence=evidence)
    assert not outcome.passed
    assert outcome.detail["checked"] == 3
    assert outcome.detail["not_found"] == [
        {"field": "amount", "line": 2, "printed": "$9.99"},
        {"field": "vendor_name", "line": None, "printed": "Invented Ltd"},
    ]


def test_a_long_printed_value_is_cut_in_the_detail() -> None:
    evidence = [make_evidence(HeaderField.VENDOR_NAME, "x" * 500, found=False)]
    outcome = run(CheckCode.VALUE_IN_DOCUMENT, evidence=evidence)
    assert len(outcome.detail["not_found"][0]["printed"]) == 80


# --- LINE_MATH ---------------------------------------------------------------------------------


def line_with(q: str | None, p: str | None, amount: int | None, number: int = 1) -> EntryLine:
    return make_line(number, quantity=q, unit_price=p, amount_minor=amount)


def test_a_line_whose_amount_is_quantity_times_price_passes() -> None:
    outcome = run(CheckCode.LINE_MATH, lines=[line_with("4", "38.00", 15200)])
    assert outcome.passed and outcome.detail["checked"] == 1


def test_the_product_is_rounded_once_half_up() -> None:
    # 3 x 0.335 = 1.005, which is 1.01 half up, not the 1.00 that binary floats would give
    assert run(CheckCode.LINE_MATH, lines=[line_with("3", "0.335", 101)]).passed
    wrong = run(CheckCode.LINE_MATH, lines=[line_with("3", "0.335", 99)])
    assert not wrong.passed
    assert wrong.detail["mismatches"] == [{"line": 1, "expected": 101, "stated": 99}]


def test_one_minor_unit_is_tolerated_two_are_not() -> None:
    assert run(CheckCode.LINE_MATH, lines=[line_with("2", "5.00", 1001)]).passed
    assert not run(CheckCode.LINE_MATH, lines=[line_with("2", "5.00", 1002)]).passed


def test_the_tolerance_is_a_setting() -> None:
    loose = Thresholds(tolerance_minor=5)
    assert run(CheckCode.LINE_MATH, lines=[line_with("2", "5.00", 1005)], thresholds=loose).passed
    strict = Thresholds(tolerance_minor=0)
    assert not run(
        CheckCode.LINE_MATH, lines=[line_with("2", "5.00", 1001)], thresholds=strict
    ).passed


def test_lines_with_a_missing_piece_are_skipped_not_failed() -> None:
    lines = [line_with(None, "5.00", 500), line_with("2", None, 500, 2), line_with("x", "5", 5, 3)]
    outcome = run(CheckCode.LINE_MATH, lines=lines)
    assert outcome.passed and outcome.detail["checked"] == 0 and outcome.detail["skipped"] == 3


def test_a_fractional_quantity_is_exact() -> None:
    assert run(CheckCode.LINE_MATH, lines=[line_with("2.5", "4.125", 1031)]).passed  # 10.3125


# --- SUBTOTAL_MATCH ----------------------------------------------------------------------------


def amounts(*cents: int | None) -> list[EntryLine]:
    return [make_line(n, amount_minor=c) for n, c in enumerate(cents, start=1)]


def test_no_printed_subtotal_is_not_applicable() -> None:
    outcome = run(CheckCode.SUBTOTAL_MATCH, lines=amounts(100))
    assert outcome.passed and outcome.detail["applicable"] is False


def test_lines_that_add_up_to_the_subtotal_pass() -> None:
    entry = make_entry(subtotal_minor=15200)
    assert run(CheckCode.SUBTOTAL_MATCH, entry=entry, lines=amounts(10000, 5200)).passed


def test_lines_that_do_not_add_up_fail_with_both_numbers() -> None:
    entry = make_entry(subtotal_minor=15200)
    outcome = run(CheckCode.SUBTOTAL_MATCH, entry=entry, lines=amounts(10000, 5300))
    assert not outcome.passed
    assert (outcome.detail["lines_sum"], outcome.detail["stated"]) == (15300, 15200)


def test_a_line_without_an_amount_means_the_sum_cannot_be_trusted() -> None:
    entry = make_entry(subtotal_minor=10000)
    outcome = run(CheckCode.SUBTOTAL_MATCH, entry=entry, lines=amounts(10000, None))
    assert not outcome.passed and outcome.detail["lines_without_amount"] == 1


def test_a_subtotal_with_no_lines_is_not_applicable() -> None:
    assert (
        run(CheckCode.SUBTOTAL_MATCH, entry=make_entry(subtotal_minor=100)).detail["applicable"]
        is False
    )


# --- TAX_MATCH ---------------------------------------------------------------------------------


def taxed(cents: int, rate: str | None, number: int = 1) -> EntryLine:
    return make_line(number, amount_minor=cents, tax_rate=rate)


def test_no_printed_tax_is_not_applicable() -> None:
    assert run(CheckCode.TAX_MATCH).detail["applicable"] is False


def test_a_printed_rate_applied_to_the_taxable_amount_matches_the_stated_tax() -> None:
    entry = make_entry(tax_total_minor=1696)
    assert run(CheckCode.TAX_MATCH, entry=entry, lines=[taxed(21200, "0.08")]).passed


def test_tax_that_does_not_match_the_rate_fails_and_shows_both() -> None:
    entry = make_entry(tax_total_minor=1996)
    outcome = run(CheckCode.TAX_MATCH, entry=entry, lines=[taxed(21200, "0.08")])
    assert not outcome.passed
    assert (outcome.detail["expected"], outcome.detail["stated"]) == (1696, 1996)


def test_a_cent_of_rounding_is_allowed_for_each_taxable_line() -> None:
    lines = [taxed(1050, "0.07", n) for n in (1, 2, 3)]  # 73.5 cents each, 74 when rounded
    assert run(CheckCode.TAX_MATCH, entry=make_entry(tax_total_minor=219), lines=lines).passed
    assert not run(CheckCode.TAX_MATCH, entry=make_entry(tax_total_minor=218), lines=lines).passed


def test_untaxed_lines_are_left_out_of_the_expected_tax() -> None:
    lines = [taxed(10000, "0.10", 1), taxed(5000, None, 2)]
    assert run(CheckCode.TAX_MATCH, entry=make_entry(tax_total_minor=1000), lines=lines).passed


def test_without_a_rate_the_implied_rate_is_reported_and_the_check_passes() -> None:
    entry = make_entry(subtotal_minor=10000, tax_total_minor=800)
    outcome = run(CheckCode.TAX_MATCH, entry=entry)
    assert outcome.passed
    assert outcome.detail["rate_printed"] is False and outcome.detail["implied_rate"] == "0.0800"
    assert "usual_rate" not in outcome.detail


def test_the_implied_rate_uses_the_line_sum_when_no_subtotal_is_printed() -> None:
    outcome = run(
        CheckCode.TAX_MATCH, entry=make_entry(tax_total_minor=500), lines=amounts(2500, 2500)
    )
    assert outcome.detail["implied_rate"] == "0.1000"


def test_an_implied_rate_far_from_the_vendors_usual_rate_is_marked_unusual() -> None:
    usual = History(tax_rates=[Decimal("0.08"), Decimal("0.08"), Decimal("0.0825")])
    entry = make_entry(subtotal_minor=10000, tax_total_minor=1500)
    outcome = run(CheckCode.TAX_MATCH, entry=entry, history=usual)
    assert outcome.passed and outcome.detail["unusual"] is True
    same = run(CheckCode.TAX_MATCH, entry=make_entry(subtotal_minor=10000, tax_total_minor=800),
               history=usual)  # fmt: skip
    assert same.detail["unusual"] is False


def test_too_little_tax_history_says_nothing_about_the_rate() -> None:
    thin = History(tax_rates=[Decimal("0.08"), Decimal("0.08")])
    entry = make_entry(subtotal_minor=10000, tax_total_minor=1500)
    assert "unusual" not in run(CheckCode.TAX_MATCH, entry=entry, history=thin).detail


# --- TOTAL_MATCH -------------------------------------------------------------------------------


def test_subtotal_plus_tax_plus_shipping_minus_discount_equals_the_total() -> None:
    entry = make_entry(
        subtotal_minor=10000, tax_total_minor=800, shipping_minor=500, discount_minor=300,
        total_minor=11000,
    )  # fmt: skip
    assert run(CheckCode.TOTAL_MATCH, entry=entry).passed


def test_a_wrong_total_fails_with_expected_and_stated() -> None:
    entry = make_entry(subtotal_minor=10000, tax_total_minor=800, total_minor=11000)
    outcome = run(CheckCode.TOTAL_MATCH, entry=entry)
    assert not outcome.passed
    assert (outcome.detail["expected"], outcome.detail["stated"]) == (10800, 11000)


def test_the_line_sum_stands_in_for_a_missing_subtotal() -> None:
    entry = make_entry(total_minor=15200)
    assert run(CheckCode.TOTAL_MATCH, entry=entry, lines=amounts(10000, 5200)).passed
    assert not run(CheckCode.TOTAL_MATCH, entry=entry, lines=amounts(10000, 5100)).passed


def test_nothing_to_add_up_or_no_total_is_not_applicable() -> None:
    assert run(CheckCode.TOTAL_MATCH).detail["applicable"] is False
    assert (
        run(CheckCode.TOTAL_MATCH, entry=make_entry(total_minor=None)).detail["applicable"] is False
    )


def test_a_credit_note_adds_up_the_same_way_because_it_is_stored_positive() -> None:
    entry = make_entry(entry_type=EntryType.CREDIT_NOTE, subtotal_minor=5000, total_minor=5000)
    assert run(CheckCode.TOTAL_MATCH, entry=entry).passed


# --- DUPLICATE_SUSPECT -------------------------------------------------------------------------


def other(**kw: Any) -> Other:
    base: dict[str, Any] = {
        "document_id": 2, "entry_type": "invoice", "invoice_number": "INV-9",
        "total_minor": 99999, "currency": "USD", "entry_date": date(2026, 1, 1),
    }  # fmt: skip
    return Other(**{**base, **kw})


def test_no_other_entries_means_no_duplicate() -> None:
    assert run(CheckCode.DUPLICATE_SUSPECT).passed


def test_the_same_invoice_number_is_a_duplicate_however_it_is_punctuated() -> None:
    for printed in ("INV-20417", "inv 20417", "Inv.20417"):
        outcome = run(CheckCode.DUPLICATE_SUSPECT, others=[other(invoice_number=printed)])
        assert not outcome.passed, printed
        assert outcome.detail["matches"] == [{"document_id": 2, "reason": "invoice_number"}]


def test_blank_invoice_numbers_never_match_each_other() -> None:
    entry = make_entry(invoice_number=None, entry_type=EntryType.RECEIPT)
    others = [other(entry_type="receipt", invoice_number=None, total_minor=1)]
    assert run(CheckCode.DUPLICATE_SUSPECT, entry=entry, others=others).passed


def test_same_total_currency_and_a_nearby_date_is_a_duplicate() -> None:
    near = other(total_minor=15200, entry_date=date(2026, 6, 7))  # six days from 1 June
    outcome = run(CheckCode.DUPLICATE_SUSPECT, others=[near])
    assert not outcome.passed and outcome.detail["matches"][0]["reason"] == "vendor_total_date"


def test_the_date_window_is_inclusive_and_a_setting() -> None:
    edge = other(total_minor=15200, entry_date=date(2026, 6, 8))  # seven days
    assert not run(CheckCode.DUPLICATE_SUSPECT, others=[edge]).passed
    far = other(total_minor=15200, entry_date=date(2026, 6, 9))  # eight days
    assert run(CheckCode.DUPLICATE_SUSPECT, others=[far]).passed
    wide = Thresholds(duplicate_window_days=30)
    assert not run(CheckCode.DUPLICATE_SUSPECT, others=[far], thresholds=wide).passed


def test_a_different_total_or_currency_is_not_a_duplicate() -> None:
    assert run(CheckCode.DUPLICATE_SUSPECT, others=[other(total_minor=15201,
               entry_date=date(2026, 6, 1))]).passed  # fmt: skip
    assert run(CheckCode.DUPLICATE_SUSPECT, others=[other(total_minor=15200, currency="EUR",
               entry_date=date(2026, 6, 1))]).passed  # fmt: skip


def test_an_invoice_and_its_credit_note_are_not_duplicates() -> None:
    same_everything = other(entry_type="credit_note", invoice_number="INV-20417", total_minor=15200,
                            entry_date=date(2026, 6, 1))  # fmt: skip
    assert run(CheckCode.DUPLICATE_SUSPECT, others=[same_everything]).passed


def test_without_a_vendor_duplicates_are_not_judged_yet() -> None:
    outcome = run(
        CheckCode.DUPLICATE_SUSPECT,
        entry=make_entry(vendor_id=None),
        others=[other(invoice_number="INV-20417")],
    )
    assert outcome.passed and outcome.detail["applicable"] is False


# --- UNKNOWN_VENDOR ----------------------------------------------------------------------------


def test_unknown_vendor_fails_until_a_vendor_is_chosen() -> None:
    assert run(CheckCode.UNKNOWN_VENDOR).passed
    assert not run(CheckCode.UNKNOWN_VENDOR, entry=make_entry(vendor_id=None)).passed


# --- AMOUNT_OUTLIER ----------------------------------------------------------------------------


def usual(*totals: int) -> History:
    return History(totals_minor=list(totals))


def test_with_too_little_history_the_outlier_check_passes_and_says_so() -> None:
    outcome = run(CheckCode.AMOUNT_OUTLIER, history=usual(100, 100, 100, 100))
    assert outcome.passed and outcome.detail["enough_history"] is False
    assert (outcome.detail["history"], outcome.detail["needed"]) == (4, 5)


def test_a_total_three_times_the_median_or_more_is_flagged_high() -> None:
    history = usual(5000, 5000, 5000, 5000, 5000)
    assert run(
        CheckCode.AMOUNT_OUTLIER, entry=make_entry(total_minor=14999), history=history
    ).passed
    flagged = run(CheckCode.AMOUNT_OUTLIER, entry=make_entry(total_minor=15000), history=history)
    assert not flagged.passed and flagged.detail["direction"] == "high"


def test_a_total_a_third_of_the_median_or_less_is_flagged_low() -> None:
    history = usual(6000, 6000, 6000, 6000, 6000)
    assert run(CheckCode.AMOUNT_OUTLIER, entry=make_entry(total_minor=2001), history=history).passed
    flagged = run(CheckCode.AMOUNT_OUTLIER, entry=make_entry(total_minor=2000), history=history)
    assert not flagged.passed and flagged.detail["direction"] == "low"


def test_the_median_not_the_mean_decides() -> None:
    history = usual(1000, 1000, 1000, 1000, 1000_00)  # one huge past bill must not move it
    assert not run(CheckCode.AMOUNT_OUTLIER, entry=make_entry(total_minor=3000),
                   history=history).passed  # fmt: skip


def test_the_ratio_and_history_size_are_settings() -> None:
    tight = Thresholds(outlier_ratio=Decimal("1.5"), outlier_min_history=2)
    outcome = run(
        CheckCode.AMOUNT_OUTLIER,
        entry=make_entry(total_minor=1600),
        history=usual(1000, 1000),
        thresholds=tight,
    )
    assert not outcome.passed


def test_a_zero_median_cannot_flag_anything() -> None:
    assert run(CheckCode.AMOUNT_OUTLIER, history=usual(0, 0, 0, 0, 0)).passed


def test_no_vendor_or_no_total_is_not_applicable() -> None:
    assert (
        run(CheckCode.AMOUNT_OUTLIER, entry=make_entry(vendor_id=None)).detail["applicable"]
        is False
    )
    assert (
        run(CheckCode.AMOUNT_OUTLIER, entry=make_entry(total_minor=None)).detail["applicable"]
        is False
    )


# --- DATE_SANITY -------------------------------------------------------------------------------


def dated(entry_date: str | None, due: str | None = None) -> Entry:
    return make_entry(entry_date=entry_date, due_date=due)


def test_an_ordinary_date_passes_and_tomorrow_is_allowed() -> None:
    assert run(CheckCode.DATE_SANITY, entry=dated("2026-06-01", "2026-07-01")).passed
    assert run(CheckCode.DATE_SANITY, entry=dated("2026-06-16")).passed


def test_a_date_more_than_a_day_ahead_is_flagged() -> None:
    outcome = run(CheckCode.DATE_SANITY, entry=dated("2026-06-17"))
    assert not outcome.passed and outcome.detail["problems"] == ["in_the_future"]


def test_a_due_date_before_the_entry_date_is_flagged() -> None:
    outcome = run(CheckCode.DATE_SANITY, entry=dated("2026-06-10", "2026-06-09"))
    assert outcome.detail["problems"] == ["due_before_entry"]


def test_a_date_older_than_the_limit_is_flagged_and_the_limit_is_a_setting() -> None:
    edge = dated("2025-05-11")  # 400 days before 15 June 2026
    assert run(CheckCode.DATE_SANITY, entry=edge).passed
    assert run(CheckCode.DATE_SANITY, entry=dated("2025-05-10")).detail["problems"] == ["too_old"]
    assert not run(CheckCode.DATE_SANITY, entry=edge, thresholds=Thresholds(max_age_days=30)).passed


def test_several_problems_are_all_reported() -> None:
    outcome = run(CheckCode.DATE_SANITY, entry=dated("2024-01-02", "2024-01-01"))
    assert outcome.detail["problems"] == ["too_old", "due_before_entry"]


def test_no_entry_date_is_not_applicable() -> None:
    assert run(CheckCode.DATE_SANITY, entry=dated(None)).detail["applicable"] is False


# --- CURRENCY_CHECK ----------------------------------------------------------------------------


def test_the_business_currency_passes() -> None:
    assert run(CheckCode.CURRENCY_CHECK).passed


def test_a_different_currency_is_flagged_with_both() -> None:
    outcome = run(CheckCode.CURRENCY_CHECK, entry=make_entry(currency="EUR"))
    assert not outcome.passed and outcome.detail == {"stated": "EUR", "usual": "USD"}


def test_the_vendors_own_currency_is_the_usual_one_when_it_has_one() -> None:
    euro_vendor = make_vendor(default_currency="EUR")
    assert run(
        CheckCode.CURRENCY_CHECK, entry=make_entry(currency="EUR"), vendor=euro_vendor
    ).passed
    assert not run(CheckCode.CURRENCY_CHECK, vendor=euro_vendor).passed


def test_no_currency_is_not_applicable() -> None:
    assert (
        run(CheckCode.CURRENCY_CHECK, entry=make_entry(currency=None)).detail["applicable"] is False
    )


# --- LOW_READ_QUALITY --------------------------------------------------------------------------


def test_a_clean_text_layer_page_passes() -> None:
    assert run(CheckCode.LOW_READ_QUALITY, pages=[make_page()]).passed


def test_mean_ocr_confidence_below_the_limit_is_flagged() -> None:
    outcome = run(CheckCode.LOW_READ_QUALITY, pages=[make_page(mean_confidence=74.9)])
    assert outcome.detail["reasons"] == ["low_confidence"]
    assert run(CheckCode.LOW_READ_QUALITY, pages=[make_page(mean_confidence=75.0)]).passed


def test_the_confidence_limit_is_a_setting_and_pages_are_averaged() -> None:
    pages = [make_page(mean_confidence=90.0), make_page(page_number=2, mean_confidence=60.0)]
    assert run(CheckCode.LOW_READ_QUALITY, pages=pages).passed  # mean 75
    assert not run(CheckCode.LOW_READ_QUALITY, pages=pages,
                   thresholds=Thresholds(low_confidence=80)).passed  # fmt: skip


def test_very_few_words_and_a_large_skew_are_flagged() -> None:
    outcome = run(CheckCode.LOW_READ_QUALITY, pages=[make_page(word_count=5, skew_degrees=-8.0)])
    assert outcome.detail["reasons"] == ["very_few_words", "large_skew"]
    assert run(CheckCode.LOW_READ_QUALITY, pages=[make_page(skew_degrees=5.0)]).passed


def test_a_document_with_no_pages_is_not_called_unreadable() -> None:
    assert run(CheckCode.LOW_READ_QUALITY).passed


# --- AMBIGUOUS_FORMAT --------------------------------------------------------------------------


def test_a_date_that_reads_two_ways_is_flagged_with_both_readings() -> None:
    evidence = [make_evidence(HeaderField.ENTRY_DATE, "03/04/2026")]
    outcome = run(CheckCode.AMBIGUOUS_FORMAT, evidence=evidence)
    assert not outcome.passed
    (found,) = outcome.detail["ambiguous"]
    assert found["field"] == "entry_date" and found["readings"] == ["2026-03-04", "2026-04-03"]


def test_an_unambiguous_date_and_amount_pass() -> None:
    evidence = [
        make_evidence(HeaderField.ENTRY_DATE, "03/14/2026"),
        make_evidence(HeaderField.TOTAL, "$1,520.00"),
    ]
    assert run(CheckCode.AMBIGUOUS_FORMAT, evidence=evidence).passed


def test_an_amount_with_a_lone_separator_is_flagged_on_its_line() -> None:
    lines = [make_line(1)]
    evidence = [make_evidence(LineField.AMOUNT, "1.234", line_id=1)]
    outcome = run(CheckCode.AMBIGUOUS_FORMAT, lines=lines, evidence=evidence)
    assert not outcome.passed and outcome.detail["ambiguous"][0]["line"] == 1


def test_text_fields_are_never_ambiguous() -> None:
    evidence = [make_evidence(HeaderField.INVOICE_NUMBER, "03/04/2026")]
    assert run(CheckCode.AMBIGUOUS_FORMAT, evidence=evidence).passed


# --- the helpers the checks lean on ------------------------------------------------------------


def test_invoice_number_keys_ignore_case_and_punctuation() -> None:
    assert r._key("INV-20417") == r._key(" inv.20417 ") == "inv20417"
    assert r._key(None) == r._key("--") == ""


@pytest.mark.parametrize("text", [None, "", "x", "1/2/3"])
def test_unreadable_dates_and_decimals_are_none(text: str | None) -> None:
    assert r._iso(text) is None
    assert r._decimal(text) is None


# --- Stage 2: the rate printed beside the tax total bounds the tax ----------------------------


def rate_page(text: str) -> Page:
    return make_page(text=text)


def test_a_tax_above_what_the_printed_rate_allows_fails_and_shows_the_most_it_could_be() -> None:
    page = rate_page("Subtotal $100.00\nSales tax (7%) $9.00\nTotal $109.00")
    outcome = run(
        CheckCode.TAX_MATCH,
        entry=make_entry(subtotal_minor=10000, tax_total_minor=900),
        pages=[page],
    )
    assert not outcome.passed
    assert (outcome.detail["printed_rate"], outcome.detail["most"], outcome.detail["stated"]) == (
        "0.07", 700, 900,
    )  # fmt: skip


def test_a_tax_at_or_below_the_bound_passes_because_some_lines_may_be_untaxed() -> None:
    page = rate_page("Sales tax (7%)")
    for tax in (700, 350, 0):
        entry = make_entry(subtotal_minor=10000, tax_total_minor=tax)
        assert run(CheckCode.TAX_MATCH, entry=entry, pages=[page]).passed


def test_shipping_counts_towards_what_may_be_taxed() -> None:
    page = rate_page("Tax 7%")
    entry = make_entry(subtotal_minor=10000, shipping_minor=1000, tax_total_minor=770)
    assert run(CheckCode.TAX_MATCH, entry=entry, pages=[page]).passed


def test_two_different_printed_rates_or_a_rate_not_beside_tax_set_no_bound() -> None:
    entry = make_entry(subtotal_minor=10000, tax_total_minor=900)
    two = rate_page("Tax (7%) and state tax 5%")
    assert run(CheckCode.TAX_MATCH, entry=entry, pages=[two]).passed
    unrelated = rate_page("Save 3% when you pay early\nTax $9.00")
    assert run(CheckCode.TAX_MATCH, entry=entry, pages=[unrelated]).passed


def test_a_per_line_rate_still_decides_and_the_page_rate_is_not_used() -> None:
    page = rate_page("Tax (7%)")
    entry = make_entry(subtotal_minor=10000, tax_total_minor=1000)
    outcome = run(CheckCode.TAX_MATCH, entry=entry, lines=[taxed(10000, "0.10")], pages=[page])
    assert outcome.passed and outcome.detail["rate_printed"] is True


# --- Round 2: the printed rate must be able to produce the stated tax -------------------------
#
# With no per-line rate read, the tax must still equal the printed rate applied to some lines (the
# taxable ones, which the page does not mark). A tax below the ceiling that no combination of the
# lines reaches cannot be right: this is what the first sealed set's seven misses looked like.


def tax_on(*cents: int, tax: int, text: str = "Sales tax (7%)", **entry_fields: int) -> Outcome:
    entry = make_entry(subtotal_minor=sum(cents), tax_total_minor=tax, **entry_fields)
    outcome: Outcome = run(
        CheckCode.TAX_MATCH, entry=entry, lines=amounts(*cents), pages=[rate_page(text)]
    )
    return outcome


def test_a_tax_below_the_ceiling_that_no_set_of_lines_reaches_fails() -> None:
    outcome = tax_on(10000, 5000, tax=500)  # 7% of 100.00 is 700, of 50.00 is 350, of both 1050
    assert not outcome.passed
    assert outcome.detail["reachable"] is False and outcome.detail["printed_rate"] == "0.07"


@pytest.mark.parametrize("tax", [350, 700, 1050])
def test_a_tax_that_is_the_rate_on_any_set_of_the_lines_passes(tax: int) -> None:
    outcome = tax_on(10000, 5000, tax=tax)
    assert outcome.passed and outcome.detail["reachable"] is True


def test_the_tax_may_be_charged_on_shipping_or_after_a_discount() -> None:
    assert tax_on(10000, 5000, tax=420, shipping_minor=1000).passed  # 7% of 50.00 + 10.00
    assert tax_on(10000, 5000, tax=665, discount_minor=500).passed  # 7% of 100.00 - 5.00
    assert not tax_on(10000, 5000, tax=500, shipping_minor=1000).passed


def test_a_cent_of_rounding_is_allowed_for_each_line_in_the_set() -> None:
    lines = (1050, 1050, 1050)  # 73.5 cents each: 74 when rounded one by one, 220 on the sum
    assert tax_on(*lines, tax=219).passed and tax_on(*lines, tax=221).passed
    assert not tax_on(*lines, tax=224).passed


def test_a_tax_of_zero_beside_a_printed_rate_fails_when_there_are_lines() -> None:
    assert not tax_on(10000, 5000, tax=0).passed


def test_with_no_lines_or_too_many_or_one_without_an_amount_only_the_ceiling_applies() -> None:
    page = rate_page("Sales tax (7%)")
    entry = make_entry(subtotal_minor=10000, tax_total_minor=500)
    assert run(CheckCode.TAX_MATCH, entry=entry, pages=[page]).passed  # no lines read
    many = amounts(*([100] * (r.MAX_TAX_SUBSET_LINES + 1)))
    assert run(CheckCode.TAX_MATCH, entry=entry, lines=many, pages=[page]).passed
    partial = [*amounts(10000), make_line(2)]  # the second line has no amount
    assert run(CheckCode.TAX_MATCH, entry=entry, lines=partial, pages=[page]).passed


def test_without_a_single_printed_rate_the_subset_test_is_not_applied() -> None:
    entry = make_entry(subtotal_minor=15000, tax_total_minor=500)
    lines = amounts(10000, 5000)
    assert run(CheckCode.TAX_MATCH, entry=entry, lines=lines, pages=[rate_page("Tax $5.00")]).passed
    two = rate_page("Tax (7%) and state tax 5%")
    assert run(CheckCode.TAX_MATCH, entry=entry, lines=lines, pages=[two]).passed


# --- Round 3: the printed rate, read through label variants, small damage and every reading ----
#
# The second sealed set's tax misses had a printed rate the check could not read: "Levy (8.25%)"
# for a label, "Sales tax total 14 (8.25%)" for a stray count, "Tax (8 25%}" for a lost point.


@pytest.mark.parametrize(
    "text",
    [
        "Tax 8.25%",
        "TAX  8.25%",
        "Sales tax (8.25%)       $42.75",
        "Levy (8.25%) amount",
        "VAT 8.25%",
        "GST (8.25%)",
        "Sales tax total 14 (8.25%)   $42.75",
        "Tax (8 25%} -  ...",
        "Tax :8 25%)    $37 15",
        "Tax 8,25%",
    ],
)
def test_the_printed_rate_is_read_beside_any_tax_label_and_through_small_damage(text: str) -> None:
    assert r.printed_tax_rate([rate_page(text)]) == Decimal("0.0825")


@pytest.mark.parametrize(
    "text",
    [
        "Tax 45%",  # no tax is that high
        "Tax 825%",
        "Tax 100%",
        "Save 3% on tax",  # the percentage is not beside the label
        "Tax ID 14",
        "Tax (7%) and levy 5%",  # two different rates on one reading
    ],
)
def test_a_percentage_that_is_not_one_plausible_tax_rate_is_not_used(text: str) -> None:
    assert r.printed_tax_rate([rate_page(text)]) is None


def reading(*lines: str) -> list[dict[str, Any]]:
    """One reading of a page as stored: words laid out in rows."""
    words: list[dict[str, Any]] = []
    for row, line in enumerate(lines):
        x = 0.05
        for token in line.split():
            words.append(
                {"t": token, "x0": x, "y0": 0.05 + 0.04 * row, "x1": x + 0.012 * len(token),
                 "y1": 0.07 + 0.04 * row, "c": None}
            )  # fmt: skip
            x += 0.012 * len(token) + 0.01
    return words


def read_twice(text: str, *others: list[str]) -> Page:
    import json

    return make_page(text=text, alt_words=json.dumps([reading(*lines) for lines in others]))


def test_a_rate_that_most_readings_agree_on_is_used_over_one_that_differs() -> None:
    page = read_twice("Sales tax (826%)", ["Sales tax (8.25%)"], ["Sales tax (8.25%)"])
    assert r.printed_tax_rate([page]) == Decimal("0.0825")
    odd = read_twice("Tax 8.25%", ["Tax 8.26%"], ["Tax 8.25%"])
    assert r.printed_tax_rate([odd]) == Decimal("0.0825")


def test_readings_that_disagree_evenly_set_no_rate() -> None:
    page = read_twice("Tax 8.25%", ["Tax 8.26%"])
    assert r.printed_tax_rate([page]) is None


def test_a_reading_with_two_rates_does_not_vote() -> None:
    page = read_twice("Tax (7%)", ["Tax (7%) and levy 5%"])
    assert r.printed_tax_rate([page]) == Decimal("0.07")


def test_a_tax_too_high_for_a_rate_only_another_reading_could_read_fails() -> None:
    page = read_twice("Sales tax total (826%)  $107.29", ["Sales tax total (8.25%)  $107.29"])
    entry = make_entry(subtotal_minor=124000, tax_total_minor=10729)
    outcome = run(CheckCode.TAX_MATCH, entry=entry, pages=[page])
    assert not outcome.passed and outcome.detail["printed_rate"] == "0.0825"
    assert outcome.detail["most"] == 10230
