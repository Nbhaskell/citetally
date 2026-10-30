"""Turn a clean PDF into the other three conditions, deterministically from a seed.

  clean_pdf    the PDF as drawn, with a text layer
  scan_light   an image-only PDF: slight skew, soft focus, mild noise
  scan_heavy   an image-only PDF: skew, blur, heavy noise, low contrast, shadow, dust, JPEG damage
  phone_photo  a JPEG: the page on a desk, in perspective, unevenly lit, soft, compressed

Two profiles exist. "tuned" damage is used for the development documents. "heldout" uses
different kinds of damage (streaks, creases, fax-style thresholding, motion blur, hard shadows)
so the held-out set also tests conditions the system was never tuned on. Pillow and NumPy only.
"""

from __future__ import annotations

import io
import time

import numpy as np
import pypdfium2 as pdfium
from numpy.typing import NDArray
from PIL import Image, ImageEnhance, ImageFilter

CONDITIONS = ("clean_pdf", "scan_light", "scan_heavy", "phone_photo")
PROFILES = ("tuned", "heldout")
_DPI = 200
_FIXED_DATE = time.struct_time((2026, 10, 31, 0, 0, 0, 5, 304, 0))  # byte-identical scans

Array = NDArray[np.float64]


def rasterize(pdf: bytes, dpi: int = _DPI) -> Image.Image:
    page = pdfium.PdfDocument(pdf)[0]
    image: Image.Image = page.render(scale=dpi / 72).to_pil().convert("RGB")
    return image


def _arr(image: Image.Image) -> Array:
    return np.asarray(image, dtype=np.float64)


def _img(array: Array) -> Image.Image:
    image: Image.Image = Image.fromarray(np.clip(array, 0, 255).astype(np.uint8))
    return image


def _noise(image: Image.Image, rng: np.random.Generator, sigma: float) -> Image.Image:
    data = _arr(image)
    return _img(data + rng.normal(0.0, sigma, data.shape[:2] + (1,) * (data.ndim - 2)))


def _rotate(image: Image.Image, angle: float, fill: tuple[int, int, int]) -> Image.Image:
    return image.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=fill)


def _jpeg_round_trip(image: Image.Image, quality: int) -> Image.Image:
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=quality)
    return Image.open(io.BytesIO(buffer.getvalue())).convert("RGB")


def _shadow(image: Image.Image, strength: float, rng: np.random.Generator) -> Image.Image:
    h, w = image.height, image.width
    xs = np.linspace(0, 1, w)[None, :]
    ys = np.linspace(0, 1, h)[:, None]
    direction = rng.uniform(0, 2 * np.pi)
    ramp = np.clip(xs * np.cos(direction) + ys * np.sin(direction) + 0.5, 0, 1)
    mask = 1.0 - strength * ramp**2
    return _img(_arr(image) * mask[:, :, None])


def _dust(image: Image.Image, rng: np.random.Generator, share: float) -> Image.Image:
    data = _arr(image)
    mask = rng.random(data.shape[:2]) < share
    data[mask] = rng.choice([0.0, 255.0], size=int(mask.sum()))[:, None]
    return _img(data)


def _streaks(image: Image.Image, rng: np.random.Generator, count: int) -> Image.Image:
    data = _arr(image)
    for x in rng.integers(0, data.shape[1], count):
        data[:, x : x + 1 + int(rng.integers(0, 2))] *= rng.uniform(0.55, 0.85)
    return _img(data)


def _crease(image: Image.Image, rng: np.random.Generator) -> Image.Image:
    data = _arr(image)
    y = int(rng.integers(data.shape[0] // 4, 3 * data.shape[0] // 4))
    data[y : y + 3] *= 0.6
    data[max(0, y - 6) : y] *= 0.9
    return _img(data)


def _motion_blur(image: Image.Image, vertical: bool) -> Image.Image:
    """A 5-pixel streak (Pillow kernels are 3x3 or 5x5)."""
    kernel = [0.0] * 25
    for i in range(5):
        kernel[(i * 5 + 2) if vertical else (2 * 5 + i)] = 1.0
    return image.filter(ImageFilter.Kernel((5, 5), kernel, scale=5.0))


def _quad_coefficients(
    source: list[tuple[float, float]], target: list[tuple[float, float]]
) -> list[float]:
    """Perspective coefficients mapping each output point (target) back to its input (source)."""
    rows: list[list[float]] = []
    values: list[float] = []
    for (x, y), (u, v) in zip(target, source, strict=True):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        values.append(u)
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        values.append(v)
    solution = np.linalg.solve(np.array(rows, dtype=float), np.array(values, dtype=float))
    return [float(c) for c in solution]


def _fax(image: Image.Image) -> Image.Image:
    """Even out the lighting, then keep only black and white, as a fax or a copier would."""
    gray = image.convert("L")
    background = np.maximum(_arr(gray.filter(ImageFilter.GaussianBlur(40))), 1.0)
    flat = np.clip(_arr(gray) / background * 255.0, 0, 255)
    return _img(np.where(flat > 190, 255.0, 0.0)).convert("L")


def _scan_light(page: Image.Image, rng: np.random.Generator, profile: str) -> Image.Image:
    image = _rotate(page, float(np.clip(rng.normal(0, 0.6), -1.2, 1.2)), (255, 255, 255))
    image = image.filter(ImageFilter.GaussianBlur(0.5))
    image = ImageEnhance.Contrast(image).enhance(0.93)
    image = _noise(image, rng, 4.0)
    if profile == "heldout":
        image = _streaks(image, rng, 6)
        image = _jpeg_round_trip(image, 55)
    return image.convert("L")


def _scan_heavy(page: Image.Image, rng: np.random.Generator, profile: str) -> Image.Image:
    sign = 1 if rng.random() < 0.5 else -1
    low, high = (1.5, 3.5) if profile == "tuned" else (3.5, 6.0)
    image = _rotate(page, sign * float(rng.uniform(low, high)), (250, 250, 250))
    small = image.resize(
        (int(image.width * 0.7), int(image.height * 0.7)), Image.Resampling.BILINEAR
    )
    image = small.resize(image.size, Image.Resampling.BILINEAR)
    image = image.filter(ImageFilter.GaussianBlur(1.1))
    image = ImageEnhance.Contrast(image).enhance(0.65)
    image = ImageEnhance.Brightness(image).enhance(float(rng.uniform(0.85, 1.0)))
    image = _shadow(image, 0.35, rng)
    image = _noise(image, rng, 14.0)
    if profile == "tuned":
        image = _dust(image, rng, 0.002)
        image = _jpeg_round_trip(image, 40)
        return image.convert("L")
    image = _crease(image, rng)
    image = _dust(image, rng, 0.015)  # salt-and-pepper
    return _fax(image)


def _phone_photo(page: Image.Image, rng: np.random.Generator, profile: str) -> Image.Image:
    held = profile == "heldout"
    canvas_w, canvas_h = 1500, 1900
    base = np.array([120.0, 95.0, 70.0]) + rng.normal(0, 6, 3)  # a wooden desk
    desk = base[None, None, :] + rng.normal(0, 10, (canvas_h, canvas_w, 1))
    canvas = _img(desk)
    scale = 0.82 * min(canvas_w / page.width, canvas_h / page.height)
    sheet = page.resize(
        (int(page.width * scale), int(page.height * scale)), Image.Resampling.LANCZOS
    )
    angle = float(rng.uniform(-8, 8))
    mask = Image.new("L", sheet.size, 255).rotate(
        angle, resample=Image.Resampling.BICUBIC, expand=True
    )
    sheet = _rotate(sheet, angle, (0, 0, 0))
    ox = (canvas_w - sheet.width) // 2
    oy = (canvas_h - sheet.height) // 2
    canvas.paste(sheet, (ox, oy), mask)

    wobble = 0.10 if held else 0.06
    w, h = canvas.size
    source = [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)]
    shift = rng.uniform(-wobble, wobble, (4, 2)) * np.array([w, h])
    target = [(sx + dx, sy + dy) for (sx, sy), (dx, dy) in zip(source, shift, strict=True)]
    coeffs = _quad_coefficients(source, target)
    canvas = canvas.transform(
        canvas.size,
        Image.Transform.PERSPECTIVE,
        coeffs,
        Image.Resampling.BICUBIC,
        fillcolor=(90, 70, 50),
    )

    xs = np.linspace(-1, 1, w)[None, :]
    ys = np.linspace(-1, 1, h)[:, None]
    vignette = 1.05 - 0.4 * (xs**2 + ys**2) / 2
    tilt = 1.0 + rng.uniform(-0.2, 0.2) * xs + rng.uniform(-0.2, 0.2) * ys
    light = vignette * tilt
    if held:
        light = light * (1.0 - 0.5 * np.clip(xs * 1.2 + ys * 0.4, 0, 1) ** 2)  # a hard shadow
    warm = np.array([1.04, 1.0, 0.93])
    canvas = _img(_arr(canvas) * light[:, :, None] * warm[None, None, :])
    canvas = (
        _motion_blur(canvas, bool(rng.random() < 0.5))
        if held
        else canvas.filter(ImageFilter.GaussianBlur(0.9))
    )
    canvas = _noise(canvas, rng, 12.0 if held else 6.0)
    return _jpeg_round_trip(canvas, 62)


def make_file(pdf: bytes, condition: str, seed: int, profile: str = "tuned") -> tuple[bytes, str]:
    """Return (file bytes, extension) for the document in the requested condition."""
    if condition not in CONDITIONS:
        raise ValueError(f"unknown condition {condition!r}")
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}")
    if condition == "clean_pdf":
        return pdf, "pdf"
    rng = np.random.default_rng(seed)
    page = rasterize(pdf)
    buffer = io.BytesIO()
    if condition == "phone_photo":
        _phone_photo(page, rng, profile).save(buffer, "JPEG", quality=62)
        return buffer.getvalue(), "jpg"
    degraded = (_scan_light if condition == "scan_light" else _scan_heavy)(page, rng, profile)
    degraded.save(
        buffer, "PDF", resolution=float(_DPI), creationDate=_FIXED_DATE, modDate=_FIXED_DATE
    )
    return buffer.getvalue(), "pdf"
