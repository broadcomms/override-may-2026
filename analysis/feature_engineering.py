"""Per-lap feature enrichment for zone detection.

Takes a sequence of `LapFeatures` (pure typed rows from `ingest`) and
attaches the derived signals that the heuristic zone detector consumes.
This separation keeps `zone_detector.py` focused on *what* counts as a
zone rather than *how* its inputs are computed.

Derived fields (per docs/plans/zone-patterns.md, "Per-lap feature engineering"):

  - time_gain_s        median(lap_time over session) - lap_time
  - roi_mj_per_s       deploy_mj / max(time_gain_s, 0.01)
  - headroom_mj_start  (1.0 - soc_start) * soc_max
  - cap_mj             per-lap harvest cap (default 8.5 MJ; tunable)
  - harvest_ratio      harvest_mj / cap_mj
  - available_override_mj   soc_start * soc_max
"""

from __future__ import annotations

import os
import statistics
from dataclasses import dataclass

from ingest.schema import LapFeatures

# Per-lap harvest cap default (MJ). This is a local calibration for replay
# analysis; regulation-grounded citations are rendered separately from Docling
# sources. Operators can tune it via OVERRIDE_HARVEST_CAP_MJ.
DEFAULT_HARVEST_CAP_MJ = 8.5


def harvest_cap_mj() -> float:
    """Resolve the per-lap harvest cap. Honors `OVERRIDE_HARVEST_CAP_MJ` env var."""
    raw = os.environ.get("OVERRIDE_HARVEST_CAP_MJ")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return DEFAULT_HARVEST_CAP_MJ


@dataclass(frozen=True)
class EnrichedLap:
    """A LapFeatures row plus its session-level derived signals.

    Frozen — passes by reference through the detector without mutation.
    """

    lap: LapFeatures
    time_gain_s: float
    roi_mj_per_s: float
    headroom_mj_start: float
    cap_mj: float
    harvest_ratio: float
    available_override_mj: float


def enrich_laps(laps: list[LapFeatures], soc_max: float) -> list[EnrichedLap]:
    """Attach derived signals to each lap. Pure function; no I/O.

    `soc_max` is the battery capacity (MJ) — same value carried on
    `LapWindow.soc_max` per `04-schema.md` §3.

    Returns the enriched rows in the **same order** as the input. The
    median lap-time used for `time_gain_s` is the median over **the input
    list** — callers passing a window that excludes warm-up / cool-down
    laps get a more stable median; that's a caller-side concern.
    """
    if not laps:
        return []
    if soc_max <= 0:
        raise ValueError(f"soc_max must be > 0; got {soc_max}")

    median_lap_time = statistics.median(lap.lap_time for lap in laps)
    cap = harvest_cap_mj()

    enriched: list[EnrichedLap] = []
    for lap in laps:
        time_gain = median_lap_time - lap.lap_time
        # Avoid div-by-zero AND avoid amplifying near-zero gains into
        # unrealistic ROI values. The 0.01 floor caps roi at 100×deploy_mj.
        roi = lap.deploy_mj / max(time_gain, 0.01) if lap.deploy_mj > 0 else 0.0
        # If the lap was *slower* than median (negative gain), ROI is
        # effectively infinite — we represent it as a large finite number
        # so downstream numeric comparisons stay well-defined.
        if time_gain <= 0 and lap.deploy_mj > 0:
            roi = lap.deploy_mj / 0.01  # i.e. 100 × deploy_mj

        headroom_start = max(0.0, (1.0 - lap.soc_start) * soc_max)
        harvest_ratio = lap.harvest_mj / cap if cap > 0 else 0.0
        available_override = lap.soc_start * soc_max

        enriched.append(
            EnrichedLap(
                lap=lap,
                time_gain_s=round(time_gain, 6),
                roi_mj_per_s=round(roi, 6),
                headroom_mj_start=round(headroom_start, 6),
                cap_mj=cap,
                harvest_ratio=round(harvest_ratio, 6),
                available_override_mj=round(available_override, 6),
            )
        )

    return enriched


__all__ = [
    "DEFAULT_HARVEST_CAP_MJ",
    "EnrichedLap",
    "enrich_laps",
    "harvest_cap_mj",
]
