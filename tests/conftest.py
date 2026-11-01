"""Fixtures for the API tests: settings in a temporary folder, the app on fakes, a client."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from citetally.api import create_app
from citetally.config import Settings
from citetally.pipeline import Services
from citetally.providers import FakeProvider
from citetally.reading.ocr import FakeOcr
from tests.api_support import HOST


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        CITETALLY_DB_PATH=str(tmp_path / "t.db"),
        CITETALLY_DATA_DIR=str(tmp_path / "data"),
        CITETALLY_MAX_FILE_MB=1,
    )


@pytest.fixture
def app(settings: Settings) -> Any:
    services = Services(
        settings=settings,
        ocr=FakeOcr(),
        provider=FakeProvider(),
        isolate=False,
        today=date(2026, 6, 15),
    )
    return create_app(settings, services=services, autostart_worker=False, isolate_ingest=False)


@pytest.fixture
def client(app: Any) -> Iterator[TestClient]:
    with TestClient(app, base_url=HOST) as test_client:
        yield test_client
