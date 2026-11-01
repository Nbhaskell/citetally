"""The background worker: queue depth, a crash that must not stop it, and what the log may hold."""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

import pytest

from citetally import pipeline
from citetally.pipeline import Services
from citetally.worker import Worker


class Boom(Exception):
    pass


@pytest.fixture
def seen(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Document ids the stand-in pipeline was asked to process; id 2 always crashes."""
    done: list[int] = []

    def fake_process(conn: Any, document_id: int, services: Any, **kwargs: Any) -> None:
        if document_id == 2:
            raise Boom("secret vendor name and amounts")
        done.append(document_id)

    monkeypatch.setattr(pipeline, "process", fake_process)
    return done


def make_worker() -> Worker:
    return Worker(lambda: sqlite3.connect(":memory:"), lambda: Services.__new__(Services))


def test_drain_processes_what_is_queued_in_order_and_depth_follows(seen: list[int]) -> None:
    worker = make_worker()
    for document_id in (3, 1, 4):
        worker.submit(document_id)
    assert worker.depth == 3
    assert worker.drain() == 3 and seen == [3, 1, 4]
    assert worker.depth == 0 and worker.drain() == 0


def test_a_crash_is_logged_by_id_and_type_only_and_the_next_document_still_runs(
    seen: list[int], caplog: pytest.LogCaptureFixture
) -> None:
    worker = make_worker()
    worker.submit(2)
    worker.submit(5)
    with caplog.at_level(logging.ERROR, logger="citetally.worker"):
        assert worker.drain() == 2
    assert seen == [5] and worker.depth == 0
    assert "document 2" in caplog.text and "Boom" in caplog.text
    assert "secret" not in caplog.text


def test_the_thread_runs_submitted_documents_and_stops_cleanly(seen: list[int]) -> None:
    worker = make_worker()
    worker.start()
    worker.start()  # starting twice does not make a second thread
    worker.submit(7)
    worker.stop()
    assert seen == [7]
    worker.stop()  # stopping when stopped is harmless
