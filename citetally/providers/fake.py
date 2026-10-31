"""A model that returns prepared replies, so tests need no model, network or GPU."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from citetally.providers.base import ModelError, ModelResult


@dataclass(frozen=True)
class FakeCall:
    """What the pipeline sent, kept so tests can check the prompt and the data block."""

    system: str
    user: str
    schema: dict[str, Any]
    images: list[bytes] | None
    max_tokens: int
    timeout_s: int


class FakeProvider:
    """Replies come from a queue: a dict (sent as JSON), a string (sent as is) or an exception.

    The name is "ollama" so rows written in pipeline tests satisfy the `extractions.provider`
    CHECK constraint; nothing about it is real.
    """

    name = "ollama"
    model = "fake-model"

    def __init__(
        self, replies: list[dict[str, Any] | str | Exception] | None = None, *, vision: bool = False
    ) -> None:
        self.supports_vision = vision
        self.replies: list[dict[str, Any] | str | Exception] = list(replies or [])
        self.calls: list[FakeCall] = []

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
    ) -> ModelResult:
        self.calls.append(FakeCall(system, user, schema, images, max_tokens, timeout_s))
        if images and not self.supports_vision:
            raise ModelError("This model does not accept images.")
        if not self.replies:
            raise ModelError("FakeProvider has no reply queued.")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        raw = reply if isinstance(reply, str) else json.dumps(reply)
        try:
            loaded = json.loads(raw)
        except ValueError:
            loaded = None
        parsed = loaded if isinstance(loaded, dict) else None
        return ModelResult(
            parsed=parsed,
            raw=raw,
            input_tokens=(len(system) + len(user)) // 4,
            output_tokens=len(raw) // 4,
            duration_ms=1,
        )
