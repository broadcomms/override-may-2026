"""Tests for core.llm_clients.ollama (v6 plan task 2.10).

The **response-shape adapter is the load-bearing piece** per the v6 review —
the OllamaChatClient implements the same Protocol as WatsonxAIChatClient and
must normalize ``{"message": {"content": ...}}`` (Ollama) into the plain
string the Protocol promises, just as WatsonxAIChatClient unpacks
``{"choices": [{"message": ...}]}`` (watsonx). Both impls return ``str``.

The adapter test fires FIRST in this file; everything else is plumbing.

No live Ollama dependency — all HTTP calls go through respx-style mocks
via httpx's MockTransport.
"""

from __future__ import annotations

import json

import httpx
import pytest

from core.llm_clients.ollama import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    OllamaChatClient,
    OllamaChatClientError,
    _extract_ollama_content,
    probe_ollama_reachable,
)


# ──────────────────────────────────────────────────────────────────────────────
# §1 Response-shape adapter — the load-bearing test (write this FIRST)
# ──────────────────────────────────────────────────────────────────────────────


def test_extract_ollama_content_happy_path():
    """Real Ollama /api/chat response shape, verified via curl against
    granite4:350m in the running lab container on 2026-05-11."""
    body = {
        "model": "granite4:350m",
        "created_at": "2026-05-12T02:28:09.276519296Z",
        "message": {"role": "assistant", "content": "4."},
        "done": True,
        "done_reason": "stop",
        "total_duration": 1578947296,
    }
    assert _extract_ollama_content(body) == "4."


def test_extract_ollama_content_unwraps_multi_word_content():
    body = {"message": {"role": "assistant", "content": "The car overharvested in S2."}, "done": True}
    assert _extract_ollama_content(body) == "The car overharvested in S2."


def test_extract_ollama_content_rejects_non_dict_response():
    with pytest.raises(OllamaChatClientError, match="unexpected Ollama response type"):
        _extract_ollama_content("not a dict")


def test_extract_ollama_content_rejects_missing_message():
    with pytest.raises(OllamaChatClientError, match="missing `message` dict"):
        _extract_ollama_content({"model": "granite4:350m", "done": True})


def test_extract_ollama_content_rejects_non_string_content():
    with pytest.raises(OllamaChatClientError, match="is not a string"):
        _extract_ollama_content({"message": {"role": "assistant", "content": 42}})


def test_extract_ollama_content_rejects_empty_content():
    """granite4:350m occasionally emits blank responses; the adapter
    surfaces this as a clear error rather than letting empty strings
    flow into JSON-shape reasoning parsing downstream."""
    with pytest.raises(OllamaChatClientError, match="empty content"):
        _extract_ollama_content({"message": {"role": "assistant", "content": "   "}})


# ──────────────────────────────────────────────────────────────────────────────
# §2 Construction defaults + env-var resolution
# ──────────────────────────────────────────────────────────────────────────────


def test_construction_default_base_url_from_const():
    c = OllamaChatClient()
    assert c.base_url == DEFAULT_BASE_URL  # http://torcs:11434
    assert c.model == DEFAULT_MODEL  # granite4:350m


def test_construction_env_overrides(monkeypatch):
    monkeypatch.setenv("OVERRIDE_OLLAMA_BASE_URL", "http://elsewhere:11434/")
    monkeypatch.setenv("OVERRIDE_OLLAMA_MODEL", "granite4:custom")
    c = OllamaChatClient()
    # Trailing slash stripped
    assert c.base_url == "http://elsewhere:11434"
    assert c.model == "granite4:custom"


def test_construction_explicit_args_beat_env(monkeypatch):
    monkeypatch.setenv("OVERRIDE_OLLAMA_BASE_URL", "http://env:11434")
    c = OllamaChatClient(base_url="http://explicit:1234", model="granite4:explicit")
    assert c.base_url == "http://explicit:1234"
    assert c.model == "granite4:explicit"


def test_construction_does_not_open_socket():
    """Construction must be side-effect-free — no HTTP call. Unit tests
    inspect base_url/model without spinning up sockets."""
    c = OllamaChatClient(base_url="http://unreachable:9999")
    # The internal client is lazy-init; should still be None after construction.
    assert c._client is None


# ──────────────────────────────────────────────────────────────────────────────
# §3 chat() — HTTP request shape + error envelopes (mocked transport)
# ──────────────────────────────────────────────────────────────────────────────


def _client_with_mock_transport(handler):
    """OllamaChatClient with the internal httpx.Client swapped for one
    using a MockTransport. Lets us assert request shape + simulate
    arbitrary response bodies without hitting the network."""
    transport = httpx.MockTransport(handler)
    c = OllamaChatClient(base_url="http://test:11434", model="granite4:350m")
    c._client = httpx.Client(transport=transport, timeout=5.0)
    return c


def test_chat_sends_correct_request_shape():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200, json={"message": {"role": "assistant", "content": "ok"}, "done": True},
        )

    c = _client_with_mock_transport(handler)
    result = c.chat("system prompt", "user message", temperature=0.5, max_tokens=512)

    assert result == "ok"
    assert captured["method"] == "POST"
    assert captured["url"] == "http://test:11434/api/chat"
    body = captured["body"]
    assert body["model"] == "granite4:350m"
    assert body["stream"] is False
    assert body["messages"] == [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "user message"},
    ]
    assert body["options"]["temperature"] == 0.5
    assert body["options"]["num_predict"] == 512


def test_chat_returns_content_string_per_protocol():
    """The Protocol promises str return. Ollama wraps in {message: {content}};
    the adapter unwraps. Watsonx wraps in {choices: [{message: {content}}]};
    its adapter unwraps. From the call site's view, both return the same str."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": "Lap 3 over-harvested."}, "done": True},
        )

    c = _client_with_mock_transport(handler)
    out = c.chat("sys", "usr")
    assert isinstance(out, str)
    assert out == "Lap 3 over-harvested."


def test_chat_non_200_raises_with_helpful_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    c = _client_with_mock_transport(handler)
    with pytest.raises(OllamaChatClientError, match="HTTP 500"):
        c.chat("sys", "usr")


def test_chat_connection_failure_raises_helpful_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    c = _client_with_mock_transport(handler)
    with pytest.raises(OllamaChatClientError, match="transport error"):
        c.chat("sys", "usr")


def test_chat_malformed_json_response_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    c = _client_with_mock_transport(handler)
    with pytest.raises(OllamaChatClientError, match="non-JSON"):
        c.chat("sys", "usr")


def test_chat_empty_content_response_raises():
    """Adapter §1 already tests _extract_ollama_content directly; this
    confirms the same guard fires through the end-to-end chat() path."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"message": {"role": "assistant", "content": ""}, "done": True},
        )

    c = _client_with_mock_transport(handler)
    with pytest.raises(OllamaChatClientError, match="empty content"):
        c.chat("sys", "usr")


# ──────────────────────────────────────────────────────────────────────────────
# §4 probe_ollama_reachable — fail-loud startup probe (v6 plan task 2.10)
# ──────────────────────────────────────────────────────────────────────────────


def test_probe_ok_when_tags_endpoint_returns_models_list():
    """Simulate the real /api/tags response shape via a temporary
    httpx-mockable URL. probe_ollama_reachable opens its own client,
    so we patch httpx.Client momentarily."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "granite4:350m"}]})

    # The probe instantiates its own httpx.Client; patch the constructor
    # to return a MockTransport-backed client. Simplest via monkeypatching.
    original_client_cls = httpx.Client
    transport = httpx.MockTransport(handler)
    try:
        httpx.Client = lambda **kw: original_client_cls(transport=transport, **{k: v for k, v in kw.items() if k != "transport"})  # type: ignore
        ok, err = probe_ollama_reachable("http://probe-test:11434")
    finally:
        httpx.Client = original_client_cls  # type: ignore
    assert ok is True
    assert err is None


def test_probe_fails_loud_on_connection_refused():
    """The classic failure mode the probe was built to catch — silent
    60-second-connection-refused at the first reasoning call. Probe
    surfaces it at app boot instead."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    original_client_cls = httpx.Client
    transport = httpx.MockTransport(handler)
    try:
        httpx.Client = lambda **kw: original_client_cls(transport=transport, **{k: v for k, v in kw.items() if k != "transport"})  # type: ignore
        ok, err = probe_ollama_reachable("http://probe-test:11434")
    finally:
        httpx.Client = original_client_cls  # type: ignore
    assert ok is False
    assert err is not None
    assert "ConnectError" in err or "connection refused" in err


def test_probe_fails_on_unexpected_response_shape():
    """If something is listening on :11434 but ISN'T Ollama (e.g., a
    proxy returning HTML), probe still flags it — the /api/tags response
    must include a `models` field."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"wrong": "shape"})

    original_client_cls = httpx.Client
    transport = httpx.MockTransport(handler)
    try:
        httpx.Client = lambda **kw: original_client_cls(transport=transport, **{k: v for k, v in kw.items() if k != "transport"})  # type: ignore
        ok, err = probe_ollama_reachable("http://probe-test:11434")
    finally:
        httpx.Client = original_client_cls  # type: ignore
    assert ok is False
    assert err is not None and "missing `models`" in err
