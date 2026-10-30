"""Repository functions: every write goes through rules, and status changes leave an audit trail."""

import json
import logging
import sqlite3
from decimal import Decimal

import pytest

from citetally import db
from citetally import repository as repo
from citetally.models import (
    BLOCKING_CHECKS,
    CategorySource,
    CheckCode,
    Decision,
    EditField,
    EntryType,
    HeaderField,
    Provider,
    ReadMethod,
    Stage,
)
from citetally.models import (
    DocumentStatus as S,
)
from citetally.statemachine import IllegalTransition


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = db.connect(":memory:")
    db.migrate(connection)
    db.seed_categories(connection)
    return connection


def new_doc(conn: sqlite3.Connection, sha: str = "h1", name: str = "invoice.pdf") -> int:
    return repo.create_document(
        conn,
        original_filename=name,
        stored_path=f"files/{sha}",
        file_sha256=sha,
        mime_type="application/pdf",
        size_bytes=1000,
    ).id


def add_extraction(conn: sqlite3.Connection, document_id: int) -> int:
    return repo.add_extraction(
        conn,
        document_id,
        provider=Provider.OLLAMA,
        model="qwen3:8b",
        extract_mode="text_only",
        prompt_version="extract-v1",
        fields={"entry_type": "invoice"},
        raw_response="{}",
    ).id


def to_extracted(conn: sqlite3.Connection, document_id: int, **entry: object) -> int:
    """Walk a document to `extracted` with an entry. Returns the entry id."""
    repo.change_status(conn, document_id, S.READ)
    extraction_id = add_extraction(conn, document_id)
    created = repo.create_entry(conn, document_id, extraction_id, EntryType.INVOICE, **entry)
    repo.change_status(conn, document_id, S.EXTRACTED)
    return created.id


def pass_all_checks(conn: sqlite3.Connection, document_id: int) -> None:
    for code in CheckCode:
        repo.upsert_check(conn, document_id, code, passed=True, detail={})


def to_review(conn: sqlite3.Connection, document_id: int, **entry: object) -> int:
    entry_id = to_extracted(conn, document_id, **entry)
    pass_all_checks(conn, document_id)
    repo.change_status(conn, document_id, S.NEEDS_REVIEW)
    return entry_id


def audit(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM audit_events ORDER BY id").fetchall()


# ---- documents and status changes -------------------------------------------------------------


def test_a_new_document_is_received_and_synthetic_by_default(conn: sqlite3.Connection) -> None:
    doc = repo.get_document(conn, new_doc(conn))
    assert doc.status is S.RECEIVED and doc.is_synthetic is True
    assert doc.created_at == doc.updated_at and doc.failure_stage is None


def test_documents_are_found_by_file_hash(conn: sqlite3.Connection) -> None:
    first = new_doc(conn, "same")
    second = new_doc(conn, "same", "copy.pdf")
    assert [d.id for d in repo.find_documents_by_sha(conn, "same")] == [first, second]
    assert repo.find_documents_by_sha(conn, "other") == []


def test_unknown_documents_raise_not_found(conn: sqlite3.Connection) -> None:
    with pytest.raises(repo.NotFound):
        repo.get_document(conn, 404)
    with pytest.raises(repo.NotFound):
        repo.change_status(conn, 404, S.READ)


def test_a_legal_change_updates_the_status_and_records_why(conn: sqlite3.Connection) -> None:
    doc_id = new_doc(conn)
    updated = repo.change_status(conn, doc_id, S.READ, request_id="req-7")
    assert updated.status is S.READ and updated.updated_at >= updated.created_at
    (event,) = audit(conn)
    assert (event["event_type"], event["from_status"], event["to_status"]) == (
        "status_changed",
        "received",
        "read",
    )
    assert json.loads(event["payload"]) == {"trigger": "read_finished"}
    assert event["document_id"] == doc_id and event["request_id"] == "req-7"


def test_an_illegal_change_is_refused_and_leaves_nothing_behind(conn: sqlite3.Connection) -> None:
    doc_id = new_doc(conn)
    with pytest.raises(IllegalTransition):
        repo.change_status(conn, doc_id, S.APPROVED)
    assert repo.get_document(conn, doc_id).status is S.RECEIVED
    assert audit(conn) == []


def test_failing_records_the_stage_and_a_reason_and_leaving_failed_clears_them(
    conn: sqlite3.Connection,
) -> None:
    doc_id = new_doc(conn)
    failed = repo.change_status(
        conn, doc_id, S.FAILED, failure_stage=Stage.INGEST, failure_message="File is too large."
    )
    assert (failed.failure_stage, failed.failure_message) == (Stage.INGEST, "File is too large.")
    event = audit(conn)[-1]
    assert event["stage"] == "ingest" and json.loads(event["payload"]) == {
        "trigger": "ingest_failed"
    }
    retried = repo.change_status(conn, doc_id, S.RECEIVED)
    assert retried.status is S.RECEIVED
    assert retried.failure_stage is None and retried.failure_message is None


def test_failing_needs_a_plain_reason(conn: sqlite3.Connection) -> None:
    doc_id = new_doc(conn)
    with pytest.raises(repo.RepositoryError, match="reason"):
        repo.change_status(conn, doc_id, S.FAILED, failure_stage=Stage.INGEST)
    with pytest.raises(repo.RepositoryError, match="reason"):
        repo.change_status(conn, doc_id, S.FAILED, failure_stage=Stage.INGEST, failure_message=" ")
    assert repo.get_document(conn, doc_id).status is S.RECEIVED


def test_marking_a_duplicate_points_at_another_existing_document(conn: sqlite3.Connection) -> None:
    original, copy = new_doc(conn, "a"), new_doc(conn, "a", "copy.pdf")
    done = repo.change_status(conn, copy, S.DUPLICATE, duplicate_of=original)
    assert done.status is S.DUPLICATE and done.duplicate_of == original
    third = new_doc(conn, "b")
    with pytest.raises(repo.RepositoryError, match="itself"):
        repo.change_status(conn, third, S.DUPLICATE, duplicate_of=third)
    with pytest.raises(repo.NotFound):
        repo.change_status(conn, third, S.DUPLICATE, duplicate_of=999)
    assert repo.get_document(conn, third).status is S.RECEIVED


def test_a_document_is_extracted_only_when_it_has_an_entry(conn: sqlite3.Connection) -> None:
    doc_id = new_doc(conn)
    repo.change_status(conn, doc_id, S.READ)
    with pytest.raises(repo.RepositoryError, match="entry"):
        repo.change_status(conn, doc_id, S.EXTRACTED)
    assert repo.get_document(conn, doc_id).status is S.READ


# ---- approval ---------------------------------------------------------------------------------


def test_approval_needs_every_blocking_check_recorded_and_passed(conn: sqlite3.Connection) -> None:
    doc_id = new_doc(conn)
    to_extracted(conn, doc_id)
    repo.change_status(conn, doc_id, S.NEEDS_REVIEW)
    with pytest.raises(repo.ApprovalBlocked) as blocked:
        repo.change_status(conn, doc_id, S.APPROVED)  # no checks recorded yet
    assert set(blocked.value.codes) == BLOCKING_CHECKS
    pass_all_checks(conn, doc_id)
    repo.upsert_check(
        conn, doc_id, CheckCode.TOTAL_MATCH, passed=False, detail={"expected_minor": 1}
    )
    with pytest.raises(repo.ApprovalBlocked) as blocked:
        repo.change_status(conn, doc_id, S.APPROVED)
    assert blocked.value.codes == [CheckCode.TOTAL_MATCH]
    assert repo.get_document(conn, doc_id).status is S.NEEDS_REVIEW


def test_a_blocking_failure_can_be_overridden_with_a_written_reason(
    conn: sqlite3.Connection,
) -> None:
    doc_id = new_doc(conn)
    to_review(conn, doc_id)
    repo.upsert_check(conn, doc_id, CheckCode.TOTAL_MATCH, passed=False, detail={})
    with pytest.raises(repo.RepositoryError, match="reason"):
        repo.override_check(conn, doc_id, CheckCode.TOTAL_MATCH, reason="  ")
    check = repo.override_check(
        conn, doc_id, CheckCode.TOTAL_MATCH, reason="Vendor confirmed by phone."
    )
    assert check.overridden is True and check.override_reason == "Vendor confirmed by phone."
    assert check.overridden_at is not None
    assert repo.change_status(conn, doc_id, S.APPROVED).status is S.APPROVED


def test_non_blocking_failures_never_stop_approval(conn: sqlite3.Connection) -> None:
    doc_id = new_doc(conn)
    to_review(conn, doc_id)
    repo.upsert_check(conn, doc_id, CheckCode.AMOUNT_OUTLIER, passed=False, detail={})
    repo.upsert_check(conn, doc_id, CheckCode.DATE_SANITY, passed=False, detail={})
    assert repo.unresolved_blocking(conn, doc_id) == []
    assert repo.change_status(conn, doc_id, S.APPROVED).status is S.APPROVED


def test_only_failed_blocking_checks_can_be_overridden(conn: sqlite3.Connection) -> None:
    doc_id = new_doc(conn)
    to_review(conn, doc_id)
    with pytest.raises(repo.RepositoryError, match="nothing to override"):
        repo.override_check(conn, doc_id, CheckCode.TOTAL_MATCH, reason="because")  # it passed
    repo.upsert_check(conn, doc_id, CheckCode.AMOUNT_OUTLIER, passed=False, detail={})
    with pytest.raises(repo.RepositoryError, match="blocking"):
        repo.override_check(conn, doc_id, CheckCode.AMOUNT_OUTLIER, reason="because")
    with pytest.raises(repo.NotFound):
        repo.override_check(conn, 404, CheckCode.LINE_MATH, reason="x")


def test_rerunning_a_check_clears_its_override(conn: sqlite3.Connection) -> None:
    """An override always refers to the values the reviewer actually saw."""
    doc_id = new_doc(conn)
    to_review(conn, doc_id)
    repo.upsert_check(conn, doc_id, CheckCode.TOTAL_MATCH, passed=False, detail={})
    repo.override_check(conn, doc_id, CheckCode.TOTAL_MATCH, reason="ok")
    again = repo.upsert_check(conn, doc_id, CheckCode.TOTAL_MATCH, passed=False, detail={"n": 2})
    assert (
        again.overridden is False and again.override_reason is None and again.overridden_at is None
    )
    assert repo.unresolved_blocking(conn, doc_id) == [CheckCode.TOTAL_MATCH]


def test_checks_know_whether_they_are_blocking_and_one_row_exists_per_code(
    conn: sqlite3.Connection,
) -> None:
    doc_id = new_doc(conn)
    to_review(conn, doc_id)
    checks = {c.check_code: c for c in repo.list_checks(conn, doc_id)}
    assert len(checks) == 14
    assert checks[CheckCode.TOTAL_MATCH].blocking is True
    assert checks[CheckCode.AMOUNT_OUTLIER].blocking is False
    repo.upsert_check(conn, doc_id, CheckCode.TOTAL_MATCH, passed=True, detail={})
    assert len(repo.list_checks(conn, doc_id)) == 14


def test_a_failed_check_leaves_an_audit_event_with_only_codes(conn: sqlite3.Connection) -> None:
    doc_id = new_doc(conn)
    to_extracted(conn, doc_id)
    before = len(audit(conn))
    repo.upsert_check(conn, doc_id, CheckCode.LINE_MATH, passed=False, detail={"lines": [1]})
    repo.upsert_check(conn, doc_id, CheckCode.TOTAL_MATCH, passed=True, detail={})
    (event,) = audit(conn)[before:]
    assert event["event_type"] == "check_failed" and event["stage"] == "check"
    assert json.loads(event["payload"]) == {"check": "LINE_MATH", "passed": False}


# ---- review decisions -------------------------------------------------------------------------


def test_approving_records_a_review_with_override_and_edit_counts(conn: sqlite3.Connection) -> None:
    doc_id = new_doc(conn)
    entry_id = to_review(conn, doc_id)
    repo.upsert_check(conn, doc_id, CheckCode.TOTAL_MATCH, passed=False, detail={})
    repo.override_check(conn, doc_id, CheckCode.TOTAL_MATCH, reason="Confirmed with the vendor.")
    repo.record_edit(conn, entry_id, EditField.TOTAL, "$10.00", "$11.00")
    review = repo.record_review(conn, doc_id, Decision.APPROVE, review_seconds=42)
    assert review.decision is Decision.APPROVE
    assert (review.overrides, review.edited, review.review_seconds) == (1, True, 42)
    assert repo.get_document(conn, doc_id).status is S.APPROVED
    last = audit(conn)[-1]
    assert last["event_type"] == "review_recorded"
    assert json.loads(last["payload"]) == {
        "decision": "approve",
        "overrides": 1,
        "edited": True,
        "review_seconds": 42,
    }


def test_a_second_approval_after_a_reopen_counts_only_new_edits(conn: sqlite3.Connection) -> None:
    doc_id = new_doc(conn)
    entry_id = to_review(conn, doc_id)
    repo.record_edit(conn, entry_id, EditField.TOTAL, "1", "2")
    assert repo.record_review(conn, doc_id, Decision.APPROVE).edited is True
    assert repo.record_review(conn, doc_id, Decision.REOPEN).edited is False
    assert repo.record_review(conn, doc_id, Decision.APPROVE).edited is False


def test_rejecting_needs_a_reason_and_can_be_reopened(conn: sqlite3.Connection) -> None:
    doc_id = new_doc(conn)
    to_review(conn, doc_id)
    with pytest.raises(repo.RepositoryError, match="reason"):
        repo.record_review(conn, doc_id, Decision.REJECT)
    assert repo.get_document(conn, doc_id).status is S.NEEDS_REVIEW
    repo.record_review(conn, doc_id, Decision.REJECT, reason="Not our invoice.")
    assert repo.get_document(conn, doc_id).status is S.REJECTED
    repo.record_review(conn, doc_id, Decision.REOPEN)
    assert repo.get_document(conn, doc_id).status is S.NEEDS_REVIEW


def test_marking_a_duplicate_through_a_review(conn: sqlite3.Connection) -> None:
    original, copy = new_doc(conn, "a"), new_doc(conn, "b")
    to_review(conn, original)
    to_review(conn, copy)
    repo.record_review(conn, copy, Decision.MARK_DUPLICATE, duplicate_of=original)
    doc = repo.get_document(conn, copy)
    assert doc.status is S.DUPLICATE and doc.duplicate_of == original
    with pytest.raises(repo.RepositoryError, match="duplicate_of"):
        repo.record_review(conn, original, Decision.MARK_DUPLICATE)


def test_a_refused_decision_leaves_no_review_and_no_event(conn: sqlite3.Connection) -> None:
    doc_id = new_doc(conn)
    to_extracted(conn, doc_id)
    repo.change_status(conn, doc_id, S.NEEDS_REVIEW)
    events_before = len(audit(conn))
    with pytest.raises(repo.ApprovalBlocked):
        repo.record_review(conn, doc_id, Decision.APPROVE)
    assert conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 0
    assert len(audit(conn)) == events_before


# ---- reprocessing -----------------------------------------------------------------------------


def seed_page(conn: sqlite3.Connection, document_id: int) -> None:
    repo.add_page(
        conn,
        document_id,
        page_number=1,
        image_path="pages/1.png",
        width_px=100,
        height_px=200,
        read_method=ReadMethod.OCR,
        ocr_engine="tesseract",
        mean_confidence=88.0,
        words=[],
        text="page text",
    )


def test_reprocessing_from_the_read_stage_clears_the_entry_and_checks_but_keeps_pages(
    conn: sqlite3.Connection,
) -> None:
    doc_id = new_doc(conn)
    seed_page(conn, doc_id)
    entry_id = to_review(conn, doc_id, invoice_number="INV-1", total_minor=100)
    repo.replace_lines(conn, entry_id, [repo.LineInput(description="Pipe", amount_minor=100)])
    repo.change_status(conn, doc_id, S.READ)
    assert repo.get_entry_for_document(conn, doc_id) is None
    assert repo.list_checks(conn, doc_id) == []
    assert len(repo.list_pages(conn, doc_id)) == 1
    assert conn.execute("SELECT COUNT(*) FROM entry_lines").fetchone()[0] == 0
    assert repo.latest_extraction(conn, doc_id) is not None  # attempts stay as history


def test_reprocessing_from_the_start_also_clears_the_pages(conn: sqlite3.Connection) -> None:
    doc_id = new_doc(conn)
    seed_page(conn, doc_id)
    to_review(conn, doc_id)
    repo.change_status(conn, doc_id, S.RECEIVED)
    assert repo.list_pages(conn, doc_id) == []
    assert repo.get_document(conn, doc_id).status is S.RECEIVED


def test_a_reprocessed_document_can_be_extracted_again_with_a_new_attempt(
    conn: sqlite3.Connection,
) -> None:
    doc_id = new_doc(conn)
    to_review(conn, doc_id)
    repo.change_status(conn, doc_id, S.READ)
    second = add_extraction(conn, doc_id)
    assert repo.latest_extraction(conn, doc_id).id == second  # type: ignore[union-attr]
    assert repo.latest_extraction(conn, doc_id).attempt == 2  # type: ignore[union-attr]
    repo.create_entry(conn, doc_id, second, EntryType.INVOICE)
    repo.change_status(conn, doc_id, S.EXTRACTED)


# ---- entries, lines, evidence, edits ----------------------------------------------------------


def test_entries_store_exact_values(conn: sqlite3.Connection) -> None:
    doc_id = new_doc(conn)
    entry_id = to_extracted(
        conn,
        doc_id,
        invoice_number="INV-20112",
        entry_date="2026-05-20",
        currency="USD",
        subtotal_minor=60740,
        total_minor=64992,
        vendor_name_raw="Millrace Plumbing Supply Co.",
    )
    entry = repo.get_entry(conn, entry_id)
    assert (entry.total_minor, entry.entry_date, entry.entry_type) == (
        64992,
        "2026-05-20",
        EntryType.INVOICE,
    )
    assert repo.get_entry_for_document(conn, doc_id).id == entry_id  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "bad",
    [
        {"total_minor": 649.92},  # a float is never an amount
        {"total_minor": True},
        {"subtotal_minor": "64992"},
        {"currency": "$"},
        {"currency": "usd"},
        {"entry_date": "05/20/2026"},
        {"entry_date": "2026-13-45"},
        {"vendor_match_score": "high"},
    ],
)
def test_entries_refuse_floats_symbols_and_unparsed_dates(
    conn: sqlite3.Connection, bad: dict[str, object]
) -> None:
    doc_id = new_doc(conn)
    repo.change_status(conn, doc_id, S.READ)
    extraction_id = add_extraction(conn, doc_id)
    with pytest.raises(repo.RepositoryError):
        repo.create_entry(conn, doc_id, extraction_id, EntryType.INVOICE, **bad)
    assert repo.get_entry_for_document(conn, doc_id) is None


def test_update_entry_changes_listed_columns_only_and_touches_updated_at(
    conn: sqlite3.Connection,
) -> None:
    doc_id = new_doc(conn)
    entry_id = to_extracted(conn, doc_id, total_minor=100)
    before = repo.get_entry(conn, entry_id)
    after = repo.update_entry(
        conn, entry_id, total_minor=250, category_source=CategorySource.MANUAL
    )
    assert after.total_minor == 250 and after.category_source is CategorySource.MANUAL
    assert after.updated_at > before.updated_at
    for forbidden in ("document_id", "id", "created_at", "nonsense"):
        with pytest.raises(repo.RepositoryError, match="cannot be changed"):
            repo.update_entry(conn, entry_id, **{forbidden: 1})


def test_lines_keep_exact_decimals_and_are_numbered_from_one(conn: sqlite3.Connection) -> None:
    doc_id = new_doc(conn)
    entry_id = to_extracted(conn, doc_id)
    repo.replace_lines(
        conn,
        entry_id,
        [
            repo.LineInput(
                description="Fuel", quantity="11.699", unit_price="4.159", amount_minor=4866
            ),
            repo.LineInput(
                description="Tape",
                quantity="10",
                unit_price="1.35",
                amount_minor=1350,
                tax_rate="0.07",
            ),
        ],
    )
    lines = repo.list_lines(conn, entry_id)
    assert [(line.line_number, line.quantity, line.unit_price) for line in lines] == [
        (1, "11.699", "4.159"),
        (2, "10", "1.35"),
    ]
    assert Decimal(lines[0].quantity or "") * Decimal(lines[0].unit_price or "") == Decimal(
        "48.656141"
    )
    repo.replace_lines(conn, entry_id, [repo.LineInput(description="Only")])
    assert [line.description for line in repo.list_lines(conn, entry_id)] == ["Only"]


@pytest.mark.parametrize(
    "bad",
    [
        {"quantity": "two"},
        {"unit_price": "NaN"},
        {"unit_price": "Infinity"},
        {"tax_rate": "7%"},
        {"amount_minor": 12.5},
    ],
)
def test_lines_refuse_values_that_are_not_exact_decimals_or_integers(
    conn: sqlite3.Connection, bad: dict[str, object]
) -> None:
    doc_id = new_doc(conn)
    entry_id = to_extracted(conn, doc_id)
    with pytest.raises(repo.RepositoryError):
        repo.replace_lines(conn, entry_id, [repo.LineInput(**bad)])  # type: ignore[arg-type]


def test_evidence_records_where_a_value_was_found(conn: sqlite3.Connection) -> None:
    doc_id = new_doc(conn)
    entry_id = to_extracted(conn, doc_id)
    found = repo.add_evidence(
        conn, entry_id, HeaderField.TOTAL, "$649.92", True, page_number=1,
        box=(0.6, 0.8, 0.9, 0.84), match_score=1.0,
    )  # fmt: skip
    missing = repo.add_evidence(conn, entry_id, HeaderField.INVOICE_NUMBER, "INV-9", False)
    assert found.found is True and found.x1 == 0.9
    assert missing.found is False and missing.x0 is None
    assert [e.field for e in repo.list_evidence(conn, entry_id)] == [
        HeaderField.TOTAL,
        HeaderField.INVOICE_NUMBER,
    ]
    with pytest.raises(repo.RepositoryError, match="box"):
        repo.add_evidence(conn, entry_id, HeaderField.TOTAL, "x", True, box=(0.9, 0.1, 0.2, 0.3))
    with pytest.raises(repo.RepositoryError, match="box"):
        repo.add_evidence(conn, entry_id, HeaderField.TOTAL, "x", True, box=(0.1, 0.1, 1.5, 0.3))


def test_edit_counts_show_which_fields_reviewers_change_most(conn: sqlite3.Connection) -> None:
    entry_id = to_extracted(conn, new_doc(conn))
    for _ in range(3):
        repo.record_edit(conn, entry_id, EditField.TOTAL, "a", "b")
    repo.record_edit(conn, entry_id, EditField.CATEGORY, None, "SUPPLIES")
    assert repo.field_correction_counts(conn) == [("total", 3), ("category", 1)]


# ---- vendors, settings, queries ---------------------------------------------------------------


def test_vendors_and_aliases_are_unique_by_normalized_name(conn: sqlite3.Connection) -> None:
    supplies = repo.get_category_by_code(conn, "SUPPLIES")
    vendor = repo.create_vendor(
        conn, "Millrace Plumbing Supply Co.", "millrace plumbing supply",
        default_category_id=supplies.id, default_currency="USD",
    )  # fmt: skip
    repo.add_alias(conn, vendor.id, "MILLRACE PLUMBING SUPPLY CO", "millrace plumbing supply co")
    assert repo.find_vendor_by_normalized(conn, "millrace plumbing supply").id == vendor.id  # type: ignore[union-attr]
    assert repo.find_vendor_by_normalized(conn, "millrace plumbing supply co").id == vendor.id  # type: ignore[union-attr]
    assert repo.find_vendor_by_normalized(conn, "nobody") is None
    with pytest.raises(sqlite3.IntegrityError):
        repo.create_vendor(conn, "Another", "millrace plumbing supply")
    assert vendor.is_synthetic is True and vendor.default_currency == "USD"


def test_settings_are_stored_by_key(conn: sqlite3.Connection) -> None:
    assert repo.get_setting(conn, "default_currency") is None
    repo.set_setting(conn, "default_currency", "USD")
    repo.set_setting(conn, "default_currency", "CAD")
    assert repo.get_setting(conn, "default_currency") == "CAD"
    assert conn.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 1


def test_the_review_queue_lists_failed_first_then_oldest_needs_review(
    conn: sqlite3.Connection,
) -> None:
    first, second, third, fourth = (new_doc(conn, f"h{n}") for n in range(4))
    to_review(conn, first)
    to_review(conn, second)
    repo.change_status(
        conn, third, S.FAILED, failure_stage=Stage.INGEST, failure_message="Bad file."
    )
    to_extracted(conn, fourth)  # still processing: not in the queue
    assert [d.id for d in repo.list_review_queue(conn)] == [third, first, second]


def vendor_entry(conn: sqlite3.Connection, vendor_id: int, sha: str, **fields: object) -> int:
    doc_id = new_doc(conn, sha)
    to_review(conn, doc_id, vendor_id=vendor_id, **fields)
    return doc_id


def test_duplicate_lookup_by_invoice_number_ignores_self_and_dead_documents(
    conn: sqlite3.Connection,
) -> None:
    vendor = repo.create_vendor(conn, "V", "v").id
    a = vendor_entry(conn, vendor, "a", invoice_number="INV-1")
    b = vendor_entry(conn, vendor, "b", invoice_number="INV-1")
    c = vendor_entry(conn, vendor, "c", invoice_number="INV-1")
    repo.record_review(conn, c, Decision.REJECT, reason="Wrong file.")
    other = repo.create_vendor(conn, "W", "w").id
    vendor_entry(conn, other, "d", invoice_number="INV-1")
    assert repo.find_duplicates_by_number(conn, vendor, "INV-1", exclude_document_id=a) == [b]
    assert sorted(
        repo.find_duplicates_by_number(conn, vendor, "INV-1", exclude_document_id=999)
    ) == [a, b]


def test_duplicate_lookup_by_content_uses_vendor_total_currency_and_a_date_window(
    conn: sqlite3.Connection,
) -> None:
    vendor = repo.create_vendor(conn, "V", "v").id
    base = {"total_minor": 64992, "currency": "USD"}
    a = vendor_entry(conn, vendor, "a", entry_date="2026-05-20", **base)
    near = vendor_entry(conn, vendor, "b", entry_date="2026-05-24", **base)
    far = vendor_entry(conn, vendor, "c", entry_date="2026-06-20", **base)
    vendor_entry(conn, vendor, "d", entry_date="2026-05-21", total_minor=1, currency="USD")
    vendor_entry(conn, vendor, "e", entry_date="2026-05-21", total_minor=64992, currency="CAD")
    found = repo.find_duplicates_by_content(
        conn, vendor, 64992, "USD", "2026-05-22", 7, exclude_document_id=a
    )
    assert found == [near]
    wide = repo.find_duplicates_by_content(
        conn, vendor, 64992, "USD", "2026-05-22", 60, exclude_document_id=a
    )
    assert sorted(wide) == sorted([near, far])


def test_vendor_history_counts_only_approved_and_exported_entries(conn: sqlite3.Connection) -> None:
    vendor = repo.create_vendor(conn, "V", "v").id
    approved = vendor_entry(conn, vendor, "a", total_minor=100, currency="USD")
    vendor_entry(conn, vendor, "b", total_minor=900, currency="USD")  # still needs review
    vendor_entry(conn, vendor, "c", total_minor=200, currency="CAD")
    repo.record_review(conn, approved, Decision.APPROVE)
    assert repo.vendor_history_totals(conn, vendor, "USD") == [100]


# ---- the whole path, and the logs -------------------------------------------------------------


def test_the_whole_path_from_upload_to_approval_leaves_a_clean_audit_trail(
    conn: sqlite3.Connection,
) -> None:
    doc_id = new_doc(conn)
    to_review(conn, doc_id, invoice_number="INV-20112", total_minor=64992)
    repo.record_review(conn, doc_id, Decision.APPROVE)
    trail = [(e["event_type"], e["from_status"], e["to_status"]) for e in audit(conn)]
    assert trail == [
        ("status_changed", "received", "read"),
        ("status_changed", "read", "extracted"),
        ("status_changed", "extracted", "needs_review"),
        ("status_changed", "needs_review", "approved"),
        ("review_recorded", None, None),
    ]


def test_no_document_content_reaches_the_audit_table_or_the_logs(
    conn: sqlite3.Connection, caplog: pytest.LogCaptureFixture
) -> None:
    secrets = ["Millrace Plumbing Supply Co.", "INV-20112", "$649.92", "649.92", "Kestrel Hollow"]
    with caplog.at_level(logging.DEBUG):
        doc_id = new_doc(conn, name="Millrace Plumbing Supply Co. INV-20112.pdf")
        repo.change_status(conn, doc_id, S.READ)
        seed_page(conn, doc_id)
        extraction_id = repo.add_extraction(
            conn, doc_id, provider=Provider.OLLAMA, model="qwen3:8b", extract_mode="text_only",
            prompt_version="extract-v1", fields={"vendor_name": secrets[0], "total": secrets[2]},
            raw_response="Total $649.92 INV-20112",
        ).id  # fmt: skip
        repo.create_entry(
            conn, doc_id, extraction_id, EntryType.INVOICE, vendor_name_raw=secrets[0],
            invoice_number=secrets[1], total_minor=64992, notes="Kestrel Hollow Plumbing",
        )  # fmt: skip
        repo.change_status(conn, doc_id, S.EXTRACTED)
        repo.upsert_check(
            conn, doc_id, CheckCode.TOTAL_MATCH, passed=False, detail={"printed_text": secrets[2]}
        )
        repo.change_status(conn, doc_id, S.NEEDS_REVIEW)
        repo.record_review(
            conn, doc_id, Decision.REJECT, reason="Millrace Plumbing Supply Co. sent it twice"
        )
    logged = "\n".join(r.getMessage() for r in caplog.records)
    stored = "\n".join(" ".join(str(v) for v in row) for row in audit(conn))
    for secret in secrets:
        assert secret not in logged, secret
        assert secret not in stored, secret
    assert "status_changed" in logged  # the lines exist; they just carry no content
