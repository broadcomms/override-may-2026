"""OllamaChatClient — implements core.reasoning.WatsonxChatClient against Ollama.

Used by ``core/reasoning.py`` and ``core/fan_mode.py`` when
``OVERRIDE_LLM_RUNTIME=ollama`` is set (see ``api.main.get_chat_client``
factory). The lab's TORCS container ships granite4:350m bundled via Ollama
at ``:11434``; this client hits its ``/api/chat`` endpoint and normalizes
the response into the same plain-text shape the watsonx impl returns.

**Response-shape adapter is the load-bearing piece** (v6 plan task 2.10).
Ollama's ``/api/chat`` returns::

    {"message": {"role": "assistant", "content": "..."}, "done": true, ...}

Watsonx's chat API returns::

    {"choices": [{"message": {"role": "assistant", "content": "..."}}], ...}

``core.reasoning.WatsonxChatClient.chat`` is documented to return a plain
``str`` (the assistant's content) — both impls unpack to that. The Protocol
isn't shape-coupled to either response, so swapping the client is
side-effect-free at the call site.

References:
  - ``core/reasoning.py`` §WatsonxChatClient (Protocol)
  - ``docs/adrs/ADR-003-llm-runtime-abstraction.md`` (hybrid posture, v1.1
    all-ollama migration plan, why Guardian + Embedding stay watsonx-only)
  - ``hands-on-labs/01_torcs_lab/RESULTS.md`` (lab's `ollama pull granite4:350m`
    instruction — the lab image ships an empty /opt/ollama/models dir;
    students populate it on first start)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


# Defaults pin to the documented lab container path. Compose's service-to-
# service DNS resolves `torcs` to the lab container; non-compose dev hits
# `localhost` via the host port forward in scripts/run_torcs_lab.sh.
DEFAULT_BASE_URL = "http://torcs:11434"
DEFAULT_MODEL = "granite4:350m"  # verified via `podman exec torcs ollama list`
DEFAULT_TIMEOUT_S = 300.0  # granite4:350m is small enough that a full
# reasoning prompt (system + LapWindow table + zone metrics) can take 2-3 min
# on a typical CPU. 5-minute ceiling is well past observed P99 on the v6 plan
# task 2.10 manual gate. v1.0 demo uses watsonx (sub-5s); ollama mode is a
# v1.1 migration story per ADR-003 where this generous timeout is acceptable.

# Startup probe timeout — short so misconfiguration fails fast, not at the
# first chat call. Per v6 plan task 2.10's fail-loud requirement.
PROBE_TIMEOUT_S = 2.0


class OllamaChatClientError(RuntimeError):
    """Raised when the Ollama HTTP layer misbehaves in a way the caller
    should know about — connection refused, malformed response shape,
    empty content. Caller (factory or reasoning loop) decides whether to
    retry, fail loud, or fall back."""


def probe_ollama_reachable(base_url: str = DEFAULT_BASE_URL) -> tuple[bool, Optional[str]]:
    """Cheap GET ``/api/tags`` round-trip. Returns ``(ok, error_message)``.

    Called at app boot by ``api.main.get_chat_client`` when
    ``OVERRIDE_LLM_RUNTIME=ollama``. If unreachable, the factory refuses
    to boot with a clear error — catches the silent-60-second-connection-
    refused failure mode at the front door instead of inside the first
    reasoning call (v6 plan task 2.10).
    """
    try:
        with httpx.Client(timeout=PROBE_TIMEOUT_S) as cl:
            r = cl.get(f"{base_url.rstrip('/')}/api/tags")
        if r.status_code != 200:
            return False, f"GET /api/tags returned HTTP {r.status_code}"
        body = r.json()
        if not isinstance(body, dict) or "models" not in body:
            return False, "GET /api/tags response missing `models` field"
        return True, None
    except httpx.HTTPError as e:
        return False, f"{type(e).__name__}: {e}"
    except Exception as e:  # pragma: no cover — defensive
        return False, f"{type(e).__name__}: {e}"


class OllamaChatClient:
    """Drop-in implementation of ``core.reasoning.WatsonxChatClient``.

    Constructed without args reads ``OVERRIDE_OLLAMA_BASE_URL`` /
    ``OVERRIDE_OLLAMA_MODEL`` env vars; tests inject explicit values.
    The HTTP client is owned per-instance (httpx.Client) so connection
    pooling works across the per-zone reasoning fan-out in
    ``core/pipeline.py``.
    """

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ):
        self.base_url = (base_url or os.environ.get("OVERRIDE_OLLAMA_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or os.environ.get("OVERRIDE_OLLAMA_MODEL") or DEFAULT_MODEL
        self._timeout_s = timeout_s
        # Lazy HTTP client — instantiated on first chat() to keep
        # construction side-effect-free (unit tests inspect base_url/model
        # without spinning up any sockets).
        self._client: Optional[httpx.Client] = None

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout_s)
        return self._client

    def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> str:
        """Call ``POST /api/chat`` and return the assistant's content as plain text.

        Matches the Protocol signature in ``core.reasoning.WatsonxChatClient``
        verbatim. Raises ``OllamaChatClientError`` on transport failures or
        malformed responses — caller's ``except RuntimeError`` in
        ``core/reasoning.py`` (and watsonx-exception mapper in
        ``api/main.py``) will surface it as ``MODEL_UNAVAILABLE`` 503.
        """
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        try:
            r = self._http().post(url, json=payload)
        except httpx.HTTPError as e:
            raise OllamaChatClientError(
                f"Ollama transport error against {url}: {type(e).__name__}: {e}"
            ) from e
        if r.status_code != 200:
            raise OllamaChatClientError(
                f"Ollama HTTP {r.status_code} from {url}: {r.text[:200]}"
            )
        try:
            body = r.json()
        except ValueError as e:
            raise OllamaChatClientError(
                f"Ollama returned non-JSON body: {r.text[:200]}"
            ) from e
        return _extract_ollama_content(body)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    # Context-manager friendly — pipeline owns clients via Depends() and
    # FastAPI handles lifecycle; explicit close() is for tests.
    def __enter__(self) -> "OllamaChatClient":
        return self

    def __exit__(self, *a: Any) -> None:
        self.close()


def _extract_ollama_content(body: Any) -> str:
    """Pull the assistant's content out of an Ollama /api/chat response.

    The response shape (per ``ollama --version`` ≥ 0.1.x) is::

        {"message": {"role": "assistant", "content": "..."}, "done": true, ...}

    The adapter intentionally does NOT translate to the watsonx-style
    ``{"choices": [{"message": ...}]}`` envelope — both clients return
    plain strings per the Protocol. Defensive:
      - dict access via .get() so partial responses raise a clear error
      - empty/whitespace content rejected (granite4:350m sometimes
        returns terse outputs; an empty string is downstream-toxic for
        JSON-shape reasoning so surface it loud)
      - non-string content type rejected (shouldn't happen with /api/chat,
        but the streaming endpoint returns a different shape entirely)
    """
    if not isinstance(body, dict):
        raise OllamaChatClientError(f"unexpected Ollama response type: {type(body).__name__}")
    msg = body.get("message")
    if not isinstance(msg, dict):
        raise OllamaChatClientError(
            f"Ollama response missing `message` dict: keys={list(body.keys())[:10]}"
        )
    content = msg.get("content")
    if not isinstance(content, str):
        raise OllamaChatClientError(
            f"Ollama response `message.content` is not a string: type={type(content).__name__}"
        )
    if not content.strip():
        raise OllamaChatClientError(
            "Ollama returned empty content — small models occasionally emit blank "
            "responses; consider raising temperature or retrying"
        )
    return content
