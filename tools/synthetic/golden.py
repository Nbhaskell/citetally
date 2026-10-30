"""The golden set: its schema, its checks, and a guard that keeps the held-out split sealed.

The file is `eval/golden/citetally_v1.json` (see docs/BACKEND_SCHEMA.md section 7). Item
`truth` values are what is printed on the page, even when the page contains a planted error.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from tools.synthetic.families import FAMILIES
from tools.synthetic.planting import EXPECTED_CHECKS, PLANTED_KINDS

GOLDEN_FILE = (
    Path(__file__).resolve().parent.parent.parent / "eval" / "golden" / "citetally_v1.json"
)
CONDITIONS = ("clean_pdf", "scan_light", "scan_heavy", "phone_photo")
SOURCE_KIND = {
    "clean_pdf": "digital_pdf",
    "scan_light": "scanned_pdf",
    "scan_heavy": "scanned_pdf",
    "phone_photo": "image",
}
MIN_DOCUMENTS = 150


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GoldenLine(_Strict):
    description: str
    quantity: str
    unit_price: str
    amount_minor: int
    tax_minor: int | None = None
    printed: dict[str, str]


class Truth(_Strict):
    entry_type: Literal["invoice", "receipt", "credit_note"]
    vendor_name: str
    invoice_number: str | None
    entry_date: str
    due_date: str | None
    po_number: str | None
    currency: str
    subtotal_minor: int | None
    tax_total_minor: int | None
    shipping_minor: int | None
    discount_minor: int | None
    total_minor: int
    lines: list[GoldenLine]
    printed: dict[str, str]


class Planted(_Strict):
    kind: Literal[
        "total_mismatch",
        "line_math",
        "tax_mismatch",
        "duplicate_invoice_number",
        "duplicate_content",
        "amount_outlier",
        "future_date",
        "due_before_entry",
        "unknown_vendor",
        "missing_invoice_number",
        "currency_mismatch",
        "injection_text",
    ]
    detail: str
    duplicate_of: str | None = None


class Item(_Strict):
    id: str
    split: Literal["tuned", "heldout"]
    template_family: str
    condition: Literal["clean_pdf", "scan_light", "scan_heavy", "phone_photo"]
    file: str
    source_kind: Literal["digital_pdf", "scanned_pdf", "image"]
    vendor_id: str
    truth: Truth
    planted: list[Planted]
    expected_checks: list[str]
    expected_duplicate_of: str | None
    notes: str


class Header(_Strict):
    version: int
    seed: int
    generator: str
    facts_sha256: str
    files_digest: str | None
    counts: dict[str, Any]
    note: str


class GoldenSet(_Strict):
    header: Header
    items: list[Item]


def problems(golden: GoldenSet, vendor_ids: set[str], unlisted_ids: set[str]) -> list[str]:
    """Everything wrong with a golden set, as plain sentences. Empty means it is valid."""
    found: list[str] = []
    items = golden.items
    ids = [i.id for i in items]
    if len(set(ids)) != len(ids):
        found.append("item ids are not unique")
    if len(items) < MIN_DOCUMENTS:
        found.append(f"only {len(items)} documents; at least {MIN_DOCUMENTS} are required")
    split_of = {f.id: f.split for f in FAMILIES}
    by_id = {i.id: i for i in items}
    for item in items:
        if split_of.get(item.template_family) != item.split:
            found.append(
                f"{item.id}: family {item.template_family} does not belong to {item.split}"
            )
        if SOURCE_KIND[item.condition] != item.source_kind:
            found.append(f"{item.id}: source kind does not match condition")
        expected_dir = "docs" if item.split == "tuned" else "heldout"
        if not item.file.startswith(f"data/synthetic/{expected_dir}/"):
            found.append(f"{item.id}: file is not under the {item.split} folder")
        if item.vendor_id not in vendor_ids | unlisted_ids:
            found.append(f"{item.id}: unknown vendor id {item.vendor_id}")
        wanted = sorted({c for p in item.planted for c in EXPECTED_CHECKS[p.kind]})
        if sorted(item.expected_checks) != wanted:
            found.append(f"{item.id}: expected checks do not match the planted problems")
        if any(p.kind == "unknown_vendor" for p in item.planted) != (
            item.vendor_id in unlisted_ids
        ):
            found.append(f"{item.id}: unknown_vendor and the vendor id disagree")
        if item.expected_duplicate_of:
            original = by_id.get(item.expected_duplicate_of)
            if original is None or original.split != item.split:
                found.append(f"{item.id}: duplicate_of must name a document in the same split")
        if len(item.planted) > 1:
            found.append(f"{item.id}: more than one planted problem")
    kinds = {p.kind for i in items for p in i.planted}
    if kinds != set(PLANTED_KINDS):
        found.append(f"planted kinds missing: {sorted(set(PLANTED_KINDS) - kinds)}")
    tuned_families = {i.template_family for i in items if i.split == "tuned"}
    held_families = {i.template_family for i in items if i.split == "heldout"}
    if tuned_families & held_families:
        found.append("a template family appears in both splits")
    if len(held_families) * 3 < len(tuned_families | held_families):
        found.append("fewer than a third of the families are held out")
    return found


def canonical_json(golden: GoldenSet) -> str:
    return json.dumps(golden.model_dump(mode="json"), indent=1, ensure_ascii=False) + "\n"


def write_golden(golden: GoldenSet, path: Path = GOLDEN_FILE) -> str:
    """Write the file and return its SHA-256 (the golden-set hash recorded by evaluation runs)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = canonical_json(golden)
    path.write_text(text, encoding="utf-8", newline="\n")
    # Counts live in their own small file so reporting never means opening held-out items.
    summary = json.dumps(golden.header.model_dump(mode="json"), indent=1, ensure_ascii=False)
    summary_path(path).write_text(summary + "\n", encoding="utf-8", newline="\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def summary_path(path: Path = GOLDEN_FILE) -> Path:
    return path.with_name(path.stem + ".summary.json")


def golden_hash(path: Path = GOLDEN_FILE) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_golden(
    path: Path = GOLDEN_FILE, split: str = "tuned", *, unseal_heldout: bool = False
) -> list[Item]:
    """Items of one split. The held-out split is sealed until Phase 8 and the one allowed run.

    Opening it needs `unseal_heldout=True`, so reading it is always a visible, deliberate act.
    """
    if split not in {"tuned", "heldout"}:
        raise ValueError(f"unknown split {split!r}; use 'tuned' or 'heldout'")
    if split == "heldout" and not unseal_heldout:
        raise PermissionError(
            "The held-out split is sealed. It is opened once, in Phase 8, after dev numbers "
            "are frozen. Pass unseal_heldout=True only for that run."
        )
    golden = GoldenSet.model_validate_json(path.read_text(encoding="utf-8"))
    return [item for item in golden.items if item.split == split]
