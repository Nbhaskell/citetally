"""Failure drills (Phase 9): break the things the app depends on and check what happens.

Each drill is a written promise from `docs/TRD.md` section 14 and `docs/APP_FLOW.md` 4.8 and 6:
the document ends in a plain status with a plain reason, other documents are not held up, nothing
that was uploaded is lost, and a retry (reprocess) or a restart gets it moving again. The model
drills run the real `OllamaProvider` against a small local server that misbehaves on purpose, and
the Tesseract drill uses the real OCR wrapper pointed at a program that is not there.
"""

from __future__ import annotations

import errno
import json
import socket
import sqlite3
import threading
import time
from collections.abc import Iterator
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from citetally import db, ingest, pipeline
from citetally import repository as repo
from citetally.api import create_app
from citetally.config import Settings
from citetally.models import DocumentStatus as S
from citetally.models import Stage
from citetally.pipeline import Services
from citetally.providers import FakeProvider
from citetally.providers.ollama import OllamaProvider
from citetally.reading.ocr import FakeOcr, TesseractOcr
from tests.api_support import HOST, queue_reply, worker
from tests.test_ingest import image_bytes
from tests.test_pipeline import GOOD, LINES, pdf

# ---- a model server that misbehaves on purpose -------------------------------------------------


class Stub(ThreadingHTTPServer):
    """Answers /api/chat the way `mode` says: ok, drop, partial, garbage or hang."""

    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), Handler)
        self.mode = "ok"
        self.calls = 0
        self.release = threading.Event()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}"


class Handler(BaseHTTPRequestHandler):
    server: Stub

    def log_message(self, *args: Any) -> None:  # keep the test output quiet
        pass

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.server.calls += 1
        mode = self.server.mode
        if mode == "drop":  # the model process was killed: the connection just closes
            self.connection.shutdown(socket.SHUT_RDWR)
            return
        if mode == "hang":
            self.server.release.wait(15)
            return
        if mode == "partial":  # killed halfway through writing the answer
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "5000")
            self.end_headers()
            self.wfile.write(b'{"message": {"content": "{\\"entry_ty')
            self.wfile.flush()
            self.connection.shutdown(socket.SHUT_RDWR)
            return
        body = b"<html>502 Bad Gateway</html>"
        if mode == "ok":
            body = json.dumps({"message": {"content": json.dumps(GOOD)}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def stub() -> Iterator[Stub]:
    server = Stub()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.release.set()
    server.shutdown()
    server.server_close()


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = db.connect(":memory:")
    db.migrate(connection)
    db.seed_categories(connection)
    return connection


class Killed:
    """A model call during which the whole program is stopped."""

    name = "ollama"
    model = "fake-model"
    supports_vision = False

    def generate_json(self, **_: Any) -> Any:
        raise SystemExit


def settings_in(tmp_path: Path, **extra: Any) -> Settings:
    return Settings(
        _env_file=None,
        CITETALLY_DB_PATH=str(tmp_path / "t.db"),
        CITETALLY_DATA_DIR=str(tmp_path / "data"),
        CITETALLY_MAX_FILE_MB=1,
        **extra,
    )


def services_for(settings: Settings, provider: Any, ocr: Any = None) -> Services:
    return Services(
        settings=settings,
        ocr=ocr or FakeOcr(),
        provider=provider,
        isolate=False,
        today=date(2026, 6, 15),
    )


def receive(conn: sqlite3.Connection, settings: Settings, data: bytes, name: str = "a.pdf") -> int:
    result = ingest.ingest(conn, data, name, settings=settings, isolate=False)
    assert result.outcome == "accepted", result.document.failure_message
    return result.document.id


def plain(message: str | None) -> bool:
    """A reason fit for the screen: words, no exception names, no paths, no tracebacks."""
    return bool(message) and not any(
        mark in str(message) for mark in ("Traceback", "Error", "Exception", "\\", "/", "0x")
    )


# ---- the model dies, hangs or is not running ---------------------------------------------------


@pytest.mark.parametrize("mode", ["drop", "partial", "garbage"])
def test_a_model_that_dies_mid_answer_fails_the_document_and_a_restart_recovers_it(
    conn: sqlite3.Connection, tmp_path: Path, stub: Stub, mode: str
) -> None:
    settings = settings_in(tmp_path)
    services = services_for(settings, OllamaProvider(stub.url, "qwen3:8b"))
    first = receive(conn, settings, pdf())
    second = receive(conn, settings, pdf([*LINES, "another page"]), "b.pdf")

    stub.mode = mode
    for document_id in (first, second):  # one failing document does not stop the next
        pipeline.process(conn, document_id, services)
    for document_id in (first, second):
        document = repo.get_document(conn, document_id)
        assert document.status is S.FAILED and document.failure_stage is Stage.EXTRACT
        assert plain(document.failure_message), document.failure_message
    assert stub.calls >= 2

    stub.mode = "ok"  # Ollama is started again; the reviewer presses Retry
    for document_id in (first, second):
        repo.change_status(conn, document_id, S.READ)
        pipeline.process(conn, document_id, services)
        assert repo.get_document(conn, document_id).status is S.NEEDS_REVIEW
    # the failed attempt left nothing behind: one entry per document, not two
    assert conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 2


def test_a_model_that_never_answers_is_stopped_at_the_timeout(
    conn: sqlite3.Connection, tmp_path: Path, stub: Stub
) -> None:
    settings = settings_in(tmp_path).model_copy(update={"extract_timeout_s": 1})
    services = services_for(settings, OllamaProvider(stub.url, "qwen3:8b"))
    document_id = receive(conn, settings, pdf())
    stub.mode = "hang"
    started = time.monotonic()
    pipeline.process(conn, document_id, services)
    assert time.monotonic() - started < 10
    document = repo.get_document(conn, document_id)
    assert document.status is S.FAILED and document.failure_stage is Stage.EXTRACT
    assert "too long" in str(document.failure_message) and plain(document.failure_message)


def test_a_model_that_is_not_running_says_so_and_the_queue_keeps_moving(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    with socket.socket() as probe:  # a port nobody listens on
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    settings = settings_in(tmp_path)
    services = services_for(settings, OllamaProvider(f"http://127.0.0.1:{port}", "qwen3:8b"))
    ids = [receive(conn, settings, pdf([*LINES, f"copy {n}"]), f"{n}.pdf") for n in range(3)]
    for document_id in ids:
        pipeline.process(conn, document_id, services)
    for document_id in ids:
        document = repo.get_document(conn, document_id)
        assert document.status is S.FAILED and document.failure_stage is Stage.EXTRACT
        assert "not running" in str(document.failure_message)


# ---- Tesseract is missing ----------------------------------------------------------------------


def test_without_tesseract_a_scan_fails_at_read_with_an_install_hint_and_a_digital_pdf_still_works(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    settings = settings_in(tmp_path)
    missing = TesseractOcr(str(tmp_path / "no-such-folder" / "tesseract.exe"))
    services = services_for(settings, FakeProvider([GOOD, GOOD]), missing)
    scan = receive(conn, settings, image_bytes("PNG"), "scan.png")
    digital = receive(conn, settings, pdf())

    pipeline.process(conn, scan, services)
    failed = repo.get_document(conn, scan)
    assert failed.status is S.FAILED and failed.failure_stage is Stage.READ
    assert "Tesseract" in str(failed.failure_message) and plain(failed.failure_message)

    pipeline.process(conn, digital, services)  # its own text layer needs no OCR
    assert repo.get_document(conn, digital).status is S.NEEDS_REVIEW


def test_the_status_screen_reports_a_missing_tesseract(tmp_path: Path) -> None:
    settings = settings_in(tmp_path, TESSERACT_CMD=str(tmp_path / "gone" / "tesseract.exe"))
    app = create_app(settings, autostart_worker=False, isolate_ingest=False)
    with TestClient(app, base_url=HOST) as client:
        body = client.get("/api/status").json()
    assert body["ocr_available"] is False


# ---- the disk is full or a page is damaged -----------------------------------------------------


def full_disk(*args: Any, **kwargs: Any) -> Any:
    raise OSError(errno.ENOSPC, "No space left on device")


def test_a_full_disk_at_upload_gives_each_file_its_own_plain_outcome_and_loses_nothing_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = settings_in(tmp_path)
    app = create_app(
        settings, services=services_for(settings, FakeProvider([GOOD])), autostart_worker=False,
        isolate_ingest=False,
    )  # fmt: skip
    with TestClient(app, base_url=HOST, raise_server_exceptions=False) as client:
        good = client.post("/api/documents", files=[("files", ("ok.pdf", pdf()))])
        assert good.status_code == 200

        monkeypatch.setattr(ingest, "store_original", full_disk)
        response = client.post(
            "/api/documents",
            files=[("files", ("a.pdf", pdf(["a"]))), ("files", ("b.pdf", pdf(["b"])))],
        )
        assert response.status_code == 200, response.text
        outcomes = response.json()["results"]
        assert [o["outcome"] for o in outcomes] == ["rejected", "rejected"]
        assert all(plain(o["message"]) and "disk" in o["message"].lower() for o in outcomes)

        monkeypatch.undo()  # space is freed: the same file can be uploaded again
        again = client.post("/api/documents", files=[("files", ("a.pdf", pdf(["a"])))])
        assert again.json()["results"][0]["outcome"] == "accepted"
        statuses = [d["status"] for d in client.get("/api/documents").json()["items"]]
        assert sorted(statuses) == ["received", "received"]  # nothing half-made was left behind


def test_a_full_disk_while_writing_the_page_pictures_fails_the_document_not_the_request(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = settings_in(tmp_path)
    monkeypatch.setattr(Path, "write_bytes", full_disk)
    result = ingest.ingest(conn, pdf(), "a.pdf", settings=settings, isolate=False)
    monkeypatch.undo()
    document = repo.get_document(conn, result.document.id)
    assert result.outcome == "failed"
    assert document.status is S.FAILED and document.failure_stage is Stage.INGEST
    assert plain(document.failure_message)
    assert (settings.data_dir / document.stored_path).exists()  # the upload itself is kept


@pytest.mark.parametrize("damage", ["garbage", "missing", "empty"])
def test_a_corrupt_or_missing_page_picture_fails_that_document_at_read_and_not_the_next(
    conn: sqlite3.Connection, tmp_path: Path, damage: str
) -> None:
    settings = settings_in(tmp_path)
    services = services_for(settings, FakeProvider([GOOD, GOOD]))
    broken = receive(conn, settings, pdf())
    fine = receive(conn, settings, pdf([*LINES, "second"]), "b.pdf")
    page = settings.data_dir / "pages" / str(broken) / "1.png"
    match damage:
        case "garbage":
            page.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        case "missing":
            page.unlink()
        case _:
            page.write_bytes(b"")
    pipeline.process(conn, broken, services)
    pipeline.process(conn, fine, services)
    document = repo.get_document(conn, broken)
    assert document.status is S.FAILED and document.failure_stage is Stage.READ
    assert plain(document.failure_message), document.failure_message
    assert repo.get_document(conn, fine).status is S.NEEDS_REVIEW


# ---- the app is stopped with work in the queue -------------------------------------------------


def test_documents_waiting_when_the_app_stops_are_picked_up_when_it_starts_again(
    tmp_path: Path,
) -> None:
    settings = settings_in(tmp_path)
    first = create_app(
        settings, services=services_for(settings, FakeProvider()), autostart_worker=False,
        isolate_ingest=False,
    )  # fmt: skip
    with TestClient(first, base_url=HOST) as client:
        for n in range(3):
            body = client.post(
                "/api/documents", files=[("files", (f"{n}.pdf", pdf([*LINES, f"copy {n}"])))]
            )
            assert body.json()["results"][0]["status"] == "received"
        # the app is stopped here: nothing was drained

    second = create_app(
        settings, services=services_for(settings, FakeProvider([GOOD] * 3)),
        autostart_worker=False, isolate_ingest=False,
    )  # fmt: skip
    with TestClient(second, base_url=HOST) as client:
        assert worker(second).depth == 3
        assert worker(second).drain() == 3
        items = client.get("/api/documents").json()["items"]
        assert sorted(d["status"] for d in items) == ["needs_review"] * 3


def test_a_document_interrupted_after_reading_resumes_at_extraction_without_double_pages(
    tmp_path: Path,
) -> None:
    settings = settings_in(tmp_path)
    app = create_app(
        settings, services=services_for(settings, FakeProvider()), autostart_worker=False,
        isolate_ingest=False,
    )  # fmt: skip
    with TestClient(app, base_url=HOST) as client:
        client.post("/api/documents", files=[("files", ("a.pdf", pdf()))])
        worker(app).services().provider = Killed()  # the app dies once the read has been saved
        with pytest.raises(SystemExit):
            worker(app).drain()
        connection = app.state.citetally.database.connect()
        try:
            assert repo.get_document(connection, 1).status is S.READ
        finally:
            connection.close()

    again = create_app(
        settings, services=services_for(settings, FakeProvider([GOOD])), autostart_worker=False,
        isolate_ingest=False,
    )  # fmt: skip
    with TestClient(again, base_url=HOST):
        assert worker(again).depth == 1 and worker(again).drain() == 1
        connection = again.state.citetally.database.connect()
        try:
            assert repo.get_document(connection, 1).status is S.NEEDS_REVIEW
            assert connection.execute("SELECT COUNT(*) FROM pages").fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 1
        finally:
            connection.close()


def test_reading_and_asking_the_model_again_replace_the_earlier_results(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    settings = settings_in(tmp_path)
    services = services_for(settings, FakeProvider([GOOD, GOOD, GOOD]))
    document_id = receive(conn, settings, pdf())
    for _ in range(3):
        pipeline.process(conn, document_id, services)
        assert repo.get_document(conn, document_id).status is S.NEEDS_REVIEW
        repo.change_status(conn, document_id, S.RECEIVED)
    pipeline.process(conn, document_id, services_for(settings, FakeProvider([GOOD])))
    for table in ("pages", "entries"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 1, table
    assert queue_reply is not None  # imported for the API drills above
