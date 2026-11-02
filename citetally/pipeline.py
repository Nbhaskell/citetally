"""The pipeline: read, extract, ground, match, check, then wait for a person (TRD section 3).

`process` takes a document as far as it can from wherever it is, so it is safe to call again after
a crash or a reprocess request: every stage replaces what it wrote earlier instead of adding to it.
A stage that cannot finish fails the document with a stage and a plain reason (never document text);
the person decides what happens next. Nothing here pays, posts or sends anything.
"""

from __future__ import annotations

import io
import json
import sqlite3
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from PIL import Image

from citetally import events, ingest
from citetally import repository as repo
from citetally.checks import run_checks
from citetally.config import Settings
from citetally.db import transaction
from citetally.extract import ExtractionInvalid, ExtractionTooLong, extract
from citetally.grounding import GroundedValue, ground
from citetally.matching import match_document
from citetally.models import (
    Document,
    EntryType,
    EventType,
    ExtractedFields,
    ExtractMode,
    HeaderField,
    LineField,
    Provider,
    ReadMethod,
    Stage,
    Word,
)
from citetally.models import DocumentStatus as S
from citetally.providers.base import ModelError, ModelProvider, ModelTimeout, ModelUnavailable
from citetally.reading import layout, text_layer
from citetally.reading.masking import mask_words
from citetally.reading.merge import merge_readings
from citetally.reading.ocr import (
    OcrEngine,
    OcrError,
    OcrTimeout,
    OcrUnavailable,
)
from citetally.reading.preprocess import (
    WORKING_MAX_LONG_SIDE,
    WORKING_MIN_LONG_SIDE,
    preprocess,
    preprocess_words,
)

IMAGE_MAX_SIDE_PX = 1568  # a larger picture only costs the model more tokens
READ_BASE_TIMEOUT_S = 60.0
READ_TIMEOUT_PER_PAGE_S = 150.0
_MESSAGES = {
    "ocr_unavailable": "Scanned pages need the Tesseract OCR program, and it is missing or "
    "will not start.",
    "ocr_timeout": "Reading a page took too long, so it was stopped.",
    "ocr_failed": "The pages could not be read.",
    "worker_timeout": "Reading the pages took too long, so it was stopped.",
    "worker_failed": "The pages could not be read. The file may be damaged.",
    "no_text": "No text could be read from this document, so there is nothing to pull out.",
    "model_down": "The language model is not running. Start Ollama, then reprocess this document.",
    "model_slow": "The language model took too long to answer. Reprocess to try again.",
    "model_other": "The language model could not be used.",
    "no_images": "The language model in use cannot read page pictures.",
    "invalid": "The model's answer could not be used, even after a second try.",
    "too_long": "This document has too much text to read in one go.",
    "read": "The pages could not be read.",
    "extract": "The language model could not be used.",
    "ground": "Finding the values on the page failed unexpectedly. Reprocess to try again.",
    "match": "Matching the vendor failed unexpectedly. Reprocess to try again.",
    "check": "Running the checks failed unexpectedly. Reprocess to try again.",
}


class StageFailure(Exception):
    """A stage cannot finish. `message` is plain words for the person reading, never content."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass
class Services:
    settings: Settings
    ocr: OcrEngine
    provider: ModelProvider
    run_checks: Callable[[sqlite3.Connection, int], None] | None = None  # tests inject one
    extract_mode: ExtractMode = ExtractMode.TEXT_ONLY
    isolate: bool = True  # read pages in a separate process; tests turn this off
    today: date | None = None  # the date the checks use; None means the real date


# ---- reading (the part that runs in a worker) --------------------------------------------------


# What each extra reading of a scanned page changes: Tesseract's page mode (None is the engine's
# own) and the size the page is enlarged to. The first reading of a plan is the usual one. In a
# trial on development scans each added reading found more of the page's true values: one reading
# 70%, two 80%, three 83% (`tools/ocr_lab.py`).
_READING_PLANS: dict[int, tuple[tuple[int | None, int, int], ...]] = {
    1: ((None, WORKING_MIN_LONG_SIDE, WORKING_MAX_LONG_SIDE),),
    2: (
        (None, WORKING_MIN_LONG_SIDE, WORKING_MAX_LONG_SIDE),
        (6, WORKING_MIN_LONG_SIDE, WORKING_MAX_LONG_SIDE),
    ),
    3: (
        (None, WORKING_MIN_LONG_SIDE, WORKING_MAX_LONG_SIDE),
        (6, WORKING_MIN_LONG_SIDE, WORKING_MAX_LONG_SIDE),
        (None, 2600, 3400),
    ),
}


@dataclass(frozen=True)
class _ReadJob:
    original: Path
    page_images: list[Path]
    is_pdf: bool
    min_chars: int
    ocr: OcrEngine
    readings: int = 1


@dataclass(frozen=True)
class _PageRead:
    words: list[Word]
    text: str
    method: ReadMethod
    engine: str | None
    mean_confidence: float | None
    skew_degrees: float | None
    width: int
    height: int
    alt_words: list[list[Word]] = field(default_factory=list)  # each separate reading


@dataclass(frozen=True)
class _ReadResult:
    pages: list[_PageRead]
    error: str | None = None


def _extra_readings(
    ocr: OcrEngine, image: Image.Image, plan: tuple[tuple[int | None, int, int], ...]
) -> list[list[Word]]:
    """The other readings of a scanned page, made at the same time. A reading that fails is left
    out: the first reading decides whether the page could be read at all."""

    def one(step: tuple[int | None, int, int]) -> list[Word] | None:
        mode, low, high = step
        try:
            prepared = preprocess(image, min_long=low, max_long=high)
            return preprocess_words(prepared, ocr.read_page(prepared.image, psm=mode).words)
        except OcrError:
            return None

    if not plan:
        return []
    with ThreadPoolExecutor(max_workers=len(plan)) as pool:
        return [words for words in pool.map(one, plan) if words is not None]


def _read_job(job: _ReadJob) -> _ReadResult:
    layer: list[list[Word] | None] = []
    if job.is_pdf:
        try:
            layer = text_layer.read_pdf(job.original.read_bytes(), job.min_chars)
        except text_layer.TextLayerError:
            layer = []
    pages: list[_PageRead] = []
    for index, path in enumerate(job.page_images):
        with Image.open(path) as opened:
            image = opened.copy()
        words = layer[index] if index < len(layer) else None
        if words is not None:
            masked = mask_words(words)
            pages.append(
                _PageRead(
                    masked,
                    layout.build_text(masked),
                    ReadMethod.TEXT_LAYER,
                    None,
                    None,
                    None,
                    *image.size,
                )
            )
            continue
        try:
            plan = _READING_PLANS[job.readings]
            first_pre = preprocess(image, min_long=plan[0][1], max_long=plan[0][2])
            first = job.ocr.read_page(first_pre.image, psm=plan[0][0])
            extras = _extra_readings(job.ocr, image, plan[1:])
        except OcrUnavailable:
            return _ReadResult([], "ocr_unavailable")
        except OcrTimeout:
            return _ReadResult([], "ocr_timeout")
        except OcrError:
            return _ReadResult([], "ocr_failed")
        readings = [mask_words(preprocess_words(first_pre, first.words))]
        readings += [mask_words(words) for words in extras]
        merged = merge_readings(readings[0], readings[1:]) if len(readings) > 1 else readings[0]
        pages.append(
            _PageRead(
                merged,
                layout.build_text(merged),
                ReadMethod.OCR,
                job.ocr.name,
                first.mean_confidence,
                first_pre.skew_degrees,
                *image.size,
                alt_words=readings if len(readings) > 1 else [],
            )
        )
    return _ReadResult(pages)


def read_stage(conn: sqlite3.Connection, document: Document, services: Services) -> dict[str, Any]:
    data_dir = services.settings.data_dir
    count = document.page_count or 0
    job = _ReadJob(
        original=data_dir / document.stored_path,
        page_images=[
            data_dir / "pages" / str(document.id) / f"{n}.png" for n in range(1, count + 1)
        ],
        is_pdf=document.mime_type == "application/pdf",
        min_chars=services.settings.text_layer_min_chars,
        ocr=services.ocr,
        readings=services.settings.ocr_readings,
    )
    try:
        if services.isolate:
            timeout = READ_BASE_TIMEOUT_S + READ_TIMEOUT_PER_PAGE_S * max(count, 1)
            result = ingest.isolated_call(_read_job, job, timeout_s=timeout)
        else:
            result = _read_job(job)
    except ingest.WorkerTimeout:
        raise StageFailure(_MESSAGES["worker_timeout"]) from None
    except (ingest.WorkerFailed, OSError):
        raise StageFailure(_MESSAGES["worker_failed"]) from None
    if result.error:
        raise StageFailure(_MESSAGES[result.error])
    if not result.pages:
        raise StageFailure(_MESSAGES["worker_failed"])

    with transaction(conn):
        repo.clear_pages(conn, document.id)
        for number, page in enumerate(result.pages, start=1):
            repo.add_page(
                conn,
                document.id,
                page_number=number,
                image_path=f"pages/{document.id}/{number}.png",
                width_px=page.width,
                height_px=page.height,
                read_method=page.method,
                words=[word.model_dump() for word in page.words],
                text=page.text,
                ocr_engine=page.engine,
                mean_confidence=page.mean_confidence,
                skew_degrees=page.skew_degrees,
                alt_words=[[w.model_dump() for w in reading] for reading in page.alt_words],
            )
        repo.change_status(conn, document.id, S.READ)

    ocr_pages = [p for p in result.pages if p.method is ReadMethod.OCR]
    payload: dict[str, Any] = {
        "pages": len(result.pages),
        "word_count": sum(len(p.words) for p in result.pages),
        "read_method": (ocr_pages[0] if ocr_pages else result.pages[0]).method.value,
    }
    confidences = [p.mean_confidence for p in ocr_pages if p.mean_confidence is not None]
    if confidences:
        payload["mean_confidence"] = round(sum(confidences) / len(confidences), 1)
    if ocr_pages and services.ocr.name == "tesseract":
        payload["ocr_engine"] = "tesseract"
    return payload


# ---- extracting --------------------------------------------------------------------------------


def _page_image(path: Path) -> bytes:
    """The stored page picture, scaled down for the model, as JPEG bytes."""
    with Image.open(path) as opened:
        picture = opened.convert("RGB")
    picture.thumbnail((IMAGE_MAX_SIDE_PX, IMAGE_MAX_SIDE_PX))
    buffer = io.BytesIO()
    picture.save(buffer, "JPEG", quality=90)
    return buffer.getvalue()


def extract_stage(
    conn: sqlite3.Connection, document: Document, services: Services
) -> dict[str, Any]:
    texts = [page.text for page in repo.list_pages(conn, document.id)]
    if not any(text.strip() for text in texts):
        raise StageFailure(_MESSAGES["no_text"])
    codes = [c.code for c in repo.list_categories(conn) if c.is_active]
    mode = services.extract_mode
    images = None
    if mode is ExtractMode.TEXT_AND_IMAGE:
        if not services.provider.supports_vision:
            raise StageFailure(_MESSAGES["no_images"])
        images = [
            _page_image(services.settings.data_dir / page.image_path)
            for page in repo.list_pages(conn, document.id)
        ]
    try:
        result = extract(
            services.provider,
            texts,
            codes,
            max_tokens=services.settings.extract_max_tokens,
            timeout_s=services.settings.extract_timeout_s,
            images=images,
        )
    except ModelUnavailable:
        raise StageFailure(_MESSAGES["model_down"]) from None
    except ModelTimeout:
        raise StageFailure(_MESSAGES["model_slow"]) from None
    except ModelError:
        raise StageFailure(_MESSAGES["model_other"]) from None
    except ExtractionInvalid:
        raise StageFailure(_MESSAGES["invalid"]) from None
    except ExtractionTooLong:
        raise StageFailure(_MESSAGES["too_long"]) from None

    fields = result.fields
    with transaction(conn):
        repo.clear_entry(conn, document.id)
        extraction = repo.add_extraction(
            conn,
            document.id,
            provider=Provider(services.provider.name),
            model=services.provider.model,
            extract_mode=mode,
            prompt_version=result.prompt_version,
            fields=fields.model_dump(mode="json"),
            raw_response=result.raw,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            duration_ms=result.duration_ms,
        )
        entry = repo.create_entry(
            conn,
            document.id,
            extraction.id,
            EntryType(fields.entry_type),
            vendor_name_raw=_clean(fields.vendor_name),
            invoice_number=_clean(fields.invoice_number),
            po_number=_clean(fields.po_number),
        )
        repo.replace_lines(
            conn,
            entry.id,
            [repo.LineInput(description=_clean(item.description)) for item in fields.lines],
        )
        repo.change_status(conn, document.id, S.EXTRACTED)

    payload: dict[str, Any] = {
        "provider": services.provider.name,
        "extract_mode": mode.value,
        "attempt": result.attempts,
    }
    if result.input_tokens is not None:
        payload["input_tokens"] = result.input_tokens
    if result.output_tokens is not None:
        payload["output_tokens"] = result.output_tokens
    return payload


def _clean(text: str | None) -> str | None:
    return text.strip() if text and text.strip() else None


# ---- grounding, matching, checking -------------------------------------------------------------


def _decimal_text(value: object, *, absolute: bool) -> str | None:
    if not isinstance(value, Decimal):
        return None
    return format(abs(value) if absolute else value, "f")


def ground_stage(
    conn: sqlite3.Connection, document: Document, services: Services
) -> dict[str, Any]:
    entry = repo.get_entry_for_document(conn, document.id)
    extraction = repo.latest_extraction(conn, document.id)
    if entry is None or extraction is None:
        raise StageFailure(_MESSAGES["ground"])
    fields = ExtractedFields.model_validate_json(extraction.fields)
    pages = [
        [Word.model_validate(w) for w in json.loads(page.words)]
        for page in repo.list_pages(conn, document.id)
    ]
    alternatives = [
        [[Word.model_validate(w) for w in reading] for reading in json.loads(page.alt_words)]
        for page in repo.list_pages(conn, document.id)
    ]
    settings = services.settings
    result = ground(
        fields,
        pages,
        alternatives=alternatives,
        locale=settings.locale,
        currency=settings.default_currency,
        threshold=settings.grounding_match_threshold,
    )

    credit = entry.entry_type is EntryType.CREDIT_NOTE
    header: dict[Any, GroundedValue] = {v.field: v for v in result.values if v.line_index is None}
    per_line = {(v.field, v.line_index): v for v in result.values if v.line_index is not None}

    def minor(name: HeaderField) -> int | None:
        value = header.get(name)
        if value is None or value.amount_minor is None:
            return None
        return (
            abs(value.amount_minor)
            if credit or name is HeaderField.DISCOUNT
            else value.amount_minor
        )

    def iso(name: HeaderField) -> str | None:
        value = header.get(name)
        return value.value.isoformat() if value and isinstance(value.value, date) else None

    def line_amount(name: LineField, index: int) -> str | None:
        value = per_line.get((name, index))
        return _decimal_text(value.value if value else None, absolute=credit)

    lines = []
    for index, line in enumerate(fields.lines):
        amount = per_line.get((LineField.AMOUNT, index))
        cents = amount.amount_minor if amount is not None else None
        lines.append(
            repo.LineInput(
                description=_clean(line.description),
                quantity=line_amount(LineField.QUANTITY, index),
                unit_price=line_amount(LineField.UNIT_PRICE, index),
                amount_minor=abs(cents) if cents is not None and credit else cents,
                tax_rate=_decimal_text(result.line_tax_rates[index], absolute=False),
            )
        )

    with transaction(conn):
        if HeaderField.INVOICE_NUMBER in result.rejected:
            repo.update_entry(conn, entry.id, invoice_number=None)
        repo.update_entry(
            conn,
            entry.id,
            entry_date=iso(HeaderField.ENTRY_DATE),
            due_date=iso(HeaderField.DUE_DATE),
            currency=result.currency,
            subtotal_minor=minor(HeaderField.SUBTOTAL),
            tax_total_minor=minor(HeaderField.TAX_TOTAL),
            shipping_minor=minor(HeaderField.SHIPPING),
            discount_minor=minor(HeaderField.DISCOUNT),
            total_minor=minor(HeaderField.TOTAL),
        )
        repo.clear_evidence(conn, entry.id)
        repo.replace_lines(conn, entry.id, lines)
        line_ids = [row.id for row in repo.list_lines(conn, entry.id)]
        for value in result.values:
            box = None
            if value.found and None not in (value.x0, value.y0, value.x1, value.y1):
                box = (value.x0, value.y0, value.x1, value.y1)
            repo.add_evidence(
                conn,
                entry.id,
                value.field,
                value.printed_text,
                value.found,
                line_id=None if value.line_index is None else line_ids[value.line_index],
                page_number=value.page_number,
                box=box,  # type: ignore[arg-type]
                match_score=value.match_score,
            )
    return {"count": len(result.values)}


def match_stage(conn: sqlite3.Connection, document: Document, services: Services) -> dict[str, Any]:
    entry = repo.get_entry_for_document(conn, document.id)
    extraction = repo.latest_extraction(conn, document.id)
    if entry is None or extraction is None:
        raise StageFailure(_MESSAGES["match"])
    fields = ExtractedFields.model_validate_json(extraction.fields)
    page_text = " ".join(page.text for page in repo.list_pages(conn, document.id) if page.text)
    matched = match_document(
        conn, entry.vendor_name_raw, fields.category_suggestion, page_text=page_text
    )
    vendor = matched.vendor
    repo.update_entry(
        conn,
        entry.id,
        vendor_id=vendor.vendor_id,
        vendor_match_method=vendor.method,
        vendor_match_score=vendor.score,
        category_id=matched.category.category_id,
        category_source=matched.category.source,
    )
    return {}


def check_stage(conn: sqlite3.Connection, document: Document, services: Services) -> dict[str, Any]:
    if services.run_checks is not None:
        services.run_checks(conn, document.id)
        return {}
    outcomes = run_checks(conn, document.id, settings=services.settings, today=services.today)
    return {"count": len(outcomes)}


# ---- running -----------------------------------------------------------------------------------

_Stage = Callable[[sqlite3.Connection, Document, Services], dict[str, Any]]


def _fail(
    conn: sqlite3.Connection, document_id: int, stage: Stage, message: str, request_id: str | None
) -> None:
    repo.change_status(
        conn,
        document_id,
        S.FAILED,
        failure_stage=stage,
        failure_message=message,
        request_id=request_id,
    )
    events.record_event(
        conn, EventType.STAGE_FAILED, document_id=document_id, stage=stage, request_id=request_id
    )


def _run(
    conn: sqlite3.Connection,
    document: Document,
    stage: Stage,
    action: _Stage,
    services: Services,
    request_id: str | None,
    *,
    attempts: int,
) -> bool:
    """Run one stage. Returns False if it failed the document."""
    events.record_event(
        conn, EventType.STAGE_STARTED, document_id=document.id, stage=stage, request_id=request_id
    )
    started = time.monotonic()
    for attempt in range(1, attempts + 1):
        try:
            payload = action(conn, document, services)
            break
        except StageFailure as failure:
            _fail(conn, document.id, stage, failure.message, request_id)
            return False
        except Exception:  # the message may hold document text, so only the fact is kept
            if attempt < attempts:
                continue
            _fail(
                conn,
                document.id,
                stage,
                _MESSAGES.get(stage.value, _MESSAGES["worker_failed"]),
                request_id,
            )
            return False
    events.record_event(
        conn,
        EventType.STAGE_FINISHED,
        document_id=document.id,
        stage=stage,
        payload=payload,
        request_id=request_id,
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    return True


def process(
    conn: sqlite3.Connection,
    document_id: int,
    services: Services,
    *,
    request_id: str | None = None,
) -> Document:
    """Take a document as far as it can go from its current status. Safe to call again."""
    document = repo.get_document(conn, document_id)
    steps: list[tuple[S, Stage, _Stage, int]] = [
        (S.RECEIVED, Stage.READ, read_stage, 1),
        (S.READ, Stage.EXTRACT, extract_stage, 1),
    ]
    for status, stage, action, attempts in steps:
        if document.status is status:
            if not _run(conn, document, stage, action, services, request_id, attempts=attempts):
                return repo.get_document(conn, document_id)
            document = repo.get_document(conn, document_id)

    if document.status is S.EXTRACTED:
        for stage, action in (
            (Stage.GROUND, ground_stage),
            (Stage.MATCH, match_stage),
            (Stage.CHECK, check_stage),
        ):
            if not _run(conn, document, stage, action, services, request_id, attempts=2):
                return repo.get_document(conn, document_id)
        repo.change_status(conn, document_id, S.NEEDS_REVIEW, request_id=request_id)
    return repo.get_document(conn, document_id)
