"""FastF1 → LapFeatures parser.

Pre-2026 FastF1 data has no native MGU-K / MGU-H telemetry (the 2026
hybrid is rule-different from 2014–2025). This parser **derives a
placeholder energy state** from throttle and brake integrals so the
downstream pipeline can be exercised end-to-end against historical races.

Two important caveats — surfaced everywhere it matters:

  1. `soc_source` is always **'derived'** here (FR-1.2). Real numbers
     come from TORCS (P1.3 / G-2). FastF1 SoC values are demonstrative,
     not authoritative.
  2. 2026-only concepts (`override_uses`, `boost_uses`) **do not exist**
     in pre-2026 source data — they are 0 in every row this parser
     emits. This is documented honestly in the schema and surfaced in
     the SessionSummary.note when this parser is the source.

The split is deliberate:

  - `parse_fastf1_lap()` is a **pure function** over pre-fetched per-lap
    data. Easy to test against synthetic fixtures without touching the
    network.
  - `parse_fastf1_session()` does the FastF1 fetch + iteration, then
    delegates each lap to `parse_fastf1_lap()`.

References:
  - docs/04-schema.md §3 (LapFeatures contract)
  - docs/06-roadmap.md P1.4 (this is the deliverable)
  - .env: TTM_R2_REPO etc. — battery model constants below should
    eventually become env-tunable; left as module constants for v1
    simplicity.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .schema import LapFeatures

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Battery-model placeholders for FastF1 derivation
# ──────────────────────────────────────────────────────────────────────────────
#
# These constants are PLACEHOLDERS for FastF1-derived sessions. They produce
# plausible-looking, well-bounded LapFeatures that exercise the rest of the
# pipeline. They will diverge from real 2026 numbers — that's why this
# parser sets soc_source="derived" and the SessionSummary carries a note.
#
# The TORCS parser (P1.4 second half) will use measured values from the
# simulator log directly when the simulator exposes them.

SOC_INITIAL = 1.0  # full battery at session start
SOC_MIN = 0.0
SOC_MAX = 1.0

# kJ harvested per second of brake-on (rough — real F1 regen is brake-force-
# weighted, FastF1 only exposes a 0/100 "Brake" applied flag at most timesteps).
HARVEST_KJ_PER_BRAKE_SECOND = 200.0

# kJ deployed per second of "full throttle" (Throttle >= 95) above the threshold.
DEPLOY_KJ_PER_FULL_THROTTLE_SECOND = 80.0

THROTTLE_DEPLOY_THRESHOLD = 95.0  # only count near-100% throttle as deploy

# Battery capacity for SoC normalization (MJ) — placeholder; real value pinned
# from the regulation at G-4 and exposed via LapWindow.soc_max.
BATTERY_CAPACITY_MJ = 4.0

RECHARGE_ZONE_THRESHOLD_MJ = 0.1  # see schema §3 LapFeatures.recharge_zones


# ──────────────────────────────────────────────────────────────────────────────
# Per-lap derivation (pure function — easy to test)
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LapInputs:
    """Pre-extracted FastF1 per-lap inputs the pure parser consumes.

    Decoupling this from FastF1's `Lap` and `Telemetry` types lets tests
    construct fixtures without importing fastf1 or hitting the network.
    """

    lap_number: int
    lap_time_s: float
    sector1_time_s: float
    sector2_time_s: float
    sector3_time_s: float
    avg_speed_kmh: float
    max_speed_kmh: float
    # Per-sector seconds at brake / full-throttle, used for derivation.
    # 3 entries each, sectors 1-2-3 in order.
    brake_time_per_sector_s: list[float]
    full_throttle_time_per_sector_s: list[float]


def parse_fastf1_lap(
    inputs: LapInputs,
    prior_soc_end: Optional[float],
) -> LapFeatures:
    """Derive a single LapFeatures row from pre-extracted FastF1 inputs.

    Pure function. No network, no FastF1 import. Tested against synthetic
    LapInputs fixtures.

    `prior_soc_end` is the previous lap's `soc_end`; None means this is
    the first lap of the session, so we start at SOC_INITIAL.
    """
    soc_start = prior_soc_end if prior_soc_end is not None else SOC_INITIAL

    # Per-sector energies (MJ). Convert kJ → MJ at the boundary; everything
    # downstream is in MJ per docs/04-schema.md §2 conventions.
    harvest_per_sector_mj = [
        (HARVEST_KJ_PER_BRAKE_SECOND * brake_s) / 1000.0
        for brake_s in inputs.brake_time_per_sector_s
    ]
    deploy_per_sector_mj = [
        (DEPLOY_KJ_PER_FULL_THROTTLE_SECOND * throttle_s) / 1000.0
        for throttle_s in inputs.full_throttle_time_per_sector_s
    ]

    harvest_mj = sum(harvest_per_sector_mj)
    deploy_mj = sum(deploy_per_sector_mj)

    # Net energy change as a fraction of capacity, then clamp to [0, 1].
    delta_soc = (harvest_mj - deploy_mj) / BATTERY_CAPACITY_MJ
    soc_end = max(SOC_MIN, min(SOC_MAX, soc_start + delta_soc))

    recharge_zones = [
        i + 1  # sectors are 1-indexed in the schema
        for i, mj in enumerate(harvest_per_sector_mj)
        if mj > RECHARGE_ZONE_THRESHOLD_MJ
    ]

    return LapFeatures(
        lap_number=inputs.lap_number,
        soc_start=round(soc_start, 6),
        soc_end=round(soc_end, 6),
        harvest_mj=round(harvest_mj, 6),
        deploy_mj=round(deploy_mj, 6),
        lap_time=inputs.lap_time_s,
        sector1_time=inputs.sector1_time_s,
        sector2_time=inputs.sector2_time_s,
        sector3_time=inputs.sector3_time_s,
        avg_speed=inputs.avg_speed_kmh,
        max_speed=inputs.max_speed_kmh,
        # 2026-only concepts; not present in pre-2026 source data.
        override_uses=0,
        boost_uses=0,
        recharge_zones=recharge_zones,
        soc_source="derived",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Session-level fetch + iteration (touches network the first time, then cached)
# ──────────────────────────────────────────────────────────────────────────────


def _fastf1_cache_dir() -> Path:
    """Resolve the FastF1 cache directory. Mkdir if missing.

    Honors FASTF1_CACHE if set; defaults to ./data/fastf1-cache (gitignored).
    """
    cache_env = os.environ.get("FASTF1_CACHE")
    if cache_env:
        cache = Path(cache_env)
    else:
        cache = Path(__file__).resolve().parent.parent / "data" / "fastf1-cache"
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _extract_lap_inputs(lap, telemetry) -> Optional[LapInputs]:
    """Convert one FastF1 (Lap, Telemetry) pair into LapInputs.

    Returns None if the lap is too incomplete to extract (e.g. missing
    sector times, in/out lap with no telemetry). Caller filters Nones.

    Imported types intentionally; this stays in the network-touching half.
    """
    import math

    import pandas as pd  # noqa: F401  — implicit dep, surfaces here for clarity

    if lap is None or telemetry is None or len(telemetry) == 0:
        return None

    def _seconds(timedelta_obj) -> Optional[float]:
        if timedelta_obj is None:
            return None
        try:
            secs = timedelta_obj.total_seconds()
        except AttributeError:
            return None
        if math.isnan(secs) or secs <= 0.0:
            return None
        return float(secs)

    lap_s = _seconds(lap.LapTime)
    s1 = _seconds(lap.Sector1Time)
    s2 = _seconds(lap.Sector2Time)
    s3 = _seconds(lap.Sector3Time)
    if None in (lap_s, s1, s2, s3):
        return None

    # Derive per-sector "Brake" and "full throttle" seconds from the telemetry
    # frame. FastF1 telemetry rows carry a `SessionTime` index and a
    # `Brake` boolean column plus `Throttle` (0–100). We compute Δt between
    # consecutive samples and bucket into sectors via the per-sector
    # boundaries — for v1 simplicity, we approximate equal-time sectors and
    # rely on the per-sector timing below.
    #
    # Cleaner: FastF1 telemetry includes a `SessionTime` column we can
    # bucket against the (lap_start, lap_start + s1, ..., lap_start + lap_s)
    # boundaries. Doing the simple approximation here — split telemetry by
    # row count proportional to sector-time fractions.

    n = len(telemetry)
    # Fractions of total lap time per sector (sum to ~1.0).
    fractions = [s1 / lap_s, s2 / lap_s, s3 / lap_s]
    # Boundary indices (inclusive-exclusive split of n rows).
    bounds = [0]
    cumulative = 0.0
    for f in fractions:
        cumulative += f
        bounds.append(int(round(n * cumulative)))
    bounds[-1] = n  # snap last bucket to end

    brake_per_sector = []
    throttle_per_sector = []
    for i in range(3):
        a, b = bounds[i], bounds[i + 1]
        if b <= a:
            brake_per_sector.append(0.0)
            throttle_per_sector.append(0.0)
            continue
        slc = telemetry.iloc[a:b]
        sector_time = (s1, s2, s3)[i]
        # Fraction of sector spent braking / at full throttle, scaled by
        # actual sector time. Simple but bounded — small numerical drift OK.
        brake_frac = float(slc["Brake"].astype(bool).mean()) if "Brake" in slc else 0.0
        throttle_frac = (
            float((slc["Throttle"] >= THROTTLE_DEPLOY_THRESHOLD).mean())
            if "Throttle" in slc
            else 0.0
        )
        brake_per_sector.append(brake_frac * sector_time)
        throttle_per_sector.append(throttle_frac * sector_time)

    avg_speed = float(telemetry["Speed"].mean()) if "Speed" in telemetry else 0.0
    max_speed = float(telemetry["Speed"].max()) if "Speed" in telemetry else 0.0

    return LapInputs(
        lap_number=int(lap.LapNumber),
        lap_time_s=lap_s,
        sector1_time_s=s1,
        sector2_time_s=s2,
        sector3_time_s=s3,
        avg_speed_kmh=avg_speed,
        max_speed_kmh=max_speed,
        brake_time_per_sector_s=brake_per_sector,
        full_throttle_time_per_sector_s=throttle_per_sector,
    )


def parse_fastf1_session(
    year: int,
    gp: str,
    session_type: str,
    driver: Optional[str] = None,
) -> list[LapFeatures]:
    """Fetch a FastF1 session and produce LapFeatures rows.

    Args:
        year: e.g. 2024
        gp: e.g. 'Monza'
        session_type: 'R' (race), 'Q', 'FP1', etc. — FastF1 conventions.
        driver: three-letter abbreviation (e.g. 'VER'). If None, uses the
            session winner's laps (deterministic for demo replays).

    Network-touching. First call populates the FastF1 cache; subsequent
    calls hit the local cache only. CI-friendly path: pre-warm the cache
    once on a developer machine and ship the cache dir, OR construct
    LapInputs fixtures directly via parse_fastf1_lap().

    Always sets soc_source='derived' (FR-1.2). 2026-only concepts emit
    as 0 (override_uses, boost_uses).
    """
    import fastf1  # imported here so test-only paths don't require the dep

    cache = _fastf1_cache_dir()
    fastf1.Cache.enable_cache(str(cache))

    session = fastf1.get_session(year, gp, session_type)
    session.load(telemetry=True, weather=False, messages=False)

    # Pick the driver: explicit > winner > any first.
    if driver is None:
        try:
            driver = session.results.iloc[0]["Abbreviation"]
        except Exception:
            driver = session.laps["Driver"].iloc[0]
        logger.info("parse_fastf1_session: driver auto-selected → %s", driver)

    laps = session.laps.pick_drivers(driver) if hasattr(session.laps, "pick_drivers") else session.laps[session.laps["Driver"] == driver]
    laps = laps.sort_values("LapNumber").reset_index(drop=True)

    out: list[LapFeatures] = []
    prior_soc_end: Optional[float] = None
    for _, lap in laps.iterrows():
        try:
            telemetry = lap.get_telemetry()
        except Exception as e:
            logger.warning("parse_fastf1_session: skipping lap %s — %s", lap.LapNumber, e)
            continue
        inputs = _extract_lap_inputs(lap, telemetry)
        if inputs is None:
            continue
        features = parse_fastf1_lap(inputs, prior_soc_end)
        out.append(features)
        prior_soc_end = features.soc_end

    if not out:
        raise ValueError(
            f"parse_fastf1_session({year}, {gp!r}, {session_type!r}, driver={driver!r}) "
            "produced 0 LapFeatures rows — check session/driver inputs"
        )
    return out


__all__ = ["LapInputs", "parse_fastf1_lap", "parse_fastf1_session"]
