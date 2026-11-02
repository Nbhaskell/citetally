"""Enums and models. The single source of truth for allowed values in the code.

Names and values come from docs/BACKEND_SCHEMA.md; tests/test_models.py fails if this file, the
document and the database CHECK constraints ever disagree. Money is never a float: amounts are
integer minor units (`*_minor`), quantities and unit prices are exact decimal strings.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator


class EntryType(StrEnum):
    INVOICE = "invoice"
    RECEIPT = "receipt"
    CREDIT_NOTE = "credit_note"


class SourceKind(StrEnum):
    DIGITAL_PDF = "digital_pdf"
    SCANNED_PDF = "scanned_pdf"
    IMAGE = "image"


class ReadMethod(StrEnum):
    TEXT_LAYER = "text_layer"
    OCR = "ocr"


class ExtractMode(StrEnum):
    TEXT_ONLY = "text_only"
    TEXT_AND_IMAGE = "text_and_image"


class DocumentStatus(StrEnum):
    RECEIVED = "received"
    READ = "read"
    EXTRACTED = "extracted"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPORTED = "exported"
    FAILED = "failed"
    DUPLICATE = "duplicate"


class Stage(StrEnum):
    INGEST = "ingest"
    READ = "read"
    EXTRACT = "extract"
    GROUND = "ground"
    MATCH = "match"
    CHECK = "check"


class CheckCode(StrEnum):
    REQUIRED_FIELDS = "REQUIRED_FIELDS"
    VALUE_IN_DOCUMENT = "VALUE_IN_DOCUMENT"
    LINE_MATH = "LINE_MATH"
    SUBTOTAL_MATCH = "SUBTOTAL_MATCH"
    TAX_MATCH = "TAX_MATCH"
    TOTAL_MATCH = "TOTAL_MATCH"
    DUPLICATE_SUSPECT = "DUPLICATE_SUSPECT"
    UNKNOWN_VENDOR = "UNKNOWN_VENDOR"
    AMOUNT_OUTLIER = "AMOUNT_OUTLIER"
    DATE_SANITY = "DATE_SANITY"
    CURRENCY_CHECK = "CURRENCY_CHECK"
    LOW_READ_QUALITY = "LOW_READ_QUALITY"
    AMBIGUOUS_FORMAT = "AMBIGUOUS_FORMAT"
    SUSPICIOUS_TEXT = "SUSPICIOUS_TEXT"


class HeaderField(StrEnum):
    VENDOR_NAME = "vendor_name"
    INVOICE_NUMBER = "invoice_number"
    ENTRY_DATE = "entry_date"
    DUE_DATE = "due_date"
    PO_NUMBER = "po_number"
    CURRENCY = "currency"
    SUBTOTAL = "subtotal"
    TAX_TOTAL = "tax_total"
    SHIPPING = "shipping"
    DISCOUNT = "discount"
    TOTAL = "total"


class LineField(StrEnum):
    DESCRIPTION = "description"
    QUANTITY = "quantity"
    UNIT_PRICE = "unit_price"
    AMOUNT = "amount"
    TAX_RATE = "tax_rate"


class EditField(StrEnum):
    """What a reviewer can change: every header and line field, plus category and entry type."""

    VENDOR_NAME = "vendor_name"
    INVOICE_NUMBER = "invoice_number"
    ENTRY_DATE = "entry_date"
    DUE_DATE = "due_date"
    PO_NUMBER = "po_number"
    CURRENCY = "currency"
    SUBTOTAL = "subtotal"
    TAX_TOTAL = "tax_total"
    SHIPPING = "shipping"
    DISCOUNT = "discount"
    TOTAL = "total"
    DESCRIPTION = "description"
    QUANTITY = "quantity"
    UNIT_PRICE = "unit_price"
    AMOUNT = "amount"
    TAX_RATE = "tax_rate"
    CATEGORY = "category"
    ENTRY_TYPE = "entry_type"


class Decision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    REOPEN = "reopen"
    MARK_DUPLICATE = "mark_duplicate"


class VendorMatchMethod(StrEnum):
    EXACT = "exact"
    ALIAS = "alias"
    FUZZY = "fuzzy"
    MANUAL = "manual"
    CREATED = "created"


class CategorySource(StrEnum):
    VENDOR_DEFAULT = "vendor_default"
    MODEL = "model"
    MANUAL = "manual"


class ExportProfile(StrEnum):
    LINES_CSV = "lines_csv"
    ENTRIES_CSV = "entries_csv"


class Provider(StrEnum):
    OLLAMA = "ollama"
    HOSTED = "hosted"


class EventType(StrEnum):
    """Audit event types (the `audit_events.event_type` column has no CHECK; see the schema)."""

    STAGE_STARTED = "stage_started"
    STAGE_FINISHED = "stage_finished"
    STAGE_FAILED = "stage_failed"
    STATUS_CHANGED = "status_changed"
    CHECK_FAILED = "check_failed"
    REVIEW_RECORDED = "review_recorded"
    EXPORT_CREATED = "export_created"


MIME_TYPES = ("application/pdf", "image/png", "image/jpeg")

# Checks that must pass, or be overridden with a written reason, before approval.
BLOCKING_CHECKS = frozenset(
    {
        CheckCode.REQUIRED_FIELDS,
        CheckCode.VALUE_IN_DOCUMENT,
        CheckCode.LINE_MATH,
        CheckCode.SUBTOTAL_MATCH,
        CheckCode.TAX_MATCH,
        CheckCode.TOTAL_MATCH,
        CheckCode.DUPLICATE_SUSPECT,
        CheckCode.UNKNOWN_VENDOR,
    }
)


def is_blocking(code: CheckCode) -> bool:
    return code in BLOCKING_CHECKS


def required_fields(entry_type: EntryType) -> set[str]:
    """Fields that must be present before an entry of this type can be approved."""
    required = {"vendor_name", "entry_date", "total", "category"}
    if entry_type in {EntryType.INVOICE, EntryType.CREDIT_NOTE}:
        required.add("invoice_number")
    return required


class _Row(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class SchemaMigration(_Row):
    version: int
    name: str
    applied_at: str


class Category(_Row):
    id: int
    code: str
    name: str
    is_active: bool
    created_at: str


class Vendor(_Row):
    id: int
    name: str
    normalized_name: str
    default_category_id: int | None
    default_currency: str | None
    is_active: bool
    is_synthetic: bool
    created_at: str


class VendorAlias(_Row):
    id: int
    vendor_id: int
    alias: str
    normalized_alias: str
    created_at: str


class Document(_Row):
    id: int
    original_filename: str
    stored_path: str
    file_sha256: str
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


class Page(_Row):
    id: int
    document_id: int
    page_number: int
    image_path: str
    width_px: int
    height_px: int
    read_method: ReadMethod
    ocr_engine: str | None
    mean_confidence: float | None
    skew_degrees: float | None
    word_count: int
    words: str  # JSON text, see Word
    text: str
    created_at: str
    alt_words: str = "[]"  # JSON text: each separate reading of the page, a list of word lists


class Extraction(_Row):
    id: int
    document_id: int
    attempt: int
    provider: Provider
    model: str
    extract_mode: ExtractMode
    prompt_version: str
    fields: str  # JSON text, see ExtractedFields
    raw_response: str
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int | None
    created_at: str


class Entry(_Row):
    id: int
    document_id: int
    extraction_id: int
    entry_type: EntryType
    vendor_id: int | None
    vendor_name_raw: str | None
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
    category_id: int | None
    category_source: CategorySource | None
    notes: str | None
    created_at: str
    updated_at: str


class EntryLine(_Row):
    id: int
    entry_id: int
    line_number: int
    description: str | None
    quantity: str | None  # exact decimal string
    unit_price: str | None  # exact decimal string
    amount_minor: int | None
    tax_rate: str | None  # exact decimal string
    created_at: str


class Evidence(_Row):
    id: int
    entry_id: int
    line_id: int | None
    field: HeaderField | LineField
    printed_text: str
    found: bool
    page_number: int | None
    x0: float | None
    y0: float | None
    x1: float | None
    y1: float | None
    match_score: float | None
    created_at: str


class Check(_Row):
    id: int
    document_id: int
    check_code: CheckCode
    blocking: bool
    passed: bool
    detail: str  # JSON text
    overridden: bool
    override_reason: str | None
    overridden_at: str | None
    created_at: str


class FieldEdit(_Row):
    id: int
    entry_id: int
    line_id: int | None
    field: EditField
    old_value: str | None
    new_value: str | None
    reviewer: str
    created_at: str


class Review(_Row):
    id: int
    document_id: int
    decision: Decision
    reason: str | None
    edited: bool
    overrides: int
    reviewer: str
    review_seconds: int | None
    created_at: str


class Export(_Row):
    id: int
    profile: ExportProfile
    entry_count: int
    row_count: int
    file_name: str
    file_sha256: str
    created_at: str


class ExportItem(_Row):
    export_id: int
    entry_id: int


class AuditEvent(_Row):
    id: int
    document_id: int | None
    event_type: str
    stage: Stage | None
    from_status: DocumentStatus | None
    to_status: DocumentStatus | None
    payload: str  # JSON text: ids, codes, counts and timings only
    request_id: str | None
    duration_ms: int | None
    created_at: str


class Setting(_Row):
    key: str
    value: str
    updated_at: str


class Word(BaseModel):
    """One word on a page. Coordinates are fractions of the page, origin at the top left."""

    model_config = ConfigDict(extra="forbid")

    t: str
    x0: float = Field(ge=0, le=1)
    y0: float = Field(ge=0, le=1)
    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)
    c: float | None  # OCR confidence 0 to 100; null for a PDF text layer

    @model_validator(mode="after")
    def box_is_ordered(self) -> Word:
        if self.x0 > self.x1 or self.y0 > self.y1:
            raise ValueError("a word's box must have x0 <= x1 and y0 <= y1")
        return self


class ExtractedLine(BaseModel):
    """Text copied from one printed line. Every value is a string or null, never a number."""

    model_config = ConfigDict(extra="forbid")

    description: StrictStr | None = None
    quantity: StrictStr | None = None
    unit_price: StrictStr | None = None
    amount: StrictStr | None = None
    tax_rate: StrictStr | None = None


class ExtractedFields(BaseModel):
    """What the model returns. It copies printed text; code parses and checks it."""

    model_config = ConfigDict(extra="forbid")

    entry_type: EntryType
    vendor_name: StrictStr | None = None
    invoice_number: StrictStr | None = None
    entry_date: StrictStr | None = None
    due_date: StrictStr | None = None
    po_number: StrictStr | None = None
    currency: StrictStr | None = None
    lines: list[ExtractedLine] = Field(default_factory=list)
    subtotal: StrictStr | None = None
    tax_total: StrictStr | None = None
    shipping: StrictStr | None = None
    discount: StrictStr | None = None
    total: StrictStr | None = None
    category_suggestion: StrictStr | None = None
