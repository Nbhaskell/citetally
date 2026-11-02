"""Scoring: saved run records against the golden truth. Pure: it calls no model and no program.

A run record (see `run.py`) is what the pipeline stored for one document. Scoring it again with a
different metric costs nothing, which is the point of keeping the runner and the scorer apart.

What is counted, and what a miss means:
- Header fields are compared as printed (what the model copied against what the page shows).
  A document that failed counts every printed field as wrong, not as absent from the table.
- Money is compared after the code has parsed it: stored minor units against the truth's.
- A planted problem is caught when every check the golden record expects for it fails.
- A false alarm is a check failing on a clean document (one with no planted problem).
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from tools.evaluation.stats import wilson
from tools.extract_dev import HEADER, norm, score_header, score_lines
from tools.synthetic.golden import Item

CONDITIONS = ("clean_pdf", "scan_light", "scan_heavy", "phone_photo")
MONEY = ("subtotal", "tax_total", "shipping", "discount", "total")
BLOCKING = (
    "REQUIRED_FIELDS", "VALUE_IN_DOCUMENT", "LINE_MATH", "SUBTOTAL_MATCH", "TAX_MATCH",
    "TOTAL_MATCH", "DUPLICATE_SUSPECT", "UNKNOWN_VENDOR",
)  # fmt: skip
NON_BLOCKING = (
    "AMOUNT_OUTLIER", "DATE_SANITY", "CURRENCY_CHECK", "LOW_READ_QUALITY", "AMBIGUOUS_FORMAT",
    "SUSPICIOUS_TEXT",
)  # fmt: skip
CHECKS = BLOCKING + NON_BLOCKING
Pair = tuple[dict[str, Any], dict[str, Any]]


def _minor_verdict(said: int | None, truth: int | None) -> str | None:
    if truth is not None:
        return "missing" if said is None else "right" if said == truth else "wrong"
    return "invented" if said is not None else None


CORE_LINE = ("description", "amount")


def _core_lines(lines: Sequence[dict[str, Any]] | None) -> list[dict[str, str | None]]:
    return [{k: norm(line.get(k)) for k in CORE_LINE} for line in lines or []]


def score_core_lines(
    lines: Sequence[dict[str, Any]] | None, truth: Sequence[dict[str, Any]]
) -> tuple[int, int]:
    """Like `score_lines` but a line counts when its description and amount are right, whatever
    the quantity and unit price say. A companion to the strict measure, added after the first
    results were read (see the report); never a headline."""
    predicted = _core_lines(lines)
    unused = list(range(len(predicted)))
    right = 0
    for wanted in _core_lines(truth):
        match = next((i for i in unused if predicted[i] == wanted), None)
        if match is not None:
            unused.remove(match)
            right += 1
    return right, len(predicted)


def score_record(record: dict[str, Any], item: Item) -> dict[str, Any]:
    """Everything the report needs from one document, as plain numbers and codes."""
    extraction = record.get("extraction") or {}
    fields = extraction.get("fields")
    entry = record.get("entry") or {}
    header = score_header(fields, item.truth.printed)
    right_lines, predicted_lines = score_lines(
        (fields or {}).get("lines"), [line.printed for line in item.truth.lines]
    )
    truth_lines = len(item.truth.lines)
    core_right, core_predicted = score_core_lines(
        (fields or {}).get("lines"), [line.printed for line in item.truth.lines]
    )

    money: dict[str, str] = {}
    for name in MONEY:
        verdict = _minor_verdict(entry.get(f"{name}_minor"), getattr(item.truth, f"{name}_minor"))
        if verdict:
            money[name] = verdict

    printed_header = {k: v for k, v in header.items() if k != "currency"}
    printed_count = sum(v in {"right", "wrong", "missing"} for v in printed_header.values())
    right_count = sum(v == "right" for v in printed_header.values())

    failed = sorted(c["code"] for c in record.get("checks", []) if not c["passed"])
    excluded = bool(record.get("context_missing"))  # its original is not in this run
    planted = [] if excluded else [p.kind for p in item.planted]
    expected = [] if excluded else list(item.expected_checks)
    vendor_right = entry.get("vendor_golden_id") == (
        None if item.vendor_id.startswith("X") else item.vendor_id
    )
    evidence = record.get("evidence", [])
    return {
        "id": record["id"],
        "condition": item.condition,
        "family": item.template_family,
        "status": record["status"],
        "header": header,
        "header_right": right_count,
        "header_printed": printed_count,
        "header_invented": sum(v == "invented" for v in printed_header.values()),
        "money": money,
        "lines_right": right_lines,
        "lines_truth": truth_lines,
        "lines_predicted": predicted_lines,
        "lines_core_right": core_right,
        "lines_core_predicted": core_predicted,
        "line_f1": 1.0
        if truth_lines == predicted_lines == 0
        else 2 * right_lines / max(truth_lines + predicted_lines, 1),
        "date_right": entry.get("entry_date") == item.truth.entry_date,
        "currency_right": entry.get("currency") == item.truth.currency,
        "type_right": entry.get("entry_type") == item.truth.entry_type,
        "vendor_right": vendor_right,
        "values": len(evidence),
        "values_found": sum(1 for e in evidence if e["found"]),
        "planted": planted,
        "expected": expected,
        "failed_checks": failed,
        "caught": bool(planted) and all(code in failed for code in expected),
        "caught_codes": [code for code in expected if code in failed],
        "collateral": [code for code in failed if code not in expected] if planted else [],
        "excluded": excluded,
        "clean_alarm": (not planted) and not excluded and any(code in BLOCKING for code in failed),
        "clean_alarm_ungrounded": (not planted)
        and not excluded
        and any(code in BLOCKING and code != "VALUE_IN_DOCUMENT" for code in failed),
        "pages": record.get("page_count") or 0,
        "seconds": record.get("seconds"),
        "input_tokens": extraction.get("input_tokens"),
        "output_tokens": extraction.get("output_tokens"),
    }


def _rate(successes: int, total: int) -> dict[str, Any]:
    """A proportion with the numbers it came from and its 95% interval."""
    interval = wilson(successes, total)
    return {
        "n": total,
        "k": successes,
        "rate": round(successes / total, 4) if total else None,
        "low": round(interval[0], 4) if interval else None,
        "high": round(interval[1], 4) if interval else None,
    }


def summarise(scores: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """The metrics of TRD section 12 for a group of scored documents."""
    header: dict[str, Counter[str]] = defaultdict(Counter)
    money: dict[str, Counter[str]] = defaultdict(Counter)
    total = Counter[str]()
    caught_by_code: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    caught_by_kind: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    alarms: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    collateral = Counter[str]()
    for s in scores:
        total["documents"] += 1
        total["failed"] += s["status"] == "failed"
        for name, verdict in s["header"].items():
            header[name][verdict] += 1
        for name, verdict in s["money"].items():
            money[name][verdict] += 1
        for key in ("header_right", "header_printed", "header_invented", "lines_right",
                    "lines_truth", "lines_predicted", "lines_core_right", "lines_core_predicted",
                    "values", "values_found"):  # fmt: skip
            total[key] += s[key]
        for key in ("date_right", "currency_right", "type_right", "vendor_right"):
            total[key] += bool(s[key])
        if s["planted"]:
            kind = s["planted"][0]
            caught_by_kind[kind][1] += 1
            caught_by_kind[kind][0] += s["caught"]
            for code in s["expected"]:
                caught_by_code[code][1] += 1
                caught_by_code[code][0] += code in s["caught_codes"]
            total["planted_docs"] += 1
            total["planted_caught"] += s["caught"]
            for code in s["collateral"]:
                collateral[code] += 1
        elif not s["excluded"]:
            total["clean_docs"] += 1
            total["clean_alarm"] += s["clean_alarm"]
            total["clean_alarm_ungrounded"] += s["clean_alarm_ungrounded"]
            for code in CHECKS:
                alarms[code][1] += 1
                alarms[code][0] += code in s["failed_checks"]

    right = sum(c["right"] for c in header.values()) - header.get("currency", Counter())["right"]
    counted = sum(
        c["right"] + c["wrong"] + c["missing"] for k, c in header.items() if k != "currency"
    )
    per_page = [
        s["seconds"] / s["pages"] for s in scores if s["seconds"] is not None and s["pages"]
    ]
    in_tokens = [s["input_tokens"] for s in scores if s["input_tokens"] is not None]
    out_tokens = [s["output_tokens"] for s in scores if s["output_tokens"] is not None]
    money_right = sum(c["right"] for c in money.values())
    money_counted = sum(c["right"] + c["wrong"] + c["missing"] for c in money.values())
    precision = (
        total["lines_right"] / total["lines_predicted"] if total["lines_predicted"] else None
    )
    recall = total["lines_right"] / total["lines_truth"] if total["lines_truth"] else None
    if precision is None or recall is None:
        f1 = None
    else:
        f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    core_precision = (
        total["lines_core_right"] / total["lines_core_predicted"]
        if total["lines_core_predicted"]
        else None
    )
    core_recall = total["lines_core_right"] / total["lines_truth"] if total["lines_truth"] else None
    if core_precision is None or core_recall is None:
        core_f1 = None
    else:
        core_f1 = (
            0.0
            if core_precision + core_recall == 0
            else 2 * core_precision * core_recall / (core_precision + core_recall)
        )
    return {
        "documents": total["documents"],
        "failed": total["failed"],
        "header_field_exact": _rate(right, counted),
        "header_invented": total["header_invented"],
        "header_by_field": {
            k: {
                **_rate(c["right"], c["right"] + c["wrong"] + c["missing"]),
                "wrong": c["wrong"],
                "missing": c["missing"],
                "invented": c["invented"],
            }
            for k, c in sorted(header.items())
        },
        "money_exact": _rate(money_right, money_counted),
        "money_by_field": {
            k: _rate(c["right"], c["right"] + c["wrong"] + c["missing"])
            for k, c in sorted(money.items())
        },
        "line_precision": None if precision is None else round(precision, 4),
        "line_recall": None if recall is None else round(recall, 4),
        "line_f1": None if f1 is None else round(f1, 4),
        "line_core_f1": None if core_f1 is None else round(core_f1, 4),
        "normalised": {
            key: _rate(total[key], total["documents"])
            for key in ("date_right", "currency_right", "type_right", "vendor_right")
        },
        "planted_recall": _rate(total["planted_caught"], total["planted_docs"]),
        "planted_recall_by_code": {k: _rate(*v) for k, v in sorted(caught_by_code.items())},
        "planted_recall_by_kind": {k: _rate(*v) for k, v in sorted(caught_by_kind.items())},
        "clean_documents": total["clean_docs"],
        "clean_any_blocking_alarm": _rate(total["clean_alarm"], total["clean_docs"]),
        "clean_alarm_without_value_in_document": _rate(
            total["clean_alarm_ungrounded"], total["clean_docs"]
        ),
        "false_alarm_by_check": {k: _rate(*v) for k, v in alarms.items()},
        "collateral_alarms_on_planted": dict(sorted(collateral.items())),
        "values_found": _rate(total["values_found"], total["values"]),
        "seconds_per_page_median": round(statistics.median(per_page), 1) if per_page else None,
        "input_tokens_mean": round(statistics.fmean(in_tokens)) if in_tokens else None,
        "output_tokens_mean": round(statistics.fmean(out_tokens)) if out_tokens else None,
    }


def group(
    scores: Iterable[dict[str, Any]], key: Callable[[dict[str, Any]], str]
) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in scores:
        groups[key(s)].append(s)
    return dict(groups)


def per_document(scores: Iterable[dict[str, Any]]) -> dict[str, dict[str, float | None]]:
    """The headline measures, one number per document (None where the measure does not apply).
    These are what two settings are compared on, document by document."""
    out: dict[str, dict[str, float | None]] = {}
    for s in scores:
        out[s["id"]] = {
            "header_accuracy": (
                s["header_right"] / s["header_printed"] if s["header_printed"] else None
            ),
            "line_f1": s["line_f1"],
            "planted_caught": float(s["caught"]) if s["planted"] else None,
            "clean_alarm": None if s["planted"] or s["excluded"] else float(s["clean_alarm"]),
        }
    return out


HEADLINES = ("header_accuracy", "line_f1", "planted_caught", "clean_alarm")


__all__ = [
    "BLOCKING", "CHECKS", "CONDITIONS", "HEADER", "HEADLINES", "MONEY", "NON_BLOCKING",
    "group", "norm", "per_document", "score_record", "summarise",
]  # fmt: skip
