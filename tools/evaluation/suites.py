"""Which documents, answer key and business each split belongs to.

    tuned, heldout   the first set (`eval/golden/citetally_v1.json`, `universe/facts.json`)
    dev2             the second business, for developing fixes (`citetally_v2_dev2.json`)
    sealed           the second business, run once after the fixes (answer key under `data/`)

`heldout` and `sealed` open only on purpose. The sealed key must also hash to the value committed
before any fix was made, so a changed set cannot be run by mistake.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tools.synthetic import fresh_build
from tools.synthetic.facts import Facts, load_facts
from tools.synthetic.golden import GOLDEN_FILE, Item, load_golden

SPLITS = ("tuned", "heldout", "dev2", "sealed")
OPENS_ONCE = ("heldout", "sealed")


@dataclass(frozen=True)
class Suite:
    items: list[Item]
    facts: Facts
    golden_file: Path


def load_suite(split: str, *, unseal: bool = False) -> Suite:
    if split not in SPLITS:
        raise ValueError(f"unknown split {split!r}; use one of {', '.join(SPLITS)}")
    if split in OPENS_ONCE and not unseal:
        raise PermissionError(f"The {split} split is sealed. It is opened once, on purpose.")
    if split in {"tuned", "heldout"}:
        items = load_golden(split=split, unseal_heldout=unseal)
        return Suite(items, load_facts(), GOLDEN_FILE)
    path = fresh_build.golden_path(split)
    fresh = fresh_build.load_fresh(path, split)
    if split == "sealed":
        committed = fresh_build.hash_path().read_text(encoding="utf-8").split()[0]
        if fresh_build.truth_digest(fresh) != committed:
            raise ValueError(
                "The sealed answer key does not match the hash committed before the fixes."
            )
    return Suite(list(fresh), load_facts(fresh_build.FACTS_RIDGE), path)
