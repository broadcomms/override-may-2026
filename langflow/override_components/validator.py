"""OVERRIDE — Langflow Custom Component #7: Pass-1 Validator.

Deterministic Pass-1 of the two-pass safety architecture (per
docs/05-security.md). Runs the production validator
(`core.validator.validate`) using `core/validator.yaml` rules. No LLM call —
pure regex + structural checks.

In production, a failed Pass-1 triggers a stricter-prompt regen
(handled by `core.pipeline._process_one_zone_inner`). The canvas does ONE
pass for the demo; the rejection card is the layered-defense story.
"""

from __future__ import annotations

from lfx.custom import Component
from lfx.io import DataInput, Output
from lfx.schema import Data


class OverrideValidator(Component):
    display_name = "Pass 1: Validator"
    description = (
        "Deterministic Pass-1 over ReasoningOutput. Checks citation existence "
        "(verbatim), banned phrases, and section consistency."
    )
    documentation: str = "https://github.com/anthropics/overdrive-may-2026"
    icon = "check-circle"

    inputs = [
        DataInput(
            name="reasoning_bundle",
            display_name="Reasoning bundle",
            required=True,
        ),
    ]

    outputs = [
        Output(name="validator_bundle", display_name="Validator bundle", method="run_validator", types=["Data"]),
    ]

    def run_validator(self) -> Data:
        from ingest.schema import LapWindow, RegulationChunk, ReasoningOutput
        from core.validator import validate

        bundle = self.reasoning_bundle.data
        reasoning = ReasoningOutput.model_validate(bundle["reasoning"])
        lap_window = LapWindow.model_validate(bundle["lap_window"])
        reg = (
            RegulationChunk.model_validate(bundle["regulation"])
            if bundle.get("regulation")
            else None
        )

        result = validate(
            reasoning,
            lap_window,
            regulation_chunks=[reg] if reg else None,
        )
        self.status = (
            f"Pass-1 {'PASSED' if result.passed else 'FAILED'}. "
            f"{len(result.failed_rules)} failed rule(s)."
        )
        return Data(data={
            **bundle,
            "validator": result.model_dump(mode="json"),
        })
