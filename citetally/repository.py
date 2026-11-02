"""Reading and writing the database through rules. Every write goes through here.

Status changes are the only way a document's status moves, and they follow the state machine,
check the data rules (an entry exists, blocking checks are resolved) and leave an audit event in
the same transaction. Amounts are integer minor units and decimals are exact strings; a float or a
symbol is refused before it reaches the database. Names of columns written to are fixed lists in
this file, never taken from input.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel

from citetally import events
from citetally import statemachine as sm
from citetally.db import now, transaction
from citetally.models import (
    BLOCKING_CHECKS,
    AuditEvent,
    Category,
    CategorySource,
    Check,
    CheckCode,
    Decision,
    Document,
    EditField,
    Entry,
    EntryLine,
    EntryType,
    EventType,
    Evidence,
    Export,
    ExportProfile,
    Extraction,
    ExtractMode,
    FieldEdit,
    HeaderField,
    LineField,
    Page,
    Provider,
    ReadMethod,
    Review,
    Stage,
    Vendor,
    VendorAlias,
    VendorMatchMethod,
    Word,
    is_blocking,
)
from citetally.models import DocumentStatus as S


class RepositoryError(Exception):
    """A write was refused because it breaks a rule."""


class NotFound(RepositoryError):
    """The row asked for does not exist."""


class ApprovalBlocked(RepositoryError):
    """Blocking checks are unresolved, so the document cannot be approved."""

    def __init__(self, codes: list[CheckCode]) -> None:
        self.codes = codes
        super().__init__(
            "Blocking checks are not resolved: " + ", ".join(code.value for code in codes)
        )


# ---- helpers ----------------------------------------------------------------------------------


def _one[T: BaseModel](
    conn: sqlite3.Connection, model: type[T], sql: str, params: Sequence[Any] = ()
) -> T | None:
    row = conn.execute(sql, params).fetchone()
    return None if row is None else model.model_validate(dict(row))


def _all[T: BaseModel](
    conn: sqlite3.Connection, model: type[T], sql: str, params: Sequence[Any] = ()
) -> list[T]:
    return [model.model_validate(dict(row)) for row in conn.execute(sql, params)]


def _required[T](value: T | None, what: str) -> T:
    if value is None:
        raise NotFound(f"{what} was not found.")
    return value


_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DECIMAL = re.compile(r"^-?\d+(\.\d+)?$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")


def _minor(name: str, value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise RepositoryError(f"{name} must be a whole number of minor units, never a float.")
    return value


def _iso_date(name: str, value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _ISO_DATE.match(value):
        raise RepositoryError(f"{name} must be a date written YYYY-MM-DD.")
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise RepositoryError(f"{name} is not a real date.") from error
    return value


def _currency(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _CURRENCY.match(value):
        raise RepositoryError("currency must be a three-letter code such as USD.")
    return value


def _decimal_text(name: str, value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _DECIMAL.match(value):
        raise RepositoryError(f"{name} must be an exact decimal string such as '2.5'.")
    try:
        Decimal(value)
    except InvalidOperation as error:  # pragma: no cover - the pattern already excludes this
        raise RepositoryError(f"{name} is not a number.") from error
    return value


def _score(name: str, value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise RepositoryError(f"{name} must be a number.")
    return float(value)


# ---- categories, vendors, settings ------------------------------------------------------------


def list_categories(conn: sqlite3.Connection) -> list[Category]:
    return _all(conn, Category, "SELECT * FROM categories ORDER BY id")


def get_category_by_code(conn: sqlite3.Connection, code: str) -> Category:
    row = _one(conn, Category, "SELECT * FROM categories WHERE code = ?", (code,))
    return _required(row, f"Category {code}")


def create_vendor(
    conn: sqlite3.Connection,
    name: str,
    normalized_name: str,
    *,
    default_category_id: int | None = None,
    default_currency: str | None = None,
    is_synthetic: bool = True,
) -> Vendor:
    cursor = conn.execute(
        "INSERT INTO vendors (name, normalized_name, default_category_id, default_currency, "
        "is_synthetic, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            name,
            normalized_name,
            default_category_id,
            _currency(default_currency),
            int(is_synthetic),
            now(),
        ),
    )
    return _required(
        _one(conn, Vendor, "SELECT * FROM vendors WHERE id = ?", (cursor.lastrowid,)), "Vendor"
    )


def add_alias(conn: sqlite3.Connection, vendor_id: int, alias: str, normalized_alias: str) -> None:
    conn.execute(
        "INSERT INTO vendor_aliases (vendor_id, alias, normalized_alias, created_at) "
        "VALUES (?, ?, ?, ?)",
        (vendor_id, alias, normalized_alias, now()),
    )


def list_vendors(conn: sqlite3.Connection, *, active_only: bool = True) -> list[Vendor]:
    where = " WHERE is_active = 1" if active_only else ""
    return _all(conn, Vendor, f"SELECT * FROM vendors{where} ORDER BY id")


def vendor_usage(conn: sqlite3.Connection) -> dict[int, tuple[int, int, str | None]]:
    """Per vendor: entries on documents not rejected, how many still wait for review, and the
    latest entry date."""
    rows = conn.execute(
        "SELECT e.vendor_id AS vendor_id, COUNT(*) AS entries, "
        "SUM(d.status = 'needs_review') AS waiting, MAX(e.entry_date) AS last_date "
        "FROM entries e JOIN documents d ON d.id = e.document_id "
        "WHERE e.vendor_id IS NOT NULL AND d.status != 'rejected' GROUP BY e.vendor_id"
    )
    return {
        int(r["vendor_id"]): (int(r["entries"]), int(r["waiting"] or 0), r["last_date"])
        for r in rows
    }


def set_vendor_category(conn: sqlite3.Connection, vendor_id: int, category_id: int | None) -> None:
    conn.execute(
        "UPDATE vendors SET default_category_id = ? WHERE id = ?", (category_id, vendor_id)
    )


def list_aliases(conn: sqlite3.Connection) -> list[VendorAlias]:
    return _all(conn, VendorAlias, "SELECT * FROM vendor_aliases ORDER BY id")


def find_vendor_by_normalized(conn: sqlite3.Connection, normalized: str) -> Vendor | None:
    """The vendor whose normalized name or alias equals `normalized`."""
    return _one(
        conn,
        Vendor,
        "SELECT v.* FROM vendors v WHERE v.normalized_name = ? "
        "UNION SELECT v.* FROM vendors v JOIN vendor_aliases a ON a.vendor_id = v.id "
        "WHERE a.normalized_alias = ? LIMIT 1",
        (normalized, normalized),
    )


def get_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return None if row is None else str(row["value"])


def delete_setting(conn: sqlite3.Connection, key: str) -> None:
    conn.execute("DELETE FROM settings WHERE key = ?", (key,))


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (key, value, now()),
    )


# ---- documents --------------------------------------------------------------------------------


def create_document(
    conn: sqlite3.Connection,
    *,
    original_filename: str,
    stored_path: str,
    file_sha256: str,
    mime_type: str,
    size_bytes: int,
    batch_label: str | None = None,
    is_synthetic: bool = True,
) -> Document:
    stamp = now()
    cursor = conn.execute(
        "INSERT INTO documents (original_filename, stored_path, file_sha256, mime_type, "
        "size_bytes, batch_label, is_synthetic, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            original_filename, stored_path, file_sha256, mime_type, size_bytes, batch_label,
            int(is_synthetic), stamp, stamp,
        ),
    )  # fmt: skip
    return get_document(conn, int(cursor.lastrowid or 0))


def get_document(conn: sqlite3.Connection, document_id: int) -> Document:
    row = _one(conn, Document, "SELECT * FROM documents WHERE id = ?", (document_id,))
    return _required(row, f"Document {document_id}")


def find_documents_by_sha(conn: sqlite3.Connection, file_sha256: str) -> list[Document]:
    return _all(
        conn, Document, "SELECT * FROM documents WHERE file_sha256 = ? ORDER BY id", (file_sha256,)
    )


def list_documents(conn: sqlite3.Connection, status: S | None = None) -> list[Document]:
    if status is None:
        return _all(conn, Document, "SELECT * FROM documents ORDER BY id")
    return _all(
        conn,
        Document,
        "SELECT * FROM documents WHERE status = ? ORDER BY created_at, id",
        (status.value,),
    )


def list_review_queue(conn: sqlite3.Connection) -> list[Document]:
    """Needs attention first: failed documents, then the oldest waiting for review."""
    return _all(
        conn,
        Document,
        "SELECT d.* FROM documents d WHERE d.status IN ('needs_review','failed') "
        "ORDER BY CASE d.status WHEN 'failed' THEN 0 ELSE 1 END, d.created_at ASC, d.id ASC",
    )


def set_document_info(
    conn: sqlite3.Connection, document_id: int, *, source_kind: str | None, page_count: int | None
) -> Document:
    from citetally.models import SourceKind

    get_document(conn, document_id)
    conn.execute(
        "UPDATE documents SET source_kind = ?, page_count = ?, updated_at = ? WHERE id = ?",
        (SourceKind(source_kind).value if source_kind else None, page_count, now(), document_id),
    )
    return get_document(conn, document_id)


def _clear_for_reprocess(conn: sqlite3.Connection, document_id: int, target: S) -> None:
    """Throw away what the stages being re-run produced. Extraction attempts stay as history."""
    conn.execute("DELETE FROM checks WHERE document_id = ?", (document_id,))
    conn.execute("DELETE FROM entries WHERE document_id = ?", (document_id,))
    if target is S.RECEIVED:
        conn.execute("DELETE FROM pages WHERE document_id = ?", (document_id,))


def change_status(
    conn: sqlite3.Connection,
    document_id: int,
    target: S,
    *,
    failure_stage: Stage | None = None,
    failure_message: str | None = None,
    duplicate_of: int | None = None,
    request_id: str | None = None,
) -> Document:
    """Move a document to a new status, or raise and change nothing."""
    with transaction(conn):
        document = get_document(conn, document_id)
        source = document.status
        sm.check_transition(source, target, failure_stage=failure_stage, duplicate_of=duplicate_of)

        if target is S.FAILED and not (failure_message or "").strip():
            raise RepositoryError("Failing a document needs a plain reason for the person reading.")
        if (
            target in {S.EXTRACTED, S.NEEDS_REVIEW, S.APPROVED}
            and get_entry_for_document(conn, document_id) is None
        ):
            raise RepositoryError(f"A document needs an entry before it becomes {target.value}.")
        if target is S.APPROVED:
            unresolved = unresolved_blocking(conn, document_id)
            if unresolved:
                raise ApprovalBlocked(unresolved)
        if target is S.DUPLICATE:
            assert duplicate_of is not None
            if duplicate_of == document_id:
                raise RepositoryError("A document cannot be a duplicate of itself.")
            get_document(conn, duplicate_of)
        if sm.is_reprocess(source, target):
            _clear_for_reprocess(conn, document_id, target)

        failing = target is S.FAILED
        conn.execute(
            "UPDATE documents SET status = ?, duplicate_of = ?, failure_stage = ?, "
            "failure_message = ?, updated_at = ? WHERE id = ?",
            (
                target.value,
                duplicate_of if target is S.DUPLICATE else document.duplicate_of,
                failure_stage.value if failing and failure_stage else None,
                failure_message.strip() if failing and failure_message else None,
                now(),
                document_id,
            ),
        )
        events.record_event(
            conn,
            EventType.STATUS_CHANGED,
            document_id=document_id,
            stage=failure_stage if failing else None,
            from_status=source,
            to_status=target,
            payload={"trigger": sm.trigger_for(source, target, failure_stage)},
            request_id=request_id,
        )
    return get_document(conn, document_id)


# ---- pages and extractions --------------------------------------------------------------------


def add_page(
    conn: sqlite3.Connection,
    document_id: int,
    *,
    page_number: int,
    image_path: str,
    width_px: int,
    height_px: int,
    read_method: ReadMethod,
    words: Sequence[Mapping[str, Any]],
    text: str,
    ocr_engine: str | None = None,
    mean_confidence: float | None = None,
    skew_degrees: float | None = None,
    alt_words: Sequence[Sequence[Mapping[str, Any]]] = (),
) -> Page:
    checked = [Word.model_validate(dict(word)).model_dump() for word in words]
    checked_alt = [
        [Word.model_validate(dict(w)).model_dump() for w in reading] for reading in alt_words
    ]
    cursor = conn.execute(
        "INSERT INTO pages (document_id, page_number, image_path, width_px, height_px, "
        "read_method, ocr_engine, mean_confidence, skew_degrees, word_count, words, text, "
        "created_at, alt_words) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            document_id,
            page_number,
            image_path,
            width_px,
            height_px,
            ReadMethod(read_method).value,
            ocr_engine,
            mean_confidence,
            skew_degrees,
            len(checked),
            json.dumps(checked),
            text,
            now(),
            json.dumps(checked_alt),
        ),
    )
    return _required(
        _one(conn, Page, "SELECT * FROM pages WHERE id = ?", (cursor.lastrowid,)), "Page"
    )


def clear_pages(conn: sqlite3.Connection, document_id: int) -> None:
    """Remove a document's pages so the read stage can be run again from nothing."""
    conn.execute("DELETE FROM pages WHERE document_id = ?", (document_id,))


def list_pages(conn: sqlite3.Connection, document_id: int) -> list[Page]:
    return _all(
        conn, Page, "SELECT * FROM pages WHERE document_id = ? ORDER BY page_number", (document_id,)
    )


def add_extraction(
    conn: sqlite3.Connection,
    document_id: int,
    *,
    provider: Provider,
    model: str,
    extract_mode: ExtractMode | str,
    prompt_version: str,
    fields: Mapping[str, Any],
    raw_response: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    duration_ms: int | None = None,
) -> Extraction:
    attempt = conn.execute(
        "SELECT COALESCE(MAX(attempt), 0) + 1 FROM extractions WHERE document_id = ?",
        (document_id,),
    ).fetchone()[0]
    cursor = conn.execute(
        "INSERT INTO extractions (document_id, attempt, provider, model, extract_mode, "
        "prompt_version, fields, raw_response, input_tokens, output_tokens, duration_ms, "
        "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            document_id, attempt, Provider(provider).value, model, ExtractMode(extract_mode).value,
            prompt_version, json.dumps(fields, sort_keys=True), raw_response, input_tokens,
            output_tokens, duration_ms, now(),
        ),
    )  # fmt: skip
    return _required(
        _one(conn, Extraction, "SELECT * FROM extractions WHERE id = ?", (cursor.lastrowid,)),
        "Extraction",
    )


def latest_extraction(conn: sqlite3.Connection, document_id: int) -> Extraction | None:
    return _one(
        conn,
        Extraction,
        "SELECT * FROM extractions WHERE document_id = ? ORDER BY attempt DESC LIMIT 1",
        (document_id,),
    )


# ---- entries and lines ------------------------------------------------------------------------

_ENTRY_COLUMNS = (
    "entry_type", "vendor_id", "vendor_name_raw", "vendor_match_method", "vendor_match_score",
    "invoice_number", "entry_date", "due_date", "po_number", "currency", "subtotal_minor",
    "tax_total_minor", "shipping_minor", "discount_minor", "total_minor", "category_id",
    "category_source", "notes",
)  # fmt: skip
_MONEY_COLUMNS = {
    "subtotal_minor",
    "tax_total_minor",
    "shipping_minor",
    "discount_minor",
    "total_minor",
}


def _entry_value(column: str, value: object) -> object:
    if column in _MONEY_COLUMNS:
        return _minor(column, value)
    if column in {"entry_date", "due_date"}:
        return _iso_date(column, value)
    if column == "currency":
        return _currency(value)
    if column == "vendor_match_score":
        return _score(column, value)
    if column == "entry_type":
        return EntryType(str(value)).value
    if column == "vendor_match_method":
        return None if value is None else VendorMatchMethod(str(value)).value
    if column == "category_source":
        return None if value is None else CategorySource(str(value)).value
    return value


def create_entry(
    conn: sqlite3.Connection,
    document_id: int,
    extraction_id: int,
    entry_type: EntryType,
    **fields: Any,
) -> Entry:
    unknown = set(fields) - set(_ENTRY_COLUMNS)
    if unknown:
        raise RepositoryError(f"Unknown entry fields: {', '.join(sorted(unknown))}.")
    columns = ["entry_type", *fields]
    values = [_entry_value("entry_type", entry_type), *(_entry_value(c, fields[c]) for c in fields)]
    stamp = now()
    cursor = conn.execute(
        f"INSERT INTO entries (document_id, extraction_id, {', '.join(columns)}, created_at, "
        f"updated_at) VALUES (?, ?, {', '.join('?' for _ in columns)}, ?, ?)",
        (document_id, extraction_id, *values, stamp, stamp),
    )
    return get_entry(conn, int(cursor.lastrowid or 0))


def get_entry(conn: sqlite3.Connection, entry_id: int) -> Entry:
    return _required(
        _one(conn, Entry, "SELECT * FROM entries WHERE id = ?", (entry_id,)), f"Entry {entry_id}"
    )


def clear_entry(conn: sqlite3.Connection, document_id: int) -> None:
    """Remove a document's entry (its lines, evidence and checks go with it)."""
    conn.execute("DELETE FROM checks WHERE document_id = ?", (document_id,))
    conn.execute("DELETE FROM entries WHERE document_id = ?", (document_id,))


def get_entry_for_document(conn: sqlite3.Connection, document_id: int) -> Entry | None:
    return _one(conn, Entry, "SELECT * FROM entries WHERE document_id = ?", (document_id,))


def update_entry(conn: sqlite3.Connection, entry_id: int, **changes: Any) -> Entry:
    bad = set(changes) - set(_ENTRY_COLUMNS)
    if bad or not changes:
        raise RepositoryError(
            f"These fields cannot be changed: {', '.join(sorted(bad)) or 'none given'}."
        )
    get_entry(conn, entry_id)
    assignments = ", ".join(f"{column} = ?" for column in changes)
    conn.execute(
        f"UPDATE entries SET {assignments}, updated_at = ? WHERE id = ?",
        (*(_entry_value(c, v) for c, v in changes.items()), now(), entry_id),
    )
    return get_entry(conn, entry_id)


@dataclass
class LineInput:
    description: str | None = None
    quantity: str | None = None
    unit_price: str | None = None
    amount_minor: int | None = None
    tax_rate: str | None = None


def replace_lines(conn: sqlite3.Connection, entry_id: int, lines: Sequence[LineInput]) -> None:
    checked = [
        (
            line.description,
            _decimal_text("quantity", line.quantity),
            _decimal_text("unit_price", line.unit_price),
            _minor("amount_minor", line.amount_minor),
            _decimal_text("tax_rate", line.tax_rate),
        )
        for line in lines
    ]
    get_entry(conn, entry_id)
    with transaction(conn):
        conn.execute("DELETE FROM entry_lines WHERE entry_id = ?", (entry_id,))
        for number, values in enumerate(checked, start=1):
            conn.execute(
                "INSERT INTO entry_lines (entry_id, line_number, description, quantity, "
                "unit_price, amount_minor, tax_rate, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (entry_id, number, *values, now()),
            )


def list_lines(conn: sqlite3.Connection, entry_id: int) -> list[EntryLine]:
    return _all(
        conn,
        EntryLine,
        "SELECT * FROM entry_lines WHERE entry_id = ? ORDER BY line_number",
        (entry_id,),
    )


# ---- evidence and edits -----------------------------------------------------------------------


def add_evidence(
    conn: sqlite3.Connection,
    entry_id: int,
    field: HeaderField | LineField,
    printed_text: str,
    found: bool,
    *,
    line_id: int | None = None,
    page_number: int | None = None,
    box: tuple[float, float, float, float] | None = None,
    match_score: float | None = None,
) -> Evidence:
    if box is not None:
        x0, y0, x1, y1 = box
        if not (0 <= x0 <= x1 <= 1 and 0 <= y0 <= y1 <= 1):
            raise RepositoryError(
                "The box must be fractions of the page with x0 <= x1 and y0 <= y1."
            )
    corners: tuple[float | None, float | None, float | None, float | None] = (
        box if box else (None, None, None, None)
    )
    cursor = conn.execute(
        "INSERT INTO evidence (entry_id, line_id, field, printed_text, found, page_number, "
        "x0, y0, x1, y1, match_score, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            entry_id, line_id, str(field.value), printed_text, int(found), page_number,
            *corners, match_score, now(),
        ),
    )  # fmt: skip
    return _required(
        _one(conn, Evidence, "SELECT * FROM evidence WHERE id = ?", (cursor.lastrowid,)), "Evidence"
    )


def clear_evidence(conn: sqlite3.Connection, entry_id: int) -> None:
    conn.execute("DELETE FROM evidence WHERE entry_id = ?", (entry_id,))


def list_evidence(conn: sqlite3.Connection, entry_id: int) -> list[Evidence]:
    return _all(
        conn, Evidence, "SELECT * FROM evidence WHERE entry_id = ? ORDER BY id", (entry_id,)
    )


def record_edit(
    conn: sqlite3.Connection,
    entry_id: int,
    field: EditField,
    old_value: str | None,
    new_value: str | None,
    *,
    line_id: int | None = None,
    reviewer: str = "local",
) -> FieldEdit:
    cursor = conn.execute(
        "INSERT INTO field_edits (entry_id, line_id, field, old_value, new_value, reviewer, "
        "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (entry_id, line_id, EditField(field).value, old_value, new_value, reviewer, now()),
    )
    return _required(
        _one(conn, FieldEdit, "SELECT * FROM field_edits WHERE id = ?", (cursor.lastrowid,)), "Edit"
    )


def field_correction_counts(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    """Which fields reviewers change most, most-changed first."""
    rows = conn.execute(
        "SELECT field, COUNT(*) AS n FROM field_edits GROUP BY field ORDER BY n DESC, field"
    )
    return [(row["field"], row["n"]) for row in rows]


# ---- checks -----------------------------------------------------------------------------------


def upsert_check(
    conn: sqlite3.Connection,
    document_id: int,
    code: CheckCode,
    *,
    passed: bool,
    detail: Mapping[str, Any],
    request_id: str | None = None,
) -> Check:
    """Record a check result. Running a check again clears any override on it."""
    get_document(conn, document_id)
    with transaction(conn):
        conn.execute(
            "INSERT INTO checks (document_id, check_code, blocking, passed, detail, overridden, "
            "created_at) VALUES (?, ?, ?, ?, ?, 0, ?) "
            "ON CONFLICT(document_id, check_code) DO UPDATE SET blocking = excluded.blocking, "
            "passed = excluded.passed, detail = excluded.detail, overridden = 0, "
            "override_reason = NULL, overridden_at = NULL, created_at = excluded.created_at",
            (
                document_id, CheckCode(code).value, int(is_blocking(code)), int(passed),
                json.dumps(detail, sort_keys=True), now(),
            ),
        )  # fmt: skip
        if not passed:
            events.record_event(
                conn,
                EventType.CHECK_FAILED,
                document_id=document_id,
                stage=Stage.CHECK,
                payload={"check": code.value, "passed": False},
                request_id=request_id,
            )
    return _required(
        _one(
            conn,
            Check,
            "SELECT * FROM checks WHERE document_id = ? AND check_code = ?",
            (document_id, code.value),
        ),
        "Check",
    )


def list_checks(conn: sqlite3.Connection, document_id: int) -> list[Check]:
    return _all(
        conn, Check, "SELECT * FROM checks WHERE document_id = ? ORDER BY id", (document_id,)
    )


def unresolved_blocking(conn: sqlite3.Connection, document_id: int) -> list[CheckCode]:
    """Blocking checks that have not run, or failed and were not overridden with a reason."""
    state = {
        row["check_code"]: row
        for row in conn.execute("SELECT * FROM checks WHERE document_id = ?", (document_id,))
    }
    unresolved: list[CheckCode] = []
    for code in CheckCode:
        if code not in BLOCKING_CHECKS:
            continue
        row = state.get(code.value)
        if row is None or not (row["passed"] or (row["overridden"] and row["override_reason"])):
            unresolved.append(code)
    return unresolved


def override_check(
    conn: sqlite3.Connection, document_id: int, code: CheckCode, *, reason: str
) -> Check:
    """Accept a failed blocking check, with a written reason."""
    if not reason.strip():
        raise RepositoryError("An override needs a written reason.")
    row = _one(
        conn,
        Check,
        "SELECT * FROM checks WHERE document_id = ? AND check_code = ?",
        (document_id, code.value),
    )
    check = _required(row, f"Check {code.value} for document {document_id}")
    if not check.blocking:
        raise RepositoryError(
            f"{code.value} is not a blocking check, so there is nothing to override."
        )
    if check.passed:
        raise RepositoryError(f"{code.value} passed, so there is nothing to override.")
    conn.execute(
        "UPDATE checks SET overridden = 1, override_reason = ?, overridden_at = ? "
        "WHERE document_id = ? AND check_code = ?",
        (reason.strip(), now(), document_id, code.value),
    )
    return _required(
        _one(
            conn,
            Check,
            "SELECT * FROM checks WHERE document_id = ? AND check_code = ?",
            (document_id, code.value),
        ),
        "Check",
    )


# ---- review decisions -------------------------------------------------------------------------

_DECISION_TARGET = {
    Decision.APPROVE: S.APPROVED,
    Decision.REJECT: S.REJECTED,
    Decision.REOPEN: S.NEEDS_REVIEW,
    Decision.MARK_DUPLICATE: S.DUPLICATE,
}


def record_review(
    conn: sqlite3.Connection,
    document_id: int,
    decision: Decision,
    *,
    reason: str | None = None,
    duplicate_of: int | None = None,
    review_seconds: int | None = None,
    reviewer: str = "local",
    request_id: str | None = None,
) -> Review:
    """Apply a reviewer's decision: change the status, store the review, log the event."""
    with transaction(conn):
        get_document(conn, document_id)
        if decision is Decision.REJECT and not (reason or "").strip():
            raise RepositoryError("A reason is required to reject a document.")
        if decision is Decision.MARK_DUPLICATE and duplicate_of is None:
            raise RepositoryError("Marking a duplicate needs duplicate_of, the original's id.")
        overrides = 0
        if decision is Decision.APPROVE:
            overrides = conn.execute(
                "SELECT COUNT(*) FROM checks "
                "WHERE document_id = ? AND blocking = 1 AND overridden = 1",
                (document_id,),
            ).fetchone()[0]
        last = conn.execute(
            "SELECT MAX(created_at) FROM reviews WHERE document_id = ?", (document_id,)
        ).fetchone()[0]
        entry = get_entry_for_document(conn, document_id)
        edited = False
        if entry is not None:
            edited = (
                conn.execute(
                    "SELECT 1 FROM field_edits WHERE entry_id = ? AND created_at > ? LIMIT 1",
                    (entry.id, last or ""),
                ).fetchone()
                is not None
            )

        change_status(
            conn,
            document_id,
            _DECISION_TARGET[decision],
            duplicate_of=duplicate_of if decision is Decision.MARK_DUPLICATE else None,
            request_id=request_id,
        )
        cursor = conn.execute(
            "INSERT INTO reviews (document_id, decision, reason, edited, overrides, reviewer, "
            "review_seconds, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                document_id, decision.value, reason.strip() if reason else None, int(edited),
                overrides, reviewer, review_seconds, now(),
            ),
        )  # fmt: skip
        payload: dict[str, Any] = {
            "decision": decision.value,
            "overrides": overrides,
            "edited": edited,
        }
        if review_seconds is not None:
            payload["review_seconds"] = review_seconds
        events.record_event(
            conn,
            EventType.REVIEW_RECORDED,
            document_id=document_id,
            payload=payload,
            request_id=request_id,
        )
    return _required(
        _one(conn, Review, "SELECT * FROM reviews WHERE id = ?", (cursor.lastrowid,)), "Review"
    )


# ---- queries from docs/BACKEND_SCHEMA.md section 5 --------------------------------------------


def find_duplicates_by_number(
    conn: sqlite3.Connection, vendor_id: int, invoice_number: str, *, exclude_document_id: int
) -> list[int]:
    rows = conn.execute(
        "SELECT e.document_id FROM entries e JOIN documents d ON d.id = e.document_id "
        "WHERE e.vendor_id = ? AND e.invoice_number = ? "
        "AND d.status NOT IN ('rejected','duplicate','failed') AND e.document_id <> ? "
        "ORDER BY e.document_id",
        (vendor_id, invoice_number, exclude_document_id),
    )
    return [row["document_id"] for row in rows]


def find_duplicates_by_content(
    conn: sqlite3.Connection,
    vendor_id: int,
    total_minor: int,
    currency: str,
    entry_date: str,
    window_days: int,
    *,
    exclude_document_id: int,
) -> list[int]:
    rows = conn.execute(
        "SELECT e.document_id FROM entries e JOIN documents d ON d.id = e.document_id "
        "WHERE e.vendor_id = ? AND e.total_minor = ? AND e.currency = ? "
        "AND ABS(julianday(e.entry_date) - julianday(?)) <= ? "
        "AND d.status NOT IN ('rejected','duplicate','failed') AND e.document_id <> ? "
        "ORDER BY e.document_id",
        (vendor_id, total_minor, currency, entry_date, window_days, exclude_document_id),
    )
    return [row["document_id"] for row in rows]


def vendor_history_totals(conn: sqlite3.Connection, vendor_id: int, currency: str) -> list[int]:
    """Totals of this vendor's approved or exported entries, for the outlier check."""
    rows = conn.execute(
        "SELECT e.total_minor FROM entries e JOIN documents d ON d.id = e.document_id "
        "WHERE e.vendor_id = ? AND e.currency = ? AND d.status IN ('approved','exported') "
        "AND e.total_minor IS NOT NULL ORDER BY e.document_id",
        (vendor_id, currency),
    )
    return [row["total_minor"] for row in rows]


@dataclass(frozen=True)
class SiblingEntry:
    """Another entry of the same vendor, as the duplicate check needs it."""

    document_id: int
    entry_type: str
    invoice_number: str | None
    total_minor: int | None
    currency: str | None
    entry_date: str | None


def sibling_entries(
    conn: sqlite3.Connection, vendor_id: int, *, exclude_document_id: int
) -> list[SiblingEntry]:
    """The vendor's other entries that are still live: not rejected, marked duplicate or failed."""
    rows = conn.execute(
        "SELECT e.document_id, e.entry_type, e.invoice_number, e.total_minor, e.currency, "
        "e.entry_date FROM entries e JOIN documents d ON d.id = e.document_id "
        "WHERE e.vendor_id = ? AND e.document_id <> ? "
        "AND d.status NOT IN ('rejected','duplicate','failed') ORDER BY e.document_id",
        (vendor_id, exclude_document_id),
    )
    return [SiblingEntry(**dict(row)) for row in rows]


@dataclass(frozen=True)
class PastEntry:
    total_minor: int | None
    subtotal_minor: int | None
    tax_total_minor: int | None


def approved_history(
    conn: sqlite3.Connection,
    vendor_id: int,
    currency: str,
    entry_type: EntryType,
    *,
    exclude_document_id: int,
) -> list[PastEntry]:
    """A vendor's approved or exported entries of one type and currency, oldest first."""
    rows = conn.execute(
        "SELECT e.total_minor, e.subtotal_minor, e.tax_total_minor FROM entries e "
        "JOIN documents d ON d.id = e.document_id "
        "WHERE e.vendor_id = ? AND e.currency = ? AND e.entry_type = ? AND e.document_id <> ? "
        "AND d.status IN ('approved','exported') ORDER BY e.document_id",
        (vendor_id, currency, EntryType(entry_type).value, exclude_document_id),
    )
    return [PastEntry(**dict(row)) for row in rows]


def get_vendor(conn: sqlite3.Connection, vendor_id: int) -> Vendor:
    return _required(
        _one(conn, Vendor, "SELECT * FROM vendors WHERE id = ?", (vendor_id,)), "Vendor"
    )


def list_audit_events(conn: sqlite3.Connection, document_id: int) -> list[AuditEvent]:
    return _all(
        conn,
        AuditEvent,
        "SELECT * FROM audit_events WHERE document_id = ? ORDER BY id",
        (document_id,),
    )


# ---- support for the API ----------------------------------------------------------------------


def get_category(conn: sqlite3.Connection, category_id: int) -> Category:
    return _required(
        _one(conn, Category, "SELECT * FROM categories WHERE id = ?", (category_id,)), "Category"
    )


def list_edits(conn: sqlite3.Connection, entry_id: int) -> list[FieldEdit]:
    return _all(
        conn, FieldEdit, "SELECT * FROM field_edits WHERE entry_id = ? ORDER BY id", (entry_id,)
    )


def list_reviews(conn: sqlite3.Connection, document_id: int) -> list[Review]:
    return _all(
        conn, Review, "SELECT * FROM reviews WHERE document_id = ? ORDER BY id", (document_id,)
    )


def list_vendor_aliases(conn: sqlite3.Connection, vendor_id: int) -> list[VendorAlias]:
    return _all(
        conn,
        VendorAlias,
        "SELECT * FROM vendor_aliases WHERE vendor_id = ? ORDER BY id",
        (vendor_id,),
    )


_LIKE_ESCAPE = chr(92)  # a backslash, given to SQLite as the ESCAPE character


def _like(text: str) -> str:
    """A pattern that matches `text` anywhere, with its own % and _ taken literally."""
    escaped = text.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
    escaped = escaped.replace("%", _LIKE_ESCAPE + "%").replace("_", _LIKE_ESCAPE + "_")
    return f"%{escaped}%"


def list_documents_page(
    conn: sqlite3.Connection,
    *,
    statuses: Sequence[S] = (),
    check: CheckCode | None = None,
    q: str | None = None,
    batch: str | None = None,
    cursor_id: int | None = None,
    oldest_first: bool = False,
    limit: int = 50,
) -> list[Document]:
    """Newest first, or oldest first; `cursor_id` is the last id of the previous page.

    `check` keeps documents where that check failed and was not overridden; `q` looks in the
    file name, printed vendor, vendor and invoice number."""
    where: list[str] = []
    params: list[Any] = []
    if statuses:
        where.append(f"d.status IN ({', '.join('?' for _ in statuses)})")
        params.extend(status.value for status in statuses)
    if batch is not None:
        where.append("d.batch_label = ?")
        params.append(batch)
    if check is not None:
        where.append(
            "EXISTS (SELECT 1 FROM checks c WHERE c.document_id = d.id AND c.check_code = ? "
            "AND c.passed = 0 AND c.overridden = 0)"
        )
        params.append(check.value)
    if q:
        where.append(
            "(d.original_filename LIKE ? ESCAPE ? OR e.vendor_name_raw LIKE ? ESCAPE ? "
            "OR e.invoice_number LIKE ? ESCAPE ? OR v.name LIKE ? ESCAPE ?)"
        )
        for _ in range(4):
            params.extend([_like(q), _LIKE_ESCAPE])
    if cursor_id is not None:
        where.append("d.id > ?" if oldest_first else "d.id < ?")
        params.append(cursor_id)
    clause = f" WHERE {' AND '.join(where)}" if where else ""
    return _all(
        conn,
        Document,
        "SELECT d.* FROM documents d LEFT JOIN entries e ON e.document_id = d.id "
        f"LEFT JOIN vendors v ON v.id = e.vendor_id{clause} "
        f"ORDER BY d.id {'ASC' if oldest_first else 'DESC'} LIMIT ?",
        (*params, limit),
    )


def get_line(conn: sqlite3.Connection, line_id: int) -> EntryLine:
    return _required(
        _one(conn, EntryLine, "SELECT * FROM entry_lines WHERE id = ?", (line_id,)), "Line"
    )


_LINE_COLUMNS = ("description", "quantity", "unit_price", "amount_minor", "tax_rate")


def update_line(conn: sqlite3.Connection, line_id: int, **changes: Any) -> EntryLine:
    bad = set(changes) - set(_LINE_COLUMNS)
    if bad or not changes:
        raise RepositoryError(
            f"These line fields cannot be changed: {', '.join(sorted(bad)) or 'none given'}."
        )
    get_line(conn, line_id)
    checked = {
        column: (
            _minor(column, value)
            if column == "amount_minor"
            else value
            if column == "description"
            else _decimal_text(column, value)
        )
        for column, value in changes.items()
    }
    assignments = ", ".join(f"{column} = ?" for column in checked)
    conn.execute(f"UPDATE entry_lines SET {assignments} WHERE id = ?", (*checked.values(), line_id))
    return get_line(conn, line_id)


def add_line(conn: sqlite3.Connection, entry_id: int, line: LineInput) -> EntryLine:
    get_entry(conn, entry_id)
    last = conn.execute(
        "SELECT COALESCE(MAX(line_number), 0) FROM entry_lines WHERE entry_id = ?", (entry_id,)
    ).fetchone()[0]
    cursor = conn.execute(
        "INSERT INTO entry_lines (entry_id, line_number, description, quantity, unit_price, "
        "amount_minor, tax_rate, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            entry_id, last + 1, line.description,
            _decimal_text("quantity", line.quantity),
            _decimal_text("unit_price", line.unit_price),
            _minor("amount_minor", line.amount_minor),
            _decimal_text("tax_rate", line.tax_rate),
            now(),
        ),
    )  # fmt: skip
    return get_line(conn, int(cursor.lastrowid or 0))


def delete_line(conn: sqlite3.Connection, line_id: int) -> None:
    """Remove a line; its evidence goes with it and edits that mention it keep a null line."""
    conn.execute("DELETE FROM entry_lines WHERE id = ?", (line_id,))


def order_lines(conn: sqlite3.Connection, entry_id: int, line_ids: Sequence[int]) -> None:
    """Number the entry's lines 1, 2, 3 in the order given (two passes: numbers are unique)."""
    for position, line_id in enumerate(line_ids, start=1):
        conn.execute(
            "UPDATE entry_lines SET line_number = ? WHERE id = ? AND entry_id = ?",
            (-position, line_id, entry_id),
        )
    conn.execute(
        "UPDATE entry_lines SET line_number = -line_number WHERE entry_id = ? AND line_number < 0",
        (entry_id,),
    )


def delete_evidence_for(
    conn: sqlite3.Connection, entry_id: int, field: HeaderField | LineField, line_id: int | None
) -> None:
    """A person who changes a value becomes its source, so the model's evidence for it goes."""
    conn.execute(
        "DELETE FROM evidence WHERE entry_id = ? AND field = ? AND line_id IS ?",
        (entry_id, field.value, line_id),
    )


def merge_vendors(conn: sqlite3.Connection, source_id: int, into_id: int) -> list[int]:
    """Fold one vendor into another: aliases and entries move, the old name becomes an alias,
    and the old vendor is switched off (entries and history still point at its row).
    Returns the ids of the documents whose entries moved."""
    if source_id == into_id:
        raise RepositoryError("A vendor cannot be merged into itself.")
    source, target = get_vendor(conn, source_id), get_vendor(conn, into_id)
    if not target.is_active:
        raise RepositoryError("The vendor to merge into is switched off.")
    with transaction(conn):
        moved = [
            row["document_id"]
            for row in conn.execute(
                "SELECT document_id FROM entries WHERE vendor_id = ?", (source_id,)
            )
        ]
        conn.execute(
            "UPDATE vendor_aliases SET vendor_id = ? WHERE vendor_id = ?", (into_id, source_id)
        )
        conn.execute(
            "INSERT OR IGNORE INTO vendor_aliases (vendor_id, alias, normalized_alias, created_at) "
            "VALUES (?, ?, ?, ?)",
            (into_id, source.name, source.normalized_name, now()),
        )
        conn.execute("UPDATE entries SET vendor_id = ? WHERE vendor_id = ?", (into_id, source_id))
        conn.execute("UPDATE vendors SET is_active = 0 WHERE id = ?", (source_id,))
    return moved


# ---- exports ----------------------------------------------------------------------------------


def insert_export(
    conn: sqlite3.Connection,
    profile: ExportProfile,
    entry_count: int,
    row_count: int,
    file_sha256: str,
) -> Export:
    """Record an export. The file is named after its id, so the name is set once the id exists."""
    cursor = conn.execute(
        "INSERT INTO exports (profile, entry_count, row_count, file_name, file_sha256, created_at) "
        "VALUES (?, ?, ?, '', ?, ?)",
        (ExportProfile(profile).value, entry_count, row_count, file_sha256, now()),
    )
    export_id = int(cursor.lastrowid or 0)
    conn.execute(
        "UPDATE exports SET file_name = ? WHERE id = ?",
        (f"citetally_{ExportProfile(profile).value}_{export_id:04d}.csv", export_id),
    )
    return get_export(conn, export_id)


def add_export_items(conn: sqlite3.Connection, export_id: int, entry_ids: Sequence[int]) -> None:
    conn.executemany(
        "INSERT INTO export_items (export_id, entry_id) VALUES (?, ?)",
        [(export_id, entry_id) for entry_id in entry_ids],
    )


def get_export(conn: sqlite3.Connection, export_id: int) -> Export:
    return _required(
        _one(conn, Export, "SELECT * FROM exports WHERE id = ?", (export_id,)),
        f"Export {export_id}",
    )


def list_exports(conn: sqlite3.Connection) -> list[Export]:
    return _all(conn, Export, "SELECT * FROM exports ORDER BY id DESC")


def entries_with_status(
    conn: sqlite3.Connection, entry_ids: Sequence[int] | None
) -> list[tuple[Entry, S]]:
    """Entries with their document's status, oldest first. Without ids: the approved and exported
    ones. With ids: exactly those, whatever their status."""
    params: tuple[int, ...]
    if entry_ids is None:
        where, params = "WHERE d.status IN ('approved','exported')", ()
    else:
        marks = ", ".join("?" for _ in entry_ids)
        where, params = f"WHERE e.id IN ({marks})", tuple(entry_ids)
    rows = conn.execute(
        "SELECT e.*, d.status AS document_status FROM entries e "
        f"JOIN documents d ON d.id = e.document_id {where} ORDER BY e.id",
        params,
    )
    found = []
    for row in rows:
        data = dict(row)
        status = S(data.pop("document_status"))
        found.append((Entry.model_validate(data), status))
    return found


def status_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """How many documents are in each status (every status is present, zero included)."""
    counts = {status.value: 0 for status in S}
    for row in conn.execute("SELECT status, COUNT(*) AS n FROM documents GROUP BY status"):
        counts[row["status"]] = row["n"]
    return counts


def unresolved_warnings(conn: sqlite3.Connection, document_id: int) -> list[CheckCode]:
    """Non-blocking checks that failed and were not overridden: the "worth a look" ones."""
    rows = conn.execute(
        "SELECT check_code FROM checks WHERE document_id = ? AND blocking = 0 AND passed = 0 "
        "AND overridden = 0 ORDER BY id",
        (document_id,),
    )
    return [CheckCode(row["check_code"]) for row in rows]


def list_batches(conn: sqlite3.Connection, limit: int = 50) -> list[str]:
    """Upload batch labels, the most recently used first."""
    rows = conn.execute(
        "SELECT batch_label FROM documents WHERE batch_label IS NOT NULL "
        "GROUP BY batch_label ORDER BY MAX(id) DESC LIMIT ?",
        (limit,),
    )
    return [row["batch_label"] for row in rows]
