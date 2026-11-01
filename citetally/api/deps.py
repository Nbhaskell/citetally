"""Dependencies the routes share: the app state, a connection for the request, its request id."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from citetally.api.errors import request_id_of
from citetally.api.state import AppState


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.citetally
    return state


def get_conn(state: Annotated[AppState, Depends(get_state)]) -> Iterator[sqlite3.Connection]:
    connection = state.database.connect()
    try:
        yield connection
    finally:
        connection.close()


def get_request_id(request: Request) -> str:
    return request_id_of(request)


State = Annotated[AppState, Depends(get_state)]
Conn = Annotated[sqlite3.Connection, Depends(get_conn)]
RequestId = Annotated[str, Depends(get_request_id)]
