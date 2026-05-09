"""Fan Mode translation — turn a structured ReasoningOutput into plain
language for broadcasters and fans.

Same model as reasoning (Granite 4-h-small on watsonx.ai), slightly
higher default temperature for natural prose, strict JSON output
contract from `prompts/fan_mode.system.md`.

Lazy by design (FR-7.4) — runs on `?mode=fan` request, not on session
upload. Each call hits watsonx; cache the result on `Recommendation.fan`
once produced.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional, Protocol

from pydantic import ValidationError

from ingest.schema import FanOutput, ReasoningOutput

logger = logging.getLogger(__name__)


_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "fan_mode.system.md"


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────────
# Chat client (re-uses the same Protocol shape as core/reasoning.py)
# ──────────────────────────────────────────────────────────────────────────────


class WatsonxFanChatClient(Protocol):
    """Same chat interface used by reasoning + Guardian. Tests pass a fake."""

    def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.5,
        max_tokens: int = 512,
    ) -> str:
        ...


# ──────────────────────────────────────────────────────────────────────────────
# Tolerant JSON parsing — same fence/whitespace handling as the others
# ──────────────────────────────────────────────────────────────────────────────


_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL | re.IGNORECASE)


class FanModeParseError(ValueError):
    """Raised when the model's response can't be coerced into FanOutput."""


def parse_fan_response(text: str, *, fallback_strip_rule_when_null: bool = True) -> FanOutput:
    """Strip code fences/whitespace, parse JSON, validate against FanOutput.

    The prompt's hard-fail rules already say to omit `the_rule` when
    `regulation_citation` was null on the input. The parser does NOT
    enforce that — it's the prompt's contract; if the model emits
    `the_rule` regardless, we accept it. (Caller can override via
    `fallback_strip_rule_when_null=False` if a stricter contract is
    needed later.)
    """
    raw = text.strip()
    if not raw:
        raise FanModeParseError("empty Fan Mode response")
    fence = _FENCE_RE.match(raw)
    if fence:
        raw = fence.group(1).strip()
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        snippet = raw[:200].replace("\n", "\\n")
        raise FanModeParseError(
            f"Fan Mode response is not valid JSON: {e.msg}; first 200 chars: {snippet!r}"
        ) from e
    try:
        return FanOutput.model_validate(obj)
    except ValidationError as e:
        raise FanModeParseError(f"Fan Mode output failed schema validation:\n{e}") from e


# ──────────────────────────────────────────────────────────────────────────────
# User-message rendering
# ──────────────────────────────────────────────────────────────────────────────


def render_user_message(reasoning: ReasoningOutput) -> str:
    """The Fan Mode prompt expects the full ReasoningOutput JSON as input.

    No lap_window or regulation re-rendering — the prompt explicitly says:
    *"A JSON object exactly as produced by OVERRIDE-Reasoning."*
    """
    return (
        "## reasoning_output\n"
        + json.dumps(reasoning.model_dump(mode="json"), indent=2)
    )


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────


def translate_to_fan_mode(
    reasoning: ReasoningOutput,
    *,
    client: WatsonxFanChatClient,
    temperature: Optional[float] = None,
    max_tokens: int = 512,
) -> FanOutput:
    """Translate a structured Engineer-Mode reasoning into Fan Mode prose.

    Args:
        reasoning: validated ReasoningOutput from core.reasoning.
        client: injected chat client. Production: re-use the same
            WatsonxAIChatClient instance from core.reasoning (same model,
            same project_id). Tests: pass a fake.
        temperature: defaults to `FAN_MODE_TEMPERATURE` env (0.5) — slightly
            higher than reasoning's 0.3, for more natural prose. Still
            bounded so the structured JSON shape stays stable.
        max_tokens: 512 is enough for the four short fields.

    Returns:
        FanOutput — `the_rule` may be None per the prompt's hard-fail
        when `regulation_citation` was None on the input.
    """
    if temperature is None:
        try:
            temperature = float(os.environ.get("FAN_MODE_TEMPERATURE", "0.5"))
        except ValueError:
            temperature = 0.5

    system = _load_system_prompt()
    user = render_user_message(reasoning)

    logger.info(
        "translate_to_fan_mode: confidence=%s citation=%s temp=%.2f",
        reasoning.confidence,
        "present" if reasoning.regulation_citation is not None else "absent",
        temperature,
    )

    raw = client.chat(system=system, user=user, temperature=temperature, max_tokens=max_tokens)
    return parse_fan_response(raw)


__all__ = [
    "FanModeParseError",
    "WatsonxFanChatClient",
    "render_user_message",
    "parse_fan_response",
    "translate_to_fan_mode",
]
