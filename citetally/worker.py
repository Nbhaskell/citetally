"""The background worker: documents wait in a queue and are processed one at a time.

One thread, so the local model and OCR are never asked to do two documents at once. The worker
opens its own database connection for each document. A document that crashes the pipeline in a way
`process` does not already handle is logged by id only (CLAUDE.md rule 6); its status stays where it
was and it is picked up again at the next start.
"""

from __future__ import annotations

import logging
import queue
import sqlite3
import threading
from collections.abc import Callable

from citetally import pipeline
from citetally.pipeline import Services

log = logging.getLogger("citetally.worker")

_STOP = -1


class Worker:
    """`submit` a document id; `start` the thread, or `drain` the queue in the calling thread."""

    def __init__(
        self,
        connect: Callable[[], sqlite3.Connection],
        make_services: Callable[[], Services],
    ) -> None:
        self._connect = connect
        self._make_services = make_services
        self._services: Services | None = None
        self._queue: queue.Queue[int] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._busy = False

    @property
    def depth(self) -> int:
        """Documents waiting or being processed."""
        return self._queue.qsize() + (1 if self._busy else 0)

    def services(self) -> Services:
        if self._services is None:
            self._services = self._make_services()
        return self._services

    def submit(self, document_id: int) -> None:
        self._queue.put(document_id)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="citetally-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout_s: float = 5.0) -> None:
        if self._thread is None:
            return
        self._queue.put(_STOP)
        self._thread.join(timeout_s)
        self._thread = None

    def drain(self) -> int:
        """Process everything queued now, in this thread. Returns how many documents ran."""
        done = 0
        while True:
            try:
                document_id = self._queue.get_nowait()
            except queue.Empty:
                return done
            if document_id != _STOP:
                self._process(document_id)
                done += 1

    def _run(self) -> None:
        while True:
            document_id = self._queue.get()
            if document_id == _STOP:
                return
            self._process(document_id)

    def _process(self, document_id: int) -> None:
        self._busy = True
        connection = None
        try:
            connection = self._connect()
            pipeline.process(connection, document_id, self.services())
        except Exception as error:  # the pipeline records its own failures; this is the backstop
            log.error("document %s: worker error (%s)", document_id, type(error).__name__)
        finally:
            if connection is not None:
                connection.close()
            self._busy = False
