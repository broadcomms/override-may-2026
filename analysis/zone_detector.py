"""Heuristic detector for the four OVERRIDE inefficient-zone patterns.

Pure-Python, deterministic, AI-free baseline. Granite reasons over the
zones this module emits — it does not replace them.

The heuristics, severity thresholds, and `metrics` keys mirror
docs/plans/zone-patterns.md verbatim. If this code disagrees with that
spec, this code is wrong; refer to the doc.

Public entry point:
    detect_zones(laps: list[LapFeatures], soc_max: float) -> list[Zone]
"""

from __future__ import annotations

from typing import Optional

from ingest.schema import LapFeatures, Severity, Zone, ZoneType

from .feature_engineering import EnrichedLap, enrich_laps


# ──────────────────────────────────────────────────────────────────────────────
# Pattern thresholds (mirror docs/plans/zone-patterns.md exactly)
# ──────────────────────────────────────────────────────────────────────────────

# Pattern 1 — low-roi-deploy
LOW_ROI_DEPLOY_MJ_FLOOR = 0.20
LOW_ROI_TIME_GAIN_CEILING_S = 0.10
LOW_ROI_FIRES_AT_ROI = 1.0
LOW_ROI_SEVERITY_MEDIUM = 3.0
LOW_ROI_SEVERITY_HIGH = 10.0

# Pattern 2a — late-recharge / harvested-when-full
LATE_RECHARGE_FULL_SOC_FLOOR = 0.85
LATE_RECHARGE_FULL_HARVEST_FLOOR = 0.30
LATE_RECHARGE_FULL_HEADROOM_CEILING = 0.6
LATE_RECHARGE_FULL_SEV_MEDIUM = 0.4
LATE_RECHARGE_FULL_SEV_HIGH = 0.2

# Pattern 2b — late-recharge / missed-harvest-window
LATE_RECHARGE_MISSED_SOC_CEILING = 0.30
LATE_RECHARGE_MISSED_HARVEST_CEILING = 0.10
LATE_RECHARGE_MISSED_SEV_MEDIUM = 0.20
LATE_RECHARGE_MISSED_SEV_HIGH = 0.10

# Pattern 3 — over-harvest
OVER_HARVEST_RATIO_FLOOR = 0.85
OVER_HARVEST_SOC_END_FLOOR = 0.90
OVER_HARVEST_SEV_MEDIUM = 0.95
OVER_HARVEST_SEV_HIGH = 1.00

# Pattern 4 — unused-override
UNUSED_OVERRIDE_SOC_FLOOR = 0.70
UNUSED_OVERRIDE_DEPLOY_CEILING = 0.10
UNUSED_OVERRIDE_SEV_MEDIUM_MJ = 3.2
UNUSED_OVERRIDE_SEV_HIGH_MJ = 3.6


# ──────────────────────────────────────────────────────────────────────────────
# Sector-assignment helpers
# ──────────────────────────────────────────────────────────────────────────────


def _slowest_sector(lap: LapFeatures) -> int:
    """Return the 1-indexed sector with the longest time."""
    times = [lap.sector1_time, lap.sector2_time, lap.sector3_time]
    return times.index(max(times)) + 1


def _harvest_sector(lap: LapFeatures, default: int = 1) -> int:
    """Return the first sector in `recharge_zones`, or `default`."""
    if lap.recharge_zones:
        return lap.recharge_zones[0]
    return default


def _last_harvest_sector(lap: LapFeatures, default: int = 3) -> int:
    """Return the last sector in `recharge_zones`, or `default`."""
    if lap.recharge_zones:
        return lap.recharge_zones[-1]
    return default


def _zone_id(prefix: str, lap_number: int, sector: int) -> str:
    """Stable, short slug like `z_lroi_l23_s2`."""
    return f"z_{prefix}_l{lap_number}_s{sector}"


# ──────────────────────────────────────────────────────────────────────────────
# Pattern 1 — low-roi-deploy
# ──────────────────────────────────────────────────────────────────────────────


def _detect_low_roi_deploy(e: EnrichedLap) -> Optional[Zone]:
    lap = e.lap
    if not (lap.deploy_mj > LOW_ROI_DEPLOY_MJ_FLOOR):
        return None
    if not (e.time_gain_s < LOW_ROI_TIME_GAIN_CEILING_S):
        return None
    if not (e.roi_mj_per_s > LOW_ROI_FIRES_AT_ROI):
        return None

    severity: Severity = (
        "high" if e.roi_mj_per_s >= LOW_ROI_SEVERITY_HIGH
        else "medium" if e.roi_mj_per_s >= LOW_ROI_SEVERITY_MEDIUM
        else "low"
    )
    sector = _slowest_sector(lap)
    description = (
        f"Lap {lap.lap_number}: deployed {lap.deploy_mj:.2f} MJ for "
        f"{e.time_gain_s:+.2f} s of advantage (ROI {e.roi_mj_per_s:.1f} MJ/s)."
    )
    return Zone(
        zone_id=_zone_id("lroi", lap.lap_number, sector),
        zone_type=ZoneType.LOW_ROI_DEPLOY,
        lap_number=lap.lap_number,
        sector=sector,
        severity=severity,
        metrics={
            "deploy_mj": lap.deploy_mj,
            "time_gain_s": e.time_gain_s,
            "roi_mj_per_s": e.roi_mj_per_s,
        },
        description=description,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Pattern 2 — late-recharge (two variants emit the same ZoneType)
# ──────────────────────────────────────────────────────────────────────────────


def _detect_late_recharge_full(e: EnrichedLap) -> Optional[Zone]:
    """Variant 1: harvested when battery near-full."""
    lap = e.lap
    if not (lap.soc_start > LATE_RECHARGE_FULL_SOC_FLOOR):
        return None
    if not (lap.harvest_mj > LATE_RECHARGE_FULL_HARVEST_FLOOR):
        return None
    if not (e.headroom_mj_start < LATE_RECHARGE_FULL_HEADROOM_CEILING):
        return None

    severity: Severity = (
        "high" if e.headroom_mj_start < LATE_RECHARGE_FULL_SEV_HIGH
        else "medium" if e.headroom_mj_start < LATE_RECHARGE_FULL_SEV_MEDIUM
        else "low"
    )
    sector = _harvest_sector(lap, default=1)
    description = (
        f"Lap {lap.lap_number}: harvested {lap.harvest_mj:.2f} MJ when battery was "
        f"{lap.soc_start * 100:.0f}% full ({e.headroom_mj_start:.2f} MJ headroom)."
    )
    return Zone(
        zone_id=_zone_id("lrch_full", lap.lap_number, sector),
        zone_type=ZoneType.LATE_RECHARGE,
        lap_number=lap.lap_number,
        sector=sector,
        severity=severity,
        metrics={
            "harvest_mj": lap.harvest_mj,
            # Negative gain (slow lap) is a "lap-time cost" — flip the sign.
            "lap_time_cost_s": max(0.0, -e.time_gain_s),
            # Available window proxy: assume ~8s of brake time per recharge sector.
            "available_window_s": float(len(lap.recharge_zones) * 8.0),
        },
        description=description,
    )


def _detect_late_recharge_missed(e: EnrichedLap) -> Optional[Zone]:
    """Variant 2: very low harvest with battery near-empty."""
    lap = e.lap
    if not (lap.soc_start < LATE_RECHARGE_MISSED_SOC_CEILING):
        return None
    if not (lap.harvest_mj < LATE_RECHARGE_MISSED_HARVEST_CEILING):
        return None
    if len(lap.recharge_zones) != 0:
        return None

    severity: Severity = (
        "high" if lap.soc_start < LATE_RECHARGE_MISSED_SEV_HIGH
        else "medium" if lap.soc_start < LATE_RECHARGE_MISSED_SEV_MEDIUM
        else "low"
    )
    # No per-sector brake telemetry in LapFeatures v1 — default to S1.
    # Refined post-G-2 when TORCS adds per-sector brake-time.
    sector = 1
    description = (
        f"Lap {lap.lap_number}: only {lap.harvest_mj:.2f} MJ harvested with "
        f"battery at {lap.soc_start * 100:.0f}% — recharge window underused."
    )
    return Zone(
        zone_id=_zone_id("lrch_miss", lap.lap_number, sector),
        zone_type=ZoneType.LATE_RECHARGE,
        lap_number=lap.lap_number,
        sector=sector,
        severity=severity,
        metrics={
            "harvest_mj": lap.harvest_mj,
            "lap_time_cost_s": max(0.0, -e.time_gain_s),
            # No recharge zones means no available window was actually used.
            "available_window_s": 0.0,
        },
        description=description,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Pattern 3 — over-harvest
# ──────────────────────────────────────────────────────────────────────────────


def _detect_over_harvest(e: EnrichedLap) -> Optional[Zone]:
    lap = e.lap
    if not (e.harvest_ratio > OVER_HARVEST_RATIO_FLOOR):
        return None
    if not (lap.soc_end > OVER_HARVEST_SOC_END_FLOOR):
        return None

    severity: Severity = (
        "high" if e.harvest_ratio >= OVER_HARVEST_SEV_HIGH
        else "medium" if e.harvest_ratio >= OVER_HARVEST_SEV_MEDIUM
        else "low"
    )
    sector = _last_harvest_sector(lap, default=3)
    description = (
        f"Lap {lap.lap_number}: harvested {lap.harvest_mj:.2f} MJ "
        f"({e.harvest_ratio * 100:.0f}% of {e.cap_mj:.1f} MJ cap) with battery "
        f"{lap.soc_end * 100:.0f}% full at lap end."
    )
    return Zone(
        zone_id=_zone_id("over", lap.lap_number, sector),
        zone_type=ZoneType.OVER_HARVEST,
        lap_number=lap.lap_number,
        sector=sector,
        severity=severity,
        metrics={
            "harvest_mj": lap.harvest_mj,
            "cap_mj": e.cap_mj,
            "headroom_mj": max(0.0, e.cap_mj - lap.harvest_mj),
        },
        description=description,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Pattern 4 — unused-override
# ──────────────────────────────────────────────────────────────────────────────


def _detect_unused_override(e: EnrichedLap) -> Optional[Zone]:
    lap = e.lap
    if lap.override_uses != 0:
        return None
    if lap.boost_uses != 0:
        return None
    if not (lap.soc_start > UNUSED_OVERRIDE_SOC_FLOOR):
        return None
    if not (lap.deploy_mj < UNUSED_OVERRIDE_DEPLOY_CEILING):
        return None

    severity: Severity = (
        "high" if e.available_override_mj >= UNUSED_OVERRIDE_SEV_HIGH_MJ
        else "medium" if e.available_override_mj >= UNUSED_OVERRIDE_SEV_MEDIUM_MJ
        else "low"
    )
    # No per-sector speed in LapFeatures v1 — default to S2 (typically the
    # longest-straight sector at most circuits). Refined post-G-2.
    sector = 2
    description = (
        f"Lap {lap.lap_number}: {e.available_override_mj:.2f} MJ available, "
        f"{lap.deploy_mj:.2f} MJ deployed — boost window unused."
    )
    return Zone(
        zone_id=_zone_id("noov", lap.lap_number, sector),
        zone_type=ZoneType.UNUSED_OVERRIDE,
        lap_number=lap.lap_number,
        sector=sector,
        severity=severity,
        metrics={
            # Placeholders — FastF1 doesn't expose these; TORCS may.
            "gap_to_leader_s": 0.0,
            "available_override_mj": e.available_override_mj,
            "straight_length_m": 0.0,
        },
        description=description,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────


def detect_zones(laps: list[LapFeatures], soc_max: float) -> list[Zone]:
    """Run all four heuristic detectors over the session.

    Returns zones ordered by `lap_number` ascending, then by zone_type
    (low-roi-deploy < late-recharge < over-harvest < unused-override) for
    determinism. Multiple zones per lap are allowed — a single lap can
    fire two patterns (e.g., over-harvest AND late-recharge-full).

    Pure function; no I/O, no LLM. Granite reasons over these zones at P2.3.
    """
    enriched = enrich_laps(laps, soc_max)

    detectors = (
        # Order matters only for the per-lap ordering inside the result list.
        ("low-roi-deploy", _detect_low_roi_deploy),
        ("late-recharge-full", _detect_late_recharge_full),
        ("late-recharge-missed", _detect_late_recharge_missed),
        ("over-harvest", _detect_over_harvest),
        ("unused-override", _detect_unused_override),
    )

    zones: list[Zone] = []
    for e in enriched:
        for _, fn in detectors:
            z = fn(e)
            if z is not None:
                zones.append(z)

    # Stable sort: by lap_number, then by zone_type.value (alphabetical).
    zones.sort(key=lambda z: (z.lap_number, z.zone_type.value))
    return zones


__all__ = ["detect_zones"]
