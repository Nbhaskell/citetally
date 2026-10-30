"""The fact sheet for the invented business. Every generated document is built from it.

Everything here is synthetic. This module is test-data tooling: it deliberately does not import
the product's own money or date code, so the truth it records is computed independently of the
code the evaluation will later measure.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FACTS_FILE = Path(__file__).resolve().parent.parent.parent / "universe" / "facts.json"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Address(_Strict):
    street: str
    city: str
    state: str = ""
    zip: str
    country: str = "United States"


class Business(_Strict):
    name: str
    kind: str
    address: Address
    phone: str
    email: str
    default_currency: str
    locale: str
    sales_tax_rate: Decimal


class Item(_Strict):
    description: str
    unit_price: Decimal
    qty: tuple[int, int]
    taxable: bool


class Vendor(_Strict):
    id: str
    name: str
    aliases: list[str]
    category: str
    currency: str
    entry_type: Literal["invoice", "receipt"]
    terms_days: int
    credit_notes: bool
    invoice_prefix: str
    invoice_start: int
    tax_rate_override: Decimal | None = Field(default=None, alias="tax_rate")
    address: Address
    phone: str
    email: str
    items: list[Item]

    def tax_rate(self, business: Business) -> Decimal:
        """The rate applied to this vendor's taxable lines."""
        if self.tax_rate_override is not None:
            return self.tax_rate_override
        return business.sales_tax_rate


class Facts(_Strict):
    schema_version: int = Field(alias="schema")
    note: str
    as_of: date
    date_range: tuple[date, date]
    business: Business
    categories: list[str]
    vendors: list[Vendor]


def load_facts(path: Path = FACTS_FILE) -> Facts:
    return Facts.model_validate_json(path.read_text(encoding="utf-8"))
