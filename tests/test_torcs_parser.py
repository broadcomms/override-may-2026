"""Tests for ingest.torcs_parser.

Two layers:

  1. **Synthetic-fixture round-trip** — a tiny JSONL written by the test that
     mimics what ``torcs_jm_par.py:parse_server_str`` emits. Verifies lap
     segmentation, sector splits, brake/throttle integration, energy
     derivation, and the gotcha-#12 JSONL safe-read (incomplete tail line +
     malformed mid-stream line both skipped silently).

  2. **Calibration regression gate** (locked by v6 plan task 1.6) — runs
     once real ``data/samples/torcs_baseline.json`` lands from task 1.5. Until
     then it's skipped via ``pytest.mark.skipif`` on file existence so the
     suite stays green pre-capture.
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

import pytest

from ingest.torcs_parser import (
    BRAKE_ON_FRACTION,
    THROTTLE_DEPLOY_FRACTION,
    parse_torcs_lap,
    parse_torcs_session,
)
from analysis.torcs_energy import BATTERY_CAPACITY_MJ


# ──────────────────────────────────────────────────────────────────────────────
# Synthetic-fixture helpers
# ──────────────────────────────────────────────────────────────────────────────


def _synth_tick(
    *,
    t: float,
    cur_lap_time: float,
    dist_from_start: float,
    speed_x: float = 50.0,
    accel: float = 0.5,
    brake: float = 0.0,
    fuel: float = 90.0,
) -> dict:
    """One ServerState-style observation tick. gym_torcs convention puts
    numeric sensor values in single-element lists; we use that shape so the
    parser's ``_coerce_float`` unwrap codepath is exercised."""
    return {
        "t": t,
        "curLapTime": [cur_lap_time],
        "distFromStart": [dist_from_start],
        "speedX": [speed_x],
        "accel": [accel],
        "brake": [brake],
        "fuel": [fuel],
    }


def _write_synthetic_jsonl(
    path: Path, *, n_laps: int = 3, ticks_per_lap: int = 120, track_length_m: float = 3000.0,
    lap_duration_s: float = 36.0,
    include_partial_tail: bool = False, include_malformed: bool = False,
) -> None:
    """Write a JSONL that mimics a few clean TORCS laps.

    Each lap is divided into three sectors of equal distance. Sector 2 is
    "deploy" (full throttle), sector 3 is "brake" — guarantees harvest>0
    and deploy>0 per lap so derive_lap_energy produces non-zero output.

    Default density: 36 s / 120 ticks = 0.3 s/tick — well under the parser's
    MAX_TICK_DT_S = 1.0 s ceiling so the integration accumulates correctly.
    Real gym_torcs ticks at ~50 Hz; this is a sparse-but-valid stand-in.
    """
    lines: list[str] = []
    wall_t = 1_700_000_000.0
    s1_end = track_length_m / 3.0
    s2_end = 2.0 * track_length_m / 3.0
    dt = lap_duration_s / ticks_per_lap

    for lap_i in range(n_laps):
        for tick_i in range(ticks_per_lap):
            cur_lap_time = tick_i * dt
            dist = (tick_i / ticks_per_lap) * track_length_m
            # Pattern: full throttle in sector 2, brake in sector 3, cruise in sector 1.
            if dist < s1_end:
                accel, brake = 0.7, 0.0
            elif dist < s2_end:
                accel, brake = 1.0, 0.0  # deploy
            else:
                accel, brake = 0.0, 0.6  # brake hard
            tick = _synth_tick(
                t=wall_t,
                cur_lap_time=cur_lap_time,
                dist_from_start=dist,
                speed_x=60.0 if accel >= 0.95 else 30.0,
                accel=accel,
                brake=brake,
                fuel=90.0 - lap_i * 2.0 - tick_i * 0.05,
            )
            lines.append(json.dumps(tick))
            wall_t += dt

    rendered = "\n".join(lines) + "\n"

    if include_malformed:
        # Inject a malformed line mid-stream (gotcha #12)
        midpoint = len(rendered) // 2
        nl_pos = rendered.find("\n", midpoint)
        rendered = (
            rendered[: nl_pos + 1]
            + "{this is not valid json\n"
            + rendered[nl_pos + 1 :]
        )

    if include_partial_tail:
        # Strip trailing newline → partial tail (gotcha #12)
        rendered = rendered.rstrip("\n") + '\n{"t": 1700099999.0, "curLapTime": [99.0'
        # No closing brace, no newline — torcs_jm_par was mid-write

    path.write_text(rendered)


# ──────────────────────────────────────────────────────────────────────────────
# Tests — parse_torcs_lap (pure function)
# ──────────────────────────────────────────────────────────────────────────────


def test_parse_torcs_lap_returns_none_for_empty_input():
    assert parse_torcs_lap([], lap_number=1, prior_soc_end=None) is None


def test_parse_torcs_lap_returns_none_for_too_short_lap():
    # Two ticks 0.1 s apart → lap_time well under MIN_LAP_TIME_S
    ticks = [
        _synth_tick(t=0.0, cur_lap_time=0.0, dist_from_start=10.0),
        _synth_tick(t=0.1, cur_lap_time=0.1, dist_from_start=20.0),
    ]
    assert parse_torcs_lap(ticks, lap_number=1, prior_soc_end=None) is None


def test_parse_torcs_lap_produces_valid_lapfeatures(tmp_path):
    """One synthetic lap with structured sector pattern → all schema fields populate."""
    p = tmp_path / "one_lap.jsonl"
    _write_synthetic_jsonl(p, n_laps=1, ticks_per_lap=90)
    laps = parse_torcs_session(p)
    assert len(laps) == 1
    lap = laps[0]
    assert lap.lap_number == 1
    assert lap.lap_time > 0
    assert all(s > 0 for s in (lap.sector1_time, lap.sector2_time, lap.sector3_time))
    assert 0.0 <= lap.soc_start <= 1.0
    assert 0.0 <= lap.soc_end <= 1.0
    assert lap.harvest_mj >= 0
    assert lap.deploy_mj >= 0
    # The synthetic pattern guarantees deploy > harvest (full throttle in S2)
    assert lap.deploy_mj > 0, "synthetic sector 2 should yield deploy_mj > 0"
    assert lap.harvest_mj > 0, "synthetic sector 3 should yield harvest_mj > 0"
    assert lap.soc_source == "derived"
    assert lap.override_uses == 0
    assert lap.boost_uses == 0


# ──────────────────────────────────────────────────────────────────────────────
# Tests — parse_torcs_session (segmentation + JSONL safety)
# ──────────────────────────────────────────────────────────────────────────────


def test_parse_torcs_session_segments_multi_lap_jsonl(tmp_path):
    p = tmp_path / "three_laps.jsonl"
    _write_synthetic_jsonl(p, n_laps=3, ticks_per_lap=80)
    laps = parse_torcs_session(p)
    assert len(laps) == 3
    assert [L.lap_number for L in laps] == [1, 2, 3]
    # SoC should chain: lap N's soc_start should equal lap N-1's soc_end
    for prior, curr in zip(laps[:-1], laps[1:]):
        assert math.isclose(curr.soc_start, prior.soc_end, abs_tol=1e-6)


def test_parse_torcs_session_skips_incomplete_tail_line(tmp_path):
    """Gotcha #12: a partial last line (no trailing newline) must be silently skipped."""
    p = tmp_path / "with_tail.jsonl"
    _write_synthetic_jsonl(p, n_laps=2, ticks_per_lap=70, include_partial_tail=True)
    # Should not raise; the 2 clean laps still parse cleanly
    laps = parse_torcs_session(p)
    assert len(laps) == 2


def test_parse_torcs_session_skips_malformed_mid_stream_line(tmp_path):
    """Gotcha #12: a malformed JSON line mid-file must not crash the parser."""
    p = tmp_path / "with_garbage.jsonl"
    _write_synthetic_jsonl(p, n_laps=2, ticks_per_lap=70, include_malformed=True)
    laps = parse_torcs_session(p)
    assert len(laps) == 2  # both laps still recoverable


def test_parse_torcs_session_raises_on_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_torcs_session(tmp_path / "nonexistent.jsonl")


def test_parse_torcs_session_raises_on_empty_file(tmp_path):
    p = tmp_path / "empty.jsonl"
    p.write_text("")
    with pytest.raises(ValueError, match="0 valid ticks"):
        parse_torcs_session(p)


# ──────────────────────────────────────────────────────────────────────────────
# Calibration regression gate (v6 plan task 1.6)
#
# Activates once data/samples/torcs_baseline.json lands in task 1.5. Until
# the real capture exists, the test is skipped so the suite stays green.
# ──────────────────────────────────────────────────────────────────────────────


REAL_BASELINE_FIXTURE = (
    Path(__file__).resolve().parent.parent / "data" / "samples" / "torcs_baseline.json"
)


@pytest.mark.skipif(
    not REAL_BASELINE_FIXTURE.exists(),
    reason=(
        "torcs_baseline.json not yet captured — task 1.5 produces it from a real "
        "TORCS lab run (lap-task 1 baseline). Test activates automatically once present."
    ),
)
def test_torcs_baseline_energy_calibration():
    """Locks the calibration constants (HARVEST_KJ_PER_BRAKE_SECOND etc.) once
    real captures land. Per the v6 plan: per-lap harvest and deploy should sit
    in the 3–7 MJ range under the 8.5 MJ FIA cap; SoC stays in [0, 1].

    Fires if anyone later tweaks the constants for the wrong reason — e.g. to
    satisfy a single noisy lap. Calibration is an invariant of the project,
    not a per-session knob.
    """
    laps = parse_torcs_session(REAL_BASELINE_FIXTURE)
    assert len(laps) >= 1, "captured baseline should have at least one usable lap"
    harvests = [L.harvest_mj for L in laps]
    deploys = [L.deploy_mj for L in laps]

    # Under the 8.5 MJ harvest cap parsed from regs.
    assert all(0 <= h <= 8.5 for h in harvests), f"harvest violates 8.5 MJ cap: {harvests}"

    # Realistic per-lap energy range — calibration target from the v6 plan.
    median_harvest = statistics.median(harvests)
    median_deploy = statistics.median(deploys)
    assert 3.0 <= median_harvest <= 7.0, f"median harvest out of range: {median_harvest:.2f}"
    assert 3.0 <= median_deploy <= 7.0, f"median deploy out of range: {median_deploy:.2f}"

    # SoC bounds on every lap.
    assert all(0.0 <= L.soc_start <= 1.0 for L in laps), "soc_start out of bounds"
    assert all(0.0 <= L.soc_end <= 1.0 for L in laps), "soc_end out of bounds"

    # Battery capacity didn't drift.
    assert math.isclose(BATTERY_CAPACITY_MJ, 4.0), "BATTERY_CAPACITY_MJ drifted"
