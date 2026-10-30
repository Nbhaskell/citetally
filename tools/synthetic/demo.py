"""The demo set: about a dozen labelled documents for trying the app by hand.

  python -m tools.synthetic.demo

Chosen from the tuned split only (never the held-out one), to show clean documents in each
condition and the problems a reviewer should catch. The files go to data/synthetic/demo/, with a
manifest saying what to look for in each. Loading them into the app is the upload route's job
(Phase 5) and the Inbox's "try a demo file" button (Phase 7).

Demo data. All vendors, invoices and amounts are invented.
"""

from __future__ import annotations

import json
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

from tools.synthetic.golden import GOLDEN_FILE, Item, load_golden

DEMO_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic"
_MILD = ("clean_pdf", "scan_light", "phone_photo", "scan_heavy")

# (label, predicate). The first unused match, in id order, fills each slot.
_SLOTS: list[tuple[str, Callable[[Item], bool]]] = [
    (
        "a clean invoice, digital PDF",
        lambda i: not i.planted and i.condition == "clean_pdf" and i.truth.entry_type == "invoice",
    ),
    (
        "a clean receipt, light scan",
        lambda i: not i.planted and i.condition == "scan_light" and i.truth.entry_type == "receipt",
    ),
    (
        "a clean invoice, phone photo",
        lambda i: (
            not i.planted and i.condition == "phone_photo" and i.truth.entry_type == "invoice"
        ),
    ),
    (
        "a clean credit note, light scan",
        lambda i: (
            not i.planted and i.condition == "scan_light" and i.truth.entry_type == "credit_note"
        ),
    ),
    ("the printed total is wrong", lambda i: _kind(i, "total_mismatch")),
    ("a line's amount is not quantity times price", lambda i: _kind(i, "line_math")),
    ("the printed tax does not match the rate", lambda i: _kind(i, "tax_mismatch")),
    ("an invoice entered twice under a new number", lambda i: _kind(i, "duplicate_content")),
    ("a vendor that is not in the vendor list", lambda i: _kind(i, "unknown_vendor")),
    ("a date in the future", lambda i: _kind(i, "future_date")),
    ("an instruction hidden in the document text", lambda i: _kind(i, "injection_text")),
]


def _kind(item: Item, kind: str) -> bool:
    return any(p.kind == kind for p in item.planted)


def _preference(item: Item) -> int:
    return _MILD.index(item.condition)


def select_demo(items: list[Item]) -> list[Item]:
    """About a dozen documents: one per slot, plus the original of any duplicate chosen."""
    if any(i.split != "tuned" for i in items):
        raise ValueError("The demo set uses the tuned split only.")
    chosen: list[Item] = []
    used: set[str] = set()
    by_id = {i.id: i for i in items}
    for _, wanted in _SLOTS:
        matches = sorted(
            (i for i in items if wanted(i) and i.id not in used),
            key=lambda i: (_preference(i), i.id),
        )
        if not matches:
            continue
        pick = matches[0]
        chosen.append(pick)
        used.add(pick.id)
        original = by_id.get(pick.expected_duplicate_of or "")
        if original is not None and original.id not in used:
            chosen.append(original)
            used.add(original.id)
    return chosen


def _look_for(item: Item, label: str) -> str:
    if item.planted:
        return f"{label}. Expected check: {', '.join(item.expected_checks)}. {item.notes}."
    return f"{label}. Nothing should be flagged."


def export_demo(
    items: list[Item], source_root: Path = DEMO_ROOT, target: Path | None = None
) -> list[Item]:
    """Copy the selected files to the demo folder and write demo_manifest.json."""
    target = target or source_root / "demo"
    target.mkdir(parents=True, exist_ok=True)
    selected = select_demo(items)
    labels = {}
    for label, wanted in _SLOTS:
        for item in selected:
            if wanted(item) and item.id not in labels:
                labels[item.id] = label
                break
    documents = []
    for item in selected:
        source = source_root / Path(item.file).relative_to("data/synthetic")
        name = source.name
        shutil.copyfile(source, target / name)
        label = labels.get(item.id, "the earlier document that the duplicate repeats")
        documents.append(
            {
                "id": item.id,
                "file": name,
                "condition": item.condition,
                "entry_type": item.truth.entry_type,
                "what_to_look_for": _look_for(item, label),
                "expected_checks": item.expected_checks,
                "expected_duplicate_of": item.expected_duplicate_of,
            }
        )
    manifest = {
        "note": "Demo data. All vendors, invoices and amounts are invented.",
        "documents": documents,
    }
    (target / "demo_manifest.json").write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    return selected


def main() -> int:
    items = load_golden(GOLDEN_FILE, "tuned")
    selected = export_demo(items)
    print(f"Wrote {len(selected)} demo documents to {DEMO_ROOT / 'demo'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
