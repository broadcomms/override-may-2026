"""ingest — turn session replays into typed LapFeatures.

Entry points:
  - parse_torcs_session(json_path) → list[LapFeatures]    (P1.4 second half, after G-2)
  - parse_fastf1_session(year, gp, session_type) → list[LapFeatures]
  - parse_fastf1_lap(inputs, prior_soc_end) → LapFeatures   (pure, testable)

Schemas live in ingest.schema and are the cross-cutting types every other
module imports. See docs/04-schema.md for the canonical contract.
"""

from .fastf1_parser import LapInputs, parse_fastf1_lap, parse_fastf1_session
from .schema import (
    FanOutput,
    Forecast,
    LapFeatures,
    LapWindow,
    ReasoningInput,
    ReasoningOutput,
    Recommendation,
    RegulationChunk,
    RegulationCitation,
    RegulationSource,
    Session,
    SessionSummary,
    Severity,
    Zone,
    ZoneType,
)

__all__ = [
    # Schemas
    "FanOutput",
    "Forecast",
    "LapFeatures",
    "LapWindow",
    "ReasoningInput",
    "ReasoningOutput",
    "Recommendation",
    "RegulationChunk",
    "RegulationCitation",
    "RegulationSource",
    "Session",
    "SessionSummary",
    "Severity",
    "Zone",
    "ZoneType",
    # FastF1 parser
    "LapInputs",
    "parse_fastf1_lap",
    "parse_fastf1_session",
]
