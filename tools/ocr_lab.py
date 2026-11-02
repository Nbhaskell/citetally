"""Try ways of reading a page, and count how many of the page's true values end up in the words.

The model is not involved. For each scan or photo in the development sets the answer key's printed
values (vendor, number, dates, amounts, quantities, unit prices, descriptions) are looked for in
the words the OCR produced, with the same grounding the pipeline uses. A value the OCR got wrong
cannot be found, so the share found is a direct measure of how well a way of reading serves the
rest of the pipeline.

    python -m tools.ocr_lab --variants current bigger psm6 --sample 80

Development splits only (`tuned`, `dev2`). Documents are chosen evenly, not by how they fared.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
from PIL import Image

from citetally.grounding import ground
from citetally.models import ExtractedFields, HeaderField, Word
from citetally.reading import preprocess as pre
from citetally.reading.merge import merge_readings
from citetally.reading.ocr import TesseractOcr, find_tesseract
from tools.evaluation.suites import load_suite
from tools.synthetic.golden import Item

ROOT = Path(__file__).resolve().parents[1]
DPI = 200
HEADER_KEYS = {f.value for f in HeaderField} - {"currency"}

# name -> what it changes. Anything not listed is the pipeline as it is.
VARIANTS: dict[str, dict[str, Any]] = {
    "current": {},
    "bigger": {"min_long": 2600, "max_long": 3400},
    "huge": {"min_long": 3200, "max_long": 4200},
    "psm6": {"psm": 6},
    "psm4": {"psm": 4},
    "bigger_psm6": {"min_long": 2600, "max_long": 3400, "psm": 6},
    "psm12": {"psm": 12},
}


def page_image(item: Item) -> Image.Image:
    path = ROOT / item.file
    if path.suffix == ".pdf":
        page = pdfium.PdfDocument(str(path))[0]
        image: Image.Image = page.render(scale=DPI / 72).to_pil().convert("RGB")
        return image
    with Image.open(path) as opened:
        return opened.convert("RGB")


def truth_fields(item: Item) -> ExtractedFields:
    printed = item.truth.printed
    lines = [
        {
            k: v
            for k, v in line.printed.items()
            if k in {"description", "quantity", "unit_price", "amount"}
        }
        for line in item.truth.lines
    ]
    header = {k: v for k, v in printed.items() if k in HEADER_KEYS}
    return ExtractedFields.model_validate(
        {"entry_type": item.truth.entry_type, **header, "lines": lines}
    )


def _words(image: Image.Image, settings: dict[str, Any], exe: str) -> list[Word]:
    prepared = pre.preprocess(
        image,
        min_long=settings.get("min_long", pre.WORKING_MIN_LONG_SIDE),
        max_long=settings.get("max_long", pre.WORKING_MAX_LONG_SIDE),
    )
    engine = TesseractOcr(exe, psm=settings.get("psm", 11), fallback_psm=6)
    return pre.preprocess_words(prepared, engine.read_page(prepared.image).words)


def read(item: Item, name: str, exe: str) -> dict[str, Any]:
    """`name` may join several settings with "+": each reads the page and a value counts as found
    when any of the readings holds it. With a "merge:" prefix the readings are merged into one."""
    started = time.monotonic()
    image = page_image(item)
    merge = name.startswith(("merge:", "best:"))
    parts = name.removeprefix("merge:").removeprefix("best:").split("+")
    readings = [_words(image, VARIANTS[part], exe) for part in parts]
    if name.startswith("best:"):  # the most confident reading is the one the others add to
        readings.sort(key=lambda words: -statistics.fmean([w.c for w in words if w.c] or [0.0]))
    if merge:  # one page made from all the readings, as the pipeline would hand it on
        readings = [merge_readings(readings[0], readings[1:])]
    result = ground(truth_fields(item), readings)
    wanted = [v for v in result.values if v.field != HeaderField.CURRENCY]
    by_kind: dict[str, list[bool]] = defaultdict(list)
    for value in wanted:
        by_kind["line:" + value.field.value if value.line_index is not None else "header"].append(
            value.found
        )
    return {
        "id": item.id,
        "condition": item.condition,
        "level": getattr(item, "level", None) or item.condition,
        "found": sum(v.found for v in wanted),
        "total": len(wanted),
        "by_kind": {k: [sum(v), len(v)] for k, v in by_kind.items()},
        "words": sum(len(r) for r in readings),
        "seconds": round(time.monotonic() - started, 1),
    }


def run_variant(name: str, items: list[Item], exe: str, workers: int) -> dict[str, Any]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(lambda item: read(item, name, exe), items))
    return summarise(name, rows)


def share(rows: list[dict[str, Any]]) -> float:
    hits: int = sum(int(r["found"]) for r in rows)
    total: int = sum(int(r["total"]) for r in rows)
    return hits / max(total, 1)


def summarise(name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    kinds: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for row in rows:
        groups[f"{row['condition']}/{row['level']}"].append(row)
        for kind, (hit, total) in row["by_kind"].items():
            kinds[kind][0] += hit
            kinds[kind][1] += total
    return {
        "variant": name,
        "documents": len(rows),
        "found_share": round(share(rows), 4),
        "by_group": {g: round(share(r), 4) for g, r in sorted(groups.items())},
        "by_kind": {k: round(v[0] / max(v[1], 1), 4) for k, v in sorted(kinds.items())},
        "median_seconds": statistics.median(r["seconds"] for r in rows),
        "words_median": statistics.median(r["words"] for r in rows),
    }


def sample_items(count: int) -> list[Item]:
    chosen: list[Item] = []
    for split in ("tuned", "dev2"):
        items = [i for i in load_suite(split).items if i.condition != "clean_pdf"]
        chosen += items
    step = max(len(chosen) // count, 1)
    return chosen[::step][:count]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument(
        "--variants", nargs="+", default=["current"], help="names, or names joined with +"
    )
    parser.add_argument("--sample", type=int, default=80)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "ocr_lab.json")
    args = parser.parse_args(argv)
    exe = find_tesseract("")
    if exe is None:
        print("Tesseract was not found.")
        return 2
    items = sample_items(args.sample)
    results: list[dict[str, Any]] = []
    for name in args.variants:
        summary = run_variant(name, items, exe, args.workers)
        results.append(summary)
        print(json.dumps(summary), flush=True)
    args.out.write_text(json.dumps(results, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
