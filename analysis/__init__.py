"""analysis — heuristic baseline + feature engineering.

Public API:
  - enrich_laps(laps, soc_max) → list[EnrichedLap]
  - detect_zones(laps, soc_max) → list[Zone]
  - derive_live_insights(snapshot, completed_laps) → list[LiveInsight]
  - build_race_report(session) → RaceReport
  - build_lap_analysis(session, lap_number) → LapAnalysis

Granite reasoning runs over these zones; it does not replace them. See
docs/plans/zone-patterns.md for the heuristic spec.
"""

from .feature_engineering import (
    DEFAULT_HARVEST_CAP_MJ,
    EnrichedLap,
    enrich_laps,
    harvest_cap_mj,
)
from .live_intelligence import derive_live_insights
from .post_race_report import build_lap_analysis, build_race_report
from .zone_detector import detect_zones

__all__ = [
    "DEFAULT_HARVEST_CAP_MJ",
    "EnrichedLap",
    "build_lap_analysis",
    "build_race_report",
    "derive_live_insights",
    "enrich_laps",
    "harvest_cap_mj",
    "detect_zones",
]
