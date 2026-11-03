"""Build `docs/images/walkthrough.gif` from the screenshots in `docs/images/`.

The GIF is a slide show of real screens (made from the invented demo documents), one caption per
screen. It is not a screen recording. Pillow only.

    .\\.venv\\Scripts\\python.exe -m tools.make_walkthrough
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

IMAGES = Path(__file__).resolve().parents[1] / "docs" / "images"
OUT = IMAGES / "walkthrough.gif"
WIDTH = 960
BAR = 54
STEPS = [
    ("inbox.png", "1. Documents arrive in the inbox; every one is waiting for a person.", 3500),
    (
        "review-blocked.png",
        "2. The page is on the left. Values are found on it; checks run in code.",
        5000,
    ),
    (
        "review-picture-check.png",
        "3. A phone photo: a value the page can't place gets one check against the picture.",
        5000,
    ),
    ("review-ready.png", "4. A clean one: nothing needs attention. A person approves it.", 4000),
    (
        "exports.png",
        "5. Approved entries leave as a CSV you download. Nothing is sent anywhere.",
        4000,
    ),
    ("insights.png", "6. Counts and sums of what was reviewed. No forecasts, no scores.", 4000),
]


def font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def frame(name: str, caption: str) -> Image.Image:
    shot = Image.open(IMAGES / name).convert("RGB")
    height = round(shot.height * WIDTH / shot.width)
    shot = shot.resize((WIDTH, height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (WIDTH, height + BAR), (24, 26, 24))
    canvas.paste(shot, (0, BAR))
    draw = ImageDraw.Draw(canvas)
    draw.text((16, 15), caption, fill=(236, 232, 220), font=font(21))
    return canvas


def main() -> int:
    frames = [frame(name, caption) for name, caption, _ in STEPS]
    tallest = max(f.height for f in frames)
    padded = []
    for f in frames:
        canvas = Image.new("RGB", (WIDTH, tallest), (24, 26, 24))
        canvas.paste(f, (0, 0))
        padded.append(
            canvas.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        )
    padded[0].save(
        OUT,
        save_all=True,
        append_images=padded[1:],
        duration=[d for _, _, d in STEPS],
        loop=0,
        optimize=True,
    )
    print(f"Wrote {OUT} ({OUT.stat().st_size // 1024} KB, {len(padded)} frames)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
