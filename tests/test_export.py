"""CSV export, the pure part: cells, amounts, credit notes, rows and the RFC 4180 file."""

from __future__ import annotations

import csv
import io
from typing import Any

import pytest

from citetally import export as ex
from citetally.models import EntryType, ExportProfile
from tests.test_check_rules import make_entry, make_line

HOSTILE = [
    "=1+1",
    "+1+1",
    "-1+1",
    "@SUM(A1:A9)",
    "\t=1+1",
    "\r=1+1",
    "=cmd|' /C calc'!A0",
    '=HYPERLINK("http://evil.example.com","click")',
    " =1+1",
    "   @x",
    "-2+3",
    "+cmd",
]


@pytest.mark.parametrize("text", HOSTILE)
def test_a_cell_that_could_start_a_formula_is_given_a_leading_quote(text: str) -> None:
    out = ex.neutralise(text)
    assert out.startswith("'") and out[1:] == text


@pytest.mark.parametrize(
    "text", ["Kibble, 30 lb bag", "5 - 3", "a=b", "x+y", "Invoice @ home", "'=already", "0", "é=è"]
)
def test_ordinary_text_is_left_alone(text: str) -> None:
    assert ex.neutralise(text) == text


def test_empty_cells_and_control_characters() -> None:
    assert ex.neutralise(None) == "" and ex.neutralise("") == ""
    assert ex.neutralise("a\x00b\x07c") == "abc"
    assert ex.neutralise("two\nlines\tand tab") == "two\nlines\tand tab"
    assert ex.neutralise("\x00=1+1") == "'=1+1"  # the trick of hiding the "=" behind a control char


@pytest.mark.parametrize(
    ("minor", "currency", "credit", "expected"),
    [
        (15200, "USD", False, "152.00"),
        (5, "USD", False, "0.05"),
        (0, "USD", False, "0.00"),
        (0, "USD", True, "0.00"),  # never "-0.00"
        (15200, "USD", True, "-152.00"),
        (1500, "JPY", False, "1500"),
        (1500, "JPY", True, "-1500"),
        (10**13, "USD", False, "100000000000.00"),
        (123456789, "EUR", False, "1234567.89"),  # no thousands separators
        (None, "USD", False, ""),
        (None, "USD", True, ""),
    ],
)
def test_amounts_are_plain_decimal_strings_from_minor_units(
    minor: int | None, currency: str, credit: bool, expected: str
) -> None:
    assert ex.amount(minor, currency, credit=credit) == expected


def test_a_decimal_is_written_exactly_and_a_credit_note_negates_it() -> None:
    assert ex.decimal_text("4.125", credit=False) == "4.125"
    assert ex.decimal_text("4.125", credit=True) == "-4.125"
    assert ex.decimal_text("0.00", credit=True) == "0.00"
    assert ex.decimal_text(None, credit=True) == ""
    assert ex.decimal_text("=bad", credit=False) == "'=bad"  # never trusted as a number


# --- rows --------------------------------------------------------------------------------------


def item(
    entry_kwargs: dict[str, Any] | None = None, lines: list[Any] | None = None, **names: str
) -> ex.ExportEntry:
    entry = make_entry(**(entry_kwargs or {}))
    return ex.ExportEntry(
        entry,
        lines if lines is not None else [],
        names.get("vendor", "Northfield Pet Supply Co."),
        names.get("category", "SUPPLIES"),
    )


def test_an_entry_row_has_a_cell_for_every_column() -> None:
    row = ex.entry_row(item({"subtotal_minor": 15000, "tax_total_minor": 200}), "USD")
    assert len(row) == len(ex.ENTRY_COLUMNS)
    got = dict(zip(ex.ENTRY_COLUMNS, row, strict=True))
    assert got["vendor"] == "Northfield Pet Supply Co." and got["type"] == "invoice"
    assert (got["subtotal"], got["tax"], got["total"]) == ("150.00", "2.00", "152.00")
    assert (got["shipping"], got["discount"]) == ("", "")  # not printed stays empty, not 0.00
    assert got["currency"] == "USD" and got["category"] == "SUPPLIES"


def test_a_credit_note_is_exported_with_every_amount_negative() -> None:
    entry = {
        "entry_type": EntryType.CREDIT_NOTE, "subtotal_minor": 10000, "tax_total_minor": 800,
        "shipping_minor": 500, "discount_minor": 300, "total_minor": 11000,
    }  # fmt: skip
    got = dict(zip(ex.ENTRY_COLUMNS, ex.entry_row(item(entry), "USD"), strict=True))
    assert (got["subtotal"], got["tax"], got["shipping"], got["discount"], got["total"]) == (
        "-100.00", "-8.00", "-5.00", "-3.00", "-110.00",
    )  # fmt: skip
    assert got["type"] == "credit_note"


def test_line_rows_repeat_the_entry_columns_and_credit_notes_keep_arithmetic_consistent() -> None:
    lines = [
        make_line(
            1,
            description="Kibble",
            quantity="4",
            unit_price="38.00",
            amount_minor=15200,
            tax_rate="0.0825",
        ),
        make_line(2, description="Bags", quantity="2.5", unit_price="4.125", amount_minor=1031),
    ]
    rows = ex.line_rows(item({"entry_type": EntryType.CREDIT_NOTE}, lines), "USD")
    assert len(rows) == 2 and all(len(r) == len(ex.LINE_COLUMNS) for r in rows)
    first = dict(zip(ex.LINE_COLUMNS, rows[0], strict=True))
    assert (first["line_number"], first["quantity"], first["unit_price"], first["line_amount"]) == (
        "1", "4", "-38.00", "-152.00",
    )  # fmt: skip
    assert first["tax_rate"] == "0.0825" and first["entry_total"] == "-152.00"
    assert first["vendor"] == "Northfield Pet Supply Co." and first["invoice_number"] == "INV-20417"
    second = dict(zip(ex.LINE_COLUMNS, rows[1], strict=True))
    assert (second["quantity"], second["unit_price"], second["line_amount"]) == (
        "2.5",
        "-4.125",
        "-10.31",
    )


def test_an_entry_without_lines_still_gets_one_row_so_its_total_is_not_lost() -> None:
    (row,) = ex.line_rows(item(), "USD")
    got = dict(zip(ex.LINE_COLUMNS, row, strict=True))
    assert got["line_number"] == "" and got["description"] == "" and got["entry_total"] == "152.00"


def test_a_missing_currency_falls_back_to_the_business_default() -> None:
    got = dict(zip(ex.ENTRY_COLUMNS, ex.entry_row(item({"currency": None}), "EUR"), strict=True))
    assert got["currency"] == "EUR"


def test_hostile_text_is_neutralised_in_every_text_column_of_both_profiles() -> None:
    entry = {"invoice_number": "=1+1", "po_number": "+PO", "currency": "USD"}
    lines = [make_line(1, description="@SUM(1+1)", quantity="1", unit_price="1", amount_minor=100)]
    hostile = item(entry, lines, vendor="-vendor", category="=CAT")
    entry_cells = dict(zip(ex.ENTRY_COLUMNS, ex.entry_row(hostile, "USD"), strict=True))
    line_cells = dict(zip(ex.LINE_COLUMNS, ex.line_rows(hostile, "USD")[0], strict=True))
    for column in ("vendor", "invoice_number", "po_number", "category"):
        assert entry_cells[column].startswith("'"), column
    for column in ("vendor", "invoice_number", "category", "description"):
        assert line_cells[column].startswith("'"), column


# --- the file ----------------------------------------------------------------------------------


def parse(data: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(data.decode("utf-8"), newline="")))


def test_the_file_is_rfc_4180_utf8_with_a_header_and_crlf_line_ends() -> None:
    data = ex.render(ExportProfile.ENTRIES_CSV, [["1"] * len(ex.ENTRY_COLUMNS)])
    assert not data.startswith(b"\xef\xbb\xbf")  # no byte order mark
    assert (
        data.endswith(b"\r\n")
        and data.count(b"\r\n") == 2
        and b"\n" not in data.replace(b"\r\n", b"")
    )
    assert parse(data)[0] == list(ex.ENTRY_COLUMNS)


def test_commas_quotes_and_line_breaks_inside_a_cell_survive_a_round_trip() -> None:
    nasty = [
        'He said "hi", then left',
        "two\nlines",
        "carriage\rreturn",
        'quote"only',
        ",",
        "naïve — ✓",
        "",
    ]
    rows = [[*nasty, *([""] * (len(ex.ENTRY_COLUMNS) - len(nasty)))]]
    data = ex.render(ExportProfile.ENTRIES_CSV, rows)
    assert b'"He said ""hi"", then left"' in data
    assert parse(data)[1] == rows[0]


def test_both_profiles_have_distinct_headers_and_a_row_width_that_matches() -> None:
    assert ex.COLUMNS[ExportProfile.ENTRIES_CSV] == ex.ENTRY_COLUMNS
    assert ex.COLUMNS[ExportProfile.LINES_CSV] == ex.LINE_COLUMNS
    assert len(set(ex.ENTRY_COLUMNS)) == len(ex.ENTRY_COLUMNS)
    assert len(set(ex.LINE_COLUMNS)) == len(ex.LINE_COLUMNS)


def test_rows_for_counts_one_row_per_entry_or_per_line() -> None:
    lines = [make_line(1), make_line(2), make_line(3)]
    items = [item(lines=lines), item(), item(lines=[make_line(1)])]
    assert len(ex.rows_for(ExportProfile.ENTRIES_CSV, items, "USD")) == 3
    assert len(ex.rows_for(ExportProfile.LINES_CSV, items, "USD")) == 3 + 1 + 1
