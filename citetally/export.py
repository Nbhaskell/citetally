"""CSV export: the only way data leaves the app (CLAUDE.md rules 1 and 8; docs/TRD.md section 4.7).

Nothing here pays, posts or sends. Approved entries are written to a CSV file the person downloads
and imports into their accounting software themselves. Amounts are decimal strings made from
integer minor units; credit notes (stored positive) are written negative; every text cell is
neutralised against spreadsheet formulas; the file follows RFC 4180 (comma separated, CRLF line
ends, double quotes where needed, UTF-8 without a byte order mark).
"""

from __future__ import annotations

import csv
import hashlib
import io
import os
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from citetally import events
from citetally import repository as repo
from citetally.config import Settings
from citetally.db import transaction
from citetally.models import DocumentStatus as S
from citetally.models import (
    Entry,
    EntryLine,
    EntryType,
    EventType,
    Export,
    ExportProfile,
)
from citetally.money import from_minor

ENTRY_COLUMNS = (
    "entry_id", "document_id", "type", "vendor", "invoice_number", "po_number", "entry_date",
    "due_date", "currency", "subtotal", "tax", "shipping", "discount", "total", "category",
)  # fmt: skip
LINE_COLUMNS = (
    "entry_id", "document_id", "type", "vendor", "invoice_number", "entry_date", "due_date",
    "currency", "category", "line_number", "description", "quantity", "unit_price", "tax_rate",
    "line_amount", "entry_total",
)  # fmt: skip
COLUMNS = {ExportProfile.ENTRIES_CSV: ENTRY_COLUMNS, ExportProfile.LINES_CSV: LINE_COLUMNS}

# A cell starting with one of these is read as a formula by spreadsheet programs.
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
_CONTROL = {c: None for c in [*range(0, 9), 11, 12, *range(14, 32)]}  # all but tab, newline, return
SAMPLE_ROWS = 5


class ExportRefused(repo.RepositoryError):
    """The export cannot be made. The message says why in plain words."""


# ---- cells -------------------------------------------------------------------------------------


def neutralise(value: str | None) -> str:
    """A text cell that a spreadsheet will show as text: control characters dropped, and a quote
    put in front of anything that would start a formula (also after leading spaces)."""
    if not value:
        return ""
    clean = value.translate(_CONTROL)
    if clean.startswith(_FORMULA_STARTS) or clean.lstrip(" ").startswith(_FORMULA_STARTS):
        return "'" + clean
    return clean


def amount(minor: int | None, currency: str, *, credit: bool) -> str:
    """Minor units as a plain decimal string ("152.00"), negative for a credit note."""
    if minor is None:
        return ""
    value = from_minor(minor, currency)
    if credit and minor != 0:
        value = -value
    return f"{value:f}"


def decimal_text(text: str | None, *, credit: bool) -> str:
    """A stored exact decimal (quantity, unit price), negated for a credit note when it is money."""
    if text is None:
        return ""
    try:
        value = Decimal(text)
    except InvalidOperation:
        return neutralise(text)
    if credit and value != 0:
        value = -value
    return f"{value:f}"


# ---- rows --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ExportEntry:
    """An entry with the names the file shows."""

    entry: Entry
    lines: Sequence[EntryLine]
    vendor: str
    category: str


def _header(item: ExportEntry) -> list[str]:
    entry = item.entry
    return [
        str(entry.id),
        str(entry.document_id),
        entry.entry_type.value,
        neutralise(item.vendor),
        neutralise(entry.invoice_number),
    ]


def entry_row(item: ExportEntry, default_currency: str) -> list[str]:
    entry = item.entry
    currency = entry.currency or default_currency
    credit = entry.entry_type is EntryType.CREDIT_NOTE
    return [
        *_header(item),
        neutralise(entry.po_number),
        entry.entry_date or "",
        entry.due_date or "",
        currency,
        amount(entry.subtotal_minor, currency, credit=credit),
        amount(entry.tax_total_minor, currency, credit=credit),
        amount(entry.shipping_minor, currency, credit=credit),
        amount(entry.discount_minor, currency, credit=credit),
        amount(entry.total_minor, currency, credit=credit),
        neutralise(item.category),
    ]


def line_rows(item: ExportEntry, default_currency: str) -> list[list[str]]:
    """One row per line. An entry with no lines still gets one row (blank line columns), so its
    total is not lost from the file while its status moves to exported."""
    entry = item.entry
    currency = entry.currency or default_currency
    credit = entry.entry_type is EntryType.CREDIT_NOTE
    head = [
        *_header(item),
        entry.entry_date or "",
        entry.due_date or "",
        currency,
        neutralise(item.category),
    ]
    total = amount(entry.total_minor, currency, credit=credit)
    if not item.lines:
        return [[*head, "", "", "", "", "", "", total]]
    return [
        [
            *head,
            str(line.line_number),
            neutralise(line.description),
            line.quantity or "",
            decimal_text(line.unit_price, credit=credit),
            line.tax_rate or "",
            amount(line.amount_minor, currency, credit=credit),
            total,
        ]
        for line in item.lines
    ]


def rows_for(
    profile: ExportProfile, items: Iterable[ExportEntry], default_currency: str
) -> list[list[str]]:
    if profile is ExportProfile.ENTRIES_CSV:
        return [entry_row(item, default_currency) for item in items]
    return [row for item in items for row in line_rows(item, default_currency)]


def render(profile: ExportProfile, rows: Sequence[Sequence[str]]) -> bytes:
    """The file: a header row, then the rows, RFC 4180 style."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(
        buffer, delimiter=",", quotechar='"', quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n"
    )
    writer.writerow(COLUMNS[profile])
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


# ---- choosing and writing ----------------------------------------------------------------------


@dataclass(frozen=True)
class Selection:
    items: list[ExportEntry]
    statuses: dict[int, S]  # entry id -> document status
    skipped_exported: int


def _item(conn: sqlite3.Connection, entry: Entry) -> ExportEntry:
    vendor = (
        repo.get_vendor(conn, entry.vendor_id).name if entry.vendor_id else entry.vendor_name_raw
    )
    category = repo.get_category(conn, entry.category_id).code if entry.category_id else ""
    return ExportEntry(entry, repo.list_lines(conn, entry.id), vendor or "", category)


def select(
    conn: sqlite3.Connection, *, entry_ids: Sequence[int] | None, include_exported: bool
) -> Selection:
    """The entries an export would hold, oldest first. Only approved entries qualify, and exported
    ones only when asked for. Named entries that cannot be exported are refused, not skipped."""
    found = repo.entries_with_status(conn, entry_ids)
    if entry_ids is not None:
        missing = sorted(set(entry_ids) - {entry.id for entry, _ in found})
        if missing:
            raise repo.NotFound(f"Entry {missing[0]} was not found.")
        blocked = sorted(e.id for e, status in found if status not in (S.APPROVED, S.EXPORTED))
        if blocked:
            raise ExportRefused(
                "Only approved entries can be exported. Not approved: "
                + ", ".join(str(i) for i in blocked)
                + "."
            )
    keep = [(e, s) for e, s in found if s is S.APPROVED or (s is S.EXPORTED and include_exported)]
    skipped = sum(1 for _, s in found if s is S.EXPORTED) if not include_exported else 0
    return Selection([_item(conn, e) for e, _ in keep], {e.id: s for e, s in keep}, skipped)


@dataclass(frozen=True)
class Preview:
    entry_count: int
    row_count: int
    totals: dict[str, str]  # currency -> signed total of the entries, credit notes negative
    first_date: str | None
    last_date: str | None
    skipped_exported: int
    columns: tuple[str, ...]
    sample: list[list[str]]


def preview(
    conn: sqlite3.Connection,
    settings: Settings,
    profile: ExportProfile,
    *,
    include_exported: bool = False,
) -> Preview:
    chosen = select(conn, entry_ids=None, include_exported=include_exported)
    rows = rows_for(profile, chosen.items, settings.default_currency)
    totals: dict[str, Decimal] = {}
    for item in chosen.items:
        entry = item.entry
        if entry.total_minor is None:
            continue
        currency = entry.currency or settings.default_currency
        value = from_minor(entry.total_minor, currency)
        value = -value if entry.entry_type is EntryType.CREDIT_NOTE else value
        totals[currency] = totals.get(currency, Decimal(0)) + value
    dates = sorted(i.entry.entry_date for i in chosen.items if i.entry.entry_date)
    return Preview(
        entry_count=len(chosen.items),
        row_count=len(rows),
        totals={currency: f"{total:f}" for currency, total in sorted(totals.items())},
        first_date=dates[0] if dates else None,
        last_date=dates[-1] if dates else None,
        skipped_exported=chosen.skipped_exported,
        columns=COLUMNS[profile],
        sample=rows[:SAMPLE_ROWS],
    )


@dataclass(frozen=True)
class Created:
    export: Export
    skipped_exported: int


def export_path(settings: Settings, export_id: int) -> Path:
    return settings.data_dir / "exports" / f"{export_id}.csv"


def _write_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".part")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def create_export(
    conn: sqlite3.Connection,
    settings: Settings,
    profile: ExportProfile,
    *,
    entry_ids: Sequence[int] | None = None,
    include_exported: bool = False,
    request_id: str | None = None,
) -> Created:
    """Write the file, record the export, and move the approved entries to exported. All of it
    happens together: if any part fails nothing is recorded and no file is left behind."""
    chosen = select(conn, entry_ids=entry_ids, include_exported=include_exported)
    if not chosen.items:
        raise ExportRefused("There are no approved entries to export.")
    rows = rows_for(profile, chosen.items, settings.default_currency)
    data = render(profile, rows)
    path: Path | None = None
    try:
        with transaction(conn):
            export = repo.insert_export(
                conn, profile, len(chosen.items), len(rows), hashlib.sha256(data).hexdigest()
            )
            path = export_path(settings, export.id)
            _write_file(path, data)
            repo.add_export_items(conn, export.id, [i.entry.id for i in chosen.items])
            for item in chosen.items:
                if chosen.statuses[item.entry.id] is S.APPROVED:
                    repo.change_status(
                        conn, item.entry.document_id, S.EXPORTED, request_id=request_id
                    )
            events.record_event(
                conn,
                EventType.EXPORT_CREATED,
                payload={
                    "export_id": export.id,
                    "profile": profile.value,
                    "entry_count": len(chosen.items),
                    "row_count": len(rows),
                },
                request_id=request_id,
            )
    except BaseException:
        if path is not None:
            path.unlink(missing_ok=True)
        raise
    return Created(repo.get_export(conn, export.id), chosen.skipped_exported)
