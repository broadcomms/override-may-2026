"""Shared 2026 hybrid energy bookkeeping for telemetry → LapFeatures parsers.

Both ``ingest/torcs_parser.py`` (TORCS replays) and ``ingest/fastf1_parser.py``
(historical FastF1 sessions) synthesize state-of-charge / harvest / deploy
from brake-on-time and throttle-≥-95%-time integrals, because neither source
exposes native MGU-K telemetry for the 2026 hybrid era. This module owns the
constants and the per-sector derivation so the two parsers don't drift.

Why shared (per v6 plan task 1.4): if both parsers carry their own copy of
``HARVEST_KJ_PER_BRAKE_SECOND`` etc., tweaking calibration in one place and
forgetting the other silently desyncs the synthetic energy model between data
sources — which the zone detector and harvest-cap validator would surface as
ghost zones depending on which fixture loaded.

Calibration target (locked by ``tests/test_torcs_parser.py``): per-lap
``harvest_mj`` and ``deploy_mj`` land in the 4–7 MJ range under the 8.5 MJ
FIA per-lap cap parsed by ``core/regs.extract_harvest_cap_mj``. The TORCS
captures determine the final constant values; the FastF1 parser inherits
them.

References:
  - ``docs/04-schema.md`` §3 (LapFeatures contract)
  - ``docs/adrs/ADR-002-torcs-as-primary-sandbox.md`` (synthetic energy
    model rationale and provenance flag)
  - ``ingest/fastf1_parser.py`` (reference caller; constants moved here)
"""

from __future__ import annotations

from dataclasses import dataclass


# ──────────────────────────────────────────────────────────────────────────────
# Calibration constants — shared between FastF1 and TORCS parsers
# ──────────────────────────────────────────────────────────────────────────────
#
# These constants are PLACEHOLDERS for derived-from-throttle/brake sessions.
# They produce plausible-looking, well-bounded LapFeatures that exercise the
# rest of the pipeline. They will diverge from real 2026 numbers — that's why
# the parsers set ``soc_source="derived"`` and the SessionSummary carries a
# note.

SOC_INITIAL = 1.0  # full battery at session start
SOC_MIN = 0.0
SOC_MAX = 1.0

# kJ harvested per second of brake-on. Rough — real F1 regen is brake-force-
# weighted, but FastF1 only exposes a 0/100 "Brake" applied flag; TORCS exposes
# a continuous brake value that we discretize to "brake on" above a threshold.
HARVEST_KJ_PER_BRAKE_SECOND = 200.0

# kJ deployed per second of "full throttle" (Throttle ≥ THROTTLE_DEPLOY_THRESHOLD).
DEPLOY_KJ_PER_FULL_THROTTLE_SECOND = 80.0

# Only throttle near 100 % counts as a deploy event — the rest is cruise.
THROTTLE_DEPLOY_THRESHOLD = 95.0

# Battery capacity for SoC normalization (MJ) — placeholder. Real value comes
# from the regulation at G-4 and is exposed via LapWindow.soc_max.
BATTERY_CAPACITY_MJ = 4.0

# A sector counts as a "recharge zone" if harvest exceeded this threshold (MJ).
# Schema §3 LapFeatures.recharge_zones.
RECHARGE_ZONE_THRESHOLD_MJ = 0.1


# ──────────────────────────────────────────────────────────────────────────────
# Derived per-lap energy bundle
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LapEnergy:
    """Output of the synthetic 2026 hybrid energy bookkeeping for one lap.

    Returned by ``derive_lap_energy``. Callers map this onto the relevant
    ``LapFeatures`` fields (``harvest_mj``, ``deploy_mj``, ``soc_start``,
    ``soc_end``, ``recharge_zones``). All energy values in MJ; SoC in [0, 1].
    """

    soc_start: float
    soc_end: float
    harvest_mj: float
    deploy_mj: float
    harvest_per_sector_mj: tuple[float, float, float]
    deploy_per_sector_mj: tuple[float, float, float]
    recharge_zones: tuple[int, ...]


def derive_lap_energy(
    brake_time_per_sector_s: tuple[float, float, float] | list[float],
    full_throttle_time_per_sector_s: tuple[float, float, float] | list[float],
    prior_soc_end: float | None,
    *,
    soc_initial: float = SOC_INITIAL,
) -> LapEnergy:
    """Synthesize one lap's 2026 hybrid energy state from brake/throttle inputs.

    Pure function — no I/O, no global state, no LapFeatures coupling. Lets
    parsers, perturbations, and tests use the same math without circular
    imports between ``ingest/`` and ``analysis/``.

    Args:
        brake_time_per_sector_s: seconds spent braking in each of the three
            sectors. Indexable, length 3.
        full_throttle_time_per_sector_s: seconds spent at throttle ≥
            ``THROTTLE_DEPLOY_THRESHOLD`` in each sector. Length 3.
        prior_soc_end: previous lap's ``soc_end``. ``None`` means this is the
            first lap, so we start at ``soc_initial`` (default full battery).
        soc_initial: starting SoC fraction when ``prior_soc_end`` is ``None``.
            Defaults to 1.0 (full). Tests can override.

    Returns:
        ``LapEnergy`` with per-sector and total harvest/deploy in MJ, the
        clamped SoC trajectory, and the recharge_zones list.
    """
    if len(brake_time_per_sector_s) != 3:
        raise ValueError("brake_time_per_sector_s must have exactly 3 entries")
    if len(full_throttle_time_per_sector_s) != 3:
        raise ValueError("full_throttle_time_per_sector_s must have exactly 3 entries")

    soc_start = prior_soc_end if prior_soc_end is not None else soc_initial

    harvest_per_sector = tuple(
        (HARVEST_KJ_PER_BRAKE_SECOND * brake_s) / 1000.0
        for brake_s in brake_time_per_sector_s
    )
    deploy_per_sector = tuple(
        (DEPLOY_KJ_PER_FULL_THROTTLE_SECOND * throttle_s) / 1000.0
        for throttle_s in full_throttle_time_per_sector_s
    )

    harvest_mj = sum(harvest_per_sector)
    deploy_mj = sum(deploy_per_sector)

    delta_soc = (harvest_mj - deploy_mj) / BATTERY_CAPACITY_MJ
    soc_end = max(SOC_MIN, min(SOC_MAX, soc_start + delta_soc))

    recharge_zones = tuple(
        i + 1  # sectors are 1-indexed in the schema
        for i, mj in enumerate(harvest_per_sector)
        if mj > RECHARGE_ZONE_THRESHOLD_MJ
    )

    return LapEnergy(
        soc_start=round(soc_start, 6),
        soc_end=round(soc_end, 6),
        harvest_mj=round(harvest_mj, 6),
        deploy_mj=round(deploy_mj, 6),
        harvest_per_sector_mj=harvest_per_sector,  # type: ignore[arg-type]
        deploy_per_sector_mj=deploy_per_sector,  # type: ignore[arg-type]
        recharge_zones=recharge_zones,
    )


__all__ = [
    "BATTERY_CAPACITY_MJ",
    "DEPLOY_KJ_PER_FULL_THROTTLE_SECOND",
    "HARVEST_KJ_PER_BRAKE_SECOND",
    "LapEnergy",
    "RECHARGE_ZONE_THRESHOLD_MJ",
    "SOC_INITIAL",
    "SOC_MAX",
    "SOC_MIN",
    "THROTTLE_DEPLOY_THRESHOLD",
    "derive_lap_energy",
]
