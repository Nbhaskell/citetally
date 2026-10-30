"""Layout-preserving text: words in, aligned reading-order text out. The model sees this text."""

import re

import pytest

from citetally.models import Word
from citetally.reading import layout


def w(text: str, x0: float, y0: float, x1: float | None = None, h: float = 0.012) -> Word:
    """A word at (x0, y0). Width defaults to 0.007 per character, like 10-point text."""
    right = x1 if x1 is not None else x0 + 0.007 * len(text)
    return Word(t=text, x0=x0, y0=y0, x1=min(right, 1.0), y1=y0 + h, c=None)


def test_no_words_give_no_text() -> None:
    assert layout.build_text([]) == ""


def test_one_word_is_just_that_word() -> None:
    assert layout.build_text([w("Total", 0.5, 0.5)]) == "Total"


def test_words_on_one_line_keep_their_horizontal_order() -> None:
    words = [w("two", 0.30, 0.2), w("one", 0.10, 0.2), w("three", 0.50, 0.2)]
    text = layout.build_text(words)
    assert text.split() == ["one", "two", "three"]
    assert "\n" not in text


def test_lines_are_read_top_to_bottom() -> None:
    words = [w("bottom", 0.1, 0.8), w("top", 0.1, 0.1), w("middle", 0.1, 0.4)]
    assert layout.build_text(words).split() == ["top", "middle", "bottom"]


def test_words_with_slightly_different_baselines_share_a_line() -> None:
    words = [w("Total", 0.1, 0.500), w("$5.00", 0.5, 0.503), w("Next", 0.1, 0.55)]
    lines = layout.build_text(words).splitlines()
    assert lines[0].split() == ["Total", "$5.00"]
    assert lines[1].split() == ["Next"]


def test_gaps_become_spaces_so_table_columns_line_up() -> None:
    rows = [
        [("Description", 0.05), ("Qty", 0.60), ("Amount", 0.80)],
        [("Wax ring", 0.05), ("2", 0.62), ("$10.80", 0.80)],
        [("Copper pipe", 0.05), ("14", 0.61), ("$437.50", 0.80)],
    ]
    words = [w(t, x, 0.2 + 0.03 * i) for i, row in enumerate(rows) for t, x in row]
    lines = layout.build_text(words).splitlines()
    assert len(lines) == 3
    starts = [line.index("$") if "$" in line else line.index("Amount") for line in lines]
    assert len(set(starts)) == 1, lines  # the right-hand column starts in the same place
    assert abs(lines[0].index("Qty") - lines[1].index("2")) <= 3  # they differ by a few columns


def test_words_closer_than_a_space_are_still_separated() -> None:
    words = [w("a", 0.100, 0.2, x1=0.107), w("b", 0.107, 0.2, x1=0.114)]
    assert layout.build_text(words) == "a b"


def test_a_tall_gap_between_lines_leaves_a_blank_line() -> None:
    words = [
        w("header", 0.1, 0.1),
        w("row1", 0.1, 0.14),
        w("row2", 0.1, 0.18),
        w("footer", 0.1, 0.60),
    ]
    lines = layout.build_text(words).split("\n")
    assert lines == ["header", "row1", "row2", "", "footer"]


def test_lines_are_never_longer_than_the_cap() -> None:
    words = [w("left", 0.0, 0.2), w("right", 0.97, 0.2, x1=1.0)]
    for line in layout.build_text(words).splitlines():
        assert len(line) <= layout.MAX_COLUMNS


def test_the_same_words_in_any_order_give_the_same_text() -> None:
    words = [w(f"w{i}", 0.05 + 0.09 * (i % 9), 0.1 + 0.05 * (i // 9)) for i in range(45)]
    forward = layout.build_text(words)
    assert layout.build_text(list(reversed(words))) == forward


def test_nothing_is_added_or_dropped() -> None:
    words = [
        w("INV-20112", 0.7, 0.1),
        w("Date:", 0.1, 0.1),
        w("2026-05-20", 0.2, 0.1),
        w("$649.92", 0.7, 0.5),
    ]
    assert sorted(layout.build_text(words).split()) == sorted(x.t for x in words)


def test_lines_have_no_trailing_spaces_and_no_tabs() -> None:
    words = [w("a", 0.1, 0.1), w("b", 0.9, 0.1), w("c", 0.1, 0.3)]
    for line in layout.build_text(words).splitlines():
        assert line == line.rstrip() and "\t" not in line


@pytest.mark.parametrize("junk", ["\x00", "\x07", "�", "‮"])
def test_control_and_direction_characters_never_reach_the_text(junk: str) -> None:
    text = layout.build_text([w(f"a{junk}b", 0.1, 0.1)])
    assert text == "ab"


def test_text_with_only_junk_words_is_empty() -> None:
    assert layout.build_text([w("\x00\x01", 0.1, 0.1)]) == ""


def test_whitespace_inside_a_word_is_collapsed() -> None:
    assert re.fullmatch(r"a b", layout.build_text([w("a \t b", 0.1, 0.1)])) is not None
