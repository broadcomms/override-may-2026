"""Granite Instruct reasoning over a single inefficient zone.

Produces a `ReasoningOutput` (per docs/04-schema.md §7) by:

  1. rendering the system prompt from prompts/reasoning.system.md
  2. rendering the user message: lap_window as compact markdown table,
     zone + (optional) forecast + (optional) regulation as JSON
  3. calling the configured `WatsonxChatClient`
  4. parsing the response tolerantly (strips markdown code fences, leading
     whitespace) and validating against the Pydantic schema

The chat client is **injected** so unit tests can mock it. The default
implementation (`WatsonxAIChatClient`) hits watsonx.ai's chat API per
ADR-001. The legacy /ml/v1/text/generation endpoint is NOT used.

Per the prompt + FR-4.3:
  - When `regulation` is None, output's `regulation_citation` is None and
    `confidence` is "low". The prompt + parser both enforce this.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional, Protocol

from pydantic import ValidationError

from ingest.schema import (
    Forecast,
    LapWindow,
    RegulationChunk,
    ReasoningInput,
    ReasoningOutput,
    Zone,
)

logger = logging.getLogger(__name__)


# Resolve the system prompt once at import time. If anyone changes the
# prompt, this picks up the new content on next process restart.
_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "reasoning.system.md"


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────────
# Chat client abstraction (so tests can mock without touching the network)
# ──────────────────────────────────────────────────────────────────────────────


class WatsonxChatClient(Protocol):
    """Minimal interface every reasoning call needs.

    Production: WatsonxAIChatClient (below). Tests: a fake that returns
    canned JSON strings.
    """

    def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> str:
        ...


class WatsonxAIChatClient:
    """Real watsonx.ai chat-API client. Reads credentials from .env."""

    def __init__(
        self,
        model_id: Optional[str] = None,
        api_key: Optional[str] = None,
        url: Optional[str] = None,
        project_id: Optional[str] = None,
    ):
        self.model_id = model_id or os.environ.get("GRANITE_INSTRUCT", "ibm/granite-4-h-small")
        self.api_key = api_key or os.environ.get("WATSONX_API_KEY")
        self.url = url or os.environ.get("WATSONX_URL")
        self.project_id = project_id or os.environ.get("WATSONX_PROJECT_ID")

        if not all([self.api_key, self.url, self.project_id]):
            raise RuntimeError(
                "WatsonxAIChatClient: missing one of WATSONX_API_KEY / WATSONX_URL / "
                "WATSONX_PROJECT_ID — see .env.example."
            )

        # Lazy-import the SDK so tests that mock the client don't pay the import cost.
        from ibm_watsonx_ai import Credentials  # noqa: F401
        from ibm_watsonx_ai.foundation_models import ModelInference

        self._creds = Credentials(api_key=self.api_key, url=self.url)
        self._model = ModelInference(
            model_id=self.model_id,
            credentials=self._creds,
            project_id=self.project_id,
        )

    def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        params = {
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        resp = self._model.chat(messages=messages, params=params)
        return _extract_chat_text(resp)


def _extract_chat_text(resp: Any) -> str:
    """Pull the assistant's text out of a watsonx chat response.

    The chat API response shape (per the watsonx SDK):
        {"choices": [{"message": {"role": "assistant", "content": "..."}}], ...}

    Defensive: also handles dict-or-object access, and plain-string fallback
    (in case a fake test client returns the raw text).
    """
    if isinstance(resp, str):
        return resp
    if isinstance(resp, dict):
        choices = resp.get("choices") or []
        if choices:
            msg = choices[0].get("message") or {}
            content = msg.get("content")
            if isinstance(content, str):
                return content
    raise RuntimeError(f"unexpected watsonx chat response shape: {type(resp).__name__}")


# ──────────────────────────────────────────────────────────────────────────────
# Prompt rendering
# ──────────────────────────────────────────────────────────────────────────────


def _render_lap_window(lap_window: LapWindow) -> str:
    """Compact markdown table of LapFeatures rows.

    Token-efficient: ~45 chars per row × 30 rows = ~1.4 KB max — well
    inside Granite 4-h-small's 128K context.
    """
    header = (
        "| lap | soc_start | soc_end | harvest_mj | deploy_mj | lap_time | "
        "sectors_s | avg_kmh | max_kmh | overtake_uses | boost | recharge_zones | soc_source |"
    )
    sep = (
        "|----:|----------:|--------:|-----------:|----------:|---------:|"
        "----------|--------:|--------:|---------:|------:|----------------|------------|"
    )
    rows = [header, sep]
    for L in lap_window.laps:
        sectors = f"{L.sector1_time:.1f}/{L.sector2_time:.1f}/{L.sector3_time:.1f}"
        rz = ",".join(str(s) for s in L.recharge_zones) or "-"
        rows.append(
            f"| {L.lap_number} | {L.soc_start:.3f} | {L.soc_end:.3f} | "
            f"{L.harvest_mj:.2f} | {L.deploy_mj:.2f} | {L.lap_time:.2f} | "
            f"{sectors} | {L.avg_speed:.0f} | {L.max_speed:.0f} | "
            f"{L.override_uses} | {L.boost_uses} | {rz} | {L.soc_source} |"
        )
    track = f" (track={lap_window.track_id})" if lap_window.track_id else ""
    return (
        f"## lap_window — session={lap_window.session_id}, "
        f"soc_max={lap_window.soc_max:.2f} MJ{track}\n"
        + "\n".join(rows)
    )


def _render_forecast(forecast: Optional[Forecast]) -> str:
    if forecast is None:
        return "## forecast\nnull (TTM-R2 unavailable; reason from observed data alone)"
    return "## forecast\n" + json.dumps(forecast.model_dump(mode="json"), indent=2)


def _render_zone(zone: Zone) -> str:
    return "## zone\n" + json.dumps(zone.model_dump(mode="json"), indent=2)


def _render_regulation(regulation: Optional[RegulationChunk]) -> str:
    if regulation is None:
        return (
            "## regulation\n"
            "null (no relevant regulation chunk retrieved). "
            'Per the hard rules above: set "regulation_citation": null and '
            'lower "confidence" to "low". Do not fabricate a citation.'
        )
    return "## regulation\n" + json.dumps(regulation.model_dump(mode="json"), indent=2)


def render_user_message(reasoning_input: ReasoningInput) -> str:
    """Compose the full user message from the typed input."""
    return "\n\n".join(
        [
            _render_lap_window(reasoning_input.lap_window),
            _render_forecast(reasoning_input.forecast),
            _render_zone(reasoning_input.zone),
            _render_regulation(reasoning_input.regulation),
        ]
    )


# ──────────────────────────────────────────────────────────────────────────────
# Tolerant JSON parsing
# ──────────────────────────────────────────────────────────────────────────────


_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL | re.IGNORECASE)


class ReasoningParseError(ValueError):
    """Raised when the model's response can't be parsed into ReasoningOutput."""


def parse_reasoning_response(text: str) -> ReasoningOutput:
    """Strip code fences / whitespace, parse JSON, validate against schema.

    The prompt asks for "JSON only, no prose preamble" but instruction-following
    models occasionally wrap output in ```json ... ``` fences anyway. This
    parser is tolerant of that one specific quirk and strict about everything
    else.
    """
    raw = text.strip()
    if not raw:
        raise ReasoningParseError("empty response from model")

    # Strip markdown code fence (with or without 'json' tag).
    fence_match = _FENCE_RE.match(raw)
    if fence_match:
        raw = fence_match.group(1).strip()

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        snippet = raw[:200].replace("\n", "\\n")
        raise ReasoningParseError(
            f"model response is not valid JSON: {e.msg} (offset {e.pos}); "
            f"first 200 chars: {snippet!r}"
        ) from e

    try:
        return ReasoningOutput.model_validate(obj)
    except ValidationError as e:
        raise ReasoningParseError(
            f"model output failed schema validation:\n{e}"
        ) from e


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────


def reason_about_zone(
    zone: Zone,
    lap_window: LapWindow,
    forecast: Optional[Forecast] = None,
    regulation: Optional[RegulationChunk] = None,
    *,
    client: WatsonxChatClient,
    temperature: Optional[float] = None,
    max_tokens: int = 1024,
    extra_system_directive: Optional[str] = None,
) -> ReasoningOutput:
    """Reason over one zone using Granite Instruct on watsonx.ai.

    Args:
        zone: The detected zone the model should explain.
        lap_window: 1–30 LapFeatures rows providing context (per schema).
        forecast: Optional 5-lap TTM-R2 forecast. Pass None when unavailable
            (graceful degradation per FR-3).
        regulation: Optional RegulationChunk. Pre-G-4 this is None and the
            output gets `regulation_citation=None, confidence='low'` per the
            prompt's hard rule.
        client: Injected `WatsonxChatClient`. Tests pass a fake.
        temperature: Override `REASONING_TEMPERATURE` env (default 0.3).
        max_tokens: Output token cap. 1024 is enough for the strict JSON shape.
        extra_system_directive: Optional appendix to the system prompt — used
            by `core.pipeline` on retry to inject a stricter directive after
            a Pass-1 or Pass-2 failure (e.g. "On retry: cite a passage that
            appears verbatim in the regulation"). Appended after the canonical
            prompt body so it overrides on conflict.

    Returns:
        A validated `ReasoningOutput`.

    Raises:
        ReasoningParseError: if the model output can't be coerced.
    """
    if temperature is None:
        try:
            temperature = float(os.environ.get("REASONING_TEMPERATURE", "0.3"))
        except ValueError:
            temperature = 0.3

    rinput = ReasoningInput(
        session_id=lap_window.session_id,
        lap_window=lap_window,
        forecast=forecast,
        zone=zone,
        regulation=regulation,
    )
    system = _load_system_prompt()
    if extra_system_directive:
        system = f"{system}\n\n# Retry directive\n{extra_system_directive.strip()}"
    user = render_user_message(rinput)

    logger.info(
        "reason_about_zone: session=%s zone=%s type=%s temp=%.2f regulation=%s retry_directive=%s",
        lap_window.session_id,
        zone.zone_id,
        zone.zone_type.value,
        temperature,
        "present" if regulation is not None else "absent",
        "yes" if extra_system_directive else "no",
    )

    # OpenTelemetry span — visible in Jaeger when OVERRIDE_TRACING=otlp.
    # No-op when tracing is off (default). See api/observability.py.
    from api.observability import traced_span

    with traced_span(
        "reasoning.chat",
        zone_id=zone.zone_id,
        zone_type=zone.zone_type.value,
        session_id=lap_window.session_id,
        regulation_present=regulation is not None,
        retry_directive=bool(extra_system_directive),
        temperature=temperature,
    ):
        raw = client.chat(system=system, user=user, temperature=temperature, max_tokens=max_tokens)
        return parse_reasoning_response(raw)


__all__ = [
    "WatsonxChatClient",
    "WatsonxAIChatClient",
    "ReasoningParseError",
    "render_user_message",
    "parse_reasoning_response",
    "reason_about_zone",
]
