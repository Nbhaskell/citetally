"""Turn a clean PDF into scans and photos at three levels of damage, from a seed.

The first set only ever had rough conditions, so it could not say how reading gets worse as the
picture gets worse. Here each condition has levels:

    clean_pdf    clean               the PDF as drawn
    scan_light   mild | typical | harsh
    scan_heavy   typical | harsh
    phone_photo  mild | typical | harsh

"typical" and "harsh" reuse the first set's two damage profiles (`degrade.py`) so results can be
compared. "mild" is new: a sharp 300 dpi flatbed scan, and a modern phone photo (2400 x 3000, good
light, a little perspective, light compression). Pillow and NumPy only.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from tools.synthetic import degrade

LEVELS = {
    "clean_pdf": ("clean",),
    "scan_light": ("mild", "typical", "harsh"),
    "scan_heavy": ("typical", "harsh"),
    "phone_photo": ("mild", "typical", "harsh"),
}
_PROFILE = {"typical": "tuned", "harsh": "heldout"}


def _scan_mild(pdf: bytes, rng: np.random.Generator) -> tuple[bytes, str]:
    page = degrade.rasterize(pdf, 300)
    image = degrade._rotate(page, float(np.clip(rng.normal(0, 0.3), -0.6, 0.6)), (255, 255, 255))
    image = image.filter(ImageFilter.GaussianBlur(0.35))
    image = ImageEnhance.Contrast(image).enhance(0.97)
    image = degrade._noise(image, rng, 2.0).convert("L")
    buffer = io.BytesIO()
    image.save(
        buffer, "PDF", resolution=300.0,
        creationDate=degrade._FIXED_DATE, modDate=degrade._FIXED_DATE,
    )  # fmt: skip
    return buffer.getvalue(), "pdf"


def _photo_mild(pdf: bytes, rng: np.random.Generator) -> tuple[bytes, str]:
    """A modern phone photo: sharp, well lit, a few degrees of tilt and a little keystone."""
    page = degrade.rasterize(pdf, 220)
    canvas_w, canvas_h = 2400, 3000
    base = np.array([150.0, 140.0, 125.0]) + rng.normal(0, 5, 3)  # a pale table top
    canvas = degrade._img(base[None, None, :] + rng.normal(0, 4, (canvas_h, canvas_w, 1)))
    scale = 0.9 * min(canvas_w / page.width, canvas_h / page.height)
    sheet = page.resize(
        (int(page.width * scale), int(page.height * scale)), Image.Resampling.LANCZOS
    )
    angle = float(rng.uniform(-4, 4))
    mask = Image.new("L", sheet.size, 255).rotate(
        angle, resample=Image.Resampling.BICUBIC, expand=True
    )
    sheet = degrade._rotate(sheet, angle, (0, 0, 0))
    canvas.paste(sheet, ((canvas_w - sheet.width) // 2, (canvas_h - sheet.height) // 2), mask)

    w, h = canvas.size
    source = [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)]
    shift = rng.uniform(-0.035, 0.035, (4, 2)) * np.array([w, h])
    target = [(sx + dx, sy + dy) for (sx, sy), (dx, dy) in zip(source, shift, strict=True)]
    canvas = canvas.transform(
        canvas.size,
        Image.Transform.PERSPECTIVE,
        degrade._quad_coefficients(source, target),
        Image.Resampling.BICUBIC,
        fillcolor=(140, 130, 115),
    )
    xs = np.linspace(-1, 1, w, dtype=np.float32)[None, :]
    ys = np.linspace(-1, 1, h, dtype=np.float32)[:, None]
    light = 1.03 - 0.18 * (xs**2 + ys**2) / 2 + rng.uniform(-0.06, 0.06) * xs
    data = np.asarray(canvas, dtype=np.float32) * light[:, :, None]
    canvas = degrade._img(data.astype(np.float64))
    canvas = canvas.filter(ImageFilter.GaussianBlur(0.5))
    canvas = degrade._noise(canvas, rng, 2.5)
    buffer = io.BytesIO()
    canvas.save(buffer, "JPEG", quality=88)
    return buffer.getvalue(), "jpg"


def make_fresh_file(pdf: bytes, condition: str, level: str, seed: int) -> tuple[bytes, str]:
    """(file bytes, extension) for the document at this condition and level of damage."""
    if level not in LEVELS.get(condition, ()):
        raise ValueError(f"{condition!r} has no level {level!r}")
    if condition == "clean_pdf":
        return pdf, "pdf"
    rng = np.random.default_rng(seed)
    if level == "mild":
        return (_scan_mild if condition == "scan_light" else _photo_mild)(pdf, rng)
    return degrade.make_file(pdf, condition, seed, _PROFILE[level])
