"""RapidOCR as an `OcrEngine`: an optional engine, installed separately (D-073).

RapidOCR runs the PP-OCR models through ONNX Runtime. The models ship inside the package, so a
page is read with no network access. It needs no program on the path, only the optional packages;
without them every read raises `OcrUnavailable`, as a missing Tesseract does. The packages are
listed in `requirements-rapidocr.txt`.

The engine is built once per process, on the first page, and not stored on the object: the pipeline
sends an `OcrEngine` to a separate process, so the object has to stay small and picklable. Errors
name the kind of failure and nothing from the page.
"""

from __future__ import annotations

import importlib
import importlib.util
import threading
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
from PIL import Image

from citetally.models import Word
from citetally.reading.ocr import OcrError, OcrPage, OcrUnavailable

_lock = threading.Lock()
_engine: Callable[..., Any] | None = None


def rapidocr_installed() -> bool:
    """True when the optional packages can be imported. Nothing is loaded or run."""
    try:
        return importlib.util.find_spec("rapidocr") is not None
    except (ImportError, ValueError):
        return False


def _shared_engine() -> Callable[..., Any]:
    global _engine
    with _lock:
        if _engine is None:
            try:
                module = importlib.import_module("rapidocr")
            except ImportError as error:
                raise OcrUnavailable("RapidOCR is not installed.") from error
            try:
                _engine = module.RapidOCR()
            except Exception as error:  # the package raises its own types
                raise OcrUnavailable("RapidOCR would not start.") from error
        return _engine


def _clamp(value: float) -> float:
    return min(max(value, 0.0), 1.0)


def words_from_result(lines: Sequence[Any], width: int, height: int) -> list[Word]:
    """Words with boxes as fractions of the image, from RapidOCR's per-word results.

    `lines` holds one tuple per text line; each item is (text, score 0 to 1, four corner points).
    """
    words: list[Word] = []
    for line in lines:
        for text, score, box in line:
            text = str(text).strip()
            xs = [point[0] for point in box]
            ys = [point[1] for point in box]
            if not text or max(xs) <= min(xs) or max(ys) <= min(ys):
                continue
            words.append(
                Word(
                    t=text,
                    x0=_clamp(min(xs) / width),
                    y0=_clamp(min(ys) / height),
                    x1=_clamp(max(xs) / width),
                    y1=_clamp(max(ys) / height),
                    c=min(max(float(score) * 100.0, 0.0), 100.0),
                )
            )
    return words


class RapidOcr:
    """RapidOCR with the engine's own page layout analysis; `psm` (a Tesseract idea) is ignored."""

    name = "rapidocr"

    def read_page(self, image: Image.Image, *, psm: int | None = None) -> OcrPage:
        engine = _shared_engine()
        try:
            result = engine(np.array(image.convert("RGB")), return_word_box=True)
        except OcrError:
            raise
        except Exception as error:  # the package raises its own types
            raise OcrError("RapidOCR failed to read the page.") from error
        words = words_from_result(result.word_results or (), image.width, image.height)
        mean = sum(word.c or 0.0 for word in words) / len(words) if words else None
        return OcrPage(words=words, mean_confidence=mean)
