"""Does showing the model the page picture help on the hardest documents? (Phase 4, task 6)

For each development scan_heavy and phone_photo document the page is read once, then extracted
twice with the same local vision model: from the OCR text alone, and from the OCR text plus the
page picture. Comparing those two separates "the picture helps" from "a different model". Both are
also set beside the text model's earlier run (eval/reports/extraction_dev_extract-v3.json).

The rule below was written before any results were seen.

    ENABLE only if, on scan_heavy or phone_photo, header-field accuracy with the picture is at least
    10 percentage points above BOTH text-only runs, failed documents and invented header values
    are no higher than in either, and the median time per document is at most 60 seconds.

Values are still grounded against the OCR words, so a value the model reads from the picture but
OCR missed is reported as not found on the page. Development split only.

    python -m tools.vision_experiment [--limit N] [--fresh]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from citetally import db, ingest, pipeline
from citetally import repository as repo
from citetally.config import Settings
from citetally.models import DocumentStatus as S
from citetally.models import ExtractMode, Stage
from citetally.providers import VISION_CONTEXT_TOKENS, OllamaProvider
from citetally.reading.ocr import TesseractOcr, find_tesseract
from tools.extract_dev import build_record, summarise
from tools.extract_dev import score_record as score
from tools.synthetic.golden import load_golden

WORK = Path("data/vision_dev")
REPORT = Path("eval/reports/vision_dev.json")
BASELINE = Path("eval/reports/extraction_dev_extract-v3.json")
VISION_MODEL = "qwen3-vl:8b-instruct"  # the thinking variant (qwen3-vl:8b) timed out, see D-048
CONDITIONS = ("scan_heavy", "phone_photo")
MIN_GAIN = 0.10
MAX_SECONDS = 60.0
CONFIGS = ("vl_text_only", "vl_text_and_image")


def verdict(report: dict[str, Any]) -> dict[str, Any]:
    """Apply the rule above to the summaries in `report["configs"]`."""
    configs = report["configs"]
    reasons: list[str] = []
    gains: dict[str, float] = {}
    for condition in CONDITIONS:
        image = configs["vl_text_and_image"][condition]
        others = [configs[name][condition] for name in ("text_model_text_only", "vl_text_only")]
        gain = min(
            (image["header_field_accuracy"] or 0) - (other["header_field_accuracy"] or 0)
            for other in others
        )
        gains[condition] = round(gain, 4)
        worse = any(
            image["failed"] > o["failed"]
            or image["header_values_invented"] > o["header_values_invented"]
            for o in others
        )
        slow = (image["seconds_per_document_median"] or 0) > MAX_SECONDS
        if gain >= MIN_GAIN and not worse and not slow:
            return {"enable": True, "gains": gains, "reason": f"{condition} clears the rule"}
        reasons.append(
            f"{condition}: gain {gain * 100:+.1f} points"
            + (", more failures or invented values" if worse else "")
            + (", too slow" if slow else "")
        )
    return {"enable": False, "gains": gains, "reason": "; ".join(reasons)}


def render(report: dict[str, Any]) -> str:
    def pct(value: float | None) -> str:
        return "  -  " if value is None else f"{value * 100:5.1f}"

    out = [
        f"{'':34}{'docs':>5}{'fail':>5}{'hdr':>7}{'all-hdr':>8}{'ln rec':>7}{'ground':>7}"
        f"{'s/doc':>7}"
    ]
    for name, by_condition in report["configs"].items():
        for condition in CONDITIONS:
            s = by_condition[condition]
            out.append(
                f"{name + ' / ' + condition:34}{s['documents']:>5}{s['failed']:>5}"
                f"{pct(s['header_field_accuracy']):>7}{pct(s['header_documents_all_right']):>8}"
                f"{pct(s['line_recall']):>7}{pct(s['grounding_coverage']):>7}"
                f"{s['seconds_per_document_median'] or 0:>7}"
            )
    out.append(
        f"verdict: {'ENABLE' if report['verdict']['enable'] else 'do not enable'}"
        f" ({report['verdict']['reason']})"
    )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare text-only with text-and-image extraction")
    parser.add_argument("--limit", type=int, default=0, help="only the first N documents")
    parser.add_argument("--fresh", action="store_true", help="delete earlier results")
    args = parser.parse_args(argv)

    items = [i for i in load_golden(split="tuned") if i.condition in CONDITIONS]
    if args.limit:
        items = items[: args.limit]
    if args.fresh:
        shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)
    results_file = WORK / "results.jsonl"
    done: dict[str, dict[str, Any]] = {}
    if results_file.exists():
        for line in results_file.read_text(encoding="utf-8").splitlines():
            earlier = json.loads(line)
            done[earlier["id"]] = earlier

    settings = Settings(
        _env_file=None,
        CITETALLY_DATA_DIR=str(WORK),
        CITETALLY_VISION_MODEL=VISION_MODEL,
    )
    conn = db.connect(str(WORK / "run.db"))
    db.migrate(conn)
    db.seed_categories(conn)
    provider = OllamaProvider(
        settings.ollama_url,
        settings.vision_model,
        supports_vision=True,
        context_tokens=VISION_CONTEXT_TOKENS,
    )
    ocr = TesseractOcr(find_tesseract(settings.tesseract_cmd) or "")
    text_only = pipeline.Services(settings=settings, ocr=ocr, provider=provider)
    with_image = pipeline.Services(
        settings=settings, ocr=ocr, provider=provider, extract_mode=ExtractMode.TEXT_AND_IMAGE
    )

    todo = [item for item in items if item.id not in done]
    print(f"{len(items)} documents, {len(done)} already done", flush=True)
    with results_file.open("a", encoding="utf-8") as sink:
        for number, item in enumerate(todo, start=1):
            path = Path(item.file)
            started = time.monotonic()
            result = ingest.ingest(conn, path.read_bytes(), path.name, settings=settings)
            doc_id = (
                result.document.duplicate_of
                if result.outcome == "duplicate"
                else result.document.id
            )
            assert doc_id is not None
            first = pipeline.process(conn, doc_id, text_only)
            read_seconds = round(time.monotonic() - started, 1)
            record: dict[str, Any] = {
                "id": item.id,
                "condition": item.condition,
                "vl_text_only": build_record(conn, first, item, read_seconds),
            }
            if first.status is S.FAILED and first.failure_stage is Stage.READ:
                record["vl_text_and_image"] = record["vl_text_only"]  # nothing was read
            else:
                started = time.monotonic()
                repo.change_status(conn, doc_id, S.READ)  # keep the pages, extract again
                second = pipeline.process(conn, doc_id, with_image)
                record["vl_text_and_image"] = build_record(
                    conn, second, item, round(time.monotonic() - started, 1)
                )
            sink.write(json.dumps(record) + "\n")
            sink.flush()
            done[item.id] = record
            print(
                f"[{number}/{len(todo)}] {item.id} {item.condition}: "
                f"text {record['vl_text_only']['status']} {record['vl_text_only']['seconds']}s, "
                f"image {record['vl_text_and_image']['status']} "
                f"{record['vl_text_and_image']['seconds']}s",
                flush=True,
            )

    by_id = {item.id: item for item in items}
    configs: dict[str, dict[str, Any]] = {}
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))["by_condition"]
    configs["text_model_text_only"] = {c: baseline[c] for c in CONDITIONS}
    for name in CONFIGS:
        configs[name] = {
            condition: summarise(
                (done[i][name], score(done[i][name], by_id[i]))
                for i in by_id
                if i in done and by_id[i].condition == condition
            )
            for condition in CONDITIONS
        }
    report: dict[str, Any] = {
        "split": "tuned",
        "vision_model": settings.vision_model,
        "text_model": "qwen3:8b",
        "configs": configs,
    }
    report["verdict"] = verdict(report)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
