"""OVERRIDE — Langflow Custom Component #8: Pass-2 Guardian Score.

Pass-2 of the two-pass safety architecture: Granite Guardian 3-8b on
watsonx.ai (per ADR-001) acting as a binary BYOC classifier over two
custom criteria — energy_safety and regulation_consistency. Scores are
binary 0.0/1.0 mapped from Yes/No, then averaged. <0.7 triggers
regen in production; the canvas does ONE pass.
"""

from __future__ import annotations

from lfx.custom import Component
from lfx.io import DataInput, Output
from lfx.schema import Data


class OverrideGuardian(Component):
    display_name = "Pass 2: Guardian Score"
    description = (
        "Granite Guardian 3-8b BYOC scoring over energy_safety + regulation_consistency."
    )
    documentation: str = "https://github.com/anthropics/overdrive-may-2026"
    icon = "shield"

    inputs = [
        DataInput(
            name="validator_bundle",
            display_name="Validator bundle",
            required=True,
        ),
    ]

    outputs = [
        Output(name="guardian_bundle", display_name="Guardian bundle", method="run_guardian", types=["Data"]),
    ]

    def run_guardian(self) -> Data:
        from ingest.schema import LapWindow, RegulationChunk, ReasoningOutput
        from core.guardian import WatsonxAIGuardianClient, score_recommendation

        bundle = self.validator_bundle.data
        reasoning = ReasoningOutput.model_validate(bundle["reasoning"])
        lap_window = LapWindow.model_validate(bundle["lap_window"])
        reg = (
            RegulationChunk.model_validate(bundle["regulation"])
            if bundle.get("regulation")
            else None
        )

        client = WatsonxAIGuardianClient()
        result = score_recommendation(reasoning, lap_window, reg, client=client)
        es = result.scores.get("energy_safety")
        rc = result.scores.get("regulation_consistency")
        self.status = (
            f"Pass-2 {'PASSED' if result.passed else 'FAILED'} "
            f"(threshold {result.pass_threshold:.2f}). "
            f"energy_safety={es:.1f} reg_consistency={rc:.1f}"
            if es is not None and rc is not None
            else f"Pass-2 {'PASSED' if result.passed else 'FAILED'} (no scores recorded)"
        )
        return Data(data={
            **bundle,
            "guardian": result.model_dump(mode="json"),
        })
