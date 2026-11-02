"""Vendor matching and category choice: plain code over invented vendors."""

import sqlite3

import pytest

from citetally import db
from citetally import repository as repo
from citetally.matching import (
    FUZZY_MIN_SCORE,
    choose_category,
    match_document,
    match_vendor,
    normalize_name,
)
from citetally.models import CategorySource, Vendor, VendorAlias, VendorMatchMethod

STAMP = "2026-01-01T00:00:00Z"


def vendor(id: int, name: str, *, category: int | None = None, active: bool = True) -> Vendor:
    return Vendor(
        id=id,
        name=name,
        normalized_name=normalize_name(name),
        default_category_id=category,
        default_currency=None,
        is_active=active,
        is_synthetic=True,
        created_at=STAMP,
    )


def alias(vendor_id: int, text: str) -> VendorAlias:
    return VendorAlias(
        id=vendor_id * 10,
        vendor_id=vendor_id,
        alias=text,
        normalized_alias=normalize_name(text),
        created_at=STAMP,
    )


VENDORS = [
    vendor(1, "Northfield Pet Supply Co.", category=10),
    vendor(2, "Wren Common Local Directory"),
    vendor(3, "Tanager Fuel & Convenience"),
]
ALIASES = [alias(1, "NF Pet Supply"), alias(3, "Tanager Fuel and Convenience Store")]


# --- normalising -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        ("Northfield Pet Supply Co.", "northfield pet supply"),
        ("NORTHFIELD PET SUPPLY, INC.", "northfield pet supply"),
        ("Acme Co Inc", "acme"),
        ("Smith & Sons, LLC", "smith and sons"),
        ("Smith and Sons Co", "smith and sons"),
        ("Brown & Co.", "brown"),
        ("  Café   Lumière  ", "cafe lumiere"),
        ("O'Neil's Hardware", "oneils hardware"),
        ("Wren-Common Directory", "wren common directory"),
        ("7-Eleven", "7 eleven"),
        ("Pet Supply Company", "pet supply"),
        ("Inc.", "inc"),  # a name that is only a suffix is kept
        ("", ""),
        ("   ", ""),
    ],
)
def test_names_are_lowercased_and_stripped_of_punctuation_and_legal_suffixes(
    printed: str, expected: str
) -> None:
    assert normalize_name(printed) == expected
    assert normalize_name(expected) == expected  # idempotent


# --- matching ----------------------------------------------------------------------------------


def test_the_same_name_with_other_punctuation_or_suffix_is_an_exact_match() -> None:
    match = match_vendor("NORTHFIELD PET SUPPLY, Inc", VENDORS, ALIASES)
    assert (match.vendor_id, match.method, match.score, match.applied) == (
        1,
        VendorMatchMethod.EXACT,
        1.0,
        True,
    )


def test_a_known_alias_is_applied_automatically() -> None:
    match = match_vendor("nf pet supply", VENDORS, ALIASES)
    assert (match.vendor_id, match.method, match.applied) == (1, VendorMatchMethod.ALIAS, True)


def test_a_vendor_name_beats_an_alias_with_the_same_text() -> None:
    clash = [alias(2, "Northfield Pet Supply")]
    assert match_vendor("Northfield Pet Supply", VENDORS, clash).method == VendorMatchMethod.EXACT


def test_a_near_miss_is_only_a_suggestion_and_leaves_the_vendor_empty() -> None:
    match = match_vendor("Northfeld Pet Suply", VENDORS, ALIASES)
    assert match.vendor_id is None and match.method is None and not match.applied
    (top, *_) = match.suggestions
    assert top.vendor_id == 1 and FUZZY_MIN_SCORE <= top.score < 1


def test_suggestions_are_best_first_at_most_three_and_above_the_floor() -> None:
    many = [vendor(i, f"Harbor Light {word}") for i, word in enumerate("ABCDE", start=10)]
    match = match_vendor("Harbor Light", many, [])
    scores = [s.score for s in match.suggestions]
    assert len(match.suggestions) == 3 and scores == sorted(scores, reverse=True)
    assert all(score >= FUZZY_MIN_SCORE for score in scores)


def test_an_unrelated_name_matches_nothing_and_suggests_nothing() -> None:
    match = match_vendor("Quarry Street Bakery", VENDORS, ALIASES)
    assert (match.vendor_id, match.method, match.suggestions) == (None, None, ())


def test_a_changed_digit_in_a_name_is_not_a_suggestion() -> None:
    near = [vendor(7, "Route 66 Diner")]
    assert match_vendor("Route 67 Diner", near, []).suggestions == ()


@pytest.mark.parametrize("printed", [None, "", "   ", "..."])
def test_a_missing_name_matches_nothing(printed: str | None) -> None:
    match = match_vendor(printed, VENDORS, ALIASES)
    assert (match.vendor_id, match.suggestions) == (None, ())


def test_an_inactive_vendor_is_never_matched_or_suggested() -> None:
    retired = [vendor(9, "Old Harbor Marine", active=False)]
    assert match_vendor("Old Harbor Marine", retired, []).vendor_id is None
    assert match_vendor("Old Harbor Marin", retired, []).suggestions == ()


# --- category ----------------------------------------------------------------------------------


CATEGORIES = {"SUPPLIES": 10, "FOOD": 11, "OTHER": 12}


def test_a_known_vendors_default_category_wins_over_the_models_suggestion() -> None:
    choice = choose_category(VENDORS[0], "FOOD", CATEGORIES)
    assert (choice.category_id, choice.source) == (10, CategorySource.VENDOR_DEFAULT)


def test_without_a_vendor_default_the_models_suggestion_is_used() -> None:
    for known in (None, VENDORS[1]):
        choice = choose_category(known, "FOOD", CATEGORIES)
        assert (choice.category_id, choice.source) == (11, CategorySource.MODEL)


def test_no_default_and_no_usable_suggestion_leaves_the_category_for_the_reviewer() -> None:
    for suggestion in (None, "", "GAMBLING"):
        choice = choose_category(None, suggestion, CATEGORIES)
        assert (choice.category_id, choice.source) == (None, None)


# --- against the database ----------------------------------------------------------------------


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = db.connect(":memory:")
    db.migrate(connection)
    db.seed_categories(connection)
    return connection


def test_match_document_reads_vendors_aliases_and_categories_from_the_database(
    conn: sqlite3.Connection,
) -> None:
    supplies = repo.get_category_by_code(conn, "SUPPLIES")
    created = repo.create_vendor(
        conn,
        "Northfield Pet Supply Co.",
        normalize_name("Northfield Pet Supply Co."),
        default_category_id=supplies.id,
    )
    repo.add_alias(conn, created.id, "NF Pet", normalize_name("NF Pet"))

    exact = match_document(conn, "northfield pet supply", "FOOD")
    assert (exact.vendor.vendor_id, exact.category.source) == (
        created.id,
        CategorySource.VENDOR_DEFAULT,
    )
    assert exact.category.category_id == supplies.id

    by_alias = match_document(conn, "NF Pet", None)
    assert by_alias.vendor.method == VendorMatchMethod.ALIAS

    unknown = match_document(conn, "Somebody Else Entirely", "FOOD")
    assert unknown.vendor.vendor_id is None
    assert unknown.category.source == CategorySource.MODEL


def test_an_inactive_category_is_not_offered(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE categories SET is_active = 0 WHERE code = 'FOOD'")
    assert match_document(conn, "Nobody", "FOOD").category.category_id is None


# --- Stage 2: the model copied only part of a name the page prints in full -----------------------


PAGE = "Tanager Fuel & Convenience\n1 Route 9\nReceipt R-40512\nBill to Kestrel Hollow Plumbing"


def test_a_shortened_name_is_matched_when_the_page_prints_the_whole_known_name() -> None:
    match = match_vendor("Fuel & Convenience", VENDORS, ALIASES, page_text=PAGE)
    assert (match.vendor_id, match.method, match.score) == (3, VendorMatchMethod.EXACT, 1.0)


def test_a_shortened_name_is_matched_through_an_alias_printed_on_the_page() -> None:
    page = "NF Pet Supply invoice 20417 to Kestrel Hollow Plumbing"
    match = match_vendor("Pet Supply", VENDORS, ALIASES, page_text=page)
    assert (match.vendor_id, match.method) == (1, VendorMatchMethod.ALIAS)


def test_a_known_vendor_named_elsewhere_on_the_page_is_not_taken_for_the_issuer() -> None:
    """The model's name must be part of the known name: a different vendor's name in the
    remarks proves nothing about who issued this document."""
    page = "Acme Plumbing Wholesale\nCredit for Northfield Pet Supply Co. return"
    match = match_vendor("Acme Plumbing Wholesale", VENDORS, ALIASES, page_text=page)
    assert match.vendor_id is None


def test_two_known_vendors_that_fit_leave_the_choice_to_the_reviewer() -> None:
    vendors = [*VENDORS, vendor(4, "Wren Common Directory")]
    page = "Wren Common Local Directory and Wren Common Directory"
    match = match_vendor("Wren Common", vendors, ALIASES, page_text=page)
    assert match.vendor_id is None


def test_the_page_is_not_searched_when_the_printed_name_already_matches_or_is_missing() -> None:
    exact = match_vendor("Northfield Pet Supply Co.", VENDORS, ALIASES, page_text=PAGE)
    assert exact.method is VendorMatchMethod.EXACT and exact.vendor_id == 1
    assert match_vendor(None, VENDORS, ALIASES, page_text=PAGE).vendor_id is None


def test_a_name_that_is_not_part_of_any_name_on_the_page_matches_nothing() -> None:
    assert match_vendor("Brightside Janitorial", VENDORS, ALIASES, page_text=PAGE).vendor_id is None


def test_an_inactive_vendor_is_not_found_on_the_page() -> None:
    vendors = [vendor(3, "Tanager Fuel & Convenience", active=False)]
    assert match_vendor("Fuel & Convenience", vendors, [], page_text=PAGE).vendor_id is None
