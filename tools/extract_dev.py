"""First measurement of extraction and grounding on the development split (Phase 4 acceptance).

Runs the real pipeline (Tesseract, the local model) on every development document in a scratch
data folder, then scores what the model copied against what is printed in the golden record, by
condition. Failed documents count as wrong, not as missing from the table. The held-out split is
never loaded (`load_golden` refuses it). Numbers from here are for tuning the prompt; the held-out
set is run once, in Phase 8, after they are frozen.

    python -m tools.extract_dev [--limit N] [--fresh]

Per-document results are kept in data/extract_dev/results.jsonl so an interrupted run resumes.
The report is written to eval/reports/extraction_dev_<prompt version>.json.
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from citetally import db, ingest, pipeline
from citetally import repository as repo
from citetally.config import Settings
from citetally.extract import PROMPT_VERSION
from citetally.providers import build_provider
from citetally.reading.ocr import TesseractOcr, find_tesseract
from tools.synthetic.golden import Item, load_golden

WORK = Path("data/extract_dev")
REPORT = Path(f"eval/reports/extraction_dev_{PROMPT_VERSION}.json")
CONDITIONS = ("clean_pdf", "scan_light", "scan_heavy", "phone_photo")
# `currency` is scored apart: some templates never print the symbol the golden record lists.
HEADER = (
    "vendor_name", "invoice_number", "entry_date", "due_date", "po_number",
    "subtotal", "tax_total", "shipping", "discount", "total",
)  # fmt: skip
LINE_FIELDS = ("description", "quantity", "unit_price", "amount")


def norm(text: object) -> str | None:
    return " ".join(text.split()) if isinstance(text, str) and text.strip() else None


# ---- scoring (pure) ----------------------------------------------------------------------------


def score_header(fields: dict[str, Any] | None, printed: dict[str, str]) -> dict[str, str]:
    """Each header field: right, wrong, missing (printed but not returned) or invented."""
    result: dict[str, str] = {}
    for key in (*HEADER, "currency"):
        said = norm((fields or {}).get(key))
        truth = norm(printed.get(key))
        if truth is not None:
            result[key] = "missing" if said is None else "right" if said == truth else "wrong"
        elif said is not None:
            result[key] = "invented"
    return result


def score_lines(lines: list[dict[str, Any]] | None, truth: list[dict[str, str]]) -> tuple[int, int]:
    """(truth lines fully right, predicted lines). A predicted line is used at most once."""
    predicted = [{k: norm(line.get(k)) for k in LINE_FIELDS} for line in lines or []]
    wanted = [{k: norm(line.get(k)) for k in LINE_FIELDS} for line in truth]
    unused = list(range(len(predicted)))
    right = 0
    for line in wanted:
        match = next((i for i in unused if predicted[i] == line), None)
        if match is not None:
            unused.remove(match)
            right += 1
    return right, len(predicted)


def score_record(record: dict[str, Any], item: Item) -> dict[str, Any]:
    fields = record.get("fields")
    header = score_header(fields, item.truth.printed)
    right, predicted = score_lines(
        (fields or {}).get("lines"), [line.printed for line in item.truth.lines]
    )
    printed = item.truth.printed
    grounding = {"correct": 0, "correct_found": 0, "wrong": 0, "wrong_found": 0}
    for row in record.get("evidence", []):
        if row["line"] or row["field"] not in HEADER:
            continue
        kind = (
            "correct" if norm(row["printed_text"]) == norm(printed.get(row["field"])) else "wrong"
        )
        grounding[kind] += 1
        grounding[f"{kind}_found"] += int(row["found"])
    found = [row["found"] for row in record.get("evidence", [])]
    return {
        "header": header,
        "lines_right": right,
        "lines_truth": len(item.truth.lines),
        "lines_predicted": predicted,
        "all_lines": right == len(item.truth.lines) == predicted,
        "all_header": all(v == "right" for k, v in header.items() if k != "currency")
        and not any(v == "invented" for k, v in header.items() if k != "currency"),
        "grounding": grounding,
        "values_found": sum(1 for f in found if f),
        "values": len(found),
    }


def rate(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def summarise(rows: Iterable[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    """Pool (record, score) pairs into the numbers the report shows."""
    rows = list(rows)
    counts: Counter[str] = Counter()
    per_field: dict[str, Counter[str]] = defaultdict(Counter)
    for record, score in rows:
        counts["documents"] += 1
        counts["failed"] += record["status"] == "failed"
        counts["needs_review"] += record["status"] == "needs_review"
        counts["all_header"] += score["all_header"]
        counts["all_lines"] += score["all_lines"]
        counts["all_right"] += score["all_header"] and score["all_lines"]
        counts["lines_right"] += score["lines_right"]
        counts["lines_truth"] += score["lines_truth"]
        counts["lines_predicted"] += score["lines_predicted"]
        counts["values"] += score["values"]
        counts["values_found"] += score["values_found"]
        for key in ("correct", "correct_found", "wrong", "wrong_found"):
            counts[f"g_{key}"] += score["grounding"][key]
        for key, verdict in score["header"].items():
            per_field[key][verdict] += 1
    right = sum(c["right"] for k, c in per_field.items() if k != "currency")
    printed = sum(
        c["right"] + c["wrong"] + c["missing"] for k, c in per_field.items() if k != "currency"
    )
    seconds = [r["seconds"] for r, _ in rows if r.get("seconds") is not None]
    return {
        "documents": counts["documents"],
        "failed": counts["failed"],
        "header_field_accuracy": rate(right, printed),
        "header_values_invented": sum(
            c["invented"] for k, c in per_field.items() if k != "currency"
        ),
        "header_documents_all_right": rate(counts["all_header"], counts["documents"]),
        "line_recall": rate(counts["lines_right"], counts["lines_truth"]),
        "line_precision": rate(counts["lines_right"], counts["lines_predicted"]),
        "line_documents_all_right": rate(counts["all_lines"], counts["documents"]),
        "documents_fully_right": rate(counts["all_right"], counts["documents"]),
        "grounding_coverage": rate(counts["values_found"], counts["values"]),
        "correct_header_values_found": rate(counts["g_correct_found"], counts["g_correct"]),
        "wrong_header_values_found": rate(counts["g_wrong_found"], counts["g_wrong"]),
        "wrong_header_values": counts["g_wrong"],
        "by_field": {k: dict(v) for k, v in sorted(per_field.items())},
        "seconds_per_document_median": round(statistics.median(seconds), 1) if seconds else None,
    }


def render(report: dict[str, Any]) -> str:
    def pct(value: float | None) -> str:
        return "   -  " if value is None else f"{value * 100:5.1f}%"

    head = (
        f"{'':12}{'docs':>5}{'failed':>7}{'header':>8}{'all-hdr':>8}{'ln rec':>8}{'ln prec':>8}"
        f"{'all ok':>8}{'ground':>8}{'wrong+found':>12}{'s/doc':>7}"
    )
    out = [head]
    for name in (*CONDITIONS, "all"):
        s = report["by_condition"].get(name)
        if not s:
            continue
        out.append(
            f"{name:12}{s['documents']:>5}{s['failed']:>7}{pct(s['header_field_accuracy']):>8}"
            f"{pct(s['header_documents_all_right']):>8}{pct(s['line_recall']):>8}"
            f"{pct(s['line_precision']):>8}{pct(s['documents_fully_right']):>8}"
            f"{pct(s['grounding_coverage']):>8}{pct(s['wrong_header_values_found']):>12}"
            f"{s['seconds_per_document_median'] or 0:>7}"
        )
    return "\n".join(out)


# ---- running -----------------------------------------------------------------------------------


def run_one(
    conn: Any, settings: Settings, services: pipeline.Services, item: Item
) -> dict[str, Any]:
    started = time.monotonic()
    result = ingest.ingest(
        conn, Path(item.file).read_bytes(), Path(item.file).name, settings=settings
    )
    doc_id = result.document.duplicate_of if result.outcome == "duplicate" else result.document.id
    document = result.document
    if result.outcome != "failed" and doc_id is not None:
        document = pipeline.process(conn, doc_id, services)
    seconds = round(time.monotonic() - started, 1)
    record: dict[str, Any] = {
        "id": item.id,
        "condition": item.condition,
        "status": document.status.value,
        "failure_stage": document.failure_stage.value if document.failure_stage else None,
        "seconds": seconds,
        "fields": None,
        "evidence": [],
    }
    entry = repo.get_entry_for_document(conn, document.id)
    extraction = repo.latest_extraction(conn, document.id)
    if extraction is not None:
        record["fields"] = json.loads(extraction.fields)
    if entry is not None:
        lines = repo.list_lines(conn, entry.id)
        line_ids = {line.id for line in lines}
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
        record["vendor_match"] = (
            entry.vendor_match_method.value if entry.vendor_match_method else None
        )
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--limit", type=int, default=0, help="only the first N documents")
    parser.add_argument(
        "--fresh", action="store_true", help="delete earlier results and start over"
    )
    args = parser.parse_args(argv)

    items = load_golden(split="tuned")
    if args.limit:
        items = items[: args.limit]
    if args.fresh:  # the database too: a document it already holds would be skipped as a duplicate
        shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)
    results_file = WORK / "results.jsonl"
    done: dict[str, dict[str, Any]] = {}
    if results_file.exists():
        for line in results_file.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            done[record["id"]] = record

    settings = Settings(_env_file=None, CITETALLY_DATA_DIR=str(WORK))
    conn = db.connect(str(WORK / "run.db"))
    db.migrate(conn)
    db.seed_categories(conn)
    services = pipeline.Services(
        settings=settings,
        ocr=TesseractOcr(find_tesseract(settings.tesseract_cmd) or ""),
        provider=build_provider(settings),
    )
    todo = [item for item in items if item.id not in done]
    print(f"{len(items)} development documents, {len(done)} already done", flush=True)
    with results_file.open("a", encoding="utf-8") as sink:
        for number, item in enumerate(todo, start=1):
            record = run_one(conn, settings, services, item)
            sink.write(json.dumps(record) + "\n")
            sink.flush()
            done[item.id] = record
            print(
                f"[{number}/{len(todo)}] {item.id} {item.condition} {record['status']} "
                f"{record['seconds']}s",
                flush=True,
            )

    by_id = {item.id: item for item in items}
    scored = [(done[i], score_record(done[i], by_id[i])) for i in by_id if i in done]
    report: dict[str, Any] = {
        "split": "tuned",
        "prompt_version": PROMPT_VERSION,
        "model": settings.text_model,
        "by_condition": {
            name: summarise(pair for pair in scored if pair[0]["condition"] == name)
            for name in CONDITIONS
        },
    }
    report["by_condition"]["all"] = summarise(scored)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
