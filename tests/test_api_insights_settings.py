"""Insights, editable settings and the self-test, through the API."""

from __future__ import annotations

import itertools
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from citetally import insights as insight_queries
from citetally.api import create_app
from citetally.config import Settings
from tests.api_support import HOST, db, detail, new_document

_numbers = itertools.count(1)


def approved(
    client: TestClient,
    app: Any,
    *,
    seconds: int | None = None,
    edit: bool = False,
    **changes: Any,
) -> int:
    """A document through the pipeline with its own vendor, approved."""
    n = next(_numbers)
    name = changes.setdefault("vendor_name", f"Insight Vendor {n} Ltd")
    document_id = new_document(client, app, **changes)
    entry = detail(client, document_id)["entry"]
    known = {v["name"]: v["id"] for v in client.get("/api/vendors").json()}
    choice = {"vendor_id": known[name]} if name in known else {"create": True, "name": name}
    assert client.post(f"/api/entries/{entry['id']}/vendor", json=choice).status_code == 200
    if edit:
        fixed = client.patch(f"/api/entries/{entry['id']}", json={"po_number": "PO-7"})
        assert fixed.status_code == 200, fixed.text
    body: dict[str, Any] = {"review_seconds": seconds} if seconds is not None else {}
    done = client.post(f"/api/documents/{document_id}/approve", json=body)
    assert done.status_code == 200, done.text
    return document_id


def insights(client: TestClient, **params: str) -> dict[str, Any]:
    response = client.get("/api/insights", params=params)
    assert response.status_code == 200, response.text
    return dict(response.json())


# --- insights ----------------------------------------------------------------------------------


def test_an_empty_desk_gives_empty_summaries_not_errors(client: TestClient) -> None:
    body = insights(client)
    assert body["by_category"] == [] and body["by_vendor"] == []
    assert body["approved_documents"] == 0 and body["edited_documents"] == 0
    assert body["review_seconds_median"] is None and body["review_seconds_count"] == 0
    assert [b["bucket"] for b in body["waiting_by_age"]] == [
        "under_1_day",
        "1_to_3_days",
        "3_to_7_days",
        "over_7_days",
    ]
    assert all(b["documents"] == 0 for b in body["waiting_by_age"])


def test_spending_is_summed_by_category_and_vendor_with_credit_notes_negative(
    client: TestClient, app: Any
) -> None:
    approved(client, app, vendor_name="Alpha Tools")
    approved(client, app, vendor_name="Gamma Paint")
    approved(client, app, vendor_name="Beta Pipes", entry_type="credit_note")
    body = insights(client)
    assert [(r["label"], r["total_minor"], r["entries"]) for r in body["by_vendor"]] == [
        ("Alpha Tools", 15200, 1),
        ("Beta Pipes", -15200, 1),
        ("Gamma Paint", 15200, 1),
    ]
    category = body["by_category"]
    assert len(category) == 1 and category[0]["total_minor"] == 15200
    assert category[0]["entries"] == 3 and category[0]["currency"] == "USD"


def test_a_document_still_waiting_does_not_count_as_spending(client: TestClient, app: Any) -> None:
    new_document(client, app)
    assert insights(client)["by_vendor"] == []


def test_the_period_limits_spending_by_the_date_printed_on_the_document(
    client: TestClient, app: Any
) -> None:
    approved(client, app)  # dated 14 March 2026
    assert len(insights(client, date_from="2026-03-01", date_to="2026-03-31")["by_vendor"]) == 1
    assert insights(client, date_from="2026-04-01")["by_vendor"] == []
    assert insights(client, date_to="2026-03-13")["by_vendor"] == []
    assert len(insights(client, date_from="2026-03-14", date_to="2026-03-14")["by_vendor"]) == 1


def test_a_bad_period_is_refused(client: TestClient) -> None:
    assert client.get("/api/insights", params={"date_from": "March"}).status_code == 422
    backwards = client.get(
        "/api/insights", params={"date_from": "2026-05-01", "date_to": "2026-04-01"}
    )
    assert backwards.status_code == 422 and backwards.json()["error"]["code"] == "bad_period"


def test_waiting_documents_are_grouped_by_how_long_they_have_waited(
    client: TestClient, app: Any
) -> None:
    ids = [new_document(client, app) for _ in range(4)]
    now = datetime.now(UTC)
    connection = db(app)
    for document_id, days in zip(ids, (0.2, 2, 5, 30), strict=True):
        stamp = (now - timedelta(days=days)).isoformat()
        connection.execute("UPDATE documents SET created_at = ? WHERE id = ?", (stamp, document_id))
    connection.close()
    by = {b["bucket"]: b["documents"] for b in insights(client)["waiting_by_age"]}
    assert by == {"under_1_day": 1, "1_to_3_days": 1, "3_to_7_days": 1, "over_7_days": 1}


def test_edited_documents_and_the_fields_edited_most_often(client: TestClient, app: Any) -> None:
    approved(client, app, edit=True)
    approved(client, app, edit=True)
    approved(client, app)
    body = insights(client)
    assert body["approved_documents"] == 3 and body["edited_documents"] == 2
    assert body["edited_fields"] == [{"field": "po_number", "edits": 2}]


def test_checks_failing_now_and_how_many_were_accepted_with_a_reason(
    client: TestClient, app: Any
) -> None:
    approved(client, app)  # the vendor was chosen, so nothing blocks
    waiting = new_document(client, app, invoice_number="")
    body = insights(client)
    failing = {c["check_code"]: c for c in body["checks_failing"]}
    assert failing["REQUIRED_FIELDS"]["documents"] >= 1
    connection = db(app)
    connection.execute(
        "UPDATE checks SET overridden = 1, override_reason = 'checked' "
        "WHERE document_id = ? AND check_code = 'REQUIRED_FIELDS'",
        (waiting,),
    )
    connection.close()
    again = {c["check_code"]: c for c in insights(client)["checks_failing"]}
    assert again["REQUIRED_FIELDS"]["overridden"] == 1


def test_median_review_time_uses_only_decisions_that_recorded_a_time(
    client: TestClient, app: Any
) -> None:
    approved(client, app, seconds=30)
    approved(client, app, seconds=90)
    approved(client, app, seconds=600)
    approved(client, app)  # no time recorded
    body = insights(client)
    assert body["review_seconds_median"] == 90 and body["review_seconds_count"] == 3


def test_the_summaries_hold_no_document_text(client: TestClient, app: Any) -> None:
    """Vendor names are the only free text, and they come from the person's own vendor list."""
    approved(client, app, vendor_name="Alpha Tools")
    body = insights(client)
    assert "invoice_number" not in str(body) and "INV-" not in str(body)


def test_ages_work_without_a_time_zone_on_the_stamp() -> None:
    assert insight_queries._parse("2026-03-14T10:00:00") is not None
    assert insight_queries._parse("not a date") is None


# --- settings ----------------------------------------------------------------------------------


def test_settings_show_what_is_read_only_and_what_can_be_changed(client: TestClient) -> None:
    body = client.get("/api/settings").json()
    assert body["status"]["model_provider"] == "ollama" and body["status"]["hosted_mode"] is False
    assert body["allow_hosted"] is False and body["extract_mode"] == "text_only"
    assert (
        body["values"]
        == body["defaults"]
        == {
            "default_currency": "USD",
            "locale": "en-US",
            "duplicate_date_window_days": 7,
            "outlier_ratio": "3",
            "low_confidence": 75.0,
        }
    )
    assert "en-GB" in body["locales"] and body["locales"] == sorted(body["locales"])


def test_a_saved_setting_takes_effect_and_survives_a_restart(
    client: TestClient, app: Any, settings: Settings
) -> None:
    changed = client.patch(
        "/api/settings",
        json={"locale": "en-GB", "duplicate_date_window_days": 14, "outlier_ratio": "2.5"},
    )
    assert changed.status_code == 200
    assert changed.json()["values"]["locale"] == "en-GB"
    assert changed.json()["values"]["outlier_ratio"] == "2.5"
    assert changed.json()["defaults"]["locale"] == "en-US"  # the environment's value is kept apart
    assert app.state.citetally.settings.duplicate_date_window_days == 14
    # the same values come back in a fresh app on the same database
    other = create_app(settings, autostart_worker=False, isolate_ingest=False)
    with TestClient(other, base_url=HOST) as again:
        assert again.get("/api/settings").json()["values"]["locale"] == "en-GB"
        assert again.get("/api/settings").json()["values"]["duplicate_date_window_days"] == 14


def test_a_value_put_back_to_the_default_is_no_longer_stored(client: TestClient, app: Any) -> None:
    client.patch("/api/settings", json={"low_confidence": 60})
    assert client.get("/api/settings").json()["values"]["low_confidence"] == 60
    client.patch("/api/settings", json={"low_confidence": 75})
    connection = db(app)
    stored = connection.execute("SELECT COUNT(*) FROM settings").fetchone()[0]
    connection.close()
    assert stored == 0


def test_a_refused_value_changes_nothing_not_even_the_valid_ones_sent_with_it(
    client: TestClient, app: Any
) -> None:
    refused = client.patch(
        "/api/settings", json={"duplicate_date_window_days": 3, "locale": "xx-XX"}
    )
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "invalid_setting"
    assert "locale" in refused.json()["error"]["message"]
    assert client.get("/api/settings").json()["values"]["duplicate_date_window_days"] == 7
    for body in (
        {"outlier_ratio": "1"},
        {"outlier_ratio": "abc"},
        {"outlier_ratio": "2.555"},
        {"outlier_ratio": "101"},
        {"low_confidence": 0},
        {"duplicate_date_window_days": 61},
        {"default_currency": "usd"},
        {"max_pages": 3},  # not an editable setting
    ):
        assert client.patch("/api/settings", json=body).status_code == 422, body


def test_a_changed_setting_is_used_by_the_next_document_the_worker_checks(
    client: TestClient, app: Any
) -> None:
    new_document(client, app)  # builds the worker's services
    client.patch("/api/settings", json={"default_currency": "EUR"})
    assert app.state.citetally.worker.services().settings.default_currency == "EUR"


def test_an_unusable_saved_value_is_ignored_at_start_instead_of_stopping_the_app(
    settings: Settings,
) -> None:
    first = create_app(settings, autostart_worker=False, isolate_ingest=False)
    with TestClient(first, base_url=HOST) as client:
        connection = db(first)
        connection.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES ('locale', 'zz-ZZ', 'x')"
        )
        connection.commit()
        connection.close()
    second = create_app(settings, autostart_worker=False, isolate_ingest=False)
    with TestClient(second, base_url=HOST) as client:
        assert client.get("/api/settings").json()["values"]["locale"] == "en-US"


def test_foreign_websites_cannot_change_settings(client: TestClient) -> None:
    refused = client.patch(
        "/api/settings", json={"locale": "en-GB"}, headers={"Origin": "http://evil.example.com"}
    )
    assert refused.status_code == 403
    assert client.get("/api/settings").json()["values"]["locale"] == "en-US"


# --- self-test ---------------------------------------------------------------------------------


def test_the_self_test_passes_and_names_what_each_sample_set_off(client: TestClient) -> None:
    body = client.post("/api/self-test").json()
    assert body["passed"] is True and len(body["results"]) >= 10
    by_name = {r["name"]: r for r in body["results"]}
    assert by_name["A clean invoice"]["fired"] == []
    assert by_name["A total that is wrong"]["fired"] == ["TOTAL_MATCH"]
    assert by_name["A page that gives orders"]["fired"] == ["SUSPICIOUS_TEXT"]


def test_the_self_test_follows_the_settings_in_force(client: TestClient) -> None:
    for change in (
        {"duplicate_date_window_days": 0},
        {"duplicate_date_window_days": 60},
        {"outlier_ratio": "1.5"},
        {"outlier_ratio": "50"},
        {"low_confidence": 10},
        {"low_confidence": 99},
    ):
        client.patch("/api/settings", json=change)
        body = client.post("/api/self-test").json()
        assert body["passed"] is True, (change, [r for r in body["results"] if not r["passed"]])


def test_the_self_test_changes_nothing(client: TestClient, app: Any) -> None:
    before = db(app).execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    client.post("/api/self-test")
    assert db(app).execute("SELECT COUNT(*) FROM documents").fetchone()[0] == before
