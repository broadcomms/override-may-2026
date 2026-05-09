"""Pass-1 deterministic validator.

Pure-Python check that runs against every ReasoningOutput before the
Guardian Pass-2 scoring sees it. The rule set, IDs, and pre-G-4 behaviors
mirror `core/validator.yaml` verbatim.

Rules:
  - energy_bounds       SoC stays in [0, max] across the lap_window
  - harvest_cap         per-lap harvest ≤ verified cap (NOOP pre-G-4)
  - citation_existence  citation passage appears verbatim in retrieved chunks
                        (auto-pass when reasoning emits regulation_citation=None)
  - language_safety     no 'you must' / 'optimal' / 'always' / 'definitely will'
  - source_consistency  citation.source.section matches a chunk's source.section
                        (auto-pass when reasoning emits regulation_citation=None)

Pass 1 must remain functional regardless of Guardian threshold tuning
(see gate G-5 in 06-roadmap.md). Tests exercise the rules independently.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from ingest.schema import LapWindow, ReasoningOutput, RegulationChunk

logger = logging.getLogger(__name__)


# Banned phrases per `language_safety` rule + the spirit of the
# decision-support guardrail (see .bob/AGENTS.md, README, etc.).
# Match is case-insensitive on a word/phrase boundary.
BANNED_PHRASES: tuple[str, ...] = (
    "you must",
    "optimal",
    "always",
    "definitely will",
)

_BANNED_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in BANNED_PHRASES) + r")\b",
    re.IGNORECASE,
)


# ──────────────────────────────────────────────────────────────────────────────
# Result type — mirrors docs/04-schema.md §8
# ──────────────────────────────────────────────────────────────────────────────


class ValidatorResult(BaseModel):
    """Pass-1 outcome.

    `retry_count` is 0 from the validator itself; the pipeline glue
    increments it across regenerations (see roadmap P2.6 + P2.7).
    """

    model_config = ConfigDict(frozen=True)

    passed: bool
    failed_rules: list[str] = Field(default_factory=list)
    retry_count: int = Field(default=0, ge=0, le=2)
    notes: list[str] = Field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Per-rule check helpers (each returns Optional[note]; None = pass)
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _RuleResult:
    rule_id: str
    passed: bool
    note: Optional[str] = None


def _check_energy_bounds(lap_window: LapWindow) -> _RuleResult:
    """SoC must stay in [0, 1] (Pydantic-enforced) AND must not be NaN.

    Pydantic already rejects out-of-range values at LapFeatures
    construction time — this rule is technically a tautology under that
    invariant, but we run the check explicitly so:
      a) the validator's "passed" output covers all 5 rule IDs uniformly,
      b) future LapFeatures relaxations (or alternate constructors) still
         get caught here.
    """
    bad: list[str] = []
    for L in lap_window.laps:
        # Pydantic already enforced [0, 1]; this catches the rare NaN case.
        if not (0.0 <= L.soc_start <= 1.0):
            bad.append(f"lap {L.lap_number}: soc_start={L.soc_start} out of [0,1]")
        if not (0.0 <= L.soc_end <= 1.0):
            bad.append(f"lap {L.lap_number}: soc_end={L.soc_end} out of [0,1]")
    if bad:
        return _RuleResult("energy_bounds", False, "; ".join(bad[:3]))
    return _RuleResult("energy_bounds", True)


def _check_harvest_cap(lap_window: LapWindow, cap_mj: Optional[float]) -> _RuleResult:
    """Each lap's harvest_mj must be ≤ verified cap.

    Pre-G-4 (cap_mj=None): NOOP, returns pass. Per `validator.yaml`
    pre_g4_behavior: noop, and per the schema §8 note.
    """
    if cap_mj is None:
        return _RuleResult("harvest_cap", True, note=None)

    bad: list[str] = []
    for L in lap_window.laps:
        if L.harvest_mj > cap_mj + 1e-6:
            bad.append(f"lap {L.lap_number}: harvest_mj={L.harvest_mj:.3f} > cap={cap_mj:.3f}")
    if bad:
        return _RuleResult("harvest_cap", False, "; ".join(bad[:3]))
    return _RuleResult("harvest_cap", True)


def _check_citation_existence(
    reasoning: ReasoningOutput, chunks: Optional[list[RegulationChunk]]
) -> _RuleResult:
    """The cited passage must appear verbatim in the retrieved chunks.

    If reasoning.regulation_citation is None → auto-pass (the prompt's
    documented "no chunk → null citation" pathway).
    If chunks is None (pre-G-4) and reasoning emitted a non-null citation
    anyway, that's a fail — the model fabricated.
    """
    cit = reasoning.regulation_citation
    if cit is None:
        return _RuleResult("citation_existence", True)

    if chunks is None:
        return _RuleResult(
            "citation_existence",
            False,
            "reasoning emitted a regulation_citation but no regulation chunks were "
            "supplied (pre-G-4); citation cannot exist",
        )

    haystack = "\n".join(c.text for c in chunks)
    if cit.passage in haystack:
        return _RuleResult("citation_existence", True)

    snippet = cit.passage[:120].replace("\n", " ")
    return _RuleResult(
        "citation_existence",
        False,
        f"citation passage not found verbatim in {len(chunks)} retrieved chunks: '{snippet}…'",
    )


def _check_language_safety(reasoning: ReasoningOutput) -> _RuleResult:
    """Reject decision-replacement language across cause/consequence/
    recommendation/reasoning_chain."""
    haystack = "\n".join(
        [
            reasoning.cause,
            reasoning.consequence,
            reasoning.recommendation,
            *reasoning.reasoning_chain,
        ]
    )
    matches = _BANNED_RE.findall(haystack)
    if matches:
        unique = sorted({m.lower() for m in matches})
        return _RuleResult(
            "language_safety",
            False,
            f"banned phrases used: {unique}",
        )
    return _RuleResult("language_safety", True)


def _check_source_consistency(
    reasoning: ReasoningOutput, chunks: Optional[list[RegulationChunk]]
) -> _RuleResult:
    """citation.source.section must equal one of the retrieved chunks'
    source.section values.

    Auto-pass when reasoning emitted regulation_citation=None (caught
    upstream by the citation_existence rule for the no-chunks-but-citation
    case)."""
    cit = reasoning.regulation_citation
    if cit is None:
        return _RuleResult("source_consistency", True)
    if chunks is None:
        return _RuleResult(
            "source_consistency",
            False,
            "no chunks supplied; cannot verify source consistency",
        )

    chunk_sections = {c.source.section for c in chunks}
    if cit.source.section in chunk_sections:
        return _RuleResult("source_consistency", True)
    return _RuleResult(
        "source_consistency",
        False,
        f"cited section {cit.source.section!r} not in chunk sections {sorted(chunk_sections)}",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────


def validate(
    reasoning: ReasoningOutput,
    lap_window: LapWindow,
    *,
    regulation_chunks: Optional[list[RegulationChunk]] = None,
    cap_mj: Optional[float] = None,
    retry_count: int = 0,
) -> ValidatorResult:
    """Run all 5 Pass-1 rules and aggregate the result.

    Args:
        reasoning: the model's structured output.
        lap_window: same lap_window passed to the model (needed for
            energy_bounds + harvest_cap).
        regulation_chunks: chunks the grounding step retrieved. None
            means pre-G-4 (or no chunk was relevant); citation_existence
            and source_consistency become auto-pass when reasoning
            emitted regulation_citation=None, fail otherwise.
        cap_mj: per-lap harvest cap from the verified regulation. None
            means pre-G-4 (harvest_cap NOOP).
        retry_count: recorded on the result; pipeline-glue concern.

    Returns:
        A ValidatorResult listing any failed rules + per-rule notes.
    """
    rules = [
        _check_energy_bounds(lap_window),
        _check_harvest_cap(lap_window, cap_mj),
        _check_citation_existence(reasoning, regulation_chunks),
        _check_language_safety(reasoning),
        _check_source_consistency(reasoning, regulation_chunks),
    ]

    failed = [r for r in rules if not r.passed]
    if failed:
        logger.info(
            "validator: %d/%d rules failed: %s",
            len(failed),
            len(rules),
            [r.rule_id for r in failed],
        )

    return ValidatorResult(
        passed=not failed,
        failed_rules=[r.rule_id for r in failed],
        retry_count=retry_count,
        notes=[f"{r.rule_id}: {r.note}" for r in failed if r.note],
    )


__all__ = [
    "BANNED_PHRASES",
    "ValidatorResult",
    "validate",
]
