"""OCR bake-off on the development split: how well do engines and settings read the scans?

  python -m tools.ocr_bakeoff                       # all configurations, writes the report
  python -m tools.ocr_bakeoff --limit 8 --workers 1 # a quick look

Only the development ("tuned") documents are read; the held-out split stays sealed. The truth
for each page is the set of printed values in the golden file (header fields and line items, as
printed), so the scores answer the question that matters here: does the value a reviewer must
check survive reading? Each printed value is scored three ways:

  found     the printed string is in the page text exactly, or (for amounts, quantities and
            dates) a word has the same digits. This is what grounding can use.
  tokens    the share of the value's words that appear exactly among the OCR words.
  near      the share that appear with at least 85% similarity (one or two slipped characters).

The report is written to eval/reports/ocr_bakeoff.json and a table is printed. Speed is the
time to read one page, single-threaded, not counting the shared pre-processing step.
"""

from __future__ import annotations

import argparse
import difflib
import io
import json
import os
import re
import statistics
import time
from collections import Counter, defaultdict
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from citetally import ingest
from citetally.models import Word
from citetally.reading import layout, ocr, preprocess
from tools.synthetic.golden import GOLDEN_FILE, Item, load_golden

REPORT = Path("eval/reports/ocr_bakeoff.json")
NEAR_THRESHOLD = 0.85
LIMITS = ingest.Limits(
    max_bytes=20 * 1024 * 1024, max_pages=10, max_pixels=40_000_000, text_min_chars=80
)

# Printed header fields and what kind of value each is.
HEADER_KINDS = {
    "total": "money",
    "subtotal": "money",
    "tax_total": "money",
    "shipping": "money",
    "discount": "money",
    "tax_rate": "money",
    "entry_date": "date",
    "due_date": "date",
    "invoice_number": "id",
    "po_number": "id",
    "vendor_name": "text",
}
LINE_KINDS = {
    "description": "text",
    "quantity": "quantity",
    "unit_price": "money",
    "amount": "money",
    "tax": "money",
}
NUMERIC_KINDS = {"money", "quantity", "date"}
KINDS = ("money", "quantity", "date", "id", "text")


@dataclass(frozen=True)
class Ref:
    kind: str
    text: str


def reference_values(item: Item) -> list[Ref]:
    """Every printed value of a golden item that a reviewer would have to check."""
    refs = [
        Ref(HEADER_KINDS[key], value)
        for key, value in item.truth.printed.items()
        if key in HEADER_KINDS and value.strip()
    ]
    for line in item.truth.lines:
        refs += [
            Ref(LINE_KINDS[key], value)
            for key, value in line.printed.items()
            if key in LINE_KINDS and value.strip()
        ]
    return refs


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def _similar(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if abs(len(a) - len(b)) > max(2, len(a) // 4):  # too different in length to reach 85%
        return 0.0
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    if matcher.quick_ratio() < NEAR_THRESHOLD:
        return 0.0
    return matcher.ratio()


@dataclass(frozen=True)
class Scored:
    found: bool
    tokens: int
    tokens_exact: int
    tokens_near: int


def score_value(ref: Ref, words: Sequence[Word], text: str) -> Scored:
    """Score one printed value against the words read from the page and the text built from them."""
    flat = _squash(text)
    found = _squash(ref.text) in flat
    if not found and ref.kind in NUMERIC_KINDS:
        wanted = _digits(ref.text)
        found = bool(wanted) and any(_digits(word.t) == wanted for word in words)
    available = Counter(word.t for word in words)
    tokens = ref.text.split()
    exact = 0
    near = 0
    for token in tokens:
        if available[token] > 0:
            available[token] -= 1
            exact += 1
            near += 1
        elif any(_similar(token, word.t) >= NEAR_THRESHOLD for word in words):
            near += 1
    return Scored(found=found, tokens=len(tokens), tokens_exact=exact, tokens_near=near)


# ---- configurations ----------------------------------------------------------------------------


PREPS: dict[str, dict[str, Any] | None] = {  # None means no pre-processing
    "raw": None,
    "clean": {},  # the defaults of `preprocess.preprocess`
    "nowhiten": {"whiten_outside": False},
}


@dataclass(frozen=True)
class Config:
    name: str
    prep: str
    psm: int

    def make(self) -> ocr.OcrEngine:
        return ocr.TesseractOcr(psm=self.psm)  # with the default timeout and fallback


def configs_from(specs: Sequence[str]) -> list[Config]:
    """Specs look like `whiten/11`: a pre-processing variant and a Tesseract page mode."""
    out = []
    for spec in specs:
        prep, _, psm = spec.partition("/")
        if prep not in PREPS:
            raise SystemExit(f"unknown pre-processing {prep!r}; choose from {sorted(PREPS)}")
        out.append(Config(f"tesseract-{prep}-psm{psm}", prep, int(psm)))
    return out


DEFAULT_SPECS = ["raw/4", "raw/11", "nowhiten/11", "clean/3", "clean/4", "clean/6", "clean/11"]


# ---- one document ------------------------------------------------------------------------------


def load_page(item: Item) -> Image.Image:
    """The page image exactly as ingest would store it."""
    data = Path(item.file).read_bytes()
    mime = ingest.detect_type(data)
    assert mime is not None
    result = ingest._inspect(data, mime, LIMITS)
    if not result["ok"]:
        raise RuntimeError("the page could not be read")
    png, _, _ = result["pages"][0]
    return Image.open(io.BytesIO(png)).convert("RGB")


def run_document(item: Item, specs: Sequence[str]) -> dict[str, Any]:
    os.environ["OMP_THREAD_LIMIT"] = "1"  # one thread, so speed does not depend on core count
    page = load_page(item)
    refs = reference_values(item)
    record: dict[str, Any] = {
        "id": item.id,
        "condition": item.condition,
        "family": item.template_family,
        "refs": len(refs),
        "preprocess_seconds": {},
        "configs": {},
    }
    images: dict[str, Image.Image] = {"raw": page}
    for config in configs_from(specs):
        if config.prep not in images:
            options = PREPS[config.prep] or {}
            started = time.perf_counter()
            images[config.prep] = preprocess.preprocess(page, **options).image
            record["preprocess_seconds"][config.prep] = time.perf_counter() - started
        started = time.perf_counter()
        try:
            result = config.make().read_page(images[config.prep])
        except ocr.OcrError:
            record["configs"][config.name] = {"error": True}
            continue
        seconds = time.perf_counter() - started
        words = result.words
        text = layout.build_text(words)
        by_kind: dict[str, list[int]] = {kind: [0, 0, 0, 0, 0] for kind in KINDS}
        for ref in refs:
            scored = score_value(ref, words, text)
            row = by_kind[ref.kind]
            row[0] += 1
            row[1] += scored.found
            row[2] += scored.tokens
            row[3] += scored.tokens_exact
            row[4] += scored.tokens_near
        record["configs"][config.name] = {
            "seconds": seconds,
            "words": len(words),
            "mean_confidence": result.mean_confidence,
            "by_kind": by_kind,  # [values, found, tokens, tokens_exact, tokens_near] per kind
        }
    return record


# ---- the report --------------------------------------------------------------------------------


def _rates(rows: list[list[int]]) -> dict[str, float]:
    values = sum(r[0] for r in rows)
    tokens = sum(r[2] for r in rows)
    return {
        "values": values,
        "found": sum(r[1] for r in rows) / values if values else 0.0,
        "tokens": sum(r[3] for r in rows) / tokens if tokens else 0.0,
        "near": sum(r[4] for r in rows) / tokens if tokens else 0.0,
    }


def summarise(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Per configuration: scores overall, by condition and by kind, plus speed."""
    names = sorted({name for record in records for name in record["configs"]})
    summary: dict[str, Any] = {}
    for name in names:
        ok = [(r, r["configs"][name]) for r in records if "seconds" in r["configs"].get(name, {})]
        groups: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
        for pair in ok:
            groups["all"].append(pair)
            groups[pair[0]["condition"]].append(pair)
        entry: dict[str, Any] = {"documents": len(ok), "errors": len(records) - len(ok)}
        for group, pairs in groups.items():
            rows = [row for _, c in pairs for row in c["by_kind"].values()]
            numeric = [c["by_kind"][k] for _, c in pairs for k in ("money", "quantity", "date")]
            seconds = [c["seconds"] for _, c in pairs]
            confidences = [
                c["mean_confidence"] for _, c in pairs if c["mean_confidence"] is not None
            ]
            entry[group] = {
                "documents": len(pairs),
                "all_values": _rates(rows),
                "numbers": _rates(numeric),
                "by_kind": {k: _rates([c["by_kind"][k] for _, c in pairs]) for k in KINDS},
                "seconds_per_page_median": statistics.median(seconds),
                "words_per_page_median": statistics.median(c["words"] for _, c in pairs),
                "mean_confidence": statistics.fmean(confidences) if confidences else None,
            }
        summary[name] = entry
    return summary


def render(summary: dict[str, Any]) -> str:
    conditions = ["all", "clean_pdf", "scan_light", "scan_heavy", "phone_photo"]
    lines = []
    for title, key in (
        ("Printed values found (any kind)", "all_values"),
        ("Numbers found (amounts, quantities, dates)", "numbers"),
    ):
        lines += [
            "",
            title,
            f"  {'configuration':<24}" + "".join(f"{c:>13}" for c in conditions) + f"{'s/page':>9}",
        ]
        for name, entry in summary.items():
            cells = "".join(
                f"{entry[c][key]['found'] * 100:>12.1f}%" for c in conditions if c in entry
            )
            lines.append(f"  {name:<24}{cells}{entry['all']['seconds_per_page_median']:>9.2f}")
    lines += ["", "Word recall of printed values, exact / near (all conditions)"]
    for name, entry in summary.items():
        v = entry["all"]["all_values"]
        lines.append(f"  {name:<24}{v['tokens'] * 100:>6.1f}% / {v['near'] * 100:>5.1f}%")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--limit", type=int, default=0, help="read only the first N documents")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--specs", nargs="+", default=DEFAULT_SPECS, help="pre-processing/psm, e.g. whiten/11"
    )
    parser.add_argument("--conditions", nargs="+", default=[], help="read only these conditions")
    parser.add_argument("--out", type=Path, default=REPORT)
    args = parser.parse_args(argv)

    items = load_golden(GOLDEN_FILE, "tuned")
    if args.conditions:
        items = [item for item in items if item.condition in args.conditions]
    items = items[: args.limit] if args.limit else items
    print(f"{len(items)} development documents, {len(args.specs)} configurations")
    if args.workers > 1:
        with ProcessPoolExecutor(args.workers) as pool:
            records = list(pool.map(run_document, items, [args.specs] * len(items)))
    else:
        records = [run_document(item, args.specs) for item in items]
    summary = summarise(records)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "split": "tuned",
        "documents": len(items),
        "ids": [r["id"] for r in records],
        "pre_processing_seconds_median": {
            prep: statistics.median(
                r["preprocess_seconds"][prep] for r in records if prep in r["preprocess_seconds"]
            )
            for prep in sorted({p for r in records for p in r["preprocess_seconds"]})
        },
        "summary": summary,
        "per_document": records,
    }
    args.out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(render(summary))
    print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
