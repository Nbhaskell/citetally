"""FastAPI app and routes. See docs/TRD.md section 7."""

from fastapi import FastAPI
from pydantic import BaseModel

from citetally import __version__
from citetally.config import Settings


class StatusResponse(BaseModel):
    app: str
    version: str
    model_provider: str
    text_model: str
    vision_model: str
    ocr_engine: str
    hosted_mode: bool
    synthetic_data: bool
    # Not built yet: the database arrives in Phase 2, OCR in Phase 3, the model call and
    # queue in Phases 4 and 5. None means "not reported yet", not "unhealthy".
    database_ok: bool | None = None
    ocr_available: bool | None = None
    queue_depth: int | None = None
    last_model_call_at: str | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="Citetally", version=__version__)

    @app.get("/api/status", response_model=StatusResponse)
    def status() -> StatusResponse:
        return StatusResponse(
            app="citetally",
            version=__version__,
            model_provider=settings.model_provider,
            text_model=settings.text_model,
            vision_model=settings.vision_model,
            ocr_engine=settings.ocr_engine,
            hosted_mode=settings.model_provider == "hosted",
            synthetic_data=settings.synthetic_data,
        )

    return app
