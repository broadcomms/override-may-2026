"""TORCS JSONL replay → LapFeatures parser.

Reads the per-tick JSONL the telemetry logger in
``RaceYourCode/gym_torcs/torcs_jm_par.py:parse_server_str`` emits when
``OVERRIDE_LOG_TELEMETRY`` is set. Each line is one ServerState tick:
::

    {"t": 1700000000.123, "speedX": 60.4, "curLapTime": 12.5,
     "distFromStart": 482.0, "fuel": 91.2, "gear": 4, ...}

Both the Week 1 fixture-capture path and the Week 3 live-ingest endpoint
(``POST /api/sessions/torcs-live`` in ``api/main.py``) feed this parser the
same JSONL shape via the shared ``torcs-telemetry`` volume.

**TORCS has no native 2026 MGU-K / battery / hybrid-energy state** — see
``docs/adrs/ADR-002-torcs-as-primary-sandbox.md``. SoC / harvest / deploy
are synthesized from brake-on and throttle-≥-threshold integrals via
``analysis/torcs_energy.derive_lap_energy``; every ``LapFeatures`` row this
parser emits sets ``soc_source="derived"``.

**JSONL safe-read** (v6 plan gotcha #12): the live-ingest path reads while
``torcs_jm_par.py`` is still appending — the last line is occasionally a
partial write without a trailing newline. The parser skips incomplete and
malformed lines silently rather than crashing the request.

References:
  - ``docs/04-schema.md`` §3 — ``LapFeatures`` contract
  - ``analysis/torcs_energy.py`` — shared energy-synthesis constants and
    ``derive_lap_energy`` pure function
  - ``ingest/fastf1_parser.py`` — sibling parser; same ``derive_lap_energy``
"""

from __future__ import annotations

import json
import logging
import statistics
from pathlib import Path
from typing import Iterator, Optional

from analysis.torcs_energy import derive_lap_energy

from .schema import LapFeatures

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# TORCS-native sensor thresholds (gym_torcs reports brake/throttle as 0..1)
# ──────────────────────────────────────────────────────────────────────────────

# A tick counts as "brake on" when the brake command is at or above this value.
# 0..1 scale per gym_torcs convention; > 0.05 means the driver is actively
# braking, not just at zero throttle.
BRAKE_ON_FRACTION = 0.05

# A tick counts as "full throttle" (deploy event) when accel is at or above
# this fraction. Matches the spirit of FastF1's ``Throttle >= 95`` rule.
THROTTLE_DEPLOY_FRACTION = 0.95

# Maximum dt between consecutive ticks to count toward integration (seconds).
# Caps the contribution of long pauses (e.g. paused simulator) to avoid
# inflating per-sector integrals. ~1 second is generous — gym_torcs ticks at
# ~50 Hz so real dt should be ~0.02 s.
MAX_TICK_DT_S = 1.0

# Minimum laps to consider valid. TORCS sometimes spits a partial first lap
# at simulator startup; drop laps shorter than this many seconds.
MIN_LAP_TIME_S = 10.0


# ──────────────────────────────────────────────────────────────────────────────
# JSONL ingestion
# ──────────────────────────────────────────────────────────────────────────────


def _iter_jsonl_safe(path: Path) -> Iterator[dict]:
    """Yield decoded observations from a JSONL file, skipping bad lines.

    Per v6 gotcha #12: the live-ingest endpoint reads while gym_torcs may
    still be appending — the last line is occasionally a partial write
    (no trailing ``\\n``). Skip those + any JSONDecodeError mid-stream
    silently; the surrounding session is still ingestible.
    """
    with open(path) as f:
        for line in f:
            if not line.endswith("\n"):
                # Incomplete tail line — torcs_jm_par is still writing.
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # Malformed mid-stream (e.g. shutdown race) — skip and continue.
                continue


def _coerce_float(value: object, default: float = 0.0) -> float:
    """Robust float extraction from sensor values.

    gym_torcs' ``destringify`` returns ints, floats, strings, or lists of
    floats depending on the sensor. Most numeric sensors come through as
    single-element lists like ``[60.42]`` — unwrap if so.
    """
    if isinstance(value, list):
        if not value:
            return default
        value = value[0]
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


# ──────────────────────────────────────────────────────────────────────────────
# Lap segmentation
# ──────────────────────────────────────────────────────────────────────────────


def _segment_into_laps(observations: list[dict]) -> list[list[dict]]:
    """Group per-tick observations into per-lap buckets.

    Lap boundaries detected by ``curLapTime`` resetting toward zero — TORCS
    sets ``curLapTime`` back to ~0 each time the car crosses the start line.
    Falls back to ``distFromStart`` wrapping when ``curLapTime`` is missing
    (the lab's baseline driver always emits both).
    """
    laps: list[list[dict]] = []
    current: list[dict] = []
    prior_lap_time = 0.0
    prior_dist = 0.0
    for tick in observations:
        cur_lap_time = _coerce_float(tick.get("curLapTime", 0.0))
        cur_dist = _coerce_float(tick.get("distFromStart", 0.0))
        # Lap boundary: curLapTime reset OR distFromStart wrap (large negative jump).
        if current and (cur_lap_time + 1.0 < prior_lap_time or cur_dist + 50.0 < prior_dist):
            laps.append(current)
            current = []
        current.append(tick)
        prior_lap_time = cur_lap_time
        prior_dist = cur_dist
    if current:
        laps.append(current)
    return laps


def _lap_track_length(lap_ticks: list[dict]) -> float:
    """Best estimate of the lap's track length from the max distFromStart seen."""
    if not lap_ticks:
        return 0.0
    return max(_coerce_float(t.get("distFromStart", 0.0)) for t in lap_ticks)


def _integrate_per_sector(
    lap_ticks: list[dict], track_length_m: float
) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]:
    """Integrate per-sector brake-on time, full-throttle time, and sector duration.

    Sector boundaries are simple thirds of the lap distance. Returns:
      ``(sector_time_s, brake_on_time_per_sector_s, full_throttle_time_per_sector_s)``

    All three are 3-tuples for sectors 1, 2, 3 in order.
    """
    if track_length_m <= 0.0 or len(lap_ticks) < 2:
        zeros = (0.0, 0.0, 0.0)
        return zeros, zeros, zeros

    s1_end = track_length_m / 3.0
    s2_end = 2.0 * track_length_m / 3.0

    sector_seconds = [0.0, 0.0, 0.0]
    brake_seconds = [0.0, 0.0, 0.0]
    throttle_seconds = [0.0, 0.0, 0.0]

    for i in range(1, len(lap_ticks)):
        prev = lap_ticks[i - 1]
        curr = lap_ticks[i]
        # dt from curLapTime (preferred) or wall-clock 't' (fallback).
        prev_t = _coerce_float(prev.get("curLapTime"))
        curr_t = _coerce_float(curr.get("curLapTime"))
        dt = curr_t - prev_t
        if dt <= 0.0 or dt > MAX_TICK_DT_S:
            # Pause / reset / first tick — use wall-clock fallback if cheap.
            prev_w = _coerce_float(prev.get("t"))
            curr_w = _coerce_float(curr.get("t"))
            dt = curr_w - prev_w if 0.0 < (curr_w - prev_w) <= MAX_TICK_DT_S else 0.0
            if dt <= 0.0:
                continue

        # Bucket by the PREVIOUS tick's position (the dt happened during the
        # interval starting there). Sectors are 0-indexed here, 1-indexed in
        # the schema.
        prev_dist = _coerce_float(prev.get("distFromStart"))
        if prev_dist < s1_end:
            idx = 0
        elif prev_dist < s2_end:
            idx = 1
        else:
            idx = 2
        sector_seconds[idx] += dt

        # Brake (0..1) and accel (0..1) come from the previous tick — the
        # driver's command at the start of the interval governs the interval.
        brake_v = _coerce_float(prev.get("brake", prev.get("brakeCmd", 0.0)))
        accel_v = _coerce_float(prev.get("accel", prev.get("accelCmd", 0.0)))
        if brake_v >= BRAKE_ON_FRACTION:
            brake_seconds[idx] += dt
        if accel_v >= THROTTLE_DEPLOY_FRACTION:
            throttle_seconds[idx] += dt

    return (
        (sector_seconds[0], sector_seconds[1], sector_seconds[2]),
        (brake_seconds[0], brake_seconds[1], brake_seconds[2]),
        (throttle_seconds[0], throttle_seconds[1], throttle_seconds[2]),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Public entry points
# ──────────────────────────────────────────────────────────────────────────────


def parse_torcs_lap(
    lap_ticks: list[dict],
    *,
    lap_number: int,
    prior_soc_end: Optional[float],
) -> Optional[LapFeatures]:
    """Convert one lap's worth of TORCS observation ticks into ``LapFeatures``.

    Pure function. Returns ``None`` when the lap is too short or too sparse
    to extract reliable features (caller filters Nones).

    Args:
        lap_ticks: chronologically-ordered observation dicts from a single
            lap (post ``_segment_into_laps``).
        lap_number: 1-indexed lap number per the schema convention.
        prior_soc_end: previous lap's ``soc_end``; ``None`` for lap 1.

    Returns:
        ``LapFeatures`` or ``None`` if the lap is filtered.
    """
    if len(lap_ticks) < 2:
        return None

    track_length_m = _lap_track_length(lap_ticks)
    if track_length_m <= 0.0:
        return None

    sector_seconds, brake_per_sector, throttle_per_sector = _integrate_per_sector(
        lap_ticks, track_length_m
    )
    lap_time = sum(sector_seconds)
    if lap_time < MIN_LAP_TIME_S:
        return None

    # Speed: gym_torcs ``speedX`` is in m/s along the car's forward axis;
    # convert to km/h. Use the absolute value because speedX can be slightly
    # negative during spins / off-track.
    speeds_kmh = [
        abs(_coerce_float(t.get("speedX", 0.0))) * 3.6 for t in lap_ticks
    ]
    avg_speed = statistics.mean(speeds_kmh) if speeds_kmh else 0.0
    max_speed = max(speeds_kmh) if speeds_kmh else 0.0

    # Synthesize 2026 hybrid energy state via the shared module.
    energy = derive_lap_energy(
        brake_time_per_sector_s=brake_per_sector,
        full_throttle_time_per_sector_s=throttle_per_sector,
        prior_soc_end=prior_soc_end,
    )

    return LapFeatures(
        lap_number=lap_number,
        soc_start=energy.soc_start,
        soc_end=energy.soc_end,
        harvest_mj=energy.harvest_mj,
        deploy_mj=energy.deploy_mj,
        lap_time=round(lap_time, 3),
        sector1_time=round(sector_seconds[0], 3),
        sector2_time=round(sector_seconds[1], 3),
        sector3_time=round(sector_seconds[2], 3),
        avg_speed=round(avg_speed, 1),
        max_speed=round(max_speed, 1),
        # TORCS is a 2014-era simulator; the 2026-only concepts have no
        # native expression. Per ADR-002 they emit as 0.
        override_uses=0,
        boost_uses=0,
        recharge_zones=list(energy.recharge_zones),
        soc_source="derived",
    )


def parse_torcs_session(path: Path | str) -> list[LapFeatures]:
    """Read a TORCS JSONL replay and produce ``LapFeatures`` rows.

    Caller passes the path to the JSONL file the telemetry logger emitted
    (typically ``/app/data/telemetry/<run_id>.jsonl`` inside the OVERRIDE
    container, mounted from ``torcs-telemetry`` shared volume).

    Empty / unparseable replays raise ``ValueError``; partial / malformed
    lines are silently skipped via ``_iter_jsonl_safe``.

    Always sets ``soc_source="derived"``; emits zero ``override_uses`` /
    ``boost_uses`` (TORCS doesn't model the 2026-only concepts).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"TORCS replay not found: {path}")

    observations = list(_iter_jsonl_safe(path))
    if not observations:
        raise ValueError(f"TORCS replay produced 0 valid ticks: {path}")

    raw_laps = _segment_into_laps(observations)
    out: list[LapFeatures] = []
    prior_soc_end: Optional[float] = None
    for i, lap_ticks in enumerate(raw_laps, start=1):
        features = parse_torcs_lap(
            lap_ticks, lap_number=len(out) + 1, prior_soc_end=prior_soc_end,
        )
        if features is None:
            logger.debug(
                "parse_torcs_session: skipping raw lap #%d (%d ticks) — too short / too sparse",
                i, len(lap_ticks),
            )
            continue
        out.append(features)
        prior_soc_end = features.soc_end

    if not out:
        raise ValueError(
            f"TORCS replay {path} yielded 0 usable laps after segmentation "
            f"(saw {len(raw_laps)} raw bucket(s) totaling {len(observations)} ticks)"
        )
    return out


__all__ = ["parse_torcs_lap", "parse_torcs_session"]
