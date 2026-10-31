"""The development-split scoring, on invented records. No model, OCR or documents."""

from typing import Any

import pytest

from tools import extract_dev as dev
from tools.synthetic.golden import load_golden

PRINTED = {"vendor_name": "Acme Co.", "invoice_number": "A-1", "total": "$10.00", "currency": "$"}


def test_header_fields_are_right_wrong_missing_or_invented() -> None:
    said = {"vendor_name": "Acme  Co.", "invoice_number": "A-2", "total": None, "due_date": "5/1"}
    assert dev.score_header(said, PRINTED) == {
        "vendor_name": "right",  # spacing is not a difference
        "invoice_number": "wrong",
        "total": "missing",
        "due_date": "invented",
        "currency": "missing",
    }
    assert dev.score_header(None, PRINTED)["total"] == "missing"  # a failed document is wrong


def test_a_line_is_right_only_when_all_four_fields_match_and_is_used_once() -> None:
    truth = [
        {"description": "Pipe", "quantity": "2", "unit_price": "$3.00", "amount": "$6.00"},
        {"description": "Pipe", "quantity": "2", "unit_price": "$3.00", "amount": "$6.00"},
    ]
    exact = {"description": "Pipe", "quantity": "2", "unit_price": "$3.00", "amount": "$6.00"}
    off = {**exact, "amount": "$6.01"}
    assert dev.score_lines([exact, off, exact], truth) == (2, 3)  # one extra line was invented
    assert dev.score_lines([exact], truth) == (1, 1)
    assert dev.score_lines(None, truth) == (0, 0)


def record(status: str = "needs_review", **extra: Any) -> dict[str, Any]:
    return {"condition": "clean_pdf", "status": status, "seconds": 4.0, "fields": None,
            "evidence": [], **extra}  # fmt: skip


def test_grounding_counts_correct_and_wrong_header_values_separately() -> None:
    item = load_golden(split="tuned")[0]
    printed = item.truth.printed
    rows = [
        {"field": "total", "line": False, "printed_text": printed["total"], "found": True},
        {"field": "vendor_name", "line": False, "printed_text": "Wrong Name", "found": True},
        {"field": "invoice_number", "line": False, "printed_text": "Wrong", "found": False},
        {"field": "amount", "line": True, "printed_text": "$1.00", "found": True},
    ]
    score = dev.score_record(record(evidence=rows), item)
    assert score["grounding"] == {"correct": 1, "correct_found": 1, "wrong": 2, "wrong_found": 1}
    assert (score["values"], score["values_found"]) == (4, 3)


def test_the_summary_counts_failures_as_wrong_and_reports_rates() -> None:
    item = load_golden(split="tuned")[0]
    ok_fields: dict[str, Any] = dict(item.truth.printed)
    ok_fields["lines"] = [dict(line.printed) for line in item.truth.lines]
    good = (record(fields=ok_fields), None)
    failed = (record("failed"), None)
    pairs = [(r, dev.score_record(r, item)) for r in (good[0], failed[0])]
    summary = dev.summarise(pairs)
    assert (summary["documents"], summary["failed"]) == (2, 1)
    assert summary["header_field_accuracy"] == 0.5  # the failed document's fields are missing
    assert summary["line_recall"] == 0.5 and summary["documents_fully_right"] == 0.5
    assert "clean_pdf" in dev.render({"by_condition": {"clean_pdf": summary, "all": summary}})


def test_the_held_out_split_cannot_be_loaded() -> None:
    with pytest.raises(PermissionError):
        load_golden(split="heldout")
