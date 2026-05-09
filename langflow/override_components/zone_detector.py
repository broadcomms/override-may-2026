"""OVERRIDE — Langflow Custom Component #3: Zone Detector.

Heuristic inefficient-zone detection over a LapWindow. Runs the production
detector (`analysis.zone_detector.detect_zones`) — same code path as the
FastAPI runtime — and emits both the full list and the first zone (the demo
canvas processes one zone end-to-end; production runs all zones in parallel).

Per docs/04-langflow-canvas.md, the demo flow walks ONE zone through the
remaining stages. The full list is emitted on the `zones_all` port for
inspection / future fan-out experiments.
"""

from __future__ import annotations

from lfx.custom import Component
from lfx.io import DataInput, Output
from lfx.schema import Data


class OverrideZoneDetector(Component):
    display_name = "Zone Detector"
    description = (
        "Run the production zone detector over a LapWindow. Emits the first "
        "zone (single) for the demo flow plus the full list for inspection."
    )
    documentation: str = "https://github.com/anthropics/overdrive-may-2026"
    icon = "search"

    inputs = [
        DataInput(
            name="lap_window",
            display_name="LapWindow",
            info="Output of Ingest & Aggregate.",
            required=True,
        ),
    ]

    outputs = [
        Output(name="zone", display_name="First Zone", method="emit_first_zone", types=["Data"]),
        Output(name="zones_all", display_name="All Zones", method="emit_all_zones", types=["Data"]),
    ]

    def _detect(self) -> tuple[list, dict]:
        from ingest.schema import LapWindow
        from analysis.zone_detector import detect_zones

        if not isinstance(self.lap_window, Data):
            raise TypeError("OverrideZoneDetector: lap_window must be a Data object")
        lw = LapWindow.model_validate(self.lap_window.data)
        zones = detect_zones(lw.laps, lw.soc_max)
        return zones, lw.model_dump(mode="json")

    def emit_first_zone(self) -> Data:
        zones, lw_dict = self._detect()
        if not zones:
            self.status = "no zones detected — recommend a different replay"
            return Data(data={})
        first = zones[0]
        self.status = (
            f"Detected {len(zones)} zone(s); using first: {first.zone_id} "
            f"({first.zone_type.value}) for demo flow."
        )
        # Bundle both zone + lap_window so downstream Reasoning has both
        return Data(
            data={
                "zone": first.model_dump(mode="json"),
                "lap_window": lw_dict,
            }
        )

    def emit_all_zones(self) -> Data:
        zones, _ = self._detect()
        return Data(
            data={
                "count": len(zones),
                "zones": [z.model_dump(mode="json") for z in zones],
            }
        )
