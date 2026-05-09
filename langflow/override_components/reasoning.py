"""OVERRIDE — Langflow Custom Component #6: Granite Reasoning.

Runs Granite 4-h-small (Instruct) on watsonx.ai per ADR-001. Same code path
as the FastAPI runtime — `core.reasoning.reason_about_zone()`. The canvas
demo runs ONE pass; production has retry-with-stricter-prompt loops handled
inside `core.pipeline.run_pipeline()`.

Inputs:
  - regulation_payload: bundle of {zone, lap_window, regulation} from the
    Reg Retriever.
  - forecast_payload: bundle of {forecast} from TTM-R2 Forecast (forecast
    may be null).

The single bundled output ferries everything downstream (validator + guardian
both need ReasoningOutput + RegulationChunk; this avoids a Mux node).
"""

from __future__ import annotations

from lfx.custom import Component
from lfx.io import DataInput, FloatInput, Output
from lfx.schema import Data


class OverrideReasoning(Component):
    display_name = "Granite Reasoning"
    description = (
        "Causal reasoning over a zone using Granite 4-h-small Instruct on "
        "watsonx.ai. Emits a typed ReasoningOutput."
    )
    documentation: str = "https://github.com/anthropics/overdrive-may-2026"
    icon = "brain"

    inputs = [
        DataInput(
            name="regulation_payload",
            display_name="Regulation bundle (from Reg Retriever)",
            required=True,
        ),
        DataInput(
            name="forecast_payload",
            display_name="Forecast bundle (from TTM-R2)",
            required=True,
        ),
        FloatInput(
            name="temperature",
            display_name="Temperature",
            value=0.3,
            info="REASONING_TEMPERATURE override. 0.3 by default.",
        ),
    ]

    outputs = [
        Output(name="reasoning_bundle", display_name="Reasoning bundle", method="run_reasoning", types=["Data"]),
    ]

    def run_reasoning(self) -> Data:
        from ingest.schema import Forecast, LapWindow, RegulationChunk, Zone
        from core.reasoning import WatsonxAIChatClient, reason_about_zone

        reg_data = self.regulation_payload.data
        fc_data = self.forecast_payload.data

        zone = Zone.model_validate(reg_data["zone"])
        lw = LapWindow.model_validate(reg_data["lap_window"])
        reg = (
            RegulationChunk.model_validate(reg_data["regulation"])
            if reg_data.get("regulation")
            else None
        )
        fc = (
            Forecast.model_validate(fc_data["forecast"])
            if fc_data.get("forecast")
            else None
        )

        client = WatsonxAIChatClient()
        out = reason_about_zone(
            zone=zone,
            lap_window=lw,
            forecast=fc,
            regulation=reg,
            client=client,
            temperature=float(self.temperature),
        )
        self.status = (
            f"Reasoning OK: {len(out.reasoning_chain)}-step chain, "
            f"confidence={out.confidence}, "
            f"citation={'present' if out.regulation_citation else 'null'}"
        )
        return Data(data={
            "reasoning": out.model_dump(mode="json"),
            "regulation": reg_data.get("regulation"),
            "zone": reg_data["zone"],
            "lap_window": reg_data["lap_window"],
        })
