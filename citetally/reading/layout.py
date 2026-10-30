"""Layout-preserving reading-order text from words with boxes.

The model sees this text, so columns must stay aligned: words are grouped into lines by vertical
position, ordered left to right, and the gaps between them become spaces in proportion to the
page width, counted from the leftmost word. Nothing is added, dropped or reordered beyond that.
Control, direction and replacement characters are removed from words here, at the one place every
page's text is built.
"""

from __future__ import annotations

import itertools
import statistics
import unicodedata
from collections.abc import Sequence

from citetally.models import Word

MAX_COLUMNS = 160
_SAME_LINE = 0.6  # a word joins a line if its centre is within this many word heights
_BLANK_LINE = 1.8  # a gap this many line pitches tall leaves one blank line
_DROP_CATEGORIES = {"Cc", "Cf", "Cs", "Co", "Cn"}


def clean_token(text: str) -> str:
    """A word's text without control, direction or replacement characters, whitespace collapsed."""
    kept = "".join(
        ch
        for ch in text
        if ch.isspace() or (ch != "\ufffd" and unicodedata.category(ch) not in _DROP_CATEGORIES)
    )
    return " ".join(kept.split())


def _centre(word: Word) -> float:
    return (word.y0 + word.y1) / 2


def build_text(words: Sequence[Word]) -> str:
    tokens = [(clean_token(word.t), word) for word in words]
    tokens = [(text, word) for text, word in tokens if text]
    if not tokens:
        return ""

    heights = [max(word.y1 - word.y0, 1e-6) for _, word in tokens]
    long_enough = [(t, w) for t, w in tokens if len(t) >= 3] or tokens
    char_width = max(
        statistics.median((w.x1 - w.x0) / len(t) for t, w in long_enough), 1 / MAX_COLUMNS
    )
    same_line = _SAME_LINE * statistics.median(heights)

    margin = min(word.x0 for _, word in tokens)  # the page's own left margin is not text

    ordered = sorted(tokens, key=lambda item: (_centre(item[1]), item[1].x0, item[0]))
    lines: list[list[tuple[str, Word]]] = []
    for item in ordered:
        centre = _centre(item[1])
        if lines and abs(centre - statistics.fmean(_centre(w) for _, w in lines[-1])) <= same_line:
            lines[-1].append(item)
        else:
            lines.append([item])
    centres = [statistics.fmean(_centre(w) for _, w in line) for line in lines]

    steps = [b - a for a, b in itertools.pairwise(centres) if b > a]
    pitch = statistics.median(steps) if steps else 0.0

    rendered: list[str] = []
    for index, line in enumerate(lines):
        if index and pitch and centres[index] - centres[index - 1] > _BLANK_LINE * pitch:
            rendered.append("")
        rendered.append(
            _render_line(sorted(line, key=lambda item: (item[1].x0, item[0])), margin, char_width)
        )
    return "\n".join(rendered)


def _render_line(line: list[tuple[str, Word]], margin: float, char_width: float) -> str:
    out = ""
    for text, word in line:
        column = round((word.x0 - margin) / char_width)
        column = min(column, max(MAX_COLUMNS - len(text), 0))
        if out:
            column = max(column, len(out) + 1)
        out += " " * (column - len(out)) + text
    while len(out) > MAX_COLUMNS and "  " in out:
        out = out.replace("  ", " ", 1)
    return out.rstrip()
