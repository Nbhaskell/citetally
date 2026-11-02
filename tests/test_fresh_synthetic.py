"""The second business, the ten new layouts, the damage levels and the two new sets.

What is checked without opening a scan: every clean PDF of both sets carries its printed values in
its text layer; the sets are valid and reproduce exactly; the committed `dev2` key matches the
generator; and the sealed key's hash, committed before any fix was made, still matches what the
generator produces. If someone changes what the generator writes into an answer key, that last
test fails, which is the point of committing the hash.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from PIL import Image

from tools.synthetic import fresh_build as fb
from tools.synthetic.docgen import truth
from tools.synthetic.facts import load_facts
from tools.synthetic.fresh_degrade import LEVELS, make_fresh_file
from tools.synthetic.fresh_families import FRESH_FAMILIES, families_of
from tools.synthetic.fresh_render import render_fresh_pdf
from tools.synthetic.render import business_block

FACTS = load_facts(fb.FACTS_RIDGE)
SQUASH = re.compile(r"\s+")


def page_text(pdf: bytes) -> str:
    page = pdfium.PdfDocument(pdf)[0]
    return SQUASH.sub(" ", page.get_textpage().get_text_range())


def test_the_second_business_is_invented_and_labelled() -> None:
    assert "SYNTHETIC TEST DATA" in FACTS.note
    vendors = [*FACTS.vendors, *FACTS.unlisted_vendors]
    assert len({v.id for v in vendors}) == len(vendors) == 19
    for vendor in vendors:
        assert re.fullmatch(r"555-01\d\d", vendor.phone), vendor.phone
        assert vendor.email == "" or vendor.email.endswith(".example.com"), vendor.email
        assert vendor.address.zip.startswith("00"), vendor.address.zip
        assert vendor.category in FACTS.categories
    assert FACTS.business.email.endswith("@example.com")
    first = {v.name for v in load_facts().vendors}
    assert not first & {v.name for v in vendors}  # no vendor is shared with the first business


def test_ten_new_layouts_five_each_and_all_use_listed_vendors() -> None:
    assert [f.id for f in FRESH_FAMILIES] == [f"T{n}" for n in range(16, 26)]
    assert len(families_of("dev2")) == len(families_of("sealed")) == 5
    listed = {v.id for v in FACTS.vendors}
    for family in FRESH_FAMILIES:
        assert set(family.vendors) <= listed
        for vendor_id in family.vendors:
            vendor = next(v for v in FACTS.vendors if v.id == vendor_id)
            assert vendor.entry_type == family.entry_types[0] or family.entry_types == (
                "credit_note",
            )
            if family.entry_types == ("credit_note",):
                assert vendor.credit_notes


@pytest.mark.parametrize("suite", ["dev2", "sealed"])
def test_every_clean_pdf_carries_its_printed_values_in_the_text_layer(suite: str) -> None:
    block = business_block(FACTS)
    for entry in fb.prepare(suite, FACTS):
        doc = entry.doc
        text = page_text(render_fresh_pdf(doc, entry.family, block))  # type: ignore[arg-type]
        printed = doc.printed
        for key in ("total", "entry_date", "invoice_number", "due_date", "po_number"):
            if key in printed:
                assert printed[key] in text, (doc.id, key, printed[key])
        for row in doc.line_printed:
            for field in ("quantity", "unit_price", "amount"):
                assert row[field] in text, (doc.id, field, row[field])
            for word in row["description"].split():  # a long description may wrap onto two lines
                assert word in text, (doc.id, word)
        assert "SYNTHETIC TEST DATA" in text


@pytest.mark.parametrize("suite", ["dev2", "sealed"])
def test_a_set_is_valid_has_every_kind_and_reproduces_exactly(suite: str) -> None:
    first, digest = fb.build(suite, files=False)
    second, again = fb.build(suite, files=False)
    assert digest == again and first.header.counts == second.header.counts
    counts = first.header.counts
    assert counts["documents"] == fb.PER_FAMILY[suite] * 5
    assert all(n >= (2 if suite == "dev2" else 4) for n in counts["by_planted_kind"].values())
    assert all(n > 0 for n in counts["by_level"].values())
    receipts = [i for i in first.items if i.truth.entry_type == "receipt"]
    unnumbered = [i for i in receipts if not i.truth.invoice_number]
    assert receipts and len(unnumbered) <= len(receipts) // 4
    assert all(i.planted for i in unnumbered)  # only a planted problem leaves a receipt unnumbered


def test_the_committed_dev2_key_is_what_the_generator_writes() -> None:
    committed = fb.load_fresh(fb.golden_path("dev2"))
    built, digest = fb.build("dev2", files=False)
    assert fb.truth_digest(committed) == digest
    assert [i.id for i in committed] == [i.id for i in built.items]


def test_the_sealed_key_still_matches_the_hash_committed_before_any_fix() -> None:
    committed = fb.hash_path().read_text(encoding="utf-8").split()[0]
    _, digest = fb.build("sealed", files=False)
    assert digest == committed


def test_the_sealed_answer_key_is_not_in_the_repository() -> None:
    assert not (fb.GOLDEN_DIR / "citetally_v2_sealed.json").exists()
    assert fb.golden_path("sealed").is_relative_to(fb.DATA_ROOT)  # data/ is git-ignored


@pytest.mark.parametrize(
    ("condition", "level"),
    [(c, lv) for c, levels in LEVELS.items() for lv in levels],
)
def test_every_level_of_damage_makes_a_readable_file_of_the_right_kind(
    condition: str, level: str
) -> None:
    entry = fb.prepare("dev2", FACTS)[0]
    pdf = render_fresh_pdf(entry.doc, entry.family, business_block(FACTS))  # type: ignore[arg-type]
    data, extension = make_fresh_file(pdf, condition, level, seed=7)
    again, _ = make_fresh_file(pdf, condition, level, seed=7)
    assert data == again  # same seed, same bytes
    assert extension == ("jpg" if condition == "phone_photo" else "pdf")
    if condition == "phone_photo":
        image = Image.open(io.BytesIO(data))
        assert image.size == ((2400, 3000) if level == "mild" else (1500, 1900))
    elif condition != "clean_pdf":
        assert not page_text(data).strip()  # a scan has no text layer
    else:
        assert data == pdf


def test_a_level_that_a_condition_does_not_use_is_refused() -> None:
    with pytest.raises(ValueError):
        make_fresh_file(b"", "scan_heavy", "mild", seed=1)


def test_the_answer_key_holds_what_is_printed_and_the_levels_and_features() -> None:
    for item in fb.load_fresh(fb.golden_path("dev2")):
        assert item.level in LEVELS[item.condition]
        assert item.features
        assert item.truth.printed["total"]
    blob = json.dumps(truth(fb.prepare("dev2", FACTS)[0].doc))
    assert "total" in blob


def test_the_first_set_is_unchanged_by_the_new_code() -> None:
    from tools.synthetic.build import build

    golden = build(files=False, golden_path=None)
    committed = json.loads((Path(fb.GOLDEN_DIR) / "citetally_v1.json").read_text(encoding="utf-8"))
    assert [i.id for i in golden.items] == [i["id"] for i in committed["items"]]
    assert golden.header.counts["documents"] == committed["header"]["counts"]["documents"]
