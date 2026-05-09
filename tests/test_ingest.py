"""Tests for ingest.schema and ingest.fastf1_parser.

Exercises:
  - Schema field constraints (lap_number, SoC bounds, severity literal, etc.)
  - parse_fastf1_lap() pure function over synthetic LapInputs (no network)
  - SoC carry-over across consecutive laps
  - Recharge-zone derivation threshold

The full session fetch (parse_fastf1_session) is **not** exercised here —
it touches the network and is gated on developer-machine FastF1 cache.
Network test lives in tests/test_ingest_network.py (added when needed)
and is marked @pytest.mark.network so CI can skip it.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ingest.fastf1_parser import (
    BATTERY_CAPACITY_MJ,
    LapInputs,
    parse_fastf1_lap,
)
from ingest.schema import (
    Forecast,
    LapFeatures,
    LapWindow,
    RegulationChunk,
    RegulationCitation,
    RegulationSource,
    Zone,
    ZoneType,
)


# ──────────────────────────────────────────────────────────────────────────────
# §3 LapFeatures
# ──────────────────────────────────────────────────────────────────────────────


def _well_formed_lap_kwargs(**overrides):
    base = dict(
        lap_number=1,
        soc_start=1.0,
        soc_end=0.95,
        harvest_mj=0.5,
        deploy_mj=0.7,
        lap_time=85.4,
        sector1_time=27.0,
        sector2_time=29.5,
        sector3_time=28.9,
        avg_speed=210.0,
        max_speed=320.0,
        override_uses=0,
        boost_uses=0,
        recharge_zones=[2],
        soc_source="derived",
    )
    base.update(overrides)
    return base


def test_lap_features_well_formed_round_trip():
    lf = LapFeatures(**_well_formed_lap_kwargs())
    assert lf.lap_number == 1
    assert lf.soc_source == "derived"
    assert lf.recharge_zones == [2]


@pytest.mark.parametrize(
    "field,bad",
    [
        ("lap_number", 0),  # ge=1
        ("lap_number", -3),
        ("soc_start", -0.1),  # ge=0
        ("soc_start", 1.5),  # le=1
        ("soc_end", 1.0001),
        ("harvest_mj", -0.001),  # ge=0
        ("deploy_mj", -1.0),
        ("lap_time", 0.0),  # gt=0
        ("sector1_time", 0.0),
        ("avg_speed", -1.0),
        ("override_uses", -1),
        ("boost_uses", -2),
    ],
)
def test_lap_features_field_constraints(field, bad):
    kwargs = _well_formed_lap_kwargs(**{field: bad})
    with pytest.raises(ValidationError):
        LapFeatures(**kwargs)


def test_lap_features_soc_source_must_be_literal():
    with pytest.raises(ValidationError):
        LapFeatures(**_well_formed_lap_kwargs(soc_source="estimated"))  # type: ignore[arg-type]


def test_lap_features_is_frozen():
    lf = LapFeatures(**_well_formed_lap_kwargs())
    with pytest.raises(ValidationError):
        lf.lap_number = 99  # frozen=True; mutation rejected


# ──────────────────────────────────────────────────────────────────────────────
# §3 LapWindow
# ──────────────────────────────────────────────────────────────────────────────


def test_lap_window_accepts_1_to_30_laps():
    lf = LapFeatures(**_well_formed_lap_kwargs())
    LapWindow(session_id="s_1", laps=[lf], soc_max=4.0)
    LapWindow(session_id="s_1", laps=[lf] * 30, soc_max=4.0)


def test_lap_window_rejects_31_laps_or_more():
    lf = LapFeatures(**_well_formed_lap_kwargs())
    with pytest.raises(ValidationError):
        LapWindow(session_id="s_1", laps=[lf] * 31, soc_max=4.0)


def test_lap_window_rejects_empty():
    with pytest.raises(ValidationError):
        LapWindow(session_id="s_1", laps=[], soc_max=4.0)


def test_lap_window_rejects_zero_soc_max():
    lf = LapFeatures(**_well_formed_lap_kwargs())
    with pytest.raises(ValidationError):
        LapWindow(session_id="s_1", laps=[lf], soc_max=0.0)


# ──────────────────────────────────────────────────────────────────────────────
# §4 ZoneType / Zone
# ──────────────────────────────────────────────────────────────────────────────


def test_zonetype_values_match_schema_doc():
    assert ZoneType.LOW_ROI_DEPLOY.value == "low-roi-deploy"
    assert ZoneType.LATE_RECHARGE.value == "late-recharge"
    assert ZoneType.OVER_HARVEST.value == "over-harvest"
    assert ZoneType.UNUSED_OVERRIDE.value == "unused-override"


def test_zone_well_formed():
    z = Zone(
        zone_id="z_t16_l23",
        zone_type=ZoneType.LOW_ROI_DEPLOY,
        lap_number=23,
        sector=2,
        severity="medium",
        metrics={"deploy_mj": 0.18, "time_gain_s": 0.05, "roi_mj_per_s": 3.6},
        description="Battery deployed in a low-throughput corner.",
    )
    assert z.zone_type is ZoneType.LOW_ROI_DEPLOY
    assert z.sector == 2


def test_zone_rejects_bad_sector():
    with pytest.raises(ValidationError):
        Zone(
            zone_id="z_x",
            zone_type=ZoneType.LOW_ROI_DEPLOY,
            lap_number=1,
            sector=4,  # only 1, 2, 3 allowed
            severity="low",
            metrics={},
            description="x",
        )


def test_zone_rejects_bad_severity():
    with pytest.raises(ValidationError):
        Zone(
            zone_id="z_x",
            zone_type=ZoneType.LOW_ROI_DEPLOY,
            lap_number=1,
            sector=1,
            severity="extreme",  # type: ignore[arg-type]
            metrics={},
            description="x",
        )


# ──────────────────────────────────────────────────────────────────────────────
# §5 Forecast
# ──────────────────────────────────────────────────────────────────────────────


def test_forecast_requires_5_point_horizon():
    f = Forecast(
        point=[0.9, 0.85, 0.8, 0.78, 0.76],
        lower=[0.85, 0.80, 0.75, 0.70, 0.68],
        upper=[0.95, 0.90, 0.85, 0.86, 0.84],
        model_version="ibm-granite/granite-timeseries-ttm-r2@d6a7957",
    )
    assert f.horizon_laps == 5
    assert len(f.point) == 5


def test_forecast_rejects_non_5_lengths():
    with pytest.raises(ValidationError):
        Forecast(
            point=[0.9, 0.85, 0.8, 0.78],  # only 4
            lower=[0.85, 0.80, 0.75, 0.70],
            upper=[0.95, 0.90, 0.85, 0.86],
            model_version="x@y",
        )


# ──────────────────────────────────────────────────────────────────────────────
# §6 Regulation grounding
# ──────────────────────────────────────────────────────────────────────────────


def _well_formed_source():
    return RegulationSource(
        document_title="FIA 2026 Formula 1 Technical Regulations",
        issue="Issue 12 — 2025-06-10",
        section="<from-docling-extraction>",
        public_url="https://www.fia.com/regulation/category/110",
        fetched_at=datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc),
    )


def test_regulation_chunk_well_formed():
    src = _well_formed_source()
    rc = RegulationChunk(
        chunk_id="c_001",
        text="Energy released from the ES into the MGU-K shall not exceed the per-lap cap.",
        source=src,
        keywords=["MGU-K", "cap"],
    )
    assert rc.embedding is None
    assert len(rc.text) > 0


def test_regulation_chunk_rejects_text_over_1000_chars():
    src = _well_formed_source()
    with pytest.raises(ValidationError):
        RegulationChunk(chunk_id="c_x", text="x" * 1001, source=src)


def test_regulation_citation_carries_source_through():
    src = _well_formed_source()
    rc = RegulationCitation(
        passage="Energy released from the ES into the MGU-K shall not exceed the per-lap cap.",
        source=src,
    )
    assert rc.source.document_title == "FIA 2026 Formula 1 Technical Regulations"


# ──────────────────────────────────────────────────────────────────────────────
# parse_fastf1_lap() — pure-function tests, no network
# ──────────────────────────────────────────────────────────────────────────────


def _baseline_inputs(**overrides) -> LapInputs:
    base = dict(
        lap_number=1,
        lap_time_s=85.4,
        sector1_time_s=27.0,
        sector2_time_s=29.5,
        sector3_time_s=28.9,
        avg_speed_kmh=210.0,
        max_speed_kmh=320.0,
        # 4 brake-seconds in S1, none in S2, 3 brake-seconds in S3
        brake_time_per_sector_s=[4.0, 0.0, 3.0],
        # 6 full-throttle-seconds in S1, 12 in S2, 4 in S3
        full_throttle_time_per_sector_s=[6.0, 12.0, 4.0],
    )
    base.update(overrides)
    return LapInputs(**base)


def test_fastf1_lap_first_lap_starts_at_full_charge():
    lf = parse_fastf1_lap(_baseline_inputs(), prior_soc_end=None)
    assert lf.soc_start == 1.0
    assert lf.soc_source == "derived"
    # 2026-only concepts not present in pre-2026 data
    assert lf.override_uses == 0
    assert lf.boost_uses == 0


def test_fastf1_lap_carries_soc_across_laps():
    lap1 = parse_fastf1_lap(_baseline_inputs(lap_number=1), prior_soc_end=None)
    lap2 = parse_fastf1_lap(_baseline_inputs(lap_number=2), prior_soc_end=lap1.soc_end)
    assert lap2.soc_start == lap1.soc_end


def test_fastf1_lap_soc_clamped_to_zero_when_drained():
    """Heavy deploy with no harvest should clamp at 0.0, not go negative."""
    drained = parse_fastf1_lap(
        _baseline_inputs(
            brake_time_per_sector_s=[0.0, 0.0, 0.0],
            full_throttle_time_per_sector_s=[200.0, 200.0, 200.0],  # absurd deploy
        ),
        prior_soc_end=0.05,
    )
    assert drained.soc_end == 0.0


def test_fastf1_lap_soc_clamped_to_one_when_overcharged():
    """Heavy harvest with no deploy should clamp at 1.0, not exceed."""
    full = parse_fastf1_lap(
        _baseline_inputs(
            brake_time_per_sector_s=[200.0, 200.0, 200.0],  # absurd harvest
            full_throttle_time_per_sector_s=[0.0, 0.0, 0.0],
        ),
        prior_soc_end=0.95,
    )
    assert full.soc_end == 1.0


def test_fastf1_lap_recharge_zones_use_threshold():
    """recharge_zones contains 1-indexed sectors with harvest > 0.1 MJ.

    With HARVEST_KJ_PER_BRAKE_SECOND=200 (kJ/s), the threshold of 0.1 MJ
    requires > 0.5s of brake time per sector. Inputs: 4s S1, 0s S2, 3s S3.
    """
    lf = parse_fastf1_lap(_baseline_inputs(), prior_soc_end=None)
    assert lf.recharge_zones == [1, 3]


def test_fastf1_lap_zero_brake_zero_harvest():
    """No braking → harvest_mj=0, no recharge zones."""
    lf = parse_fastf1_lap(
        _baseline_inputs(brake_time_per_sector_s=[0.0, 0.0, 0.0]),
        prior_soc_end=None,
    )
    assert lf.harvest_mj == 0.0
    assert lf.recharge_zones == []


def test_fastf1_lap_energy_consistency_within_capacity():
    """Sanity: |delta_soc| should be <= harvest+deploy / capacity."""
    lf = parse_fastf1_lap(_baseline_inputs(), prior_soc_end=0.5)
    delta = abs(lf.soc_end - lf.soc_start)
    bound = (lf.harvest_mj + lf.deploy_mj) / BATTERY_CAPACITY_MJ
    assert delta <= bound + 1e-9


def test_fastf1_lap_returns_validated_lap_features():
    """Output must be a frozen, validated LapFeatures instance."""
    lf = parse_fastf1_lap(_baseline_inputs(), prior_soc_end=None)
    assert isinstance(lf, LapFeatures)
    with pytest.raises(ValidationError):
        lf.lap_number = 99  # frozen
