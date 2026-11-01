"""One error shape for the whole API: {"error": {"code", "message", "request_id"}}.

Messages are written for the person using the screen and never hold document text, a model reply
or a stack trace. Anything unexpected becomes a plain 500 and is logged by type only.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from citetally import repository as repo
from citetally.statemachine import IllegalTransition

log = logging.getLogger("citetally.api")

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class ApiError(Exception):
    """A refusal the routes raise on purpose."""

    def __init__(
        self, status: int, code: str, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def new_request_id(incoming: str | None = None) -> str:
    """The caller's X-Request-ID when it is a plain token, otherwise a fresh one."""
    if incoming and _SAFE_ID.match(incoming):
        return incoming
    return uuid.uuid4().hex[:16]


def request_id_of(request: Request) -> str:
    return getattr(request.state, "request_id", None) or new_request_id()


def error_response(
    request: Request, status: int, code: str, message: str, details: dict[str, Any] | None = None
) -> JSONResponse:
    body = ErrorBody(code=code, message=message, request_id=request_id_of(request), details=details)
    return JSONResponse(
        {"error": body.model_dump(exclude_none=True)},
        status_code=status,
        headers={"X-Request-ID": body.request_id},
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(request: Request, error: ApiError) -> JSONResponse:
        return error_response(request, error.status, error.code, error.message, error.details)

    @app.exception_handler(repo.NotFound)
    async def not_found(request: Request, error: repo.NotFound) -> JSONResponse:
        return error_response(request, 404, "not_found", str(error))

    @app.exception_handler(repo.ApprovalBlocked)
    async def blocked(request: Request, error: repo.ApprovalBlocked) -> JSONResponse:
        codes = [code.value for code in error.codes]
        return error_response(request, 409, "approval_blocked", str(error), {"unresolved": codes})

    @app.exception_handler(repo.RepositoryError)
    async def refused(request: Request, error: repo.RepositoryError) -> JSONResponse:
        return error_response(request, 422, "rule_violation", str(error))

    @app.exception_handler(IllegalTransition)
    async def illegal(request: Request, error: IllegalTransition) -> JSONResponse:
        return error_response(request, 409, "illegal_transition", str(error))

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, error: RequestValidationError) -> JSONResponse:
        # Names of the fields that failed, never the values sent.
        where = sorted(
            {".".join(str(p) for p in e["loc"][1:]) or str(e["loc"][0]) for e in error.errors()}
        )
        return error_response(
            request, 422, "invalid_request", "The request is not valid.", {"fields": where}
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(error.status_code, "http_error")
        message = "That address does not exist." if error.status_code == 404 else "Not allowed."
        return error_response(request, error.status_code, code, message)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, error: Exception) -> JSONResponse:
        log.error("request %s: unexpected %s", request_id_of(request), type(error).__name__)
        return error_response(request, 500, "internal_error", "Something went wrong on our side.")
