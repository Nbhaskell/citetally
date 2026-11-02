# ruff: noqa: E501
"""Spike: can the vision model point at a value, and can a crop of that spot be read back?

For harsh development scans and photos, the values the picture path read but OCR could not locate
are the ones that block a document. This asks the vision model for a box around each such value,
crops the page there, enlarges it, reads it with Tesseract, and checks with the strict grounding
whether the crop holds the value. Nothing here is part of the pipeline.

    python -m tools.crop_spike --docs 20
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sqlite3
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageOps

from citetally.grounding import ground
from citetally.models import ExtractedFields, HeaderField
from citetally.providers import OllamaProvider
from citetally.providers.base import ModelError
from citetally.providers.ollama import post_json
from citetally.reading.ocr import TesseractOcr, find_tesseract
from tools.evaluation.run import RUNS, SCRATCH, read_records
from tools.evaluation.score import same_value
from tools.evaluation.suites import load_suite

ROOT = Path(__file__).resolve().parents[1]
MAX_SIDE = 1568
RUNS_USED = {
    "dev2": ["dev2-final-p1"],
    "tuned": ["tuned-final-p1-scan_heavy+phone_photo"],
}
HEADER = {f.value for f in HeaderField}
SCHEMA = {
    "type": "object",
    "properties": {
        "boxes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer"},
                    "x0": {"type": "integer"},
                    "y0": {"type": "integer"},
                    "x1": {"type": "integer"},
                    "y1": {"type": "integer"},
                },
                "required": ["n", "x0", "y0", "x1", "y1"],
            },
        }
    },
    "required": ["boxes"],
}
SYSTEM = (
    "You find printed text in a picture of a business document and report where it is. "
    "You never change the text."
)


def pick(count: int) -> list[tuple[str, str, dict[str, Any]]]:
    """Harsh-ish documents (heavy scans and phone photos) with values OCR could not locate."""
    chosen: list[tuple[str, str, dict[str, Any]]] = []
    for split, runs in RUNS_USED.items():
        items = {i.id: i for i in load_suite(split).items}
        rows: list[tuple[str, str, dict[str, Any]]] = []
        for name in runs:
            for record in read_records(RUNS / name / "records.jsonl").values():
                item = items[record["id"]]
                missing = [
                    e for e in record["evidence"] if not e["found"] and e["field"] != "currency"
                ]
                if item.condition in {"scan_heavy", "phone_photo"} and missing and not item.planted:
                    rows.append((split, name, record))
        step = max(len(rows) // (count // 2), 1)
        chosen += rows[::step][: count // 2]
    return chosen


def page_path(run: str, filename: str) -> Path:
    db = sqlite3.connect(SCRATCH / run / "run.db")
    row = db.execute(
        "SELECT p.image_path FROM pages p JOIN documents d ON d.id = p.document_id "
        "WHERE d.original_filename LIKE ? ORDER BY d.id DESC LIMIT 1",
        (Path(filename).stem + ".%",),
    ).fetchone()
    db.close()
    return Path(SCRATCH / run / str(row[0]))


def jpeg_for_model(image: Image.Image) -> tuple[bytes, tuple[int, int]]:
    picture = image.convert("RGB")
    picture.thumbnail((MAX_SIDE, MAX_SIDE))
    buffer = io.BytesIO()
    picture.save(buffer, "JPEG", quality=90)
    return buffer.getvalue(), picture.size


def ask_boxes(
    provider: OllamaProvider, jpeg: bytes, values: list[tuple[str, str]]
) -> list[dict[str, int]]:
    listing = "\n".join(f"{n}. {field}: {text}" for n, (field, text) in enumerate(values, start=1))
    user = (
        "For each numbered item below, give the box of that exact printed text in the picture. "
        "Use integers from 0 to 1000 across the picture's width (x) and height (y), origin at the "
        "top left, as x0, y0 (top left corner) and x1, y1 (bottom right corner). Leave out any item "
        "you cannot see.\n\n" + listing
    )
    result = provider.generate_json(
        system=SYSTEM, user=user, schema=SCHEMA, images=[jpeg], max_tokens=800, timeout_s=240
    )
    boxes = (result.parsed or {}).get("boxes", [])
    return [b for b in boxes if isinstance(b, dict)]


def crop_words(
    page: Image.Image, box: tuple[float, float, float, float], engine: TesseractOcr
) -> list[list[Any]]:
    """Several readings of the cropped spot. Each is a list of words (fractions of the crop)."""
    w, h = page.size
    x0, y0, x1, y1 = box
    padx, pady = (x1 - x0) * 0.12 + 0.004, (y1 - y0) * 0.35 + 0.003
    area = (
        max(0, int((x0 - padx) * w)),
        max(0, int((y0 - pady) * h)),
        min(w, int((x1 + padx) * w)),
        min(h, int((y1 + pady) * h)),
    )
    crop = page.crop(area).convert("L")
    if crop.width < 4 or crop.height < 4:
        return []
    scale = max(1.0, 110 / crop.height)
    big = crop.resize((int(crop.width * scale), int(crop.height * scale)), Image.Resampling.LANCZOS)
    variants = [
        ImageOps.autocontrast(big, cutoff=2),
        ImageOps.autocontrast(big.filter(ImageFilter.GaussianBlur(1.0)), cutoff=2).point(
            lambda p: 255 if p > 150 else 0
        ),
        ImageOps.expand(ImageOps.autocontrast(big, cutoff=2), border=20, fill=255),
    ]
    readings = []
    for variant in variants:
        for psm in (7, 6):
            try:
                readings.append(engine.read_page(variant, psm=psm).words)
            except Exception:
                continue
    return readings


def located(field: str, text: str, readings: list[list[Any]]) -> bool:
    if field in HEADER:
        fields = ExtractedFields.model_validate({"entry_type": "invoice", field: text})
    else:
        fields = ExtractedFields.model_validate({"entry_type": "invoice", "lines": [{field: text}]})
    result = ground(fields, readings)
    return any(v.found for v in result.values if v.field.value == field)


def truthful(item: Any, field: str, text: str) -> bool:
    """Whether the value is what the page really prints (the answer key)."""
    if field in HEADER:
        return same_value(field, item.truth.printed.get(field), text)
    pool = {line.printed.get(field, "") for line in item.truth.lines}
    return any(
        same_value("total", p, text)
        if field in {"amount", "unit_price"}
        else p.strip().casefold() == text.strip().casefold()
        for p in pool
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--docs", type=int, default=20)
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "crop_spike.json")
    args = parser.parse_args(argv)
    exe = find_tesseract("")
    engine = TesseractOcr(exe or "")
    provider = OllamaProvider(
        "http://127.0.0.1:11434", "qwen3-vl:8b-instruct", supports_vision=True, context_tokens=16384
    )
    items = {i.id: i for s in ("dev2", "tuned") for i in load_suite(s).items}
    rows: list[dict[str, Any]] = []
    for split, run, record in pick(args.docs):
        item = items[record["id"]]
        path = page_path(run, item.file)
        page = Image.open(path)
        jpeg, sent = jpeg_for_model(page)
        wanted = [
            (e["field"], e["printed_text"])
            for e in record["evidence"]
            if not e["found"] and e["field"] != "currency"
        ][:8]
        started = time.monotonic()
        try:
            boxes = ask_boxes(provider, jpeg, wanted)
        except ModelError as error:
            print(record["id"], "model error", type(error).__name__)
            continue
        asked = round(time.monotonic() - started, 1)
        by_n = {b.get("n"): b for b in boxes}
        for n, (field, text) in enumerate(wanted, start=1):
            box = by_n.get(n)
            row: dict[str, Any] = {
                "doc": record["id"], "split": split, "condition": item.condition,
                "level": getattr(item, "level", None), "field": field, "value": text,
                "true": truthful(item, field, text), "asked_s": asked, "box": None,
            }  # fmt: skip
            if box and all(isinstance(box.get(k), int) for k in ("x0", "y0", "x1", "y1")):
                row["box"] = [box["x0"], box["y0"], box["x1"], box["y1"]]
                raw = row["box"]
                for convention in ("norm1000", "pixels"):
                    if convention == "norm1000":
                        frac = (raw[0] / 1000, raw[1] / 1000, raw[2] / 1000, raw[3] / 1000)
                    else:
                        frac = (
                            raw[0] / sent[0],
                            raw[1] / sent[1],
                            raw[2] / sent[0],
                            raw[3] / sent[1],
                        )
                    valid = 0 <= frac[0] < frac[2] <= 1.01 and 0 <= frac[1] < frac[3] <= 1.01
                    small = valid and (frac[2] - frac[0]) < 0.6 and (frac[3] - frac[1]) < 0.15
                    ok = bool(small) and located(field, text, crop_words(page, frac, engine))
                    row[convention] = {"valid": bool(valid), "small": bool(small), "located": ok}
            rows.append(row)
        print(
            record["id"],
            item.condition,
            getattr(item, "level", None),
            f"{len(wanted)} values, {len(boxes)} boxes, {asked}s",
            flush=True,
        )
    args.out.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    summarise(rows)
    return 0


def summarise(rows: list[dict[str, Any]]) -> None:
    n = len(rows)
    boxed = [r for r in rows if r["box"]]
    print(
        f"\n{n} unfound values over {len({r['doc'] for r in rows})} documents; the model gave a box for {len(boxed)}"
    )
    for convention in ("norm1000", "pixels"):
        hits = [r for r in boxed if r.get(convention, {}).get("located")]
        valid = [r for r in boxed if r.get(convention, {}).get("valid")]
        wrong = [r for r in hits if not r["true"]]
        print(
            f"  {convention:9} valid box {len(valid)}/{len(boxed)}; value located from the crop "
            f"{len(hits)}/{n} ({len(hits) / max(n, 1) * 100:.0f}%); located but not what the page prints: {len(wrong)}"
        )
    print(f"  values that really match the answer key: {sum(r['true'] for r in rows)}/{n}")
    print(
        f"  median seconds for the box request: {statistics.median(r['asked_s'] for r in rows):.1f}"
    )
    by_field: dict[str, list[bool]] = {}
    for r in rows:
        best = max(
            (r.get(c, {}).get("located", False) for c in ("norm1000", "pixels")), default=False
        )
        by_field.setdefault(r["field"], []).append(best)
    print(
        "  located by field (best convention):",
        {f: f"{sum(v)}/{len(v)}" for f, v in sorted(by_field.items())},
    )


_ = (re, post_json)

if __name__ == "__main__":
    sys.exit(main())
