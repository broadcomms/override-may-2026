"""OVERRIDE — Langflow Custom Component #10: Fan Translator.

Plain-language rewrite of a ReasoningOutput for fan mode (per FR-7).
Lazy in production: only fires on `?mode=fan` requests. The canvas wires
this after the Mode Router's fan branch.

Uses Granite 4-h-small Instruct on watsonx.ai with a separate fan-mode
system prompt (`prompts/fan_mode.system.md`).
"""

from __future__ import annotations

from lfx.custom import Component
from lfx.io import DataInput, Output
from lfx.schema import Data


class OverrideFanTranslator(Component):
    display_name = "Fan Translator"
    description = (
        "Plain-language rewrite of ReasoningOutput for fan mode. "
        "Granite 4-h-small Instruct on watsonx.ai."
    )
    documentation: str = "https://github.com/anthropics/overdrive-may-2026"
    icon = "users"

    inputs = [
        DataInput(
            name="guardian_bundle",
            display_name="Guardian bundle (post Pass-2)",
            required=True,
        ),
    ]

    outputs = [
        Output(name="fan_bundle", display_name="Fan output bundle", method="run_fan", types=["Data"]),
    ]

    def run_fan(self) -> Data:
        from ingest.schema import ReasoningOutput
        from core.fan_mode import translate_to_fan_mode
        from core.reasoning import WatsonxAIChatClient

        bundle = self.guardian_bundle.data
        reasoning = ReasoningOutput.model_validate(bundle["reasoning"])

        client = WatsonxAIChatClient()
        fan_out = translate_to_fan_mode(reasoning, client=client)
        self.status = f"Fan translation OK ({len(fan_out.headline)} chars headline)"
        return Data(data={
            **bundle,
            "fan": fan_out.model_dump(mode="json"),
        })
