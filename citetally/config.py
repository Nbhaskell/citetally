"""Settings read from environment variables (and a local .env file). See docs/TRD.md section 8."""

from decimal import Decimal
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
    web_port: int = Field(default=5175, validation_alias="CITETALLY_WEB_PORT")
    db_path: Path = Field(default=Path("data/citetally.db"), validation_alias="CITETALLY_DB_PATH")
    data_dir: Path = Field(default=Path("data"), validation_alias="CITETALLY_DATA_DIR")

    model_provider: Literal["ollama", "hosted"] = Field(
        "ollama", validation_alias="CITETALLY_MODEL_PROVIDER"
    )
    ollama_url: str = Field(default="http://127.0.0.1:11434", validation_alias="OLLAMA_URL")
    text_model: str = Field(default="qwen3:8b", validation_alias="CITETALLY_TEXT_MODEL")
    vision_model: str = Field(
        default="qwen3-vl:8b-instruct", validation_alias="CITETALLY_VISION_MODEL"
    )

    # text_only: the page's text. text_and_image: the text and the picture, always. auto: the text
    # for a PDF with a text layer, the text and the picture for a scan or photo (when a vision
    # model is set; without one, auto is text_only).
    extract_mode: Literal["text_only", "text_and_image", "auto"] = Field(
        default="auto", validation_alias="CITETALLY_EXTRACT_MODE"
    )
    enable_thinking: bool = Field(default=False, validation_alias="CITETALLY_ENABLE_THINKING")
    # A model that thinks first spends part of this budget (and time) before it answers.
    extract_max_tokens: int = Field(
        default=2000, ge=200, validation_alias="CITETALLY_EXTRACT_MAX_TOKENS"
    )
    extract_timeout_s: int = Field(
        default=180, ge=10, validation_alias="CITETALLY_EXTRACT_TIMEOUT_S"
    )

    # `rapidocr` is optional and installed separately (`requirements-rapidocr.txt`, D-073).
    ocr_engine: Literal["tesseract", "rapidocr"] = Field(
        default="tesseract", validation_alias="CITETALLY_OCR_ENGINE"
    )
    # A second engine whose words are used only to locate values on the page; the text the model
    # reads and the read-quality confidence stay the first engine's (D-075).
    ocr_locator: Literal["none", "rapidocr"] = Field(
        default="none", validation_alias="CITETALLY_OCR_LOCATOR"
    )
    tesseract_cmd: str = Field(default="", validation_alias="TESSERACT_CMD")
    # How many ways each scanned page is read. Tesseract: 1 the usual way; 2 adds block mode; 3 also
    # a larger copy. RapidOCR: 1 the cleaned page; 2 or 3 add a reading of the page as it came.
    # Each reading finds values the others lose; every value is still located in the words.
    ocr_readings: int = Field(default=3, ge=1, le=3, validation_alias="CITETALLY_OCR_READINGS")

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

    low_confidence: float = Field(
        default=75.0, ge=0, le=100, validation_alias="CITETALLY_LOW_CONFIDENCE"
    )
    math_tolerance_minor: int = Field(
        default=1, ge=0, validation_alias="CITETALLY_MATH_TOLERANCE_MINOR"
    )
    duplicate_date_window_days: int = Field(
        default=7, ge=0, validation_alias="CITETALLY_DUPLICATE_DATE_WINDOW_DAYS"
    )
    outlier_min_history: int = Field(
        default=5, ge=1, validation_alias="CITETALLY_OUTLIER_MIN_HISTORY"
    )
    outlier_ratio: Decimal = Field(
        default=Decimal(3), gt=1, validation_alias="CITETALLY_OUTLIER_RATIO"
    )
    max_age_days: int = Field(default=400, ge=1, validation_alias="CITETALLY_MAX_AGE_DAYS")
    suspicious_phrases: str = Field(
        default="", validation_alias="CITETALLY_SUSPICIOUS_PHRASES"
    )  # extra phrases for SUSPICIOUS_TEXT, separated by semicolons, matched as plain text

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
    def locator_helps_tesseract(self) -> "Settings":
        if self.ocr_locator != "none" and self.ocr_engine != "tesseract":
            raise ValueError(
                "CITETALLY_OCR_LOCATOR adds to Tesseract: set CITETALLY_OCR_ENGINE=tesseract."
            )
        return self

    @model_validator(mode="after")
    def hosted_requires_opt_in(self) -> "Settings":
        if self.model_provider == "hosted" and not self.allow_hosted:
            raise ValueError(
                "CITETALLY_MODEL_PROVIDER=hosted requires CITETALLY_ALLOW_HOSTED=true. "
                "Hosted models send page content to a third party and are off by default."
            )
        return self
