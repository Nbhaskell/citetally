"""Exports through the API: selection, the exported status, the file, and what must not leak."""

from __future__ import annotations

import csv
import hashlib
import io
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from citetally import repository as repo
from tests.api_support import HOST, db, detail, new_document

_vendor_numbers = iter(range(1, 10_000))


def approved(client: TestClient, app: Any, *, label: str | None = None, **changes: Any) -> int:
    """A document through the pipeline with its own vendor (so none is a duplicate), approved."""
    n = next(_vendor_numbers)
    printed = changes.setdefault("vendor_name", f"Vendor Number {n} Ltd")
    document_id = new_document(client, app, **changes)
    entry = detail(client, document_id)["entry"]
    chosen = client.post(
        f"/api/entries/{entry['id']}/vendor", json={"create": True, "name": label or printed}
    )
    assert chosen.status_code == 200, chosen.text
    response = client.post(f"/api/documents/{document_id}/approve", json={})
    assert response.status_code == 200, response.text
    return document_id


def read(client: TestClient, export_id: int) -> list[dict[str, str]]:
    response = client.get(f"/api/exports/{export_id}/download")
    assert response.status_code == 200
    return list(csv.DictReader(io.StringIO(response.content.decode("utf-8"), newline="")))


def make(client: TestClient, **body: Any) -> Any:
    return client.post("/api/exports", json={"profile": "entries_csv", **body})


def status_of(client: TestClient, document_id: int) -> str:
    return str(detail(client, document_id)["document"]["status"])


# --- nothing to export / preview ---------------------------------------------------------------


def test_with_nothing_approved_the_preview_is_empty_and_an_export_is_refused(
    client: TestClient,
) -> None:
    body = client.get("/api/exports/preview", params={"profile": "entries_csv"}).json()
    assert (body["entry_count"], body["row_count"], body["sample"], body["totals"]) == (
        0,
        0,
        [],
        {},
    )
    assert body["first_date"] is None and body["columns"][0] == "entry_id"
    refused = make(client)
    assert (
        refused.status_code == 422 and "no approved entries" in refused.json()["error"]["message"]
    )


def test_the_preview_shows_counts_totals_dates_and_a_short_sample(
    client: TestClient, app: Any
) -> None:
    for _ in range(7):
        approved(client, app)
    body = client.get("/api/exports/preview", params={"profile": "entries_csv"}).json()
    assert (body["entry_count"], body["row_count"]) == (7, 7)
    assert body["totals"] == {"USD": "1064.00"}
    assert body["first_date"] == body["last_date"] == "2026-03-14"
    assert len(body["sample"]) == 5 and len(body["sample"][0]) == len(body["columns"])
    lines = client.get("/api/exports/preview", params={"profile": "lines_csv"}).json()
    assert lines["row_count"] == 7 and lines["columns"][9] == "line_number"
    assert client.get("/api/exports/preview", params={"profile": "nope"}).status_code == 422
    assert client.get("/api/exports/preview").status_code == 422


def test_a_preview_changes_nothing(client: TestClient, app: Any) -> None:
    document_id = approved(client, app)
    client.get("/api/exports/preview", params={"profile": "entries_csv"})
    assert status_of(client, document_id) == "approved" and client.get("/api/exports").json() == []


# --- making an export --------------------------------------------------------------------------


def test_an_export_writes_the_file_records_it_and_moves_the_entries_to_exported(
    client: TestClient, app: Any, settings: Any
) -> None:
    first, second = approved(client, app), approved(client, app)
    waiting = new_document(client, app)  # not approved: must stay out
    response = make(client)
    assert response.status_code == 201
    body = response.json()
    export = body["export"]
    assert (export["profile"], export["entry_count"], export["row_count"]) == ("entries_csv", 2, 2)
    assert export["file_name"] == f"citetally_entries_csv_{export['id']:04d}.csv"
    assert export["download_url"] == f"/api/exports/{export['id']}/download"
    assert body["skipped_already_exported"] == 0

    assert (status_of(client, first), status_of(client, second)) == ("exported", "exported")
    assert status_of(client, waiting) == "needs_review"

    path = Path(settings.data_dir) / "exports" / f"{export['id']}.csv"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == export["file_sha256"]
    connection = db(app)
    items = connection.execute(
        "SELECT entry_id FROM export_items WHERE export_id = ?", (export["id"],)
    ).fetchall()
    connection.close()
    assert len(items) == 2
    assert [e["id"] for e in client.get("/api/exports").json()] == [export["id"]]


def test_the_download_is_the_recorded_file_as_an_attachment(client: TestClient, app: Any) -> None:
    approved(client, app)
    export = make(client).json()["export"]
    response = client.get(export["download_url"])
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert export["file_name"] in response.headers["content-disposition"]
    assert "attachment" in response.headers["content-disposition"]
    assert hashlib.sha256(response.content).hexdigest() == export["file_sha256"]
    assert response.headers["cache-control"] == "no-store"


def test_the_file_matches_the_database_to_the_cent(client: TestClient, app: Any) -> None:
    ids = [approved(client, app) for _ in range(3)]
    credit = approved(client, app, entry_type="credit_note")
    export = make(client).json()["export"]
    rows = {int(r["entry_id"]): r for r in read(client, export["id"])}
    assert len(rows) == 4

    signed_db = Decimal(0)
    for document_id in [*ids, credit]:
        entry = detail(client, document_id)["entry"]
        row = rows[entry["id"]]
        sign = -1 if entry["entry_type"] == "credit_note" else 1
        assert Decimal(row["total"]) == sign * Decimal(entry["total_minor"]) / 100
        assert (
            row["vendor"] == entry["vendor_name"]
            and row["invoice_number"] == entry["invoice_number"]
        )
        assert row["category"] == entry["category"] and row["currency"] == entry["currency"]
        assert row["entry_date"] == entry["entry_date"] and row["type"] == entry["entry_type"]
        signed_db += sign * Decimal(entry["total_minor"]) / 100
    assert sum(Decimal(r["total"]) for r in rows.values()) == signed_db == Decimal("304.00")
    assert rows[detail(client, credit)["entry"]["id"]]["total"] == "-152.00"
    assert detail(client, credit)["entry"]["total_minor"] == 15200  # stored positive


def test_the_lines_file_has_every_line_and_the_totals_agree(client: TestClient, app: Any) -> None:
    first, second = approved(client, app), approved(client, app, entry_type="credit_note")
    export = make(client, profile="lines_csv").json()["export"]
    assert export["row_count"] == 2 and export["entry_count"] == 2
    rows = read(client, export["id"])
    by_entry = {int(r["entry_id"]): r for r in rows}
    for document_id in (first, second):
        entry = detail(client, document_id)["entry"]
        row = by_entry[entry["id"]]
        line = entry["lines"][0]
        sign = -1 if entry["entry_type"] == "credit_note" else 1
        assert Decimal(row["line_amount"]) == sign * Decimal(line["amount_minor"]) / 100
        assert Decimal(row["unit_price"]) == sign * Decimal(line["unit_price"])
        assert row["description"] == line["description"] and row["line_number"] == "1"
        assert Decimal(row["entry_total"]) == sign * Decimal(entry["total_minor"]) / 100
    assert sum(Decimal(r["line_amount"]) for r in rows) == Decimal("0.00")  # 152.00 and -152.00


def test_exported_entries_are_left_out_of_the_next_export_unless_asked_for(
    client: TestClient, app: Any
) -> None:
    old = approved(client, app)
    make(client)
    new = approved(client, app)

    preview = client.get("/api/exports/preview", params={"profile": "entries_csv"}).json()
    assert (preview["entry_count"], preview["skipped_already_exported"]) == (1, 1)

    second = make(client)
    assert (
        second.json()["export"]["entry_count"] == 1
        and second.json()["skipped_already_exported"] == 1
    )
    assert status_of(client, new) == "exported"

    nothing = make(client)
    assert nothing.status_code == 422  # everything left is already exported

    both = make(client, include_exported=True)
    assert both.status_code == 201 and both.json()["export"]["entry_count"] == 2
    assert both.json()["skipped_already_exported"] == 0
    assert (
        status_of(client, old) == "exported"
    )  # exported is final; including again changes nothing
    including = client.get(
        "/api/exports/preview", params={"profile": "entries_csv", "include_exported": True}
    ).json()
    assert including["entry_count"] == 2


def test_named_entries_are_exported_alone_and_a_bad_name_is_refused(
    client: TestClient, app: Any
) -> None:
    a, b = approved(client, app), approved(client, app)
    waiting = new_document(client, app)
    a_id, b_id = detail(client, a)["entry"]["id"], detail(client, b)["entry"]["id"]
    waiting_id = detail(client, waiting)["entry"]["id"]

    assert make(client, entry_ids=[waiting_id]).status_code == 422
    assert "Not approved" in make(client, entry_ids=[a_id, waiting_id]).json()["error"]["message"]
    assert make(client, entry_ids=[999_999]).status_code == 404
    assert make(client, entry_ids=[]).status_code == 422
    assert status_of(client, a) == "approved"  # a refused export changes nothing

    one = make(client, entry_ids=[b_id])
    assert one.status_code == 201 and one.json()["export"]["entry_count"] == 1
    assert (status_of(client, a), status_of(client, b)) == ("approved", "exported")


def test_an_exported_entry_cannot_be_reopened_or_edited(client: TestClient, app: Any) -> None:
    document_id = approved(client, app)
    make(client)
    reopen = client.post(f"/api/documents/{document_id}/reopen")
    assert reopen.status_code == 409 and reopen.json()["error"]["code"] == "illegal_transition"
    entry_id = detail(client, document_id)["entry"]["id"]
    assert client.patch(f"/api/entries/{entry_id}", json={"notes": "x"}).status_code == 409


# --- hostile data ------------------------------------------------------------------------------


def test_text_that_would_run_as_a_formula_reaches_the_file_as_text(
    client: TestClient, app: Any
) -> None:
    document_id = approved(client, app, label="=cmd|' /C calc'!A0")
    entry_id = detail(client, document_id)["entry"]["id"]
    # approved documents cannot be edited, so reopen, change, approve again
    client.post(f"/api/documents/{document_id}/reopen")
    (line,) = detail(client, document_id)["entry"]["lines"]
    patched = client.patch(
        f"/api/entries/{entry_id}",
        json={
            "invoice_number": "-1+1",
            "po_number": "@SUM(1+1)",
            "lines": [{"id": line["id"], "description": '=HYPERLINK("http://evil.example.com")'}],
        },
    )
    assert patched.status_code == 200
    approve = client.post(f"/api/documents/{document_id}/approve", json={})
    assert approve.status_code == 200, approve.text

    for profile, text_columns in (
        ("entries_csv", ("vendor", "invoice_number", "po_number")),
        ("lines_csv", ("vendor", "invoice_number", "description")),
    ):
        export = make(client, profile=profile, include_exported=True).json()["export"]
        (row,) = read(client, export["id"])
        for column in text_columns:
            assert row[column].startswith("'"), (profile, column, row[column])
        assert row["vendor"] == "'=cmd|' /C calc'!A0"
    raw = client.get(export["download_url"]).text
    assert "\n=" not in raw and ",=" not in raw  # no cell begins with the trigger


# --- the file and the record are one thing -----------------------------------------------------


def test_a_failure_while_recording_leaves_no_export_no_file_and_the_entries_approved(
    client: TestClient, app: Any, settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    document_id = approved(client, app)

    def explode(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("disk problem")

    monkeypatch.setattr(repo, "add_export_items", explode)
    quiet = TestClient(app, base_url=HOST, raise_server_exceptions=False)
    assert quiet.post("/api/exports", json={"profile": "entries_csv"}).status_code == 500
    monkeypatch.undo()

    assert status_of(client, document_id) == "approved"
    assert client.get("/api/exports").json() == []
    folder = Path(settings.data_dir) / "exports"
    assert not folder.exists() or list(folder.iterdir()) == []
    assert make(client).status_code == 201  # and it can be done properly afterwards


def test_a_changed_or_missing_file_is_never_served(
    client: TestClient, app: Any, settings: Any
) -> None:
    approved(client, app)
    export = make(client).json()["export"]
    path = Path(settings.data_dir) / "exports" / f"{export['id']}.csv"
    path.write_bytes(path.read_bytes() + b"tampered\r\n")
    changed = client.get(export["download_url"])
    assert changed.status_code == 409 and changed.json()["error"]["code"] == "export_file_changed"
    path.unlink()
    assert client.get(export["download_url"]).status_code == 404
    assert client.get("/api/exports/9999/download").status_code == 404


def test_the_audit_trail_records_the_export_with_numbers_only(client: TestClient, app: Any) -> None:
    approved(client, app, label="Secret Vendor Name")
    export = make(client).json()["export"]
    connection = db(app)
    rows = connection.execute(
        "SELECT payload FROM audit_events WHERE event_type = 'export_created'"
    ).fetchall()
    connection.close()
    (row,) = rows
    assert "Secret" not in row["payload"] and "citetally_" not in row["payload"]
    import json

    assert json.loads(row["payload"]) == {
        "export_id": export["id"], "profile": "entries_csv", "entry_count": 1, "row_count": 1,
    }  # fmt: skip


def test_the_history_lists_newest_first(client: TestClient, app: Any) -> None:
    approved(client, app)
    first = make(client).json()["export"]["id"]
    approved(client, app)
    second = make(client, profile="lines_csv").json()["export"]["id"]
    history = client.get("/api/exports").json()
    assert [e["id"] for e in history] == [second, first]
    assert history[0]["profile"] == "lines_csv" and history[0]["row_count"] == 1


def test_a_foreign_website_cannot_create_an_export(client: TestClient, app: Any) -> None:
    document_id = approved(client, app)
    response = client.post(
        "/api/exports",
        json={"profile": "entries_csv"},
        headers={"Origin": "http://evil.example.com"},
    )
    assert response.status_code == 403
    assert status_of(client, document_id) == "approved"
