"""The invented business: the fact sheet every generated document is built from."""

import re
from datetime import date
from decimal import Decimal

import pytest

from tools.synthetic.facts import FACTS_FILE, Facts, load_facts

# Seed categories from docs/BACKEND_SCHEMA.md section 1. Phase 2 moves these to db/seed.
SEED_CATEGORIES = {
    "SUPPLIES",
    "FOOD",
    "CLEANING",
    "UTILITIES",
    "REPAIRS",
    "INSURANCE",
    "SOFTWARE",
    "PROFESSIONAL",
    "VEHICLE",
    "MARKETING",
    "OTHER",
}


@pytest.fixture(scope="module")
def facts() -> Facts:
    return load_facts()


def test_fact_sheet_loads_from_the_committed_file(facts: Facts) -> None:
    assert FACTS_FILE.name == "facts.json"
    assert facts.business.default_currency == "USD"
    assert facts.as_of > facts.date_range[1] > facts.date_range[0]
    assert facts.as_of == date(2026, 10, 31)


def test_there_are_about_fifteen_vendors_with_unique_names(facts: Facts) -> None:
    assert 14 <= len(facts.vendors) <= 18
    names = [v.name for v in facts.vendors]
    assert len(set(names)) == len(names)
    assert len({v.id for v in facts.vendors}) == len(facts.vendors)


def test_aliases_are_variants_of_the_name_and_never_collide(facts: Facts) -> None:
    """Printed variants (upper case, abbreviations) belong to one vendor only."""
    owner: dict[str, str] = {}
    for vendor in facts.vendors:
        for text in [vendor.name, *vendor.aliases]:
            key = text.lower()
            assert owner.setdefault(key, vendor.id) == vendor.id, f"{text!r} belongs to two vendors"
        assert len(vendor.aliases) >= 2, vendor.id
        assert vendor.name not in vendor.aliases, vendor.id


def test_vendors_use_the_seed_categories_and_cover_most_of_them(facts: Facts) -> None:
    assert set(facts.categories) == SEED_CATEGORIES
    used = {v.category for v in facts.vendors}
    assert used <= SEED_CATEGORIES
    assert len(used) >= 9


def test_everything_is_visibly_invented(facts: Facts) -> None:
    people_and_places = [(v.phone, v.email, v.address.zip) for v in facts.vendors]
    people_and_places.append(
        (facts.business.phone, facts.business.email, facts.business.address.zip)
    )
    for phone, email, zip_code in people_and_places:
        assert re.search(r"555-01\d\d$", phone), phone
        assert email == "" or email.endswith("example.com"), email
        assert zip_code.startswith("00"), zip_code  # unassigned ZIP range


def test_catalog_items_are_exact_decimals_with_sane_quantity_ranges(facts: Facts) -> None:
    for vendor in facts.vendors:
        assert len(vendor.items) >= 3, vendor.id
        for item in vendor.items:
            assert isinstance(item.unit_price, Decimal) and item.unit_price > 0
            low, high = item.qty
            assert 1 <= low <= high, (vendor.id, item.description)


def test_entry_types_match_how_the_vendor_bills(facts: Facts) -> None:
    receipts = [v for v in facts.vendors if v.entry_type == "receipt"]
    assert len(receipts) >= 2
    for vendor in facts.vendors:
        if vendor.entry_type == "receipt":
            assert vendor.invoice_prefix == "" and vendor.invoice_start == 0
        else:
            assert vendor.invoice_start > 0
    assert sum(v.credit_notes for v in facts.vendors) >= 2


def test_one_vendor_bills_in_another_currency(facts: Facts) -> None:
    currencies = {v.currency for v in facts.vendors}
    assert "USD" in currencies and len(currencies) >= 2
    for code in currencies:
        assert re.fullmatch(r"[A-Z]{3}", code)


def test_tax_rates_are_exact_decimals(facts: Facts) -> None:
    assert facts.business.sales_tax_rate == Decimal("0.0825")
    for vendor in facts.vendors:
        assert Decimal("0") <= vendor.tax_rate(facts.business) <= Decimal("0.25")
