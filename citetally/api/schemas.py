"""Request and response models. The OpenAPI schema made from these generates the web app's types."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from citetally.models import (
    CheckCode,
    DocumentStatus,
    EntryLine,
    EntryType,
    Evidence,
    ExportProfile,
    FieldEdit,
    Review,
    SourceKind,
    Stage,
    VendorMatchMethod,
)

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
ReviewSeconds = Annotated[int, Field(ge=0, le=86_400)]


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---- status ------------------------------------------------------------------------------------


class StatusResponse(BaseModel):
    app: str
    version: str
    model_provider: str
    text_model: str
    vision_model: str
    ocr_engine: str
    hosted_mode: bool
    synthetic_data: bool
    database_ok: bool | None = None
    ocr_available: bool | None = None
    queue_depth: int | None = None
    last_model_call_at: str | None = None


# ---- documents ---------------------------------------------------------------------------------


class UploadResult(_Out):
    filename: str
    outcome: Literal["accepted", "duplicate", "failed", "rejected"]
    document_id: int | None = None
    status: DocumentStatus | None = None
    message: str | None = None


class UploadResponse(_Out):
    results: list[UploadResult]


class DocumentOut(_Out):
    id: int
    original_filename: str
    mime_type: str
    source_kind: SourceKind | None
    page_count: int | None
    size_bytes: int
    status: DocumentStatus
    duplicate_of: int | None
    failure_stage: Stage | None
    failure_message: str | None
    batch_label: str | None
    is_synthetic: bool
    created_at: str
    updated_at: str


class DocumentSummary(DocumentOut):
    entry_id: int | None = None
    entry_type: EntryType | None = None
    vendor_name: str | None = None
    invoice_number: str | None = None
    entry_date: str | None = None
    currency: str | None = None
    total_minor: int | None = None
    unresolved_checks: list[CheckCode] = []
    warnings: list[CheckCode] = []


class DocumentCounts(BaseModel):
    counts: dict[str, int]
    batches: list[str] = []


class DocumentList(_Out):
    items: list[DocumentSummary]
    next_cursor: str | None = None


class PageOut(_Out):
    page_number: int
    width_px: int
    height_px: int
    read_method: str
    ocr_engine: str | None
    mean_confidence: float | None
    skew_degrees: float | None
    word_count: int
    text: str
    image_url: str


class ExtractionOut(_Out):
    id: int
    attempt: int
    provider: str
    model: str
    extract_mode: str
    prompt_version: str
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int | None
    created_at: str


class EntryOut(_Out):
    id: int
    entry_type: EntryType
    vendor_id: int | None
    vendor_name_raw: str | None
    vendor_name: str | None
    vendor_match_method: VendorMatchMethod | None
    vendor_match_score: float | None
    invoice_number: str | None
    entry_date: str | None
    due_date: str | None
    po_number: str | None
    currency: str | None
    subtotal_minor: int | None
    tax_total_minor: int | None
    shipping_minor: int | None
    discount_minor: int | None
    total_minor: int | None
    category: str | None
    category_source: str | None
    notes: str | None
    lines: list[EntryLine]


class CheckOut(BaseModel):
    check_code: CheckCode
    blocking: bool
    passed: bool
    detail: dict[str, Any]
    overridden: bool
    override_reason: str | None
    overridden_at: str | None


class EventOut(BaseModel):
    event_type: str
    stage: Stage | None
    from_status: DocumentStatus | None
    to_status: DocumentStatus | None
    payload: dict[str, Any]
    duration_ms: int | None
    created_at: str


class DocumentDetail(BaseModel):
    document: DocumentOut
    pages: list[PageOut]
    extraction: ExtractionOut | None
    entry: EntryOut | None
    evidence: list[Evidence]
    checks: list[CheckOut]
    edits: list[FieldEdit]
    reviews: list[Review]
    history: list[EventOut]


class ReprocessRequest(_In):
    from_stage: Literal["read", "extract"]


# ---- editing -----------------------------------------------------------------------------------


class LinePatch(_In):
    id: int | None = None  # an existing line to change; omit for a new line
    description: Annotated[str, StringConstraints(max_length=500)] | None = None
    quantity: Annotated[str, StringConstraints(max_length=40)] | None = None
    unit_price: Annotated[str, StringConstraints(max_length=40)] | None = None
    amount_minor: Annotated[int, Field(ge=0, le=10**13)] | None = None
    tax_rate: Annotated[str, StringConstraints(max_length=40)] | None = None


class EntryPatch(_In):
    """Only the fields present are changed; null clears a field. `lines`, when present, is the
    whole list as it should be: lines left out are removed."""

    entry_type: EntryType | None = None
    invoice_number: Annotated[str, StringConstraints(max_length=200)] | None = None
    entry_date: Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")] | None = None
    due_date: Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")] | None = None
    po_number: Annotated[str, StringConstraints(max_length=200)] | None = None
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] | None = None
    subtotal_minor: Annotated[int, Field(ge=0, le=10**13)] | None = None
    tax_total_minor: Annotated[int, Field(ge=0, le=10**13)] | None = None
    shipping_minor: Annotated[int, Field(ge=0, le=10**13)] | None = None
    discount_minor: Annotated[int, Field(ge=0, le=10**13)] | None = None
    total_minor: Annotated[int, Field(ge=0, le=10**13)] | None = None
    category: Annotated[str, StringConstraints(max_length=40)] | None = None  # a category code
    notes: Annotated[str, StringConstraints(max_length=2000)] | None = None
    lines: Annotated[list[LinePatch], Field(max_length=500)] | None = None


class VendorChoice(_In):
    """Pick an existing vendor, or create one (from `name`, else the name printed on the page)."""

    vendor_id: int | None = None
    create: bool = False
    name: Text | None = None


# ---- decisions ---------------------------------------------------------------------------------


class Override(_In):
    check_code: CheckCode
    reason: Reason


class ApproveRequest(_In):
    overrides: Annotated[list[Override], Field(max_length=20)] = []
    review_seconds: ReviewSeconds | None = None


class RejectRequest(_In):
    reason: Reason
    review_seconds: ReviewSeconds | None = None


class ReopenRequest(_In):
    pass


class MarkDuplicateRequest(_In):
    duplicate_of: int
    review_seconds: ReviewSeconds | None = None


class DecisionResponse(BaseModel):
    document: DocumentOut
    review: Review


# ---- vendors and categories --------------------------------------------------------------------


class VendorOut(_Out):
    id: int
    name: str
    default_category: str | None = None
    default_currency: str | None
    is_active: bool
    aliases: list[str] = []


class VendorCreate(_In):
    name: Text
    default_category: Annotated[str, StringConstraints(max_length=40)] | None = None
    default_currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] | None = None


class AliasCreate(_In):
    alias: Text


class VendorMerge(_In):
    into: int


class CategoryOut(_Out):
    code: str
    name: str
    is_active: bool


# ---- exports -----------------------------------------------------------------------------------


class ExportOut(_Out):
    id: int
    profile: ExportProfile
    entry_count: int
    row_count: int
    file_name: str
    file_sha256: str
    created_at: str
    download_url: str


class ExportCreate(_In):
    profile: ExportProfile
    entry_ids: Annotated[list[int], Field(min_length=1, max_length=5000)] | None = None
    include_exported: bool = False


class ExportCreated(BaseModel):
    export: ExportOut
    skipped_already_exported: int


class ExportPreview(BaseModel):
    entry_count: int
    row_count: int
    totals: dict[str, str]
    first_date: str | None
    last_date: str | None
    skipped_already_exported: int
    columns: list[str]
    sample: list[list[str]]
