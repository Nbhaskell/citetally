"""The PDF text layer: words and boxes straight from the file, and a check that they look sane."""

import io
import random
import re
from datetime import date

import pytest
from PIL import Image
from reportlab.pdfgen.canvas import Canvas

from citetally.models import Word
from citetally.reading import layout, text_layer
from tools.synthetic.docgen import generate
from tools.synthetic.facts import load_facts
from tools.synthetic.families import FAMILIES, Family
from tools.synthetic.render import business_block, render_pdf


def simple_pdf() -> bytes:
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=(612, 792), invariant=1)
    canvas.setFont("Helvetica", 12)
    canvas.drawString(72, 700, "Invoice INV-20112")
    canvas.drawString(72, 680, "Total due $649.92 on 2026-05-20")
    canvas.drawRightString(540, 600, "Page right")
    canvas.showPage()
    canvas.drawString(72, 700, "Second page")
    canvas.save()
    return buffer.getvalue()


def test_words_come_out_with_boxes_as_fractions_of_the_page() -> None:
    words = text_layer.extract_words(simple_pdf(), 0)
    by_text = {word.t: word for word in words}
    assert {"Invoice", "INV-20112", "Total", "$649.92", "2026-05-20", "Page", "right"} <= set(
        by_text
    )
    for word in words:
        assert isinstance(word, Word) and word.c is None  # a text layer has no confidence
        assert 0 <= word.x0 < word.x1 <= 1 and 0 <= word.y0 < word.y1 <= 1
    total, invoice = by_text["Total"], by_text["Invoice"]
    assert total.y0 > invoice.y0  # lower on the page: larger y, origin at the top left
    assert abs(invoice.x0 - 72 / 612) < 0.01
    assert by_text["right"].x1 > 0.85  # right-aligned text ends near the right margin


def test_words_on_the_second_page_are_separate() -> None:
    data = simple_pdf()
    assert [w.t for w in text_layer.extract_words(data, 1)] == ["Second", "page"]
    assert text_layer.page_count(data) == 2


def test_a_page_without_text_has_no_words() -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (300, 300), "white").save(buffer, "PDF")
    assert text_layer.extract_words(buffer.getvalue(), 0) == []


def long_words(count: int) -> list[Word]:
    return [Word(t="word", x0=0.1, y0=0.1, x1=0.15, y1=0.12, c=None) for _ in range(count)]


def test_a_page_with_enough_ordinary_text_is_sane() -> None:
    assert text_layer.looks_sane(long_words(30), min_chars=80)


def test_a_page_with_too_little_text_is_not_enough() -> None:
    assert not text_layer.looks_sane(long_words(5), min_chars=80)
    assert text_layer.looks_sane(long_words(5), min_chars=0)


@pytest.mark.parametrize(
    "junk",
    [
        "�" * 40,  # replacement characters: a broken font map
        "\x01\x02\x03" * 20,
        "" * 30,  # private use area
        "x" * 300,  # no plausible words
    ],
)
def test_garbled_text_layers_are_rejected_so_the_page_goes_to_ocr(junk: str) -> None:
    words = [Word(t=junk, x0=0.1, y0=0.1, x1=0.9, y1=0.12, c=None) for _ in range(3)]
    assert not text_layer.looks_sane(words, min_chars=80)


def test_read_pdf_returns_words_for_good_pages_and_none_for_the_rest() -> None:
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=(612, 792), invariant=1)
    for line in range(8):
        canvas.drawString(
            72, 700 - 14 * line, f"Plumbing supply invoice line number {line} total 12.50"
        )
    canvas.showPage()
    canvas.drawString(72, 700, "hi")
    canvas.save()
    pages = text_layer.read_pdf(buffer.getvalue(), min_chars=80)
    assert pages[0] is not None and len(pages[0]) > 30
    assert pages[1] is None  # too little text: use OCR for this page


def test_a_damaged_pdf_raises_instead_of_returning_nonsense() -> None:
    with pytest.raises(text_layer.TextLayerError):
        text_layer.extract_words(b"%PDF-1.7 not a pdf", 0)


@pytest.mark.parametrize("fam", FAMILIES, ids=lambda f: f.id)
def test_every_printed_value_survives_from_pdf_to_words_to_aligned_text(fam: Family) -> None:
    """The whole read path on realistic documents: no value is lost, split or reordered."""
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
        pdf = render_pdf(doc, fam, business_block(facts))
        words = text_layer.extract_words(pdf, 0)
        text = re.sub(r"\s+", " ", layout.build_text(words))
        wanted = [v for k, v in doc.printed.items() if k != "currency"]
        for row in doc.line_printed:
            wanted += list(row.values())
        for value in wanted:
            assert value in text, (fam.id, vendor_id, value)
