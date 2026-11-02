import pytest
from pydantic import ValidationError

from citetally.config import Settings


def make() -> Settings:
    """Build settings from the process environment only, ignoring any .env file."""
    return Settings(_env_file=None)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "CITETALLY_PORT",
        "CITETALLY_MODEL_PROVIDER",
        "CITETALLY_ALLOW_HOSTED",
        "CITETALLY_MAX_FILE_MB",
        "CITETALLY_MAX_PAGES",
        "CITETALLY_MAX_IMAGE_PIXELS",
        "CITETALLY_TEXT_LAYER_MIN_CHARS",
        "CITETALLY_SYNTHETIC_DATA",
        "CITETALLY_TEXT_MODEL",
        "CITETALLY_GROUNDING_MATCH_THRESHOLD",
        "CITETALLY_DEFAULT_CURRENCY",
        "CITETALLY_LOCALE",
        "CITETALLY_VISION_MODEL",
        "OLLAMA_URL",
        "TESSERACT_CMD",
    ):
        monkeypatch.delenv(name, raising=False)


def test_defaults_match_the_docs() -> None:
    s = make()
    assert s.port == 8200
    assert s.model_provider == "ollama"
    assert s.text_model == "qwen3:8b"
    assert s.vision_model == "qwen3-vl:8b-instruct"
    assert s.ocr_engine == "tesseract"
    assert s.allow_hosted is False
    assert s.synthetic_data is True
    assert s.ollama_url == "http://127.0.0.1:11434"


def test_environment_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CITETALLY_PORT", "9000")
    monkeypatch.setenv("CITETALLY_TEXT_MODEL", "other:1b")
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:1234")
    s = make()
    assert (s.port, s.text_model, s.ollama_url) == (9000, "other:1b", "http://127.0.0.1:1234")


def test_empty_values_fall_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    # .env.example ships with empty entries; they must not break parsing.
    monkeypatch.setenv("CITETALLY_PORT", "")
    monkeypatch.setenv("TESSERACT_CMD", "")
    s = make()
    assert s.port == 8200
    assert s.tesseract_cmd == ""


def test_hosted_provider_refuses_to_start_without_allow_hosted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CITETALLY_MODEL_PROVIDER", "hosted")
    with pytest.raises(ValidationError, match="CITETALLY_ALLOW_HOSTED"):
        make()


def test_hosted_provider_starts_when_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CITETALLY_MODEL_PROVIDER", "hosted")
    monkeypatch.setenv("CITETALLY_ALLOW_HOSTED", "true")
    assert make().model_provider == "hosted"


def test_unknown_provider_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CITETALLY_MODEL_PROVIDER", "mystery")
    with pytest.raises(ValidationError):
        make()


def test_upload_limits_default_to_the_documented_values() -> None:
    s = make()
    assert (s.max_file_mb, s.max_pages, s.text_layer_min_chars) == (20, 10, 80)
    assert s.max_image_pixels == 40_000_000


def test_upload_limits_must_be_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CITETALLY_MAX_FILE_MB", "0")
    with pytest.raises(ValidationError):
        make()


def test_grounding_and_locale_defaults_match_the_docs() -> None:
    s = make()
    assert (s.grounding_match_threshold, s.default_currency, s.locale) == (0.85, "USD", "en-US")


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("CITETALLY_GROUNDING_MATCH_THRESHOLD", "0"),
        ("CITETALLY_GROUNDING_MATCH_THRESHOLD", "1.5"),
        ("CITETALLY_DEFAULT_CURRENCY", "usd"),
        ("CITETALLY_LOCALE", "xx-YY"),
    ],
)
def test_bad_grounding_and_locale_settings_are_refused(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        make()


def test_scans_get_their_picture_by_default_and_always_picture_mode_needs_a_vision_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CITETALLY_EXTRACT_MODE", raising=False)
    monkeypatch.delenv("CITETALLY_VISION_MODEL", raising=False)
    assert make().extract_mode == "auto" and make().vision_model == "qwen3-vl:8b-instruct"
    assert make().ocr_readings == 3
    with pytest.raises(ValidationError):
        Settings(_env_file=None, CITETALLY_EXTRACT_MODE="text_and_image", CITETALLY_VISION_MODEL="")
    monkeypatch.setenv("CITETALLY_EXTRACT_MODE", "text_and_image")
    assert make().extract_mode == "text_and_image"


def test_auto_mode_needs_no_vision_model_but_text_and_image_still_does() -> None:
    assert (
        Settings(
            _env_file=None, CITETALLY_EXTRACT_MODE="auto", CITETALLY_VISION_MODEL=""
        ).extract_mode
        == "auto"
    )
    with pytest.raises(ValueError, match="VISION_MODEL"):
        Settings(_env_file=None, CITETALLY_EXTRACT_MODE="text_and_image", CITETALLY_VISION_MODEL="")
