"""The one interface the pipeline uses to talk to a language model (TRD section 5).

A provider takes a system message, a user message and a JSON schema, and returns the reply with
its token counts and timing. Providers never log or raise with prompt or reply text: errors name
the kind of failure and nothing from the document.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ModelError(Exception):
    """The model could not be used. The message never holds document text."""


class ModelTimeout(ModelError):
    """The model did not answer in time."""


class ModelUnavailable(ModelError):
    """The model server is not reachable, refused the request, or is not set up."""


@dataclass(frozen=True)
class ModelResult:
    parsed: dict[str, Any] | None  # None when the reply was not a JSON object
    raw: str  # the reply text exactly as returned; stored with the extraction
    input_tokens: int | None  # None when the provider does not report them
    output_tokens: int | None
    duration_ms: int | None


class ModelProvider(Protocol):
    name: str  # a `Provider` value: "ollama" or "hosted"
    model: str
    supports_vision: bool

    def generate_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        images: list[bytes] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2000,
        timeout_s: int = 180,
        seed: int | None = 0,
    ) -> ModelResult: ...
