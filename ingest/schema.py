"""Cross-cutting Pydantic v2 schemas for the OVERRIDE pipeline.

Single source of truth — every consumer (parsers, analysis, forecasting,
reasoning, validator, Guardian, API, UI) imports from here. The contracts
mirror docs/04-schema.md §3–§6 verbatim. If a downstream consumer disagrees
with this file, the consumer is wrong.

Conventions (per docs/04-schema.md §2):
  - times in seconds (float)
  - energies in MJ (float); never mix kJ/J in transit
  - powers in kW (float)
  - speeds in km/h (float)
  - lap_number is 1-indexed (FIA convention)
  - JSON keys are snake_case
  - Optional[T] with None for unknowns; never sentinel strings
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ──────────────────────────────────────────────────────────────────────────────
# §3  Lap-level features
# ──────────────────────────────────────────────────────────────────────────────


class LapFeatures(BaseModel):
    """One row per completed lap, produced by ingest/{torcs,fastf1}_parser.py.

    See docs/04-schema.md §3 for the canonical contract. The `soc_source`
    field carries provenance (R1 mitigation) — measured directly when the
    underlying source exposes battery state, derived from throttle/brake
    integrals when not.
    """

    model_config = ConfigDict(frozen=True)

    lap_number: int = Field(ge=1, description="1-indexed (FIA convention)")
    soc_start: float = Field(ge=0.0, le=1.0, description="battery state-of-charge at lap start")
    soc_end: float = Field(ge=0.0, le=1.0, description="battery state-of-charge at lap end")
    harvest_mj: float = Field(ge=0.0, description="total harvested energy this lap, MJ")
    deploy_mj: float = Field(ge=0.0, description="total deployed energy this lap, MJ")
    lap_time: float = Field(gt=0.0, description="full lap time, seconds")
    sector1_time: float = Field(gt=0.0)
    sector2_time: float = Field(gt=0.0)
    sector3_time: float = Field(gt=0.0)
    avg_speed: float = Field(ge=0.0, description="km/h")
    max_speed: float = Field(ge=0.0, description="km/h")
    override_uses: int = Field(ge=0, description="count of Override Mode activations this lap")
    boost_uses: int = Field(ge=0, description="count of additional MGU-K boost windows")
    recharge_zones: list[int] = Field(
        default_factory=list,
        description="sector indices (1, 2, 3) where harvest > 0.1 MJ",
    )
    soc_source: Literal["measured", "derived"] = Field(
        description="provenance flag — 'derived' when energy state inferred from throttle/brake integrals (risk R1)",
    )


class LapWindow(BaseModel):
    """Rolling 30-lap context fed into TTM-R2 forecasting and reasoning.

    Reasoning never receives more than 30 laps (prompt-size bound). For
    longer sessions, the most recent 30 laps are used. TTM-R2 requires
    exactly 30 laps; reasoning accepts shorter windows.
    """

    model_config = ConfigDict(frozen=True)

    session_id: str
    laps: list[LapFeatures] = Field(min_length=1, max_length=30)
    soc_max: float = Field(gt=0.0, description="battery capacity, MJ — used for [0, max] bounds")
    track_id: Optional[str] = Field(default=None, description="e.g. 'monza'; informational only")


# ──────────────────────────────────────────────────────────────────────────────
# §4  Zone detection
# ──────────────────────────────────────────────────────────────────────────────


class ZoneType(str, Enum):
    """The four inefficient-zone patterns OVERRIDE detects.

    Lower-case hyphenated values match the schema doc, the prompts, and the
    UI rendering. Do not change the string values without updating every
    consumer in the same PR (see docs/04-schema.md §13 versioning).
    """

    LOW_ROI_DEPLOY = "low-roi-deploy"
    LATE_RECHARGE = "late-recharge"
    OVER_HARVEST = "over-harvest"
    UNUSED_OVERRIDE = "unused-override"


Severity = Literal["low", "medium", "high"]


class Zone(BaseModel):
    """One inefficient-zone detection. Produced by analysis/zone_detector.py.

    `metrics` is a free-form dict[str, float] in v1; per-`zone_type`
    discriminated unions are tracked as ADR-002 candidate (docs/04-schema.md §14).
    """

    model_config = ConfigDict(frozen=True)

    zone_id: str = Field(min_length=1, description="short slug, e.g. 'z_t16_l23'")
    zone_type: ZoneType
    lap_number: int = Field(ge=1)
    sector: Literal[1, 2, 3]
    severity: Severity
    metrics: dict[str, float] = Field(default_factory=dict)
    description: str = Field(min_length=1, description="deterministic English summary; no LLM")


# ──────────────────────────────────────────────────────────────────────────────
# §5  Forecasting
# ──────────────────────────────────────────────────────────────────────────────


class Forecast(BaseModel):
    """5-lap SoC trajectory from TTM-R2.

    Optional — only produced when `len(laps) >= 30` AND prediction-interval
    width is below `TTM_MAX_INTERVAL_WIDTH` (see .env). Otherwise the field
    carrying a Forecast is set to None and the UI renders the empty state.
    No partial / fabricated forecast is ever returned (FR-3.3).
    """

    model_config = ConfigDict(frozen=True)

    horizon_laps: int = Field(default=5, description="always 5")
    point: list[float] = Field(min_length=5, max_length=5, description="predicted SoC")
    lower: list[float] = Field(min_length=5, max_length=5, description="prediction-interval lower bound")
    upper: list[float] = Field(min_length=5, max_length=5, description="prediction-interval upper bound")
    mae_validation: Optional[float] = Field(default=None, ge=0.0, description="held-out MAE (P2.2)")
    model_version: str = Field(description="e.g. 'ibm-granite/granite-timeseries-ttm-r2@<revision>'")


# ──────────────────────────────────────────────────────────────────────────────
# §6  Regulation grounding
# ──────────────────────────────────────────────────────────────────────────────


class RegulationSource(BaseModel):
    """Provenance for a regulation citation.

    HARD RULE (docs/04-schema.md §6): No prompt, schema default, test
    fixture, or user-facing string carries a hardcoded FIA article string —
    ever. Before gate G-4, prompts use generic phrasing and the
    `regulation_source` API field is null. After G-4, `section` is read out
    of the Docling extraction at runtime and lives only here — never as a
    literal in code, prompts, or templates.
    """

    model_config = ConfigDict(frozen=True)

    document_title: str = Field(min_length=1)
    issue: str = Field(min_length=1, description="e.g. 'Issue 12 — 2025-06-10'")
    section: str = Field(
        min_length=1,
        description="read from Docling DocTag at runtime, never hardcoded",
    )
    public_url: str
    fetched_at: datetime


class RegulationChunk(BaseModel):
    """One Docling-extracted passage. Produced by core/regs.py.

    Embedding is 768-dim from ibm/granite-embedding-278m-multilingual via
    watsonx.ai (see ADR-001). Optional — populated only when vector search
    is enabled.
    """

    model_config = ConfigDict(frozen=True)

    chunk_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=1000, description="verbatim, ≤ 1000 chars")
    source: RegulationSource
    keywords: list[str] = Field(default_factory=list)
    embedding: Optional[list[float]] = Field(
        default=None,
        description="768-dim from ibm/granite-embedding-278m-multilingual via watsonx (ADR-001)",
    )


class RegulationCitation(BaseModel):
    """Reduced citation form attached to a ReasoningOutput.

    The passage MUST appear character-for-character in the source chunk's
    text (validator `citation_existence` rule enforces this).
    """

    model_config = ConfigDict(frozen=True)

    passage: str = Field(min_length=1, description="≤ 25 words, verbatim from RegulationChunk.text")
    source: RegulationSource


# ──────────────────────────────────────────────────────────────────────────────
# §7  Reasoning (lives logically with core/reasoning.py per 04-schema.md §1,
#     but defined here because validator + Guardian + API + UI all consume it)
# ──────────────────────────────────────────────────────────────────────────────


class ReasoningInput(BaseModel):
    """Bundle passed into core.reasoning.reason_about_zone().

    Constructed by core/pipeline.py at P2.7. One ReasoningInput → one
    ReasoningOutput per detected zone.
    """

    model_config = ConfigDict(frozen=True)

    session_id: str
    lap_window: LapWindow
    forecast: Optional[Forecast] = None
    zone: Zone
    regulation: Optional[RegulationChunk] = None


class ReasoningOutput(BaseModel):
    """Granite Instruct's structured response. Normative — the prompt
    `prompts/reasoning.system.md` must produce exactly this shape.

    Per FR-4.3: when `regulation` is None on the input, `regulation_citation`
    is None on the output and `confidence` is "low". The prompt enforces
    this; the validator re-checks it at Pass 1.
    """

    model_config = ConfigDict(frozen=True)

    cause: str = Field(min_length=1, description="1 sentence")
    consequence: str = Field(min_length=1, description="1 sentence")
    recommendation: str = Field(
        min_length=1,
        description="1 sentence; tone 'consider' / 'could explore', never 'optimal' / 'always'",
    )
    regulation_citation: Optional[RegulationCitation] = None
    confidence: Literal["low", "medium", "high"]
    confidence_justification: str = Field(min_length=1, description="1 sentence")
    reasoning_chain: list[str] = Field(
        min_length=3,
        max_length=5,
        description="3–5 short steps showing evidence → conclusion",
    )


# ──────────────────────────────────────────────────────────────────────────────
# §10  Fan Mode output (consumed by core/fan_mode.py — P3.4 — and the UI)
# ──────────────────────────────────────────────────────────────────────────────


class FanOutput(BaseModel):
    """Plain-language rendering of a ReasoningOutput. Produced by Granite
    Instruct under `prompts/fan_mode.system.md`. The Mode toggle in the
    UI calls Fan Mode lazily — not as part of the upload pipeline.
    """

    model_config = ConfigDict(frozen=True)

    headline: str = Field(min_length=1, max_length=200, description="≤ 14 words")
    what_happened: str = Field(min_length=1, description="1–2 sentences, no acronyms")
    why_it_mattered: str = Field(min_length=1, description="1–2 sentences, qualitative")
    the_rule: Optional[str] = Field(
        default=None,
        description="1-sentence paraphrase of the regulation; None if regulation_citation was None",
    )


# ──────────────────────────────────────────────────────────────────────────────
# §11  API surface types (consumed by core/pipeline.py and the FastAPI layer)
# ──────────────────────────────────────────────────────────────────────────────
#
# These import lazily because Recommendation references types defined in
# core.validator and core.guardian — but those modules import from
# ingest.schema for LapWindow / ReasoningOutput. We sidestep the circular
# import by referring to the result types via Pydantic's forward-reference
# mechanism (string class names) and binding them after construction.


class Recommendation(BaseModel):
    """The unit the UI renders per zone. One per detected zone.

    `validator` is a `core.validator.ValidatorResult`; `guardian` is a
    `core.guardian.GuardianResult`. Both are forward-references resolved
    in `ingest/__init__.py` to avoid a circular import.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    zone: Zone
    reasoning: ReasoningOutput
    fan: Optional[FanOutput] = None
    validator: Any  # ValidatorResult (forward-ref; see ingest/__init__.py)
    guardian: Any   # GuardianResult  (forward-ref; see ingest/__init__.py)


class SessionSummary(BaseModel):
    """Lightweight session-level metadata."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    uploaded_at: datetime
    source: Literal["torcs", "fastf1"]
    lap_count: int = Field(ge=0, description="post-truncation, if any")
    forecast_available: bool
    zone_count: int = Field(ge=0)
    track_id: Optional[str] = None
    note: Optional[str] = Field(
        default=None,
        description="surface-level message about the session (e.g. truncation note)",
    )


class Session(BaseModel):
    """Full debrief — what core.pipeline.run_pipeline() returns."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    summary: SessionSummary
    laps: list[LapFeatures]
    forecast: Optional[Forecast] = None
    recommendations: list[Recommendation] = Field(default_factory=list)
    regulation_source: Optional[RegulationSource] = None


# ──────────────────────────────────────────────────────────────────────────────
# §8  What-if perturbations (FR-8)
#
# Spec: docs/plans/whatif-semantics.md (deleted in the FR-8 ship PR per
# plan-file-lifecycle). Three perturbations operate on list[LapFeatures]
# and return a new list; the endpoint composes them with run_pipeline().
# ──────────────────────────────────────────────────────────────────────────────


PerturbationKind = Literal[
    "delay_first_deploy",   # shift first deploy event by n laps (energy conserved)
    "skip_harvest_zone",    # zero harvest_mj on a target zone's lap (energy LOST)
    "extend_override",      # add 0.5 MJ deploy for extra_laps after a target zone
]


class WhatIfRequest(BaseModel):
    """One perturbation request — input to POST /api/sessions/{id}/what-if.

    Frozen so a stable ``model_dump_json()`` representation hashes
    deterministically into the disk cache key
    ``sha256(...).hexdigest()[:16]`` (v6 plan gotcha #4). Per-perturbation
    fields validated via the cross-field validator below.
    """

    model_config = ConfigDict(frozen=True)

    perturbation: PerturbationKind = Field(description="which what-if to apply")
    # Required for skip_harvest_zone + extend_override; ignored for delay_first_deploy.
    zone_id: Optional[str] = Field(
        default=None,
        pattern=r"^z_[A-Za-z0-9_]+$",
        description="target zone (required for skip_harvest_zone, extend_override)",
    )
    # Required for delay_first_deploy; ignored for the other two.
    n: Optional[int] = Field(
        default=None,
        ge=1,
        le=10,
        description="laps to shift the first deploy by (delay_first_deploy only)",
    )
    # Optional for extend_override; defaults to 1 per whatif-semantics.md §Perturbation 3.
    extra_laps: int = Field(
        default=1,
        ge=1,
        le=5,
        description="additional laps of Override deploy (extend_override only)",
    )

    @model_validator(mode="after")
    def _enforce_required_fields(self) -> "WhatIfRequest":
        if self.perturbation == "delay_first_deploy":
            if self.n is None:
                raise ValueError(
                    "delay_first_deploy requires `n` (laps to shift the first deploy)"
                )
        elif self.perturbation == "skip_harvest_zone":
            if not self.zone_id:
                raise ValueError("skip_harvest_zone requires `zone_id`")
        elif self.perturbation == "extend_override":
            if not self.zone_id:
                raise ValueError("extend_override requires `zone_id`")
        return self


class WhatIfResult(BaseModel):
    """Output of POST /api/sessions/{id}/what-if.

    Pairs the original session's recommendations with the perturbed-session
    recommendations so the UI's WhatIfDiff component can render
    side-by-side Before/After cards (whatif-semantics.md §"What the UI
    diff renders"). Both lists have matching zone_ids — perturbation
    doesn't add or remove zones, only changes the energy state the zone
    detector + reasoning operates on. New zones surfacing post-perturbation
    appear in ``perturbed`` without a matching ``original`` partner; the
    UI labels these "newly detected" rather than "before/after."
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    request: WhatIfRequest
    cache_key: str = Field(
        min_length=16, max_length=16, pattern=r"^[0-9a-f]{16}$",
        description="sha256(request.model_dump_json())[:16] — disk cache filename",
    )
    original: list[Recommendation] = Field(
        description="recommendations from the unperturbed pipeline run",
    )
    perturbed: list[Recommendation] = Field(
        description="recommendations after applying the perturbation",
    )
    note: Optional[str] = Field(
        default=None,
        description=(
            "honest message about edge-case handling — e.g. 'extension "
            "truncated: battery exhausted on lap 4', 'no deploy events to "
            "delay in this session'. None when no edge case fired."
        ),
    )


__all__ = [
    "LapFeatures",
    "LapWindow",
    "ZoneType",
    "Severity",
    "Zone",
    "Forecast",
    "RegulationSource",
    "RegulationChunk",
    "RegulationCitation",
    "ReasoningInput",
    "ReasoningOutput",
    "FanOutput",
    "Recommendation",
    "SessionSummary",
    "Session",
    "PerturbationKind",
    "WhatIfRequest",
    "WhatIfResult",
]
