"""Ingest: judge a file by its bytes, enforce limits, hash it, store it by hash, render its pages.

An uploaded file is hostile until proven otherwise (docs/TRD.md sections 4.1 and 9):
  * the type comes from the leading bytes, never from the name or the declared type;
  * size, page count and pixel count are limited, and a tiny file that claims to be enormous is
    refused from its header, before anything is decoded;
  * parsing and rendering run in a separate process with a timeout, so a malformed file can
    crash or hang that process but not the server;
  * the original is stored under its SHA-256, never under a name taken from the upload, and the
    uploaded name is kept only as cleaned display text;
  * nothing in the file is executed or followed.
"""

from __future__ import annotations

import hashlib
import io
import multiprocessing
import os
import re
import shutil
import sqlite3
import tempfile
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any, Literal

import pypdfium2 as pdfium
from PIL import Image, ImageOps

from citetally import events
from citetally import repository as repo
from citetally.config import Settings
from citetally.models import Document, EventType, SourceKind, Stage
from citetally.models import DocumentStatus as S

RENDER_DPI = 200
INSPECT_TIMEOUT_S = 60.0
_MAX_NAME = 200

_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)
_FORMAT_FOR = {"image/png": "PNG", "image/jpeg": "JPEG"}


class IngestRejected(Exception):
    """The file was refused and nothing was kept: an unsupported type, or no room to save it."""


class WorkerTimeout(Exception):
    """The isolated worker did not finish in time and was killed."""


class WorkerFailed(Exception):
    """The isolated worker crashed or raised. The reason carries no file content."""


@dataclass(frozen=True)
class Limits:
    max_bytes: int
    max_pages: int
    max_pixels: int
    text_min_chars: int

    @classmethod
    def from_settings(cls, settings: Settings) -> Limits:
        return cls(
            max_bytes=settings.max_file_mb * 1024 * 1024,
            max_pages=settings.max_pages,
            max_pixels=settings.max_image_pixels,
            text_min_chars=settings.text_layer_min_chars,
        )


@dataclass(frozen=True)
class PageImage:
    page_number: int
    path: str  # relative to the data folder
    width_px: int
    height_px: int


@dataclass(frozen=True)
class IngestResult:
    document: Document
    pages: list[PageImage]
    outcome: Literal["accepted", "duplicate", "failed"]


# ---- small pure helpers -----------------------------------------------------------------------


def detect_type(data: bytes) -> str | None:
    """The MIME type from the file's first bytes. The PDF marker must be the very first thing."""
    for signature, mime in _SIGNATURES:
        if data.startswith(signature):
            return mime
    return None


def sanitize_filename(name: str) -> str:
    """The uploaded name as safe display text: no folders, no control or direction characters."""
    last = re.split(r"[\\/]", name)[-1]
    kept = "".join(ch for ch in last if unicodedata.category(ch) not in {"Cc", "Cf", "Cs", "Co"})
    kept = kept.strip(" .")
    if not kept:
        return "unnamed"
    if len(kept) > _MAX_NAME:
        stem, dot, extension = kept.rpartition(".")
        extension = extension if dot and len(extension) <= 10 else ""
        keep = _MAX_NAME - len(extension) - (1 if extension else 0)
        kept = (kept[:keep] if not extension else stem[:keep] + "." + extension)[:_MAX_NAME]
    return kept


_NO_ROOM = "The file could not be saved. The disk may be full or not writable."


def store_original(folder: Path, data: bytes) -> Path:
    """Write the file as `<folder>/<sha256>`. Whole or not at all; never overwritten."""
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / hashlib.sha256(data).hexdigest()
    if target.exists():
        return target
    descriptor, temporary = tempfile.mkstemp(dir=folder, prefix=".incoming-")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    return target


# ---- the isolated worker ----------------------------------------------------------------------


def _run_child(connection: Connection, func: Callable[..., Any], args: tuple[Any, ...]) -> None:
    try:
        connection.send(("ok", func(*args)))
    except BaseException as error:
        connection.send(("error", type(error).__name__))
    finally:
        connection.close()


def isolated_call(func: Callable[..., Any], *args: Any, timeout_s: float) -> Any:
    """Run `func(*args)` in a fresh process. Killed at the timeout; failures carry no content."""
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_run_child, args=(sender, func, args), daemon=True)
    process.start()
    sender.close()
    try:
        if not receiver.poll(timeout_s):
            raise WorkerTimeout(f"The worker did not finish within {timeout_s:g} seconds.")
        try:
            kind, payload = receiver.recv()
        except (EOFError, OSError) as error:
            raise WorkerFailed("The worker stopped without an answer.") from error
    finally:
        receiver.close()
        if process.is_alive():
            process.kill()
        process.join(10)
    if kind != "ok":
        raise WorkerFailed(f"The worker failed ({payload}).")
    return payload


# ---- inspecting a file (runs in the worker) ---------------------------------------------------


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def _inspect_pdf(data: bytes, limits: Limits) -> dict[str, Any]:
    document = pdfium.PdfDocument(data)
    count = len(document)
    if count == 0:
        return {"ok": False, "reason": "The PDF has no pages."}
    if count > limits.max_pages:
        return {
            "ok": False,
            "reason": f"The PDF has {count} pages; the limit is {limits.max_pages}.",
        }
    scale = RENDER_DPI / 72
    sizes = [document[i].get_size() for i in range(count)]
    for width, height in sizes:
        if width * scale * height * scale > limits.max_pixels:
            return {"ok": False, "reason": "A page is too large to render safely."}
    pages: list[tuple[bytes, int, int]] = []
    with_text = 0
    for index in range(count):
        page = document[index]
        text = page.get_textpage().get_text_range()
        if sum(1 for ch in text if ch.isprintable() and not ch.isspace()) >= limits.text_min_chars:
            with_text += 1
        rendered = page.render(scale=scale).to_pil().convert("RGB")
        pages.append((_png(rendered), rendered.width, rendered.height))
    digital = with_text * 2 >= count
    return {
        "ok": True,
        "source_kind": (SourceKind.DIGITAL_PDF if digital else SourceKind.SCANNED_PDF).value,
        "pages": pages,
    }


def _inspect_image(data: bytes, mime: str, limits: Limits) -> dict[str, Any]:
    # Our own check below runs on the header before any pixel is decoded, so Pillow's separate
    # bomb check (which would raise or warn first, with a less useful message) is switched off.
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(io.BytesIO(data)) as image:
        if image.format != _FORMAT_FOR[mime]:
            return {"ok": False, "reason": "The file's contents do not match its type."}
        if image.width * image.height > limits.max_pixels:
            return {
                "ok": False,
                "reason": (
                    f"The image is {image.width:,} by {image.height:,} pixels; "
                    f"the limit is {limits.max_pixels:,} pixels in total."
                ),
            }
        image.seek(0)
        upright = ImageOps.exif_transpose(image) or image
        if upright.mode in {"RGBA", "LA", "P"}:
            rgba = upright.convert("RGBA")
            flat = Image.new("RGB", rgba.size, "white")
            flat.paste(rgba, mask=rgba.getchannel("A"))
            upright = flat
        else:
            upright = upright.convert("RGB")
        return {
            "ok": True,
            "source_kind": SourceKind.IMAGE.value,
            "pages": [(_png(upright), upright.width, upright.height)],
        }


def _inspect(data: bytes, mime: str, limits: Limits) -> dict[str, Any]:
    """Validate and render. Returns pages as PNG bytes, or a plain reason the file was refused."""
    try:
        if mime == "application/pdf":
            return _inspect_pdf(data, limits)
        return _inspect_image(data, mime, limits)
    except Exception:
        return {"ok": False, "reason": "The file could not be read. It may be damaged or locked."}


# ---- the stage --------------------------------------------------------------------------------


def _fail(conn: sqlite3.Connection, document_id: int, reason: str, request_id: str | None) -> None:
    repo.change_status(
        conn,
        document_id,
        S.FAILED,
        failure_stage=Stage.INGEST,
        failure_message=reason,
        request_id=request_id,
    )
    events.record_event(
        conn,
        EventType.STAGE_FAILED,
        document_id=document_id,
        stage=Stage.INGEST,
        request_id=request_id,
    )


def ingest(
    conn: sqlite3.Connection,
    data: bytes,
    filename: str,
    *,
    settings: Settings,
    batch_label: str | None = None,
    is_synthetic: bool = True,
    request_id: str | None = None,
    isolate: bool = True,
) -> IngestResult:
    """Accept one uploaded file. Returns what happened; raises IngestRejected for other types."""
    mime = detect_type(data)
    if mime is None:
        raise IngestRejected("This file is not a PDF, PNG or JPEG, so it cannot be read.")
    limits = Limits.from_settings(settings)
    sha = hashlib.sha256(data).hexdigest()
    name = sanitize_filename(filename)
    started = time.monotonic()

    def new_row(stored_path: str) -> Document:
        row = repo.create_document(
            conn,
            original_filename=name,
            stored_path=stored_path,
            file_sha256=sha,
            mime_type=mime,
            size_bytes=len(data),
            batch_label=batch_label,
            is_synthetic=is_synthetic,
        )
        events.record_event(
            conn,
            EventType.STAGE_STARTED,
            document_id=row.id,
            stage=Stage.INGEST,
            request_id=request_id,
        )
        return row

    earlier = [d for d in repo.find_documents_by_sha(conn, sha) if d.status is not S.FAILED]
    if earlier:
        row = new_row(earlier[0].stored_path)
        done = repo.change_status(
            conn, row.id, S.DUPLICATE, duplicate_of=earlier[0].id, request_id=request_id
        )
        return IngestResult(done, [], "duplicate")

    if len(data) > limits.max_bytes:
        row = new_row("")
        megabytes = limits.max_bytes // (1024 * 1024)
        _fail(conn, row.id, f"The file is larger than the {megabytes} MB limit.", request_id)
        return IngestResult(repo.get_document(conn, row.id), [], "failed")

    data_dir = settings.data_dir
    try:
        store_original(data_dir / "files", data)
    except OSError:  # a full or read-only disk: say so plainly, and make no row for a file not kept
        raise IngestRejected(_NO_ROOM) from None
    row = new_row(f"files/{sha}")

    try:
        if isolate:
            report = isolated_call(_inspect, data, mime, limits, timeout_s=INSPECT_TIMEOUT_S)
        else:
            report = _inspect(data, mime, limits)
    except WorkerTimeout:
        report = {"ok": False, "reason": "Reading the file took too long, so it was stopped."}
    except WorkerFailed:
        report = {"ok": False, "reason": "The file could not be read. It may be damaged or locked."}
    if not report["ok"]:
        _fail(conn, row.id, report["reason"], request_id)
        return IngestResult(repo.get_document(conn, row.id), [], "failed")

    pages: list[PageImage] = []
    page_folder = data_dir / "pages" / str(row.id)
    try:
        page_folder.mkdir(parents=True, exist_ok=True)
        for number, (png, width, height) in enumerate(report["pages"], start=1):
            (page_folder / f"{number}.png").write_bytes(png)
            pages.append(PageImage(number, f"pages/{row.id}/{number}.png", width, height))
    except OSError:  # the upload is kept; uploading it again later starts fresh
        shutil.rmtree(page_folder, ignore_errors=True)
        _fail(conn, row.id, _NO_ROOM, request_id)
        return IngestResult(repo.get_document(conn, row.id), [], "failed")
    document = repo.set_document_info(
        conn, row.id, source_kind=report["source_kind"], page_count=len(pages)
    )
    events.record_event(
        conn,
        EventType.STAGE_FINISHED,
        document_id=row.id,
        stage=Stage.INGEST,
        payload={"pages": len(pages)},
        request_id=request_id,
        duration_ms=int((time.monotonic() - started) * 1000),
    )
    return IngestResult(document, pages, "accepted")
