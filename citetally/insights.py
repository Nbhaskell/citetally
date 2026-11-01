"""Small, honest summaries of what has been reviewed (docs/UI_UX_DESIGN_BRIEF.md section 2.5).

Everything here is a count or a sum of recorded values. There are no forecasts and no scores.

What each part counts, and over which dates:
- Spending: approved and exported entries, by the date printed on the document. Credit notes
  count as negative. Each currency is kept apart; amounts in different currencies are never added.
- Waiting: documents in review now, by how long they have been in the list. No period applies.
- Edits: documents approved in the period, how many of them had a value changed by hand, and
  which fields were changed most. Confirming a vendor under the name already printed changes
  nothing, so it is not counted.
- Checks: for documents added in the period, how many have each check failing now, and how many
  of those were accepted with a written reason.
- Review time: the median of the seconds the screen was open for approvals and rejections made in
  the period (only decisions that recorded a time).
"""

from __future__ import annotations

import sqlite3
import statistics
from dataclasses import dataclass, field
from datetime import UTC, datetime

AGE_BUCKETS = ("under_1_day", "1_to_3_days", "3_to_7_days", "over_7_days")


@dataclass(frozen=True)
class Spend:
    code: str | None  # category code; None for the vendor table and for "no category"
    label: str
    currency: str
    total_minor: int
    entries: int


@dataclass(frozen=True)
class CheckCount:
    check_code: str
    documents: int
    overridden: int


@dataclass(frozen=True)
class FieldCount:
    field: str
    edits: int


@dataclass
class Insights:
    by_category: list[Spend] = field(default_factory=list)
    by_vendor: list[Spend] = field(default_factory=list)
    waiting_by_age: dict[str, int] = field(default_factory=dict)
    approved_documents: int = 0
    edited_documents: int = 0
    edited_fields: list[FieldCount] = field(default_factory=list)
    checks_failing: list[CheckCount] = field(default_factory=list)
    review_seconds_median: int | None = None
    review_seconds_count: int = 0


_SIGNED = "CASE WHEN e.entry_type = 'credit_note' THEN -e.total_minor ELSE e.total_minor END"
_IN_PERIOD = "(? IS NULL OR {col} >= ?) AND (? IS NULL OR {col} <= ?)"


def _period(column: str) -> str:
    return _IN_PERIOD.format(col=column)


def _bounds(date_from: str | None, date_to: str | None) -> tuple[str | None, ...]:
    return (date_from, date_from, date_to, date_to)


def _spending(
    conn: sqlite3.Connection,
    *,
    by: str,
    date_from: str | None,
    date_to: str | None,
    default_currency: str,
) -> list[Spend]:
    if by == "category":
        code, label, group = "c.code", "COALESCE(c.name, 'No category')", "c.id"
    else:
        code, label, group = "NULL", "COALESCE(v.name, 'No vendor chosen')", "v.id"
    rows = conn.execute(
        f"SELECT {code} AS code, {label} AS label, COALESCE(e.currency, ?) AS currency, "
        f"SUM({_SIGNED}) AS total, COUNT(*) AS entries "
        "FROM entries e JOIN documents d ON d.id = e.document_id "
        "LEFT JOIN categories c ON c.id = e.category_id "
        "LEFT JOIN vendors v ON v.id = e.vendor_id "
        "WHERE d.status IN ('approved', 'exported') AND e.total_minor IS NOT NULL "
        f"AND {_period('e.entry_date')} "
        f"GROUP BY {group}, COALESCE(e.currency, ?) "
        "ORDER BY currency, ABS(total) DESC, label",
        (default_currency, *_bounds(date_from, date_to), default_currency),
    )
    return [
        Spend(r["code"], r["label"], r["currency"], int(r["total"]), int(r["entries"]))
        for r in rows
    ]


def _parse(stamp: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _age_bucket(days: float) -> str:
    if days < 1:
        return AGE_BUCKETS[0]
    if days < 3:
        return AGE_BUCKETS[1]
    if days < 7:
        return AGE_BUCKETS[2]
    return AGE_BUCKETS[3]


def gather(
    conn: sqlite3.Connection,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    default_currency: str = "USD",
    now: datetime | None = None,
) -> Insights:
    now = now or datetime.now(UTC)
    result = Insights()
    result.by_category = _spending(
        conn, by="category", date_from=date_from, date_to=date_to, default_currency=default_currency
    )
    result.by_vendor = _spending(
        conn, by="vendor", date_from=date_from, date_to=date_to, default_currency=default_currency
    )

    result.waiting_by_age = dict.fromkeys(AGE_BUCKETS, 0)
    for row in conn.execute("SELECT created_at FROM documents WHERE status = 'needs_review'"):
        added = _parse(row["created_at"])
        if added is not None:
            days = max(0.0, (now - added).total_seconds() / 86400)
            result.waiting_by_age[_age_bucket(days)] += 1

    approved = conn.execute(
        "SELECT DISTINCT r.document_id FROM reviews r "
        f"WHERE r.decision = 'approve' AND {_period('date(r.created_at)')}",
        _bounds(date_from, date_to),
    ).fetchall()
    approved_ids = [int(r["document_id"]) for r in approved]
    result.approved_documents = len(approved_ids)
    if approved_ids:
        marks = ",".join("?" * len(approved_ids))
        edits = conn.execute(
            "SELECT f.field AS field, COUNT(*) AS edits, e.document_id AS document_id "
            "FROM field_edits f JOIN entries e ON e.id = f.entry_id "
            f"WHERE e.document_id IN ({marks}) AND f.old_value IS NOT f.new_value "
            "GROUP BY f.field, e.document_id",
            approved_ids,
        ).fetchall()
        result.edited_documents = len({int(r["document_id"]) for r in edits})
        totals: dict[str, int] = {}
        for r in edits:
            totals[r["field"]] = totals.get(r["field"], 0) + int(r["edits"])
        result.edited_fields = [
            FieldCount(name, count)
            for name, count in sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))
        ]

    rows = conn.execute(
        "SELECT c.check_code AS code, COUNT(*) AS documents, SUM(c.overridden) AS overridden "
        "FROM checks c JOIN documents d ON d.id = c.document_id "
        f"WHERE c.passed = 0 AND {_period('date(d.created_at)')} "
        "GROUP BY c.check_code ORDER BY documents DESC, c.check_code",
        _bounds(date_from, date_to),
    )
    result.checks_failing = [
        CheckCount(r["code"], int(r["documents"]), int(r["overridden"] or 0)) for r in rows
    ]

    seconds = [
        int(r["review_seconds"])
        for r in conn.execute(
            "SELECT review_seconds FROM reviews r "
            "WHERE r.decision IN ('approve', 'reject') AND r.review_seconds IS NOT NULL "
            f"AND {_period('date(r.created_at)')}",
            _bounds(date_from, date_to),
        )
    ]
    result.review_seconds_count = len(seconds)
    if seconds:
        result.review_seconds_median = round(statistics.median(seconds))
    return result
