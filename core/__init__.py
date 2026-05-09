"""core — production runtime: reasoning, validation, grounding, forecasting.

Public API (currently shipped):
  - reasoning: WatsonxAIChatClient, reason_about_zone, parse_reasoning_response
  - validator: validate, ValidatorResult, BANNED_PHRASES

Pending (per roadmap):
  - core.regs              P2.5 — Docling regulation grounding
  - core.guardian          P2.6 — Granite Guardian Pass-2 BYOC scoring
  - core.forecasting       P2.2 — TTM-R2 5-lap forecast (optional)
  - core.fan_mode          P3.4 — plain-language translator
  - core.pipeline          P2.7 — end-to-end orchestrator
"""

from .guardian import (
    ENERGY_SAFETY,
    REGULATION_CONSISTENCY,
    GuardianParseError,
    GuardianResult,
    WatsonxAIGuardianClient,
    WatsonxGuardianClient,
    score_recommendation,
)
from .pipeline import (
    PASS_1_RETRY_DIRECTIVE,
    PASS_2_RETRY_DIRECTIVE,
    ForecastFn,
    derive_final_confidence,
    run_pipeline,
)
from .reasoning import (
    ReasoningParseError,
    WatsonxAIChatClient,
    WatsonxChatClient,
    parse_reasoning_response,
    reason_about_zone,
    render_user_message,
)
from .regs import (
    CHUNK_MAX_CHARS,
    CHUNK_MIN_CHARS,
    DEFAULT_CHUNKS_PATH,
    DEFAULT_RELEVANCE_THRESHOLD,
    WatsonxAIEmbeddingClient,
    WatsonxEmbeddingClient,
    chunk_markdown,
    embed_chunks,
    extract_harvest_cap_mj,
    load_chunks,
    retrieve_chunk,
    save_chunks,
)
from .validator import BANNED_PHRASES, ValidatorResult, validate

__all__ = [
    # Reasoning
    "ReasoningParseError",
    "WatsonxAIChatClient",
    "WatsonxChatClient",
    "parse_reasoning_response",
    "reason_about_zone",
    "render_user_message",
    # Grounding
    "CHUNK_MAX_CHARS",
    "CHUNK_MIN_CHARS",
    "DEFAULT_CHUNKS_PATH",
    "DEFAULT_RELEVANCE_THRESHOLD",
    "WatsonxAIEmbeddingClient",
    "WatsonxEmbeddingClient",
    "chunk_markdown",
    "embed_chunks",
    "extract_harvest_cap_mj",
    "load_chunks",
    "retrieve_chunk",
    "save_chunks",
    # Validator (Pass 1)
    "BANNED_PHRASES",
    "ValidatorResult",
    "validate",
    # Guardian (Pass 2)
    "ENERGY_SAFETY",
    "REGULATION_CONSISTENCY",
    "GuardianParseError",
    "GuardianResult",
    "WatsonxAIGuardianClient",
    "WatsonxGuardianClient",
    "score_recommendation",
    # Pipeline orchestrator
    "PASS_1_RETRY_DIRECTIVE",
    "PASS_2_RETRY_DIRECTIVE",
    "ForecastFn",
    "derive_final_confidence",
    "run_pipeline",
]
