"""The HTTP API end to end with fakes: every route, every decision, every refusal."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from citetally import repository as repo
from tests.api_support import (
    HOST,
    db,
    detail,
    new_document,
    queue_reply,
    worker,
)
from tests.test_pipeline import pdf

# --- every response has a request id, errors have one shape ------------------------------------


def test_a_request_id_is_made_echoed_and_never_taken_from_a_hostile_value(
    client: TestClient,
) -> None:
    made = client.get("/api/status").headers["x-request-id"]
    assert len(made) >= 8
    assert (
        client.get("/api/status", headers={"X-Request-ID": "abc-12345678"}).headers["x-request-id"]
        == "abc-12345678"
    )
    hostile = client.get("/api/status", headers={"X-Request-ID": 'x y"<script>'}).headers
    assert hostile["x-request-id"] != 'x y"<script>'


def test_every_error_has_the_same_shape_with_the_request_id(client: TestClient) -> None:
    for response in (
        client.get("/api/documents/9999"),
        client.get("/api/nothing-here"),
        client.post("/api/documents/1/reprocess", json={"from_stage": "nope"}),
    ):
        error = response.json()["error"]
        assert {"code", "message", "request_id"} <= set(error)
        assert error["request_id"] == response.headers["x-request-id"]
    assert client.get("/api/documents/9999").json()["error"]["code"] == "not_found"
    assert client.get("/api/nothing-here").status_code == 404


def test_validation_errors_name_the_fields_but_never_echo_the_values(client: TestClient) -> None:
    secret = "SECRET-VALUE-123"
    response = client.post("/api/vendors", json={"name": "", "default_currency": secret})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_request"
    assert set(error["details"]["fields"]) == {"name", "default_currency"}
    assert secret not in response.text


def test_an_unexpected_failure_is_a_plain_500_without_details(
    client: TestClient, app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(repo, "list_documents_page", explode)
    quiet = TestClient(app, base_url=HOST, raise_server_exceptions=False)
    response = quiet.get("/api/documents")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret" not in response.text


def test_responses_are_not_cached_and_not_sniffed(client: TestClient) -> None:
    headers = client.get("/api/status").headers
    assert headers["cache-control"] == "no-store"
    assert headers["x-content-type-options"] == "nosniff"


# --- the API answers only local callers --------------------------------------------------------


def test_a_foreign_host_name_is_refused(app: Any) -> None:
    other = TestClient(app, base_url="http://evil.example.com")
    assert other.get("/api/status").status_code == 400


def test_a_change_from_another_website_is_refused_but_the_web_app_is_allowed(
    client: TestClient,
) -> None:
    foreign = client.post(
        "/api/vendors", json={"name": "X"}, headers={"Origin": "http://evil.example.com"}
    )
    assert foreign.status_code == 403 and foreign.json()["error"]["code"] == "foreign_origin"
    assert client.get("/api/vendors").json() == []  # nothing was created
    ours = client.post(
        "/api/vendors", json={"name": "X"}, headers={"Origin": "http://127.0.0.1:5175"}
    )
    assert ours.status_code == 201
    local = client.post(
        "/api/vendors", json={"name": "Y"}, headers={"Origin": "http://localhost:8200"}
    )
    assert local.status_code == 201


# --- upload ------------------------------------------------------------------------------------


def test_an_uploaded_file_is_queued_then_processed_into_the_review_queue(
    client: TestClient, app: Any
) -> None:
    queue_reply(app)
    response = client.post(
        "/api/documents", files=[("files", ("inv.pdf", pdf()))], data={"batch_label": " march "}
    )
    assert response.status_code == 200
    (result,) = response.json()["results"]
    assert (result["outcome"], result["status"], result["filename"]) == (
        "accepted",
        "received",
        "inv.pdf",
    )
    assert client.get("/api/status").json()["queue_depth"] == 1

    assert worker(app).drain() == 1
    body = detail(client, result["document_id"])
    assert body["document"]["status"] == "needs_review"
    assert body["document"]["batch_label"] == "march"
    assert client.get("/api/status").json()["queue_depth"] == 0
    assert client.get("/api/status").json()["last_model_call_at"] is not None


def test_each_file_gets_its_own_outcome_and_one_bad_file_stops_no_other(
    client: TestClient, app: Any
) -> None:
    queue_reply(app)
    response = client.post(
        "/api/documents",
        files=[
            ("files", ("notes.txt", b"just words")),
            ("files", ("inv.pdf", pdf())),
            ("files", ("again.pdf", pdf())),
        ],
    )
    first, second, third = response.json()["results"]
    assert (first["outcome"], first["document_id"]) == ("rejected", None)
    assert "not a PDF" in first["message"]
    assert second["outcome"] == "accepted"
    assert (third["outcome"], third["status"]) == ("duplicate", "duplicate")


def test_a_file_over_the_size_limit_fails_that_document_with_a_plain_reason(
    client: TestClient,
) -> None:
    big = b"%PDF-1.4\n" + b"0" * (1024 * 1024 + 10)
    (result,) = client.post("/api/documents", files=[("files", ("big.pdf", big))]).json()["results"]
    assert result["outcome"] == "failed" and "larger than the 1 MB limit" in result["message"]


def test_too_many_files_in_one_request_are_refused(client: TestClient) -> None:
    files = [("files", (f"{i}.txt", b"x")) for i in range(51)]
    response = client.post("/api/documents", files=files)
    assert response.status_code == 413 and response.json()["error"]["code"] == "too_many_files"


def test_an_upload_with_no_files_is_invalid(client: TestClient) -> None:
    assert client.post("/api/documents").status_code == 422


def test_a_hostile_filename_is_kept_for_display_only(client: TestClient, app: Any) -> None:
    queue_reply(app)
    client.post("/api/documents", files=[("files", ("../../etc/<b>x</b>.pdf", pdf()))])
    worker(app).drain()
    name = client.get("/api/documents").json()["items"][0]["original_filename"]
    assert "/" not in name and "\\" not in name and ".." not in name


# --- list --------------------------------------------------------------------------------------


def test_the_list_is_newest_first_and_pages_with_a_cursor(client: TestClient, app: Any) -> None:
    ids = [new_document(client, app) for _ in range(3)]
    first = client.get("/api/documents", params={"limit": 2}).json()
    assert [d["id"] for d in first["items"]] == [ids[2], ids[1]]
    assert first["next_cursor"] is not None
    second = client.get(
        "/api/documents", params={"limit": 2, "cursor": first["next_cursor"]}
    ).json()
    assert [d["id"] for d in second["items"]] == [ids[0]] and second["next_cursor"] is None


def test_list_rows_carry_what_the_queue_screen_needs(client: TestClient, app: Any) -> None:
    document_id = new_document(client, app)
    (row,) = client.get("/api/documents").json()["items"]
    assert row["id"] == document_id and row["status"] == "needs_review"
    assert (row["vendor_name"], row["total_minor"], row["currency"]) == (
        "Northfield Pet Supply Co.", 15200, "USD",
    )  # fmt: skip
    assert row["unresolved_checks"] == ["UNKNOWN_VENDOR"]
    assert "stored_path" not in row and "file_sha256" not in row


def test_a_search_treats_percent_and_underscore_as_plain_characters(
    client: TestClient, app: Any
) -> None:
    new_document(client, app)
    assert client.get("/api/documents", params={"q": "%"}).json()["items"] == []
    assert client.get("/api/documents", params={"q": "_"}).json()["items"] == []


def test_a_bad_cursor_or_filter_is_refused(client: TestClient) -> None:
    assert client.get("/api/documents", params={"cursor": "abc"}).status_code == 422
    assert client.get("/api/documents", params={"status": "nope"}).status_code == 422
    assert client.get("/api/documents", params={"limit": 0}).status_code == 422
    assert client.get("/api/documents", params={"limit": 500}).status_code == 422


# --- detail and page pictures ------------------------------------------------------------------


def test_the_detail_holds_everything_the_review_screen_shows(client: TestClient, app: Any) -> None:
    body = detail(client, new_document(client, app))
    assert set(body) == {
        "document", "pages", "extraction", "entry", "evidence", "checks", "edits", "reviews",
        "history",
    }  # fmt: skip
    assert body["entry"]["lines"][0]["amount_minor"] == 15200
    assert body["entry"]["category"] == "SUPPLIES"
    assert len(body["checks"]) == 14
    assert body["evidence"] and all(e["found"] for e in body["evidence"])
    assert body["extraction"]["prompt_version"] == "extract-v3"
    assert body["pages"][0]["image_url"].endswith("/pages/1/image")
    assert "words" not in body["pages"][0] and "image_path" not in body["pages"][0]
    assert {h["event_type"] for h in body["history"]} >= {"status_changed", "stage_finished"}
    dumped = json.dumps(body)
    assert "stored_path" not in dumped and "raw_response" not in dumped


def test_a_page_picture_is_served_as_a_png_and_only_for_a_real_page(
    client: TestClient, app: Any
) -> None:
    document_id = new_document(client, app)
    picture = client.get(f"/api/documents/{document_id}/pages/1/image")
    assert picture.status_code == 200 and picture.headers["content-type"] == "image/png"
    assert picture.content[:4] == b"\x89PNG"
    assert client.get(f"/api/documents/{document_id}/pages/2/image").status_code == 404
    assert client.get(f"/api/documents/{document_id}/pages/0/image").status_code == 404
    assert client.get("/api/documents/9999/pages/1/image").status_code == 404


def test_a_page_picture_outside_the_data_folder_is_never_served(
    client: TestClient, app: Any, tmp_path: Path
) -> None:
    document_id = new_document(client, app)
    outside = tmp_path / "secret.png"
    outside.write_bytes(b"\x89PNG not for you")
    connection = db(app)
    connection.execute(
        "UPDATE pages SET image_path = ? WHERE document_id = ?", ("../secret.png", document_id)
    )
    connection.close()
    assert client.get(f"/api/documents/{document_id}/pages/1/image").status_code == 404


# --- reprocess ---------------------------------------------------------------------------------


def test_reprocessing_from_extract_runs_the_model_again_and_keeps_the_pages(
    client: TestClient, app: Any
) -> None:
    document_id = new_document(client, app)
    queue_reply(app, vendor_name="Corrected Vendor Ltd")
    response = client.post(
        f"/api/documents/{document_id}/reprocess", json={"from_stage": "extract"}
    )
    assert response.status_code == 200 and response.json()["status"] == "read"
    worker(app).drain()
    body = detail(client, document_id)
    assert body["document"]["status"] == "needs_review"
    assert body["entry"]["vendor_name_raw"] == "Corrected Vendor Ltd"
    assert len(body["pages"]) == 1


def test_reprocessing_from_read_reads_the_pages_again(client: TestClient, app: Any) -> None:
    document_id = new_document(client, app)
    queue_reply(app)
    assert (
        client.post(f"/api/documents/{document_id}/reprocess", json={"from_stage": "read"}).json()[
            "status"
        ]
        == "received"
    )
    worker(app).drain()
    assert detail(client, document_id)["document"]["status"] == "needs_review"


def test_the_list_filters_by_status_check_batch_and_search(client: TestClient, app: Any) -> None:
    first = new_document(client, app)
    second = new_document(client, app, vendor_name="Lakeside Hardware")
    queue_reply(app)
    files = [("files", ("waiting.pdf", pdf(["Other file"])))]
    client.post("/api/documents", files=files, data={"batch_label": "b1"})

    def ids(**params: Any) -> list[int]:
        items = client.get("/api/documents", params=params).json()["items"]
        return [d["id"] for d in items]

    (waiting,) = ids(status="received")
    assert set(ids(status="needs_review")) == {first, second}
    assert set(ids(check="UNKNOWN_VENDOR")) == {first, second}
    assert ids(check="LINE_MATH") == []
    assert ids(batch="b1") == [waiting]
    assert ids(q="lakeside") == [second]
    assert set(ids(q="INV-")) == {first, second}
    assert ids(q="waiting") == [waiting]


def test_a_document_that_cannot_go_back_is_refused_with_the_reason(
    client: TestClient, app: Any
) -> None:
    approved = new_document(client, app)
    entry_id = detail(client, approved)["entry"]["id"]
    client.post(f"/api/entries/{entry_id}/vendor", json={"create": True})
    assert client.post(f"/api/documents/{approved}/approve", json={}).status_code == 200
    response = client.post(f"/api/documents/{approved}/reprocess", json={"from_stage": "extract"})
    assert response.status_code == 409 and response.json()["error"]["code"] == "illegal_transition"

    queue_reply(app)
    waiting = client.post("/api/documents", files=[("files", ("w.pdf", pdf(["x"])))]).json()[
        "results"
    ][0]
    again = client.post(
        f"/api/documents/{waiting['document_id']}/reprocess", json={"from_stage": "read"}
    )
    assert again.status_code == 409  # nothing has been made yet that could be redone
    assert (
        client.post("/api/documents/9999/reprocess", json={"from_stage": "read"}).status_code == 404
    )
