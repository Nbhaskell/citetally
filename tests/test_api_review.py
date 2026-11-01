"""Editing, choosing a vendor, the reviewer's decisions, vendors and categories, and startup."""

from __future__ import annotations

import time
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from citetally import ingest
from citetally import repository as repo
from citetally.api import create_app
from citetally.config import Settings
from citetally.models import CheckCode
from citetally.pipeline import Services
from citetally.providers import FakeProvider
from citetally.reading.ocr import FakeOcr
from tests.api_support import (
    HOST,
    check,
    db,
    detail,
    known_vendor,
    new_document,
    worker,
)
from tests.test_pipeline import GOOD, LINES, pdf


def entry_id(client: TestClient, document_id: int) -> int:
    return int(detail(client, document_id)["entry"]["id"])


def patch(client: TestClient, document_id: int, **changes: Any) -> Any:
    return client.patch(f"/api/entries/{entry_id(client, document_id)}", json=changes)


def with_vendor(client: TestClient, document_id: int) -> None:
    """Create the vendor from the printed name, so the blocking checks can pass."""
    response = client.post(
        f"/api/entries/{entry_id(client, document_id)}/vendor", json={"create": True}
    )
    assert response.status_code == 200


# --- editing the header ------------------------------------------------------------------------


def test_an_edit_is_recorded_drops_the_models_evidence_and_runs_the_checks_again(
    client: TestClient, app: Any
) -> None:
    document_id = new_document(client, app)
    response = patch(client, document_id, total_minor=99900)
    assert response.status_code == 200
    body = response.json()
    assert body["entry"]["total_minor"] == 99900
    (edit,) = body["edits"]
    assert (edit["field"], edit["old_value"], edit["new_value"], edit["line_id"]) == (
        "total", "15200", "99900", None,
    )  # fmt: skip
    assert not any(e["field"] == "total" for e in body["evidence"])
    total = check(body, "TOTAL_MATCH")
    assert not total["passed"] and total["detail"] == {"expected": 15200, "stated": 99900}


def test_editing_clears_every_override_but_a_change_that_changes_nothing_does_not(
    client: TestClient, app: Any
) -> None:
    document_id = new_document(client, app)
    connection = db(app)
    repo.override_check(connection, document_id, CheckCode.UNKNOWN_VENDOR, reason="new vendor")
    connection.close()

    same = patch(client, document_id, total_minor=15200, notes=None)
    assert check(same.json(), "UNKNOWN_VENDOR")["overridden"] is True
    assert same.json()["edits"] == [] or all(e["field"] != "total" for e in same.json()["edits"])

    changed = patch(client, document_id, po_number="PO-7")
    assert changed.json()["edits"][-1]["field"] == "po_number"
    assert check(changed.json(), "UNKNOWN_VENDOR")["overridden"] is False


def test_the_header_fields_can_be_changed_and_cleared(client: TestClient, app: Any) -> None:
    document_id = new_document(client, app)
    body = patch(
        client,
        document_id,
        invoice_number="INV-X",
        entry_date="2026-03-15",
        due_date="2026-04-15",
        currency="EUR",
        subtotal_minor=15000,
        tax_total_minor=200,
        shipping_minor=0,
        discount_minor=0,
        entry_type="receipt",
        notes="checked by phone",
    ).json()
    entry = body["entry"]
    assert (entry["invoice_number"], entry["entry_date"], entry["due_date"], entry["currency"]) == (
        "INV-X", "2026-03-15", "2026-04-15", "EUR",
    )  # fmt: skip
    assert (entry["entry_type"], entry["notes"], entry["shipping_minor"]) == (
        "receipt",
        "checked by phone",
        0,
    )
    assert {e["field"] for e in body["edits"]} == {
        "invoice_number", "entry_date", "due_date", "currency", "subtotal", "tax_total", "shipping",
        "discount", "entry_type",
    }  # fmt: skip
    cleared = patch(client, document_id, due_date=None, po_number=None).json()["entry"]
    assert cleared["due_date"] is None


def test_the_entry_type_cannot_be_cleared(client: TestClient, app: Any) -> None:
    document_id = new_document(client, app)
    response = patch(client, document_id, entry_type=None)
    assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_request"


def test_a_category_is_set_by_code_and_marked_as_chosen_by_hand(
    client: TestClient, app: Any
) -> None:
    document_id = new_document(client, app)
    entry = patch(client, document_id, category="FOOD").json()["entry"]
    assert (entry["category"], entry["category_source"]) == ("FOOD", "manual")
    assert patch(client, document_id, category=None).json()["entry"]["category"] is None
    assert patch(client, document_id, category="NOPE").status_code == 404
    connection = db(app)
    connection.execute("UPDATE categories SET is_active = 0 WHERE code = 'OTHER'")
    connection.close()
    off = patch(client, document_id, category="OTHER")
    assert off.status_code == 422 and "switched off" in off.json()["error"]["message"]


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"entry_date": "14/03/2026"}, "entry_date"),
        ({"currency": "usd"}, "currency"),
        ({"total_minor": -5}, "total_minor"),
        ({"total_minor": 1.5}, "total_minor"),
        ({"unknown_field": 1}, "unknown_field"),
        ({"lines": [{"amount_minor": -1}]}, "lines.0.amount_minor"),
    ],
)
def test_an_invalid_edit_is_refused_and_names_only_the_field(
    client: TestClient, app: Any, changes: dict[str, Any], field: str
) -> None:
    document_id = new_document(client, app)
    response = patch(client, document_id, **changes)
    assert response.status_code == 422
    assert response.json()["error"]["details"]["fields"] == [field]
    assert detail(client, document_id)["edits"] == []


def test_a_date_that_does_not_exist_is_refused(client: TestClient, app: Any) -> None:
    document_id = new_document(client, app)
    assert patch(client, document_id, entry_date="2026-02-30").status_code == 422


def test_an_unknown_entry_is_not_found(client: TestClient) -> None:
    assert client.patch("/api/entries/9999", json={"notes": "x"}).status_code == 404


def test_only_a_document_waiting_for_review_can_be_edited(client: TestClient, app: Any) -> None:
    document_id = new_document(client, app)
    with_vendor(client, document_id)
    client.post(f"/api/documents/{document_id}/approve", json={})
    response = patch(client, document_id, total_minor=1)
    assert response.status_code == 409 and response.json()["error"]["code"] == "not_editable"
    client.post(f"/api/documents/{document_id}/reopen")
    assert patch(client, document_id, total_minor=15200).status_code == 200


# --- editing lines -----------------------------------------------------------------------------


def test_a_line_can_be_corrected_and_only_that_value_changes(client: TestClient, app: Any) -> None:
    document_id = new_document(client, app)
    (line,) = detail(client, document_id)["entry"]["lines"]
    body = patch(client, document_id, lines=[{"id": line["id"], "amount_minor": 15100}]).json()
    (corrected,) = body["entry"]["lines"]
    assert (corrected["amount_minor"], corrected["description"], corrected["quantity"]) == (
        15100, "Kibble 30 lb bag", "4",
    )  # fmt: skip
    (edit,) = body["edits"]
    assert (edit["field"], edit["line_id"], edit["old_value"], edit["new_value"]) == (
        "amount", line["id"], "15200", "15100",
    )  # fmt: skip
    assert not any(e["field"] == "amount" and e["line_id"] == line["id"] for e in body["evidence"])
    assert not check(body, "LINE_MATH")["passed"]


def test_a_line_can_be_added_removed_and_reordered(client: TestClient, app: Any) -> None:
    document_id = new_document(client, app)
    (first,) = detail(client, document_id)["entry"]["lines"]

    added = patch(
        client,
        document_id,
        lines=[{"id": first["id"]}, {"description": "Delivery", "amount_minor": 500}],
    ).json()
    assert [(line["line_number"], line["description"]) for line in added["entry"]["lines"]] == [
        (1, "Kibble 30 lb bag"), (2, "Delivery"),
    ]  # fmt: skip
    second_id = added["entry"]["lines"][1]["id"]
    assert not check(added, "SUBTOTAL_MATCH")["passed"]  # 15,700 against the printed 15,200

    swapped = patch(client, document_id, lines=[{"id": second_id}, {"id": first["id"]}]).json()
    assert [(line["id"], line["line_number"]) for line in swapped["entry"]["lines"]] == [
        (second_id, 1), (first["id"], 2),
    ]  # fmt: skip

    removed = patch(client, document_id, lines=[{"id": first["id"]}]).json()
    assert [line["id"] for line in removed["entry"]["lines"]] == [first["id"]]
    assert removed["entry"]["lines"][0]["line_number"] == 1
    gone = [e for e in removed["edits"] if e["old_value"] == "Delivery" and e["new_value"] is None]
    assert gone and gone[0]["field"] == "description"


def test_an_empty_list_removes_every_line_and_no_lines_key_leaves_them(
    client: TestClient, app: Any
) -> None:
    document_id = new_document(client, app)
    assert patch(client, document_id, notes="x").json()["entry"]["lines"] != []
    assert patch(client, document_id, lines=[]).json()["entry"]["lines"] == []


def test_a_line_that_is_not_on_this_entry_is_refused_and_nothing_changes(
    client: TestClient, app: Any
) -> None:
    mine = new_document(client, app)
    theirs = new_document(client, app)
    (other_line,) = detail(client, theirs)["entry"]["lines"]
    response = patch(
        client, mine, total_minor=1, lines=[{"id": other_line["id"], "amount_minor": 1}]
    )
    assert response.status_code == 422 and response.json()["error"]["code"] == "unknown_line"
    body = detail(client, mine)
    assert body["entry"]["total_minor"] == 15200 and body["edits"] == []  # all or nothing


def test_a_bad_quantity_is_refused(client: TestClient, app: Any) -> None:
    document_id = new_document(client, app)
    (line,) = detail(client, document_id)["entry"]["lines"]
    response = patch(client, document_id, lines=[{"id": line["id"], "quantity": "lots"}])
    assert response.status_code == 422


# --- choosing the vendor -----------------------------------------------------------------------


def test_choosing_an_existing_vendor_sets_it_learns_the_printed_name_and_applies_its_category(
    client: TestClient, app: Any
) -> None:
    vendor_id = known_vendor(app, "Northfield Supply")
    document_id = new_document(client, app)
    response = client.post(
        f"/api/entries/{entry_id(client, document_id)}/vendor", json={"vendor_id": vendor_id}
    )
    assert response.status_code == 200
    body = response.json()
    entry = body["entry"]
    assert (entry["vendor_id"], entry["vendor_name"], entry["vendor_match_method"]) == (
        vendor_id, "Northfield Supply", "manual",
    )  # fmt: skip
    assert (entry["category"], entry["category_source"]) == ("FOOD", "vendor_default")
    assert check(body, "UNKNOWN_VENDOR")["passed"]
    edit = body["edits"][-1]
    assert (edit["field"], edit["old_value"], edit["new_value"]) == (
        "vendor_name", "Northfield Pet Supply Co.", "Northfield Supply",
    )  # fmt: skip
    vendors = client.get("/api/vendors").json()
    assert vendors[0]["aliases"] == ["Northfield Pet Supply Co."]


def test_a_category_chosen_by_hand_is_not_replaced_by_the_vendors(
    client: TestClient, app: Any
) -> None:
    vendor_id = known_vendor(app)
    document_id = new_document(client, app)
    patch(client, document_id, category="OTHER")
    entry = client.post(
        f"/api/entries/{entry_id(client, document_id)}/vendor", json={"vendor_id": vendor_id}
    ).json()["entry"]
    assert (entry["category"], entry["category_source"]) == ("OTHER", "manual")


def test_creating_a_vendor_from_the_printed_name_and_the_clash_that_follows(
    client: TestClient, app: Any
) -> None:
    first = new_document(client, app)
    created = client.post(
        f"/api/entries/{entry_id(client, first)}/vendor", json={"create": True}
    ).json()
    assert created["entry"]["vendor_name"] == "Northfield Pet Supply Co."
    assert created["entry"]["vendor_match_method"] == "created"

    second = new_document(client, app)
    clash = client.post(f"/api/entries/{entry_id(client, second)}/vendor", json={"create": True})
    assert clash.status_code == 409 and clash.json()["error"]["code"] == "vendor_exists"
    assert clash.json()["error"]["details"]["vendor_id"] == created["entry"]["vendor_id"]

    named = client.post(
        f"/api/entries/{entry_id(client, second)}/vendor",
        json={"create": True, "name": "Northfield Pets"},
    )
    assert named.status_code == 200 and named.json()["entry"]["vendor_name"] == "Northfield Pets"


@pytest.mark.parametrize(
    "body",
    [{}, {"vendor_id": 1, "create": True}, {"create": True, "name": " "}, {"vendor_id": "x"}],
)
def test_a_vendor_choice_must_be_exactly_one_clear_thing(
    client: TestClient, app: Any, body: dict[str, Any]
) -> None:
    known_vendor(app)
    document_id = new_document(client, app)
    response = client.post(f"/api/entries/{entry_id(client, document_id)}/vendor", json=body)
    assert response.status_code == 422


def test_an_unknown_or_switched_off_vendor_cannot_be_chosen(client: TestClient, app: Any) -> None:
    vendor_id = known_vendor(app)
    document_id = new_document(client, app)
    url = f"/api/entries/{entry_id(client, document_id)}/vendor"
    assert client.post(url, json={"vendor_id": 9999}).status_code == 404
    connection = db(app)
    connection.execute("UPDATE vendors SET is_active = 0 WHERE id = ?", (vendor_id,))
    connection.close()
    assert client.post(url, json={"vendor_id": vendor_id}).status_code == 422


def test_choosing_the_vendor_runs_the_duplicate_check_against_that_vendors_other_documents(
    client: TestClient, app: Any
) -> None:
    first = new_document(client, app, invoice_number="SAME-1")
    second = new_document(client, app, invoice_number="same 1")
    with_vendor(client, first)
    body = client.post(
        f"/api/entries/{entry_id(client, second)}/vendor",
        json={"vendor_id": detail(client, first)["entry"]["vendor_id"]},
    ).json()
    duplicate = check(body, "DUPLICATE_SUSPECT")
    assert not duplicate["passed"]
    assert duplicate["detail"]["matches"] == [{"document_id": first, "reason": "invoice_number"}]


# --- approving ---------------------------------------------------------------------------------


def test_approval_is_refused_while_a_blocking_check_is_unresolved(
    client: TestClient, app: Any
) -> None:
    document_id = new_document(client, app)
    response = client.post(f"/api/documents/{document_id}/approve", json={})
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "approval_blocked" and error["details"]["unresolved"] == [
        "UNKNOWN_VENDOR"
    ]
    body = detail(client, document_id)
    assert body["document"]["status"] == "needs_review" and body["reviews"] == []


def test_a_clean_document_is_approved_and_the_review_is_recorded(
    client: TestClient, app: Any
) -> None:
    document_id = new_document(client, app)
    with_vendor(client, document_id)
    response = client.post(f"/api/documents/{document_id}/approve", json={"review_seconds": 42})
    assert response.status_code == 200
    body = response.json()
    assert body["document"]["status"] == "approved"
    review = body["review"]
    got = (review["decision"], review["overrides"], review["edited"], review["review_seconds"])
    assert got == (
        "approve", 0, True, 42,
    )  # fmt: skip
    history = detail(client, document_id)["history"]
    recorded = next(h for h in history if h["event_type"] == "review_recorded")
    assert recorded["payload"] == {
        "decision": "approve",
        "overrides": 0,
        "edited": True,
        "review_seconds": 42,
    }


def test_a_review_that_changed_nothing_says_so_and_the_time_is_optional(
    client: TestClient, app: Any
) -> None:
    vendor_id = known_vendor(app)
    document_id = new_document(client, app)
    connection = db(app)
    entry = repo.get_entry_for_document(connection, document_id)
    assert entry is not None
    repo.update_entry(connection, entry.id, vendor_id=vendor_id, vendor_match_method="exact")
    from citetally.checks import run_checks

    run_checks(
        connection,
        document_id,
        settings=app.state.citetally.settings,
        today=date(2026, 6, 15),
    )
    connection.close()
    review = client.post(f"/api/documents/{document_id}/approve", json={}).json()["review"]
    assert (review["edited"], review["review_seconds"], review["overrides"]) == (False, None, 0)


def test_a_failed_blocking_check_can_be_accepted_with_a_written_reason(
    client: TestClient, app: Any
) -> None:
    document_id = new_document(client, app)
    response = client.post(
        f"/api/documents/{document_id}/approve",
        json={"overrides": [{"check_code": "UNKNOWN_VENDOR", "reason": "New vendor, added later"}]},
    )
    assert response.status_code == 200 and response.json()["review"]["overrides"] == 1
    kept = check(detail(client, document_id), "UNKNOWN_VENDOR")
    assert (kept["passed"], kept["overridden"], kept["override_reason"]) == (
        False, True, "New vendor, added later",
    )  # fmt: skip


def test_overrides_sent_with_a_refused_approval_are_not_kept(client: TestClient, app: Any) -> None:
    document_id = new_document(client, app)
    patch(client, document_id, total_minor=99900)  # TOTAL_MATCH now fails as well
    response = client.post(
        f"/api/documents/{document_id}/approve",
        json={"overrides": [{"check_code": "UNKNOWN_VENDOR", "reason": "will add"}]},
    )
    assert response.status_code == 409
    assert response.json()["error"]["details"]["unresolved"] == ["TOTAL_MATCH"]
    assert check(detail(client, document_id), "UNKNOWN_VENDOR")["overridden"] is False


@pytest.mark.parametrize(
    ("override", "status"),
    [
        ({"check_code": "UNKNOWN_VENDOR", "reason": ""}, 422),
        ({"check_code": "UNKNOWN_VENDOR", "reason": "   "}, 422),
        ({"check_code": "NOT_A_CHECK", "reason": "x"}, 422),
        ({"check_code": "AMBIGUOUS_FORMAT", "reason": "x"}, 422),  # not blocking
        ({"check_code": "TOTAL_MATCH", "reason": "x"}, 422),  # passed, nothing to accept
        ({"check_code": "UNKNOWN_VENDOR"}, 422),
    ],
)
def test_an_override_needs_a_real_reason_a_known_check_and_something_to_accept(
    client: TestClient, app: Any, override: dict[str, Any], status: int
) -> None:
    document_id = new_document(client, app)
    response = client.post(f"/api/documents/{document_id}/approve", json={"overrides": [override]})
    assert response.status_code == status
    assert detail(client, document_id)["document"]["status"] == "needs_review"


@pytest.mark.parametrize("seconds", [-1, 86_401, "soon", 1.5])
def test_the_review_time_must_be_a_sensible_whole_number_of_seconds(
    client: TestClient, app: Any, seconds: Any
) -> None:
    document_id = new_document(client, app)
    with_vendor(client, document_id)
    assert (
        client.post(
            f"/api/documents/{document_id}/approve", json={"review_seconds": seconds}
        ).status_code
        == 422
    )
    assert (
        client.post(f"/api/documents/{document_id}/approve", json={"review_seconds": 0}).status_code
        == 200
    )


def test_an_approval_with_an_unknown_field_is_refused(client: TestClient, app: Any) -> None:
    document_id = new_document(client, app)
    assert (
        client.post(f"/api/documents/{document_id}/approve", json={"force": True}).status_code
        == 422
    )


# --- rejecting, reopening, duplicates ----------------------------------------------------------


def test_rejecting_needs_a_reason_and_can_be_undone_by_reopening(
    client: TestClient, app: Any
) -> None:
    document_id = new_document(client, app)
    url = f"/api/documents/{document_id}/reject"
    assert client.post(url, json={}).status_code == 422
    assert client.post(url, json={"reason": "  "}).status_code == 422
    rejected = client.post(url, json={"reason": "Not ours", "review_seconds": 9}).json()
    assert rejected["document"]["status"] == "rejected"
    assert (rejected["review"]["reason"], rejected["review"]["review_seconds"]) == ("Not ours", 9)

    reopened = client.post(f"/api/documents/{document_id}/reopen").json()
    assert reopened["document"]["status"] == "needs_review"
    assert reopened["review"]["decision"] == "reopen"
    assert [r["decision"] for r in detail(client, document_id)["reviews"]] == ["reject", "reopen"]


def test_an_approved_document_can_be_reopened_and_edited(client: TestClient, app: Any) -> None:
    document_id = new_document(client, app)
    with_vendor(client, document_id)
    client.post(f"/api/documents/{document_id}/approve", json={})
    assert (
        client.post(f"/api/documents/{document_id}/reopen", json={}).json()["document"]["status"]
        == "needs_review"
    )


def test_decisions_that_the_status_does_not_allow_are_refused_with_the_reason(
    client: TestClient, app: Any
) -> None:
    document_id = new_document(client, app)
    first = client.post(f"/api/documents/{document_id}/reopen")
    assert first.status_code == 409 and first.json()["error"]["code"] == "illegal_transition"

    client.post(f"/api/documents/{document_id}/reject", json={"reason": "no"})
    for action, body in (
        ("approve", {}),
        ("reject", {"reason": "again"}),
        ("mark-duplicate", {"duplicate_of": 1}),
    ):
        response = client.post(f"/api/documents/{document_id}/{action}", json=body)
        assert response.status_code == 409, action
        assert response.json()["error"]["code"] == "illegal_transition"

    other = new_document(client, app)
    with_vendor(client, other)
    client.post(f"/api/documents/{other}/approve", json={})
    assert client.post(f"/api/documents/{other}/approve", json={}).status_code == 409


def test_a_document_can_be_marked_as_a_duplicate_of_another(client: TestClient, app: Any) -> None:
    original = new_document(client, app)
    copy = new_document(client, app)
    body = client.post(
        f"/api/documents/{copy}/mark-duplicate", json={"duplicate_of": original}
    ).json()
    assert (
        body["document"]["status"] == "duplicate" and body["document"]["duplicate_of"] == original
    )
    assert body["review"]["decision"] == "mark_duplicate"


def test_marking_a_duplicate_needs_a_real_other_document(client: TestClient, app: Any) -> None:
    document_id = new_document(client, app)
    url = f"/api/documents/{document_id}/mark-duplicate"
    assert client.post(url, json={"duplicate_of": document_id}).status_code == 422
    assert client.post(url, json={"duplicate_of": 9999}).status_code == 404
    assert client.post(url, json={}).status_code == 422


@pytest.mark.parametrize("action", ["approve", "reject", "reopen", "mark-duplicate", "reprocess"])
def test_every_decision_on_an_unknown_document_is_not_found(
    client: TestClient, action: str
) -> None:
    body = {
        "reject": {"reason": "x"},
        "mark-duplicate": {"duplicate_of": 1},
        "reprocess": {"from_stage": "read"},
    }
    response = client.post(f"/api/documents/9999/{action}", json=body.get(action, {}))
    assert response.status_code == 404


# --- vendors and categories --------------------------------------------------------------------


def test_vendors_are_created_listed_and_a_repeat_name_is_refused(client: TestClient) -> None:
    created = client.post(
        "/api/vendors",
        json={
            "name": "Lakeside Hardware, Inc.",
            "default_category": "REPAIRS",
            "default_currency": "USD",
        },
    )
    assert created.status_code == 201
    assert created.json()["default_category"] == "REPAIRS" and created.json()["aliases"] == []
    assert [v["name"] for v in client.get("/api/vendors").json()] == ["Lakeside Hardware, Inc."]
    repeat = client.post("/api/vendors", json={"name": "lakeside hardware"})
    assert repeat.status_code == 409 and repeat.json()["error"]["code"] == "vendor_exists"
    assert (
        client.post("/api/vendors", json={"name": "X", "default_category": "NOPE"}).status_code
        == 404
    )


def test_aliases_are_added_once_and_cannot_steal_another_vendors_name(client: TestClient) -> None:
    a = client.post("/api/vendors", json={"name": "Alpha Supply"}).json()["id"]
    b = client.post("/api/vendors", json={"name": "Beta Tools"}).json()["id"]
    added = client.post(f"/api/vendors/{a}/aliases", json={"alias": "Alpha Sup."})
    assert added.status_code == 201 and added.json()["aliases"] == ["Alpha Sup."]
    again = client.post(f"/api/vendors/{a}/aliases", json={"alias": "alpha sup"})
    assert again.status_code == 201 and again.json()["aliases"] == ["Alpha Sup."]
    stolen = client.post(f"/api/vendors/{b}/aliases", json={"alias": "Alpha Sup."})
    assert stolen.status_code == 409
    assert client.post("/api/vendors/9999/aliases", json={"alias": "x"}).status_code == 404


def test_merging_moves_documents_aliases_and_the_old_name_and_checks_them_again(
    client: TestClient, app: Any
) -> None:
    old = known_vendor(app, "Northfield Supply")
    new = client.post("/api/vendors", json={"name": "Northfield Pet Supply"}).json()["id"]
    client.post(f"/api/vendors/{old}/aliases", json={"alias": "NPS"})
    document_id = new_document(client, app)
    client.post(f"/api/entries/{entry_id(client, document_id)}/vendor", json={"vendor_id": old})

    merged = client.post(f"/api/vendors/{old}/merge", json={"into": new})
    assert merged.status_code == 200
    assert set(merged.json()["aliases"]) == {"NPS", "Northfield Supply"}
    body = detail(client, document_id)
    assert body["entry"]["vendor_id"] == new
    assert check(body, "UNKNOWN_VENDOR")["passed"]
    assert [v["id"] for v in client.get("/api/vendors").json()] == [new]
    assert old in [
        v["id"] for v in client.get("/api/vendors", params={"include_inactive": True}).json()
    ]


def test_a_vendor_cannot_be_merged_into_itself_a_stranger_or_a_switched_off_vendor(
    client: TestClient, app: Any
) -> None:
    a = client.post("/api/vendors", json={"name": "Alpha"}).json()["id"]
    b = client.post("/api/vendors", json={"name": "Beta"}).json()["id"]
    assert client.post(f"/api/vendors/{a}/merge", json={"into": a}).status_code == 422
    assert client.post(f"/api/vendors/{a}/merge", json={"into": 9999}).status_code == 404
    assert client.post("/api/vendors/9999/merge", json={"into": a}).status_code == 404
    connection = db(app)
    connection.execute("UPDATE vendors SET is_active = 0 WHERE id = ?", (b,))
    connection.close()
    assert client.post(f"/api/vendors/{a}/merge", json={"into": b}).status_code == 422


def test_the_categories_are_listed(client: TestClient) -> None:
    categories = client.get("/api/categories").json()
    assert len(categories) == 11 and categories[0] == {
        "code": "SUPPLIES",
        "name": "Supplies",
        "is_active": True,
    }


# --- starting up -------------------------------------------------------------------------------


def test_work_interrupted_by_a_restart_is_queued_again_at_startup(settings: Settings) -> None:
    services = Services(
        settings=settings, ocr=FakeOcr(), provider=FakeProvider([GOOD]), isolate=False
    )
    app = create_app(settings, services=services, autostart_worker=False, isolate_ingest=False)
    connection = app.state.citetally.database.connect()
    ingest.ingest(
        connection, pdf(), "stuck.pdf", settings=settings, isolate=False
    )  # never processed
    connection.close()
    with TestClient(app, base_url=HOST) as client:
        assert client.get("/api/status").json()["queue_depth"] == 1
        assert worker(app).drain() == 1
        (row,) = client.get("/api/documents").json()["items"]
        assert row["status"] == "needs_review"


def test_the_background_thread_processes_uploads_on_its_own(settings: Settings) -> None:
    services = Services(
        settings=settings, ocr=FakeOcr(), provider=FakeProvider([GOOD]), isolate=False
    )
    app = create_app(settings, services=services, autostart_worker=True, isolate_ingest=False)
    with TestClient(app, base_url=HOST) as client:
        client.post("/api/documents", files=[("files", ("a.pdf", pdf(LINES)))])
        deadline = time.monotonic() + 15
        status = "received"
        while status != "needs_review" and time.monotonic() < deadline:
            time.sleep(0.05)
            status = client.get("/api/documents").json()["items"][0]["status"]
        assert status == "needs_review"
        assert client.get("/api/status").json()["queue_depth"] == 0
