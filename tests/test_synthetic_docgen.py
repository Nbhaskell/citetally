"""Generated documents: exact arithmetic by construction, and truth equal to what is printed."""

import random
from datetime import date, timedelta
from decimal import Decimal

import pytest

from tools.synthetic.arith import line_amount_minor, tax_minor
from tools.synthetic.docgen import arithmetic_problems, generate, reprint, truth
from tools.synthetic.facts import Facts, Vendor, load_facts
from tools.synthetic.model import Doc, Style

DAY = date(2026, 6, 17)


@pytest.fixture(scope="module")
def facts() -> Facts:
    return load_facts()


def vendor_of(facts: Facts, vendor_id: str) -> Vendor:
    return next(v for v in [*facts.vendors, *facts.unlisted_vendors] if v.id == vendor_id)


def make(
    facts: Facts, vendor_id: str, seed: int = 1, style: Style | None = None, **kw: object
) -> Doc:
    vendor = vendor_of(facts, vendor_id)
    return generate(
        random.Random(seed),
        facts,
        vendor,
        doc_id=f"t-{seed}",
        entry_date=DAY,
        serial=seed,
        style=style or Style(),
        **kw,  # type: ignore[arg-type]
    )


def test_same_seed_gives_the_same_document(facts: Facts) -> None:
    assert truth(make(facts, "V01", 7)) == truth(make(facts, "V01", 7))
    assert truth(make(facts, "V01", 7)) != truth(make(facts, "V01", 8))


def test_arithmetic_is_consistent_for_every_vendor_and_many_seeds(facts: Facts) -> None:
    styles = [
        Style(),
        Style(tax_mode="per_line"),
        Style(has_shipping=True, has_discount=True),
        Style(prints_subtotal=False, prints_tax_rate=False),
    ]
    for vendor in [*facts.vendors, *facts.unlisted_vendors]:
        for seed in range(25):
            for style in styles:
                doc = make(facts, vendor.id, seed, style)
                assert arithmetic_problems(doc) == [], (vendor.id, seed, style)


def test_line_amounts_are_quantity_times_price_rounded_half_up(facts: Facts) -> None:
    doc = make(facts, "V03", 3)
    for line in doc.lines:
        assert line.amount_minor == line_amount_minor(line.quantity, line.unit_price)
    assert doc.subtotal_minor == sum(line.amount_minor for line in doc.lines)


def test_document_tax_is_the_rate_times_the_taxable_lines(facts: Facts) -> None:
    doc = make(facts, "V01", 2)
    taxable = sum(line.amount_minor for line in doc.lines if line.taxable)
    assert doc.tax_rate == Decimal("0.07")
    assert doc.tax_total_minor == tax_minor(taxable, Decimal("0.07"))
    assert doc.total_minor == doc.subtotal_minor + doc.tax_total_minor


def test_per_line_tax_adds_up_to_the_tax_total(facts: Facts) -> None:
    doc = make(facts, "V05", 4, Style(tax_mode="per_line"))
    for line in doc.lines:
        expected = tax_minor(line.amount_minor, doc.tax_rate) if line.taxable else 0
        assert line.tax_minor == expected
    assert doc.tax_total_minor == sum(line.tax_minor for line in doc.lines)


def test_total_is_subtotal_plus_tax_plus_shipping_minus_discount(facts: Facts) -> None:
    doc = make(facts, "V01", 5, Style(has_shipping=True, has_discount=True))
    assert doc.shipping_minor > 0 and doc.discount_minor > 0
    assert doc.total_minor == (
        doc.subtotal_minor + doc.tax_total_minor + doc.shipping_minor - doc.discount_minor
    )


def test_vendors_without_taxable_lines_charge_no_tax(facts: Facts) -> None:
    doc = make(facts, "V09", 1)
    assert doc.tax_total_minor == 0


def test_invoices_receipts_and_credit_notes_have_the_right_fields(facts: Facts) -> None:
    invoice = make(facts, "V01", 1)
    assert invoice.entry_type == "invoice"
    assert invoice.invoice_number and invoice.invoice_number.startswith("INV-")
    assert invoice.due_date == DAY + timedelta(days=30)

    receipt = make(facts, "V10", 1)
    assert receipt.entry_type == "receipt"
    assert receipt.invoice_number is None and receipt.due_date is None

    credit = make(facts, "V01", 1, entry_type="credit_note")
    assert credit.entry_type == "credit_note"
    assert credit.invoice_number and credit.invoice_number.startswith("CN-")
    assert credit.due_date is None


def test_credit_notes_are_refused_for_vendors_that_do_not_issue_them(facts: Facts) -> None:
    with pytest.raises(ValueError, match="credit"):
        make(facts, "V09", 1, entry_type="credit_note")


def test_lines_come_from_the_vendor_catalog_within_quantity_ranges(facts: Facts) -> None:
    vendor = vendor_of(facts, "V01")
    catalog = {item.description: item for item in vendor.items}
    for seed in range(20):
        for line in make(facts, "V01", seed).lines:
            item = catalog[line.description]
            assert item.unit_price == line.unit_price
            assert item.qty[0] <= line.quantity <= item.qty[1]


def test_fuel_is_sold_by_the_thousandth_of_a_gallon(facts: Facts) -> None:
    diesel = [
        line
        for seed in range(30)
        for line in make(facts, "V10", seed).lines
        if line.description.endswith(", gal")
    ]
    assert diesel and any(line.quantity % 1 != 0 for line in diesel)
    assert all((line.quantity * 1000) % 1 == 0 for line in diesel)


def test_printed_vendor_name_is_the_name_or_one_of_its_variants(facts: Facts) -> None:
    vendor = vendor_of(facts, "V01")
    seen = {make(facts, "V01", seed).vendor_name for seed in range(60)}
    assert seen <= {vendor.name, *vendor.aliases}
    assert vendor.name in seen and len(seen) > 1


def test_truth_holds_the_printed_values_and_parsed_values(facts: Facts) -> None:
    doc = make(facts, "V01", 9, Style(money="us_symbol", date="dmy_mon"))
    t = truth(doc)
    assert t["entry_type"] == "invoice"
    assert t["vendor_name"] == doc.vendor_name
    assert t["entry_date"] == "2026-06-17"
    assert t["printed"]["entry_date"] == "17 Jun 2026"
    assert t["total_minor"] == doc.total_minor
    assert t["printed"]["total"].startswith("$")
    assert t["lines"][0]["amount_minor"] == doc.lines[0].amount_minor
    assert t["lines"][0]["quantity"] == str(doc.lines[0].quantity)
    assert t["lines"][0]["unit_price"] == str(doc.lines[0].unit_price)


def test_subtotal_is_null_in_the_truth_when_the_document_does_not_print_one(facts: Facts) -> None:
    doc = make(facts, "V09", 3, Style(prints_subtotal=False))
    assert truth(doc)["subtotal_minor"] is None
    assert "subtotal" not in truth(doc)["printed"]
    assert arithmetic_problems(doc) == []


def test_euro_vendor_prints_european_numbers(facts: Facts) -> None:
    doc = make(facts, "V08", 2)
    assert doc.currency == "EUR"
    assert doc.printed["total"].endswith("€")
    assert "," in doc.printed["total"]


def test_reprint_follows_changed_numbers(facts: Facts) -> None:
    doc = make(facts, "V01", 4)
    before = doc.printed["total"]
    doc.total_minor += 10000
    reprint(doc)
    assert doc.printed["total"] != before
    assert truth(doc)["total_minor"] == doc.total_minor
    assert arithmetic_problems(doc) == ["TOTAL_MATCH"]


def test_arithmetic_problems_names_each_broken_rule(facts: Facts) -> None:
    doc = make(facts, "V01", 4)
    doc.lines[0].amount_minor += 500
    assert set(arithmetic_problems(doc)) >= {"LINE_MATH", "SUBTOTAL_MATCH"}
    doc = make(facts, "V01", 4)
    doc.tax_total_minor += 500
    assert "TAX_MATCH" in arithmetic_problems(doc)
