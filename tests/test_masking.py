"""Masking card-like and labelled account numbers before any model sees the text."""

import random
import re
from datetime import date

import pytest

from citetally.models import Word
from citetally.reading import layout, masking, text_layer
from tools.synthetic.docgen import generate
from tools.synthetic.facts import load_facts
from tools.synthetic.families import FAMILIES, Family
from tools.synthetic.render import business_block, render_pdf

# Published test numbers of the card networks; none belongs to a real card.
VISA = "4111111111111111"
MASTERCARD = "5555555555554444"
AMEX = "378282246310005"
DISCOVER = "6011111111111117"
DINERS = "30569309025904"
JCB = "3530111333300000"
VISA_13 = "4222222222222"


def w(text: str, x0: float, y0: float = 0.2, h: float = 0.012) -> Word:
    return Word(t=text, x0=x0, y0=y0, x1=min(x0 + 0.007 * len(text), 1.0), y1=y0 + h, c=90.0)


def luhn_valid_number_starting_with(prefix: str, length: int) -> str:
    """A number that passes the Luhn check, for building cases that are not card networks."""
    body = prefix + "0" * (length - len(prefix) - 1)
    for check in "0123456789":
        if masking.luhn_valid(body + check):
            return body + check
    raise AssertionError("no check digit works")


@pytest.mark.parametrize("number", [VISA, MASTERCARD, AMEX, DISCOVER, DINERS, JCB, VISA_13])
def test_the_published_test_numbers_pass_the_luhn_check_and_look_like_cards(number: str) -> None:
    assert masking.luhn_valid(number)
    assert masking.is_card_number(number)


def test_the_luhn_check_rejects_a_changed_digit_and_non_digits() -> None:
    assert not masking.luhn_valid("4111111111111112")
    assert not masking.luhn_valid("")
    assert not masking.luhn_valid("4111 1111")
    assert not masking.luhn_valid("411111111111111a")


def test_a_number_must_also_have_a_card_length_and_a_network_prefix() -> None:
    assert not masking.is_card_number(luhn_valid_number_starting_with("1", 16))  # no such network
    assert not masking.is_card_number(luhn_valid_number_starting_with("4", 12))  # too short
    assert not masking.is_card_number(luhn_valid_number_starting_with("4", 20))  # too long
    assert not masking.is_card_number(luhn_valid_number_starting_with("37", 16))  # Amex is 15
    assert masking.is_card_number(
        luhn_valid_number_starting_with("2221", 16)
    )  # Mastercard 2-series


@pytest.mark.parametrize(
    ("text", "masked"),
    [
        (f"Card {VISA} exp 04/29", "Card ************1111 exp 04/29"),
        ("Card 4111 1111 1111 1111.", "Card **** **** **** 1111."),
        ("Card 4111-1111-1111-1111", "Card ****-****-****-1111"),
        ("Amex 3782 822463 10005", "Amex **** ****** *0005"),
        (f"{VISA} and {MASTERCARD}", "************1111 and ************4444"),
        (f"({VISA})", "(************1111)"),
    ],
)
def test_card_numbers_in_text_keep_only_the_last_four_digits(text: str, masked: str) -> None:
    assert masking.mask_card_numbers(text) == masked


@pytest.mark.parametrize(
    "text",
    [
        "Invoice No.: INV-20112",
        "Total due $4,111,111,111,111.11",
        "Total due 4.111.111.111.111,11",
        "Tel 555-0111 and 555-0171",
        "Date 2026-05-20",
        "PO 4111111111111112",  # fails the Luhn check
        f"INV-{VISA}",  # part of a reference, not a card
        f"{VISA}A",
        f"A{VISA}",
        f"{VISA}1",  # one digit too many to be this number
        "Qty 4 1 1 1 $7.85 $282.60",
        f"Order {luhn_valid_number_starting_with('1', 16)}",
        "",
    ],
)
def test_ordinary_numbers_are_left_alone(text: str) -> None:
    assert masking.mask_card_numbers(text) == text


@pytest.mark.parametrize(
    ("text", "masked"),
    [
        ("Bank account #: 000123456789", "Bank account #: ********6789"),
        ("Acct no 4412 8890 1234", "Acct no **** **** 1234"),
        ("Routing number 021000021", "Routing number *****0021"),
        ("routing: 021000021", "routing: *****0021"),
        ("ABA 021000021", "ABA *****0021"),
        ("IBAN DE89 3704 0044 0532 0130 00", "IBAN **** **** **** **** **30 00"),
        ("Account number:        12345678", "Account number:        ****5678"),
        ("Account number: 12345678  Total $5.00", "Account number: ****5678  Total $5.00"),
    ],
)
def test_labelled_numbers_keep_only_the_last_four_characters(text: str, masked: str) -> None:
    assert masking.mask_labelled_numbers(text) == masked


@pytest.mark.parametrize(
    "text",
    [
        "Account bill no.: 4412889012",  # the utility template's invoice number label
        "Invoice No.: 20112",
        "Account number",  # a label with no value
        "Account number:\n12345678",  # the value is on another line
        "Account number: 12345",  # too short to be an account number
        "Routing slip 021000021",
        "PO number: 8687",
        "Total due $649.92",
    ],
)
def test_other_labels_and_short_values_are_left_alone(text: str) -> None:
    assert masking.mask_labelled_numbers(text) == text


def test_the_text_for_a_model_has_both_kinds_masked_and_masking_twice_changes_nothing() -> None:
    text = f"Card {VISA}\nAccount number: 12345678\nInvoice No.: INV-20112"
    once = masking.mask_for_model(text)
    assert once == "Card ************1111\nAccount number: ****5678\nInvoice No.: INV-20112"
    assert masking.mask_for_model(once) == once


def test_a_card_number_in_one_word_is_masked_in_the_word_and_nothing_else_changes() -> None:
    words = [w("Card", 0.1), w(VISA, 0.2), w("Total", 0.5)]
    masked = masking.mask_words(words)
    assert [m.t for m in masked] == ["Card", "************1111", "Total"]
    assert masked[0] == words[0] and masked[2] == words[2]
    assert (masked[1].x0, masked[1].x1, masked[1].c) == (words[1].x0, words[1].x1, words[1].c)


def test_a_card_number_split_over_words_is_masked_across_them() -> None:
    words = [w("Card", 0.1)] + [
        w(group, 0.2 + 0.04 * i) for i, group in enumerate(["4111", "1111", "1111", "1111"])
    ]
    masked = masking.mask_words(words)
    assert [m.t for m in masked] == ["Card", "****", "****", "****", "1111"]


def test_words_are_returned_in_the_order_they_came_in() -> None:
    words = [w("1111", 0.32), w("4111", 0.20), w("1111", 0.28), w("1111", 0.24), w("Card", 0.1)]
    masked = masking.mask_words(words)
    assert [m.t for m in masked] == ["1111", "****", "****", "****", "Card"]


def test_digit_groups_on_different_lines_or_far_apart_are_not_joined() -> None:
    lines = [w("4111", 0.1, 0.20), w("1111", 0.1, 0.25), w("1111", 0.1, 0.30), w("1111", 0.1, 0.35)]
    assert masking.mask_words(lines) == lines
    columns = [w("4111", 0.05), w("1111", 0.30), w("1111", 0.55), w("1111", 0.80)]
    assert masking.mask_words(columns) == columns


def test_a_card_split_by_ocr_with_hyphens_is_masked() -> None:
    words = [w("4111-1111-", 0.2), w("1111-1111", 0.28)]
    assert [m.t for m in masking.mask_words(words)] == ["****-****-", "****-1111"]


def test_only_the_card_is_masked_when_other_numbers_sit_beside_it() -> None:
    words = [w("55", 0.1), w("4111", 0.13), w("1111", 0.17), w("1111", 0.21), w("1111", 0.25)]
    masked = masking.mask_words(words)
    assert [m.t for m in masked][-4:] == ["****", "****", "****", "1111"]
    assert masked[0].t in {"55", "**"}  # a preceding group is never revealed as part of the card


def test_masked_words_build_text_with_the_card_hidden() -> None:
    words = [w("Card", 0.1), w("4111", 0.2), w("1111", 0.24), w("1111", 0.28), w("1111", 0.32)]
    text = layout.build_text(masking.mask_words(words))
    assert "4111" not in text and "1111" in text
    assert VISA[:12] not in text.replace(" ", "")


def test_masking_does_not_change_the_boxes_the_text_or_the_count_of_ordinary_pages() -> None:
    words = [w("Total", 0.1), w("$649.92", 0.3), w("INV-20112", 0.5), w("2026-05-20", 0.7)]
    assert masking.mask_words(words) == words
    assert masking.mask_words([]) == []


@pytest.mark.parametrize("fam", FAMILIES, ids=lambda f: f.id)
def test_no_printed_value_in_any_template_family_is_changed_by_masking(fam: Family) -> None:
    """Every invoice number, date, amount and phone number survives the whole masking path."""
    facts = load_facts()
    vendors = {v.id: v for v in facts.vendors}
    for vendor_id in fam.vendors:
        entry_type = fam.entry_types[0]
        doc = generate(
            random.Random(3),
            facts,
            vendors[vendor_id],
            doc_id="t",
            entry_date=date(2026, 5, 20),
            serial=3,
            style=fam.style,
            entry_type="credit_note" if entry_type == "credit_note" else None,
        )
        words = text_layer.extract_words(render_pdf(doc, fam, business_block(facts)), 0)
        assert masking.mask_words(words) == words
        text = layout.build_text(words)
        assert masking.mask_for_model(text) == text
        wanted = [v for k, v in doc.printed.items() if k != "currency"]
        for row in doc.line_printed:
            wanted += list(row.values())
        flat = re.sub(r"\s+", " ", masking.mask_for_model(text))
        for value in wanted:
            assert value in flat, (fam.id, vendor_id, value)


def test_few_random_sixteen_digit_references_look_like_cards() -> None:
    """About a tenth pass Luhn and about a quarter of those have a network prefix and length."""
    rng = random.Random(5)
    hits = sum(masking.is_card_number(str(rng.randrange(10**15, 10**16))) for _ in range(10_000))
    assert hits < 500
