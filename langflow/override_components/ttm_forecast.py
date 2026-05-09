"""OVERRIDE — Langflow Custom Component #4: TTM-R2 Forecast.

5-lap SoC trajectory forecast using IBM Granite Time Series (TTM-R2).
TTM is *optional* per FR-3 — the pipeline must run end-to-end without it.
This component emits null when TTM is unavailable, and downstream nodes
gracefully degrade (Reasoning sets confidence='low', etc.).
"""

from __future__ import annotations

from lfx.custom import Component
from lfx.io import BoolInput, DataInput, Output
from lfx.schema import Data


class OverrideTTMForecast(Component):
    display_name = "TTM-R2 Forecast"
    description = (
        "Optional 5-lap SoC forecast via Granite Time Series. "
        "Emits null when disabled or when TTM is unavailable."
    )
    documentation: str = "https://github.com/anthropics/overdrive-may-2026"
    icon = "trending-up"

    inputs = [
        DataInput(
            name="lap_window",
            display_name="LapWindow",
            required=True,
        ),
        BoolInput(
            name="enabled",
            display_name="Enable TTM",
            value=False,
            info="Off by default — TTM is optional. Enable for an enhanced demo.",
        ),
    ]

    outputs = [
        Output(name="forecast", display_name="Forecast (or null)", method="run_forecast", types=["Data"]),
    ]

    def run_forecast(self) -> Data:
        if not bool(self.enabled):
            self.status = "TTM disabled — emitting null (graceful degradation per FR-3)"
            return Data(data={"forecast": None})

        from ingest.schema import LapWindow
        try:
            from core.forecasting import forecast_soc  # type: ignore
        except ImportError:
            self.status = "TTM module not available — emitting null"
            return Data(data={"forecast": None})

        lw = LapWindow.model_validate(self.lap_window.data)
        try:
            fc = forecast_soc(lw)
            self.status = f"TTM-R2 emitted {len(fc.points) if fc else 0}-point forecast"
            return Data(data={"forecast": fc.model_dump(mode="json") if fc else None})
        except Exception as exc:
            self.status = f"TTM forecast failed: {exc} — emitting null"
            return Data(data={"forecast": None})
