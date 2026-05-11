"""End-to-end pipeline orchestrator.

Composes everything we've built so far into a single async entry point:

    laps → detect_zones → for each zone: (retrieve → reason → validate
    → guardian → retry-with-stricter-prompt if needed) → bundle as Session.

This module owns:
  - The retry loop (core/{validator,guardian}.py emit single-pass results;
    P2.7 decides when to regenerate)
  - The cross-zone parallelism (asyncio.gather over per-zone work)
  - The Session/Recommendation assembly
  - `final_confidence` derivation (FR-6.3 — "no silent drops")

What it explicitly does NOT do:
  - Fan Mode generation. Lazy per FR-7.4 — runs on `?mode=fan` request.
  - HTTP layer. `api/main.py` (separate, future) wraps this.
  - Persistence. `api/main.py` writes Session to disk per `04-api.md §7`.

Synchronous LLM clients are wrapped in `asyncio.to_thread()` so this
orchestrator can do `asyncio.gather` cross-zone parallelism without
forcing the rest of the codebase async.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Literal, Optional

from analysis import detect_zones
from ingest.schema import (
    Forecast,
    LapFeatures,
    LapWindow,
    ReasoningOutput,
    Recommendation,
    RegulationChunk,
    RegulationSource,
    Session,
    SessionSummary,
    Zone,
)

from .guardian import (
    GuardianResult,
    WatsonxGuardianClient,
    score_recommendation,
)
from .reasoning import WatsonxChatClient, reason_about_zone
from .regs import (
    DEFAULT_CHUNKS_PATH,
    WatsonxEmbeddingClient,
    extract_harvest_cap_mj,
    load_chunks,
    retrieve_chunk,
)
from .validator import ValidatorResult, validate

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Retry directives — appended to the reasoning system prompt on regen
# ──────────────────────────────────────────────────────────────────────────────


PASS_1_RETRY_DIRECTIVE = (
    "RETRY — your previous output failed Pass-1 deterministic validation. "
    "On this attempt, ensure: (a) regulation_citation.passage appears VERBATIM "
    "(character-for-character) in the input regulation passage; (b) the "
    "recommendation uses 'consider' / 'could explore' / 'would have' framing "
    "and contains NONE of the banned phrases (you must, optimal, always, "
    "definitely will); (c) regulation_citation.source.section matches the "
    "input regulation source. If the citation cannot be made verbatim, set "
    "regulation_citation to null and confidence to 'low'."
)

PASS_2_RETRY_DIRECTIVE = (
    "RETRY — your previous output passed deterministic validation but Granite "
    "Guardian flagged a safety concern (energy_safety or regulation_consistency). "
    "On this attempt, prioritize: (a) the recommended action must keep SoC in "
    "[0, max] and harvest within the per-lap cap; (b) the regulation_citation, "
    "if any, must be tightly aligned with the zone_type; (c) reasoning_chain "
    "must explicitly trace from data to conclusion without hand-waving."
)


# ──────────────────────────────────────────────────────────────────────────────
# Confidence derivation
# ──────────────────────────────────────────────────────────────────────────────


def derive_final_confidence(
    reasoning_confidence: Literal["low", "medium", "high"],
    validator_passed: bool,
    guardian_passed: bool,
) -> Literal["low", "medium", "high"]:
    """Final confidence = min(reasoning, guardrails).

    If either pass failed (after retries exhausted), confidence drops to
    'low' — the recommendation ships flagged, never silently dropped
    (FR-6.3). Otherwise the model's own confidence wins.
    """
    if not validator_passed or not guardian_passed:
        return "low"
    return reasoning_confidence


# ──────────────────────────────────────────────────────────────────────────────
# Per-zone retry loop
# ──────────────────────────────────────────────────────────────────────────────


async def _process_one_zone(
    zone: Zone,
    lap_window: LapWindow,
    forecast: Optional[Forecast],
    chunks: list[RegulationChunk],
    *,
    chat_client: WatsonxChatClient,
    embedding_client: WatsonxEmbeddingClient,
    guardian_client: WatsonxGuardianClient,
    cap_mj: Optional[float],
    max_retries: int,
) -> Recommendation:
    """Reason → validate → guardian → retry if needed. Always emits a
    Recommendation — never silently drops, per FR-6.3."""
    from api.observability import traced_span

    # One span per zone — wraps retrieval, reasoning, validation, and
    # Guardian into a single tree node. Nested spans inside core/{regs,
    # reasoning, guardian}.py give the per-call detail.
    with traced_span(
        "pipeline.process_zone",
        zone_id=zone.zone_id,
        zone_type=zone.zone_type.value,
        zone_severity=zone.severity,
        session_id=lap_window.session_id,
    ):
        return await _process_one_zone_inner(
            zone, lap_window, forecast, chunks,
            chat_client=chat_client,
            embedding_client=embedding_client,
            guardian_client=guardian_client,
            cap_mj=cap_mj,
            max_retries=max_retries,
        )


async def _process_one_zone_inner(
    zone: Zone,
    lap_window: LapWindow,
    forecast: Optional[Forecast],
    chunks: list[RegulationChunk],
    *,
    chat_client: WatsonxChatClient,
    embedding_client: WatsonxEmbeddingClient,
    guardian_client: WatsonxGuardianClient,
    cap_mj: Optional[float],
    max_retries: int,
) -> Recommendation:
    # Retrieval is read-only over chunks already loaded in memory; do it
    # once per zone, no retry needed.
    retrieval = await asyncio.to_thread(
        retrieve_chunk, zone.zone_type, chunks, embedding_client
    )
    regulation = retrieval[0] if retrieval is not None else None

    retry_count = 0
    extra_directive: Optional[str] = None
    reasoning: Optional[ReasoningOutput] = None
    validator_result: Optional[ValidatorResult] = None
    guardian_result: Optional[GuardianResult] = None

    while True:
        # 1. Reason
        reasoning = await asyncio.to_thread(
            reason_about_zone,
            zone, lap_window, forecast, regulation,
            client=chat_client,
            extra_system_directive=extra_directive,
        )

        # 2. Pass-1 deterministic validator
        validator_result = await asyncio.to_thread(
            validate,
            reasoning,
            lap_window,
            regulation_chunks=chunks if regulation is not None else None,
            cap_mj=cap_mj,
            retry_count=retry_count,
        )
        if not validator_result.passed and retry_count < max_retries:
            retry_count += 1
            extra_directive = PASS_1_RETRY_DIRECTIVE
            logger.info(
                "pipeline: zone=%s pass-1 fail (rules=%s), retry %d/%d",
                zone.zone_id, validator_result.failed_rules, retry_count, max_retries,
            )
            continue

        # 3. Pass-2 Guardian
        guardian_result = await asyncio.to_thread(
            score_recommendation,
            reasoning, lap_window, regulation,
            client=guardian_client,
        )
        if not guardian_result.passed and retry_count < max_retries:
            retry_count += 1
            extra_directive = PASS_2_RETRY_DIRECTIVE
            logger.info(
                "pipeline: zone=%s pass-2 fail (scores=%s), retry %d/%d",
                zone.zone_id,
                {k: round(v, 3) for k, v in guardian_result.scores.items()},
                retry_count, max_retries,
            )
            continue

        # Either both passed, or we ran out of retries — exit the loop.
        break

    assert reasoning is not None and validator_result is not None and guardian_result is not None

    # Stamp retry_count + final_confidence onto the GuardianResult
    # (these were P2.7's responsibility per the module docstring in
    # core/guardian.py — guardian.py emits both at defaults, we fill).
    final_confidence = derive_final_confidence(
        reasoning.confidence, validator_result.passed, guardian_result.passed
    )
    guardian_final = guardian_result.model_copy(
        update={"retry_count": retry_count, "final_confidence": final_confidence}
    )
    validator_final = validator_result.model_copy(update={"retry_count": retry_count})

    return Recommendation(
        zone=zone,
        reasoning=reasoning,
        fan=None,                   # populated lazily on `?mode=fan` request
        validator=validator_final,
        guardian=guardian_final,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────


ForecastFn = Callable[[list[LapFeatures]], Optional[Forecast]]


def _new_session_id() -> str:
    """Short, URL-safe slug per `04-schema.md §2`."""
    return f"s_{datetime.now(timezone.utc):%Y%m%d}_{uuid.uuid4().hex[:4]}"


def _max_session_laps() -> int:
    import os
    try:
        return int(os.environ.get("MAX_SESSION_LAPS", "120"))
    except ValueError:
        return 120


async def run_pipeline(
    laps: list[LapFeatures],
    soc_max: float,
    *,
    chat_client: WatsonxChatClient,
    embedding_client: WatsonxEmbeddingClient,
    guardian_client: WatsonxGuardianClient,
    source: Literal["torcs", "fastf1"],
    track_id: Optional[str] = None,
    chunks_path: Path = DEFAULT_CHUNKS_PATH,
    forecast_fn: Optional[ForecastFn] = None,
    cap_mj: Optional[float] = None,
    max_retries: int = 2,
    session_id: Optional[str] = None,
) -> Session:
    """Run the full OVERRIDE pipeline on one session.

    Args:
        laps: Per-lap features from `ingest/{torcs,fastf1}_parser.py`. The
            list is truncated to MAX_SESSION_LAPS (default 120) — per FR-1.3
            — with a note recorded on the session summary.
        soc_max: Battery capacity (MJ) for `LapWindow.soc_max`.
        chat_client/embedding_client/guardian_client: Injected watsonx
            clients. Tests pass fakes; production passes the real impls.
        source: 'torcs' or 'fastf1' — recorded on SessionSummary.
        track_id: Informational only.
        chunks_path: Where regulation chunks live. Default points at the
            committed sample JSON.
        forecast_fn: Optional 5-lap TTM-R2 forecaster. None → forecast
            unavailable; pipeline still runs end-to-end (FR-3).
        cap_mj: Per-lap harvest cap. None → validator's `harvest_cap` rule
            stays NOOP (pre-G-4-cap-parser default; safe).
        max_retries: Per-zone retry budget for Pass-1/Pass-2 failures.
            Default 2 per FR-6.1 / FR-6.2.
        session_id: Override the auto-generated slug. Mainly for tests.

    Returns:
        A validated Session — recommendations ordered by lap_number,
        forecast_available reflecting the actual forecast result, every
        Recommendation carrying both safety-pass results.
    """
    sid = session_id or _new_session_id()
    note: Optional[str] = None

    # Truncate per FR-1.3 — keep most recent 120 laps if longer
    cap = _max_session_laps()
    if len(laps) > cap:
        note = f"Truncated from {len(laps)} to {cap} laps (most recent retained)."
        laps = laps[-cap:]

    if source == "fastf1":
        # FastF1 always sets soc_source='derived'; surface it once on the session.
        derived_count = sum(1 for L in laps if L.soc_source == "derived")
        if derived_count == len(laps):
            extra = "Energy state derived from throttle/brake telemetry (FastF1 has no native MGU-K data)."
            note = f"{note}  {extra}" if note else extra

    # Detect zones (heuristic, deterministic, AI-free)
    zones = detect_zones(laps, soc_max=soc_max)

    # Optional forecast
    forecast: Optional[Forecast] = None
    if forecast_fn is not None:
        try:
            forecast = await asyncio.to_thread(forecast_fn, laps)
        except Exception as e:
            logger.warning("pipeline: forecast_fn raised %s: %s — continuing without forecast", type(e).__name__, e)
            forecast = None

    # Load chunks once per session
    chunks, chunks_meta = load_chunks(chunks_path)
    regulation_source: Optional[RegulationSource] = None
    if chunks and chunks_meta.get("g4_status") == "closed":
        # Use the first chunk's source as the canonical regulation_source
        # (all chunks share the same document_title/issue/public_url).
        regulation_source = chunks[0].source

    # Harvest cap: parse from the regulation when caller didn't override.
    # Flips the validator's `harvest_cap` rule from NOOP → active when a
    # cap is found. NOOP stays in place when caller passes cap_mj=None
    # AND the chunks don't yield a parseable cap (e.g. pre-G-4).
    if cap_mj is None and chunks:
        parsed_cap = extract_harvest_cap_mj(chunks)
        if parsed_cap is not None:
            cap_mj = parsed_cap
            logger.info("pipeline: parsed harvest cap from regulation: %.2f MJ/lap", cap_mj)

    # Build a lap_window — most recent 30 laps for reasoning context (per
    # schema §3.2). This is the same window every zone sees.
    window_laps = laps[-30:] if len(laps) > 30 else laps
    lap_window = LapWindow(
        session_id=sid,
        laps=window_laps,
        soc_max=soc_max,
        track_id=track_id,
    )

    # Process every zone in parallel — each per-zone task does its own
    # sequential reason→validate→guardian→retry loop.
    if zones:
        recommendations = await asyncio.gather(
            *(
                _process_one_zone(
                    z, lap_window, forecast, chunks,
                    chat_client=chat_client,
                    embedding_client=embedding_client,
                    guardian_client=guardian_client,
                    cap_mj=cap_mj,
                    max_retries=max_retries,
                )
                for z in zones
            )
        )
        recommendations = sorted(recommendations, key=lambda r: r.zone.lap_number)
    else:
        recommendations = []

    summary = SessionSummary(
        session_id=sid,
        uploaded_at=datetime.now(timezone.utc),
        source=source,
        lap_count=len(laps),
        forecast_available=forecast is not None,
        zone_count=len(zones),
        track_id=track_id,
        note=note,
    )

    return Session(
        summary=summary,
        laps=laps,
        forecast=forecast,
        recommendations=recommendations,
        regulation_source=regulation_source,
    )


__all__ = [
    "PASS_1_RETRY_DIRECTIVE",
    "PASS_2_RETRY_DIRECTIVE",
    "ForecastFn",
    "derive_final_confidence",
    "run_pipeline",
]
