"""RapidOCR as an optional engine: result conversion, failures, the setting and the reading plan.

None of these tests needs RapidOCR installed: the engine is replaced by a stub that returns the
shape the package returns.
"""

import json
import pickle
import sqlite3
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image
from pydantic import ValidationError

from citetally import db, events
from citetally.config import Settings
from citetally.models import EventType, Stage
from citetally.pipeline import _extra_readings, _reading_plan
from citetally.reading import rapid_ocr
from citetally.reading.ocr import FakeOcr, OcrError, OcrUnavailable, fake_page


def stub(result: Any) -> Any:
    def engine(array: Any, **options: Any) -> Any:
        assert options == {"return_word_box": True}
        assert array.shape[2] == 3
        return result

    return engine


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = db.connect(":memory:")
    db.migrate(connection)
    connection.execute(
        "INSERT INTO documents (original_filename, stored_path, file_sha256, mime_type, "
        "size_bytes, created_at, updated_at) VALUES ('a.pdf', 'x', 'h', 'application/pdf', 1, "
        "'t', 't')"
    )
    return connection


@pytest.fixture(autouse=True)
def forget_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rapid_ocr, "_engine", None)


def test_words_become_boxes_as_fractions_with_a_confidence_out_of_100() -> None:
    lines = [
        (
            ("Total", 0.9, [[100, 200], [400, 200], [400, 240], [100, 240]]),
            ("$12.50", 0.5, [[420, 200], [600, 200], [600, 240], [420, 240]]),
        ),
        (("", 1.0, [[0, 0], [5, 0], [5, 5], [0, 5]]),),
        (("flat", 1.0, [[10, 10], [10, 10], [10, 10], [10, 10]]),),
    ]
    words = rapid_ocr.words_from_result(lines, 1000, 400)
    assert [w.t for w in words] == ["Total", "$12.50"]
    assert (words[0].x0, words[0].y0, words[0].x1, words[0].y1) == pytest.approx(
        (0.1, 0.5, 0.4, 0.6)
    )
    assert words[0].c == pytest.approx(90.0) and words[1].c == pytest.approx(50.0)


def test_a_box_outside_the_image_is_clamped() -> None:
    (word,) = rapid_ocr.words_from_result(
        [(("Edge", 1.0, [[-20, -5], [1100, -5], [1100, 420], [-20, 420]]),)], 1000, 400
    )
    assert (word.x0, word.y0, word.x1, word.y1) == (0.0, 0.0, 1.0, 1.0)


def test_read_page_returns_words_and_their_mean_confidence(monkeypatch: pytest.MonkeyPatch) -> None:
    result = SimpleNamespace(
        word_results=[
            (
                ("Net", 1.0, [[0, 0], [50, 0], [50, 20], [0, 20]]),
                ("30", 0.8, [[60, 0], [90, 0], [90, 20], [60, 20]]),
            )
        ]
    )
    monkeypatch.setattr(rapid_ocr, "_engine", stub(result))
    page = rapid_ocr.RapidOcr().read_page(Image.new("L", (100, 40)), psm=6)
    assert [w.t for w in page.words] == ["Net", "30"]
    assert page.mean_confidence == pytest.approx(90.0)


def test_a_blank_page_has_no_words_and_no_confidence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rapid_ocr, "_engine", stub(SimpleNamespace(word_results=None)))
    page = rapid_ocr.RapidOcr().read_page(Image.new("L", (100, 40)))
    assert page.words == [] and page.mean_confidence is None


def test_an_engine_failure_is_an_ocr_error_that_carries_no_page_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(array: Any, **options: Any) -> Any:
        raise RuntimeError("secret invoice text ACME-1234")

    monkeypatch.setattr(rapid_ocr, "_engine", broken)
    with pytest.raises(OcrError) as caught:
        rapid_ocr.RapidOcr().read_page(Image.new("L", (10, 10)))
    assert "ACME" not in str(caught.value)


def test_without_the_package_reading_says_the_engine_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(name: str) -> Any:
        raise ImportError(name)

    monkeypatch.setattr("citetally.reading.rapid_ocr.importlib.import_module", missing)
    with pytest.raises(OcrUnavailable):
        rapid_ocr.RapidOcr().read_page(Image.new("L", (10, 10)))


def test_the_engine_object_can_be_sent_to_another_process() -> None:
    assert pickle.loads(pickle.dumps(rapid_ocr.RapidOcr())).name == "rapidocr"


def test_the_engine_can_be_chosen_and_an_unknown_one_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CITETALLY_OCR_ENGINE", "rapidocr")
    assert Settings(_env_file=None).ocr_engine == "rapidocr"
    monkeypatch.setenv("CITETALLY_OCR_ENGINE", "nothing")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_the_audit_event_accepts_the_engine_name(conn: sqlite3.Connection) -> None:
    event = events.record_event(
        conn,
        EventType.STAGE_FINISHED,
        document_id=1,
        stage=Stage.READ,
        payload={"read_method": "ocr", "ocr_engine": "rapidocr", "pages": 1},
        request_id="req-1",
        duration_ms=5,
    )
    assert json.loads(event.payload)["ocr_engine"] == "rapidocr"


def test_tesseract_keeps_three_readings_and_rapidocr_two() -> None:
    assert len(_reading_plan("tesseract", 3)) == 3
    assert len(_reading_plan("fake", 2)) == 2
    assert len(_reading_plan("rapidocr", 1)) == 1
    assert len(_reading_plan("rapidocr", 2)) == 2
    assert len(_reading_plan("rapidocr", 3)) == 2


def test_the_second_rapidocr_reading_is_of_the_page_as_it_came_capped_in_size() -> None:
    engine = FakeOcr([fake_page(["Total 12.50"])])
    steps = _reading_plan("rapidocr", 2)[1:]
    (words,) = _extra_readings(engine, Image.new("RGB", (5000, 2000), "white"), steps)
    assert [w.t for w in words] == ["Total", "12.50"]
    assert engine.calls == [(3400, 1360)]
