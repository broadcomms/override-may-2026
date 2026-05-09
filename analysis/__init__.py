"""analysis — heuristic baseline + feature engineering.

Public API:
  - enrich_laps(laps, soc_max) → list[EnrichedLap]
  - detect_zones(laps, soc_max) → list[Zone]

Granite reasoning runs over these zones; it does not replace them. See
docs/plans/zone-patterns.md for the heuristic spec.
"""

from .feature_engineering import (
    DEFAULT_HARVEST_CAP_MJ,
    EnrichedLap,
    enrich_laps,
    harvest_cap_mj,
)
from .zone_detector import detect_zones

__all__ = [
    "DEFAULT_HARVEST_CAP_MJ",
    "EnrichedLap",
    "enrich_laps",
    "harvest_cap_mj",
    "detect_zones",
]
