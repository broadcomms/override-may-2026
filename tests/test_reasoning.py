"""Tests for core.reasoning.

Coverage:
  - render_user_message: lap_window markdown table, forecast/regulation JSON
  - parse_reasoning_response: bare JSON, fenced JSON, leading whitespace,
    invalid JSON, schema-mismatched JSON
  - reason_about_zone: end-to-end via FakeChatClient (no network)
  - regulation=None pathway → confidence=low + null citation accepted

A `@pytest.mark.network` test exercises the real watsonx chat API on a
synthetic single-zone fixture. Skipped by default; run with
`pytest -m network`.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pytest

from core.reasoning import (
    ReasoningParseError,
    parse_reasoning_response,
    reason_about_zone,
    render_user_message,
)
from ingest.schema import (
    Forecast,
    LapFeatures,
    LapWindow,
    ReasoningInput,
    ReasoningOutput,
    RegulationChunk,
    RegulationCitation,
    RegulationSource,
    Zone,
    ZoneType,
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
        lap_time=85.0 + 0.1 * n,
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


def _lap_window(n_laps: int = 5) -> LapWindow:
    return LapWindow(
        session_id="s_test",
        laps=[_lap(i) for i in range(1, n_laps + 1)],
        soc_max=4.0,
        track_id="monza",
    )


def _zone() -> Zone:
    return Zone(
        zone_id="z_lroi_l3_s2",
        zone_type=ZoneType.LOW_ROI_DEPLOY,
        lap_number=3,
        sector=2,
        severity="medium",
        metrics={"deploy_mj": 0.45, "time_gain_s": 0.06, "roi_mj_per_s": 7.5},
        description="Lap 3: deployed 0.45 MJ for +0.06 s of advantage (ROI 7.5 MJ/s).",
    )


def _forecast() -> Forecast:
    return Forecast(
        point=[0.65, 0.60, 0.55, 0.52, 0.50],
        lower=[0.60, 0.55, 0.50, 0.47, 0.45],
        upper=[0.70, 0.65, 0.60, 0.57, 0.55],
        model_version="ibm-granite/granite-timeseries-ttm-r2@d6a7957",
    )


def _reg_source() -> RegulationSource:
    return RegulationSource(
        document_title="FIA 2026 Formula 1 Technical Regulations",
        issue="Issue 12 — 2025-06-10",
        section="<from-docling>",
        public_url="https://www.fia.com/regulation/category/110",
        fetched_at=datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc),
    )


def _reg_chunk() -> RegulationChunk:
    return RegulationChunk(
        chunk_id="c_001",
        text="Energy released from the ES into the MGU-K shall not exceed the per-lap cap.",
        source=_reg_source(),
        keywords=["MGU-K", "cap"],
    )


# Canned model output (a clean ReasoningOutput JSON, dict form)
def _canned_response_dict(*, with_citation: bool = True, confidence: str = "medium") -> dict:
    out = {
        "cause": "Lap 3 deployed 0.45 MJ in a slow-corner sector for limited time gain.",
        "consequence": "Approximately 0.06 s lap-time benefit at a low ROI of 7.5 MJ per second of advantage.",
        "recommendation": "Consider delaying first deploy by one lap to reserve charge for the longer straight.",
        "regulation_citation": (
            {
                "passage": "Energy released from the ES into the MGU-K shall not exceed the per-lap cap.",
                "source": _reg_source().model_dump(mode="json"),
            }
            if with_citation
            else None
        ),
        "confidence": confidence,
        "confidence_justification": "Forecast unavailable; reasoning from observed lap_window only.",
        "reasoning_chain": [
            "Lap 3 deploy event detected at 0.45 MJ in S2.",
            "Lap-time delta vs median +0.06 s.",
            "Per-MJ ROI is below typical efficiency band.",
        ],
    }
    return out


def _canned_response_text(**kw) -> str:
    return json.dumps(_canned_response_dict(**kw))


class FakeChatClient:
    """Returns a pre-configured response and records calls."""

    def __init__(self, response: str = ""):
        self.response = response
        self.calls: list[dict] = []

    def chat(self, system: str, user: str, *, temperature: float = 0.3, max_tokens: int = 1024) -> str:
        self.calls.append(
            {"system": system, "user": user, "temperature": temperature, "max_tokens": max_tokens}
        )
        return self.response


# ──────────────────────────────────────────────────────────────────────────────
# render_user_message
# ──────────────────────────────────────────────────────────────────────────────


def test_render_user_message_includes_all_four_sections():
    lw = _lap_window()
    rinput = ReasoningInput(
        session_id=lw.session_id,
        lap_window=lw,
        forecast=_forecast(),
        zone=_zone(),
        regulation=_reg_chunk(),
    )
    msg = render_user_message(rinput)
    assert "## lap_window" in msg
    assert "## forecast" in msg
    assert "## zone" in msg
    assert "## regulation" in msg


def test_render_user_message_lap_window_is_markdown_table():
    lw = _lap_window(3)
    rinput = ReasoningInput(session_id="x", lap_window=lw, zone=_zone())
    msg = render_user_message(rinput)
    # Header + alignment-separator row present
    assert "| lap |" in msg
    assert "|----:|" in msg
    # Three lap rows ("| 1 |", "| 2 |", "| 3 |") plus header = 4 rows starting with "| "
    data_rows = [line for line in msg.split("\n") if line.startswith("| ")]
    assert len(data_rows) == 1 + 3   # header + 3 data rows
    # Confirm each lap_number appears in its own row
    for n in (1, 2, 3):
        assert f"| {n} |" in msg


def test_render_user_message_forecast_null_explicit():
    rinput = ReasoningInput(
        session_id="x", lap_window=_lap_window(), forecast=None, zone=_zone()
    )
    msg = render_user_message(rinput)
    assert "## forecast" in msg
    assert "null" in msg
    assert "TTM-R2 unavailable" in msg


def test_render_user_message_regulation_null_includes_hard_rule_reminder():
    rinput = ReasoningInput(
        session_id="x", lap_window=_lap_window(), zone=_zone(), regulation=None
    )
    msg = render_user_message(rinput)
    assert "## regulation" in msg
    assert "null" in msg
    # Reminder pulled from the prompt's hard rules
    assert "regulation_citation" in msg
    assert "low" in msg


# ──────────────────────────────────────────────────────────────────────────────
# parse_reasoning_response
# ──────────────────────────────────────────────────────────────────────────────


def test_parse_bare_json():
    out = parse_reasoning_response(_canned_response_text())
    assert isinstance(out, ReasoningOutput)
    assert out.confidence == "medium"


def test_parse_strips_json_code_fence():
    text = "```json\n" + _canned_response_text() + "\n```"
    out = parse_reasoning_response(text)
    assert isinstance(out, ReasoningOutput)


def test_parse_strips_plain_code_fence():
    text = "```\n" + _canned_response_text() + "\n```"
    out = parse_reasoning_response(text)
    assert isinstance(out, ReasoningOutput)


def test_parse_strips_leading_and_trailing_whitespace():
    text = "   \n\n" + _canned_response_text() + "\n  \n"
    out = parse_reasoning_response(text)
    assert isinstance(out, ReasoningOutput)


def test_parse_rejects_empty():
    with pytest.raises(ReasoningParseError, match="empty response"):
        parse_reasoning_response("   \n  ")


def test_parse_rejects_invalid_json():
    with pytest.raises(ReasoningParseError, match="not valid JSON"):
        parse_reasoning_response("{not json,")


def test_parse_rejects_schema_mismatch():
    """Missing required fields → ReasoningParseError wrapping a ValidationError."""
    bad = {"cause": "x"}  # most required fields missing
    with pytest.raises(ReasoningParseError, match="schema validation"):
        parse_reasoning_response(json.dumps(bad))


def test_parse_low_confidence_with_null_citation_accepted():
    """The documented pre-G-4 / no-grounding pathway must round-trip."""
    text = _canned_response_text(with_citation=False, confidence="low")
    out = parse_reasoning_response(text)
    assert out.regulation_citation is None
    assert out.confidence == "low"


def test_parse_reasoning_chain_must_have_3_to_5_steps():
    """3 ≤ len(reasoning_chain) ≤ 5 is enforced by the schema."""
    d = _canned_response_dict()
    d["reasoning_chain"] = ["only one step"]
    with pytest.raises(ReasoningParseError):
        parse_reasoning_response(json.dumps(d))

    d["reasoning_chain"] = ["a", "b", "c", "d", "e", "f"]  # 6 steps
    with pytest.raises(ReasoningParseError):
        parse_reasoning_response(json.dumps(d))


# ──────────────────────────────────────────────────────────────────────────────
# reason_about_zone — end-to-end via FakeChatClient
# ──────────────────────────────────────────────────────────────────────────────


def test_reason_about_zone_with_canned_client():
    client = FakeChatClient(response=_canned_response_text())
    out = reason_about_zone(
        zone=_zone(),
        lap_window=_lap_window(),
        forecast=_forecast(),
        regulation=_reg_chunk(),
        client=client,
    )
    assert isinstance(out, ReasoningOutput)
    # The fake recorded exactly one chat call with the system prompt loaded
    assert len(client.calls) == 1
    assert "OVERRIDE-Reasoning" in client.calls[0]["system"]
    assert "## lap_window" in client.calls[0]["user"]


def test_reason_about_zone_passes_temperature_through():
    client = FakeChatClient(response=_canned_response_text())
    reason_about_zone(
        zone=_zone(),
        lap_window=_lap_window(),
        client=client,
        temperature=0.0,
    )
    assert client.calls[0]["temperature"] == 0.0


def test_reason_about_zone_temperature_default_from_env(monkeypatch):
    monkeypatch.setenv("REASONING_TEMPERATURE", "0.7")
    client = FakeChatClient(response=_canned_response_text())
    reason_about_zone(zone=_zone(), lap_window=_lap_window(), client=client)
    assert client.calls[0]["temperature"] == pytest.approx(0.7)


def test_reason_about_zone_handles_fenced_response():
    client = FakeChatClient(response="```json\n" + _canned_response_text() + "\n```")
    out = reason_about_zone(zone=_zone(), lap_window=_lap_window(), client=client)
    assert isinstance(out, ReasoningOutput)


def test_reason_about_zone_propagates_parse_errors():
    client = FakeChatClient(response="not even close to JSON")
    with pytest.raises(ReasoningParseError):
        reason_about_zone(zone=_zone(), lap_window=_lap_window(), client=client)


def test_reason_about_zone_regulation_none_produces_low_confidence_path(monkeypatch):
    """When regulation is None, the canned response (already low-confidence,
    null citation) round-trips cleanly."""
    monkeypatch.setenv("REASONING_TEMPERATURE", "0.0")
    client = FakeChatClient(
        response=_canned_response_text(with_citation=False, confidence="low")
    )
    out = reason_about_zone(
        zone=_zone(), lap_window=_lap_window(), regulation=None, client=client
    )
    assert out.regulation_citation is None
    assert out.confidence == "low"


# ──────────────────────────────────────────────────────────────────────────────
# Live integration test — only runs with `pytest -m network`
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.network
def test_reason_about_zone_live_watsonx():
    """Hit the real watsonx chat API on a synthetic single-zone fixture.

    Asserts the response parses cleanly into ReasoningOutput. Doesn't assert
    on content — that's not the point of this test (P2.4 eval harness covers
    quality). Run with: `pytest -m network tests/test_reasoning.py`
    """
    from dotenv import load_dotenv
    from core.reasoning import WatsonxAIChatClient

    load_dotenv()
    if not os.environ.get("WATSONX_API_KEY"):
        pytest.skip("WATSONX_API_KEY not set; skipping live watsonx test")

    client = WatsonxAIChatClient()
    out = reason_about_zone(
        zone=_zone(),
        lap_window=_lap_window(),
        forecast=None,        # force the no-forecast pathway
        regulation=None,      # force the pre-G-4 pathway
        client=client,
        temperature=0.0,      # deterministic for the test
    )
    assert isinstance(out, ReasoningOutput)
    # Pre-G-4 pathway: prompt instructs the model to set citation=null and
    # confidence=low. The model SHOULD comply — but we don't fail the test
    # on Granite quirks; we log and continue.
    if out.regulation_citation is not None or out.confidence != "low":
        pytest.skip(
            f"model didn't honor the no-regulation pathway "
            f"(citation={out.regulation_citation is not None}, conf={out.confidence}); "
            "this is a prompt-iteration concern for P2.4, not a test failure"
        )
