"""Gather what the checks need from the database, run all 14, and store the results."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from citetally import repository as repo
from citetally.checks.inputs import CheckInput, History, Other, Outcome, Thresholds
from citetally.checks.rules import RULES
from citetally.config import Settings
from citetally.models import CheckCode


def _iso(text: str | None) -> date | None:
    try:
        return date.fromisoformat(text) if text else None
    except ValueError:
        return None


def gather(
    conn: sqlite3.Connection, document_id: int, settings: Settings, today: date | None = None
) -> CheckInput:
    entry = repo.get_entry_for_document(conn, document_id)
    if entry is None:
        raise repo.NotFound(f"Document {document_id} has no entry to check.")
    thresholds = Thresholds.from_settings(settings)
    vendor = repo.get_vendor(conn, entry.vendor_id) if entry.vendor_id is not None else None
    others: list[Other] = []
    history = History()
    if entry.vendor_id is not None:
        others = [
            Other(
                document_id=row.document_id,
                entry_type=row.entry_type,
                invoice_number=row.invoice_number,
                total_minor=row.total_minor,
                currency=row.currency,
                entry_date=_iso(row.entry_date),
            )
            for row in repo.sibling_entries(conn, entry.vendor_id, exclude_document_id=document_id)
        ]
        past = repo.approved_history(
            conn,
            entry.vendor_id,
            entry.currency or thresholds.default_currency,
            entry.entry_type,
            exclude_document_id=document_id,
        )
        history = History(
            totals_minor=[p.total_minor for p in past if p.total_minor is not None],
            tax_rates=[
                Decimal(p.tax_total_minor) / Decimal(p.subtotal_minor)
                for p in past
                if p.tax_total_minor is not None and p.subtotal_minor
            ],
        )
    return CheckInput(
        entry=entry,
        lines=repo.list_lines(conn, entry.id),
        evidence=repo.list_evidence(conn, entry.id),
        pages=repo.list_pages(conn, document_id),
        vendor=vendor,
        others=others,
        history=history,
        today=today or date.today(),
        thresholds=thresholds,
    )


def run_checks(
    conn: sqlite3.Connection,
    document_id: int,
    *,
    settings: Settings,
    today: date | None = None,
    request_id: str | None = None,
) -> list[Outcome]:
    """Run every check and store each result. A check run again clears its override, so after an
    edit the reviewer must give an override again for the values now on screen."""
    data = gather(conn, document_id, settings, today)
    outcomes = [RULES[code](data) for code in CheckCode]
    for outcome in outcomes:
        repo.upsert_check(
            conn,
            document_id,
            outcome.code,
            passed=outcome.passed,
            detail=outcome.detail,
            request_id=request_id,
        )
    return outcomes
