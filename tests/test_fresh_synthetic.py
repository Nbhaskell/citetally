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
FACTS_MARIGOLD = load_facts(fb.FACTS_MARIGOLD)
FACTS_FERNWICK = load_facts(fb.FACTS_FERNWICK)
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


def test_the_third_business_is_invented_labelled_and_shares_nothing() -> None:
    assert "SYNTHETIC TEST DATA" in FACTS_MARIGOLD.note
    vendors = [*FACTS_MARIGOLD.vendors, *FACTS_MARIGOLD.unlisted_vendors]
    assert len({v.id for v in vendors}) == len(vendors) == 19
    for vendor in vendors:
        assert re.fullmatch(r"555-01\d\d", vendor.phone), vendor.phone
        assert vendor.email == "" or vendor.email.endswith(".example.com"), vendor.email
        assert vendor.address.zip.startswith("00"), vendor.address.zip
        assert vendor.category in FACTS_MARIGOLD.categories
    assert FACTS_MARIGOLD.business.email.endswith("@example.com")
    earlier = {v.name for f in (load_facts(), FACTS) for v in [*f.vendors, *f.unlisted_vendors]}
    assert not earlier & {v.name for v in vendors}


def test_the_fourth_business_is_invented_labelled_and_shares_no_vendor() -> None:
    assert "SYNTHETIC TEST DATA" in FACTS_FERNWICK.note
    vendors = [*FACTS_FERNWICK.vendors, *FACTS_FERNWICK.unlisted_vendors]
    assert len({v.id for v in vendors}) == len(vendors) == 19
    for vendor in vendors:
        assert re.fullmatch(r"555-01\d\d", vendor.phone), vendor.phone
        assert vendor.email == "" or vendor.email.endswith(".example.com"), vendor.email
        assert vendor.address.zip.startswith("00"), vendor.address.zip
        assert vendor.category in FACTS_FERNWICK.categories
    assert FACTS_FERNWICK.business.email.endswith("@example.com")
    earlier = {
        v.name
        for f in (load_facts(), FACTS, FACTS_MARIGOLD)
        for v in [*f.vendors, *f.unlisted_vendors]
    }
    assert not earlier & {v.name for v in vendors}


def test_twenty_layouts_five_per_set_and_all_use_listed_vendors() -> None:
    assert [f.id for f in FRESH_FAMILIES] == [f"T{n}" for n in range(16, 36)]
    assert len(families_of("dev2")) == len(families_of("sealed")) == 5
    assert len(families_of("sealed2")) == len(families_of("sealed3")) == 5
    for family in FRESH_FAMILIES:
        facts = load_facts(fb.FACTS_OF[family.split])
        listed = {v.id for v in facts.vendors}
        assert set(family.vendors) <= listed
        for vendor_id in family.vendors:
            vendor = next(v for v in facts.vendors if v.id == vendor_id)
            assert vendor.entry_type == family.entry_types[0] or family.entry_types == (
                "credit_note",
            )
            if family.entry_types == ("credit_note",):
                assert vendor.credit_notes


@pytest.mark.parametrize("suite", ["dev2", "sealed", "sealed2", "sealed3"])
def test_every_clean_pdf_carries_its_printed_values_in_the_text_layer(suite: str) -> None:
    facts = load_facts(fb.FACTS_OF[suite])
    block = business_block(facts)
    for entry in fb.prepare(suite, facts):
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
        for note in doc.notes:  # a planted instruction line must really be on the page
            for word in note.split():
                assert word in text, (doc.id, "note", word)


@pytest.mark.parametrize("suite", ["dev2", "sealed", "sealed2", "sealed3"])
def test_a_set_is_valid_has_every_kind_and_reproduces_exactly(suite: str) -> None:
    first, digest = fb.build(suite, files=False)
    second, again = fb.build(suite, files=False)
    assert digest == again and first.header.counts == second.header.counts
    counts = first.header.counts
    assert counts["documents"] == fb.PER_FAMILY[suite] * 5
    assert all(n >= fb.MIN_PER_KIND[suite] for n in counts["by_planted_kind"].values())
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


def test_the_second_sealed_key_matches_the_hash_committed_before_its_fixes() -> None:
    committed = fb.hash_path("sealed2").read_text(encoding="utf-8").split()[0]
    _, digest = fb.build("sealed2", files=False)
    assert digest == committed


def test_the_third_sealed_key_matches_the_hash_committed_before_its_fixes() -> None:
    committed = fb.hash_path("sealed3").read_text(encoding="utf-8").split()[0]
    _, digest = fb.build("sealed3", files=False)
    assert digest == committed


@pytest.mark.parametrize("suite", ["sealed", "sealed2", "sealed3"])
def test_a_sealed_answer_key_is_not_in_the_repository(suite: str) -> None:
    for version in ("v2", "v3", "v4"):
        assert not (fb.GOLDEN_DIR / f"citetally_{version}_{suite}.json").exists()
    assert fb.golden_path(suite).is_relative_to(fb.DATA_ROOT)  # data/ is git-ignored


def test_the_second_sealed_set_leans_on_tax_and_instruction_text_and_uses_new_phrasings() -> None:
    from tools.synthetic.injection_sealed2 import INJECTION_TEXT_SEALED2
    from tools.synthetic.planting import _INJECTION_TEXT

    built, _ = fb.build("sealed2", files=False)
    kinds = built.header.counts["by_planted_kind"]
    assert kinds["tax_mismatch"] >= 12 and kinds["injection_text"] >= 12
    assert not set(INJECTION_TEXT_SEALED2) & set(_INJECTION_TEXT)
    assert fb.PREFIX["sealed2"] not in {fb.PREFIX["sealed"], fb.PREFIX["dev2"]}
    assert all(i.id.startswith(fb.PREFIX["sealed2"]) for i in built.items)


def test_the_third_sealed_set_leans_on_tax_and_instruction_text_and_uses_new_phrasings() -> None:
    from tools.synthetic.injection_sealed2 import INJECTION_TEXT_SEALED2
    from tools.synthetic.injection_sealed3 import INJECTION_TEXT_SEALED3
    from tools.synthetic.planting import _INJECTION_TEXT

    built, _ = fb.build("sealed3", files=False)
    kinds = built.header.counts["by_planted_kind"]
    assert kinds["tax_mismatch"] >= 12 and kinds["injection_text"] >= 12
    assert len(set(INJECTION_TEXT_SEALED3)) == len(INJECTION_TEXT_SEALED3) == 14
    assert not set(INJECTION_TEXT_SEALED3) & (set(INJECTION_TEXT_SEALED2) | set(_INJECTION_TEXT))
    assert fb.PREFIX["sealed3"] not in {fb.PREFIX[s] for s in ("dev2", "sealed", "sealed2")}
    assert all(i.id.startswith(fb.PREFIX["sealed3"]) for i in built.items)


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
