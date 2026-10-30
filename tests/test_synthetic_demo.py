"""The demo set (about a dozen labelled documents) and the counts report."""

import json
from pathlib import Path

import pytest

from tools.synthetic.build import build
from tools.synthetic.demo import export_demo, select_demo
from tools.synthetic.golden import GoldenSet, Item, summary_path, write_golden
from tools.synthetic.report import render

SEED = 20261031


@pytest.fixture(scope="module")
def golden() -> GoldenSet:
    return build(SEED, 14, golden_path=None, files=False)


@pytest.fixture(scope="module")
def tuned(golden: GoldenSet) -> list[Item]:
    return [i for i in golden.items if i.split == "tuned"]


def test_demo_has_about_a_dozen_tuned_documents(tuned: list[Item]) -> None:
    demo = select_demo(tuned)
    assert len(demo) == 12
    assert all(i.split == "tuned" for i in demo)
    assert len({i.id for i in demo}) == 12


def test_demo_shows_clean_documents_and_the_main_problems(tuned: list[Item]) -> None:
    demo = select_demo(tuned)
    kinds = {p.kind for i in demo for p in i.planted}
    assert {
        "total_mismatch",
        "line_math",
        "tax_mismatch",
        "duplicate_content",
        "unknown_vendor",
        "injection_text",
    } <= kinds
    clean = [i for i in demo if not i.planted]
    assert len(clean) >= 4
    assert len({i.condition for i in demo}) >= 3
    assert {"invoice", "receipt", "credit_note"} <= {i.truth.entry_type for i in demo}


def test_demo_includes_both_halves_of_a_duplicate_pair(tuned: list[Item]) -> None:
    demo = select_demo(tuned)
    ids = {i.id for i in demo}
    duplicates = [i for i in demo if i.expected_duplicate_of]
    assert duplicates and all(i.expected_duplicate_of in ids for i in duplicates)


def test_demo_selection_is_deterministic_and_refuses_held_out_items(
    golden: GoldenSet, tuned: list[Item]
) -> None:
    assert [i.id for i in select_demo(tuned)] == [i.id for i in select_demo(tuned)]
    with pytest.raises(ValueError, match="tuned"):
        select_demo(golden.items)


def test_export_copies_files_and_writes_a_manifest(tuned: list[Item], tmp_path: Path) -> None:
    source = tmp_path / "src"
    for item in tuned:
        path = source / Path(item.file).relative_to("data/synthetic")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    target = tmp_path / "demo"
    selected = export_demo(tuned, source, target)
    manifest = json.loads((target / "demo_manifest.json").read_text(encoding="utf-8"))
    assert [d["id"] for d in manifest["documents"]] == [i.id for i in selected]
    assert "Demo data" in manifest["note"]
    for entry in manifest["documents"]:
        assert (target / entry["file"]).read_bytes() == b"x"
        assert entry["what_to_look_for"]


def test_report_prints_counts_and_no_document_ids(golden: GoldenSet, tmp_path: Path) -> None:
    path = tmp_path / "golden.json"
    write_golden(golden, path)
    header = json.loads(summary_path(path).read_text(encoding="utf-8"))
    text = render(header)
    for heading in ("By split", "By condition", "By planted kind", "By template family"):
        assert heading in text
    assert "heldout" in text and "sealed" in text
    assert "inv-0" not in text and "rcp-0" not in text and "crn-0" not in text
    assert "T11" in text  # families are named; their documents are not
