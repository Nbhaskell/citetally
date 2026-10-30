import pytest
from fastapi.testclient import TestClient

from citetally.api import create_app
from citetally.config import Settings


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings(_env_file=None)))


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


def test_status_marks_features_not_built_yet_as_null(client: TestClient) -> None:
    # Database health, OCR availability, queue depth and last model call arrive in later phases.
    body = client.get("/api/status").json()
    for key in ("database_ok", "ocr_available", "queue_depth", "last_model_call_at"):
        assert key in body
        assert body[key] is None


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
