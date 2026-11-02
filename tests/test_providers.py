"""The model providers, with no model: a recorded Ollama reply, a fake and a local test server."""

import base64
import contextlib
import json
import socket
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from citetally.config import Settings
from citetally.providers import (
    FakeProvider,
    ModelError,
    ModelTimeout,
    ModelUnavailable,
    OllamaProvider,
    build_provider,
)
from citetally.providers.ollama import post_json

RECORDED = json.loads(
    (Path(__file__).parent / "fixtures" / "ollama_chat_reply.json").read_text(encoding="utf-8")
)
SCHEMA: dict[str, Any] = {"type": "object", "properties": {"total": {"type": ["string", "null"]}}}
SECRET = "SECRET-VENDOR-TEXT"


class Recorder:
    """A transport that remembers the request and answers with a prepared reply."""

    def __init__(self, reply: dict[str, Any]) -> None:
        self.reply = reply
        self.requests: list[tuple[str, dict[str, Any], float]] = []

    def __call__(self, url: str, body: dict[str, Any], timeout_s: float) -> dict[str, Any]:
        self.requests.append((url, body, timeout_s))
        return self.reply


def ollama(reply: dict[str, Any] | None = None, **kwargs: Any) -> tuple[OllamaProvider, Recorder]:
    recorder = Recorder(RECORDED if reply is None else reply)
    provider = OllamaProvider("http://127.0.0.1:11434/", "qwen3:8b", transport=recorder, **kwargs)
    return provider, recorder


# --- the recorded reply ------------------------------------------------------------------------


def test_a_recorded_ollama_reply_becomes_parsed_json_with_tokens_and_timing() -> None:
    provider, _ = ollama()
    result = provider.generate_json(system="s", user="u", schema=SCHEMA)
    assert result.parsed == {"invoice_number": "INV-20001", "total": "$12.50"}
    assert result.raw == RECORDED["message"]["content"]
    assert (result.input_tokens, result.output_tokens) == (58, 24)
    assert result.duration_ms == 4170  # nanoseconds to whole milliseconds


def test_a_reply_without_counts_leaves_them_unknown() -> None:
    provider, _ = ollama({"message": {"role": "assistant", "content": '{"total": null}'}})
    result = provider.generate_json(system="s", user="u", schema=SCHEMA)
    assert result.parsed == {"total": None}
    assert (result.input_tokens, result.output_tokens, result.duration_ms) == (None, None, None)


@pytest.mark.parametrize("content", ["not json at all", "[1, 2]", '"text"', "", '{"total": '])
def test_a_reply_that_is_not_a_json_object_is_returned_unparsed_with_the_raw_text(
    content: str,
) -> None:
    provider, _ = ollama({"message": {"content": content}})
    result = provider.generate_json(system="s", user="u", schema=SCHEMA)
    assert result.parsed is None and result.raw == content


@pytest.mark.parametrize("reply", [{}, {"message": None}, {"message": {"content": 5}}])
def test_a_reply_with_no_message_text_is_an_error(reply: dict[str, Any]) -> None:
    provider, _ = ollama(reply)
    with pytest.raises(ModelError):
        provider.generate_json(system="s", user="u", schema=SCHEMA)


# --- the request -------------------------------------------------------------------------------


def test_the_request_pins_the_model_schema_seed_context_and_thinking() -> None:
    provider, recorder = ollama()
    provider.generate_json(
        system="SYS", user="USR", schema=SCHEMA, max_tokens=500, timeout_s=42, seed=7
    )
    ((url, body, timeout),) = recorder.requests
    assert url == "http://127.0.0.1:11434/api/chat" and timeout == 42.0
    assert body["model"] == "qwen3:8b" and body["stream"] is False and body["think"] is False
    assert body["format"] == SCHEMA
    assert body["messages"] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "USR"},
    ]
    assert body["options"] == {"temperature": 0.0, "num_predict": 500, "num_ctx": 8192, "seed": 7}


def test_no_seed_is_sent_when_none_is_asked_for_and_thinking_can_be_turned_on() -> None:
    provider, recorder = ollama(think=True, context_tokens=16384)
    provider.generate_json(system="s", user="u", schema=SCHEMA, seed=None)
    body = recorder.requests[0][1]
    assert "seed" not in body["options"] and body["options"]["num_ctx"] == 16384
    assert body["think"] is True


def test_images_are_sent_base64_encoded_only_to_a_vision_model() -> None:
    provider, recorder = ollama(supports_vision=True)
    provider.generate_json(system="s", user="u", schema=SCHEMA, images=[b"\x89PNG"])
    sent = recorder.requests[0][1]["messages"][1]["images"]
    assert [base64.b64decode(item) for item in sent] == [b"\x89PNG"]

    text_only, other = ollama()
    with pytest.raises(ModelError):
        text_only.generate_json(system="s", user="u", schema=SCHEMA, images=[b"x"])
    assert other.requests == []  # nothing was sent


def test_the_address_must_be_http() -> None:
    with pytest.raises(ValueError):
        OllamaProvider("file:///etc/passwd", "m")


# --- failures never carry document text --------------------------------------------------------


def test_errors_do_not_contain_the_prompt() -> None:
    def failing(url: str, body: dict[str, Any], timeout_s: float) -> dict[str, Any]:
        raise ModelUnavailable("The model server could not be reached.")

    provider = OllamaProvider("http://127.0.0.1:1", "m", transport=failing)
    with pytest.raises(ModelUnavailable) as caught:
        provider.generate_json(system=SECRET, user=SECRET, schema=SCHEMA)
    assert SECRET not in str(caught.value)


# --- the real transport, against a small local server ------------------------------------------


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length))
        mode = body["model"]
        if mode == "slow":
            time.sleep(1.0)
        if mode == "missing":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(SECRET.encode())
            return
        payload = b"<html>" if mode == "html" else json.dumps(RECORDED).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        with contextlib.suppress(OSError):  # the client may have given up
            self.wfile.write(payload)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def server() -> Iterator[str]:
    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/api/chat"
    httpd.shutdown()
    httpd.server_close()


def test_the_real_transport_round_trips_json(server: str) -> None:
    assert post_json(server, {"model": "ok"}, 5)["message"] == RECORDED["message"]


def test_a_slow_server_is_a_timeout(server: str) -> None:
    with pytest.raises(ModelTimeout):
        post_json(server, {"model": "slow"}, 0.2)


def test_an_http_error_is_unavailable_and_does_not_echo_the_body(server: str) -> None:
    with pytest.raises(ModelUnavailable) as caught:
        post_json(server, {"model": "missing"}, 5)
    assert "404" in str(caught.value) and SECRET not in str(caught.value)


def test_a_reply_that_is_not_json_is_a_model_error(server: str) -> None:
    with pytest.raises(ModelError):
        post_json(server, {"model": "html"}, 5)


def test_a_server_that_is_not_running_is_unavailable() -> None:
    with socket.socket() as closed:
        closed.bind(("127.0.0.1", 0))
        port = closed.getsockname()[1]
    with pytest.raises(ModelUnavailable):
        post_json(f"http://127.0.0.1:{port}/api/chat", {}, 10)


# --- the fake ----------------------------------------------------------------------------------


def test_the_fake_returns_queued_replies_in_order_and_records_every_call() -> None:
    fake = FakeProvider([{"total": "$1.00"}, '{"total": null}', "garbage"])
    results = [fake.generate_json(system="s", user=f"u{i}", schema=SCHEMA) for i in range(3)]
    assert [r.parsed for r in results] == [{"total": "$1.00"}, {"total": None}, None]
    assert results[2].raw == "garbage"
    assert [call.user for call in fake.calls] == ["u0", "u1", "u2"]


def test_the_fake_raises_a_queued_error_and_complains_when_empty() -> None:
    fake = FakeProvider([ModelTimeout("slow")])
    with pytest.raises(ModelTimeout):
        fake.generate_json(system="s", user="u", schema=SCHEMA)
    with pytest.raises(ModelError):
        fake.generate_json(system="s", user="u", schema=SCHEMA)
    assert len(fake.calls) == 2


def test_the_fake_refuses_images_unless_it_is_made_to_accept_them() -> None:
    with pytest.raises(ModelError):
        FakeProvider([{}]).generate_json(system="s", user="u", schema=SCHEMA, images=[b"x"])
    assert (
        FakeProvider([{}], vision=True)
        .generate_json(system="s", user="u", schema=SCHEMA, images=[b"x"])
        .parsed
        == {}
    )


# --- choosing a provider -----------------------------------------------------------------------


def test_the_default_settings_build_the_local_ollama_provider() -> None:
    provider = build_provider(Settings(_env_file=None))
    assert provider.name == "ollama" and provider.model == "qwen3:8b"
    assert not provider.supports_vision


def test_the_hosted_provider_is_not_built_yet_even_when_allowed() -> None:
    values = {"CITETALLY_MODEL_PROVIDER": "hosted", "CITETALLY_ALLOW_HOSTED": True}
    settings = Settings(_env_file=None, **values)  # type: ignore[arg-type]
    with pytest.raises(ModelUnavailable):
        build_provider(settings)


def test_image_mode_builds_the_vision_model_with_a_bigger_context_window() -> None:
    values = {"CITETALLY_EXTRACT_MODE": "text_and_image", "CITETALLY_VISION_MODEL": "qwen3-vl:8b"}
    provider = build_provider(Settings(_env_file=None, **values))  # type: ignore[arg-type]
    assert provider.model == "qwen3-vl:8b" and provider.supports_vision
    assert isinstance(provider, OllamaProvider) and provider.context_tokens > 8192


def test_the_vision_provider_exists_only_in_auto_mode_with_a_vision_model() -> None:
    from citetally.config import Settings
    from citetally.providers import build_provider, build_vision_provider

    def settings(**values: str) -> Settings:
        return Settings(_env_file=None, **values)  # type: ignore[arg-type]

    assert build_vision_provider(settings(CITETALLY_EXTRACT_MODE="text_only")) is None
    assert (
        build_vision_provider(settings(CITETALLY_EXTRACT_MODE="auto", CITETALLY_VISION_MODEL=""))
        is None
    )
    both = settings(CITETALLY_EXTRACT_MODE="auto", CITETALLY_VISION_MODEL="qwen3-vl:8b-instruct")
    vision = build_vision_provider(both)
    assert vision is not None and vision.supports_vision and vision.model == "qwen3-vl:8b-instruct"
    assert not build_provider(both).supports_vision  # the text model stays the text model
