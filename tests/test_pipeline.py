"""Tests for core.pipeline.run_pipeline.

Per the P2.7 review's test plan:
  - full pipeline on synthetic 5-lap session with mocked clients
  - retry loop fires once on Pass-1 fail, succeeds (boundary)
  - retry loop fires twice on repeated Pass-2 fail, ships with
    final_confidence='low' (FR-6.3 — no silent drops)
  - forecast_fn=None — graceful degradation works
  - empty zones list — zero-zone session edge case (FR-2.3)
  - deterministic — same input twice → same output
  - one @pytest.mark.network test on FastF1-style synthetic input

Plus the captured layered-defense fixture round-trips cleanly through
Recommendation/Session validation (proves the pre-P2.7 capture stays
schema-valid post-orchestrator).
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pytest

from core.pipeline import (
    PASS_1_RETRY_DIRECTIVE,
    PASS_2_RETRY_DIRECTIVE,
    derive_final_confidence,
    run_pipeline,
)
from ingest.schema import (
    Forecast,
    LapFeatures,
    LapWindow,
    ReasoningOutput,
    Recommendation,
    RegulationCitation,
    RegulationSource,
    Session,
    SessionSummary,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


def _lap(n: int = 1, **kw) -> LapFeatures:
    base = dict(
        lap_number=n, soc_start=0.7, soc_end=0.6, harvest_mj=0.5, deploy_mj=0.4,
        lap_time=85.0 + 0.1 * n, sector1_time=27.0, sector2_time=29.0, sector3_time=29.0,
        avg_speed=210.0, max_speed=320.0, override_uses=1, boost_uses=0,
        recharge_zones=[2], soc_source="derived",
    )
    base.update(kw)
    return LapFeatures(**base)


def _laps_with_zone(n: int = 5) -> list[LapFeatures]:
    """A session that triggers low-roi-deploy on lap 3 (heavy deploy, no time gain)."""
    return [
        _lap(1),
        _lap(2),
        # heavy deploy + no time advantage → triggers low-roi-deploy
        _lap(3, soc_start=0.7, soc_end=0.55, harvest_mj=0.2, deploy_mj=0.7,
             lap_time=85.0, override_uses=0),
        _lap(4),
        _lap(5),
    ]


def _laps_clean(n: int = 5) -> list[LapFeatures]:
    """A session that triggers no zones — different lap times so all
    heuristics stay below their thresholds."""
    return [
        _lap(1, lap_time=85.0, deploy_mj=0.05, harvest_mj=0.05, override_uses=1),
        _lap(2, lap_time=85.5, deploy_mj=0.05, harvest_mj=0.05, override_uses=1),
        _lap(3, lap_time=85.2, deploy_mj=0.05, harvest_mj=0.05, override_uses=1),
        _lap(4, lap_time=85.4, deploy_mj=0.05, harvest_mj=0.05, override_uses=1),
        _lap(5, lap_time=85.1, deploy_mj=0.05, harvest_mj=0.05, override_uses=1),
    ]


def _source(section: str = "C5.18") -> RegulationSource:
    return RegulationSource(
        document_title="FIA 2026 F1 Technical Regulations — Section C",
        issue="Issue 12 — 2025-06-10",
        section=section,
        public_url="https://www.fia.com/regulation/category/110",
        fetched_at=datetime(2026, 5, 9, 12, 0, tzinfo=timezone.utc),
    )


def _well_formed_reasoning_json(*, with_citation: bool = True, confidence: str = "medium") -> str:
    body = {
        "cause": "Lap 3 deployed 0.70 MJ in S2 with limited time gain.",
        "consequence": "Approximately 0.06 s benefit at low ROI of 11.7 MJ per second.",
        "recommendation": "Consider delaying first deploy to reserve charge for the next straight.",
        "regulation_citation": (
            {
                "passage": "C5.18 MGU-K. The MGU-K shall not exceed 350 kW.",
                "source": _source("C5.18").model_dump(mode="json"),
            }
            if with_citation
            else None
        ),
        "confidence": confidence,
        "confidence_justification": "Reasoning from observed lap_window only; no forecast.",
        "reasoning_chain": [
            "Lap 3 deploy event detected.",
            "Lap-time delta vs median is small.",
            "Per-MJ ROI below efficiency band.",
        ],
    }
    return json.dumps(body)


# ──────────────────────────────────────────────────────────────────────────────
# Fake clients — instrumented for retry-counting tests
# ──────────────────────────────────────────────────────────────────────────────


class FakeChatClient:
    """Returns canned chat responses; can vary per call to simulate retries."""

    def __init__(self, responses=None, *, default_with_citation: bool = True, default_confidence: str = "medium"):
        # `responses` is an optional list of explicit JSON strings, one per call.
        # If exhausted (or None), falls back to a default well-formed response.
        self.responses = list(responses) if responses else []
        self.default_with_citation = default_with_citation
        self.default_confidence = default_confidence
        self.calls: list[dict] = []
        self._lock = threading.Lock()

    def chat(self, system: str, user: str, *, temperature: float = 0.3, max_tokens: int = 1024) -> str:
        with self._lock:
            idx = len(self.calls)
            self.calls.append({
                "system_len": len(system),
                "has_retry_directive": "RETRY —" in system,
                "temperature": temperature,
            })
        if idx < len(self.responses):
            return self.responses[idx]
        return _well_formed_reasoning_json(
            with_citation=self.default_with_citation,
            confidence=self.default_confidence,
        )


class FakeEmbeddingClient:
    """Cheap projection — just enough so retrieve_chunk returns *some* chunk."""

    def __init__(self, dim: int = 3):
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            h = abs(hash(t)) % 1000
            v = [(h % 7) / 10.0, ((h // 7) % 7) / 10.0, ((h // 49) % 7) / 10.0]
            v += [0.0] * (self.dim - len(v))
            out.append(v[: self.dim])
        return out


class FakeGuardianClient:
    """Returns Yes/No verdicts; retries can be simulated by feeding lists."""

    def __init__(self, *, energy_responses=None, reg_responses=None):
        self.energy_responses = list(energy_responses) if energy_responses else ["No: ok"]
        self.reg_responses = list(reg_responses) if reg_responses else ["No: ok"]
        self.energy_calls = 0
        self.reg_calls = 0
        self._lock = threading.Lock()

    def chat(self, system: str, user: str, *, temperature: float = 0.0, max_tokens: int = 256) -> str:
        with self._lock:
            if "Energy-Safety" in system:
                idx = self.energy_calls
                self.energy_calls += 1
                pool = self.energy_responses
            elif "Regulation Citation Consistency" in system:
                idx = self.reg_calls
                self.reg_calls += 1
                pool = self.reg_responses
            else:
                raise AssertionError("FakeGuardianClient: unrecognized system prompt")
        return pool[min(idx, len(pool) - 1)]


def _empty_chunks_path(tmp_path: Path) -> Path:
    """Empty chunks JSON — simulates pre-G-4 retrieval (returns no chunks)."""
    p = tmp_path / "empty_chunks.json"
    p.write_text(json.dumps({
        "g4_status": "pending",
        "saved_at": "2026-05-08T00:00:00Z",
        "source_document_label": None,
        "notes": "test fixture — no chunks",
        "n_chunks": 0,
        "embedding_dimensions": None,
        "chunks": [],
    }))
    return p


def _chunks_path_with_front_matter_first(tmp_path: Path) -> Path:
    """Chunks JSON mirroring the real corpus shape: front-matter chunks
    (cover page, TOC) at indices 0..N inherit the document-title section
    label; sub-article chunks follow. Locks the regulation_source-selection
    fix so chunks[0]'s "SECTION C: TECHNICAL REGULATIONS" label can't leak
    into Session.regulation_source.
    """
    p = tmp_path / "front_matter_chunks.json"

    def _chunk(chunk_id: str, section: str, text: str) -> dict:
        return {
            "chunk_id": chunk_id,
            "text": text,
            "source": {
                "document_title": "FIA 2026 Formula 1 Technical Regulations — Section C",
                "issue": "Issue 18 — 2026-05-07",
                "section": section,
                "public_url": "https://www.fia.com/regulation/category/110",
                "fetched_at": "2026-05-09T14:11:34.772446Z",
            },
            "keywords": [],
            "embedding": None,
        }

    p.write_text(json.dumps({
        "g4_status": "closed",
        "saved_at": "2026-05-09T14:11:34Z",
        "source_document_label": "FIA 2026 Formula 1 Technical Regulations — Section C",
        "notes": "test fixture — front-matter-first shape",
        "n_chunks": 3,
        "embedding_dimensions": 768,
        "chunks": [
            # Cover page — inherits the document-title label (front matter).
            _chunk("c_000_01", "SECTION C: TECHNICAL REGULATIONS",
                   "SECTION C: TECHNICAL REGULATIONS\n\nVersion: Issue 18"),
            # TOC chunk — same inherited label, even though the body mentions C3.x.
            _chunk("c_001_01", "SECTION C: TECHNICAL REGULATIONS",
                   "| C3.8  Rear Bodywork  29  C3.9  Tail"),
            # An incidental non-scope chunk (e.g. a C1.x sub-article that
            # slipped through the chunker's section filter at build time).
            # Even though it's not front-matter, it shouldn't win the
            # session-level pointer when the corpus's primary scope is C5.
            _chunk("c_007_01", "C1.3.5",
                   "C1.3.5 Any amendments to the … (out-of-scope chunk)"),
            # First real C5 chunk — this is the one regulation_source
            # must land on (primary article scope = C5, derived dynamically).
            _chunk("c_049_01", "C5.1",
                   "C5.1 Engine specification — C5.1.1 Only 4-stroke engines"),
            _chunk("c_050_01", "C5.2",
                   "C5.2 Power Unit Energy Flow"),
            _chunk("c_082_02", "C5.18",
                   "C5.18 MGU-K. The MGU-K shall not exceed 350 kW."),
        ],
    }))
    return p


# ──────────────────────────────────────────────────────────────────────────────
# derive_final_confidence
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "rc,vp,gp,expected",
    [
        ("high", True, True, "high"),
        ("medium", True, True, "medium"),
        ("low", True, True, "low"),
        ("high", False, True, "low"),
        ("high", True, False, "low"),
        ("high", False, False, "low"),
        ("medium", False, True, "low"),
    ],
)
def test_derive_final_confidence(rc, vp, gp, expected):
    assert derive_final_confidence(rc, vp, gp) == expected


# ──────────────────────────────────────────────────────────────────────────────
# Full pipeline — happy path
# ──────────────────────────────────────────────────────────────────────────────


def test_pipeline_happy_path(tmp_path):
    """Full run on a synthetic 5-lap session with mocked clients (no chunks
    → null-citation pathway → both passes auto-/easy-pass)."""
    chunks_path = _empty_chunks_path(tmp_path)
    chat = FakeChatClient(default_with_citation=False, default_confidence="low")
    emb = FakeEmbeddingClient()
    guard = FakeGuardianClient()  # both criteria say "No"

    session = asyncio.run(run_pipeline(
        laps=_laps_with_zone(),
        soc_max=4.0,
        chat_client=chat, embedding_client=emb, guardian_client=guard,
        source="fastf1",
        chunks_path=chunks_path,
        session_id="s_test_happy",
    ))

    assert isinstance(session, Session)
    assert session.summary.session_id == "s_test_happy"
    assert session.summary.source == "fastf1"
    assert session.summary.lap_count == 5
    assert session.summary.zone_count >= 1
    assert session.forecast is None       # no forecast_fn
    assert session.regulation_source is None  # empty chunks → no source
    # Every emitted recommendation passed both Pass-1 (citation=null
    # auto-passes) and Pass-2 (Guardian "No risk")
    assert all(r.validator.passed for r in session.recommendations)
    assert all(r.guardian.passed for r in session.recommendations)


def test_pipeline_regulation_source_skips_front_matter_chunks(tmp_path):
    """When the chunks corpus has front-matter (cover page, TOC) chunks
    at indices 0..N inheriting the bare document-title label, the
    session-level `regulation_source` must skip them and land on the
    first chunk with a real sub-article label.

    Locks the fix for the live-pipeline failure where
    Session.regulation_source.section came back as 'SECTION C: TECHNICAL
    REGULATIONS' instead of 'C5.1' / 'C5.18' / etc.
    """
    chunks_path = _chunks_path_with_front_matter_first(tmp_path)
    chat = FakeChatClient(default_with_citation=False, default_confidence="low")
    emb = FakeEmbeddingClient()
    guard = FakeGuardianClient()

    session = asyncio.run(run_pipeline(
        laps=_laps_with_zone(),
        soc_max=4.0,
        chat_client=chat, embedding_client=emb, guardian_client=guard,
        source="fastf1",
        chunks_path=chunks_path,
        session_id="s_test_frontmatter",
    ))

    assert session.regulation_source is not None
    # Must skip the two front-matter chunks and land on the C5.1 chunk
    assert session.regulation_source.section == "C5.1", (
        f"front-matter chunk leaked into session.regulation_source — "
        f"got section={session.regulation_source.section!r}"
    )


def test_pipeline_orders_recommendations_by_lap_number(tmp_path):
    chunks_path = _empty_chunks_path(tmp_path)
    chat = FakeChatClient(default_with_citation=False, default_confidence="low")
    session = asyncio.run(run_pipeline(
        laps=_laps_with_zone(), soc_max=4.0,
        chat_client=chat, embedding_client=FakeEmbeddingClient(),
        guardian_client=FakeGuardianClient(),
        source="fastf1", chunks_path=chunks_path,
    ))
    laps_seen = [r.zone.lap_number for r in session.recommendations]
    assert laps_seen == sorted(laps_seen)


# ──────────────────────────────────────────────────────────────────────────────
# Retry loop — Pass-1
# ──────────────────────────────────────────────────────────────────────────────


def test_pipeline_pass1_retry_succeeds_after_first_fail(tmp_path):
    """First reasoning has banned phrase 'optimal' → Pass-1 fails →
    retry with stricter directive → second response is clean → ships."""
    chunks_path = _empty_chunks_path(tmp_path)
    bad_first = json.dumps({
        "cause": "Lap 3 deployed too much.",
        "consequence": "Lost 0.05s of pace.",
        "recommendation": "You must pit on the optimal lap to maximize stint.",  # 'optimal' AND 'you must'
        "regulation_citation": None,
        "confidence": "medium",
        "confidence_justification": "From observed data only.",
        "reasoning_chain": ["a", "b", "c"],
    })
    good_second = _well_formed_reasoning_json(with_citation=False, confidence="low")
    chat = FakeChatClient(responses=[bad_first, good_second] * 10)  # plenty for parallel zones

    session = asyncio.run(run_pipeline(
        laps=_laps_with_zone(), soc_max=4.0,
        chat_client=chat, embedding_client=FakeEmbeddingClient(),
        guardian_client=FakeGuardianClient(),
        source="fastf1", chunks_path=chunks_path,
        max_retries=2,
    ))
    # Per-zone retry was triggered — second call carried the stricter directive
    assert any(c["has_retry_directive"] for c in chat.calls)
    # And the recommendation that ships passed Pass-1 (regen succeeded)
    assert any(r.validator.passed for r in session.recommendations)


# ──────────────────────────────────────────────────────────────────────────────
# Retry loop — Pass-2 exhaustion → final_confidence='low' (FR-6.3)
# ──────────────────────────────────────────────────────────────────────────────


def test_pipeline_pass2_exhaustion_ships_with_final_confidence_low(tmp_path):
    """Guardian rejects energy_safety on every attempt → after max_retries,
    recommendation ships with passed=False AND final_confidence='low'.
    Per FR-6.3: NEVER silently dropped."""
    chunks_path = _empty_chunks_path(tmp_path)
    # All 3 reasoning attempts (initial + 2 retries) are well-formed Pass-1.
    chat = FakeChatClient(default_with_citation=False, default_confidence="medium")
    # Guardian energy_safety always says Yes (risk) — every attempt fails Pass-2.
    guard = FakeGuardianClient(
        energy_responses=["Yes: harvest exceeds cap"] * 10,
        reg_responses=["No: passage is on-topic"] * 10,
    )

    session = asyncio.run(run_pipeline(
        laps=_laps_with_zone(), soc_max=4.0,
        chat_client=chat, embedding_client=FakeEmbeddingClient(),
        guardian_client=guard,
        source="fastf1", chunks_path=chunks_path,
        max_retries=2,
    ))

    # At least one recommendation fired — exhaustion path produced a result.
    assert len(session.recommendations) >= 1
    for r in session.recommendations:
        assert r.guardian.passed is False
        assert r.guardian.retry_count == 2
        assert r.guardian.final_confidence == "low"


# ──────────────────────────────────────────────────────────────────────────────
# Graceful degradation
# ──────────────────────────────────────────────────────────────────────────────


def test_pipeline_runs_without_forecast_fn(tmp_path):
    """forecast_fn=None → forecast_available=False, pipeline runs end-to-end."""
    chunks_path = _empty_chunks_path(tmp_path)
    chat = FakeChatClient(default_with_citation=False, default_confidence="low")
    session = asyncio.run(run_pipeline(
        laps=_laps_with_zone(), soc_max=4.0,
        chat_client=chat, embedding_client=FakeEmbeddingClient(),
        guardian_client=FakeGuardianClient(),
        source="fastf1", chunks_path=chunks_path,
        forecast_fn=None,
    ))
    assert session.forecast is None
    assert session.summary.forecast_available is False


def test_pipeline_with_forecast_fn(tmp_path):
    chunks_path = _empty_chunks_path(tmp_path)
    chat = FakeChatClient(default_with_citation=False, default_confidence="low")

    def fake_forecast(_laps):
        return Forecast(
            point=[0.6, 0.55, 0.5, 0.48, 0.45],
            lower=[0.55, 0.5, 0.45, 0.42, 0.4],
            upper=[0.65, 0.6, 0.55, 0.54, 0.5],
            model_version="ttm-r2@test",
        )

    session = asyncio.run(run_pipeline(
        laps=_laps_with_zone(), soc_max=4.0,
        chat_client=chat, embedding_client=FakeEmbeddingClient(),
        guardian_client=FakeGuardianClient(),
        source="fastf1", chunks_path=chunks_path,
        forecast_fn=fake_forecast,
    ))
    assert session.forecast is not None
    assert session.summary.forecast_available is True


def test_pipeline_swallows_forecast_exception(tmp_path):
    """A throwing forecast_fn must not crash the pipeline — graceful degradation."""
    chunks_path = _empty_chunks_path(tmp_path)
    chat = FakeChatClient(default_with_citation=False, default_confidence="low")

    def broken_forecast(_laps):
        raise RuntimeError("ttm crashed")

    session = asyncio.run(run_pipeline(
        laps=_laps_with_zone(), soc_max=4.0,
        chat_client=chat, embedding_client=FakeEmbeddingClient(),
        guardian_client=FakeGuardianClient(),
        source="fastf1", chunks_path=chunks_path,
        forecast_fn=broken_forecast,
    ))
    assert session.forecast is None
    assert session.summary.forecast_available is False


# ──────────────────────────────────────────────────────────────────────────────
# Edge cases
# ──────────────────────────────────────────────────────────────────────────────


def test_pipeline_empty_zones_returns_zero_recommendations(tmp_path):
    chunks_path = _empty_chunks_path(tmp_path)
    chat = FakeChatClient(default_with_citation=False, default_confidence="low")
    session = asyncio.run(run_pipeline(
        laps=_laps_clean(), soc_max=4.0,
        chat_client=chat, embedding_client=FakeEmbeddingClient(),
        guardian_client=FakeGuardianClient(),
        source="fastf1", chunks_path=chunks_path,
    ))
    # If no zones fire, no LLM calls were made for reasoning
    assert session.summary.zone_count == 0
    assert session.recommendations == []
    assert chat.calls == []


def test_pipeline_truncates_long_session(tmp_path):
    """120 cap from MAX_SESSION_LAPS — keeps most recent."""
    chunks_path = _empty_chunks_path(tmp_path)
    chat = FakeChatClient(default_with_citation=False, default_confidence="low")
    long_laps = [_lap(i, lap_time=85.0 + 0.001 * i) for i in range(1, 130)]
    session = asyncio.run(run_pipeline(
        laps=long_laps, soc_max=4.0,
        chat_client=chat, embedding_client=FakeEmbeddingClient(),
        guardian_client=FakeGuardianClient(),
        source="fastf1", chunks_path=chunks_path,
    ))
    assert session.summary.lap_count == 120
    assert "Truncated from 129" in (session.summary.note or "")


def test_pipeline_fastf1_source_records_derived_note(tmp_path):
    chunks_path = _empty_chunks_path(tmp_path)
    chat = FakeChatClient(default_with_citation=False, default_confidence="low")
    session = asyncio.run(run_pipeline(
        laps=_laps_with_zone(), soc_max=4.0,
        chat_client=chat, embedding_client=FakeEmbeddingClient(),
        guardian_client=FakeGuardianClient(),
        source="fastf1", chunks_path=chunks_path,
    ))
    note = session.summary.note or ""
    assert "derived from throttle/brake telemetry" in note


# ──────────────────────────────────────────────────────────────────────────────
# Determinism
# ──────────────────────────────────────────────────────────────────────────────


def test_pipeline_deterministic_for_same_input(tmp_path):
    chunks_path = _empty_chunks_path(tmp_path)

    def go():
        chat = FakeChatClient(default_with_citation=False, default_confidence="low")
        return asyncio.run(run_pipeline(
            laps=_laps_with_zone(), soc_max=4.0,
            chat_client=chat, embedding_client=FakeEmbeddingClient(),
            guardian_client=FakeGuardianClient(),
            source="fastf1", chunks_path=chunks_path,
            session_id="s_det",
        ))

    s1 = go()
    s2 = go()
    # zone IDs + reasoning content stable
    assert [r.zone.zone_id for r in s1.recommendations] == [r.zone.zone_id for r in s2.recommendations]
    assert [r.reasoning.recommendation for r in s1.recommendations] == [r.reasoning.recommendation for r in s2.recommendations]


# ──────────────────────────────────────────────────────────────────────────────
# Captured layered-defense fixture round-trips through the schema
# ──────────────────────────────────────────────────────────────────────────────


def test_layered_defense_fixture_loads_and_validates():
    """The fixture captured pre-orchestrator must remain schema-valid
    after P2.7. Confirms the demo asset doesn't break under the
    Recommendation/Session shape."""
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "layered_defense_demo.json"
    if not fixture_path.exists():
        pytest.skip("layered_defense_demo.json not captured (run scripts/capture_layered_defense.py)")
    payload = json.loads(fixture_path.read_text())
    # The captured reasoning round-trips
    reasoning = ReasoningOutput.model_validate(payload["stages"]["reasoning"]["output"])
    assert reasoning.confidence in {"low", "medium", "high"}
    # The captured signature observation: layered defense fired
    assert payload["key_observations"]["layered_defense_fired"] is True
    assert payload["key_observations"]["pass_1_passed"] is False
    assert "citation_existence" in payload["key_observations"]["pass_1_failed_rules"]


# ──────────────────────────────────────────────────────────────────────────────
# Live integration test
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.network
def test_pipeline_live_watsonx_end_to_end():
    """Full pipeline against real watsonx + the closed-G-4 chunk corpus."""
    from dotenv import load_dotenv
    from core.guardian import WatsonxAIGuardianClient
    from core.reasoning import WatsonxAIChatClient
    from core.regs import DEFAULT_CHUNKS_PATH, WatsonxAIEmbeddingClient

    load_dotenv()
    if not os.environ.get("WATSONX_API_KEY"):
        pytest.skip("WATSONX_API_KEY not set; skipping live pipeline test")

    session = asyncio.run(run_pipeline(
        laps=_laps_with_zone(),
        soc_max=4.0,
        chat_client=WatsonxAIChatClient(),
        embedding_client=WatsonxAIEmbeddingClient(),
        guardian_client=WatsonxAIGuardianClient(),
        source="fastf1",
        track_id="monza",
        chunks_path=DEFAULT_CHUNKS_PATH,
        max_retries=2,
    ))
    assert isinstance(session, Session)
    assert session.summary.zone_count >= 1
    # G-4 closed → regulation_source should populate
    assert session.regulation_source is not None
    assert session.regulation_source.section.startswith(("C5", "Article C5"))
    # Every recommendation carries both safety-pass results
    for r in session.recommendations:
        assert r.validator is not None
        assert r.guardian is not None
        assert r.guardian.final_confidence in {"low", "medium", "high"}
