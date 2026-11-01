"""Documents: upload, list, detail, page pictures, reprocess (docs/TRD.md section 7)."""

from __future__ import annotations

import json
import sqlite3
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import FileResponse

from citetally import ingest
from citetally import repository as repo
from citetally.api.deps import Conn, RequestId, State
from citetally.api.errors import ApiError
from citetally.api.schemas import (
    CheckOut,
    DocumentDetail,
    DocumentList,
    DocumentOut,
    DocumentSummary,
    EntryOut,
    EventOut,
    ExtractionOut,
    PageOut,
    ReprocessRequest,
    UploadResponse,
    UploadResult,
)
from citetally.models import CheckCode, Document, Entry
from citetally.models import DocumentStatus as S

router = APIRouter(prefix="/api", tags=["documents"])

MAX_FILES_PER_UPLOAD = 50
MAX_PAGE_SIZE = 200


# ---- builders shared with the review routes ----------------------------------------------------


def entry_out(conn: sqlite3.Connection, entry: Entry) -> EntryOut:
    vendor = repo.get_vendor(conn, entry.vendor_id) if entry.vendor_id is not None else None
    category = repo.get_category(conn, entry.category_id) if entry.category_id else None
    return EntryOut(
        id=entry.id,
        entry_type=entry.entry_type,
        vendor_id=entry.vendor_id,
        vendor_name_raw=entry.vendor_name_raw,
        vendor_name=vendor.name if vendor else None,
        vendor_match_method=entry.vendor_match_method,
        vendor_match_score=entry.vendor_match_score,
        invoice_number=entry.invoice_number,
        entry_date=entry.entry_date,
        due_date=entry.due_date,
        po_number=entry.po_number,
        currency=entry.currency,
        subtotal_minor=entry.subtotal_minor,
        tax_total_minor=entry.tax_total_minor,
        shipping_minor=entry.shipping_minor,
        discount_minor=entry.discount_minor,
        total_minor=entry.total_minor,
        category=category.code if category else None,
        category_source=entry.category_source.value if entry.category_source else None,
        notes=entry.notes,
        lines=repo.list_lines(conn, entry.id),
    )


def document_detail(conn: sqlite3.Connection, document: Document) -> DocumentDetail:
    entry = repo.get_entry_for_document(conn, document.id)
    extraction = repo.latest_extraction(conn, document.id)
    return DocumentDetail(
        document=DocumentOut.model_validate(document),
        pages=[
            PageOut(
                **page.model_dump(exclude={"words", "image_path"}),
                image_url=f"/api/documents/{document.id}/pages/{page.page_number}/image",
            )
            for page in repo.list_pages(conn, document.id)
        ],
        extraction=ExtractionOut.model_validate(extraction) if extraction else None,
        entry=entry_out(conn, entry) if entry else None,
        evidence=repo.list_evidence(conn, entry.id) if entry else [],
        checks=[
            CheckOut(
                check_code=check.check_code,
                blocking=check.blocking,
                passed=check.passed,
                detail=json.loads(check.detail),
                overridden=check.overridden,
                override_reason=check.override_reason,
                overridden_at=check.overridden_at,
            )
            for check in repo.list_checks(conn, document.id)
        ],
        edits=repo.list_edits(conn, entry.id) if entry else [],
        reviews=repo.list_reviews(conn, document.id),
        history=[
            EventOut(
                event_type=event.event_type,
                stage=event.stage,
                from_status=event.from_status,
                to_status=event.to_status,
                payload=json.loads(event.payload),
                duration_ms=event.duration_ms,
                created_at=event.created_at,
            )
            for event in repo.list_audit_events(conn, document.id)
        ],
    )


def document_summary(conn: sqlite3.Connection, document: Document) -> DocumentSummary:
    entry = repo.get_entry_for_document(conn, document.id)
    vendor = repo.get_vendor(conn, entry.vendor_id) if entry and entry.vendor_id else None
    return DocumentSummary(
        **DocumentOut.model_validate(document).model_dump(),
        entry_id=entry.id if entry else None,
        entry_type=entry.entry_type if entry else None,
        vendor_name=(vendor.name if vendor else entry.vendor_name_raw) if entry else None,
        invoice_number=entry.invoice_number if entry else None,
        entry_date=entry.entry_date if entry else None,
        currency=entry.currency if entry else None,
        total_minor=entry.total_minor if entry else None,
        unresolved_checks=(
            repo.unresolved_blocking(conn, document.id) if document.status is S.NEEDS_REVIEW else []
        ),
    )


# ---- routes ------------------------------------------------------------------------------------


@router.post("/documents", response_model=UploadResponse)
def upload(
    files: Annotated[list[UploadFile], File()],
    conn: Conn,
    state: State,
    request_id: RequestId,
    batch_label: Annotated[str | None, Form(max_length=100)] = None,
) -> UploadResponse:
    """Accept files and queue them. Each file gets its own outcome; one bad file stops no other."""
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise ApiError(
            413, "too_many_files", f"Upload at most {MAX_FILES_PER_UPLOAD} files at a time."
        )
    settings = state.settings
    limit = settings.max_file_mb * 1024 * 1024
    results: list[UploadResult] = []
    for upload_file in files:
        name = upload_file.filename or "file"
        data = upload_file.file.read(limit + 1)  # one byte past the limit is enough to refuse it
        try:
            result = ingest.ingest(
                conn,
                data,
                name,
                settings=settings,
                batch_label=batch_label.strip() if batch_label and batch_label.strip() else None,
                is_synthetic=settings.synthetic_data,
                request_id=request_id,
                isolate=state.isolate_ingest,
            )
        except ingest.IngestRejected as error:
            results.append(UploadResult(filename=name, outcome="rejected", message=str(error)))
            continue
        document = result.document
        if result.outcome == "accepted":
            state.worker.submit(document.id)
        results.append(
            UploadResult(
                filename=name,
                outcome=result.outcome,
                document_id=document.id,
                status=document.status,
                message=document.failure_message,
            )
        )
    return UploadResponse(results=results)


@router.get("/documents", response_model=DocumentList)
def list_documents(
    conn: Conn,
    status: S | None = None,
    check: CheckCode | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    batch: Annotated[str | None, Query(max_length=100)] = None,
    cursor: Annotated[str | None, Query(max_length=20)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
) -> DocumentList:
    """Newest first. `cursor` is the `next_cursor` of the previous page."""
    before: int | None = None
    if cursor is not None:
        if not cursor.isdigit():
            raise ApiError(422, "invalid_cursor", "That page marker is not valid.")
        before = int(cursor)
    rows = repo.list_documents_page(
        conn,
        status=status,
        check=check,
        q=q.strip() if q and q.strip() else None,
        batch=batch,
        before_id=before,
        limit=limit + 1,
    )
    more = len(rows) > limit
    page = rows[:limit]
    return DocumentList(
        items=[document_summary(conn, document) for document in page],
        next_cursor=str(page[-1].id) if more else None,
    )


@router.get("/documents/{document_id}", response_model=DocumentDetail)
def get_document(document_id: int, conn: Conn) -> DocumentDetail:
    return document_detail(conn, repo.get_document(conn, document_id))


@router.get("/documents/{document_id}/pages/{page_number}/image")
def page_image(document_id: int, page_number: int, conn: Conn, state: State) -> FileResponse:
    repo.get_document(conn, document_id)
    page = next(
        (p for p in repo.list_pages(conn, document_id) if p.page_number == page_number), None
    )
    root = state.settings.data_dir.resolve()
    path = (root / page.image_path).resolve() if page else None
    if page is None or path is None or root not in path.parents or not path.is_file():
        raise repo.NotFound(f"Page {page_number} of document {document_id} has no picture")
    return FileResponse(
        path, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"}
    )


@router.post("/documents/{document_id}/reprocess", response_model=DocumentOut)
def reprocess(
    document_id: int, body: ReprocessRequest, conn: Conn, state: State, request_id: RequestId
) -> Document:
    """Read again (`read`) or ask the model again (`extract`). What was made after that point is
    discarded; the state machine says which documents may be sent back."""
    target = S.RECEIVED if body.from_stage == "read" else S.READ
    document = repo.change_status(conn, document_id, target, request_id=request_id)
    state.worker.submit(document_id)
    return document
