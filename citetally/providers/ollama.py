"""Ollama on the user's own machine, through its `/api/chat` endpoint.

The request asks for JSON that matches the schema, sets the context window explicitly (Ollama's
default of a few thousand tokens silently cuts long prompts), and turns thinking off unless asked.
Calls go straight to the configured address with no proxy, so page text never leaves the machine.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from citetally.providers.base import (
    ModelError,
    ModelResult,
    ModelTimeout,
    ModelUnavailable,
)

# (url, JSON body, timeout in seconds) -> decoded JSON reply
Transport = Callable[[str, dict[str, Any], float], dict[str, Any]]

_DEFAULT_CONTEXT_TOKENS = 8192
_NS_PER_MS = 1_000_000


def post_json(url: str, body: dict[str, Any], timeout_s: float) -> dict[str, Any]:
    """POST JSON and return the decoded reply, mapping every failure to a `ModelError`."""
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout_s) as response:
            payload = response.read()
    except urllib.error.HTTPError as error:
        raise ModelUnavailable(f"The model server answered HTTP {error.code}.") from None
    except TimeoutError:
        raise ModelTimeout("The model did not answer in time.") from None
    except urllib.error.URLError as error:
        if isinstance(error.reason, TimeoutError):
            raise ModelTimeout("The model did not answer in time.") from None
        raise ModelUnavailable("The model server could not be reached.") from None
    except OSError:
        raise ModelUnavailable("The connection to the model server failed.") from None
    try:
        decoded = json.loads(payload)
    except ValueError:
        raise ModelError("The model server sent something that is not JSON.") from None
    if not isinstance(decoded, dict):
        raise ModelError("The model server sent an unexpected reply.")
    return decoded


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        supports_vision: bool = False,
        think: bool = False,
        context_tokens: int = _DEFAULT_CONTEXT_TOKENS,
        transport: Transport = post_json,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("The Ollama address must start with http:// or https://")
        self.url = base_url.rstrip("/") + "/api/chat"
        self.model = model
        self.supports_vision = supports_vision
        self.think = think
        self.context_tokens = context_tokens
        self._transport = transport

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
        if images and not self.supports_vision:
            raise ModelError("This model does not accept images.")
        message: dict[str, Any] = {"role": "user", "content": user}
        if images:
            message["images"] = [base64.b64encode(image).decode("ascii") for image in images]
        options: dict[str, Any] = {
            "temperature": temperature,
            "num_predict": max_tokens,
            "num_ctx": self.context_tokens,
        }
        if seed is not None:
            options["seed"] = seed
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, message],
            "stream": False,
            "think": self.think,
            "format": schema,
            "options": options,
        }
        reply = self._transport(self.url, body, float(timeout_s))
        message_out = reply.get("message")
        content = message_out.get("content") if isinstance(message_out, dict) else None
        if not isinstance(content, str):
            raise ModelError("The model server's reply had no message.")
        try:
            loaded = json.loads(content)
        except ValueError:
            loaded = None
        nanoseconds = _count(reply.get("total_duration"))
        return ModelResult(
            parsed=loaded if isinstance(loaded, dict) else None,
            raw=content,
            input_tokens=_count(reply.get("prompt_eval_count")),
            output_tokens=_count(reply.get("eval_count")),
            duration_ms=None if nanoseconds is None else nanoseconds // _NS_PER_MS,
        )
