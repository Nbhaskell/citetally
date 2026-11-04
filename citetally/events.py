"""Structured events: one audit row and one JSON log line per event. No document content, ever.

Document text, vendor names, invoice numbers and amounts must not appear in logs or in
`audit_events` (CLAUDE.md rule 6). This is enforced by what a payload may contain: a short list
of keys, each with a closed vocabulary or a number or a flag. There is deliberately no key for
free text, because an invoice number or a vendor name looks like any other identifier. Errors
name the key that was refused, never the value.
"""

from __future__ import annotations

import json
import logging
import math
import sqlite3
import sys
from collections.abc import Mapping
from enum import StrEnum
from typing import IO, Any

from citetally.db import now
from citetally.models import (
    AuditEvent,
    CheckCode,
    Decision,
    DocumentStatus,
    EventType,
    ExportProfile,
    ExtractMode,
    Provider,
    ReadMethod,
    Stage,
)
from citetally.statemachine import TRIGGERS

logger = logging.getLogger("citetally.events")

_ENUM_KEYS: dict[str, type[StrEnum]] = {
    "read_method": ReadMethod,
    "check": CheckCode,
    "profile": ExportProfile,
    "provider": Provider,
    "extract_mode": ExtractMode,
    "decision": Decision,
    "stage": Stage,
}
_CLOSED_KEYS: dict[str, frozenset[str]] = {
    "ocr_engine": frozenset(
        {"tesseract", "rapidocr", "tesseract+rapidocr"}
    ),  # add an engine here when one is added
    "trigger": TRIGGERS,
}
_NUMBER_KEYS = frozenset(
    {
        "pages", "word_count", "mean_confidence", "attempt", "input_tokens", "output_tokens",
        "entries", "rows", "entry_count", "row_count", "other_document_id", "export_id",
        "failed_checks", "overrides", "review_seconds", "count",
    }
)  # fmt: skip
_FLAG_KEYS = frozenset({"passed", "edited", "found"})


class PayloadError(ValueError):
    """The payload holds a key or a value that events do not allow."""


def validate_payload(payload: Mapping[str, object]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in payload.items():
        if key in _ENUM_KEYS:
            if not isinstance(value, str) or value not in {m.value for m in _ENUM_KEYS[key]}:
                raise PayloadError(f"The value for '{key}' is not one of its allowed codes.")
        elif key in _CLOSED_KEYS:
            if not isinstance(value, str) or value not in _CLOSED_KEYS[key]:
                raise PayloadError(f"The value for '{key}' is not one of its allowed codes.")
        elif key in _NUMBER_KEYS:
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise PayloadError(f"The value for '{key}' must be a number.")
            if isinstance(value, float) and not math.isfinite(value):
                raise PayloadError(f"The value for '{key}' must be a finite number.")
        elif key in _FLAG_KEYS:
            if not isinstance(value, bool):
                raise PayloadError(f"The value for '{key}' must be true or false.")
        else:
            raise PayloadError(f"The payload key '{key}' is not allowed.")
        clean[key] = value
    return clean


def record_event(
    connection: sqlite3.Connection,
    event_type: EventType,
    *,
    document_id: int | None = None,
    stage: Stage | None = None,
    from_status: DocumentStatus | None = None,
    to_status: DocumentStatus | None = None,
    payload: Mapping[str, object] | None = None,
    request_id: str | None = None,
    duration_ms: int | None = None,
) -> AuditEvent:
    """Validate, store in `audit_events`, and log one line. Returns the stored event."""
    clean = validate_payload(payload or {})
    text = json.dumps(clean, sort_keys=True)
    cursor = connection.execute(
        "INSERT INTO audit_events (document_id, event_type, stage, from_status, to_status, "
        "payload, request_id, duration_ms, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            document_id,
            event_type.value,
            stage.value if stage else None,
            from_status.value if from_status else None,
            to_status.value if to_status else None,
            text,
            request_id,
            duration_ms,
            now(),
        ),
    )
    row = connection.execute(
        "SELECT * FROM audit_events WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()
    event = AuditEvent.model_validate(dict(row))
    logger.info(
        json.dumps(
            {
                "event": event.event_type,
                "document_id": document_id,
                "stage": event.stage.value if event.stage else None,
                "from_status": event.from_status.value if event.from_status else None,
                "to_status": event.to_status.value if event.to_status else None,
                "request_id": request_id,
                "duration_ms": duration_ms,
                "payload": clean,
            },
            sort_keys=True,
        )
    )
    return event


def configure_logging(stream: IO[str] | None = None) -> logging.Handler:
    """Send event lines, as bare JSON, to a stream (stderr by default). Returns the handler."""
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return handler
