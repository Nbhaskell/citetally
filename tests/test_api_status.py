from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from citetally.api import create_app
from citetally.config import Settings
from citetally.pipeline import Services
from citetally.providers import FakeProvider
from citetally.reading.ocr import FakeOcr


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings(
        _env_file=None,
        CITETALLY_DB_PATH=str(tmp_path / "t.db"),
        CITETALLY_DATA_DIR=str(tmp_path / "data"),
    )
    services = Services(settings=settings, ocr=FakeOcr(), provider=FakeProvider(), isolate=False)
    app = create_app(settings, services=services, autostart_worker=False, isolate_ingest=False)
    return TestClient(app, base_url="http://127.0.0.1")


def test_status_reports_configuration(client: TestClient) -> None:
    response = client.get("/api/status")
    assert response.status_code == 200
    body = response.json()
    assert body["app"] == "citetally"
    assert body["model_provider"] == "ollama"
    assert body["text_model"] == "qwen3:8b"
    assert body["ocr_engine"] == "tesseract"
    assert body["hosted_mode"] is False
    assert body["synthetic_data"] is True


def test_status_reports_database_ocr_queue_and_last_model_call(client: TestClient) -> None:
    body = client.get("/api/status").json()
    assert body["database_ok"] is True
    assert body["ocr_available"] is True
    assert body["queue_depth"] == 0
    assert body["last_model_call_at"] is None  # nothing has been read yet


def test_status_exposes_only_the_documented_fields(client: TestClient) -> None:
    assert set(client.get("/api/status").json()) == {
        "app",
        "version",
        "model_provider",
        "text_model",
        "vision_model",
        "ocr_engine",
        "hosted_mode",
        "synthetic_data",
        "database_ok",
        "ocr_available",
        "queue_depth",
        "last_model_call_at",
    }


def test_an_unreachable_database_is_reported_not_raised(tmp_path: Path) -> None:
    blocker = tmp_path / "not_a_folder"
    blocker.write_text("a file where the database folder should be", encoding="utf-8")
    settings = Settings(
        _env_file=None,
        CITETALLY_DB_PATH=str(blocker / "t.db"),
        CITETALLY_DATA_DIR=str(tmp_path / "data"),
    )
    client = TestClient(create_app(settings, autostart_worker=False), base_url="http://127.0.0.1")
    assert client.get("/api/status").json()["database_ok"] is False
