"""Shared by the API tests: a running app on fakes, and small helpers for the usual steps."""

from __future__ import annotations

import itertools
from typing import Any

from fastapi.testclient import TestClient

from citetally import repository as repo
from citetally.matching import normalize_name
from tests.test_pipeline import GOOD, LINES, pdf

HOST = "http://127.0.0.1"
_counter = itertools.count(1)


def worker(app: Any) -> Any:
    return app.state.citetally.worker


def queue_reply(app: Any, **changes: Any) -> None:
    worker(app).services().provider.replies.append({**GOOD, **changes})


def db(app: Any) -> Any:
    return app.state.citetally.database.connect()


def new_document(
    client: TestClient, app: Any, *, extra_lines: tuple[str, ...] = (), **changes: Any
) -> int:
    """Upload a distinct invoice, let the worker process it, and return its document id."""
    n = next(_counter)
    fields = {"invoice_number": f"INV-{n}", **changes}
    queue_reply(app, **fields)
    page = [
        line.replace("INV-20417", fields["invoice_number"]).replace(
            GOOD["vendor_name"], fields.get("vendor_name", GOOD["vendor_name"])
        )
        for line in LINES
    ]
    body = client.post(
        "/api/documents", files=[("files", (f"a{n}.pdf", pdf([*page, *extra_lines, f"copy {n}"])))]
    )
    document_id = body.json()["results"][0]["document_id"]
    assert worker(app).drain() >= 1
    return int(document_id)


def detail(client: TestClient, document_id: int) -> dict[str, Any]:
    response = client.get(f"/api/documents/{document_id}")
    assert response.status_code == 200
    return dict(response.json())


def check(body: dict[str, Any], code: str) -> dict[str, Any]:
    return next(c for c in body["checks"] if c["check_code"] == code)


def known_vendor(app: Any, name: str = "Northfield Pet Supply Co.") -> int:
    connection = db(app)
    try:
        food = repo.get_category_by_code(connection, "FOOD")
        return repo.create_vendor(
            connection, name, normalize_name(name), default_category_id=food.id
        ).id
    finally:
        connection.close()
