"""Grounding: find every value the model returned on the page, and parse it (TRD section 4.4).

Code only; no model. For each printed string the model copied we look for the run of page words
that spells it. A letter slip from OCR is tolerated, but a run whose digits differ is never a
match: one wrong digit is a different amount, date or number, and silently accepting it would
defeat the purpose (CLAUDE.md rule 5). If the text cannot be found, the same amount or date
printed another way may still be accepted at a lower score. A value with no place on the page is
returned with `found = False`; `VALUE_IN_DOCUMENT` fails on it later. Nothing here raises or
reports with page text.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from citetally.dates import parse_date
from citetally.models import ExtractedFields, HeaderField, LineField, Word
from citetally.money import parse_decimal, parse_money, parse_rate, to_minor
from citetally.reading.layout import clean_token, line_indices

Method = Literal["exact", "fuzzy", "numeric"]
Kind = Literal["text", "money", "decimal", "date", "rate"]

DEFAULT_THRESHOLD = 0.85
NUMERIC_SCORE = 0.75  # the score of an amount or date found printed another way
_MAX_FUZZY_CHARS = 400  # a longer printed string must match exactly
_MAX_DATE_WORDS = 4  # "14 March 2026" and "March 14, 2026" are three words

_KINDS: dict[HeaderField | LineField, Kind] = {
    HeaderField.ENTRY_DATE: "date",
    HeaderField.DUE_DATE: "date",
    HeaderField.SUBTOTAL: "money",
    HeaderField.TAX_TOTAL: "money",
    HeaderField.SHIPPING: "money",
    HeaderField.DISCOUNT: "money",
    HeaderField.TOTAL: "money",
    LineField.AMOUNT: "money",
    LineField.QUANTITY: "decimal",
    LineField.UNIT_PRICE: "decimal",
    LineField.TAX_RATE: "rate",
}
_HEADER_ORDER = tuple(HeaderField)
_MONEY_FIELDS = frozenset(f for f, kind in _KINDS.items() if kind == "money")
_LINE_ORDER = (
    LineField.DESCRIPTION,
    LineField.QUANTITY,
    LineField.UNIT_PRICE,
    LineField.AMOUNT,
    LineField.TAX_RATE,
)


@dataclass(frozen=True)
class GroundedValue:
    """One printed value: where it is on the page, and what it means."""

    field: HeaderField | LineField
    line_index: int | None  # position in `fields.lines`; None for a header field
    printed_text: str
    found: bool
    page_number: int | None  # 1-based
    x0: float | None  # union of the matched words' boxes, fractions of the page
    y0: float | None
    x1: float | None
    y1: float | None
    match_score: float | None  # 0 to 1
    method: Method | None
    parsed: bool  # False when a money, decimal or date string could not be read
    value: Decimal | date | None  # as printed, sign included
    amount_minor: int | None  # money fields only
    ambiguous: bool
    readings: tuple[str, ...]  # every plausible reading when ambiguous, the chosen one first


@dataclass(frozen=True)
class Grounding:
    values: list[GroundedValue]
    line_tax_rates: list[Decimal | None]  # per line, as a fraction ("7%" is 0.07)
    currency: str  # the ISO code the amounts were read in
    rejected: tuple[
        HeaderField, ...
    ] = ()  # returned by the model, but the page labels it otherwise

    @property
    def found_count(self) -> int:
        return sum(1 for value in self.values if value.found)

    @property
    def coverage(self) -> float:
        """The share of printed values that were found on the page (1.0 when none were printed)."""
        return self.found_count / len(self.values) if self.values else 1.0


@dataclass
class _Page:
    number: int
    words: Sequence[Word]
    order: list[int]  # word positions in reading order, empty words left out
    norm: dict[int, str]
    loose: dict[int, str]  # the same words without brackets and sentence punctuation around them
    claimed: set[int]


@dataclass(frozen=True)
class _Candidate:
    page: _Page
    positions: tuple[int, ...]  # word positions
    score: float
    method: Method

    @property
    def rank(self) -> tuple[float, int, int]:
        overlap = sum(1 for position in self.positions if position in self.page.claimed)
        return (-self.score, overlap, self.page.number)


def _normalise(text: str) -> str:
    return "".join(unicodedata.normalize("NFKC", text).casefold().split())


_OPENING = "([{<\"'"
_CLOSING = ")]}>\"'.,;:"


def _trim(text: str) -> str:
    """A word without the brackets and sentence punctuation around it: "(6.5%)" is "6.5%"."""
    trimmed = text.lstrip(_OPENING).rstrip(_CLOSING)
    return trimmed or text


def _digits(text: str) -> str:
    return "".join(ch for ch in text if ch.isdigit())


def _make_page(number: int, words: Sequence[Word]) -> _Page:
    norm = {i: _normalise(clean_token(word.t)) for i, word in enumerate(words)}
    loose = {i: _trim(text) for i, text in norm.items()}
    order = [i for line in line_indices(words) for i in line if norm[i]]
    return _Page(number, words, order, norm, loose, set())


def _distance(a: str, b: str, limit: int) -> int:
    """Edit distance, or `limit + 1` as soon as it must exceed `limit`."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    previous = list(range(len(b) + 1))
    for i, ch_a in enumerate(a, start=1):
        current = [i]
        for j, ch_b in enumerate(b, start=1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ch_a != ch_b))
            )
        if min(current) > limit:
            return limit + 1
        previous = current
    return previous[-1]


def _search(
    page: _Page, target: str, threshold: float, *, loose: bool = False
) -> _Candidate | None:
    """The best run of words that spells `target`, or None. `loose` ignores the brackets and
    sentence punctuation around each page word."""
    words = page.loose if loose else page.norm
    size = len(target)
    limit = int((1 - threshold) * size) if size <= _MAX_FUZZY_CHARS else 0
    target_digits = _digits(target)
    best: _Candidate | None = None
    order = page.order
    for start in range(len(order)):
        joined = ""
        for end in range(start, len(order)):
            joined += words[order[end]]
            if len(joined) > size + limit:
                break
            if len(joined) < size - limit:
                continue
            if _digits(joined) != target_digits:
                continue
            distance = 0 if joined == target else _distance(joined, target, limit)
            if distance > limit:
                continue
            score = 1 - distance / max(len(joined), size)
            if score < threshold:
                continue
            candidate = _Candidate(
                page,
                tuple(order[start : end + 1]),
                round(score, 4),
                "exact" if distance == 0 else "fuzzy",
            )
            if best is None or candidate.rank < best.rank:
                best = candidate
    return best


def _inside_word(page: _Page, target: str) -> _Candidate | None:
    """A currency symbol printed attached to an amount: "$" inside "$38.00"."""
    for position in page.order:
        if target in page.norm[position]:
            return _Candidate(page, (position,), 1.0, "exact")
    return None


def _parse_text(kind: Kind, text: str, locale: str, currency: str) -> object:
    if kind == "money":
        return parse_money(text, locale, currency)
    if kind == "decimal":
        return parse_decimal(text, locale, currency)
    return parse_date(text, locale)


def _numeric(
    pages: Sequence[_Page], kind: Kind, wanted: Decimal | date, locale: str, currency: str
) -> _Candidate | None:
    """The same amount or date, printed some other way, anywhere on the page."""
    best: _Candidate | None = None
    for page in pages:
        for at in range(len(page.order)):
            for width in range(1, (_MAX_DATE_WORDS if kind == "date" else 1) + 1):
                run = page.order[at : at + width]
                if len(run) < width:
                    break
                text = " ".join(clean_token(page.words[i].t) for i in run)
                parsed = _parse_text(kind, text, locale, currency)
                readings = getattr(parsed, "readings", None)
                if parsed is None or readings is None:
                    continue
                if getattr(parsed, "value", None) == wanted or wanted in readings:
                    candidate = _Candidate(page, tuple(run), NUMERIC_SCORE, "numeric")
                    if best is None or candidate.rank < best.rank:
                        best = candidate
    return best


def _text(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


def ground(
    fields: ExtractedFields,
    pages: Sequence[Sequence[Word]],
    *,
    locale: str = "en-US",
    currency: str = "USD",
    threshold: float = DEFAULT_THRESHOLD,
) -> Grounding:
    """Locate and parse every printed value in `fields`.

    `pages` holds each page's words in page order. `currency` is the business's default and what a
    bare "$" means. Nothing is raised for a value that cannot be found or read; it is reported.
    """
    indexed = [_make_page(number, words) for number, words in enumerate(pages, start=1)]
    wanted: list[tuple[HeaderField | LineField, int | None, str]] = []
    for header in _HEADER_ORDER:
        text = _text(getattr(fields, header.value))
        if text is not None:
            wanted.append((header, None, text))
    for index, line in enumerate(fields.lines):
        for line_field in _LINE_ORDER:
            text = _text(getattr(line, line_field.value))
            if text is not None:
                wanted.append((line_field, index, text))

    document_currency = next(
        (
            parsed.currency
            for field, _, text in wanted
            if _KINDS.get(field) == "money"
            and (parsed := parse_money(text, locale, currency)) is not None
            and parsed.currency is not None
        ),
        currency,
    )

    values = []
    for field, line_index, text in wanted:
        kind = _KINDS.get(field, "text")
        values.append(
            _ground_one(
                indexed,
                field,
                line_index,
                text,
                kind,
                locale,
                currency,
                document_currency,
                threshold,
            )
        )
    rates = [
        parse_rate(rate, locale) if (rate := _text(line.tax_rate)) is not None else None
        for line in fields.lines
    ]
    settled = _settle(values, indexed, locale, currency)
    rejected: tuple[HeaderField, ...] = ()
    if _not_an_invoice_number(settled, indexed, fields):
        rejected = (HeaderField.INVOICE_NUMBER,)
        settled = [v for v in settled if v.field != HeaderField.INVOICE_NUMBER]
    return Grounding(
        values=settled, line_tax_rates=rates, currency=document_currency, rejected=rejected
    )


def _occurrences(pages: Sequence[_Page], wanted: Decimal, locale: str, currency: str) -> int:
    """How many single words on the page read as exactly this amount."""
    count = 0
    for page in pages:
        for position in page.order:
            parsed = parse_money(clean_token(page.words[position].t), locale, currency)
            if parsed is not None and parsed.value == wanted:
                count += 1
    return count


def _label_left(page: _Page, value: GroundedValue) -> str:
    """The few words printed to the left of a located value on its line, lower case."""
    if None in (value.x0, value.y0, value.y1):
        return ""
    assert value.x0 is not None and value.y0 is not None and value.y1 is not None
    middle = (value.y0 + value.y1) / 2
    tolerance = max(value.y1 - value.y0, 1e-6) * 0.7
    left = [
        word
        for word in page.words
        if abs((word.y0 + word.y1) / 2 - middle) <= tolerance and word.x1 <= value.x0 + 1e-6
    ]
    left.sort(key=lambda word: word.x0)
    return " ".join(clean_token(word.t) for word in left[-4:]).casefold()


_OTHER_IDS = frozenset({"customer", "cust", "account", "acct", "po", "purchase", "policy"})
_INVOICE_WORDS = frozenset(
    {"invoice", "inv", "bill", "statement", "memo", "receipt", "ticket", "credit"}
)


def _not_an_invoice_number(
    values: list[GroundedValue], pages: Sequence[_Page], fields: ExtractedFields
) -> bool:
    """True when the value returned as the invoice number is one the page labels as something else.

    The model copied the right characters from the wrong line: a customer ID, an account or policy
    number or a purchase order. The same string given as the PO number is the same case. The number
    is not changed, only not accepted as this document's invoice number, so `REQUIRED_FIELDS` asks
    a person for the real one. "Order no." is left alone: some layouts use it for the invoice.
    """
    number = next((v for v in values if v.field == HeaderField.INVOICE_NUMBER), None)
    if number is None or not number.found:
        return False
    po = _text(fields.po_number)
    if po is not None and _normalise(po) == _normalise(number.printed_text):
        return True
    page = next((p for p in pages if p.number == number.page_number), None)
    if page is None:
        return False
    words = re.findall(r"[a-z]+", _label_left(page, number))[-3:]
    if _INVOICE_WORDS & set(words):
        return False
    return bool(_OTHER_IDS & set(words))


def _settle(
    values: list[GroundedValue], pages: Sequence[_Page], locale: str, currency: str
) -> list[GroundedValue]:
    """Drop what the page does not support and the entry does not use.

    - A currency symbol the model returned but the page does not print. The entry's currency comes
      from the amounts and the business's default, never from this field, so reporting it as a
      missing value would only make a correct document fail.
    - A subtotal and a total that are the same amount when the page prints that amount fewer times
      than there are fields claiming it. The model copied one into the other. The printed label
      says which: a label with "sub" in it is the subtotal, so the total was the copy; otherwise
      the subtotal was. A page that prints the amount for each claim keeps all of them.
    """
    by_field = {v.field: v for v in values if v.line_index is None}
    total = by_field.get(HeaderField.TOTAL)
    subtotal = by_field.get(HeaderField.SUBTOTAL)
    dropped: GroundedValue | None = None
    if (
        subtotal is not None
        and total is not None
        and subtotal.found
        and total.found
        and isinstance(subtotal.value, Decimal)
        and subtotal.value == total.value
    ):
        claims = sum(
            1 for v in values if v.found and v.field in _MONEY_FIELDS and v.value == subtotal.value
        )
        if _occurrences(pages, subtotal.value, locale, currency) < claims:
            page = next((p for p in pages if p.number == subtotal.page_number), None)
            label = _label_left(page, subtotal) if page is not None else ""
            dropped = total if "sub" in label else subtotal
    return [
        v
        for v in values
        if not (v.field == HeaderField.CURRENCY and not v.found) and v is not dropped
    ]


def _ground_one(
    pages: list[_Page],
    field: HeaderField | LineField,
    line_index: int | None,
    text: str,
    kind: Kind,
    locale: str,
    currency: str,
    document_currency: str,
    threshold: float,
) -> GroundedValue:
    parsed = None if kind in ("text", "rate") else _parse_text(kind, text, locale, currency)
    value: Decimal | date | None = getattr(parsed, "value", None)
    if kind == "rate":
        value = parse_rate(text, locale)  # not guessed without a % sign

    target = _normalise(text)
    found = [c for page in pages if (c := _search(page, target, threshold)) is not None]
    if not found and kind != "money" and field != HeaderField.CURRENCY:
        # "(6.5%)" or "INV-77:" is the printed value with punctuation around it. Money is left
        # alone: "($70.00)" is a credit, and "$70.00" must not be read from it.
        trimmed = _trim(target)
        found = [c for page in pages if (c := _search(page, trimmed, threshold, loose=True))]
    candidate = min(found, key=lambda c: c.rank, default=None)
    if candidate is None and field == HeaderField.CURRENCY:
        candidate = min(
            (c for page in pages if (c := _inside_word(page, target)) is not None),
            key=lambda c: c.rank,
            default=None,
        )
    if candidate is None and value is not None and kind not in ("text", "rate"):
        candidate = _numeric(pages, kind, value, locale, currency)

    minor = None
    if kind == "money" and isinstance(value, Decimal):
        minor = to_minor(value, getattr(parsed, "currency", None) or document_currency)
    readings = tuple(str(r) for r in getattr(parsed, "readings", ())) if parsed else ()
    ambiguous = bool(getattr(parsed, "ambiguous", False))

    words = [candidate.page.words[i] for i in candidate.positions] if candidate else []
    if candidate is not None:
        candidate.page.claimed.update(candidate.positions)
    return GroundedValue(
        field=field,
        line_index=line_index,
        printed_text=text,
        found=candidate is not None,
        page_number=candidate.page.number if candidate else None,
        x0=min((w.x0 for w in words), default=None),
        y0=min((w.y0 for w in words), default=None),
        x1=max((w.x1 for w in words), default=None),
        y1=max((w.y1 for w in words), default=None),
        match_score=candidate.score if candidate else None,
        method=candidate.method if candidate else None,
        parsed=kind == "text" or parsed is not None or (kind == "rate" and value is not None),
        value=value,
        amount_minor=minor,
        ambiguous=ambiguous,
        readings=readings if ambiguous else (),
    )
