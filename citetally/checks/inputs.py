"""What the checks look at, gathered in one place so every rule is a pure function of it."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from citetally.config import Settings
from citetally.models import CheckCode, Entry, EntryLine, Evidence, Page, Vendor


@dataclass(frozen=True)
class Thresholds:
    """The numbers that tune the checks (TRD section 8)."""

    tolerance_minor: int = 1
    duplicate_window_days: int = 7
    outlier_min_history: int = 5
    outlier_ratio: Decimal = Decimal(3)
    max_age_days: int = 400
    low_confidence: float = 75.0
    default_currency: str = "USD"
    locale: str = "en-US"
    extra_phrases: tuple[str, ...] = ()

    @classmethod
    def from_settings(cls, settings: Settings) -> Thresholds:
        phrases = tuple(p.strip() for p in settings.suspicious_phrases.split(";") if p.strip())
        return cls(
            tolerance_minor=settings.math_tolerance_minor,
            duplicate_window_days=settings.duplicate_date_window_days,
            outlier_min_history=settings.outlier_min_history,
            outlier_ratio=settings.outlier_ratio,
            max_age_days=settings.max_age_days,
            low_confidence=settings.low_confidence,
            default_currency=settings.default_currency,
            locale=settings.locale,
            extra_phrases=phrases,
        )


@dataclass(frozen=True)
class Other:
    """Another entry of the same vendor, for the duplicate check."""

    document_id: int
    entry_type: str
    invoice_number: str | None
    total_minor: int | None
    currency: str | None
    entry_date: date | None


@dataclass(frozen=True)
class History:
    """A vendor's approved or exported entries of the same type: what is usual for them."""

    totals_minor: Sequence[int] = ()
    tax_rates: Sequence[Decimal] = ()  # tax total over subtotal, where both were stated


@dataclass(frozen=True)
class CheckInput:
    entry: Entry
    lines: Sequence[EntryLine]
    evidence: Sequence[Evidence]
    pages: Sequence[Page]
    vendor: Vendor | None
    others: Sequence[Other]
    history: History
    today: date
    thresholds: Thresholds = field(default_factory=Thresholds)

    @property
    def currency(self) -> str:
        return self.entry.currency or self.thresholds.default_currency


@dataclass(frozen=True)
class Outcome:
    """One check's result. `detail` holds numbers and field names the review screen can show."""

    code: CheckCode
    passed: bool
    detail: dict[str, Any] = field(default_factory=dict)
