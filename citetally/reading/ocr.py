"""OCR behind one small interface: a page image in, words with boxes and confidences out.

`TesseractOcr` runs the Tesseract program in a separate process with a timeout and reads its
tab-separated output. `FakeOcr` returns prepared pages so tests need no OCR program. Nothing here
logs or raises with page text: errors name the kind of failure and nothing from the page.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PIL import Image

from citetally.models import Word

_WINDOWS_DEFAULTS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)
_TSV_COLUMNS = 12
_WORD_LEVEL = "5"

Runner = Callable[[Sequence[str], float], str]


class OcrError(Exception):
    """The page could not be read. The message never holds page content."""


class OcrUnavailable(OcrError):
    """The OCR program is not installed or would not start."""


@dataclass(frozen=True)
class OcrPage:
    words: list[Word]
    mean_confidence: float | None  # 0 to 100; None when no words were found


class OcrEngine(Protocol):
    name: str

    def read_page(self, image: Image.Image) -> OcrPage: ...


def find_tesseract(configured: str = "") -> str | None:
    """The path of the Tesseract program: the configured one, then PATH, then default folders."""
    if configured:
        return configured if Path(configured).is_file() else shutil.which(configured)
    on_path = shutil.which("tesseract")
    if on_path:
        return on_path
    defaults = list(_WINDOWS_DEFAULTS)
    if os.environ.get("LOCALAPPDATA"):
        defaults.append(rf"{os.environ['LOCALAPPDATA']}\Programs\Tesseract-OCR\tesseract.exe")
    return next((path for path in defaults if Path(path).is_file()), None)


def _clamp(value: float) -> float:
    return min(max(value, 0.0), 1.0)


def parse_tsv(tsv: str, width: int, height: int) -> OcrPage:
    """Words from Tesseract's `tsv` output, with boxes as fractions of the image.

    Only word rows with printable text and a confidence are kept; Tesseract reports page, block,
    paragraph and line rows, and a confidence of -1 for anything that is not a recognised word.
    """
    words: list[Word] = []
    for row in tsv.splitlines()[1:]:
        cells = row.split("\t", _TSV_COLUMNS - 1)
        if len(cells) < _TSV_COLUMNS or cells[0] != _WORD_LEVEL:
            continue
        text = cells[11].strip()
        try:
            left, top, box_w, box_h = (int(cells[i]) for i in (6, 7, 8, 9))
            confidence = float(cells[10])
        except ValueError:
            continue
        if not text or math.isnan(confidence) or confidence < 0 or box_w <= 0 or box_h <= 0:
            continue
        words.append(
            Word(
                t=text,
                x0=_clamp(left / width),
                y0=_clamp(top / height),
                x1=_clamp((left + box_w) / width),
                y1=_clamp((top + box_h) / height),
                c=min(confidence, 100.0),
            )
        )
    mean = sum(word.c or 0.0 for word in words) / len(words) if words else None
    return OcrPage(words=words, mean_confidence=mean)


def _run(args: Sequence[str], timeout_s: float) -> str:
    try:
        done = subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError as error:
        raise OcrUnavailable("Tesseract was not found.") from error
    except PermissionError as error:
        raise OcrUnavailable("Tesseract would not start.") from error
    except subprocess.TimeoutExpired as error:
        raise OcrError("Tesseract took too long to read the page.") from error
    if done.returncode != 0:
        raise OcrError(f"Tesseract failed (exit code {done.returncode}).")
    return done.stdout


class TesseractOcr:
    name = "tesseract"

    def __init__(
        self,
        command: str = "",
        *,
        language: str = "eng",
        psm: int = 4,
        dpi: int = 200,
        timeout_s: float = 120.0,
        runner: Runner | None = None,
    ) -> None:
        self._command = command
        self._language = language
        self._psm = psm
        self._dpi = dpi
        self._timeout_s = timeout_s
        self._runner = runner or _run

    def read_page(self, image: Image.Image) -> OcrPage:
        exe = find_tesseract(self._command)
        if exe is None:
            raise OcrUnavailable("Tesseract was not found.")
        with tempfile.TemporaryDirectory(prefix="citetally-ocr-") as folder:
            path = Path(folder) / "page.png"
            image.convert("L").save(path, "PNG")
            args = [
                exe, str(path), "stdout", "-l", self._language,
                "--psm", str(self._psm), "--dpi", str(self._dpi), "tsv",
            ]  # fmt: skip
            output = self._runner(args, self._timeout_s)
        return parse_tsv(output, image.width, image.height)


class FakeOcr:
    """Returns prepared pages, one per call and then the last again, and records image sizes."""

    name = "fake"

    def __init__(self, pages: Sequence[OcrPage] = (), *, error: OcrError | None = None) -> None:
        self._pages = list(pages)
        self._error = error
        self.calls: list[tuple[int, int]] = []

    def read_page(self, image: Image.Image) -> OcrPage:
        self.calls.append(image.size)
        if self._error is not None:
            raise self._error
        if not self._pages:
            return OcrPage(words=[], mean_confidence=None)
        return self._pages[min(len(self.calls) - 1, len(self._pages) - 1)]


def fake_page(lines: Sequence[str], confidence: float = 95.0) -> OcrPage:
    """A page of words laid out in rows, as if read from a clean page. For tests."""
    words: list[Word] = []
    for row, line in enumerate(lines):
        x = 0.08
        y = 0.05 + 0.03 * row
        for text in line.split():
            right = x + 0.007 * len(text)
            words.append(Word(t=text, x0=x, y0=y, x1=min(right, 1.0), y1=y + 0.015, c=confidence))
            x = right + 0.014
    return OcrPage(words=words, mean_confidence=confidence if words else None)
