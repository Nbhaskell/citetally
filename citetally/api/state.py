"""What the routes share: the database, the worker and the settings."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass

from citetally import db
from citetally.config import Settings
from citetally.models import ExtractMode
from citetally.pipeline import Services
from citetally.providers import build_provider, build_vision_provider
from citetally.reading.ocr import TesseractOcr, find_tesseract
from citetally.worker import Worker


class Database:
    """Opens connections to the database file, migrating it the first time it is needed."""

    def __init__(self, settings: Settings) -> None:
        self._path = settings.db_path
        self._data_dir = settings.data_dir
        self._lock = threading.Lock()
        self._ready = False

    def ensure(self) -> None:
        with self._lock:
            if self._ready:
                return
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._data_dir.mkdir(parents=True, exist_ok=True)
            connection = db.connect(self._path)
            try:
                db.migrate(connection)
                db.seed_categories(connection)
            finally:
                connection.close()
            self._ready = True

    def connect(self) -> sqlite3.Connection:
        self.ensure()
        return db.connect(self._path, any_thread=True)


def real_services(settings: Settings) -> Services:
    """The Tesseract and Ollama pipeline. Built when the first document is processed."""
    ocr = TesseractOcr(find_tesseract(settings.tesseract_cmd) or "")
    return Services(
        settings=settings,
        ocr=ocr,
        provider=build_provider(settings),
        extract_mode=(
            ExtractMode.TEXT_AND_IMAGE
            if settings.extract_mode == "text_and_image"
            else ExtractMode.TEXT_ONLY
        ),
        vision_provider=build_vision_provider(settings),
        automatic_pictures=settings.extract_mode == "auto",
    )


@dataclass
class AppState:
    settings: Settings  # in force: the environment's, with saved changes laid over
    base_settings: Settings  # the environment's alone
    database: Database
    worker: Worker
    autostart_worker: bool = True
    isolate_ingest: bool = True
    services_injected: bool = False
