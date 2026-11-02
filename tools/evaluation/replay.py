"""Replay: run the code that comes after the model again, on what a saved run already read.

Grounding, vendor matching and the checks are plain code. When one of them changes, nothing has to
be read again: the pages and the model's answers are in the run's database, so the stages from
grounding onward can be run once more in seconds, and the new results compared with the old,
document by document. Nothing is read from the model or from Tesseract, so the pass-to-pass spread
that separates a real difference from noise does not apply: the same inputs go through different
code, and what matters is which documents changed and in which direction.

    python -m tools.evaluation.replay --base tuned-baseline-p1 --label g1
    python -m tools.evaluation.replay --base dev2-baseline-p1 --label g1

The held-out and sealed splits are refused: a replay is for development.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from citetally import db, pipeline
from citetally import repository as repo
from citetally.config import Settings
from citetally.pipeline import Services
from citetally.providers import FakeProvider
from citetally.reading.ocr import FakeOcr
from tools.evaluation.run import RUNS, SCRATCH, VARIANTS, _git, _known_world, collect, read_records
from tools.evaluation.score import HEADLINES, per_document, score_record, summarise
from tools.evaluation.suites import OPENS_ONCE, load_suite

HEADLINE_NAMES = {
    "header_accuracy": "Header fields exact",
    "line_f1": "Line items F1",
    "planted_caught": "Planted problems caught",
    "clean_alarm": "Clean documents blocked",
}


def replay(base_run: str, label: str) -> tuple[str, list[dict[str, Any]]]:
    """Make a new run `<split>-<label>-p<n>` from `base_run`, with today's code after the model."""
    base_dir = RUNS / base_run
    meta = json.loads((base_dir / "meta.json").read_text(encoding="utf-8"))
    split = meta["split"]
    if split in OPENS_ONCE:
        raise SystemExit(f"A replay is for development: the {split} split is not replayed.")
    old_records = read_records(base_dir / "records.jsonl")
    source = SCRATCH / base_run
    if not (source / "run.db").exists():
        raise SystemExit(f"The saved database of {base_run} is gone ({source}); run it again.")
    pass_number = base_run.split("-p")[-1].split("-")[0]
    new_id = f"{split}-{label}-p{pass_number}"
    target = SCRATCH / new_id
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    for part in source.glob("run.db*"):
        shutil.copy2(part, target / part.name)

    suite = load_suite(split)
    items = {item.id: item for item in suite.items}
    settings = Settings(
        _env_file=None,
        CITETALLY_DATA_DIR=str(target),
        **VARIANTS.get(meta["variant"], {}),  # type: ignore[arg-type]
    )
    services = Services(settings, FakeOcr(), FakeProvider(), isolate=False, today=suite.facts.as_of)
    conn = db.connect(str(target / "run.db"))
    try:
        rows = conn.execute(
            "SELECT id, original_filename, status FROM documents "
            "WHERE original_filename NOT LIKE 'history-%' ORDER BY id"
        ).fetchall()
        by_item = {Path(r["original_filename"]).stem: r["id"] for r in rows}
        # Everything that was waiting for review goes back to just after the model, in the order
        # it was first processed, so a duplicate still sees only the documents before it.
        again = [
            r["id"]
            for r in rows
            if r["status"] == "needs_review" and repo.latest_extraction(conn, r["id"])
        ]
        for document_id in again:
            conn.execute("UPDATE documents SET status = 'extracted' WHERE id = ?", (document_id,))
            # Until its own turn a document must not count as an earlier entry of its vendor.
            conn.execute(
                "UPDATE entries SET vendor_id = NULL WHERE document_id = ?", (document_id,)
            )
        for document_id in again:
            pipeline.process(conn, document_id, services)
        world = _known_world(conn, suite.facts)
        records = []
        for old in old_records.values():
            document = repo.get_document(conn, by_item[old["id"]])
            record = collect(
                conn, document, items[old["id"]], old["seconds"], world,
                context_missing=old["context_missing"],
            )  # fmt: skip
            records.append(record)
    finally:
        conn.close()

    out = RUNS / new_id
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    (out / "records.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8"
    )
    new_meta = {
        **meta,
        "run_id": new_id,
        "variant": label,
        "replay_of": base_run,
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": _git("rev-parse", "HEAD"),
        "tree_changed": bool(_git("status", "--porcelain")),
    }
    (out / "meta.json").write_text(json.dumps(new_meta, indent=1), encoding="utf-8")
    return new_id, records


def compare(
    old_records: Sequence[dict[str, Any]], new_records: Sequence[dict[str, Any]], split: str
) -> str:
    """Old against new on the same documents: the headline numbers and who changed."""
    items = {i.id: i for i in load_suite(split).items}
    old = [score_record(r, items[r["id"]]) for r in old_records]
    new = [score_record(r, items[r["id"]]) for r in new_records]
    a, b = summarise(old), summarise(new)
    rows = [
        ("Header fields exact", a["header_field_exact"]["rate"], b["header_field_exact"]["rate"]),
        ("Money exact", a["money_exact"]["rate"], b["money_exact"]["rate"]),
        ("Line items F1", a["line_f1"], b["line_f1"]),
        ("Planted caught", a["planted_recall"]["rate"], b["planted_recall"]["rate"]),
        ("Clean documents blocked", a["clean_any_blocking_alarm"]["rate"],
         b["clean_any_blocking_alarm"]["rate"]),
        ("Values found on the page", a["values_found"]["rate"], b["values_found"]["rate"]),
    ]  # fmt: skip
    lines = ["| Measure | Before | After | Change |", "|---|---|---|---|"]
    for name, x, y in rows:
        lines.append(f"| {name} | {x * 100:.1f}% | {y * 100:.1f}% | {(y - x) * 100:+.1f} points |")
    before, after = per_document(old), per_document(new)
    lines += ["", "| Per document | Better | Worse | Same |", "|---|---|---|---|"]
    worse: dict[str, list[str]] = {}
    for measure in HEADLINES:
        good = measure != "clean_alarm"
        better = bad = same = 0
        for doc_id, values in before.items():
            x, y = values[measure], after[doc_id][measure]
            if x is None or y is None or abs(x - y) < 1e-9:
                same += 1
            elif (y > x) == good:
                better += 1
            else:
                bad += 1
                worse.setdefault(measure, []).append(doc_id)
        lines.append(f"| {HEADLINE_NAMES[measure]} | {better} | {bad} | {same} |")
    for measure, ids in worse.items():
        lines.append(f"\nWorse on {HEADLINE_NAMES[measure]}: {', '.join(ids)}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--base", required=True, help="the saved run to start from")
    parser.add_argument("--label", help="a short name for this code state")
    parser.add_argument(
        "--against", help="compare with this saved run instead of replaying (same documents only)"
    )
    args = parser.parse_args(argv)
    if args.against:
        old = read_records(RUNS / args.base / "records.jsonl")
        new = read_records(RUNS / args.against / "records.jsonl")
        shared = [k for k in new if k in old]
        meta = json.loads((RUNS / args.against / "meta.json").read_text(encoding="utf-8"))
        print(f"{len(shared)} documents in common.\n")
        print(compare([old[k] for k in shared], [new[k] for k in shared], meta["split"]))
        return 0
    if not args.label:
        parser.error("--label is needed to replay")
    started = time.monotonic()
    old = read_records(RUNS / args.base / "records.jsonl")
    new_id, records = replay(args.base, args.label)
    split = json.loads((RUNS / new_id / "meta.json").read_text(encoding="utf-8"))["split"]
    print(f"Replayed {len(records)} documents as {new_id} in {time.monotonic() - started:.0f} s.\n")
    print(compare(list(old.values()), records, split))
    return 0


if __name__ == "__main__":
    sys.exit(main())
