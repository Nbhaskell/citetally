"""Settings read from environment variables (and a local .env file). See docs/TRD.md section 8."""

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    ocr_engine: Literal["tesseract"] = Field(
        default="tesseract", validation_alias="CITETALLY_OCR_ENGINE"
    )
    tesseract_cmd: str = Field(default="", validation_alias="TESSERACT_CMD")

    allow_hosted: bool = Field(default=False, validation_alias="CITETALLY_ALLOW_HOSTED")
    synthetic_data: bool = Field(default=True, validation_alias="CITETALLY_SYNTHETIC_DATA")

    @model_validator(mode="after")
    def hosted_requires_opt_in(self) -> "Settings":
        if self.model_provider == "hosted" and not self.allow_hosted:
            raise ValueError(
                "CITETALLY_MODEL_PROVIDER=hosted requires CITETALLY_ALLOW_HOSTED=true. "
                "Hosted models send page content to a third party and are off by default."
            )
        return self
