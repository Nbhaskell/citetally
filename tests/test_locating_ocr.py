"""A second OCR engine that only helps locate values (D-075): the page text, the words and the
read-quality confidence stay the first engine's, and the second engine's words are added as
separate readings for grounding."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from citetally import db, events
from citetally.api import create_app, routes_settings
from citetally.config import Settings
from citetally.models import EventType, Stage
from citetally.pipeline import _read_job, _ReadJob
from citetally.reading.ocr import FakeOcr, OcrPage, OcrUnavailable, fake_page


def job(tmp_path: Path, ocr: FakeOcr, locator: FakeOcr | None, readings: int = 1) -> _ReadJob:
    path = tmp_path / "page.png"
    Image.new("RGB", (1000, 1400), "white").save(path)
    return _ReadJob(path, [path], False, 80, ocr, readings, locator)


def rapid(page: OcrPage | None = None, error: Exception | None = None) -> FakeOcr:
    engine = FakeOcr([page] if page else [], error=error)  # type: ignore[arg-type]
    engine.name = "rapidocr"
    return engine


def test_the_second_engines_words_are_extra_readings_not_page_text(tmp_path: Path) -> None:
    tesseract = FakeOcr([fake_page(["Date 03/14/2026", "Total 12.50"], 62.0)])
    locator = rapid(fake_page(["Date 03.14.2026", "Total $12.50"], 99.0))
    result = _read_job(job(tmp_path, tesseract, locator))
    (page,) = result.pages
    assert page.engine == "fake+rapidocr"
    assert "03.14.2026" not in page.text and "03/14/2026" in page.text
    assert [w.t for w in page.words] == ["Date", "03/14/2026", "Total", "12.50"]
    assert page.mean_confidence == pytest.approx(62.0)
    texts = [[w.t for w in reading] for reading in page.alt_words]
    assert ["Date", "03/14/2026", "Total", "12.50"] in texts
    assert ["Date", "03.14.2026", "Total", "$12.50"] in texts


def test_a_second_engine_is_read_as_often_as_the_setting_says(tmp_path: Path) -> None:
    tesseract = FakeOcr([fake_page(["Total 12.50"])])
    locator = rapid(fake_page(["Total 12.50"]))
    _read_job(job(tmp_path, tesseract, locator, readings=2))
    assert len(locator.calls) == 2 and len(tesseract.calls) == 2
    one = rapid(fake_page(["Total 12.50"]))
    _read_job(job(tmp_path, FakeOcr([fake_page(["Total 12.50"])]), one, readings=1))
    assert len(one.calls) == 1


def test_without_a_second_engine_nothing_changes(tmp_path: Path) -> None:
    (page,) = _read_job(job(tmp_path, FakeOcr([fake_page(["Total 12.50"], 80.0)]), None)).pages
    assert page.engine == "fake" and page.alt_words == [] and page.mean_confidence == 80.0


def test_a_second_engine_that_fails_leaves_the_first_reading_alone(tmp_path: Path) -> None:
    tesseract = FakeOcr([fake_page(["Total 12.50"], 80.0)])
    result = _read_job(job(tmp_path, tesseract, rapid(error=OcrUnavailable("not installed"))))
    assert result.error is None
    (page,) = result.pages
    assert page.engine == "fake" and page.alt_words == [] and "12.50" in page.text


def test_the_setting_accepts_the_second_engine_and_refuses_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert Settings(_env_file=None).ocr_locator == "none"
    monkeypatch.setenv("CITETALLY_OCR_LOCATOR", "rapidocr")
    assert Settings(_env_file=None).ocr_locator == "rapidocr"
    monkeypatch.setenv("CITETALLY_OCR_LOCATOR", "paddle")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_the_combined_name_is_a_known_audit_value() -> None:
    connection = db.connect(":memory:")
    db.migrate(connection)
    connection.execute(
        "INSERT INTO documents (original_filename, stored_path, file_sha256, mime_type, "
        "size_bytes, created_at, updated_at) VALUES ('a.pdf', 'x', 'h', 'application/pdf', 1, "
        "'t', 't')"
    )
    event = events.record_event(
        connection,
        EventType.STAGE_FINISHED,
        document_id=1,
        stage=Stage.READ,
        payload={"read_method": "ocr", "ocr_engine": "tesseract+rapidocr", "pages": 1},
        request_id="req-1",
        duration_ms=5,
    )
    assert json.loads(event.payload)["ocr_engine"] == "tesseract+rapidocr"


def test_status_reports_the_ocr_as_missing_when_the_second_engine_is_not_installed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = Settings(
        _env_file=None,
        CITETALLY_DB_PATH=str(tmp_path / "t.db"),
        CITETALLY_DATA_DIR=str(tmp_path / "data"),
        CITETALLY_OCR_LOCATOR="rapidocr",
    )
    monkeypatch.setattr(routes_settings, "find_tesseract", lambda _command: "tesseract")
    app = create_app(settings, autostart_worker=False, isolate_ingest=False)
    client = TestClient(app, base_url="http://127.0.0.1")
    monkeypatch.setattr(routes_settings, "rapidocr_installed", lambda: False)
    assert client.get("/api/status").json()["ocr_available"] is False
    monkeypatch.setattr(routes_settings, "rapidocr_installed", lambda: True)
    assert client.get("/api/status").json()["ocr_available"] is True


def test_a_second_engine_with_rapidocr_as_the_first_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CITETALLY_OCR_ENGINE", "rapidocr")
    monkeypatch.setenv("CITETALLY_OCR_LOCATOR", "rapidocr")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
