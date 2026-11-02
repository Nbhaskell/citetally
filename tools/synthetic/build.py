"""Build the synthetic document set and the golden file from a seed.

  python -m tools.synthetic.build            generate everything (seed 20261031, 14 per family)
  python -m tools.synthetic.build --check    generate and validate without writing files

Same seed, same library versions, same bytes. Tuned documents go to data/synthetic/docs/, held-out
documents to data/synthetic/heldout/ (which development tools never open).
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import random
import statistics
import sys
import zlib
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from tools.synthetic.degrade import make_file
from tools.synthetic.docgen import generate, reprint, truth
from tools.synthetic.facts import FACTS_FILE, Facts, Vendor, load_facts
from tools.synthetic.families import FAMILIES, Family
from tools.synthetic.golden import (
    CONDITIONS,
    GOLDEN_FILE,
    SOURCE_KIND,
    GoldenSet,
    Header,
    Item,
    problems,
    write_golden,
)
from tools.synthetic.model import Doc
from tools.synthetic.planting import EXPECTED_CHECKS, PLANTED_KINDS, eligible, plant
from tools.synthetic.render import business_block, render_pdf

GENERATOR = "citetally-synthetic 1"
DEFAULT_SEED = 20261031
DEFAULT_PER_FAMILY = 14
PLANTED_SHARE = 0.26
BAND = 2.5  # natural totals stay within this factor of the vendor's median
REPO_ROOT = FACTS_FILE.parent.parent
DATA_ROOT = REPO_ROOT / "data" / "synthetic"


@dataclass
class Entry:
    doc: Doc
    family: Family
    condition: str
    serial: int  # the vendor's running invoice-number counter
    planted: list[dict[str, Any]] = field(default_factory=list)


def _file_seed(seed: int, doc_id: str) -> int:
    return zlib.crc32(f"{seed}:{doc_id}".encode())


def _random_date(rng: random.Random, facts: Facts) -> date:
    start, end = facts.date_range
    return start + timedelta(days=rng.randint(0, (end - start).days))


def _vendors(facts: Facts) -> dict[str, Vendor]:
    return {v.id: v for v in [*facts.vendors, *facts.unlisted_vendors]}


def _set_date(doc: Doc, new_date: date) -> None:
    doc.entry_date = new_date
    if doc.due_date is not None:
        doc.due_date = new_date + timedelta(days=doc.vendor.terms_days)
    reprint(doc)


def natural_entries(facts: Facts, seed: int, per_family: int) -> list[Entry]:
    """Consistent documents, before any problem is planted."""
    vendors = _vendors(facts)
    rng = random.Random(f"{seed}:documents")
    serial: dict[str, int] = {}
    counters = {"inv": 0, "rcp": 0, "crn": 0}
    entries: list[Entry] = []
    for fam_index, family in enumerate(FAMILIES):
        entry_type = family.entry_types[0]
        prefix = {"invoice": "inv", "receipt": "rcp", "credit_note": "crn"}[entry_type]
        for i in range(per_family):
            vendor = vendors[family.vendors[i % len(family.vendors)]]
            counters[prefix] += 1
            serial[vendor.id] = serial.get(vendor.id, 0) + 1
            doc = generate(
                rng,
                facts,
                vendor,
                doc_id=f"{prefix}-{counters[prefix]:04d}",
                entry_date=_random_date(rng, facts),
                serial=serial[vendor.id],
                style=family.style,
                entry_type="credit_note" if entry_type == "credit_note" else None,
            )
            condition = CONDITIONS[(i + fam_index) % len(CONDITIONS)]
            entries.append(Entry(doc, family, condition, serial[vendor.id]))
    _rebalance_totals(entries, facts, seed)
    _separate_accidental_duplicates(entries, rng, facts)
    return entries


def vendor_medians(entries: list[Entry]) -> dict[str, int]:
    totals: dict[str, list[int]] = {}
    for e in entries:
        totals.setdefault(e.doc.vendor.id, []).append(e.doc.total_minor)
    return {vendor: int(statistics.median(values)) for vendor, values in totals.items()}


def _rebalance_totals(entries: list[Entry], facts: Facts, seed: int) -> None:
    """Redraw natural documents whose total is far from the vendor's usual, so only planted
    outliers trip the outlier check."""
    medians = vendor_medians(entries)
    for e in entries:
        median = medians[e.doc.vendor.id]
        for attempt in range(80):
            if median / BAND <= e.doc.total_minor <= median * BAND:
                break
            e.doc = generate(
                random.Random(f"{seed}:{e.doc.id}:{attempt}"),
                facts,
                e.doc.vendor,
                doc_id=e.doc.id,
                entry_date=e.doc.entry_date,
                serial=e.serial,
                style=e.family.style,
                entry_type=e.doc.entry_type if e.doc.entry_type == "credit_note" else None,
            )


def _separate_accidental_duplicates(entries: list[Entry], rng: random.Random, facts: Facts) -> None:
    """Natural documents must not look like duplicates of each other by chance."""
    start, end = facts.date_range
    for _ in range(50):
        moved = False
        seen: dict[tuple[str, str, int], list[Entry]] = {}
        for e in entries:
            seen.setdefault((e.doc.vendor.id, e.doc.currency, e.doc.total_minor), []).append(e)
        for group in seen.values():
            group.sort(key=lambda e: e.doc.entry_date)
            for earlier, later in itertools.pairwise(group):
                if (later.doc.entry_date - earlier.doc.entry_date).days <= 10:
                    target = later.doc.entry_date + timedelta(days=rng.randint(12, 40))
                    if target > end:
                        target = max(start, earlier.doc.entry_date - timedelta(days=15))
                    _set_date(later.doc, target)
                    moved = True
        if not moved:
            return


def plan_planting(
    entries: list[Entry], facts: Facts, seed: int, share: float = PLANTED_SHARE
) -> None:
    """Give about a quarter of the documents (`share`) exactly one known problem."""
    rng = random.Random(f"{seed}:planting")
    medians = vendor_medians(entries)
    counts: dict[str, int] = {}
    for e in entries:
        counts[e.doc.vendor.id] = counts.get(e.doc.vendor.id, 0) + 1
    target = round(share * len(entries))
    kinds = [PLANTED_KINDS[i % len(PLANTED_KINDS)] for i in range(target)]
    taken: set[int] = set()
    stranger_serial = 100
    for kind in kinds:
        order = list(range(len(entries)))
        rng.shuffle(order)
        for idx in order:
            e = entries[idx]
            if idx in taken:
                continue
            original_idx: int | None = None
            original: Doc | None = None
            if kind in {"duplicate_invoice_number", "duplicate_content"}:
                partner = [
                    j
                    for j in order
                    if j not in taken
                    and j != idx
                    and entries[j].family.id == e.family.id
                    and entries[j].doc.vendor.id == e.doc.vendor.id
                ]
                if not partner:
                    continue
                original_idx = partner[0]
                original = entries[original_idx].doc
            if kind == "unknown_vendor":
                if e.family.entry_types[0] != "invoice":
                    continue
                stranger = rng.choice(facts.unlisted_vendors)
                stranger_serial += 1
                e.doc = generate(
                    random.Random(f"{seed}:{e.doc.id}:stranger"),
                    facts,
                    stranger,
                    doc_id=e.doc.id,
                    entry_date=e.doc.entry_date,
                    serial=stranger_serial,
                    style=e.family.style,
                )
            median = medians.get(e.doc.vendor.id)
            if kind == "amount_outlier" and counts.get(e.doc.vendor.id, 0) < 6:
                continue
            if not eligible(kind, e.doc, original=original, vendor_median_minor=median):
                continue
            record = plant(kind, e.doc, rng, facts, original=original, vendor_median_minor=median)
            e.planted.append(record)
            taken.add(idx)
            if original_idx is not None:
                taken.add(original_idx)
            break


def _folder(split: str) -> str:
    return "docs" if split == "tuned" else "heldout"


def write_files(entries: list[Entry], facts: Facts, seed: int, root: Path) -> str:
    """Render and degrade every document. Returns a digest of all file contents."""
    block = business_block(facts)
    digest = hashlib.sha256()
    for e in sorted(entries, key=lambda e: e.doc.id):
        pdf = render_pdf(e.doc, e.family, block)
        profile = "heldout" if e.family.split == "heldout" else "tuned"
        data, extension = make_file(pdf, e.condition, _file_seed(seed, e.doc.id), profile)
        folder = root / _folder(e.family.split)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{e.doc.id}.{extension}").write_bytes(data)
        digest.update(f"{e.doc.id}:{hashlib.sha256(data).hexdigest()}\n".encode())
    return digest.hexdigest()


def _extension(condition: str) -> str:
    return "jpg" if condition == "phone_photo" else "pdf"


def golden_items(entries: list[Entry]) -> list[Item]:
    items: list[Item] = []
    for e in sorted(entries, key=lambda e: e.doc.id):
        planted = e.planted
        checks = sorted({c for p in planted for c in EXPECTED_CHECKS[p["kind"]]})
        duplicate_of = next((p["duplicate_of"] for p in planted if "duplicate_of" in p), None)
        folder = _folder(e.family.split)
        items.append(
            Item.model_validate(
                {
                    "id": e.doc.id,
                    "split": e.family.split,
                    "template_family": e.family.id,
                    "condition": e.condition,
                    "file": f"data/synthetic/{folder}/{e.doc.id}.{_extension(e.condition)}",
                    "source_kind": SOURCE_KIND[e.condition],
                    "vendor_id": e.doc.vendor.id,
                    "truth": truth(e.doc),
                    "planted": planted,
                    "expected_checks": checks,
                    "expected_duplicate_of": duplicate_of,
                    "notes": "; ".join(p["detail"] for p in planted)
                    or "clean: a correct reader should raise no check",
                }
            )
        )
    return items


def counts_of(items: list[Item]) -> dict[str, Any]:
    def tally(values: list[str]) -> dict[str, int]:
        return dict(sorted({v: values.count(v) for v in set(values)}.items()))

    return {
        "documents": len(items),
        "by_split": tally([i.split for i in items]),
        "by_condition": tally([i.condition for i in items]),
        "by_family": tally([i.template_family for i in items]),
        "by_planted_kind": tally([p.kind for i in items for p in i.planted]),
        "with_planted_problem": sum(1 for i in items if i.planted),
        # The report script prints these, so it never has to open held-out items.
        "planted_by_split": tally([i.split for i in items if i.planted]),
        "by_split_and_condition": tally([f"{i.split}/{i.condition}" for i in items]),
        "families_by_split": {
            split: sorted({i.template_family for i in items if i.split == split})
            for split in ("tuned", "heldout")
        },
    }


def build(
    seed: int = DEFAULT_SEED,
    per_family: int = DEFAULT_PER_FAMILY,
    root: Path = DATA_ROOT,
    golden_path: Path | None = GOLDEN_FILE,
    files: bool = True,
) -> GoldenSet:
    facts = load_facts()
    entries = natural_entries(facts, seed, per_family)
    plan_planting(entries, facts, seed)
    digest = write_files(entries, facts, seed, root) if files else None
    items = golden_items(entries)
    golden = GoldenSet(
        header=Header(
            version=1,
            seed=seed,
            generator=GENERATOR,
            facts_sha256=hashlib.sha256(FACTS_FILE.read_bytes()).hexdigest(),
            files_digest=digest,
            counts=counts_of(items),
            note=(
                "SYNTHETIC TEST DATA. Truth is what is printed on each page, planted errors "
                "included. The heldout split is sealed until Phase 8."
            ),
        ),
        items=items,
    )
    found = problems(golden, {v.id for v in facts.vendors}, {v.id for v in facts.unlisted_vendors})
    if found and per_family >= DEFAULT_PER_FAMILY:
        raise ValueError("golden set is not valid:\n" + "\n".join(found))
    if golden_path is not None:
        write_golden(golden, golden_path)
    return golden


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the synthetic documents and golden set.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--per-family", type=int, default=DEFAULT_PER_FAMILY)
    parser.add_argument("--check", action="store_true", help="validate only; write nothing")
    args = parser.parse_args(argv)
    golden = build(
        args.seed,
        args.per_family,
        golden_path=None if args.check else GOLDEN_FILE,
        files=not args.check,
    )
    counts = golden.header.counts
    print(
        f"{counts['documents']} documents, {counts['with_planted_problem']} with a planted problem"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
