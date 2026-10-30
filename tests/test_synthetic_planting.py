"""Planted problems: each breaks exactly one thing and records which check should notice."""

import random
from datetime import date, timedelta

import pytest

from tools.synthetic.docgen import arithmetic_problems, generate, truth
from tools.synthetic.facts import Facts, Vendor, load_facts
from tools.synthetic.model import Doc, Style
from tools.synthetic.planting import (
    EXPECTED_CHECKS,
    PLANTED_KINDS,
    eligible,
    plant,
)

STYLE = Style(has_shipping=True)


@pytest.fixture(scope="module")
def facts() -> Facts:
    return load_facts()


def vendor_of(facts: Facts, vendor_id: str) -> Vendor:
    return next(v for v in [*facts.vendors, *facts.unlisted_vendors] if v.id == vendor_id)


def make(facts: Facts, vendor_id: str = "V01", seed: int = 1, style: Style = STYLE) -> Doc:
    return generate(
        random.Random(seed),
        facts,
        vendor_of(facts, vendor_id),
        doc_id=f"d-{seed}",
        entry_date=date(2026, 6, 17),
        serial=seed,
        style=style,
    )


def test_there_are_twelve_kinds_and_each_names_expected_checks() -> None:
    assert len(PLANTED_KINDS) == 12
    assert set(EXPECTED_CHECKS) == set(PLANTED_KINDS)
    valid = {
        "REQUIRED_FIELDS", "LINE_MATH", "SUBTOTAL_MATCH", "TAX_MATCH", "TOTAL_MATCH",
        "DUPLICATE_SUSPECT", "UNKNOWN_VENDOR", "AMOUNT_OUTLIER", "DATE_SANITY",
        "CURRENCY_CHECK", "SUSPICIOUS_TEXT",
    }  # fmt: skip
    for kind, codes in EXPECTED_CHECKS.items():
        assert codes and set(codes) <= valid, kind


def test_total_mismatch_changes_only_the_printed_total(facts: Facts) -> None:
    doc = make(facts)
    good = doc.total_minor
    planted = plant("total_mismatch", doc, random.Random(3), facts)
    assert planted["kind"] == "total_mismatch"
    assert abs(doc.total_minor - good) >= 100
    assert arithmetic_problems(doc) == ["TOTAL_MATCH"]
    assert truth(doc)["total_minor"] == doc.total_minor  # truth is what is printed
    assert "cents" in planted["detail"]


def test_line_math_breaks_one_line_and_keeps_the_totals_consistent(facts: Facts) -> None:
    doc = make(facts)
    plant("line_math", doc, random.Random(3), facts)
    assert arithmetic_problems(doc) == ["LINE_MATH"]


def test_tax_mismatch_changes_tax_and_total_together(facts: Facts) -> None:
    doc = make(facts)
    assert eligible("tax_mismatch", doc)
    plant("tax_mismatch", doc, random.Random(3), facts)
    assert arithmetic_problems(doc) == ["TAX_MATCH"]


def test_tax_mismatch_needs_a_printed_rate_and_taxable_lines(facts: Facts) -> None:
    assert not eligible("tax_mismatch", make(facts, style=Style(prints_tax_rate=False)))
    assert not eligible("tax_mismatch", make(facts, "V09"))  # nothing taxable


def test_future_date_is_after_the_as_of_date(facts: Facts) -> None:
    doc = make(facts)
    plant("future_date", doc, random.Random(3), facts)
    assert doc.entry_date > facts.as_of + timedelta(days=1)
    assert truth(doc)["entry_date"] == doc.entry_date.isoformat()
    assert doc.due_date is None or doc.due_date >= doc.entry_date
    assert arithmetic_problems(doc) == []


def test_due_before_entry_puts_the_due_date_in_the_past(facts: Facts) -> None:
    doc = make(facts)
    assert eligible("due_before_entry", doc)
    plant("due_before_entry", doc, random.Random(3), facts)
    assert doc.due_date is not None and doc.due_date < doc.entry_date
    assert not eligible("due_before_entry", make(facts, "V10"))  # a receipt has no due date


def test_missing_invoice_number_is_only_for_documents_that_have_one(facts: Facts) -> None:
    doc = make(facts)
    plant("missing_invoice_number", doc, random.Random(3), facts)
    assert doc.invoice_number is None and truth(doc)["invoice_number"] is None
    assert "invoice_number" not in doc.printed
    assert not eligible("missing_invoice_number", make(facts, "V10"))


def test_currency_mismatch_prints_another_currency(facts: Facts) -> None:
    doc = make(facts)
    plant("currency_mismatch", doc, random.Random(3), facts)
    assert doc.currency == "CAD" and doc.printed["total"].startswith("CA$")
    assert not eligible("currency_mismatch", make(facts, "V08"))  # already not USD


def test_injection_text_adds_an_instruction_aimed_at_an_assistant(facts: Facts) -> None:
    doc = make(facts)
    plant("injection_text", doc, random.Random(3), facts)
    text = " ".join(doc.notes).lower()
    assert any(word in text for word in ("ignore", "approve", "skip", "assistant"))
    assert arithmetic_problems(doc) == []


def test_unknown_vendor_needs_a_vendor_outside_the_list(facts: Facts) -> None:
    stranger = make(facts, "X01")
    assert eligible("unknown_vendor", stranger)
    plant("unknown_vendor", stranger, random.Random(3), facts)
    assert not eligible("unknown_vendor", make(facts, "V01"))


def test_amount_outlier_scales_quantities_past_three_times_the_usual(facts: Facts) -> None:
    doc = make(facts)
    usual = doc.total_minor
    assert eligible("amount_outlier", doc, vendor_median_minor=usual)
    plant("amount_outlier", doc, random.Random(3), facts, vendor_median_minor=usual)
    assert doc.total_minor >= 3.3 * usual
    assert arithmetic_problems(doc) == []


def test_amount_outlier_is_refused_when_the_scale_would_be_silly(facts: Facts) -> None:
    doc = make(facts, "V06")  # fixed monthly premium
    assert not eligible("amount_outlier", doc, vendor_median_minor=doc.total_minor * 20)


def test_duplicate_invoice_number_reuses_the_number_of_an_earlier_document(facts: Facts) -> None:
    original = make(facts, seed=1)
    doc = make(facts, seed=2)
    planted = plant("duplicate_invoice_number", doc, random.Random(3), facts, original=original)
    assert doc.invoice_number == original.invoice_number
    assert doc.vendor.id == original.vendor.id
    assert planted["duplicate_of"] == original.id
    assert doc.total_minor != original.total_minor or doc.entry_date != original.entry_date


def test_duplicate_content_repeats_the_figures_under_a_new_number_and_nearby_date(
    facts: Facts,
) -> None:
    original = make(facts, seed=1)
    doc = make(facts, seed=2)
    planted = plant("duplicate_content", doc, random.Random(3), facts, original=original)
    assert doc.total_minor == original.total_minor
    assert doc.currency == original.currency and doc.vendor.id == original.vendor.id
    assert doc.invoice_number != original.invoice_number
    assert 1 <= abs((doc.entry_date - original.entry_date).days) <= 5
    assert planted["duplicate_of"] == original.id
    assert arithmetic_problems(doc) == []


def test_receipts_duplicate_by_content_without_a_number(facts: Facts) -> None:
    original = make(facts, "V10", seed=1, style=Style())
    doc = make(facts, "V10", seed=2, style=Style())
    plant("duplicate_content", doc, random.Random(3), facts, original=original)
    assert doc.invoice_number is None and doc.total_minor == original.total_minor
    assert not eligible("duplicate_invoice_number", doc, original=original)


def test_planting_is_deterministic(facts: Facts) -> None:
    a, b = make(facts), make(facts)
    plant("total_mismatch", a, random.Random(5), facts)
    plant("total_mismatch", b, random.Random(5), facts)
    assert truth(a) == truth(b)


def test_planting_an_ineligible_document_is_an_error(facts: Facts) -> None:
    with pytest.raises(ValueError, match="eligible"):
        plant("due_before_entry", make(facts, "V10"), random.Random(1), facts)
