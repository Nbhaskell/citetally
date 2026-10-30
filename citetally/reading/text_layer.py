"""Words and boxes from a PDF's own text layer, when the layer is good enough to trust.

A text layer is exact and fast, so it is used first (docs/TRD.md section 4.2). A page whose layer
is too short or garbled (a broken font map, scanner software that wrote nonsense) is handed to
OCR instead. Boxes are fractions of the page with the origin at the top left, as stored in
`pages.words`. This runs on untrusted files, so callers run it in the isolated worker.
"""

from __future__ import annotations

import statistics
import unicodedata
from collections.abc import Sequence

import pypdfium2 as pdfium

from citetally.models import Word

_MAX_PLAUSIBLE_WORD = 40
_MAX_BAD_SHARE = 0.05
_MAX_GAP_EM = 0.6  # a gap wider than this share of the line height splits a word


class TextLayerError(Exception):
    """The PDF could not be opened or the page does not exist."""


def _open(data: bytes) -> pdfium.PdfDocument:
    try:
        return pdfium.PdfDocument(data)
    except Exception as error:
        raise TextLayerError("The PDF could not be opened.") from error


def page_count(data: bytes) -> int:
    return len(_open(data))


def _clamp(value: float) -> float:
    return min(max(value, 0.0), 1.0)


def extract_words(data: bytes, page_index: int) -> list[Word]:
    """Every word on one page, in the order the file stores them, with normalised boxes."""
    document = _open(data)
    try:
        page = document[page_index]
        textpage = page.get_textpage()
        width, height = page.get_size()
        count = textpage.count_chars()
        text = textpage.get_text_range()
    except Exception as error:
        raise TextLayerError("The page could not be read.") from error
    if not count or width <= 0 or height <= 0:
        return []
    if len(text) != count:  # characters outside the basic plane count twice; read one by one
        text = "".join(textpage.get_text_range(i, 1) or " " for i in range(count))

    words: list[Word] = []
    chars: list[str] = []
    box: list[float] = []  # left, bottom, right, top of the ink, in points
    previous: tuple[float, float, float, float] | None = None  # line box of the last character

    def flush() -> None:
        nonlocal chars, box, previous
        if chars and box and box[2] > box[0] and box[3] > box[1]:
            words.append(
                Word(
                    t="".join(chars),
                    x0=_clamp(box[0] / width),
                    y0=_clamp(1 - box[3] / height),
                    x1=_clamp(box[2] / width),
                    y1=_clamp(1 - box[1] / height),
                    c=None,
                )
            )
        chars, box, previous = [], [], None

    for index in range(min(count, len(text))):
        char = text[index]
        if char.isspace() or char in "\x00\ufffe":
            flush()
            continue
        left, bottom, right, top = textpage.get_charbox(index)
        if right <= left or top <= bottom:
            continue  # a character with no visible box (a generated mark): skip it, keep the word
        # Breaks are judged on the font's line box, which has one height for every glyph, never on
        # the ink box, which is short for "-" or "r" and tall for "M".
        line = textpage.get_charbox(index, loose=True)
        if previous is not None:
            em = max(line[3] - line[1], 1e-6)
            new_line = abs((line[3] + line[1]) / 2 - (previous[3] + previous[1]) / 2) > 0.5 * em
            gap = line[0] - previous[2] > _MAX_GAP_EM * em  # a space the file never wrote
            if new_line or gap:
                flush()
        chars.append(char)
        box = (
            [min(box[0], left), min(box[1], bottom), max(box[2], right), max(box[3], top)]
            if box
            else [left, bottom, right, top]
        )
        previous = (line[0], line[1], line[2], line[3])
    flush()
    return words


def looks_sane(words: Sequence[Word], min_chars: int) -> bool:
    """Enough ordinary text to trust: not too short, not garbled, with plausible word lengths."""
    letters = [ch for word in words for ch in word.t if not ch.isspace()]
    if len(letters) < min_chars or (min_chars and not letters):
        return False
    if not words:
        return True
    bad = sum(
        1
        for ch in letters
        if ch == "\ufffd" or unicodedata.category(ch) in {"Cc", "Cf", "Co", "Cn", "Cs"}
    )
    if bad / len(letters) > _MAX_BAD_SHARE:
        return False
    lengths = [len(word.t) for word in words]
    too_long = sum(1 for n in lengths if n > _MAX_PLAUSIBLE_WORD)
    if too_long / len(lengths) > _MAX_BAD_SHARE:
        return False
    return 1 <= statistics.fmean(lengths) <= 20


def read_pdf(data: bytes, min_chars: int) -> list[list[Word] | None]:
    """For each page: its words if the text layer is good, or None meaning "use OCR"."""
    pages: list[list[Word] | None] = []
    for index in range(page_count(data)):
        words = extract_words(data, index)
        pages.append(words if looks_sane(words, min_chars) else None)
    return pages
