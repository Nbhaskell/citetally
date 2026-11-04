"""Two sets of saved runs on the same documents, side by side (development splits only).

    python -m tools.compare_runs --old dev2-cur-p1 tuned-curl-p1 tuned-curhp-p1 \
        --new dev2-final_rapid-p1-scan_light+scan_heavy+phone_photo \
              tuned-final_rapid-p1-scan_light+scan_heavy+phone_photo

Only documents in both sets are compared, clean PDFs are left out (they are read from their text
layer, so the OCR does not touch them), and a document counts for one side only as scored by
`tools/evaluation/score.py`. To compare older runs under today's checks, replay them first
(`tools/evaluation/replay.py`). The paired counts say how many documents moved each way, which is
what separates a change from noise at these sizes. Writes `eval/reports/<name>.json` with `--name`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from typing import Any

from tools.evaluation.run import ROOT, RUNS, read_records
from tools.evaluation.score import score_record, summarise
from tools.evaluation.suites import OPENS_ONCE, SPLITS, load_suite

METRICS = (
    "header_field_exact",
    "money_exact",
    "line_f1",
    "planted_recall",
    "clean_any_blocking_alarm",
    "clean_alarm_without_value_in_document",
    "values_found",
)
IGNORED = {"LOW_READ_QUALITY", "SUSPICIOUS_TEXT"}


def _rate(value: Any) -> float | None:
    if isinstance(value, dict):
        value = value.get("rate")
    return None if value is None else round(float(value), 4)


def _load(names: Sequence[str]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for name in names:
        if name.split("-")[0] in OPENS_ONCE:
            raise SystemExit(f"{name}: sealed and held-out runs are not compared here.")
        records.update(read_records(RUNS / name / "records.jsonl"))
    return records


def _low_read(records: dict[str, dict[str, Any]], ids: Sequence[str]) -> dict[str, Any]:
    fired = sum(
        1
        for i in ids
        for c in records[i]["checks"]
        if c["code"] == "LOW_READ_QUALITY" and not c["passed"]
    )
    confidences = sorted(
        p["mean_confidence"]
        for i in ids
        for p in records[i].get("pages") or []
        if p.get("mean_confidence") is not None
    )
    return {
        "fired": fired,
        "median_confidence": confidences[len(confidences) // 2] if confidences else None,
    }


def compare(
    old_names: Sequence[str], new_names: Sequence[str], exclude: Sequence[str] = ()
) -> dict[str, Any]:
    items = {i.id: i for s in SPLITS if s not in OPENS_ONCE for i in load_suite(s).items}
    old, new = _load(old_names), _load(new_names)
    ids = [
        i
        for i in new
        if i in old and i in items and items[i].condition != "clean_pdf" and i not in exclude
    ]
    result: dict[str, Any] = {
        "old": list(old_names),
        "new": list(new_names),
        "excluded": list(exclude),
        "groups": {},
    }
    for label, wanted in (
        ("all", None),
        *((c, c) for c in sorted({items[i].condition for i in ids})),
    ):
        sel = [i for i in ids if wanted is None or items[i].condition == wanted]
        scores_old = {i: score_record(old[i], items[i]) for i in sel}
        scores_new = {i: score_record(new[i], items[i]) for i in sel}
        a, b = summarise(list(scores_old.values())), summarise(list(scores_new.values()))
        paired = Counter[str]()
        for i in sel:
            o, n = scores_old[i], scores_new[i]
            paired["header_better"] += n["header_right"] > o["header_right"]
            paired["header_worse"] += n["header_right"] < o["header_right"]
            paired["lines_better"] += n["lines_right"] > o["lines_right"]
            paired["lines_worse"] += n["lines_right"] < o["lines_right"]
            if not o["planted"]:
                paired["clean"] += 1
                paired["blocked_only_old"] += o["clean_alarm"] and not n["clean_alarm"]
                paired["blocked_only_new"] += n["clean_alarm"] and not o["clean_alarm"]
                paired["blocked_both"] += n["clean_alarm"] and o["clean_alarm"]
        blocking = {}
        for side, scores in (("old", scores_old), ("new", scores_new)):
            counts = Counter(
                code
                for s in scores.values()
                if not s["planted"]
                for code in s["failed_checks"]
                if code not in IGNORED
            )
            blocking[side] = dict(sorted(counts.items()))
        result["groups"][label] = {
            "documents": len(sel),
            "metrics": {m: {"old": _rate(a[m]), "new": _rate(b[m])} for m in METRICS},
            "seconds_per_page_median": {
                "old": a["seconds_per_page_median"],
                "new": b["seconds_per_page_median"],
            },
            "paired": dict(paired),
            "checks_failing_on_clean_documents": blocking,
            "low_read_quality": {"old": _low_read(old, sel), "new": _low_read(new, sel)},
        }
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--old", nargs="+", required=True)
    parser.add_argument("--new", nargs="+", required=True)
    parser.add_argument("--exclude", nargs="*", default=[], help="document ids to leave out")
    parser.add_argument("--name", help="also write eval/reports/<name>.json")
    args = parser.parse_args(argv)
    result = compare(args.old, args.new, args.exclude)
    text = json.dumps(result, indent=1)
    print(text)
    if args.name:
        (ROOT / "eval" / "reports" / f"{args.name}.json").write_text(
            text, encoding="utf-8", newline="\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
