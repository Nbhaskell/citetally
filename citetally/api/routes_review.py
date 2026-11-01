"""Editing an entry and recording the reviewer's decision (docs/TRD.md section 7).

A person who edits a value becomes its source: the model's evidence for that value is removed, the
change is recorded in `field_edits`, and all 14 checks run again (which clears every override, so
an override always refers to the values on screen when approving).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter

from citetally import repository as repo
from citetally.api.deps import Conn, RequestId, State
from citetally.api.errors import ApiError
from citetally.api.routes_documents import document_detail
from citetally.api.schemas import (
    ApproveRequest,
    DecisionResponse,
    DocumentDetail,
    DocumentOut,
    EntryPatch,
    LinePatch,
    MarkDuplicateRequest,
    RejectRequest,
    ReopenRequest,
    VendorChoice,
)
from citetally.checks import run_checks
from citetally.config import Settings
from citetally.db import transaction
from citetally.matching import normalize_name
from citetally.models import (
    CategorySource,
    Decision,
    EditField,
    Entry,
    HeaderField,
    LineField,
    VendorMatchMethod,
)
from citetally.models import DocumentStatus as S

router = APIRouter(prefix="/api", tags=["review"])

# Entry column -> (edit field, evidence field or None). Money columns are stored in minor units
# and recorded in `field_edits` the same way.
_HEADER: dict[str, tuple[EditField, HeaderField | None]] = {
    "entry_type": (EditField.ENTRY_TYPE, None),
    "invoice_number": (EditField.INVOICE_NUMBER, HeaderField.INVOICE_NUMBER),
    "entry_date": (EditField.ENTRY_DATE, HeaderField.ENTRY_DATE),
    "due_date": (EditField.DUE_DATE, HeaderField.DUE_DATE),
    "po_number": (EditField.PO_NUMBER, HeaderField.PO_NUMBER),
    "currency": (EditField.CURRENCY, HeaderField.CURRENCY),
    "subtotal_minor": (EditField.SUBTOTAL, HeaderField.SUBTOTAL),
    "tax_total_minor": (EditField.TAX_TOTAL, HeaderField.TAX_TOTAL),
    "shipping_minor": (EditField.SHIPPING, HeaderField.SHIPPING),
    "discount_minor": (EditField.DISCOUNT, HeaderField.DISCOUNT),
    "total_minor": (EditField.TOTAL, HeaderField.TOTAL),
}
_LINE: dict[str, tuple[EditField, LineField]] = {
    "description": (EditField.DESCRIPTION, LineField.DESCRIPTION),
    "quantity": (EditField.QUANTITY, LineField.QUANTITY),
    "unit_price": (EditField.UNIT_PRICE, LineField.UNIT_PRICE),
    "amount_minor": (EditField.AMOUNT, LineField.AMOUNT),
    "tax_rate": (EditField.TAX_RATE, LineField.TAX_RATE),
}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _editable_entry(conn: sqlite3.Connection, entry_id: int) -> Entry:
    entry = repo.get_entry(conn, entry_id)
    document = repo.get_document(conn, entry.document_id)
    if document.status is not S.NEEDS_REVIEW:
        raise ApiError(
            409,
            "not_editable",
            "Only a document waiting for review can be edited. Reopen it first.",
        )
    return entry


def _edit_header(conn: sqlite3.Connection, entry: Entry, patch: EntryPatch) -> bool:
    changed = False
    new_values: dict[str, Any] = {}
    for column, (edit_field, evidence_field) in _HEADER.items():
        if column not in patch.model_fields_set:
            continue
        new = getattr(patch, column)
        if new is None and column == "entry_type":
            raise ApiError(422, "invalid_request", "The type of the entry cannot be cleared.")
        old = getattr(entry, column)
        if _text(old) == _text(new):
            continue
        new_values[column] = new
        repo.record_edit(conn, entry.id, edit_field, _text(old), _text(new))
        if evidence_field is not None:
            repo.delete_evidence_for(conn, entry.id, evidence_field, None)
    if "category" in patch.model_fields_set:
        old_code = repo.get_category(conn, entry.category_id).code if entry.category_id else None
        if patch.category is None:
            new_values.update(category_id=None, category_source=None)
        else:
            category = repo.get_category_by_code(conn, patch.category)
            if not category.is_active:
                raise ApiError(422, "rule_violation", "That category is switched off.")
            new_values.update(category_id=category.id, category_source=CategorySource.MANUAL)
        if old_code != patch.category:
            repo.record_edit(conn, entry.id, EditField.CATEGORY, old_code, patch.category)
        else:
            new_values.pop("category_id", None)
            new_values.pop("category_source", None)
    if "notes" in patch.model_fields_set and patch.notes != entry.notes:
        new_values["notes"] = (
            patch.notes
        )  # notes are the reviewer's own words, not an extracted value
    if new_values:
        repo.update_entry(conn, entry.id, **new_values)
        changed = True
    return changed


def _edit_lines(conn: sqlite3.Connection, entry: Entry, wanted: list[LinePatch]) -> bool:
    existing = {line.id: line for line in repo.list_lines(conn, entry.id)}
    changed = False
    order: list[int] = []
    for item in wanted:
        sent = item.model_fields_set - {"id"}
        if item.id is not None:
            if item.id not in existing:
                raise ApiError(422, "unknown_line", "A line in the request is not on this entry.")
            line = existing[item.id]
            for column in sent:
                edit_field, evidence_field = _LINE[column]
                old, new = getattr(line, column), getattr(item, column)
                if _text(old) == _text(new):
                    continue
                repo.update_line(conn, line.id, **{column: new})
                repo.record_edit(
                    conn, entry.id, edit_field, _text(old), _text(new), line_id=line.id
                )
                repo.delete_evidence_for(conn, entry.id, evidence_field, line.id)
                changed = True
            order.append(line.id)
        else:
            created = repo.add_line(
                conn, entry.id, repo.LineInput(**{column: getattr(item, column) for column in sent})
            )
            for column in sent:
                new = getattr(item, column)
                if new is not None:
                    repo.record_edit(
                        conn, entry.id, _LINE[column][0], None, _text(new), line_id=created.id
                    )
            order.append(created.id)
            changed = True
    for line_id in existing.keys() - set(order):
        removed = existing[line_id]
        # Recorded as the description becoming empty; the line id goes null when the row does.
        repo.record_edit(
            conn, entry.id, EditField.DESCRIPTION, removed.description, None, line_id=line_id
        )
        repo.delete_line(conn, line_id)
        changed = True
    if order != [line_id for line_id in existing if line_id in order]:
        changed = True  # the same lines in a different order is an edit too
    if changed:
        repo.order_lines(conn, entry.id, order)
    return changed


def _recheck(
    conn: sqlite3.Connection, document_id: int, settings: Settings, request_id: str
) -> None:
    run_checks(conn, document_id, settings=settings, request_id=request_id)


@router.patch("/entries/{entry_id}", response_model=DocumentDetail)
def edit_entry(
    entry_id: int, patch: EntryPatch, conn: Conn, state: State, request_id: RequestId
) -> DocumentDetail:
    entry = _editable_entry(conn, entry_id)
    with transaction(conn):
        changed = _edit_header(conn, entry, patch)
        if patch.lines is not None:
            changed = _edit_lines(conn, entry, patch.lines) or changed
        if changed:
            _recheck(conn, entry.document_id, state.settings, request_id)
    return document_detail(conn, repo.get_document(conn, entry.document_id))


@router.post("/entries/{entry_id}/vendor", response_model=DocumentDetail)
def set_vendor(
    entry_id: int, choice: VendorChoice, conn: Conn, state: State, request_id: RequestId
) -> DocumentDetail:
    """Set the vendor: an existing one, or a new one made from `name` or the printed name."""
    entry = _editable_entry(conn, entry_id)
    if (choice.vendor_id is None) == (not choice.create):
        raise ApiError(
            422, "invalid_request", "Give either vendor_id or create, not both or neither."
        )
    with transaction(conn):
        if choice.vendor_id is not None:
            vendor = repo.get_vendor(conn, choice.vendor_id)
            if not vendor.is_active:
                raise ApiError(422, "rule_violation", "That vendor is switched off.")
            method = VendorMatchMethod.MANUAL
        else:
            name = (choice.name or entry.vendor_name_raw or "").strip()
            if not name:
                raise ApiError(422, "invalid_request", "A new vendor needs a name.")
            known = repo.find_vendor_by_normalized(conn, normalize_name(name))
            if known is not None:
                raise ApiError(
                    409,
                    "vendor_exists",
                    "A vendor with that name already exists.",
                    {"vendor_id": known.id},
                )
            vendor = repo.create_vendor(
                conn, name, normalize_name(name), is_synthetic=state.settings.synthetic_data
            )
            method = VendorMatchMethod.CREATED

        previous = (
            repo.get_vendor(conn, entry.vendor_id).name
            if entry.vendor_id
            else entry.vendor_name_raw
        )
        changes: dict[str, Any] = {
            "vendor_id": vendor.id,
            "vendor_match_method": method,
            "vendor_match_score": None,
        }
        if vendor.default_category_id and entry.category_source is not CategorySource.MANUAL:
            changes.update(
                category_id=vendor.default_category_id,
                category_source=CategorySource.VENDOR_DEFAULT,
            )
        repo.update_entry(conn, entry.id, **changes)
        repo.record_edit(conn, entry.id, EditField.VENDOR_NAME, previous, vendor.name)
        printed = normalize_name(entry.vendor_name_raw or "")
        if (
            printed
            and printed != vendor.normalized_name
            and repo.find_vendor_by_normalized(conn, printed) is None
        ):
            repo.add_alias(
                conn, vendor.id, entry.vendor_name_raw or "", printed
            )  # next time it matches
        _recheck(conn, entry.document_id, state.settings, request_id)
    return document_detail(conn, repo.get_document(conn, entry.document_id))


# ---- decisions ---------------------------------------------------------------------------------


def _decision(conn: sqlite3.Connection, document_id: int, review: Any) -> DecisionResponse:
    return DecisionResponse(
        document=DocumentOut.model_validate(repo.get_document(conn, document_id)), review=review
    )


@router.post("/documents/{document_id}/approve", response_model=DecisionResponse)
def approve(
    document_id: int, body: ApproveRequest, conn: Conn, request_id: RequestId
) -> DecisionResponse:
    """Approve, giving a written reason for each blocking check that failed and is being accepted.
    All or nothing: if approval is refused, the overrides sent with it are not kept."""
    with transaction(conn):
        for override in body.overrides:
            repo.override_check(conn, document_id, override.check_code, reason=override.reason)
        review = repo.record_review(
            conn,
            document_id,
            Decision.APPROVE,
            review_seconds=body.review_seconds,
            request_id=request_id,
        )
    return _decision(conn, document_id, review)


@router.post("/documents/{document_id}/reject", response_model=DecisionResponse)
def reject(
    document_id: int, body: RejectRequest, conn: Conn, request_id: RequestId
) -> DecisionResponse:
    review = repo.record_review(
        conn,
        document_id,
        Decision.REJECT,
        reason=body.reason,
        review_seconds=body.review_seconds,
        request_id=request_id,
    )
    return _decision(conn, document_id, review)


@router.post("/documents/{document_id}/reopen", response_model=DecisionResponse)
def reopen(
    document_id: int, conn: Conn, request_id: RequestId, body: ReopenRequest | None = None
) -> DecisionResponse:
    review = repo.record_review(conn, document_id, Decision.REOPEN, request_id=request_id)
    return _decision(conn, document_id, review)


@router.post("/documents/{document_id}/mark-duplicate", response_model=DecisionResponse)
def mark_duplicate(
    document_id: int, body: MarkDuplicateRequest, conn: Conn, request_id: RequestId
) -> DecisionResponse:
    review = repo.record_review(
        conn,
        document_id,
        Decision.MARK_DUPLICATE,
        duplicate_of=body.duplicate_of,
        review_seconds=body.review_seconds,
        request_id=request_id,
    )
    return _decision(conn, document_id, review)
