"""Build the second evaluation sets: `dev2` (develop fixes on it), `sealed` (run once, last) and
`sealed2` (a fresh set for the second round of fixes, also run once).

  python -m tools.synthetic.fresh_build --suite dev2
  python -m tools.synthetic.fresh_build --suite sealed
  python -m tools.synthetic.fresh_build --suite sealed2
  python -m tools.synthetic.fresh_build --suite sealed2 --verify    regenerate, compare the hash

`dev2` and `sealed` use a second invented business (`universe/facts_ridge.json`) and ten new
layouts (`fresh_families.py`); `sealed2` uses a third (`universe/facts_marigold.json`) and five
more layouts. Each condition has several levels of damage (`fresh_degrade.py`).

A sealed set is made before the fixes it will test and kept out of git: its answer key is written
under `data/synthetic/<suite>/`, and only the SHA-256 of that key's contents is committed, in
`eval/golden/`. Run again later with `--verify`, the generator must reproduce the same hash, which
shows the documents were not changed after the fixes were made.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any, Literal

from tools.synthetic.build import (
    Entry,
    _file_seed,
    _random_date,
    _rebalance_totals,
    _separate_accidental_duplicates,
    _vendors,
    plan_planting,
)
from tools.synthetic.docgen import generate, reprint, truth
from tools.synthetic.facts import Facts, load_facts
from tools.synthetic.fresh_degrade import LEVELS, make_fresh_file
from tools.synthetic.fresh_families import FreshFamily, families_of
from tools.synthetic.fresh_render import render_fresh_pdf
from tools.synthetic.golden import GoldenSet, Header, Item
from tools.synthetic.injection_sealed2 import INJECTION_TEXT_SEALED2
from tools.synthetic.planting import EXPECTED_CHECKS, PLANTED_KINDS
from tools.synthetic.render import business_block

REPO_ROOT = Path(__file__).resolve().parents[2]
FACTS_RIDGE = REPO_ROOT / "universe" / "facts_ridge.json"
FACTS_MARIGOLD = REPO_ROOT / "universe" / "facts_marigold.json"
FACTS_OF = {"dev2": FACTS_RIDGE, "sealed": FACTS_RIDGE, "sealed2": FACTS_MARIGOLD}
SEALED_SUITES = ("sealed", "sealed2")
DATA_ROOT = REPO_ROOT / "data" / "synthetic"
GOLDEN_DIR = REPO_ROOT / "eval" / "golden"
GENERATOR = "citetally-synthetic-fresh 1"
SEEDS = {"dev2": 4417201, "sealed": 9083377, "sealed2": 6120589}
PER_FAMILY = {"dev2": 20, "sealed": 50, "sealed2": 60}
PREFIX = {"dev2": "d2-", "sealed": "s2-", "sealed2": "s3-"}
PLANTED_SHARE = {"dev2": 0.30, "sealed": 0.30, "sealed2": 0.36}
# sealed2 deals tax and injection problems twice as often as the others: seven of each (D-066) was
# too few to say anything about them. Every kind still has at least seven documents.
PLANT_CYCLE = {"sealed2": (*PLANTED_KINDS, "tax_mismatch", "injection_text")}
PLANT_PHRASES = {"sealed2": INJECTION_TEXT_SEALED2}
MIN_PER_KIND = {"dev2": 2, "sealed": 4, "sealed2": 7}
MIN_PER_CONDITION = {"dev2": 20, "sealed": 50, "sealed2": 60}
# Ten combinations, so a family of 20 or 50 documents holds each equally often: clean twice.
COMBOS: tuple[tuple[str, str], ...] = (
    ("clean_pdf", "clean"), ("clean_pdf", "clean"),
    ("scan_light", "mild"), ("scan_light", "typical"), ("scan_light", "harsh"),
    ("scan_heavy", "typical"), ("scan_heavy", "harsh"),
    ("phone_photo", "mild"), ("phone_photo", "typical"), ("phone_photo", "harsh"),
)  # fmt: skip
SOURCE_KIND = {"clean_pdf": "digital_pdf", "scan_light": "scanned_pdf",
               "scan_heavy": "scanned_pdf", "phone_photo": "image"}  # fmt: skip


class FreshItem(Item):
    split: Literal["dev2", "sealed", "sealed2"]  # type: ignore[assignment]
    level: Literal["clean", "mild", "typical", "harsh"]
    features: list[str]


class FreshGoldenSet(GoldenSet):
    items: list[FreshItem]  # type: ignore[assignment]


def golden_path(suite: str) -> Path:
    if suite in SEALED_SUITES:
        return DATA_ROOT / suite / f"golden_{suite}.json"
    return GOLDEN_DIR / f"citetally_v2_{suite}.json"


def hash_path(suite: str = "sealed") -> Path:
    version = "v3" if suite == "sealed2" else "v2"
    return GOLDEN_DIR / f"citetally_{version}_{suite}.sha256"


def entries_for(suite: str, facts: Facts) -> list[Entry]:
    seed = SEEDS[suite]
    vendors = _vendors(facts)
    rng = random.Random(f"{seed}:documents")
    counters = {"inv": 0, "rcp": 0, "crn": 0}
    serial: dict[str, int] = {}
    entries: list[Entry] = []
    for fam_index, family in enumerate(families_of(suite)):
        entry_type = family.entry_types[0]
        prefix = {"invoice": "inv", "receipt": "rcp", "credit_note": "crn"}[entry_type]
        for i in range(PER_FAMILY[suite]):
            vendor = vendors[family.vendors[i % len(family.vendors)]]
            counters[prefix] += 1
            serial[vendor.id] = serial.get(vendor.id, 0) + 1
            doc = generate(
                rng, facts, vendor,
                doc_id=f"{PREFIX[suite]}{prefix}-{counters[prefix]:04d}",
                entry_date=_random_date(rng, facts),
                serial=serial[vendor.id],
                style=family.style,
                entry_type="credit_note" if entry_type == "credit_note" else None,
            )  # fmt: skip
            condition, _ = COMBOS[(i + fam_index) % len(COMBOS)]
            entries.append(Entry(doc, family, condition, serial[vendor.id]))
    _rebalance_totals(entries, facts, seed)
    _separate_accidental_duplicates(entries, rng, facts)
    return entries


def level_of(entry: Entry, index_in_family: int, fam_index: int) -> str:
    return COMBOS[(index_in_family + fam_index) % len(COMBOS)][1]


def number_receipts(entries: list[Entry], seed: int) -> None:
    """Real receipts carry a number, so the key has it too (as the invoice number)."""
    rng = random.Random(f"{seed}:receipt-numbers")
    for e in entries:
        skip = {"missing_invoice_number", "duplicate_invoice_number", "duplicate_content"}
        if e.doc.entry_type == "receipt" and not any(p["kind"] in skip for p in e.planted):
            e.doc.invoice_number = f"R-{rng.randint(10000, 99999)}"
            reprint(e.doc)


def assign_levels(entries: list[Entry], suite: str) -> dict[str, str]:
    levels: dict[str, str] = {}
    families = list(families_of(suite))
    seen: dict[str, int] = {}
    for e in entries:
        k = seen.get(e.family.id, 0)
        seen[e.family.id] = k + 1
        fam_index = families.index(e.family)  # type: ignore[arg-type]
        condition, level = COMBOS[(k + fam_index) % len(COMBOS)]
        assert condition == e.condition
        levels[e.doc.id] = level
    return levels


def build_items(entries: list[Entry], levels: dict[str, str], suite: str) -> list[FreshItem]:
    items: list[FreshItem] = []
    for e in sorted(entries, key=lambda e: e.doc.id):
        assert isinstance(e.family, FreshFamily)
        extension = "jpg" if e.condition == "phone_photo" else "pdf"
        checks = sorted({c for p in e.planted for c in EXPECTED_CHECKS[p["kind"]]})
        items.append(
            FreshItem.model_validate(
                {
                    "id": e.doc.id,
                    "split": suite,
                    "template_family": e.family.id,
                    "condition": e.condition,
                    "level": levels[e.doc.id],
                    "features": list(e.family.features),
                    "file": f"data/synthetic/{suite}/{e.doc.id}.{extension}",
                    "source_kind": SOURCE_KIND[e.condition],
                    "vendor_id": e.doc.vendor.id,
                    "truth": truth(e.doc),
                    "planted": e.planted,
                    "expected_checks": checks,
                    "expected_duplicate_of": next(
                        (p["duplicate_of"] for p in e.planted if "duplicate_of" in p), None
                    ),
                    "notes": "; ".join(p["detail"] for p in e.planted)
                    or "clean: a correct reader should raise no check",
                }
            )
        )
    return items


def problems(items: list[FreshItem], suite: str, facts: Facts) -> list[str]:
    found: list[str] = []
    ids = [i.id for i in items]
    if len(set(ids)) != len(ids):
        found.append("item ids are not unique")
    expected = PER_FAMILY[suite] * len(families_of(suite))
    if len(items) != expected:
        found.append(f"{len(items)} documents, expected {expected}")
    listed = {v.id for v in facts.vendors}
    unlisted = {v.id for v in facts.unlisted_vendors}
    by_id = {i.id: i for i in items}
    for i in items:
        if i.level not in LEVELS[i.condition]:
            found.append(f"{i.id}: level {i.level} is not used for {i.condition}")
        if i.vendor_id not in listed | unlisted:
            found.append(f"{i.id}: unknown vendor {i.vendor_id}")
        if len(i.planted) > 1:
            found.append(f"{i.id}: more than one planted problem")
        if any(p.kind == "unknown_vendor" for p in i.planted) != (i.vendor_id in unlisted):
            found.append(f"{i.id}: unknown_vendor and the vendor id disagree")
        if i.expected_duplicate_of and i.expected_duplicate_of not in by_id:
            found.append(f"{i.id}: duplicate_of is not in this set")
    kinds: list[str] = [p.kind for i in items for p in i.planted]
    for kind in PLANTED_KINDS:
        if kinds.count(kind) < MIN_PER_KIND[suite]:
            found.append(f"only {kinds.count(kind)} documents with planted {kind}")
    for condition in LEVELS:
        if sum(1 for i in items if i.condition == condition) < MIN_PER_CONDITION[suite]:
            found.append(f"too few {condition} documents")
    return found


def truth_digest(items: list[FreshItem]) -> str:
    """SHA-256 of every answer in the key: what the sealed set commits to."""
    blob = json.dumps(
        [i.model_dump(mode="json") for i in items], sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def write_files(entries: list[Entry], suite: str, facts: Facts, root: Path) -> str:
    seed = SEEDS[suite]
    block = business_block(facts)
    levels = assign_levels(entries, suite)
    digest = hashlib.sha256()
    folder = root / suite
    folder.mkdir(parents=True, exist_ok=True)
    for e in sorted(entries, key=lambda e: e.doc.id):
        assert isinstance(e.family, FreshFamily)
        pdf = render_fresh_pdf(e.doc, e.family, block)
        data, ext = make_fresh_file(pdf, e.condition, levels[e.doc.id], _file_seed(seed, e.doc.id))
        (folder / f"{e.doc.id}.{ext}").write_bytes(data)
        digest.update(f"{e.doc.id}:{hashlib.sha256(data).hexdigest()}\n".encode())
    return digest.hexdigest()


def prepare(suite: str, facts: Facts) -> list[Entry]:
    """Every document of the suite, with its planted problem (if any), before it is drawn."""
    entries = entries_for(suite, facts)
    plan_planting(
        entries,
        facts,
        SEEDS[suite],
        share=PLANTED_SHARE[suite],
        cycle=PLANT_CYCLE.get(suite, PLANTED_KINDS),
        injection_phrases=PLANT_PHRASES.get(suite),
    )
    number_receipts(entries, SEEDS[suite])
    return entries


def build(suite: str, *, files: bool = True, root: Path = DATA_ROOT) -> tuple[FreshGoldenSet, str]:
    facts_file = FACTS_OF[suite]
    facts = load_facts(facts_file)
    seed = SEEDS[suite]
    entries = prepare(suite, facts)
    digest = write_files(entries, suite, facts, root) if files else None
    levels = assign_levels(entries, suite)
    items = build_items(entries, levels, suite)
    wrong = problems(items, suite, facts)
    if wrong:
        raise ValueError("the set is not valid:\n" + "\n".join(wrong))
    counts: dict[str, Any] = {
        "documents": len(items),
        "with_planted_problem": sum(1 for i in items if i.planted),
        "by_condition": {c: sum(1 for i in items if i.condition == c) for c in LEVELS},
        "by_level": {
            f"{c}/{lv}": sum(1 for i in items if i.condition == c and i.level == lv)
            for c, lvs in LEVELS.items() for lv in lvs
        },
        "by_family": {f.id: sum(1 for i in items if i.template_family == f.id)
                      for f in families_of(suite)},
        "by_planted_kind": {k: sum(1 for i in items for p in i.planted if p.kind == k)
                            for k in PLANTED_KINDS},
    }  # fmt: skip
    golden = FreshGoldenSet(
        header=Header(
            version=2, seed=seed, generator=GENERATOR,
            facts_sha256=hashlib.sha256(facts_file.read_bytes()).hexdigest(),
            files_digest=digest, counts=counts,
            note=(
                f"SYNTHETIC TEST DATA. An invented business ({facts.business.name}). Truth is "
                "what is printed on each page, planted errors included."
                + (" Sealed: run once, after the fixes." if suite in SEALED_SUITES else "")
            ),
        ),
        items=items,
    )  # fmt: skip
    return golden, truth_digest(items)


def write(golden: FreshGoldenSet, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(golden.model_dump(mode="json"), indent=1, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def load_fresh(path: Path, split: str | None = None) -> list[FreshItem]:
    golden = FreshGoldenSet.model_validate_json(path.read_text(encoding="utf-8"))
    return [i for i in golden.items if split is None or i.split == split]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--suite", choices=list(FACTS_OF), required=True)
    parser.add_argument("--check", action="store_true", help="validate only; write nothing")
    parser.add_argument("--verify", action="store_true", help="sealed: regenerate and compare hash")
    args = parser.parse_args(argv)
    golden, digest = build(args.suite, files=not (args.check or args.verify))
    counts = golden.header.counts
    print(
        f"{counts['documents']} documents, {counts['with_planted_problem']} with a planted problem"
    )
    print(f"answer-key digest {digest}")
    if args.verify:
        committed = hash_path(args.suite).read_text(encoding="utf-8").split()[0]
        ok = committed == digest
        print(
            "MATCHES the committed hash" if ok else f"DIFFERS from the committed hash {committed}"
        )
        return 0 if ok else 1
    if not args.check:
        write(golden, golden_path(args.suite))
        if args.suite in SEALED_SUITES:
            hash_path(args.suite).write_text(
                f"{digest}  sealed answer key, see tools/synthetic/fresh_build.py\n",
                encoding="utf-8",
                newline="\n",
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
