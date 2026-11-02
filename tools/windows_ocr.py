"""The OCR that ships with Windows 10 and 11, as an `OcrEngine`, for the bake-off only.

It needs the MIT-licensed `winrt-*` packages and an OCR language installed for the user's
profile. It reports word boxes but no confidence, so every word's `c` is None here and the page's
mean confidence is None. It is not part of the product (D-040).
"""

from __future__ import annotations

import asyncio
import io

from PIL import Image

from citetally.models import Word
from citetally.reading.ocr import OcrError, OcrPage, OcrUnavailable


def _clamp(value: float) -> float:
    return min(max(value, 0.0), 1.0)


async def _recognise(png: bytes, width: int, height: int) -> list[Word]:
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.media.ocr import OcrEngine as WindowsOcr
    from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    engine = WindowsOcr.try_create_from_user_profile_languages()
    if engine is None:
        raise OcrUnavailable("Windows OCR has no language installed.")
    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(png)
    await writer.store_async()
    await writer.flush_async()
    writer.detach_stream()
    stream.seek(0)
    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    result = await engine.recognize_async(bitmap)
    words: list[Word] = []
    for line in result.lines:
        for word in line.words:
            box = word.bounding_rect
            text = word.text.strip()
            if not text or box.width <= 0 or box.height <= 0:
                continue
            words.append(
                Word(
                    t=text,
                    x0=_clamp(box.x / width),
                    y0=_clamp(box.y / height),
                    x1=_clamp((box.x + box.width) / width),
                    y1=_clamp((box.y + box.height) / height),
                    c=None,
                )
            )
    return words


class WindowsOcrEngine:
    name = "windows"

    def read_page(self, image: Image.Image, *, psm: int | None = None) -> OcrPage:
        try:
            from winrt.windows.media.ocr import OcrEngine as WindowsOcr
        except ImportError as error:
            raise OcrUnavailable("The winrt packages are not installed.") from error
        longest = max(image.size)
        if longest > WindowsOcr.max_image_dimension:
            scale = WindowsOcr.max_image_dimension / longest
            image = image.resize(
                (int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS
            )
        buffer = io.BytesIO()
        image.convert("L").save(buffer, "PNG")
        try:
            words = asyncio.run(_recognise(buffer.getvalue(), image.width, image.height))
        except OcrError:
            raise
        except Exception as error:
            raise OcrError("Windows OCR failed.") from error
        return OcrPage(words=words, mean_confidence=None)
