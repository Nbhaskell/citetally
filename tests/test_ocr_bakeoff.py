"""The OCR bake-off's scoring and summary, on invented words. No OCR program is needed."""

import pytest

from citetally.models import Word
from citetally.reading import layout
from tools import ocr_bakeoff as bake
from tools.synthetic.golden import load_golden


def word(text: str, x0: float = 0.1, y0: float = 0.1) -> Word:
    return Word(t=text, x0=x0, y0=y0, x1=min(x0 + 0.007 * len(text), 1.0), y1=y0 + 0.012, c=90.0)


def page(*texts: str) -> tuple[list[Word], str]:
    words = [word(t, 0.05 + 0.1 * i) for i, t in enumerate(texts)]
    return words, layout.build_text(words)


def test_a_value_present_in_the_text_is_found_and_every_token_matches() -> None:
    words, text = page("Total", "due", "$1,208.30")
    scored = bake.score_value(bake.Ref("money", "$1,208.30"), words, text)
    assert (scored.found, scored.tokens, scored.tokens_exact, scored.tokens_near) == (True, 1, 1, 1)


def test_a_multi_word_value_must_be_contiguous_to_be_found_but_tokens_count_separately() -> None:
    words, text = page("Copper", "Ball", "pipe,")
    scored = bake.score_value(bake.Ref("text", "Copper pipe,"), words, text)
    assert not scored.found  # the words are all there, but not next to each other
    assert (scored.tokens, scored.tokens_exact) == (2, 2)


def test_an_amount_with_the_same_digits_is_found_even_if_the_punctuation_differs() -> None:
    words, text = page("Total", "($1,208.30)")
    assert bake.score_value(bake.Ref("money", "$1,208.30"), words, text).found
    assert bake.score_value(bake.Ref("date", "2026-07-20"), *page("2026.07.20")).found
    # the same leniency is not given to text or identifiers
    assert not bake.score_value(bake.Ref("id", "INV-20112"), *page("INV20112")).found


def test_a_different_number_is_not_found() -> None:
    words, text = page("$1,208.31")
    scored = bake.score_value(bake.Ref("money", "$1,208.30"), words, text)
    assert not scored.found and scored.tokens_exact == 0
    assert scored.tokens_near == 1  # one slipped digit is close enough for the tolerant score


def test_a_word_that_is_far_off_or_much_shorter_is_not_near() -> None:
    scored = bake.score_value(bake.Ref("text", "Plumbing"), *page("Pl", "Plumbxxx"))
    assert scored.tokens_exact == 0 and scored.tokens_near == 0


def test_a_repeated_token_is_matched_once_per_occurrence_read() -> None:
    scored = bake.score_value(bake.Ref("text", "ball ball"), *page("ball"))
    assert (scored.tokens, scored.tokens_exact) == (2, 1)


def test_an_empty_page_finds_nothing() -> None:
    scored = bake.score_value(bake.Ref("money", "$5.00"), [], "")
    assert not scored.found and scored.tokens_exact == 0 and scored.tokens_near == 0


def test_reference_values_are_the_printed_strings_and_nothing_else() -> None:
    item = load_golden(split="tuned")[0]
    refs = bake.reference_values(item)
    printed = set(item.truth.printed.values()) | {
        v for line in item.truth.lines for v in line.printed.values()
    }
    assert refs and all(ref.text in printed for ref in refs)
    assert all(ref.kind in bake.KINDS for ref in refs)
    assert "USD" not in [r.text for r in refs] and item.truth.printed["currency"] not in [
        r.text for r in refs if r.kind != "money"
    ]
    assert len([r for r in refs if r.kind == "quantity"]) == len(item.truth.lines)


def test_only_the_development_split_can_be_loaded_by_default() -> None:
    assert {item.split for item in load_golden(split="tuned")} == {"tuned"}
    with pytest.raises(PermissionError):
        load_golden(split="heldout")


def test_specs_name_a_preprocessing_variant_and_a_page_mode() -> None:
    (config,) = bake.configs_from(["clean/11"])
    assert (config.name, config.prep, config.psm) == ("tesseract-clean-psm11", "clean", 11)
    with pytest.raises(SystemExit):
        bake.configs_from(["nonsense/4"])


def record(condition: str, found: int, values: int, seconds: float) -> dict[str, object]:
    by_kind = {kind: [0, 0, 0, 0, 0] for kind in bake.KINDS}
    by_kind["money"] = [values, found, values, found, found]
    return {
        "condition": condition,
        "configs": {
            "x": {"seconds": seconds, "words": 100, "mean_confidence": 80.0, "by_kind": by_kind}
        },
    }


def test_the_summary_pools_values_by_condition_and_reports_speed() -> None:
    summary = bake.summarise(
        [
            record("clean_pdf", 10, 10, 1.0),
            record("clean_pdf", 5, 10, 3.0),
            record("scan_heavy", 0, 10, 2.0),
        ]
    )["x"]
    assert summary["documents"] == 3
    assert summary["clean_pdf"]["all_values"]["found"] == 0.75
    assert summary["scan_heavy"]["all_values"]["found"] == 0
    assert summary["all"]["all_values"]["found"] == pytest.approx(0.5)
    assert summary["all"]["seconds_per_page_median"] == 2.0
    assert summary["all"]["numbers"]["values"] == 30
    assert "clean_pdf" in bake.render({"x": summary})


def test_a_failed_page_is_counted_as_an_error_not_averaged_in() -> None:
    bad = {"condition": "clean_pdf", "configs": {"x": {"error": True}}}
    summary = bake.summarise([record("clean_pdf", 10, 10, 1.0), bad])["x"]
    assert (summary["documents"], summary["errors"]) == (1, 1)
