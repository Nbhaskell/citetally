"""Insights, settings and the self-test (docs/TRD.md section 7)."""

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Query

from citetally import __version__, runtime_settings
from citetally import insights as insight_queries
from citetally.api.deps import Conn, State
from citetally.api.errors import ApiError
from citetally.api.schemas import (
    AgeBucket,
    CheckCount,
    EditableSettings,
    FieldCount,
    InsightsOut,
    SelfTestOut,
    SelfTestRow,
    SettingsOut,
    SettingsUpdate,
    SpendRow,
    StatusResponse,
)
from citetally.api.state import AppState
from citetally.checks import Thresholds
from citetally.config import Settings
from citetally.dates import LOCALES
from citetally.models import CheckCode
from citetally.reading.ocr import find_tesseract
from citetally.reading.rapid_ocr import rapidocr_installed
from citetally.selftest import run_self_test

router = APIRouter(prefix="/api", tags=["settings"])

_DAY = r"^\d{4}-\d{2}-\d{2}$"


def current_status(state: AppState) -> StatusResponse:
    settings = state.settings
    database_ok: bool | None
    last_call: str | None = None
    try:
        connection = state.database.connect()
        try:
            connection.execute("SELECT 1").fetchone()
            last_call = connection.execute("SELECT MAX(created_at) FROM extractions").fetchone()[0]
        finally:
            connection.close()
        database_ok = True
    except (sqlite3.Error, OSError):
        database_ok = False
    if state.services_injected:
        ocr = True
    else:
        ocr = (
            rapidocr_installed()
            if settings.ocr_engine == "rapidocr"
            else find_tesseract(settings.tesseract_cmd) is not None
        ) and (settings.ocr_locator == "none" or rapidocr_installed())
    return StatusResponse(
        app="citetally",
        version=__version__,
        model_provider=settings.model_provider,
        text_model=settings.text_model,
        vision_model=settings.vision_model,
        ocr_engine=settings.ocr_engine,
        hosted_mode=settings.model_provider == "hosted",
        synthetic_data=settings.synthetic_data,
        database_ok=database_ok,
        ocr_available=ocr,
        queue_depth=state.worker.depth,
        last_model_call_at=last_call,
    )


def _editable(settings: Settings) -> EditableSettings:
    return EditableSettings(
        default_currency=settings.default_currency,
        locale=settings.locale,
        duplicate_date_window_days=settings.duplicate_date_window_days,
        outlier_ratio=f"{settings.outlier_ratio:f}",
        low_confidence=settings.low_confidence,
    )


def _settings_out(state: AppState) -> SettingsOut:
    return SettingsOut(
        status=current_status(state),
        allow_hosted=state.settings.allow_hosted,
        extract_mode=state.settings.extract_mode,
        values=_editable(state.settings),
        defaults=_editable(state.base_settings),
        locales=sorted(LOCALES),
    )


@router.get("/insights", response_model=InsightsOut)
def insights(
    conn: Conn,
    state: State,
    date_from: Annotated[str | None, Query(pattern=_DAY)] = None,
    date_to: Annotated[str | None, Query(pattern=_DAY)] = None,
) -> InsightsOut:
    if date_from and date_to and date_from > date_to:
        raise ApiError(422, "bad_period", "The period ends before it starts.")
    found = insight_queries.gather(
        conn,
        date_from=date_from,
        date_to=date_to,
        default_currency=state.settings.default_currency,
    )
    return InsightsOut(
        date_from=date_from,
        date_to=date_to,
        by_category=[SpendRow.model_validate(s, from_attributes=True) for s in found.by_category],
        by_vendor=[SpendRow.model_validate(s, from_attributes=True) for s in found.by_vendor],
        waiting_by_age=[
            AgeBucket(bucket=name, documents=count) for name, count in found.waiting_by_age.items()
        ],
        approved_documents=found.approved_documents,
        edited_documents=found.edited_documents,
        edited_fields=[
            FieldCount.model_validate(f, from_attributes=True) for f in found.edited_fields
        ],
        checks_failing=[
            CheckCount(
                check_code=CheckCode(c.check_code), documents=c.documents, overridden=c.overridden
            )
            for c in found.checks_failing
        ],
        review_seconds_median=found.review_seconds_median,
        review_seconds_count=found.review_seconds_count,
    )


@router.get("/settings", response_model=SettingsOut)
def read_settings(state: State) -> SettingsOut:
    return _settings_out(state)


@router.patch("/settings", response_model=SettingsOut)
def update_settings(body: SettingsUpdate, conn: Conn, state: State) -> SettingsOut:
    changes = body.model_dump(exclude_none=True)
    if changes:
        try:
            state.settings = runtime_settings.save(state.base_settings, conn, changes)
        except ValueError as error:
            raise ApiError(422, "invalid_setting", str(error)) from error
        state.worker.use_settings(state.settings)
    return _settings_out(state)


@router.post("/self-test", response_model=SelfTestOut)
def self_test(state: State) -> SelfTestOut:
    """Run the checks on invented sample documents. Reads nothing and changes nothing."""
    results = run_self_test(Thresholds.from_settings(state.settings))
    return SelfTestOut(
        passed=all(r.passed for r in results),
        results=[
            SelfTestRow(
                name=r.name,
                expectation=r.expectation,
                passed=r.passed,
                fired=[CheckCode(code) for code in r.fired],
            )
            for r in results
        ],
    )
