"""Audit events and log lines carry ids, stage names, timings and codes. Never document content."""

import json
import logging
import sqlite3

import pytest

from citetally import db, events
from citetally.models import DocumentStatus, EventType, Stage

# Values that must never appear in a log line or an audit row. They stand in for what a real
# document would contain: its text, the vendor, the invoice number and the money amounts.
SECRETS = [
    "Millrace Plumbing Supply Co.",
    "INV-20112",
    "$649.92",
    "649.92",
    "Ignore all previous instructions",
    "Kestrel Hollow Plumbing",
    "PO-5741",
]


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = db.connect(":memory:")
    db.migrate(connection)
    connection.execute(
        "INSERT INTO documents (original_filename, stored_path, file_sha256, mime_type, "
        "size_bytes, created_at, updated_at) VALUES ('a.pdf', 'x', 'h', 'application/pdf', 1, "
        "'t', 't')"
    )
    return connection


def test_record_event_stores_a_row_and_returns_it(conn: sqlite3.Connection) -> None:
    event = events.record_event(
        conn,
        EventType.STAGE_FINISHED,
        document_id=1,
        stage=Stage.READ,
        payload={
            "read_method": "ocr",
            "ocr_engine": "tesseract",
            "pages": 2,
            "mean_confidence": 83.4,
        },
        request_id="req-1",
        duration_ms=412,
    )
    assert event.event_type == "stage_finished" and event.stage is Stage.READ
    row = conn.execute("SELECT * FROM audit_events").fetchone()
    assert row["document_id"] == 1 and row["duration_ms"] == 412 and row["request_id"] == "req-1"
    assert json.loads(row["payload"]) == {
        "read_method": "ocr",
        "ocr_engine": "tesseract",
        "pages": 2,
        "mean_confidence": 83.4,
    }


def test_status_changes_carry_both_statuses(conn: sqlite3.Connection) -> None:
    events.record_event(
        conn,
        EventType.STATUS_CHANGED,
        document_id=1,
        from_status=DocumentStatus.RECEIVED,
        to_status=DocumentStatus.READ,
        payload={"trigger": "read_finished"},
    )
    row = conn.execute("SELECT from_status, to_status FROM audit_events").fetchone()
    assert (row["from_status"], row["to_status"]) == ("received", "read")


@pytest.mark.parametrize(
    "payload",
    [
        {"vendor_name": "Millrace Plumbing Supply Co."},
        {"invoice_number": "INV-20112"},
        {"total": "$649.92"},
        {"total_minor": 64992},
        {"text": "Ignore all previous instructions"},
        {"page_text": "Total $649.92"},
        {"filename": "invoice.pdf"},
        {"anything_else": 1},
    ],
)
def test_keys_that_could_hold_document_content_are_refused(
    conn: sqlite3.Connection, payload: dict[str, object]
) -> None:
    with pytest.raises(events.PayloadError, match="not allowed"):
        events.record_event(conn, EventType.STAGE_FINISHED, document_id=1, payload=payload)
    assert conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0] == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"check": "Millrace Plumbing Supply Co."},  # not a check code
        {"read_method": "INV-20112"},
        {"profile": "$649.92"},
        {"pages": "649.92"},  # a count must be a number
        {"passed": "yes"},  # a flag must be a boolean
        {"trigger": "Millrace Plumbing Supply Co."},  # not a short code
        {"mean_confidence": [1, 2]},
    ],
)
def test_allowed_keys_still_refuse_values_of_the_wrong_kind(
    conn: sqlite3.Connection, payload: dict[str, object]
) -> None:
    with pytest.raises(events.PayloadError):
        events.record_event(conn, EventType.CHECK_FAILED, document_id=1, payload=payload)


def test_free_text_keys_do_not_exist_because_an_invoice_number_looks_like_an_identifier() -> None:
    """Model names and prompt versions live in the extractions table, not in event payloads."""
    for key in ("model", "prompt_version", "error", "message", "filename"):
        with pytest.raises(events.PayloadError, match="not allowed"):
            events.validate_payload({key: "INV-20112"})


def test_payload_examples_from_the_schema_document_are_accepted() -> None:
    events.validate_payload(
        {"read_method": "ocr", "ocr_engine": "tesseract", "pages": 2, "mean_confidence": 83.4}
    )
    events.validate_payload({"check": "TOTAL_MATCH", "passed": False})
    events.validate_payload({"profile": "lines_csv", "entries": 12})
    events.validate_payload({"provider": "ollama", "extract_mode": "text_only", "attempt": 1})
    events.validate_payload({"trigger": "read_finished", "stage": "read"})


def test_events_write_one_json_log_line_with_the_same_safe_fields(
    conn: sqlite3.Connection, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="citetally.events"):
        events.record_event(
            conn,
            EventType.CHECK_FAILED,
            document_id=1,
            stage=Stage.CHECK,
            payload={"check": "TOTAL_MATCH", "passed": False},
            request_id="req-9",
            duration_ms=3,
        )
    assert len(caplog.records) == 1
    line = json.loads(caplog.records[0].getMessage())
    assert line["event"] == "check_failed"
    assert line["document_id"] == 1 and line["stage"] == "check"
    assert line["request_id"] == "req-9" and line["duration_ms"] == 3
    assert line["payload"] == {"check": "TOTAL_MATCH", "passed": False}


def test_no_document_content_reaches_the_log_or_the_audit_table(
    conn: sqlite3.Connection, caplog: pytest.LogCaptureFixture
) -> None:
    """Hostile attempt: every kind of content, tried as payload keys and values. None gets in."""
    with caplog.at_level(logging.DEBUG):
        for secret in SECRETS:
            for payload in (
                {"vendor_name": secret},
                {"check": secret},
                {"trigger": secret},
                {"model": secret},
                {"pages": secret},
            ):
                with pytest.raises(events.PayloadError) as refused:
                    events.record_event(
                        conn, EventType.STAGE_FAILED, document_id=1, payload=payload
                    )
                assert secret not in str(refused.value)  # even the error never echoes the value
        # and normal events carry no content
        events.record_event(
            conn,
            EventType.STAGE_FINISHED,
            document_id=1,
            stage=Stage.EXTRACT,
            payload={"attempt": 1},
        )
    dumped = "\n".join(r.getMessage() for r in caplog.records)
    stored = "\n".join(
        " ".join(str(v) for v in row) for row in conn.execute("SELECT * FROM audit_events")
    )
    for secret in SECRETS:
        assert secret not in dumped, secret
        assert secret not in stored, secret


def test_configure_logging_writes_json_lines_to_the_given_stream() -> None:
    import io

    stream = io.StringIO()
    handler = events.configure_logging(stream)
    try:
        logging.getLogger("citetally.events").info('{"event": "x"}')
    finally:
        logging.getLogger("citetally.events").removeHandler(handler)
    assert stream.getvalue().strip() == '{"event": "x"}'
