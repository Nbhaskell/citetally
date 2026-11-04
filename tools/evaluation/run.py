"""The runner: put golden documents through the real pipeline and save what came out.

It scores nothing. Each document's result is appended to `eval/runs/<run id>/records.jsonl` as it
finishes, so an interrupted run resumes where it stopped. `meta.json` beside it records what the
run was made of: commit and whether the tree was changed, the settings that differ from the
defaults, models, OCR engine and prompt version, and the hash of the golden file.

    python -m tools.evaluation.run --variant baseline --pass 1
    python -m tools.evaluation.run --variant forced_ocr --pass 1 --conditions clean_pdf

The held-out split opens only with `--split heldout --confirm-heldout-once`, once, ever: a lock
file remembers it. That run is made after the development numbers are frozen.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from citetally import db, ingest, pipeline
from citetally import repository as repo
from citetally.api.state import real_services
from citetally.config import Settings
from citetally.extract import PROMPT_VERSION
from citetally.matching import normalize_name
from citetally.pipeline import Services
from tools.evaluation.suites import OPENS_ONCE, SPLITS, load_suite
from tools.evaluation.world import World, order, seed
from tools.synthetic.facts import Facts
from tools.synthetic.golden import GOLDEN_FILE, Item

ROOT = Path(__file__).resolve().parent.parent.parent
RUNS = ROOT / "eval" / "runs"
SCRATCH = ROOT / "data" / "eval"
HELDOUT_LOCK = RUNS / "HELDOUT_RUN.lock"
SEALED_LOCK = RUNS / "SEALED_RUN.lock"
SEALED2_LOCK = RUNS / "SEALED2_RUN.lock"
SEALED3_LOCK = RUNS / "SEALED3_RUN.lock"

# What each variant changes, as environment names. Anything not listed is the default.
VARIANTS: dict[str, dict[str, str]] = {
    "baseline": {},
    # The product as it is after Stage 2: its own defaults, nothing overridden.
    "final": {},
    # Digital PDFs normally use their text layer. This ignores it, so the page is read by OCR.
    "forced_ocr": {"CITETALLY_TEXT_LAYER_MIN_CHARS": "1000000000"},
    # The model also sees the page picture.
    "text_and_image": {
        "CITETALLY_EXTRACT_MODE": "text_and_image",
        "CITETALLY_VISION_MODEL": "qwen3-vl:8b-instruct",
    },
    # Each scanned page is read in two or three ways (Tesseract page modes and sizes).
    "ocr2": {"CITETALLY_OCR_READINGS": "2"},
    "ocr3": {"CITETALLY_OCR_READINGS": "3"},
    # Scanned pages are read three ways and sent with their picture to the vision model; a PDF
    # with a text layer goes to the text model as text.
    "auto3": {
        "CITETALLY_EXTRACT_MODE": "auto",
        "CITETALLY_VISION_MODEL": "qwen3-vl:8b-instruct",
        "CITETALLY_OCR_READINGS": "3",
    },
    # The model also sees the page picture, and each scanned page is read three ways.
    "image_ocr3": {
        "CITETALLY_EXTRACT_MODE": "text_and_image",
        "CITETALLY_VISION_MODEL": "qwen3-vl:8b-instruct",
        "CITETALLY_OCR_READINGS": "3",
    },
    # The product's own settings with RapidOCR in place of Tesseract (D-073). A page with a text
    # layer is read as before, so only scans and photos differ.
    "final_rapid": {"CITETALLY_OCR_ENGINE": "rapidocr"},
    # Tesseract's text and confidence for the model and the read-quality check, with RapidOCR's
    # words added only for locating values (D-075).
    "final_hybrid": {"CITETALLY_OCR_LOCATOR": "rapidocr"},
    # The model thinks before it answers; the token budget and timeout are raised with it.
    "thinking": {
        "CITETALLY_ENABLE_THINKING": "true",
        "CITETALLY_EXTRACT_MAX_TOKENS": "8000",
        "CITETALLY_EXTRACT_TIMEOUT_S": "900",
    },
}


# ---- provenance --------------------------------------------------------------------------------


def _git(*args: str) -> str:
    try:
        done = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip()


def _tesseract_version(path: str) -> str:
    try:
        done = subprocess.run(
            [path, "--version"], capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return (done.stdout or done.stderr).splitlines()[0] if (done.stdout or done.stderr) else ""


def _rapidocr_version() -> str:
    try:
        return "rapidocr " + importlib.metadata.version("rapidocr")
    except importlib.metadata.PackageNotFoundError:
        return "rapidocr not installed"


def _ocr_version(settings: Settings, tesseract: str) -> str | None:
    if settings.ocr_engine == "rapidocr":
        return _rapidocr_version()
    if settings.ocr_locator == "rapidocr":
        return f"{tesseract}, with {_rapidocr_version()} locating values"
    return None


def provenance(
    settings: Settings, variant: str, run_id: str, split: str, golden_file: Path = GOLDEN_FILE
) -> dict[str, Any]:
    from citetally.reading.ocr import find_tesseract

    cmd = find_tesseract(settings.tesseract_cmd) or ""
    return {
        "run_id": run_id,
        "split": split,
        "variant": variant,
        "variant_settings": VARIANTS.get(variant, {}),
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": _git("rev-parse", "HEAD"),
        "tree_changed": bool(_git("status", "--porcelain")),
        "golden_file": str(golden_file.relative_to(ROOT)),
        "golden_sha256": hashlib.sha256(golden_file.read_bytes()).hexdigest(),
        "provider": settings.model_provider,
        "text_model": settings.text_model,
        "vision_model": settings.vision_model,
        "extract_mode": settings.extract_mode,
        "enable_thinking": settings.enable_thinking,
        "extract_max_tokens": settings.extract_max_tokens,
        "text_layer_min_chars": settings.text_layer_min_chars,
        "ocr_engine": settings.ocr_engine,
        "tesseract": _tesseract_version(cmd) if cmd else "not found",
        "ocr_version": _ocr_version(settings, _tesseract_version(cmd) if cmd else "not found"),
        "prompt_version": PROMPT_VERSION,
        "temperature": 0.0,
        "seed": 0,
        "machine": f"{platform.system()} {platform.release()}, Python {platform.python_version()}",
    }


# ---- one document ------------------------------------------------------------------------------


def collect(
    conn: Any, document: Any, item: Item, seconds: float, world: World, *, context_missing: bool
) -> dict[str, Any]:
    """What the pipeline stored for one document, as plain data for the scorer."""
    record: dict[str, Any] = {
        "id": item.id,
        "condition": item.condition,
        "split": item.split,
        "status": document.status.value,
        "failure_stage": document.failure_stage.value if document.failure_stage else None,
        "seconds": seconds,
        "page_count": document.page_count,
        "source_kind": document.source_kind.value if document.source_kind else None,
        "context_missing": context_missing,
        "pages": [],
        "extraction": None,
        "entry": None,
        "lines": [],
        "evidence": [],
        "checks": [],
        "stage_ms": {},
    }
    record["pages"] = [
        {
            "read_method": p.read_method.value,
            "mean_confidence": p.mean_confidence,
            "word_count": p.word_count,
        }
        for p in repo.list_pages(conn, document.id)
    ]
    for event in repo.list_audit_events(conn, document.id):
        if event.event_type == "stage_finished" and event.stage and event.duration_ms is not None:
            record["stage_ms"][event.stage.value] = event.duration_ms
    extraction = repo.latest_extraction(conn, document.id)
    if extraction is not None:
        record["extraction"] = {
            "fields": json.loads(extraction.fields),
            "input_tokens": extraction.input_tokens,
            "output_tokens": extraction.output_tokens,
            "duration_ms": extraction.duration_ms,
            "model": extraction.model,
            "prompt_version": extraction.prompt_version,
            "extract_mode": extraction.extract_mode.value,
        }
    entry = repo.get_entry_for_document(conn, document.id)
    if entry is not None:
        method = entry.vendor_match_method
        category = repo.get_category(conn, entry.category_id) if entry.category_id else None
        record["entry"] = {
            "entry_type": entry.entry_type.value,
            "vendor_golden_id": world.vendor_golden_id.get(entry.vendor_id or -1),
            "vendor_match_method": method.value if method else None,
            "invoice_number": entry.invoice_number,
            "entry_date": entry.entry_date,
            "due_date": entry.due_date,
            "currency": entry.currency,
            "subtotal_minor": entry.subtotal_minor,
            "tax_total_minor": entry.tax_total_minor,
            "shipping_minor": entry.shipping_minor,
            "discount_minor": entry.discount_minor,
            "total_minor": entry.total_minor,
            "category": category.code if category else None,
        }
        record["lines"] = [
            {
                "description": line.description,
                "quantity": line.quantity,
                "unit_price": line.unit_price,
                "amount_minor": line.amount_minor,
            }
            for line in repo.list_lines(conn, entry.id)
        ]
        line_ids = {line.id for line in repo.list_lines(conn, entry.id)}
        record["evidence"] = [
            {
                "field": e.field.value,
                "line": e.line_id in line_ids,
                "printed_text": e.printed_text,
                "found": e.found,
                "score": e.match_score,
            }
            for e in repo.list_evidence(conn, entry.id)
        ]
    record["checks"] = [
        {
            "code": c.check_code.value,
            "blocking": c.blocking,
            "passed": c.passed,
            "detail": json.loads(c.detail),
        }
        for c in repo.list_checks(conn, document.id)
    ]
    return record


def run_one(
    conn: Any,
    settings: Settings,
    services: Services,
    item: Item,
    world: World,
    *,
    context_missing: bool,
) -> dict[str, Any]:
    started = time.monotonic()
    path = Path(item.file)
    if not path.is_absolute():
        path = ROOT / path
    result = ingest.ingest(conn, path.read_bytes(), path.name, settings=settings)
    document = result.document
    target = document.duplicate_of if result.outcome == "duplicate" else document.id
    if result.outcome != "failed" and target is not None:
        document = pipeline.process(conn, target, services)
    return collect(
        conn, document, item, round(time.monotonic() - started, 1), world,
        context_missing=context_missing,
    )  # fmt: skip


# ---- a whole run -------------------------------------------------------------------------------


def read_records(path: Path) -> dict[str, dict[str, Any]]:
    done: dict[str, dict[str, Any]] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                done[record["id"]] = record
    return done


def run(
    *,
    items: Sequence[Item],
    history_items: Sequence[Item],
    facts: Facts,
    settings: Settings,
    services: Services,
    work_dir: Path,
    out_dir: Path,
    meta: dict[str, Any],
    log: Any = print,
) -> list[dict[str, Any]]:
    """Process `items` (originals first) in a fresh database under `work_dir`; return records."""
    out_dir.mkdir(parents=True, exist_ok=True)
    records_file = out_dir / "records.jsonl"
    done = read_records(records_file)
    if not done:  # a resumed run keeps its database; a new one starts clean
        shutil.rmtree(work_dir, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    conn = db.connect(str(work_dir / "run.db"))
    db.migrate(conn)
    db.seed_categories(conn)
    if conn.execute("SELECT COUNT(*) FROM vendors").fetchone()[0] > 0:  # resumed: already seeded
        world = _known_world(conn, facts)
    else:
        world = seed(conn, facts, history_items, min_history=settings.outlier_min_history)
    meta = {
        **meta,
        "vendors_seeded": world.vendors,
        "history_entries": world.history_entries,
        "history_padded": world.history_padded,
        "documents": len(items),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")

    ids = {item.id for item in items}
    todo = [item for item in order(items) if item.id not in done]
    log(f"{len(items)} documents, {len(done)} already done", flush=True)
    with records_file.open("a", encoding="utf-8") as sink:
        for number, item in enumerate(todo, start=1):
            missing = bool(item.expected_duplicate_of) and item.expected_duplicate_of not in ids
            record = run_one(conn, settings, services, item, world, context_missing=missing)
            sink.write(json.dumps(record) + "\n")
            sink.flush()
            done[item.id] = record
            log(
                f"[{number}/{len(todo)}] {item.id} {item.condition} {record['status']} "
                f"{record['seconds']}s",
                flush=True,
            )
    conn.close()
    meta["finished_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    meta["records_sha256"] = hashlib.sha256(records_file.read_bytes()).hexdigest()
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return [done[item.id] for item in items if item.id in done]


def _known_world(conn: Any, facts: Facts) -> World:
    """The world of a run that is being resumed: which golden id each vendor row is."""
    world = World()
    for vendor in facts.vendors:
        row = repo.find_vendor_by_normalized(conn, normalize_name(vendor.name))
        if row is not None:
            world.vendor_golden_id[row.id] = vendor.id
            world.vendors += 1
    world.history_entries = conn.execute(
        "SELECT COUNT(*) FROM documents WHERE original_filename LIKE 'history-%'"
    ).fetchone()[0]
    return world


# ---- command line ------------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--split", choices=list(SPLITS), default="tuned")
    parser.add_argument("--variant", choices=sorted(VARIANTS), default="baseline")
    parser.add_argument("--pass", dest="pass_number", type=int, default=1)
    parser.add_argument("--conditions", default="", help="comma-separated; default all four")
    parser.add_argument("--limit", type=int, default=0, help="only the first N documents")
    parser.add_argument("--fresh", action="store_true", help="delete this run and start over")
    parser.add_argument(
        "--confirm-heldout-once",
        action="store_true",
        help="open the held-out split. Allowed once, after dev numbers are frozen.",
    )
    parser.add_argument(
        "--confirm-sealed-once",
        action="store_true",
        help="open the sealed split. Allowed once, after the fixes are made.",
    )
    parser.add_argument(
        "--confirm-sealed2-once",
        action="store_true",
        help="open the second sealed split. Allowed once, after the second round of fixes.",
    )
    parser.add_argument(
        "--confirm-sealed3-once",
        action="store_true",
        help="open the third sealed split. Allowed once, after the third round of fixes.",
    )
    args = parser.parse_args(argv)

    opens_once = args.split in OPENS_ONCE
    suffix = ""
    conditions = [c for c in args.conditions.split(",") if c]
    if conditions:
        suffix += "-" + "+".join(conditions)
    if args.limit:
        suffix += f"-first{args.limit}"
    run_id = f"{args.split}-{args.variant}-p{args.pass_number}{suffix}"

    if opens_once:
        flag = f"--confirm-{args.split}-once"
        lock = {
            "heldout": HELDOUT_LOCK,
            "sealed": SEALED_LOCK,
            "sealed2": SEALED2_LOCK,
            "sealed3": SEALED3_LOCK,
        }[args.split]
        confirmed = getattr(args, f"confirm_{args.split}_once")
        if not confirmed:
            print(f"The {args.split} split is sealed. Add {flag} to open it, once.")
            return 2
        if lock.exists() and lock.read_text(encoding="utf-8").strip() != run_id:
            print(f"The {args.split} split has already been run ({lock.read_text().strip()}).")
            return 2
        if args.limit or conditions or args.pass_number != 1:
            print(f"The {args.split} run is one full pass: no --limit, --conditions or --pass.")
            return 2
        RUNS.mkdir(parents=True, exist_ok=True)
        lock.write_text(run_id, encoding="utf-8")

    suite = load_suite(args.split, unseal=opens_once)
    all_items = suite.items
    items = [i for i in all_items if not conditions or i.condition in conditions]
    if args.limit:
        items = items[: args.limit]
    out_dir = RUNS / run_id
    if args.fresh and not opens_once:
        shutil.rmtree(out_dir, ignore_errors=True)

    work_dir = SCRATCH / run_id
    env = VARIANTS[args.variant]
    settings = Settings(_env_file=None, CITETALLY_DATA_DIR=str(work_dir), **env)  # type: ignore[arg-type]
    facts = suite.facts
    services = real_services(settings)
    services.today = facts.as_of
    meta = provenance(settings, args.variant, run_id, args.split, suite.golden_file)
    run(
        items=items, history_items=all_items, facts=facts, settings=settings, services=services,
        work_dir=work_dir, out_dir=out_dir, meta=meta,
    )  # fmt: skip
    print(f"Run saved in {out_dir.relative_to(ROOT)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
