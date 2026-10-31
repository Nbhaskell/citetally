"""Model providers. The pipeline only ever sees `ModelProvider`."""

from citetally.config import Settings
from citetally.providers.base import (
    ModelError,
    ModelProvider,
    ModelResult,
    ModelTimeout,
    ModelUnavailable,
)
from citetally.providers.fake import FakeCall, FakeProvider
from citetally.providers.ollama import OllamaProvider

__all__ = [
    "FakeCall",
    "FakeProvider",
    "ModelError",
    "ModelProvider",
    "ModelResult",
    "ModelTimeout",
    "ModelUnavailable",
    "OllamaProvider",
    "build_provider",
]


def build_provider(settings: Settings) -> ModelProvider:
    """The provider the settings ask for. Hosted is designed (TRD section 6) but not built."""
    if settings.model_provider == "hosted":
        raise ModelUnavailable("The hosted provider is not built yet.")
    return OllamaProvider(settings.ollama_url, settings.text_model)
