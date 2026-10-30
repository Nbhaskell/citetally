"""The whole set: counts, splits, planted problems, determinism and the sealed held-out split."""

import hashlib
import itertools
import json
from collections import Counter
from pathlib import Path

import pytest

from tools.synthetic.build import (
    BAND,
    Entry,
    build,
    natural_entries,
    plan_planting,
    vendor_medians,
)
from tools.synthetic.docgen import arithmetic_problems
from tools.synthetic.facts import Facts, load_facts
from tools.synthetic.families import FAMILIES
from tools.synthetic.golden import GoldenSet, load_golden, problems, write_golden
from tools.synthetic.planting import EXPECTED_CHECKS, PLANTED_KINDS

SEED = 20261031
ARITHMETIC = {"LINE_MATH", "SUBTOTAL_MATCH", "TAX_MATCH", "TOTAL_MATCH"}


@pytest.fixture(scope="module")
def facts() -> Facts:
    return load_facts()


@pytest.fixture(scope="module")
def entries(facts: Facts) -> list[Entry]:
    found = natural_entries(facts, SEED, 14)
    plan_planting(found, facts, SEED)
    return found


@pytest.fixture(scope="module")
def golden() -> GoldenSet:
    return build(SEED, 14, golden_path=None, files=False)


def test_the_golden_set_is_valid_and_large_enough(golden: GoldenSet, facts: Facts) -> None:
    vendors = {v.id for v in facts.vendors}
    strangers = {v.id for v in facts.unlisted_vendors}
    assert problems(golden, vendors, strangers) == []
    assert len(golden.items) >= 150


def test_a_third_of_the_families_are_held_out_and_never_appear_in_tuned_documents(
    golden: GoldenSet,
) -> None:
    tuned = {i.template_family for i in golden.items if i.split == "tuned"}
    held = {i.template_family for i in golden.items if i.split == "heldout"}
    assert len(tuned) == 10 and len(held) == 5 and not tuned & held
    assert {f.id for f in FAMILIES if f.split == "heldout"} == held


def test_about_a_quarter_of_documents_carry_one_planted_problem_of_each_kind(
    golden: GoldenSet,
) -> None:
    planted = [i for i in golden.items if i.planted]
    assert 0.2 <= len(planted) / len(golden.items) <= 0.3
    kinds = Counter(p.kind for i in planted for p in i.planted)
    assert set(kinds) == set(PLANTED_KINDS)
    assert min(kinds.values()) >= 3
    assert all(len(i.planted) == 1 for i in planted)


def test_conditions_are_balanced_and_present_in_both_splits(golden: GoldenSet) -> None:
    for split in ("tuned", "heldout"):
        counts = Counter(i.condition for i in golden.items if i.split == split)
        assert len(counts) == 4 and min(counts.values()) >= 10, (split, counts)


def test_every_vendor_has_tuned_documents(golden: GoldenSet) -> None:
    tuned = {i.vendor_id for i in golden.items if i.split == "tuned"}
    assert {f"V{n:02d}" for n in range(1, 17)} <= tuned


def test_planted_documents_break_only_what_was_planted(entries: list[Entry]) -> None:
    for e in entries:
        broken = set(arithmetic_problems(e.doc))
        planted = {c for p in e.planted for c in EXPECTED_CHECKS[p["kind"]]}
        assert broken == planted & ARITHMETIC, (e.doc.id, broken, planted)


def test_natural_documents_have_sane_dates_numbers_and_totals(
    entries: list[Entry], facts: Facts
) -> None:
    medians = vendor_medians(entries)
    start, end = facts.date_range
    numbers: set[tuple[str, str]] = set()
    for e in (e for e in entries if not e.planted):
        doc = e.doc
        assert start <= doc.entry_date <= end, doc.id
        assert doc.due_date is None or doc.due_date >= doc.entry_date
        if doc.invoice_number:
            key = (doc.vendor.id, doc.invoice_number)
            assert key not in numbers, key
            numbers.add(key)
    out_of_band = [
        e.doc.id
        for e in entries
        if not e.planted
        and not medians[e.doc.vendor.id] / (BAND * 1.4)
        <= e.doc.total_minor
        <= medians[e.doc.vendor.id] * BAND * 1.4
    ]
    assert len(out_of_band) <= 3, out_of_band  # a few lumpy catalogs may stay near the band


def test_natural_documents_do_not_look_like_duplicates_of_each_other(entries: list[Entry]) -> None:
    groups: dict[tuple[str, str, int], list[Entry]] = {}
    for e in entries:
        groups.setdefault((e.doc.vendor.id, e.doc.currency, e.doc.total_minor), []).append(e)
    for group in groups.values():
        group.sort(key=lambda e: e.doc.entry_date)
        for a, b in itertools.pairwise(group):
            if (b.doc.entry_date - a.doc.entry_date).days <= 7:
                assert a.planted or b.planted, (a.doc.id, b.doc.id)


def test_duplicates_point_at_a_clean_original_in_the_same_family(entries: list[Entry]) -> None:
    by_id = {e.doc.id: e for e in entries}
    pairs = 0
    for e in entries:
        for p in e.planted:
            if "duplicate_of" in p:
                original = by_id[p["duplicate_of"]]
                assert original.family.id == e.family.id and not original.planted
                assert original.doc.vendor.id == e.doc.vendor.id
                pairs += 1
    assert pairs >= 6


def test_unknown_vendor_documents_come_from_vendors_outside_the_list(
    entries: list[Entry],
) -> None:
    strangers = [e for e in entries if any(p["kind"] == "unknown_vendor" for p in e.planted)]
    assert strangers and all(e.doc.vendor.id.startswith("X") for e in strangers)
    assert not [e for e in entries if e.doc.vendor.id.startswith("X") and not e.planted]


def test_generation_is_deterministic_from_the_seed(golden: GoldenSet) -> None:
    again = build(SEED, 14, golden_path=None, files=False)
    assert again.model_dump() == golden.model_dump()
    other = build(SEED + 1, 14, golden_path=None, files=False)
    assert other.model_dump() != golden.model_dump()


def test_the_heldout_split_is_sealed_until_it_is_deliberately_opened(
    golden: GoldenSet, tmp_path: Path
) -> None:
    path = tmp_path / "golden.json"
    write_golden(golden, path)
    assert all(i.split == "tuned" for i in load_golden(path))
    with pytest.raises(PermissionError, match="sealed"):
        load_golden(path, split="heldout")
    assert load_golden(path, split="heldout", unseal_heldout=True)
    with pytest.raises(ValueError, match="split"):
        load_golden(path, split="everything")


def test_files_are_written_to_the_right_folders_and_match_the_digest(tmp_path: Path) -> None:
    golden = build(SEED, 1, root=tmp_path, golden_path=None, files=True)
    items = golden.items
    assert len(items) == 15
    digest = hashlib.sha256()
    for item in sorted(items, key=lambda i: i.id):
        relative = Path(item.file).relative_to("data/synthetic")
        path = tmp_path / relative
        assert path.is_file(), item.file
        assert path.suffix == (".jpg" if item.condition == "phone_photo" else ".pdf")
        assert (path.parent.name == "heldout") == (item.split == "heldout")
        digest.update(f"{item.id}:{hashlib.sha256(path.read_bytes()).hexdigest()}\n".encode())
    assert golden.header.files_digest == digest.hexdigest()


def test_golden_json_round_trips(golden: GoldenSet) -> None:
    text = json.dumps(golden.model_dump(mode="json"))
    assert GoldenSet.model_validate_json(text) == golden
