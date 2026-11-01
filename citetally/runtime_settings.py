"""The few settings a person may change from the Settings screen, kept in the database.

Everything else comes from environment variables and needs a restart. These five tune how the
checks behave, so they are stored in the `settings` table and laid over the environment values
when the app starts and whenever they are saved. A stored value equal to the environment's own is
not kept, so putting a value back to the default removes it.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal, InvalidOperation
from typing import Any

from citetally import repository as repo
from citetally.config import Settings
from citetally.dates import LOCALES

EDITABLE = (
    "default_currency",
    "locale",
    "duplicate_date_window_days",
    "outlier_ratio",
    "low_confidence",
)


def _valid(name: str, value: Any) -> Any:
    """The value in its proper type, or raises ValueError. Same limits the screen enforces."""
    if name == "default_currency":
        text = str(value)
        if len(text) != 3 or not text.isascii() or not text.isalpha() or not text.isupper():
            raise ValueError("A currency is three capital letters, such as USD.")
        return text
    if name == "locale":
        if value not in LOCALES:
            raise ValueError("That locale is not one Citetally reads dates for.")
        return str(value)
    if name == "duplicate_date_window_days":
        days = int(value)
        if not 0 <= days <= 60:
            raise ValueError("The duplicate window is between 0 and 60 days.")
        return days
    if name == "outlier_ratio":
        try:
            ratio = Decimal(str(value))
        except InvalidOperation as error:
            raise ValueError("The outlier ratio must be a number.") from error
        if not ratio.is_finite() or not Decimal(1) < ratio <= Decimal(100):
            raise ValueError("The outlier ratio is a number above 1, up to 100.")
        if ratio != ratio.quantize(Decimal("0.01")):
            raise ValueError("The outlier ratio has at most 2 decimal places.")
        return ratio
    if name == "low_confidence":
        confidence = float(value)
        if not 1 <= confidence <= 99:
            raise ValueError("The read-quality threshold is between 1 and 99.")
        return confidence
    raise ValueError(f"{name} cannot be changed here.")


def apply_overrides(base: Settings, conn: sqlite3.Connection) -> Settings:
    """The environment's settings with whatever is saved laid over them. A saved value that no
    longer passes validation is ignored rather than stopping the app from starting."""
    changes: dict[str, Any] = {}
    for name in EDITABLE:
        stored = repo.get_setting(conn, name)
        if stored is None:
            continue
        try:
            changes[name] = _valid(name, stored)
        except (ValueError, TypeError):
            continue
    return base.model_copy(update=changes)


def save(base: Settings, conn: sqlite3.Connection, changes: dict[str, Any]) -> Settings:
    """Validate and store the changed values; returns the new effective settings. Raises
    ValueError, naming the setting, when a value is not allowed. Nothing is stored then."""
    clean: dict[str, Any] = {}
    for name, value in changes.items():
        try:
            clean[name] = _valid(name, value)
        except (ValueError, TypeError) as error:
            raise ValueError(f"{name}: {error}") from error
    for name, value in clean.items():
        if value == getattr(base, name):
            repo.delete_setting(conn, name)
        else:
            repo.set_setting(conn, name, str(value))
    return apply_overrides(base, conn)
