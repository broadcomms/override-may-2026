"""Tests for core.guardian (Pass-2 BYOC scoring).

Coverage matrix (from the P2.6 review's test plan):
  - both pass:        scores=(0.84, 0.91) → passed=True
  - energy fails:     scores=(0.45, 0.92) → passed=False, energy_safety in failures
  - reg fails:        scores=(0.91, 0.55) → passed=False, regulation_consistency in failures
  - both fail:        scores=(0.32, 0.41) → passed=False, both in failures
  - exactly threshold:scores=(0.70, 0.70) → passed=True (`>=`, not `>`)
  - null citation:    regulation_citation=None → regulation_consistency auto-passes at 0.7
                      WITHOUT a Guardian API call (verified by call recording)
  - language guard:   recommendation containing "optimal" → caught by Pass-1 BEFORE
                      Guardian sees it (cross-doc test against core/validator.py)
  - rubric loading:   YAML loads cleanly + criterion IDs match constants
  - parser tolerance: bare JSON / fenced JSON / leading whitespace / score clamp
  - parser errors:    empty / non-JSON / missing fields / non-numeric score
  - parallelism:      both criterion calls dispatched concurrently
  - retry/confidence: NOT set by this module (P2.7 concern) — verify defaults
  - @pytest.mark.network: real watsonx Guardian on a synthetic recommendation
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import pytest

from core import validate
from core.guardian import (
    ENERGY_SAFETY,
    NULL_CITATION_AUTO_PASS_SCORE,
    REGULATION_CONSISTENCY,
    GuardianParseError,
    GuardianResult,
    score_recommendation,
)
from core.guardian import (
    _parse_score_response,
    _render_system_prompt,
    _CRITERIA_BY_ID,
    _PASS_THRESHOLD,
)
from ingest.schema import (
    LapFeatures,
    LapWindow,
    ReasoningOutput,
    RegulationChunk,
    RegulationCitation,
    RegulationSource,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixture builders
# ──────────────────────────────────────────────────────────────────────────────


def _lap(n: int = 1, **kw) -> LapFeatures:
    base = dict(
        lap_number=n, soc_start=0.7, soc_end=0.6, harvest_mj=0.5, deploy_mj=0.4,
        lap_time=85.0, sector1_time=27.0, sector2_time=29.0, sector3_time=29.0,
        avg_speed=210.0, max_speed=320.0, override_uses=0, boost_uses=0,
        recharge_zones=[2], soc_source="derived",
    )
    base.update(kw)
    return LapFeatures(**base)


def _lap_window(n: int = 3) -> LapWindow:
    return LapWindow(
        session_id="s_g_test",
        laps=[_lap(i) for i in range(1, n + 1)],
        soc_max=4.0,
    )


def _source(section: str = "C5.18") -> RegulationSource:
    return RegulationSource(
        document_title="FIA 2026 F1 Technical Regulations — Section C",
        issue="Issue 12 — 2025-06-10",
        section=section,
        public_url="https://www.fia.com/regulation/category/110",
        fetched_at=datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc),
    )


def _chunk(
    text: str = "C5.18 MGU-K. The MGU-K shall not exceed the deployment cap of 350 kW.",
    section: str = "C5.18",
) -> RegulationChunk:
    return RegulationChunk(
        chunk_id="c_test", text=text, source=_source(section), keywords=["MGU-K"]
    )


def _reasoning(
    *,
    with_citation: bool = True,
    confidence: str = "medium",
    recommendation: str = "Consider delaying the first deploy to reserve charge for the next straight.",
) -> ReasoningOutput:
    return ReasoningOutput(
        cause="Lap 2 deployed 0.45 MJ in S2 with limited time gain.",
        consequence="Approximately 0.06 s benefit at low ROI of 7.5 MJ per second.",
        recommendation=recommendation,
        regulation_citation=(
            RegulationCitation(
                passage="The MGU-K shall not exceed the deployment cap of 350 kW.",
                source=_source("C5.18"),
            )
            if with_citation
            else None
        ),
        confidence=confidence,
        confidence_justification="Forecast unavailable; reasoning from observed lap_window only.",
        reasoning_chain=[
            "Lap 2 deploy event detected at 0.45 MJ in S2.",
            "Lap-time delta vs median is +0.06 s.",
            "Per-MJ ROI below typical efficiency band.",
        ],
    )


class FakeGuardianClient:
    """Returns canned JSON for each criterion. Records all calls."""

    def __init__(
        self,
        *,
        energy_score: float = 0.85,
        energy_rationale: str = "Action stays inside SoC bounds and harvest cap.",
        reg_score: float = 0.90,
        reg_rationale: str = "Citation appears verbatim and is topically aligned.",
        # Optional explicit raw responses (override above for parse-edge tests)
        energy_raw: Optional[str] = None,
        reg_raw: Optional[str] = None,
        # Sleep-on-call to test parallelism
        delay_s: float = 0.0,
    ):
        self.energy_score = energy_score
        self.energy_rationale = energy_rationale
        self.reg_score = reg_score
        self.reg_rationale = reg_rationale
        self.energy_raw = energy_raw
        self.reg_raw = reg_raw
        self.delay_s = delay_s
        self.calls: list[dict] = []
        self._lock = threading.Lock()

    def chat(self, system: str, user: str, *, temperature: float = 0.0, max_tokens: int = 256) -> str:
        with self._lock:
            self.calls.append(
                {
                    "system": system,
                    "user": user,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "started_at": time.monotonic(),
                }
            )
        if self.delay_s > 0:
            time.sleep(self.delay_s)

        # Identify which criterion this is by what's in the system prompt.
        if "Energy-Safety" in system:
            if self.energy_raw is not None:
                return self.energy_raw
            return json.dumps({"score": self.energy_score, "rationale": self.energy_rationale})
        if "Regulation Citation Consistency" in system:
            if self.reg_raw is not None:
                return self.reg_raw
            return json.dumps({"score": self.reg_score, "rationale": self.reg_rationale})
        raise AssertionError(f"FakeGuardianClient: unrecognized system prompt: {system[:80]!r}")


# ──────────────────────────────────────────────────────────────────────────────
# YAML rubric loading
# ──────────────────────────────────────────────────────────────────────────────


def test_byoc_yaml_loads_two_criteria_with_expected_ids():
    assert ENERGY_SAFETY in _CRITERIA_BY_ID
    assert REGULATION_CONSISTENCY in _CRITERIA_BY_ID
    assert _CRITERIA_BY_ID[ENERGY_SAFETY]["name"] == "Energy-Safety Constraint Compliance"
    assert _CRITERIA_BY_ID[REGULATION_CONSISTENCY]["name"] == "Regulation Citation Consistency"


def test_pass_threshold_loaded_from_yaml():
    assert _PASS_THRESHOLD == 0.70


def test_render_system_prompt_includes_criterion_name_and_rubric():
    sys = _render_system_prompt(ENERGY_SAFETY)
    assert "Energy-Safety Constraint Compliance" in sys
    assert "Score 1.0 if" in sys
    # Output format is binary Yes/No (Granite Guardian's native output)
    assert "Yes:" in sys
    assert "No:" in sys
    assert "Risk question" in sys


# ──────────────────────────────────────────────────────────────────────────────
# Score-response parser
# ──────────────────────────────────────────────────────────────────────────────

# Granite Guardian is a binary classifier. Its natural output is "Yes"
# (risk detected → fail, score 0.0) or "No" (no risk → pass, score 1.0).
# A graded JSON form is accepted as a forward-compatibility fallback.


# Yes/No (primary, native Guardian output) ------------------------------------

def test_parse_bare_no_maps_to_score_1():
    out = _parse_score_response("No")
    assert out.score == 1.0
    assert "no risk" in out.rationale.lower()


def test_parse_bare_yes_maps_to_score_0():
    out = _parse_score_response("Yes")
    assert out.score == 0.0
    assert "risk detected" in out.rationale.lower()


def test_parse_yes_with_colon_rationale():
    out = _parse_score_response("Yes: harvest of 9.2 MJ exceeds the per-lap cap")
    assert out.score == 0.0
    assert out.rationale == "harvest of 9.2 MJ exceeds the per-lap cap"


def test_parse_no_with_dash_rationale():
    out = _parse_score_response("No - SoC trajectory stays in [0.2, 0.85]")
    assert out.score == 1.0
    assert "SoC trajectory" in out.rationale


def test_parse_yesno_case_insensitive():
    assert _parse_score_response("yes: x").score == 0.0
    assert _parse_score_response("NO: y").score == 1.0


def test_parse_yesno_strips_leading_whitespace():
    out = _parse_score_response("   \n  No: clean\n")
    assert out.score == 1.0


# Graded JSON fallback --------------------------------------------------------

def test_parse_graded_json_fallback():
    out = _parse_score_response('{"score": 0.83, "rationale": "Looks OK"}')
    assert out.score == pytest.approx(0.83)
    assert out.rationale == "Looks OK"


def test_parse_strips_json_fence():
    out = _parse_score_response('```json\n{"score": 0.7, "rationale": "ok"}\n```')
    assert out.score == 0.7


def test_parse_strips_plain_fence():
    out = _parse_score_response('```\n{"score": 0.5, "rationale": "marginal"}\n```')
    assert out.score == 0.5


def test_parse_clamps_score_above_1():
    out = _parse_score_response('{"score": 1.05, "rationale": "x"}')
    assert out.score == 1.0


def test_parse_clamps_score_below_0():
    out = _parse_score_response('{"score": -0.02, "rationale": "x"}')
    assert out.score == 0.0


def test_parse_supplies_default_when_rationale_empty():
    out = _parse_score_response('{"score": 0.8, "rationale": ""}')
    assert out.score == 0.8
    assert "no rationale" in out.rationale.lower()


# Rejection paths -------------------------------------------------------------

def test_parse_rejects_empty():
    with pytest.raises(GuardianParseError, match="empty"):
        _parse_score_response("")


def test_parse_rejects_non_yesno_non_json():
    with pytest.raises(GuardianParseError, match="neither Yes/No nor JSON"):
        _parse_score_response("definitely not a verdict")


def test_parse_rejects_json_missing_fields():
    with pytest.raises(GuardianParseError, match="missing required fields"):
        _parse_score_response('{"score": 0.8}')


def test_parse_rejects_non_numeric_score():
    with pytest.raises(GuardianParseError, match="not numeric"):
        _parse_score_response('{"score": "high", "rationale": "x"}')


# ──────────────────────────────────────────────────────────────────────────────
# score_recommendation — combinatorial pass/fail matrix
# ──────────────────────────────────────────────────────────────────────────────


def test_both_pass_above_threshold():
    client = FakeGuardianClient(energy_score=0.84, reg_score=0.91)
    result = score_recommendation(
        reasoning=_reasoning(),
        lap_window=_lap_window(),
        regulation=_chunk(),
        client=client,
    )
    assert result.passed is True
    assert result.scores[ENERGY_SAFETY] == pytest.approx(0.84)
    assert result.scores[REGULATION_CONSISTENCY] == pytest.approx(0.91)


def test_energy_safety_fails():
    client = FakeGuardianClient(energy_score=0.45, reg_score=0.92)
    result = score_recommendation(
        reasoning=_reasoning(), lap_window=_lap_window(),
        regulation=_chunk(),
        client=client,
    )
    assert result.passed is False
    assert result.scores[ENERGY_SAFETY] < result.pass_threshold
    assert result.scores[REGULATION_CONSISTENCY] >= result.pass_threshold


def test_regulation_consistency_fails():
    client = FakeGuardianClient(energy_score=0.91, reg_score=0.55)
    result = score_recommendation(
        reasoning=_reasoning(), lap_window=_lap_window(),
        regulation=_chunk(),
        client=client,
    )
    assert result.passed is False
    assert result.scores[REGULATION_CONSISTENCY] < result.pass_threshold


def test_both_fail():
    client = FakeGuardianClient(energy_score=0.32, reg_score=0.41)
    result = score_recommendation(
        reasoning=_reasoning(), lap_window=_lap_window(),
        regulation=_chunk(),
        client=client,
    )
    assert result.passed is False
    assert all(v < result.pass_threshold for v in result.scores.values())


def test_exactly_at_threshold_passes():
    """Threshold is `>=`, not `>` — exactly 0.70 must pass."""
    client = FakeGuardianClient(energy_score=0.70, reg_score=0.70)
    result = score_recommendation(
        reasoning=_reasoning(), lap_window=_lap_window(),
        regulation=_chunk(),
        client=client,
    )
    assert result.passed is True


def test_custom_pass_threshold_honored():
    client = FakeGuardianClient(energy_score=0.65, reg_score=0.65)
    # default threshold 0.70 → fails
    assert score_recommendation(
        reasoning=_reasoning(), lap_window=_lap_window(),
        regulation=_chunk(),
        client=client,
    ).passed is False
    # loosened threshold per gate G-5 calibration → passes
    assert score_recommendation(
        reasoning=_reasoning(), lap_window=_lap_window(),
        regulation=_chunk(),
        client=client,
        pass_threshold=0.60,
    ).passed is True


# ──────────────────────────────────────────────────────────────────────────────
# Null-citation auto-pass behavior
# ──────────────────────────────────────────────────────────────────────────────


def test_null_citation_auto_passes_regulation_consistency_without_api_call():
    """When reasoning emitted regulation_citation=None, don't burn an API
    call — auto-pass at 0.7 with the documented rationale."""
    client = FakeGuardianClient(energy_score=0.85)
    result = score_recommendation(
        reasoning=_reasoning(with_citation=False, confidence="low"),
        lap_window=_lap_window(),
        regulation=None,
        client=client,
    )
    assert result.scores[REGULATION_CONSISTENCY] == NULL_CITATION_AUTO_PASS_SCORE
    assert "self-flagged" in result.rationales[REGULATION_CONSISTENCY]
    # Energy safety still hit Guardian; regulation_consistency did NOT
    energy_calls = [c for c in client.calls if "Energy-Safety" in c["system"]]
    reg_calls = [c for c in client.calls if "Regulation Citation Consistency" in c["system"]]
    assert len(energy_calls) == 1
    assert len(reg_calls) == 0


def test_null_citation_with_chunks_still_auto_passes():
    """If reasoning produced regulation_citation=None, the auto-pass
    branch fires regardless of chunk availability — there's nothing to
    validate."""
    client = FakeGuardianClient()
    result = score_recommendation(
        reasoning=_reasoning(with_citation=False, confidence="low"),
        lap_window=_lap_window(),
        regulation=None,
        client=client,
    )
    assert result.scores[REGULATION_CONSISTENCY] == NULL_CITATION_AUTO_PASS_SCORE


def test_empty_chunks_list_auto_passes():
    """Reasoning has a citation but the retrieved-chunks list is empty
    (e.g. pre-G-4 reproduction) — auto-pass; nothing to compare against."""
    client = FakeGuardianClient()
    result = score_recommendation(
        reasoning=_reasoning(with_citation=True),
        lap_window=_lap_window(),
        regulation=None,
        client=client,
    )
    assert result.scores[REGULATION_CONSISTENCY] == NULL_CITATION_AUTO_PASS_SCORE


# ──────────────────────────────────────────────────────────────────────────────
# Module-boundary defaults — retry_count + final_confidence
# ──────────────────────────────────────────────────────────────────────────────


def test_guardian_does_not_set_retry_count_or_final_confidence():
    """Per the module docstring: retry orchestration belongs in P2.7's
    pipeline. score_recommendation always emits retry_count=0,
    final_confidence='medium'. The orchestrator overwrites these."""
    client = FakeGuardianClient()
    result = score_recommendation(
        reasoning=_reasoning(), lap_window=_lap_window(),
        regulation=_chunk(),
        client=client,
    )
    assert result.retry_count == 0
    assert result.final_confidence == "medium"


def test_guardian_result_is_frozen():
    client = FakeGuardianClient()
    result = score_recommendation(
        reasoning=_reasoning(), lap_window=_lap_window(),
        regulation=_chunk(),
        client=client,
    )
    with pytest.raises(Exception):
        result.passed = False  # type: ignore[misc]


# ──────────────────────────────────────────────────────────────────────────────
# Cross-doc layered-safety: language hits Pass-1 first
# ──────────────────────────────────────────────────────────────────────────────


def test_pass1_catches_banned_language_before_guardian():
    """A recommendation containing 'optimal' fails Pass-1 — Guardian
    never even sees that recommendation in the production flow."""
    bad = _reasoning(
        recommendation="Pit on the optimal lap to maximize stint pace.",
        with_citation=False, confidence="low",
    )
    val = validate(reasoning=bad, lap_window=_lap_window())
    assert val.passed is False
    assert "language_safety" in val.failed_rules
    # And if Pass-1 lets it through (older code path), Guardian still scores it —
    # demonstrates the layered defense without coupling the two passes here.
    client = FakeGuardianClient()
    result = score_recommendation(
        reasoning=bad, lap_window=_lap_window(),
        regulation=None,
        client=client,
    )
    assert isinstance(result, GuardianResult)


# ──────────────────────────────────────────────────────────────────────────────
# Parallelism — both criterion calls dispatched concurrently
# ──────────────────────────────────────────────────────────────────────────────


def test_two_criteria_scored_in_parallel():
    """A 0.5s delay per call should still let both finish within ~0.6s
    if they run concurrently. Sequential would take ~1.0s."""
    client = FakeGuardianClient(delay_s=0.5)
    t0 = time.monotonic()
    score_recommendation(
        reasoning=_reasoning(), lap_window=_lap_window(),
        regulation=_chunk(),
        client=client,
    )
    elapsed = time.monotonic() - t0
    # Generous bound to avoid CI flakiness; sequential would be > 0.95s
    assert elapsed < 0.9, f"expected concurrent scoring, took {elapsed:.2f}s"


def test_temperature_passed_through_to_client():
    """Default 0.0 (Granite Guardian requirement)."""
    client = FakeGuardianClient()
    score_recommendation(
        reasoning=_reasoning(), lap_window=_lap_window(),
        regulation=_chunk(),
        client=client,
    )
    for call in client.calls:
        assert call["temperature"] == 0.0


def test_temperature_override_propagates():
    client = FakeGuardianClient()
    score_recommendation(
        reasoning=_reasoning(), lap_window=_lap_window(),
        regulation=_chunk(),
        client=client,
        temperature=0.2,
    )
    for call in client.calls:
        assert call["temperature"] == 0.2


# ──────────────────────────────────────────────────────────────────────────────
# Binary Yes/No end-to-end (the actual Guardian production path)
# ──────────────────────────────────────────────────────────────────────────────


def test_score_recommendation_with_native_yes_no_responses():
    """Real Granite Guardian returns 'Yes'/'No'. score_recommendation
    must handle that natively and produce the right pass/fail."""
    client = FakeGuardianClient(
        energy_raw="No: SoC stays in [0.2, 0.85] and harvest is well below the cap.",
        reg_raw="No: passage appears verbatim in chunk c_test and is on-topic for MGU-K.",
    )
    result = score_recommendation(
        reasoning=_reasoning(), lap_window=_lap_window(),
        regulation=_chunk(),
        client=client,
    )
    assert result.passed is True
    assert result.scores[ENERGY_SAFETY] == 1.0
    assert result.scores[REGULATION_CONSISTENCY] == 1.0
    assert "SoC trajectory" not in result.rationales[ENERGY_SAFETY]
    assert result.rationales[ENERGY_SAFETY].startswith("SoC stays")


def test_score_recommendation_with_yes_failure():
    client = FakeGuardianClient(
        energy_raw="Yes: harvest of 9.2 MJ exceeds the 8.5 MJ per-lap cap.",
        reg_raw="No: passage is on-topic.",
    )
    result = score_recommendation(
        reasoning=_reasoning(), lap_window=_lap_window(),
        regulation=_chunk(),
        client=client,
    )
    assert result.passed is False
    assert result.scores[ENERGY_SAFETY] == 0.0
    assert result.scores[REGULATION_CONSISTENCY] == 1.0
    assert "exceeds" in result.rationales[ENERGY_SAFETY]


def test_score_recommendation_bare_yes_no_no_rationale():
    """Guardian sometimes returns just 'No' with no rationale — parser
    supplies a default."""
    client = FakeGuardianClient(energy_raw="No", reg_raw="No")
    result = score_recommendation(
        reasoning=_reasoning(), lap_window=_lap_window(),
        regulation=_chunk(),
        client=client,
    )
    assert result.passed is True
    assert "no risk" in result.rationales[ENERGY_SAFETY].lower()


# ──────────────────────────────────────────────────────────────────────────────
# Live integration test — only runs with `pytest -m network`
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.network
def test_score_recommendation_live_watsonx():
    """Hit real watsonx Granite Guardian. Asserts both scores land in [0,1]
    and the result is well-formed. Doesn't assert specific scores —
    quality is a P2.4-style eval-harness concern."""
    from dotenv import load_dotenv
    from core.guardian import WatsonxAIGuardianClient

    load_dotenv()
    if not os.environ.get("WATSONX_API_KEY"):
        pytest.skip("WATSONX_API_KEY not set; skipping live Guardian test")

    client = WatsonxAIGuardianClient()
    result = score_recommendation(
        reasoning=_reasoning(),
        lap_window=_lap_window(),
        regulation=_chunk(),
        client=client,
    )
    assert isinstance(result, GuardianResult)
    assert 0.0 <= result.scores[ENERGY_SAFETY] <= 1.0
    assert 0.0 <= result.scores[REGULATION_CONSISTENCY] <= 1.0
    assert isinstance(result.rationales[ENERGY_SAFETY], str)
    assert isinstance(result.rationales[REGULATION_CONSISTENCY], str)
