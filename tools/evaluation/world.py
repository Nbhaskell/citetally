"""The small world a run happens in: the vendor list, earlier approved entries, and the order.

The checks need context to mean anything. A vendor is unknown only if it is not on the list; an
amount is unusual only against that vendor's earlier approved entries; a duplicate needs the
earlier document to be there. The harness builds that context from the fact sheet and the golden
file, the way an owner who had been using the desk for a while would have it:

- every listed vendor of the fact sheet is on the vendor list, with its other names, default
  category and usual currency (the unlisted vendors are not, so UNKNOWN_VENDOR has work to do);
- each listed vendor has earlier approved entries: the printed totals of that vendor's clean
  documents in the split being run, with no date and no number so they cannot be mistaken for
  duplicates. A vendor with fewer than the minimum history is padded by repeating its own totals
  (the padding is counted in the report);
- documents go in with originals first, so a duplicate finds the document it copies.

The history is built from other documents' printed totals, never from the document being scored
reading its own answer, but the vendor's own clean totals are in it. That is how a person's
history would contain them. It is a stated limit of the harness.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from citetally import repository as repo
from citetally.matching import normalize_name
from citetally.models import DocumentStatus, EntryType, ExtractMode, Provider
from tools.synthetic.facts import Facts
from tools.synthetic.golden import Item


@dataclass
class World:
    vendor_golden_id: dict[int, str] = field(default_factory=dict)  # vendor row id -> "V01"
    history_entries: int = 0
    history_padded: int = 0
    vendors: int = 0


def order(items: Sequence[Item]) -> list[Item]:
    """Originals before the documents that copy them, otherwise by id."""
    return sorted(items, key=lambda i: (i.expected_duplicate_of is not None, i.id))


def seed(
    conn: sqlite3.Connection, facts: Facts, history_items: Sequence[Item], *, min_history: int
) -> World:
    """Put the vendor list and the earlier approved entries into an empty database."""
    world = World()
    categories = {c.code: c.id for c in repo.list_categories(conn)}
    row_of: dict[str, int] = {}
    for vendor in facts.vendors:
        row = repo.create_vendor(
            conn,
            vendor.name,
            normalize_name(vendor.name),
            default_category_id=categories.get(vendor.category),
            default_currency=vendor.currency,
        )
        row_of[vendor.id] = row.id
        world.vendor_golden_id[row.id] = vendor.id
        world.vendors += 1
        for alias in vendor.aliases:
            normalized = normalize_name(alias)
            if normalized and repo.find_vendor_by_normalized(conn, normalized) is None:
                repo.add_alias(conn, row.id, alias, normalized)

    groups: dict[tuple[str, str, str], list[tuple[int, int | None, int | None]]] = defaultdict(list)
    for item in history_items:
        if item.planted or item.vendor_id not in row_of:
            continue
        truth = item.truth
        key = (item.vendor_id, truth.currency, truth.entry_type)
        groups[key].append((truth.total_minor, truth.subtotal_minor, truth.tax_total_minor))

    number = 0
    for (vendor_id, currency, entry_type), rows in sorted(groups.items()):
        padded = list(rows)
        while len(padded) < min_history:
            padded.append(rows[len(padded) % len(rows)])
            world.history_padded += 1
        for total, subtotal, tax in padded:
            number += 1
            kind = EntryType(entry_type)
            _history_entry(conn, row_of[vendor_id], number, currency, kind, total, subtotal, tax)
            world.history_entries += 1
    return world


def _history_entry(
    conn: sqlite3.Connection,
    vendor_row: int,
    number: int,
    currency: str,
    entry_type: EntryType,
    total: int,
    subtotal: int | None,
    tax: int | None,
) -> None:
    name = f"history-{number}"
    document = repo.create_document(
        conn,
        original_filename=name,
        stored_path=name,
        file_sha256=hashlib.sha256(name.encode()).hexdigest(),
        mime_type="application/pdf",
        size_bytes=1,
    )
    extraction = repo.add_extraction(
        conn,
        document.id,
        provider=Provider.OLLAMA,
        model="history",
        extract_mode=ExtractMode.TEXT_ONLY,
        prompt_version="history",
        fields={},
        raw_response="",
    )
    repo.create_entry(
        conn,
        document.id,
        extraction.id,
        entry_type,
        vendor_id=vendor_row,
        currency=currency,
        total_minor=total,
        subtotal_minor=subtotal,
        tax_total_minor=tax,
    )
    conn.execute(
        "UPDATE documents SET status = ? WHERE id = ?", (DocumentStatus.APPROVED.value, document.id)
    )
