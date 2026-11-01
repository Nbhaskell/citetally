"""FastAPI app: wiring, request ids, local-only protection, and the status route.

The API serves one person on one machine. It is protected the way a local tool should be: only
local host names are answered (against DNS rebinding), and a browser request that carries a foreign
`Origin` and changes something is refused (against another website posting to it). See
docs/TRD.md sections 7 and 9.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware

from citetally import __version__
from citetally import repository as repo
from citetally.api import (
    routes_documents,
    routes_exports,
    routes_review,
    routes_settings,
    routes_vendors,
)
from citetally.api.deps import get_state
from citetally.api.errors import (
    ApiError,
    ErrorResponse,
    error_response,
    install_error_handlers,
    new_request_id,
)
from citetally.api.schemas import StatusResponse
from citetally.api.state import AppState, Database, real_services
from citetally.config import Settings
from citetally.models import DocumentStatus
from citetally.pipeline import Services
from citetally.runtime_settings import apply_overrides
from citetally.worker import Worker

log = logging.getLogger("citetally.api")

LOCAL_HOSTS = ["127.0.0.1", "localhost", "[::1]", "::1"]
_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
_STUCK = (DocumentStatus.RECEIVED, DocumentStatus.READ, DocumentStatus.EXTRACTED)


def _allowed_origins(settings: Settings) -> set[str]:
    return {
        f"http://{host}:{port}"
        for host in ("127.0.0.1", "localhost")
        for port in (settings.port, settings.web_port)
    }


def create_app(
    settings: Settings | None = None,
    *,
    services: Services | None = None,
    autostart_worker: bool = True,
    isolate_ingest: bool = True,
) -> FastAPI:
    """`services` replaces the real OCR and model (tests); `autostart_worker=False` leaves the
    queue for the caller to run with `app.state.citetally.worker.drain()`."""
    settings = settings or Settings()
    database = Database(settings)
    worker = Worker(
        database.connect, (lambda: services) if services else lambda: real_services(state.settings)
    )
    state = AppState(
        settings=settings,
        base_settings=settings,
        database=database,
        worker=worker,
        autostart_worker=autostart_worker,
        isolate_ingest=isolate_ingest,
        services_injected=services is not None,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database.ensure()
        connection = database.connect()
        try:
            state.settings = apply_overrides(state.base_settings, connection)
            for status in _STUCK:  # work interrupted by a restart picks up where it stopped
                for document in repo.list_documents(connection, status):
                    worker.submit(document.id)
        finally:
            connection.close()
        if state.autostart_worker:
            worker.start()
        yield
        worker.stop()

    app = FastAPI(
        title="Citetally",
        version=__version__,
        lifespan=lifespan,
        responses={"default": {"model": ErrorResponse}},
    )
    app.state.citetally = state
    install_error_handlers(app)

    @app.middleware("http")
    async def protect(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = new_request_id(request.headers.get("x-request-id"))
        origin = request.headers.get("origin")
        if request.method in _UNSAFE and origin and origin not in _allowed_origins(settings):
            error = ApiError(403, "foreign_origin", "This request came from another website.")
            return error_response(request, error.status, error.code, error.message)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=LOCAL_HOSTS)

    @app.get("/api/status", response_model=StatusResponse)
    def status(state: Annotated[AppState, Depends(get_state)]) -> StatusResponse:
        return routes_settings.current_status(state)

    app.include_router(routes_documents.router)
    app.include_router(routes_exports.router)
    app.include_router(routes_review.router)
    app.include_router(routes_settings.router)
    app.include_router(routes_vendors.router)
    return app
