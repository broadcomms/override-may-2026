"""Tests for core.validator (Pass-1 deterministic check).

Coverage per rule:
  - energy_bounds: passes on schema-clean lap_window
  - harvest_cap: NOOP pre-G-4 (cap_mj=None); fires when cap exceeded
  - citation_existence: auto-pass when citation is None;
                        passes on chunk-text match;
                        fails on fabricated citation
  - language_safety: catches each banned phrase across cause/consequence/
                     recommendation/reasoning_chain
  - source_consistency: passes on chunk-section match; fails on mismatch

Plus aggregated tests:
  - well-formed reasoning over real chunks → all 5 rules pass
  - failed_rules list + notes are populated correctly
  - retry_count is recorded faithfully
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.validator import BANNED_PHRASES, ValidatorResult, validate
from ingest.schema import (
    LapFeatures,
    LapWindow,
    ReasoningOutput,
    RegulationChunk,
    RegulationCitation,
    RegulationSource,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


def _lap(n: int = 1, **kw) -> LapFeatures:
    base = dict(
        lap_number=n,
        soc_start=0.8,
        soc_end=0.7,
        harvest_mj=0.5,
        deploy_mj=0.4,
        lap_time=85.0,
        sector1_time=27.0,
        sector2_time=29.5,
        sector3_time=28.5,
        avg_speed=210.0,
        max_speed=320.0,
        override_uses=0,
        boost_uses=0,
        recharge_zones=[2],
        soc_source="derived",
    )
    base.update(kw)
    return LapFeatures(**base)


def _lap_window(n: int = 5, **kw) -> LapWindow:
    return LapWindow(
        session_id="s_test",
        laps=[_lap(i, **kw) for i in range(1, n + 1)],
        soc_max=4.0,
    )


def _source(section: str = "<from-docling>") -> RegulationSource:
    return RegulationSource(
        document_title="FIA 2026 Formula 1 Technical Regulations",
        issue="Issue 12 — 2025-06-10",
        section=section,
        public_url="https://www.fia.com/regulation/category/110",
        fetched_at=datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc),
    )


CITATION_TEXT = (
    "Energy released from the ES into the MGU-K shall not exceed the per-lap cap."
)


def _chunk(text: str = CITATION_TEXT, section: str = "<from-docling>") -> RegulationChunk:
    return RegulationChunk(
        chunk_id="c_001",
        text=text,
        source=_source(section),
        keywords=["MGU-K", "cap"],
    )


def _reasoning(
    *,
    cause: str = "Lap 3 deployed 0.45 MJ in S2 for limited time gain.",
    consequence: str = "Approximately 0.06 s benefit at low ROI of 7.5 MJ per second.",
    recommendation: str = "Consider delaying first deploy by one lap to reserve charge.",
    confidence: str = "medium",
    citation_passage: str = CITATION_TEXT,
    citation_section: str = "<from-docling>",
    with_citation: bool = True,
    reasoning_chain: list[str] | None = None,
) -> ReasoningOutput:
    return ReasoningOutput(
        cause=cause,
        consequence=consequence,
        recommendation=recommendation,
        regulation_citation=(
            RegulationCitation(passage=citation_passage, source=_source(citation_section))
            if with_citation
            else None
        ),
        confidence=confidence,
        confidence_justification="Forecast unavailable; reasoning from observed lap_window only.",
        reasoning_chain=reasoning_chain
        or [
            "Lap 3 deploy event detected at 0.45 MJ in S2.",
            "Lap-time delta vs median is +0.06 s.",
            "Per-MJ ROI below typical efficiency band.",
        ],
    )


# ──────────────────────────────────────────────────────────────────────────────
# Happy path: well-formed reasoning + chunks → all 5 rules pass
# ──────────────────────────────────────────────────────────────────────────────


def test_validator_happy_path_all_rules_pass():
    result = validate(
        reasoning=_reasoning(),
        lap_window=_lap_window(),
        regulation_chunks=[_chunk()],
        cap_mj=8.5,
    )
    assert isinstance(result, ValidatorResult)
    assert result.passed is True
    assert result.failed_rules == []
    assert result.notes == []


def test_validator_pre_g4_pathway_passes_when_citation_is_null():
    """Reasoning emitted regulation_citation=None and confidence='low' (the
    documented pre-G-4 pathway). With cap_mj=None and no chunks, all rules
    auto-pass."""
    result = validate(
        reasoning=_reasoning(with_citation=False, confidence="low"),
        lap_window=_lap_window(),
        regulation_chunks=None,
        cap_mj=None,
    )
    assert result.passed is True


# ──────────────────────────────────────────────────────────────────────────────
# energy_bounds rule
# ──────────────────────────────────────────────────────────────────────────────


def test_energy_bounds_passes_on_schema_clean_window():
    result = validate(
        reasoning=_reasoning(with_citation=False, confidence="low"),
        lap_window=_lap_window(),
    )
    assert "energy_bounds" not in result.failed_rules


# ──────────────────────────────────────────────────────────────────────────────
# harvest_cap rule
# ──────────────────────────────────────────────────────────────────────────────


def test_harvest_cap_noop_pre_g4():
    """cap_mj=None → harvest_cap rule does not fire even on big harvest."""
    big = _lap_window(n=3, harvest_mj=999.0)
    result = validate(
        reasoning=_reasoning(with_citation=False, confidence="low"),
        lap_window=big,
        cap_mj=None,
    )
    assert "harvest_cap" not in result.failed_rules


def test_harvest_cap_fires_when_cap_exceeded():
    big = _lap_window(n=3, harvest_mj=10.0)
    result = validate(
        reasoning=_reasoning(with_citation=False, confidence="low"),
        lap_window=big,
        cap_mj=8.5,
    )
    assert "harvest_cap" in result.failed_rules
    assert any("harvest_cap:" in n for n in result.notes)


def test_harvest_cap_passes_at_exact_cap():
    """Boundary: harvest_mj == cap_mj should pass (the rule is 'must not exceed')."""
    on_cap = _lap_window(n=3, harvest_mj=8.5)
    result = validate(
        reasoning=_reasoning(with_citation=False, confidence="low"),
        lap_window=on_cap,
        cap_mj=8.5,
    )
    assert "harvest_cap" not in result.failed_rules


# ──────────────────────────────────────────────────────────────────────────────
# citation_existence rule
# ──────────────────────────────────────────────────────────────────────────────


def test_citation_existence_auto_pass_when_citation_null():
    result = validate(
        reasoning=_reasoning(with_citation=False, confidence="low"),
        lap_window=_lap_window(),
        regulation_chunks=None,
    )
    assert "citation_existence" not in result.failed_rules


def test_citation_existence_passes_on_verbatim_match():
    result = validate(
        reasoning=_reasoning(citation_passage=CITATION_TEXT),
        lap_window=_lap_window(),
        regulation_chunks=[_chunk(text=CITATION_TEXT)],
    )
    assert "citation_existence" not in result.failed_rules


def test_citation_existence_fires_on_fabricated_citation_no_chunks():
    result = validate(
        reasoning=_reasoning(citation_passage="this passage does not exist"),
        lap_window=_lap_window(),
        regulation_chunks=None,
    )
    assert "citation_existence" in result.failed_rules


def test_citation_existence_fires_when_passage_missing_from_chunks():
    result = validate(
        reasoning=_reasoning(citation_passage="totally fabricated quote"),
        lap_window=_lap_window(),
        regulation_chunks=[_chunk(text=CITATION_TEXT)],
    )
    assert "citation_existence" in result.failed_rules


# ──────────────────────────────────────────────────────────────────────────────
# language_safety rule — one test per banned phrase + exhaustive sweep
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("phrase", BANNED_PHRASES)
def test_language_safety_catches_each_banned_phrase_in_recommendation(phrase):
    bad = _reasoning(
        recommendation=f"You {phrase} maintain SoC above 0.5 throughout the stint.",
        with_citation=False,
        confidence="low",
    )
    result = validate(reasoning=bad, lap_window=_lap_window())
    assert "language_safety" in result.failed_rules


@pytest.mark.parametrize("phrase", BANNED_PHRASES)
def test_language_safety_is_case_insensitive(phrase):
    upper = phrase.upper()
    bad = _reasoning(
        consequence=f"That sequence {upper} produce a 0.2 s deficit.",
        with_citation=False,
        confidence="low",
    )
    result = validate(reasoning=bad, lap_window=_lap_window())
    assert "language_safety" in result.failed_rules


def test_language_safety_scans_reasoning_chain_too():
    bad = _reasoning(
        reasoning_chain=[
            "Lap 3 deployed 0.45 MJ.",
            "The optimal pattern would have been to delay.",  # banned 'optimal'
            "Forecast confirmed depletion by lap 7.",
        ],
        with_citation=False,
        confidence="low",
    )
    result = validate(reasoning=bad, lap_window=_lap_window())
    assert "language_safety" in result.failed_rules


def test_language_safety_passes_on_compliant_text():
    # 'consider' / 'could explore' / 'would have' are explicitly allowed
    ok = _reasoning(
        cause="Lap 3 deployed 0.45 MJ in S2 for limited time gain.",
        consequence="Approximately 0.06 s benefit at low ROI of 7.5 MJ per second.",
        recommendation="Consider delaying first deploy by one lap; the team could explore reserving charge for the next straight.",
        with_citation=False,
        confidence="low",
    )
    result = validate(reasoning=ok, lap_window=_lap_window())
    assert "language_safety" not in result.failed_rules


def test_language_safety_doesnt_match_substrings():
    """'must' inside 'mustard' or 'always' inside 'alwaysland' shouldn't fire.

    (Rule uses \\b word boundaries.)
    """
    ok = _reasoning(
        cause="Driver chose mustard-yellow tyre allocation; the alwaysland approach.",
        with_citation=False,
        confidence="low",
    )
    result = validate(reasoning=ok, lap_window=_lap_window())
    assert "language_safety" not in result.failed_rules


# ──────────────────────────────────────────────────────────────────────────────
# source_consistency rule
# ──────────────────────────────────────────────────────────────────────────────


def test_source_consistency_passes_on_section_match():
    result = validate(
        reasoning=_reasoning(citation_section="C.5.4"),
        lap_window=_lap_window(),
        regulation_chunks=[_chunk(section="C.5.4")],
    )
    assert "source_consistency" not in result.failed_rules


def test_source_consistency_fires_on_section_mismatch():
    result = validate(
        reasoning=_reasoning(citation_section="C.7.1"),
        lap_window=_lap_window(),
        regulation_chunks=[_chunk(section="C.5.4")],
    )
    assert "source_consistency" in result.failed_rules


def test_source_consistency_auto_pass_when_citation_null():
    result = validate(
        reasoning=_reasoning(with_citation=False, confidence="low"),
        lap_window=_lap_window(),
        regulation_chunks=None,
    )
    assert "source_consistency" not in result.failed_rules


# ──────────────────────────────────────────────────────────────────────────────
# Aggregation behavior
# ──────────────────────────────────────────────────────────────────────────────


def test_validator_records_retry_count():
    result = validate(
        reasoning=_reasoning(),
        lap_window=_lap_window(),
        regulation_chunks=[_chunk()],
        cap_mj=8.5,
        retry_count=2,
    )
    assert result.retry_count == 2


def test_validator_lists_all_failed_rules_not_just_first():
    """Multiple failures should all be reported."""
    bad = _reasoning(
        recommendation="You must deploy at the optimal point every lap.",
        citation_passage="this is fabricated",
        citation_section="C.7.1",
    )
    result = validate(
        reasoning=bad,
        lap_window=_lap_window(),
        regulation_chunks=[_chunk(section="C.5.4")],
        cap_mj=8.5,
    )
    assert not result.passed
    # language_safety + citation_existence + source_consistency all fail
    assert "language_safety" in result.failed_rules
    assert "citation_existence" in result.failed_rules
    assert "source_consistency" in result.failed_rules


def test_validator_result_is_frozen():
    result = validate(
        reasoning=_reasoning(with_citation=False, confidence="low"),
        lap_window=_lap_window(),
    )
    with pytest.raises(Exception):
        result.passed = False  # type: ignore[misc]


def test_validator_notes_format_is_rule_id_prefix():
    bad = _reasoning(
        recommendation="You must always pit on lap 5.",
        with_citation=False,
        confidence="low",
    )
    result = validate(reasoning=bad, lap_window=_lap_window())
    assert any(n.startswith("language_safety:") for n in result.notes)
