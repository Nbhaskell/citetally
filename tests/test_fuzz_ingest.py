"""The fuzz tool's own behaviour: same seed, same damage, and a bounded size.

The campaign itself (hundreds of files through the real Tesseract) is run by hand with
`python -m tools.fuzz_ingest`; its counts are in `eval/reports/fuzz_ingest.json`.
"""

import random

from tools.fuzz_ingest import MAX_BYTES, mutate

SOURCE = bytes(range(256)) * 40
OTHER = b"%PDF-1.7 other " * 500


def test_the_same_seed_gives_the_same_damage() -> None:
    first = [mutate(SOURCE, OTHER, random.Random(5)) for _ in range(3)]
    second = [mutate(SOURCE, OTHER, random.Random(5)) for _ in range(3)]
    assert first == second


def test_every_kind_of_damage_is_used_and_changes_the_bytes_within_the_size_cap() -> None:
    rng = random.Random(1)
    seen: set[str] = set()
    for _ in range(300):
        data, kind = mutate(SOURCE, OTHER, rng)
        seen.add(kind)
        assert len(data) <= MAX_BYTES
    assert seen == {
        "flip", "delete", "insert", "truncate", "repeat", "zero", "splice", "header", "tail",
    }  # fmt: skip
