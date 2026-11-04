"""The 14 checks (TRD section 4.6, BACKEND_SCHEMA section 1). Pure functions: no database, no model.

Each takes a `CheckInput` and returns an `Outcome`. A check that has nothing to test passes and says
so in its detail (`"applicable": False`) rather than failing on a missing input; missing inputs are
REQUIRED_FIELDS' job. Amounts in details are integer minor units.
"""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from citetally.checks.injection import scan
from citetally.checks.inputs import CheckInput, Other, Outcome
from citetally.dates import parse_date
from citetally.models import CheckCode, HeaderField, LineField, Page, Word, required_fields
from citetally.money import line_amount_minor, parse_decimal, parse_money, tax_minor
from citetally.reading.layout import build_text

MIN_WORDS = 15  # a document with fewer words than this was probably not read
MAX_SKEW_DEGREES = 5.0  # a page straightened by more than this was badly photographed
UNUSUAL_TAX_RATE_GAP = Decimal("0.01")  # one percentage point from the vendor's usual rate
MIN_RATE_HISTORY = 3
MAX_TAX_SUBSET_LINES = 14  # the lines are tried in every combination, so only up to this many
_SHOWN = 80  # characters of a printed value kept in a detail


def _not_applicable(code: CheckCode, reason: str) -> Outcome:
    return Outcome(code, True, {"applicable": False, "reason": reason})


def _decimal(text: str | None) -> Decimal | None:
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _iso(text: str | None) -> date | None:
    try:
        return date.fromisoformat(text) if text else None
    except ValueError:
        return None


def _blank(value: str | None) -> bool:
    return value is None or not value.strip()


def _line_total(i: CheckInput) -> tuple[int, int]:
    """The sum of the line amounts and how many lines have none."""
    amounts = [line.amount_minor for line in i.lines]
    return sum(a for a in amounts if a is not None), sum(1 for a in amounts if a is None)


def _line_number(i: CheckInput, line_id: int | None) -> int | None:
    numbers = {line.id: line.line_number for line in i.lines}
    return None if line_id is None else numbers.get(line_id)


# ---- the document's own arithmetic -------------------------------------------------------------


def required_fields_check(i: CheckInput) -> Outcome:
    entry = i.entry
    present = {
        "vendor_name": entry.vendor_id is not None or not _blank(entry.vendor_name_raw),
        "invoice_number": not _blank(entry.invoice_number),
        "entry_date": entry.entry_date is not None,
        "total": entry.total_minor is not None,
        "category": entry.category_id is not None,
    }
    missing = sorted(name for name in required_fields(entry.entry_type) if not present[name])
    return Outcome(CheckCode.REQUIRED_FIELDS, not missing, {"missing": missing})


def value_in_document(i: CheckInput) -> Outcome:
    missing = [
        {
            "field": row.field.value,
            "line": _line_number(i, row.line_id),
            "printed": row.printed_text[:_SHOWN],
        }
        for row in i.evidence
        if not row.found
    ]
    return Outcome(
        CheckCode.VALUE_IN_DOCUMENT,
        not missing,
        {"checked": len(i.evidence), "not_found": missing},
    )


def line_math(i: CheckInput) -> Outcome:
    mismatches = []
    checked = 0
    for line in i.lines:
        quantity, price = _decimal(line.quantity), _decimal(line.unit_price)
        if quantity is None or price is None or line.amount_minor is None:
            continue
        checked += 1
        expected = line_amount_minor(quantity, price, i.currency)
        if abs(expected - line.amount_minor) > i.thresholds.tolerance_minor:
            mismatches.append(
                {"line": line.line_number, "expected": expected, "stated": line.amount_minor}
            )
    return Outcome(
        CheckCode.LINE_MATH,
        not mismatches,
        {"checked": checked, "skipped": len(i.lines) - checked, "mismatches": mismatches},
    )


def subtotal_match(i: CheckInput) -> Outcome:
    stated = i.entry.subtotal_minor
    if stated is None:
        return _not_applicable(CheckCode.SUBTOTAL_MATCH, "no subtotal is printed")
    if not i.lines:
        return _not_applicable(CheckCode.SUBTOTAL_MATCH, "no line items were read")
    total, without_amount = _line_total(i)
    ok = without_amount == 0 and abs(total - stated) <= i.thresholds.tolerance_minor
    return Outcome(
        CheckCode.SUBTOTAL_MATCH,
        ok,
        {"lines_sum": total, "stated": stated, "lines_without_amount": without_amount},
    )


# The rate printed beside a tax label: "Tax (8.25%)", "Levy 8.25%", "Sales tax total 14 (8.25%)".
# A scan can lose the decimal point ("8 25%") or read it as a comma; both are taken as the point.
# A number straight after the label that is followed by a bracket is a count, not the rate.
_TAX_RATE = re.compile(
    r"(?:tax|levy|vat|gst)[^\n%$\d]{0,24}(?:\d{1,3}\s*(?=\())?\(?\s*"
    r"(\d{1,2})(?:[.,\s](\d{1,3}))?\s*%",
    re.IGNORECASE,
)
MAX_PLAUSIBLE_TAX_RATE = Decimal("0.30")


def _readings(page: Page) -> list[str]:
    """The text of the page as merged, then the text of each separate reading of it."""
    texts = [page.text or ""]
    try:
        stored = json.loads(page.alt_words or "[]")
        texts += [build_text([Word.model_validate(w) for w in reading]) for reading in stored]
    except (ValueError, TypeError):
        pass
    return texts


def _rate_in(text: str) -> Decimal | None:
    """The one plausible rate this text prints beside a tax label, or None."""
    rates = set()
    for found in _TAX_RATE.finditer(text):
        rate = Decimal(f"{found.group(1)}.{found.group(2) or '0'}") / 100
        if rate <= MAX_PLAUSIBLE_TAX_RATE:
            rates.add(rate)
    return next(iter(rates)) if len(rates) == 1 else None


def printed_tax_rate(pages: Sequence[Page]) -> Decimal | None:
    """The rate the page prints beside a tax label, as a fraction, or None.

    The page may have been read more than once (the merged text and each separate reading). Each
    text gives one rate or none: two different rates in one text, or a percentage that is not
    beside a label ("save 3%"), give none for that text. The rate most texts agree on is the page's;
    a tie, or no text with a rate, gives None and no bound is applied.
    """
    votes = Counter(
        rate for page in pages for text in _readings(page) if (rate := _rate_in(text)) is not None
    )
    if not votes:
        return None
    ranked = votes.most_common(2)
    if len(ranked) == 2 and ranked[0][1] == ranked[1][1]:
        return None
    return ranked[0][0]


def _tax_reachable(
    amounts: Sequence[int], extras: Sequence[int], rate: Decimal, stated: int, tolerance: int
) -> bool:
    """Whether `stated` is `rate` applied to some non-empty set of the line amounts.

    The page does not say which lines are taxed, so every combination is tried. `extras` are the
    other amounts a tax base may include or leave out (shipping, minus a discount), in each
    combination. A cent of rounding is allowed for each line in the set.
    """
    for mask in range(1, 1 << len(amounts)):
        chosen = [a for index, a in enumerate(amounts) if mask >> index & 1]
        allowed = max(tolerance, len(chosen))
        base = sum(chosen)
        if any(abs(tax_minor(base + extra, rate) - stated) <= allowed for extra in extras):
            return True
    return False


def tax_match(i: CheckInput) -> Outcome:
    stated = i.entry.tax_total_minor
    if stated is None:
        return _not_applicable(CheckCode.TAX_MATCH, "no tax is printed")
    taxed = [
        (line.amount_minor, rate)
        for line in i.lines
        if line.amount_minor is not None and (rate := _decimal(line.tax_rate)) is not None
    ]
    if taxed:
        expected = sum(tax_minor(amount, rate) for amount, rate in taxed)
        allowed = max(i.thresholds.tolerance_minor, len(taxed))  # a cent of rounding per line
        return Outcome(
            CheckCode.TAX_MATCH,
            abs(expected - stated) <= allowed,
            {
                "rate_printed": True,
                "expected": expected,
                "stated": stated,
                "taxed_lines": len(taxed),
            },
        )
    # No rate was read for a line. Report what the tax implies, and where the page prints one rate
    # beside the word "tax", hold the tax against it: at most that rate on everything that could
    # be taxed. Less is fine (some lines may be untaxed); more cannot be right.
    base = i.entry.subtotal_minor
    if base is None and i.lines:
        total, without_amount = _line_total(i)
        base = total if without_amount == 0 else None
    detail: dict[str, Any] = {"rate_printed": False, "stated": stated}
    page_rate = printed_tax_rate(i.pages)
    if page_rate is not None and base is not None:
        most = tax_minor(base + (i.entry.shipping_minor or 0), page_rate)
        detail.update({"printed_rate": str(page_rate), "most": most})
        if stated > most + i.thresholds.tolerance_minor:
            return Outcome(CheckCode.TAX_MATCH, False, detail)
    # A tax under that ceiling can still be impossible: it has to be the rate on some of the lines.
    line_amounts = [line.amount_minor for line in i.lines]
    if (
        page_rate is not None
        and line_amounts
        and None not in line_amounts
        and len(line_amounts) <= MAX_TAX_SUBSET_LINES
    ):
        shipping, discount = i.entry.shipping_minor or 0, i.entry.discount_minor or 0
        extras = sorted({0, shipping, -discount, shipping - discount})
        reachable = _tax_reachable(
            [a for a in line_amounts if a is not None],
            extras,
            page_rate,
            stated,
            i.thresholds.tolerance_minor,
        )
        detail.update({"printed_rate": str(page_rate), "reachable": reachable})
        if not reachable:
            return Outcome(CheckCode.TAX_MATCH, False, detail)
    if base:
        implied = (Decimal(stated) / Decimal(base)).quantize(Decimal("0.0001"))
        detail["implied_rate"] = str(implied)
        usual = list(i.history.tax_rates)
        if len(usual) >= MIN_RATE_HISTORY:
            median = statistics.median(usual).quantize(Decimal("0.0001"))
            detail["usual_rate"] = str(median)
            detail["unusual"] = abs(implied - median) > UNUSUAL_TAX_RATE_GAP
    return Outcome(CheckCode.TAX_MATCH, True, detail)


def total_match(i: CheckInput) -> Outcome:
    entry = i.entry
    if entry.total_minor is None:
        return _not_applicable(CheckCode.TOTAL_MATCH, "no total was read")
    base = entry.subtotal_minor
    if base is None:
        if not i.lines:
            return _not_applicable(CheckCode.TOTAL_MATCH, "no subtotal or line items")
        base, _ = _line_total(i)
    expected = (
        base
        + (entry.tax_total_minor or 0)
        + (entry.shipping_minor or 0)
        - (entry.discount_minor or 0)
    )
    return Outcome(
        CheckCode.TOTAL_MATCH,
        abs(expected - entry.total_minor) <= i.thresholds.tolerance_minor,
        {"expected": expected, "stated": entry.total_minor},
    )


# ---- the document against the rest of the books ------------------------------------------------


def _key(number: str | None) -> str:
    return "".join(ch for ch in (number or "").casefold() if ch.isalnum())


def _near_content(i: CheckInput, other: Other) -> bool:
    entry = i.entry
    mine = _iso(entry.entry_date)
    if entry.total_minor is None or mine is None or other.entry_date is None:
        return False
    if other.total_minor != entry.total_minor:
        return False
    if (other.currency or i.thresholds.default_currency) != i.currency:
        return False
    return abs((mine - other.entry_date).days) <= i.thresholds.duplicate_window_days


def duplicate_suspect(i: CheckInput) -> Outcome:
    if i.entry.vendor_id is None:
        return _not_applicable(CheckCode.DUPLICATE_SUSPECT, "the vendor is not known yet")
    matches = []
    mine = _key(i.entry.invoice_number)
    for other in i.others:
        if other.entry_type != i.entry.entry_type.value:
            continue  # a credit note is not a duplicate of the invoice it reverses
        if mine and mine == _key(other.invoice_number):
            matches.append({"document_id": other.document_id, "reason": "invoice_number"})
        elif _near_content(i, other):
            matches.append({"document_id": other.document_id, "reason": "vendor_total_date"})
    return Outcome(CheckCode.DUPLICATE_SUSPECT, not matches, {"matches": matches})


def unknown_vendor(i: CheckInput) -> Outcome:
    return Outcome(CheckCode.UNKNOWN_VENDOR, i.entry.vendor_id is not None, {})


def amount_outlier(i: CheckInput) -> Outcome:
    total, history = i.entry.total_minor, list(i.history.totals_minor)
    need = i.thresholds.outlier_min_history
    if total is None or i.entry.vendor_id is None:
        return _not_applicable(CheckCode.AMOUNT_OUTLIER, "no vendor or total to compare")
    if len(history) < need:
        return Outcome(
            CheckCode.AMOUNT_OUTLIER,
            True,
            {"enough_history": False, "history": len(history), "needed": need},
        )
    median = Decimal(str(statistics.median(history)))
    ratio = i.thresholds.outlier_ratio
    high = median > 0 and Decimal(total) >= median * ratio
    low = median > 0 and Decimal(total) * ratio <= median
    return Outcome(
        CheckCode.AMOUNT_OUTLIER,
        not (high or low),
        {
            "enough_history": True,
            "history": len(history),
            "median": str(median),
            "stated": total,
            "direction": "high" if high else "low" if low else None,
        },
    )


def date_sanity(i: CheckInput) -> Outcome:
    entry_date, due = _iso(i.entry.entry_date), _iso(i.entry.due_date)
    if entry_date is None:
        return _not_applicable(CheckCode.DATE_SANITY, "no entry date")
    problems = []
    if entry_date > i.today + timedelta(days=1):
        problems.append("in_the_future")
    if entry_date < i.today - timedelta(days=i.thresholds.max_age_days):
        problems.append("too_old")
    if due is not None and due < entry_date:
        problems.append("due_before_entry")
    return Outcome(CheckCode.DATE_SANITY, not problems, {"problems": problems})


def currency_check(i: CheckInput) -> Outcome:
    if i.entry.currency is None:
        return _not_applicable(CheckCode.CURRENCY_CHECK, "no currency was read")
    usual = (i.vendor.default_currency if i.vendor else None) or i.thresholds.default_currency
    return Outcome(
        CheckCode.CURRENCY_CHECK,
        i.entry.currency == usual,
        {"stated": i.entry.currency, "usual": usual},
    )


# ---- the page itself ---------------------------------------------------------------------------


def low_read_quality(i: CheckInput) -> Outcome:
    confidences = [p.mean_confidence for p in i.pages if p.mean_confidence is not None]
    mean = sum(confidences) / len(confidences) if confidences else None
    words = sum(p.word_count for p in i.pages)
    skews = [abs(p.skew_degrees) for p in i.pages if p.skew_degrees is not None]
    reasons = []
    if mean is not None and mean < i.thresholds.low_confidence:
        reasons.append("low_confidence")
    if i.pages and words < MIN_WORDS:
        reasons.append("very_few_words")
    if skews and max(skews) > MAX_SKEW_DEGREES:
        reasons.append("large_skew")
    return Outcome(
        CheckCode.LOW_READ_QUALITY,
        not reasons,
        {
            "mean_confidence": None if mean is None else round(mean, 1),
            "words": words,
            "max_skew": round(max(skews), 1) if skews else None,
            "reasons": reasons,
        },
    )


_DATE_FIELDS = {HeaderField.ENTRY_DATE, HeaderField.DUE_DATE}
_MONEY_FIELDS = {
    HeaderField.SUBTOTAL,
    HeaderField.TAX_TOTAL,
    HeaderField.SHIPPING,
    HeaderField.DISCOUNT,
    HeaderField.TOTAL,
    LineField.AMOUNT,
}
_DECIMAL_FIELDS = {LineField.QUANTITY, LineField.UNIT_PRICE}


def ambiguous_format(i: CheckInput) -> Outcome:
    """A printed date or number that reads two ways. Evidence keeps what the model copied, so the
    parser that grounding used is run on it again."""
    locale, dollar = i.thresholds.locale, i.thresholds.default_currency
    found = []
    for row in i.evidence:
        parsed: Any = None
        if row.field in _DATE_FIELDS:
            parsed = parse_date(row.printed_text, locale)
        elif row.field in _MONEY_FIELDS:
            parsed = parse_money(row.printed_text, locale, dollar)
        elif row.field in _DECIMAL_FIELDS:
            parsed = parse_decimal(row.printed_text, locale, dollar)
        if parsed is not None and parsed.ambiguous:
            found.append(
                {
                    "field": row.field.value,
                    "line": _line_number(i, row.line_id),
                    "readings": [str(reading) for reading in parsed.readings],
                }
            )
    return Outcome(CheckCode.AMBIGUOUS_FORMAT, not found, {"ambiguous": found})


def suspicious_text(i: CheckInput) -> Outcome:
    findings = scan([page.text for page in i.pages], i.thresholds.extra_phrases)
    return Outcome(
        CheckCode.SUSPICIOUS_TEXT,
        not findings,
        {"matches": [{"pattern": f.pattern, "page": f.page_number} for f in findings]},
    )


RULES: dict[CheckCode, Callable[[CheckInput], Outcome]] = {
    CheckCode.REQUIRED_FIELDS: required_fields_check,
    CheckCode.VALUE_IN_DOCUMENT: value_in_document,
    CheckCode.LINE_MATH: line_math,
    CheckCode.SUBTOTAL_MATCH: subtotal_match,
    CheckCode.TAX_MATCH: tax_match,
    CheckCode.TOTAL_MATCH: total_match,
    CheckCode.DUPLICATE_SUSPECT: duplicate_suspect,
    CheckCode.UNKNOWN_VENDOR: unknown_vendor,
    CheckCode.AMOUNT_OUTLIER: amount_outlier,
    CheckCode.DATE_SANITY: date_sanity,
    CheckCode.CURRENCY_CHECK: currency_check,
    CheckCode.LOW_READ_QUALITY: low_read_quality,
    CheckCode.AMBIGUOUS_FORMAT: ambiguous_format,
    CheckCode.SUSPICIOUS_TEXT: suspicious_text,
}
