"""Make a page image easier for OCR to read: grey, evened out, denoised, upright and straight.

Steps, in order: scale to a working size, flatten uneven light, remove speckle, turn a sideways
page upright, remove tilt, turn an upside-down page, stretch contrast. Only the image changes.
Every rotation is recorded, so word boxes found on the cleaned image can be mapped back onto the
page image the person sees (`Preprocessed.word_on_original`). Pillow and NumPy only; the values
here are starting points, to be judged by the OCR bake-off (docs/IMPLEMENTATION_PLAN.md Phase 3).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageFilter

from citetally.models import Word

WORKING_MIN_LONG_SIDE = 1800  # smaller pages are enlarged to this, larger ones reduced to MAX
WORKING_MAX_LONG_SIDE = 2400
MAX_TILT_DEGREES = 12.0  # more than this is not straightened (it is more likely not a page)
_SEARCH_WIDTH = 700  # tilt is searched for on a copy this wide
_SIDEWAYS_RATIO = 1.3  # columns must be this much "stripier" than rows to turn the page
_UPSIDE_DOWN_MARGIN = 0.02  # the ascender-versus-descender evidence needed to turn it over
_BACKGROUND_SCALE = 4  # the lighting is estimated on a copy this many times smaller
_PAPER_LEVEL = 190.0  # on a flattened page, anything lighter than this is paper, not ink
_PAPER_SHARE = 0.5  # below this share of the brightest tenth's brightness is not paper

Gray = NDArray[np.float64]


@dataclass(frozen=True)
class Turn:
    """One rotation about the centre, counter-clockwise, with the canvas grown to fit it."""

    degrees: float
    before: tuple[int, int]
    after: tuple[int, int]


@dataclass(frozen=True)
class Preprocessed:
    """The cleaned page and what was done to it."""

    image: Image.Image  # mode "L"
    skew_degrees: float  # tilt found: positive when text lines rose to the right
    turns: tuple[Turn, ...]  # in the order they were applied

    @property
    def quarter_turns(self) -> int:
        """Whole quarter turns counter-clockwise applied to make the page upright, 0 to 3."""
        sideways = sum(t.degrees for t in self.turns if t.degrees % 90 == 0)
        return round(sideways / 90) % 4

    def point_on_original(self, x: float, y: float) -> tuple[float, float]:
        """A point as fractions of the cleaned image, mapped to fractions of the page image."""
        for turn in reversed(self.turns):
            x, y = _unrotate(x, y, turn)
        return x, y

    def word_on_original(self, word: Word) -> Word:
        """A word found on the cleaned image, with its box moved onto the original page image."""
        corners = [
            self.point_on_original(x, y) for x in (word.x0, word.x1) for y in (word.y0, word.y1)
        ]
        xs = [min(max(x, 0.0), 1.0) for x, _ in corners]
        ys = [min(max(y, 0.0), 1.0) for _, y in corners]
        return word.model_copy(update={"x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys)})


def _unrotate(x: float, y: float, turn: Turn) -> tuple[float, float]:
    """Undo one rotation for a point given as fractions of the rotated canvas."""
    (w0, h0), (w1, h1) = turn.before, turn.after
    angle = math.radians(turn.degrees)
    cos, sin = math.cos(angle), math.sin(angle)
    if turn.degrees % 90 == 0:  # exact, with no rounding noise
        cos, sin = round(cos), round(sin)
    dx, dy = x * w1 - w1 / 2, y * h1 - h1 / 2
    return (dx * cos - dy * sin + w0 / 2) / w0, (dx * sin + dy * cos + h0 / 2) / h0


def _rotate(image: Image.Image, degrees: float, fill: int) -> tuple[Image.Image, Turn]:
    rotated = image.rotate(degrees, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=fill)
    return rotated, Turn(degrees=degrees, before=image.size, after=rotated.size)


def _arr(image: Image.Image) -> Gray:
    return np.asarray(image, dtype=np.float64)


def _img(array: Gray) -> Image.Image:
    return Image.fromarray(np.clip(array, 0, 255).astype(np.uint8), "L")


def to_working_size(image: Image.Image) -> Image.Image:
    """Grey, and enlarged or reduced so the long side is 1800 to 2400 pixels."""
    gray = image.convert("L")
    long_side = max(gray.size)
    target = min(max(long_side, WORKING_MIN_LONG_SIDE), WORKING_MAX_LONG_SIDE)
    if target == long_side:
        return gray
    scale = target / long_side
    size = (max(round(gray.width * scale), 1), max(round(gray.height * scale), 1))
    return gray.resize(size, Image.Resampling.LANCZOS)


def flatten_light(gray: Image.Image) -> Image.Image:
    """Divide out slow changes in brightness (shadows, vignetting) so paper is even and white."""
    small = gray.resize(
        (max(gray.width // _BACKGROUND_SCALE, 1), max(gray.height // _BACKGROUND_SCALE, 1)),
        Image.Resampling.BOX,
    )
    paper = small.filter(ImageFilter.MaxFilter(9))  # skips over the dark ink
    paper = paper.filter(ImageFilter.GaussianBlur(max(small.width // 40, 4)))
    background = np.maximum(_arr(paper.resize(gray.size, Image.Resampling.BILINEAR)), 1.0)
    return _img(np.minimum(_arr(gray) / background, 1.0) * 255.0)


def remove_speckle(gray: Image.Image) -> Image.Image:
    return gray.filter(ImageFilter.MedianFilter(3))


def stretch_contrast(gray: Image.Image) -> Image.Image:
    """Map the darkest 1% of pixels to black and the paper (the median) to white."""
    data = _arr(gray)
    low, high = np.percentile(data, [1, 50])
    if high - low < 8:  # a blank page, or one with no ink to measure
        return gray
    return _img((data - low) / (high - low) * 255.0)


def page_mask(gray: Image.Image) -> Image.Image:
    """255 where there is paper, 0 on a desk or other dark surround, from the unflattened image.

    Paper is much brighter than what it lies on, so a pixel (judged on a small blurred copy)
    below about half the brightness of the brightest tenth is not paper. The edge is pulled in
    by a few pixels so the dark rim of a photographed page is never taken for ink. A scan that
    is paper all over keeps a full mask.
    """
    small = gray.resize(
        (max(gray.width // _BACKGROUND_SCALE, 1), max(gray.height // _BACKGROUND_SCALE, 1)),
        Image.Resampling.BOX,
    ).filter(ImageFilter.GaussianBlur(2))
    data = _arr(small)
    bright = float(np.percentile(data, 90))
    mask = _img(np.where(data > _PAPER_SHARE * bright, 255.0, 0.0)).filter(ImageFilter.MinFilter(7))
    return mask.resize(gray.size, Image.Resampling.NEAREST)


def _ink_image(gray: Image.Image, mask: Image.Image) -> Image.Image:
    """How dark each pixel is on paper, 0 for paper and anything off the page, 255 for black."""
    ink = np.clip((_PAPER_LEVEL - _arr(gray)) / _PAPER_LEVEL, 0.0, 1.0) * (_arr(mask) / 255.0)
    return _img(ink * 255.0)


def _stripes(ink: Gray, axis: int) -> float:
    """How strongly ink gathers into rows (axis 1) or columns (axis 0): sum of squared profile."""
    profile = ink.sum(axis=axis)
    return float(np.sum(profile**2))


def _best_stripes(
    small: Image.Image, axis: int, around: float, span: float, step: float
) -> tuple[float, float]:
    """The best stripe score for rows (axis 1) or columns (axis 0), and the tilt that gave it."""
    count = round(span / step)
    best = (-1.0, around)
    for i in range(-count, count + 1):
        degrees = around + step * i
        turned = small.rotate(degrees, resample=Image.Resampling.BILINEAR, fillcolor=0)
        best = max(best, (_stripes(_arr(turned) / 255.0, axis), degrees))
    return best


def is_sideways(ink: Image.Image) -> bool:
    """True when the text runs in columns rather than rows (a page turned a quarter turn).

    A tilt blurs both profiles, so each axis is scored at its own best tilt.
    """
    scale = _SEARCH_WIDTH / max(ink.width, 1)
    small = ink.resize((_SEARCH_WIDTH, max(round(ink.height * scale), 1)), Image.Resampling.BOX)
    scores = []
    for axis in (1, 0):
        _, coarse = _best_stripes(small, axis, 0.0, MAX_TILT_DEGREES, 2.0)
        scores.append(_best_stripes(small, axis, coarse, 1.0, 0.5)[0])
    rows, columns = scores
    return rows > 0 and columns > _SIDEWAYS_RATIO * rows


def _tilt_score(small: Image.Image, degrees: float) -> float:
    turned = small.rotate(degrees, resample=Image.Resampling.BILINEAR, fillcolor=0)
    return _stripes(_arr(turned) / 255.0, 1)


def measure_tilt(ink: Image.Image) -> float:
    """The tilt in degrees, positive when lines of text rise to the right; 0 when it is unclear."""
    scale = _SEARCH_WIDTH / max(ink.width, 1)
    small = ink.resize((_SEARCH_WIDTH, max(round(ink.height * scale), 1)), Image.Resampling.BOX)
    if _stripes(_arr(small) / 255.0, 1) <= 0:
        return 0.0
    best = 0.0
    for step, span in ((1.0, MAX_TILT_DEGREES), (0.25, 1.0), (0.05, 0.25)):
        count = round(span / step)
        candidates = [best + step * i for i in range(-count, count + 1)]
        candidates = [c for c in candidates if abs(c) <= MAX_TILT_DEGREES]
        best = max(candidates, key=lambda degrees: _tilt_score(small, degrees))
    # Turning the page counter-clockwise by `best` levelled the lines, so they had been rising by
    # the opposite amount.
    return -best


def upside_down_evidence(ink: Image.Image) -> float:
    """Above 0 when the page reads upright, below 0 when upside down, near 0 when unclear.

    In Latin text the baseline is a sharp lower edge (few letters have descenders), while the
    top of a line is blurred by capitals and ascenders. So inside each line of text the ink falls
    away faster at the bottom than it rises at the top.
    """
    profile = np.convolve((_arr(ink) / 255.0).sum(axis=1), np.ones(3) / 3, mode="same")
    strong = np.percentile(profile, 90)
    if strong <= 0:
        return 0.0
    inside = profile > 0.25 * strong
    steps = np.diff(profile)
    total = 0.0
    weight = 0.0
    start = None
    for row in range(len(inside) + 1):
        on = row < len(inside) and bool(inside[row])
        if on and start is None:
            start = row
        elif not on and start is not None:
            if 6 <= row - start <= 90:  # a line of text, not a rule or a logo
                band = steps[max(start - 2, 0) : row + 1]
                rise, drop = float(band.max()), float(-band.min())
                total += drop - rise
                weight += drop + rise
            start = None
    return total / weight if weight else 0.0


def preprocess(image: Image.Image) -> Preprocessed:
    """Clean one page image for OCR and record how it was turned."""
    working = to_working_size(image)
    mask = page_mask(working)
    gray = remove_speckle(flatten_light(working))
    turns: list[Turn] = []

    def turn_by(degrees: float) -> None:
        nonlocal gray, mask
        gray, turn = _rotate(gray, degrees, 255)
        mask, _ = _rotate(mask, degrees, 255)
        turns.append(turn)

    if is_sideways(_ink_image(gray, mask)):
        turn_by(90)
    tilt = measure_tilt(_ink_image(gray, mask))
    if tilt:
        turn_by(-tilt)
    if upside_down_evidence(_ink_image(gray, mask)) < -_UPSIDE_DOWN_MARGIN:
        turn_by(180)
    return Preprocessed(image=stretch_contrast(gray), skew_degrees=tilt, turns=tuple(turns))


def preprocess_words(pre: Preprocessed, words: Sequence[Word]) -> list[Word]:
    """Words read from the cleaned image, with boxes on the original page image."""
    return [pre.word_on_original(word) for word in words]
