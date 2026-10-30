"""Enums are defined once. They must match the schema document and the database CHECKs."""

import re
import sqlite3
import types
import typing
from enum import StrEnum
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from citetally import db, models
from citetally.config import Settings

SCHEMA_DOC = Path(__file__).resolve().parent.parent / "docs" / "BACKEND_SCHEMA.md"


@pytest.fixture(scope="module")
def conn() -> sqlite3.Connection:
    connection = db.connect(":memory:")
    db.migrate(connection)
    return connection


def doc_enums() -> dict[str, list[str]]:
    """The enumeration table in docs/BACKEND_SCHEMA.md section 1."""
    text = SCHEMA_DOC.read_text(encoding="utf-8")
    section = text.split("## 1. Enumerations", 1)[1].split("### Check codes", 1)[0]
    found: dict[str, list[str]] = {}
    for row in re.finditer(r"^\| `([^`]+)`(?: \((\w+)\))? \| (.+?) \|$", section, re.M):
        name = row.group(1) if row.group(2) is None else f"{row.group(1)}:{row.group(2)}"
        found[name] = re.findall(r"`([^`]+)`", row.group(3))
    return found


def doc_blocking() -> dict[str, bool]:
    text = SCHEMA_DOC.read_text(encoding="utf-8")
    section = text.split("### Check codes: default severity", 1)[1].split("### Required", 1)[0]
    return {
        m.group(1): m.group(2) == "yes"
        for m in re.finditer(r"^\| `([A-Z_]+)` \| (yes|no) \|", section, re.M)
    }


def check_constraints(conn: sqlite3.Connection) -> dict[tuple[str, str], set[str]]:
    """Every CHECK (column IN (...)) in the database, keyed by (table, column)."""
    found: dict[tuple[str, str], set[str]] = {}
    rows = conn.execute("SELECT name, sql FROM sqlite_master WHERE type = 'table'").fetchall()
    for table in rows:
        for match in re.finditer(r"CHECK\s*\(\s*(\w+)\s+IN\s*\(([^)]*)\)\s*\)", table["sql"]):
            found[(table["name"], match.group(1))] = set(re.findall(r"'([^']*)'", match.group(2)))
    return found


def values(enum: type[StrEnum]) -> set[str]:
    return {member.value for member in enum}


def test_enums_match_the_schema_document() -> None:
    docs = doc_enums()
    expected = {
        "entry_type": models.EntryType,
        "source_kind": models.SourceKind,
        "read_method": models.ReadMethod,
        "extract_mode": models.ExtractMode,
        "document_status": models.DocumentStatus,
        "stage": models.Stage,
        "check_code": models.CheckCode,
        "field:header": models.HeaderField,
        "field:line": models.LineField,
        "decision": models.Decision,
        "vendor_match_method": models.VendorMatchMethod,
        "category_source": models.CategorySource,
        "export_profile": models.ExportProfile,
        "provider": models.Provider,
    }
    assert set(docs) == set(expected), "an enumeration in the document is not in the code"
    for name, enum in expected.items():
        assert [m.value for m in enum] == docs[name], name


def test_every_check_constraint_in_the_database_matches_an_enum(conn: sqlite3.Connection) -> None:
    mapping: dict[tuple[str, str], set[str]] = {
        ("documents", "mime_type"): set(models.MIME_TYPES),
        ("documents", "source_kind"): values(models.SourceKind),
        ("documents", "status"): values(models.DocumentStatus),
        ("documents", "failure_stage"): values(models.Stage),
        ("pages", "read_method"): values(models.ReadMethod),
        ("extractions", "provider"): values(models.Provider),
        ("extractions", "extract_mode"): values(models.ExtractMode),
        ("entries", "entry_type"): values(models.EntryType),
        ("entries", "vendor_match_method"): values(models.VendorMatchMethod),
        ("entries", "category_source"): values(models.CategorySource),
        ("evidence", "field"): values(models.HeaderField) | values(models.LineField),
        ("checks", "check_code"): values(models.CheckCode),
        ("field_edits", "field"): values(models.EditField),
        ("reviews", "decision"): values(models.Decision),
        ("exports", "profile"): values(models.ExportProfile),
    }
    assert check_constraints(conn) == mapping


def test_edit_fields_are_the_header_and_line_fields_plus_category_and_entry_type() -> None:
    assert values(models.EditField) == (
        values(models.HeaderField) | values(models.LineField) | {"category", "entry_type"}
    )


def test_the_config_provider_choices_come_from_the_same_list() -> None:
    options = typing.get_args(Settings.model_fields["model_provider"].annotation)
    assert set(options) == values(models.Provider)


def test_blocking_checks_match_the_schema_document() -> None:
    documented = doc_blocking()
    assert set(documented) == values(models.CheckCode)
    for code in models.CheckCode:
        assert models.is_blocking(code) == documented[code.value], code
    assert {c for c in models.CheckCode if documented[c.value]} == models.BLOCKING_CHECKS


def test_required_fields_per_entry_type() -> None:
    header = {"vendor_name", "entry_date", "total", "category"}
    assert models.required_fields(models.EntryType.RECEIPT) == header
    assert models.required_fields(models.EntryType.INVOICE) == header | {"invoice_number"}
    assert models.required_fields(models.EntryType.CREDIT_NOTE) == header | {"invoice_number"}


ROW_MODELS: dict[str, type[BaseModel]] = {
    "schema_migrations": models.SchemaMigration,
    "categories": models.Category,
    "vendors": models.Vendor,
    "vendor_aliases": models.VendorAlias,
    "documents": models.Document,
    "pages": models.Page,
    "extractions": models.Extraction,
    "entries": models.Entry,
    "entry_lines": models.EntryLine,
    "evidence": models.Evidence,
    "checks": models.Check,
    "field_edits": models.FieldEdit,
    "reviews": models.Review,
    "exports": models.Export,
    "export_items": models.ExportItem,
    "audit_events": models.AuditEvent,
    "settings": models.Setting,
}


def allows_none(annotation: object) -> bool:
    if annotation is type(None):
        return True
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        return any(allows_none(a) for a in typing.get_args(annotation))
    return False


def test_there_is_a_row_model_for_every_table(conn: sqlite3.Connection) -> None:
    tables = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    assert set(ROW_MODELS) == tables


@pytest.mark.parametrize("table", sorted(ROW_MODELS))
def test_row_model_fields_match_the_table_columns(conn: sqlite3.Connection, table: str) -> None:
    model = ROW_MODELS[table]
    columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
    assert set(model.model_fields) == {c["name"] for c in columns}
    for column in columns:
        field = model.model_fields[column["name"]]
        nullable = column["notnull"] == 0 and column["pk"] == 0
        assert allows_none(field.annotation) == nullable, (table, column["name"])


def test_row_models_reject_unknown_columns_and_bad_enum_values() -> None:
    good = {
        "id": 1,
        "code": "SUPPLIES",
        "name": "Supplies",
        "is_active": 1,
        "created_at": "2026-10-30T10:00:00.000Z",
    }
    assert models.Category.model_validate(good).is_active is True
    with pytest.raises(ValidationError):
        models.Category.model_validate({**good, "colour": "red"})
    with pytest.raises(ValidationError):
        models.Review.model_validate(
            {"id": 1, "document_id": 1, "decision": "pay", "created_at": "x", "reviewer": "local"}
            | {"reason": None, "edited": 0, "overrides": 0, "review_seconds": None}
        )


def test_the_documented_example_of_extracted_fields_validates() -> None:
    fields = models.ExtractedFields.model_validate(
        {
            "entry_type": "invoice",
            "vendor_name": "Millrace Plumbing Supply Co.",
            "invoice_number": "INV-20417",
            "entry_date": "03/14/2026",
            "due_date": "04/13/2026",
            "po_number": None,
            "currency": "$",
            "lines": [
                {
                    "description": "Wax ring with bolts",
                    "quantity": "4",
                    "unit_price": "$5.40",
                    "amount": "$21.60",
                    "tax_rate": None,
                }
            ],
            "subtotal": "$21.60",
            "tax_total": "$1.51",
            "shipping": None,
            "discount": None,
            "total": "$23.11",
            "category_suggestion": "SUPPLIES",
        }
    )
    assert fields.lines[0].unit_price == "$5.40"


def test_extracted_fields_copy_printed_text_so_numbers_and_extras_are_rejected() -> None:
    base = {"entry_type": "invoice", "vendor_name": "A", "lines": []}
    models.ExtractedFields.model_validate(base)
    with pytest.raises(ValidationError):
        models.ExtractedFields.model_validate({**base, "total": 23.11})  # a number, not text
    with pytest.raises(ValidationError):
        models.ExtractedFields.model_validate({**base, "total": 2311})
    with pytest.raises(ValidationError):
        models.ExtractedFields.model_validate({**base, "approved": "yes"})  # unknown key
    with pytest.raises(ValidationError):
        models.ExtractedFields.model_validate({**base, "entry_type": "statement"})


def test_words_have_normalized_coordinates_and_a_nullable_confidence() -> None:
    word = models.Word.model_validate(
        {"t": "Total", "x0": 0.612, "y0": 0.823, "x1": 0.661, "y1": 0.841, "c": None}
    )
    assert word.c is None
    with pytest.raises(ValidationError):
        models.Word.model_validate({"t": "x", "x0": -0.1, "y0": 0, "x1": 0.5, "y1": 0.5, "c": 90})
    with pytest.raises(ValidationError):
        models.Word.model_validate({"t": "x", "x0": 0.6, "y0": 0, "x1": 0.5, "y1": 0.5, "c": 90})
