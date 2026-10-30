"""Ingest: files are judged by their bytes, limited, hashed, stored by hash and rendered."""

import hashlib
import io
import os
import sqlite3
import time
from pathlib import Path

import pytest
from PIL import Image
from reportlab.pdfgen.canvas import Canvas

from citetally import db, ingest
from citetally import repository as repo
from citetally.config import Settings
from citetally.models import DocumentStatus as S
from citetally.models import SourceKind, Stage


def settings(tmp_path: Path, **overrides: int) -> Settings:
    values: dict[str, object] = {"CITETALLY_DATA_DIR": str(tmp_path / "data"), **overrides}
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = db.connect(":memory:")
    db.migrate(connection)
    return connection


def text_pdf(pages: int = 1, words_per_page: int = 40) -> bytes:
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=(612, 792), invariant=1)
    for number in range(pages):
        for line in range(words_per_page // 5):
            canvas.drawString(72, 700 - line * 14, f"Invoice line {number}-{line} total 12.50 USD")
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def blank_pdf(pages: int = 1) -> bytes:
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=(612, 792), invariant=1)
    for _ in range(pages):
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def scanned_pdf(size: tuple[int, int] = (850, 1100)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, "PDF", resolution=100.0)
    return buffer.getvalue()


def image_bytes(
    fmt: str, size: tuple[int, int] = (400, 300), mode: str = "RGB", **kw: object
) -> bytes:
    buffer = io.BytesIO()
    colours: dict[str, object] = {
        "L": 128, "P": 128, "LA": (128, 255), "RGBA": (200, 180, 160, 255), "RGB": (200, 180, 160),
    }  # fmt: skip
    Image.new(mode, size, colours[mode]).save(buffer, fmt, **kw)  # type: ignore[arg-type]
    return buffer.getvalue()


# ---- type by content --------------------------------------------------------------------------


def test_type_comes_from_the_leading_bytes_only() -> None:
    assert ingest.detect_type(text_pdf()) == "application/pdf"
    assert ingest.detect_type(image_bytes("PNG")) == "image/png"
    assert ingest.detect_type(image_bytes("JPEG")) == "image/jpeg"


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"%PD",
        b"MZ\x90\x00\x03",  # a Windows program
        b"<html><script>alert(1)</script></html>",
        b"GIF89a\x01\x00",
        b"PK\x03\x04",  # a zip
        b"\x89PNG",  # truncated signature
        b"\xff\xd8",  # truncated JPEG signature
        b"junk" + b"%PDF-1.7",  # the PDF marker is not at the start
        b"\n%PDF-1.7",
    ],
)
def test_other_content_is_not_a_supported_type(data: bytes) -> None:
    assert ingest.detect_type(data) is None


def test_an_unsupported_file_is_rejected_without_a_database_row(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    with pytest.raises(ingest.IngestRejected, match="PDF, PNG or JPEG"):
        ingest.ingest(
            conn, b"MZ\x90\x00 program", "invoice.pdf", settings=settings(tmp_path), isolate=False
        )
    assert repo.list_documents(conn) == []
    assert not (tmp_path / "data").exists()  # nothing was written to disk either


def test_the_declared_name_and_extension_do_not_matter(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    result = ingest.ingest(
        conn, image_bytes("PNG"), "photo.pdf", settings=settings(tmp_path), isolate=False
    )
    assert result.document.mime_type == "image/png"
    assert result.document.source_kind is SourceKind.IMAGE


# ---- accepted files ---------------------------------------------------------------------------


def test_a_digital_pdf_is_stored_by_hash_and_rendered_to_page_images(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    data = text_pdf(pages=2)
    result = ingest.ingest(
        conn, data, "April invoice.pdf", settings=settings(tmp_path), isolate=False
    )
    document = result.document
    sha = hashlib.sha256(data).hexdigest()
    assert result.outcome == "accepted"
    assert document.status is S.RECEIVED and document.file_sha256 == sha
    assert document.source_kind is SourceKind.DIGITAL_PDF and document.page_count == 2
    assert document.original_filename == "April invoice.pdf"
    assert document.stored_path == f"files/{sha}"
    assert (tmp_path / "data" / "files" / sha).read_bytes() == data
    assert [p.page_number for p in result.pages] == [1, 2]
    for page in result.pages:
        assert page.path == f"pages/{document.id}/{page.page_number}.png"
        with Image.open(tmp_path / "data" / page.path) as image:
            assert image.format == "PNG" and image.size == (page.width_px, page.height_px)
    assert result.pages[0].width_px == round(612 * ingest.RENDER_DPI / 72)


def test_a_pdf_without_text_is_a_scanned_pdf(conn: sqlite3.Connection, tmp_path: Path) -> None:
    result = ingest.ingest(
        conn, scanned_pdf(), "scan.pdf", settings=settings(tmp_path), isolate=False
    )
    assert result.document.source_kind is SourceKind.SCANNED_PDF
    blank = ingest.ingest(
        conn, blank_pdf(), "blank.pdf", settings=settings(tmp_path), isolate=False
    )
    assert blank.document.source_kind is SourceKind.SCANNED_PDF


def test_too_little_text_does_not_make_a_digital_pdf(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    sparse = text_pdf(words_per_page=5)  # one short line, under the 80 character minimum
    result = ingest.ingest(conn, sparse, "sparse.pdf", settings=settings(tmp_path), isolate=False)
    assert result.document.source_kind is SourceKind.SCANNED_PDF


def test_jpeg_and_png_photos_become_one_page_png_images(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    for fmt in ("JPEG", "PNG"):
        data = image_bytes(fmt, size=(640, 480))
        result = ingest.ingest(
            conn, data, f"photo.{fmt.lower()}", settings=settings(tmp_path), isolate=False
        )
        assert result.document.source_kind is SourceKind.IMAGE and result.document.page_count == 1
        assert (result.pages[0].width_px, result.pages[0].height_px) == (640, 480)


def test_exif_orientation_is_applied_so_the_page_is_upright(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    image = Image.new("RGB", (200, 100), "white")
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 degrees to display
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", exif=exif)
    result = ingest.ingest(
        conn, buffer.getvalue(), "phone.jpg", settings=settings(tmp_path), isolate=False
    )
    assert (result.pages[0].width_px, result.pages[0].height_px) == (100, 200)


@pytest.mark.parametrize("mode", ["RGBA", "P", "L", "LA"])
def test_pngs_in_any_colour_mode_are_saved_as_plain_rgb(
    conn: sqlite3.Connection, tmp_path: Path, mode: str
) -> None:
    result = ingest.ingest(
        conn, image_bytes("PNG", mode=mode), "x.png", settings=settings(tmp_path), isolate=False
    )
    with Image.open(tmp_path / "data" / result.pages[0].path) as page:
        assert page.mode == "RGB"


def test_ingest_leaves_stage_events_with_only_the_page_count(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    result = ingest.ingest(
        conn, text_pdf(), "Secret Vendor INV-1.pdf", settings=settings(tmp_path), isolate=False
    )
    events = repo.list_audit_events(conn, result.document.id)
    assert [e.event_type for e in events] == ["stage_started", "stage_finished"]
    assert all(e.stage is Stage.INGEST for e in events)
    assert events[-1].payload == '{"pages": 1}'
    assert "Secret Vendor" not in " ".join(e.payload for e in events)


# ---- hashing, storage and duplicates ----------------------------------------------------------


def test_the_same_file_twice_is_a_duplicate_and_is_stored_once(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    data = text_pdf()
    first = ingest.ingest(conn, data, "a.pdf", settings=settings(tmp_path), isolate=False)
    second = ingest.ingest(conn, data, "copy of a.pdf", settings=settings(tmp_path), isolate=False)
    assert second.outcome == "duplicate" and second.pages == []
    assert (
        second.document.status is S.DUPLICATE and second.document.duplicate_of == first.document.id
    )
    assert second.document.stored_path == first.document.stored_path
    assert len(list((tmp_path / "data" / "files").iterdir())) == 1
    assert not (tmp_path / "data" / "pages" / str(second.document.id)).exists()


def test_a_file_that_failed_before_is_not_a_duplicate_of_the_failure(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    data = text_pdf(pages=3)
    first = ingest.ingest(
        conn, data, "a.pdf", settings=settings(tmp_path, CITETALLY_MAX_PAGES=2), isolate=False
    )
    assert first.outcome == "failed"
    again = ingest.ingest(
        conn, data, "a.pdf", settings=settings(tmp_path, CITETALLY_MAX_PAGES=5), isolate=False
    )
    assert again.outcome == "accepted" and again.document.status is S.RECEIVED


def test_stored_files_are_written_whole_and_never_overwritten(tmp_path: Path) -> None:
    folder = tmp_path / "files"
    path = ingest.store_original(folder, b"first")
    assert path.name == hashlib.sha256(b"first").hexdigest() and path.read_bytes() == b"first"
    before = path.stat().st_mtime_ns
    assert ingest.store_original(folder, b"first") == path
    assert path.stat().st_mtime_ns == before
    assert [p.name for p in folder.iterdir()] == [path.name]  # no temporary files left behind


# ---- limits and failures ----------------------------------------------------------------------


def failed(conn: sqlite3.Connection, result: ingest.IngestResult) -> tuple[str, str]:
    document = repo.get_document(conn, result.document.id)
    assert document.status is S.FAILED and document.failure_stage is Stage.INGEST
    assert result.outcome == "failed" and result.pages == []
    return document.failure_message or "", document.stored_path


def test_a_file_over_the_size_limit_fails_and_is_not_stored(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    data = text_pdf() + b" " * (1024 * 1024)
    result = ingest.ingest(
        conn, data, "big.pdf", settings=settings(tmp_path, CITETALLY_MAX_FILE_MB=1), isolate=False
    )
    message, stored = failed(conn, result)
    assert "1 MB" in message and "larger" in message.lower()
    assert stored == "" and not (tmp_path / "data" / "files").exists()


def test_a_pdf_with_too_many_pages_fails_before_anything_is_rendered(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    result = ingest.ingest(
        conn,
        blank_pdf(pages=4),
        "long.pdf",
        settings=settings(tmp_path, CITETALLY_MAX_PAGES=3),
        isolate=False,
    )
    message, _ = failed(conn, result)
    assert "4 pages" in message and "3" in message
    assert not (tmp_path / "data" / "pages").exists()


def test_an_image_over_the_pixel_cap_fails(conn: sqlite3.Connection, tmp_path: Path) -> None:
    result = ingest.ingest(
        conn,
        image_bytes("PNG", size=(1200, 1000)),
        "huge.png",
        settings=settings(tmp_path, CITETALLY_MAX_IMAGE_PIXELS=1_000_000),
        isolate=False,
    )
    message, _ = failed(conn, result)
    assert "pixels" in message


def test_a_decompression_bomb_is_refused_from_its_header(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    """A tiny file that claims to be enormous must never be decoded."""
    bomb = io.BytesIO()
    Image.new("1", (16000, 16000), 0).save(bomb, "PNG", optimize=False, compress_level=9)
    assert len(bomb.getvalue()) < 1_000_000
    started = time.monotonic()
    result = ingest.ingest(
        conn, bomb.getvalue(), "bomb.png", settings=settings(tmp_path), isolate=False
    )
    message, _ = failed(conn, result)
    assert "pixels" in message and time.monotonic() - started < 5


def test_a_pdf_page_with_an_enormous_page_box_is_refused(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=(14000, 14000), invariant=1)
    canvas.drawString(100, 100, "tiny file, huge page")
    canvas.save()
    result = ingest.ingest(
        conn, buffer.getvalue(), "poster.pdf", settings=settings(tmp_path), isolate=False
    )
    message, _ = failed(conn, result)
    assert "too large" in message and "page" in message


@pytest.mark.parametrize(
    "data",
    [
        b"%PDF-1.7\nthis is not really a pdf",
        b"%PDF-1.4\n" + os.urandom(2000),
        b"\x89PNG\r\n\x1a\n" + os.urandom(500),
        b"\xff\xd8\xff\xe0" + os.urandom(500),
    ],
)
def test_a_damaged_file_with_a_valid_signature_fails_with_a_plain_reason(
    conn: sqlite3.Connection, tmp_path: Path, data: bytes
) -> None:
    result = ingest.ingest(conn, data, "broken", settings=settings(tmp_path), isolate=False)
    message, _ = failed(conn, result)
    assert "could not be read" in message
    assert "Traceback" not in message and "Error" not in message


def test_a_password_protected_pdf_fails_with_a_plain_reason(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    from reportlab.lib.pdfencrypt import StandardEncryption

    buffer = io.BytesIO()
    canvas = Canvas(buffer, invariant=1, encrypt=StandardEncryption("secret", canPrint=0))
    canvas.drawString(100, 100, "locked")
    canvas.save()
    result = ingest.ingest(
        conn, buffer.getvalue(), "locked.pdf", settings=settings(tmp_path), isolate=False
    )
    message, _ = failed(conn, result)
    assert "could not be read" in message


def test_a_failed_document_can_be_retried(conn: sqlite3.Connection, tmp_path: Path) -> None:
    result = ingest.ingest(
        conn, b"%PDF-1.7 broken", "x.pdf", settings=settings(tmp_path), isolate=False
    )
    assert repo.change_status(conn, result.document.id, S.RECEIVED).status is S.RECEIVED


# ---- filenames --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "shown"),
    [
        ("invoice.pdf", "invoice.pdf"),
        ("April invoice (final).pdf", "April invoice (final).pdf"),
        ("../../etc/passwd", "passwd"),
        ("..\\..\\Windows\\system32\\config", "config"),
        (
            "C:" + "\\Users\\" + "someone" + "\\scan.pdf",
            "scan.pdf",
        ),  # built from parts: see the PII guard
        ("a\x00b.pdf", "ab.pdf"),
        ("evil\u202egnp.exe", "evilgnp.exe"),  # a right-to-left override can fake an extension
        ("tab\tname\n.pdf", "tabname.pdf"),
        ("", "unnamed"),
        ("   ", "unnamed"),
        ("...", "unnamed"),
        ("x" * 400 + ".pdf", "x" * 196 + ".pdf"),
    ],
)
def test_filenames_are_cleaned_for_display_and_never_used_as_paths(raw: str, shown: str) -> None:
    assert ingest.sanitize_filename(raw) == shown


def test_a_hostile_filename_changes_nothing_on_disk(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    result = ingest.ingest(
        conn, text_pdf(), "../../outside.pdf", settings=settings(tmp_path), isolate=False
    )
    assert result.document.original_filename == "outside.pdf"
    written = {p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file()}
    assert all(str(p).startswith("data") for p in written)
    assert not (tmp_path.parent / "outside.pdf").exists()


# ---- the isolated worker ----------------------------------------------------------------------


def _current_pid() -> int:
    return os.getpid()


def _sleep_forever(*_: object) -> None:
    time.sleep(600)


def _explode() -> None:
    raise RuntimeError("secret vendor text inside an error")


def _die() -> None:
    os._exit(3)  # what a crash in a native library looks like from outside


def test_the_worker_runs_in_another_process() -> None:
    assert ingest.isolated_call(_current_pid, timeout_s=30) != os.getpid()


def test_a_worker_that_hangs_is_killed_at_the_timeout() -> None:
    started = time.monotonic()
    with pytest.raises(ingest.WorkerTimeout):
        ingest.isolated_call(_sleep_forever, timeout_s=2)
    assert time.monotonic() - started < 15


def test_a_worker_that_crashes_or_raises_is_reported_without_its_message() -> None:
    with pytest.raises(ingest.WorkerFailed) as raised:
        ingest.isolated_call(_explode, timeout_s=30)
    assert "secret vendor text" not in str(raised.value)
    with pytest.raises(ingest.WorkerFailed):
        ingest.isolated_call(_die, timeout_s=30)


def test_ingest_uses_the_isolated_worker_by_default(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    result = ingest.ingest(conn, image_bytes("JPEG"), "photo.jpg", settings=settings(tmp_path))
    assert result.outcome == "accepted" and result.document.page_count == 1


def test_a_hung_parser_fails_the_document_instead_of_the_server(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ingest, "_inspect", _sleep_forever)
    monkeypatch.setattr(ingest, "INSPECT_TIMEOUT_S", 2.0)
    result = ingest.ingest(conn, text_pdf(), "hang.pdf", settings=settings(tmp_path))
    message, _ = failed(conn, result)
    assert "took too long" in message
