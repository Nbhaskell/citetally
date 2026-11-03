"""The pilot tool's plain code: the choice of documents, the comparison with the answer key, and the
summary. The interactive and database parts are used by hand and are not tested here."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from tools import pilot


def doc(item_id: str, condition: str, copy_of: str | None = None) -> Any:
    return SimpleNamespace(id=item_id, condition=condition, expected_duplicate_of=copy_of)


def pool() -> list[Any]:
    items = [doc(f"{c}-{n:02d}", c) for c in pilot.CONDITIONS for n in range(30)]
    items.append(doc("clean_pdf-copy", "clean_pdf", copy_of="clean_pdf-00"))
    return items


def test_select_takes_ten_of_each_condition_and_is_repeatable() -> None:
    first = pilot.select(pool())
    assert len(first) == 40 == len(set(first))
    for condition in pilot.CONDITIONS:
        assert sum(i.startswith(condition) for i in first) == 10
    assert pilot.select(pool()) == first
    assert pilot.select(pool(), seed_=8) != first


def test_select_leaves_out_documents_that_copy_another() -> None:
    assert "clean_pdf-copy" not in pilot.select(pool())


def test_select_refuses_a_condition_with_too_few_documents() -> None:
    with pytest.raises(ValueError, match="scan_heavy"):
        pilot.select([d for d in pool() if d.condition != "scan_heavy"])


def truth() -> Any:
    line = SimpleNamespace(
        description="Flour, 25 kg", quantity="2", unit_price="20.00", amount_minor=4000
    )
    return SimpleNamespace(
        vendor_name="Ridge Mill",
        printed={"vendor_name": "RIDGE MILL CO."},
        invoice_number="INV-77",
        entry_date="2026-03-10",
        entry_type="invoice",
        due_date=None,
        po_number=None,
        currency="USD",
        subtotal_minor=4000,
        tax_total_minor=None,
        shipping_minor=None,
        discount_minor=None,
        total_minor=4000,
        lines=[line],
    )


def stored() -> dict[str, Any]:
    return {
        "vendor": "Ridge Mill",
        "invoice_number": "inv-77",
        "entry_date": "2026-03-10",
        "entry_type": "invoice",
        "due_date": None,
        "po_number": None,
        "currency": "USD",
        "subtotal_minor": 4000,
        "tax_total_minor": None,
        "shipping_minor": None,
        "discount_minor": None,
        "total_minor": 4000,
        "lines": [
            {
                "description": "flour, 25 kg",
                "quantity": "2.00",
                "unit_price": "20",
                "amount_minor": 4000,
            }
        ],
    }


def test_a_matching_entry_has_no_differences() -> None:
    assert pilot.entry_differences(stored(), truth()) == []


def test_each_wrong_value_is_named() -> None:
    entry = stored()
    entry["total_minor"] = 4001
    entry["vendor"] = "Someone Else"
    entry["lines"][0]["amount_minor"] = 3999
    entry["due_date"] = "2026-04-01"
    wrong = pilot.entry_differences(entry, truth())
    assert {"total", "vendor", "lines", "due_date"} <= set(wrong)
    assert set(wrong) & set(pilot.CORE) == {"total", "vendor", "lines"}


def test_a_missing_line_is_wrong() -> None:
    entry = stored()
    entry["lines"] = []
    assert "lines" in pilot.entry_differences(entry, truth())


def typed() -> dict[str, Any]:
    return {
        "vendor": "ridge mill co.",
        "invoice_number": "INV-77",
        "entry_date": "2026-03-10",
        "total": "$40.00",
        "lines": [
            {
                "description": "Flour, 25 kg",
                "quantity": "2",
                "unit_price": "$20.00",
                "amount": "$40.00",
            }
        ],
    }


def test_typed_values_are_compared_by_meaning() -> None:
    assert pilot.typed_differences(typed(), truth()) == []
    bad = typed()
    bad["total"] = "$41.00"
    bad["entry_date"] = "not a date"
    assert pilot.typed_differences(bad, truth()) == ["entry_date", "total"]


def row(pilot_id: str, condition: str, review: int, typed_s: float, **extra: Any) -> dict[str, Any]:
    return {
        "pilot": pilot_id,
        "condition": condition,
        "status": "approved",
        "decision": "approve",
        "review_seconds": review,
        "typed_seconds": typed_s,
        "overrides": 0,
        "wrong_core": [],
        "wrong_other": [],
        "typed_wrong": [],
        **extra,
    }


def test_summary_gives_the_ratio_and_separates_wrong_values_by_override() -> None:
    rows = [
        row("p01", "clean_pdf", 20, 100.0),
        row("p02", "scan_heavy", 60, 120.0, overrides=1, wrong_core=["total"]),
        row("p03", "phone_photo", 40, 80.0, wrong_core=["vendor"]),
        {
            "pilot": "p04",
            "condition": "scan_light",
            "status": "needs_review",
            "decision": None,
            "id": "x",
        },
    ]
    s = pilot.summarise(rows)
    assert s["reviewed_and_typed"] == 3
    assert s["review_median"] == 40 and s["typed_median"] == 100.0
    assert s["ratio"] == pytest.approx(0.4)
    assert s["wrong_core_approved"] == 2
    assert s["wrong_core_approved_without_override"] == ["p03"]
    assert s["wrong_core_approved_with_override"] == ["p02"]
    assert s["not_reviewed"] == ["p04"] and s["not_typed"] == ["p04"]
    text = pilot.render(s)
    assert "0.40" in text and "(met)" in text


def test_summary_with_nothing_done_does_not_divide_by_zero() -> None:
    s = pilot.summarise([{"pilot": "p01", "condition": "clean_pdf", "id": "x"}])
    assert s["ratio"] is None
    assert "not measured" in pilot.render(s)
