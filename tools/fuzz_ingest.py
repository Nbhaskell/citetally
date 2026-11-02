"""Fuzz the whole intake path with damaged files and report what happened.

Each case takes one of the invented demo files, damages it (flipped, deleted, inserted, repeated,
zeroed or truncated bytes, or a splice with another file), and puts it through `ingest` and then
`pipeline.process` with the real Tesseract and a fake model. A case passes when it ends in a
known status, on time, without an exception escaping and without writing outside the data folder.

Only counts and plain failure reasons are kept: never file content. Same seed, same cases.

    .\\.venv\\Scripts\\python.exe -m tools.fuzz_ingest --cases 300 --seed 1
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from citetally import db, ingest, pipeline
from citetally.config import Settings
from citetally.models import DocumentStatus
from citetally.providers import FakeProvider
from citetally.reading.ocr import TesseractOcr, find_tesseract

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "data" / "synthetic" / "docs"
REPORT = ROOT / "eval" / "reports" / "fuzz_ingest.json"
SLOW_S = 120.0
MAX_BYTES = 6 * 1024 * 1024

REPLY: dict[str, Any] = {
    "entry_type": "invoice",
    "vendor_name": "Fuzz Vendor",
    "invoice_number": "F-1",
    "entry_date": "2026-03-14",
    "currency": "$",
    "lines": [{"description": "Item", "quantity": "1", "unit_price": "$1.00", "amount": "$1.00"}],
    "total": "$1.00",
}
ENDS = {DocumentStatus.NEEDS_REVIEW, DocumentStatus.FAILED, DocumentStatus.DUPLICATE}


def mutate(data: bytes, other: bytes, rng: random.Random) -> tuple[bytes, str]:
    out = bytearray(data)
    kind = rng.choice(
        ["flip", "delete", "insert", "truncate", "repeat", "zero", "splice", "header", "tail"]
    )
    for _ in range(rng.randrange(1, 12) if kind in {"flip", "delete", "insert"} else 1):
        at = rng.randrange(max(len(out), 1))
        match kind:
            case "flip":
                if out:
                    out[at] = rng.randrange(256)
            case "delete":
                del out[at : at + rng.randrange(1, 4096)]
            case "insert":
                out[at:at] = bytes(rng.randrange(256) for _ in range(rng.randrange(1, 256)))
            case "truncate":
                del out[max(rng.randrange(len(out)), 8) :]
            case "repeat":
                chunk = bytes(out[at : at + rng.randrange(64, 8192)])
                out[at:at] = chunk * rng.randrange(2, 200)
            case "zero":
                out[at : at + rng.randrange(1, 8192)] = bytes(min(8192, len(out) - at))
            case "splice":
                cut = rng.randrange(len(other))
                out = bytearray(out[:at] + other[cut : cut + rng.randrange(256, 65536)])
            case "header":
                out = bytearray(out[: rng.randrange(4, 64)])
            case _:  # tail: junk after the end
                out += bytes(rng.randrange(256) for _ in range(rng.randrange(1, 4096)))
    return bytes(out[:MAX_BYTES]), kind


def snapshot(folder: Path) -> set[str]:
    return {str(p.relative_to(folder)) for p in folder.rglob("*")} if folder.exists() else set()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--cases", type=int, default=100)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--out", type=Path, default=REPORT)
    args = parser.parse_args(argv)

    exe = find_tesseract("")
    if exe is None or not DOCS.exists():
        print("Needs Tesseract and data/synthetic/docs (run tools.synthetic.build).")
        return 2
    rng = random.Random(args.seed)
    files = sorted(DOCS.iterdir())
    work = Path(tempfile.mkdtemp(prefix="citetally-fuzz-"))
    settings = Settings(_env_file=None, CITETALLY_DATA_DIR=str(work / "data"))
    conn = db.connect(str(work / "fuzz.db"))
    db.migrate(conn)
    ocr = TesseractOcr(exe)

    outcomes: collections.Counter[str] = collections.Counter()
    reasons: collections.Counter[str] = collections.Counter()
    by_mutation: collections.Counter[str] = collections.Counter()
    problems: list[dict[str, Any]] = []
    slowest = 0.0
    slowest_case = ""
    try:
        for number in range(args.cases):
            source, other = rng.choice(files), rng.choice(files)
            data, kind = mutate(source.read_bytes(), other.read_bytes(), rng)
            name = f"fuzz{number}{source.suffix}"
            services = pipeline.Services(settings, ocr, FakeProvider([REPLY] * 4), isolate=True)
            started = time.monotonic()
            note: str | None = None
            try:
                result = ingest.ingest(conn, data, name, settings=settings)
                document = result.document
                if result.outcome not in {"failed", "duplicate"}:
                    document = pipeline.process(conn, document.id, services)
                outcome = document.status.value
                reason = document.failure_message or ""
                if document.status not in ENDS:
                    note = f"ended in {outcome}"
            except ingest.IngestRejected as refused:  # a type it cannot recognise: refused, no row
                outcome, reason = "rejected", str(refused)
            except Exception as error:
                outcome, reason, note = "failed", "", f"escaped {type(error).__name__}"
            seconds = time.monotonic() - started
            if seconds > slowest:
                slowest, slowest_case = seconds, f"{kind}:{source.suffix}"
            if seconds > SLOW_S:
                note = (note or "") + f" slow {seconds:.0f}s"
            by_mutation[f"{kind}:{source.suffix}"] += 1
            outcomes[outcome] += 1
            if reason:
                reasons[reason] += 1
            if note:
                problems.append(
                    {"case": number, "mutation": kind, "type": source.suffix, "note": note}
                )
            if number % 25 == 24:
                print(f"{number + 1}/{args.cases} done, slowest so far {slowest:.1f}s", flush=True)
        stray = [p for p in snapshot(work) if not (p.startswith("data") or p.startswith("fuzz.db"))]
    finally:
        conn.close()
        shutil.rmtree(work, ignore_errors=True)

    report = {
        "seed": args.seed,
        "cases": args.cases,
        "outcomes": dict(outcomes),
        "failure_reasons": dict(reasons.most_common()),
        "cases_by_mutation": dict(sorted(by_mutation.items())),
        "slowest_seconds": round(slowest, 1),
        "slowest_case": slowest_case,
        "problems": problems,
        "files_outside_data_folder": stray,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("outcomes", "slowest_seconds")}))
    print(f"{len(problems)} problem case(s); {len(stray)} stray file(s). Report: {args.out}")
    return 1 if problems or stray else 0


if __name__ == "__main__":
    sys.exit(main())
