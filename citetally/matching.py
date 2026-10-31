"""Vendor matching and category choice (TRD section 4.5). Plain code; the model decides nothing.

An exact or alias match is applied automatically. A near miss is only a suggestion the reviewer can
accept, so a wrong vendor never gets in without a person choosing it. A name that matches nothing
leaves the vendor empty and `UNKNOWN_VENDOR` fails until someone picks or creates one.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from citetally import repository as repo
from citetally.models import CategorySource, Vendor, VendorAlias, VendorMatchMethod

FUZZY_MIN_SCORE = 0.75  # below this a name is not offered as a suggestion
MAX_SUGGESTIONS = 3
_TOKEN_MATCH = 0.8  # how alike two words must be to count as the same word

_LEGAL_SUFFIXES = frozenset(
    {
        *("inc", "incorporated", "llc", "llp", "lp", "pllc", "ltd", "limited"),
        *("co", "company", "corp", "corporation", "plc", "gmbh", "pty", "sa", "ag"),
    }
)
_TRAILING = _LEGAL_SUFFIXES | {"and"}


def normalize_name(name: str) -> str:
    """Lowercase, accents and punctuation removed, "&" read as "and", legal suffixes dropped."""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    # apostrophes (straight, curly, grave) vanish instead of splitting a word: "O'Neil" is "oneil"
    text = "".join(
        ch for ch in text.casefold() if ch not in "'`" and unicodedata.category(ch) != "Pf"
    ).replace("&", " and ")
    tokens = re.sub(r"[\W_]+", " ", text).split()
    while len(tokens) > 1 and tokens[-1] in _TRAILING:
        tokens.pop()
    return " ".join(tokens)


@dataclass(frozen=True)
class Suggestion:
    vendor_id: int
    score: float


@dataclass(frozen=True)
class VendorMatch:
    vendor_id: int | None  # set only for an exact or alias match
    method: VendorMatchMethod | None
    score: float | None
    suggestions: tuple[Suggestion, ...]  # best first; empty when a match was applied

    @property
    def applied(self) -> bool:
        return self.vendor_id is not None


@dataclass(frozen=True)
class CategoryChoice:
    category_id: int | None
    source: CategorySource | None


@dataclass(frozen=True)
class Matched:
    vendor: VendorMatch
    category: CategoryChoice


def _word_score(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if any(ch.isdigit() for ch in a + b):
        return 0.0  # one changed digit is a different name
    ratio = SequenceMatcher(None, a, b).ratio()
    return ratio if ratio >= _TOKEN_MATCH else 0.0


def _similarity(a: str, b: str) -> float:
    """Token-set similarity: words may be slightly misspelt, missing or extra."""
    left, right = a.split(), b.split()
    if not left or not right:
        return 0.0
    pairs = sorted(
        ((_word_score(x, y), i, j) for i, x in enumerate(left) for j, y in enumerate(right)),
        reverse=True,
    )
    used_left: set[int] = set()
    used_right: set[int] = set()
    total = 0.0
    for score, i, j in pairs:
        if score > 0 and i not in used_left and j not in used_right:
            used_left.add(i)
            used_right.add(j)
            total += score
    return 2 * total / (len(left) + len(right))


def match_vendor(
    printed: str | None, vendors: Sequence[Vendor], aliases: Sequence[VendorAlias]
) -> VendorMatch:
    none = VendorMatch(None, None, None, ())
    normalized = normalize_name(printed) if printed else ""
    if not normalized:
        return none
    active = {v.id: v for v in vendors if v.is_active}
    for vendor in active.values():
        if vendor.normalized_name == normalized:
            return VendorMatch(vendor.id, VendorMatchMethod.EXACT, 1.0, ())
    for found in aliases:
        if found.vendor_id in active and found.normalized_alias == normalized:
            return VendorMatch(found.vendor_id, VendorMatchMethod.ALIAS, 1.0, ())

    names: dict[int, list[str]] = {vid: [v.normalized_name] for vid, v in active.items()}
    for found in aliases:
        if found.vendor_id in active:
            names[found.vendor_id].append(found.normalized_alias)
    scored = [
        Suggestion(vid, round(max(_similarity(normalized, name) for name in candidates), 4))
        for vid, candidates in names.items()
    ]
    best = sorted(
        (s for s in scored if s.score >= FUZZY_MIN_SCORE), key=lambda s: (-s.score, s.vendor_id)
    )
    return VendorMatch(None, None, None, tuple(best[:MAX_SUGGESTIONS]))


def choose_category(
    vendor: Vendor | None, suggestion: str | None, categories: Mapping[str, int]
) -> CategoryChoice:
    """The vendor's default if there is one, else the model's suggestion, else leave it empty.

    `categories` maps the code of each active category to its id.
    """
    if vendor is not None and vendor.default_category_id is not None:
        return CategoryChoice(vendor.default_category_id, CategorySource.VENDOR_DEFAULT)
    if suggestion is not None and suggestion in categories:
        return CategoryChoice(categories[suggestion], CategorySource.MODEL)
    return CategoryChoice(None, None)


def match_document(
    conn: sqlite3.Connection, printed_vendor: str | None, category_suggestion: str | None
) -> Matched:
    """Match the printed vendor and choose a category, reading what is needed from the database."""
    vendors = repo.list_vendors(conn)
    match = match_vendor(printed_vendor, vendors, repo.list_aliases(conn))
    known = next((v for v in vendors if v.id == match.vendor_id), None)
    categories = {c.code: c.id for c in repo.list_categories(conn) if c.is_active}
    return Matched(match, choose_category(known, category_suggestion, categories))
