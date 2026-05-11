"""OVERRIDE — Langflow Custom Component #2: Ingest & Aggregate.

Wraps the production TORCS / FastF1 parser and emits a `LapWindow` (per
`ingest/schema.py`) for downstream nodes. This component is a thin
adapter — all parsing logic lives in `ingest/{torcs_parser,fastf1_parser}.py`
and is shared with the FastAPI runtime.

The Langflow canvas is the design + demo layer (per ADR-001 + docs/04-langflow-canvas.md).
Production ingest runs through `api/main.py`.

Wiring in the canvas:
  Upload Session File (FileInput) → Ingest & Aggregate → {Zone Detector, TTM Forecast}
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lfx.custom import Component
from lfx.io import DropdownInput, FloatInput, Output, StrInput
from lfx.schema import Data


class OverrideIngest(Component):
    display_name = "Ingest & Aggregate"
    description = (
        "Parse a TORCS JSON or FastF1 export into a typed LapWindow "
        "(per ingest/schema.py). Mirrors the production runtime."
    )
    documentation: str = "https://github.com/anthropics/overdrive-may-2026"
    icon = "database"

    inputs = [
        StrInput(
            name="file_path",
            display_name="File path",
            info="Absolute path to the TORCS JSON or FastF1 cache export. "
                 "Wire from a File component or paste a path during demo.",
            required=True,
        ),
        DropdownInput(
            name="source",
            display_name="Source",
            options=["torcs", "fastf1"],
            value="torcs",
            info="Parser to use. 'torcs' for TORCS JSON, 'fastf1' for FastF1.",
        ),
        StrInput(
            name="track_id",
            display_name="Track ID",
            value="monza",
            info="Track identifier (lowercase slug).",
        ),
        FloatInput(
            name="soc_max",
            display_name="SoC max (MJ)",
            value=4.0,
            info="Battery max stored energy. Per FIA 2026, soc_max=4.0 MJ.",
        ),
        StrInput(
            name="session_id",
            display_name="Session ID (optional)",
            value="",
            info="Leave empty to auto-generate a slug.",
        ),
    ]

    outputs = [
        Output(name="lap_window", display_name="LapWindow", method="run_ingest", types=["Data"]),
    ]

    def run_ingest(self) -> Data:
        import json
        from ingest.schema import LapFeatures, LapWindow

        file_path = Path(str(self.file_path)).expanduser()
        if not file_path.exists():
            raise FileNotFoundError(f"OverrideIngest: file not found at {file_path}")

        source = str(self.source).lower()
        track_id = str(self.track_id) or "monza"
        soc_max = float(self.soc_max)
        session_id = str(self.session_id) or f"langflow_{file_path.stem}"

        # Mirror api/main.py::_parse_upload: accept the canonical lap-features
        # JSON shape (bare list or {"laps":[...]}). The dedicated torcs_parser
        # is post-G-2 (empty stub today); FastF1 parquet path uses pandas.
        if source in {"torcs", "fastf1"}:
            if file_path.suffix == ".parquet" and source == "fastf1":
                import io, pandas as pd
                df = pd.read_parquet(io.BytesIO(file_path.read_bytes()))
                laps = [LapFeatures.model_validate(r) for r in df.to_dict(orient="records")]
            else:
                payload = json.loads(file_path.read_text(encoding="utf-8"))
                rows = payload["laps"] if isinstance(payload, dict) and "laps" in payload else payload
                if not isinstance(rows, list):
                    raise ValueError("OverrideIngest: expected JSON list or {'laps': [...]} wrapper")
                laps = [LapFeatures.model_validate(r) for r in rows]
        else:
            raise ValueError(f"OverrideIngest: unknown source {source!r}")

        lap_window = LapWindow(
            session_id=session_id,
            track_id=track_id,
            soc_max=soc_max,
            laps=laps[:30],  # FR-2.x: 1–30 lap window
        )
        self.status = (
            f"Parsed {len(laps)} laps; emitting first {len(lap_window.laps)} as window. "
            f"track={track_id} soc_max={soc_max:.2f} MJ"
        )
        return Data(data=lap_window.model_dump(mode="json"))
