"""Exports: preview, create, history and download (docs/TRD.md section 7).

Creating an export writes a CSV file and marks the included entries exported. Nothing is sent
anywhere; the person downloads the file and imports it themselves.
"""

from __future__ import annotations

import hashlib

from fastapi import APIRouter
from fastapi.responses import FileResponse

from citetally import export as exporting
from citetally import repository as repo
from citetally.api.deps import Conn, RequestId, State
from citetally.api.errors import ApiError
from citetally.api.schemas import ExportCreate, ExportCreated, ExportOut, ExportPreview
from citetally.models import Export, ExportProfile

router = APIRouter(prefix="/api", tags=["exports"])


def export_out(export: Export) -> ExportOut:
    return ExportOut(**export.model_dump(), download_url=f"/api/exports/{export.id}/download")


@router.get("/exports/preview", response_model=ExportPreview)
def preview(
    conn: Conn, state: State, profile: ExportProfile, include_exported: bool = False
) -> ExportPreview:
    """What an export would hold now: counts, totals, dates and the first few rows."""
    found = exporting.preview(conn, state.settings, profile, include_exported=include_exported)
    return ExportPreview(
        entry_count=found.entry_count,
        row_count=found.row_count,
        totals=found.totals,
        first_date=found.first_date,
        last_date=found.last_date,
        skipped_already_exported=found.skipped_exported,
        columns=list(found.columns),
        sample=found.sample,
    )


@router.post("/exports", response_model=ExportCreated, status_code=201)
def create_export(
    body: ExportCreate, conn: Conn, state: State, request_id: RequestId
) -> ExportCreated:
    created = exporting.create_export(
        conn,
        state.settings,
        body.profile,
        entry_ids=body.entry_ids,
        include_exported=body.include_exported,
        request_id=request_id,
    )
    return ExportCreated(
        export=export_out(created.export), skipped_already_exported=created.skipped_exported
    )


@router.get("/exports", response_model=list[ExportOut])
def list_exports(conn: Conn) -> list[ExportOut]:
    return [export_out(e) for e in repo.list_exports(conn)]


@router.get("/exports/{export_id}/download")
def download(export_id: int, conn: Conn, state: State) -> FileResponse:
    export = repo.get_export(conn, export_id)
    path = exporting.export_path(state.settings, export.id)
    if not path.is_file():
        raise repo.NotFound(f"The file for export {export_id} is missing")
    if hashlib.sha256(path.read_bytes()).hexdigest() != export.file_sha256:
        raise ApiError(
            409,
            "export_file_changed",
            "This file no longer matches what was exported, so it was not sent. "
            "Make a new export instead.",
        )
    return FileResponse(
        path,
        media_type="text/csv; charset=utf-8",
        filename=export.file_name,
        headers={"Cache-Control": "no-store"},
    )
