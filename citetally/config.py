"""Settings read from environment variables (and a local .env file). See docs/TRD.md section 8."""

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from citetally.dates import LOCALES


class Settings(BaseSettings):
    """Only the settings that exist so far; later phases add the rest of TRD section 8."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    port: int = Field(default=8200, validation_alias="CITETALLY_PORT")
    db_path: Path = Field(default=Path("data/citetally.db"), validation_alias="CITETALLY_DB_PATH")
    data_dir: Path = Field(default=Path("data"), validation_alias="CITETALLY_DATA_DIR")

    model_provider: Literal["ollama", "hosted"] = Field(
        "ollama", validation_alias="CITETALLY_MODEL_PROVIDER"
    )
    ollama_url: str = Field(default="http://127.0.0.1:11434", validation_alias="OLLAMA_URL")
    text_model: str = Field(default="qwen3:8b", validation_alias="CITETALLY_TEXT_MODEL")
    vision_model: str = Field(default="", validation_alias="CITETALLY_VISION_MODEL")

    extract_mode: Literal["text_only", "text_and_image"] = Field(
        default="text_only", validation_alias="CITETALLY_EXTRACT_MODE"
    )

    ocr_engine: Literal["tesseract"] = Field(
        default="tesseract", validation_alias="CITETALLY_OCR_ENGINE"
    )
    tesseract_cmd: str = Field(default="", validation_alias="TESSERACT_CMD")

    max_file_mb: int = Field(default=20, ge=1, validation_alias="CITETALLY_MAX_FILE_MB")
    max_pages: int = Field(default=10, ge=1, validation_alias="CITETALLY_MAX_PAGES")
    max_image_pixels: int = Field(
        default=40_000_000, ge=1, validation_alias="CITETALLY_MAX_IMAGE_PIXELS"
    )
    text_layer_min_chars: int = Field(
        default=80, ge=0, validation_alias="CITETALLY_TEXT_LAYER_MIN_CHARS"
    )

    grounding_match_threshold: float = Field(
        default=0.85, gt=0, le=1, validation_alias="CITETALLY_GROUNDING_MATCH_THRESHOLD"
    )
    default_currency: str = Field(
        default="USD", pattern=r"^[A-Z]{3}$", validation_alias="CITETALLY_DEFAULT_CURRENCY"
    )
    locale: str = Field(default="en-US", validation_alias="CITETALLY_LOCALE")

    allow_hosted: bool = Field(default=False, validation_alias="CITETALLY_ALLOW_HOSTED")
    synthetic_data: bool = Field(default=True, validation_alias="CITETALLY_SYNTHETIC_DATA")

    @field_validator("locale")
    @classmethod
    def locale_is_known(cls, value: str) -> str:
        if value not in LOCALES:
            raise ValueError(f"CITETALLY_LOCALE must be one of: {', '.join(sorted(LOCALES))}")
        return value

    @model_validator(mode="after")
    def image_mode_needs_a_vision_model(self) -> "Settings":
        if self.extract_mode == "text_and_image" and not self.vision_model:
            raise ValueError("CITETALLY_EXTRACT_MODE=text_and_image needs CITETALLY_VISION_MODEL.")
        return self

    @model_validator(mode="after")
    def hosted_requires_opt_in(self) -> "Settings":
        if self.model_provider == "hosted" and not self.allow_hosted:
            raise ValueError(
                "CITETALLY_MODEL_PROVIDER=hosted requires CITETALLY_ALLOW_HOSTED=true. "
                "Hosted models send page content to a third party and are off by default."
            )
        return self
