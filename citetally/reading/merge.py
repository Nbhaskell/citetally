"""Merge several readings of one page into one list of words.

Tesseract reads a page differently under different settings: one drops a lone digit that another
keeps, one loses a column the other finds. The first reading stays as it is. A word from a later
reading is added only where the words so far have nothing, judged by its centre falling inside no
word already there, so the same word is never in the text twice and a different reading of a word
already present never overrides it. Code only; the words keep their own boxes and confidences.
"""

from __future__ import annotations

from collections.abc import Sequence

from citetally.models import Word

_PAD = 0.004  # a little slack around each box, in fractions of the page


def _covers(word: Word, x: float, y: float) -> bool:
    return word.x0 - _PAD <= x <= word.x1 + _PAD and word.y0 - _PAD <= y <= word.y1 + _PAD


def merge_readings(first: Sequence[Word], others: Sequence[Sequence[Word]]) -> list[Word]:
    merged = list(first)
    for reading in others:
        added: list[Word] = []
        for word in reading:
            x, y = (word.x0 + word.x1) / 2, (word.y0 + word.y1) / 2
            if not any(_covers(have, x, y) for have in merged) and not any(
                _covers(have, x, y) for have in added
            ):
                added.append(word)
        merged.extend(added)
    return merged
