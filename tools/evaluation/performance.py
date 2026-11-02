"""Time per page by condition, from the runs already saved: `eval/reports/performance.md`.

Reads only timing and page counts from `eval/runs/*/records.jsonl` (no document content, no golden
file). Each document's seconds are the whole path from upload to the review queue, so they include
reading, the model call and the checks. The numbers are for one machine with the local model and
Tesseract, and the machine was not dedicated to them.

    .\\.venv\\Scripts\\python.exe -m tools.evaluation.performance
"""

from __future__ import annotations

import json
import platform
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "eval" / "runs"
OUT = ROOT / "eval" / "reports" / "performance.md"
CONDITIONS = ("clean_pdf", "scan_light", "scan_heavy", "phone_photo")
SOURCES = {
    "development, baseline, 2 passes": ["tuned-baseline-p1", "tuned-baseline-p2"],
    "held-out, baseline, 1 pass": ["heldout-baseline-p1"],
}


def quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


def load(names: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name in names:
        path = RUNS / name / "records.jsonl"
        if path.exists():
            out += [
                json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line
            ]
    return out


def table(records: list[dict[str, Any]]) -> list[str]:
    rows = [
        "| Condition | Documents | Pages | Median s per page | 90th percentile s per page | "
        "Slowest document (s) | Median s: read | Median s: model | Failed |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[record["condition"]].append(record)
        groups["all"].append(record)
    for name in (*CONDITIONS, "all"):
        group = groups.get(name)
        if not group:
            continue
        timed = [r for r in group if r.get("seconds") is not None and r.get("page_count")]
        per_page = [r["seconds"] / r["page_count"] for r in timed]
        read = [r["stage_ms"]["read"] / 1000 for r in group if "read" in r.get("stage_ms", {})]
        model = [
            r["stage_ms"]["extract"] / 1000 for r in group if "extract" in r.get("stage_ms", {})
        ]
        rows.append(
            f"| {name.replace('_', ' ')} | {len(group)}"
            f" | {sum(r.get('page_count') or 0 for r in group)}"
            f" | {statistics.median(per_page):.1f} | {quantile(per_page, 0.9):.1f}"
            f" | {max(r['seconds'] for r in timed):.0f}"
            f" | {statistics.median(read):.1f} | {statistics.median(model):.1f}"
            f" | {sum(r['status'] == 'failed' for r in group)} |"
        )
    return rows


def main() -> int:
    lines = [
        "# Time per page",
        "",
        "Invented documents only. Whole path from upload to the review queue, one document at a "
        "time, on one Windows 11 machine with Tesseract and the local `qwen3:8b` model, "
        f"Python {platform.python_version()}. Made from the saved evaluation runs by "
        "`tools/evaluation/performance.py`; no document was processed again.",
        "",
    ]
    found = False
    for title, names in SOURCES.items():
        records = load(names)
        if not records:
            continue
        found = True
        lines += [f"## {title}", "", *table(records), ""]
    if not found:
        print("No saved runs under eval/runs/.")
        return 2
    lines += [
        "## Reading these",
        "",
        "- Every document in the golden set is one page, so seconds per document and per page are "
        "the same here. Multi-page documents were not timed.",
        "- In every row the median time in the model is larger than the median time reading.",
        "- The machine was not dedicated to these runs, so read the 90th percentile and the "
        "slowest document as typical trouble, not as limits.",
        "- The slowest documents are heavy scans. The failed ones (two scans in both development "
        "passes, one in the held-out run) all failed at the model step with \"The model's answer "
        'could not be used, even after a second try"; the model is asked twice, so these cost '
        "about twice a normal answer.",
    ]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
