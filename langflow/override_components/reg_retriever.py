"""OVERRIDE — Langflow Custom Component #5: Docling Regulation Retriever.

Retrieves the highest-scoring regulation chunk for a zone, using the
production retriever (`core.regs.retrieve_chunk`). Embeddings come from
Granite Embedding 278m on watsonx.ai (per ADR-001). Chunks are loaded once
per process from the pre-built `data/regs/extracted_chunks.json`.

Emits None if no chunk meets the relevance threshold — downstream
Reasoning then sets `regulation_citation=null` and `confidence='low'` per
the prompt's hard rule (and the validator enforces it).
"""

from __future__ import annotations

import os
from pathlib import Path

from lfx.custom import Component
from lfx.io import DataInput, FloatInput, Output, StrInput
from lfx.schema import Data


class OverrideRegRetriever(Component):
    display_name = "Docling Reg Retriever"
    description = (
        "Retrieve the most relevant FIA regulation chunk for the zone. "
        "Uses Granite Embedding on watsonx.ai (per ADR-001)."
    )
    documentation: str = "https://github.com/anthropics/overdrive-may-2026"
    icon = "book-open"

    inputs = [
        DataInput(
            name="zone_payload",
            display_name="Zone (from Zone Detector)",
            info="Bundled {zone, lap_window} from the Zone Detector's first-zone port.",
            required=True,
        ),
        StrInput(
            name="chunks_path",
            display_name="Chunks JSON path",
            value="data/regs/extracted_chunks.json",
            info="Falls back to extracted_chunks.sample.json if missing.",
        ),
        FloatInput(
            name="threshold",
            display_name="Relevance threshold",
            value=0.45,
            info="Below this, retrieve_chunk returns null.",
        ),
    ]

    outputs = [
        Output(name="regulation", display_name="RegulationChunk (or null)", method="run_retrieval", types=["Data"]),
    ]

    def run_retrieval(self) -> Data:
        from ingest.schema import Zone
        from core.regs import (
            DEFAULT_CHUNKS_PATH,
            WatsonxAIEmbeddingClient,
            load_chunks,
            retrieve_chunk,
        )

        payload = self.zone_payload.data
        zone = Zone.model_validate(payload["zone"])

        path = Path(str(self.chunks_path))
        if not path.exists():
            sample = path.with_name(path.stem + ".sample.json")
            if sample.exists():
                path = sample
            else:
                path = DEFAULT_CHUNKS_PATH

        chunks, _meta = load_chunks(path)
        if not chunks:
            self.status = f"No chunks at {path} — emitting null"
            return Data(data={
                "zone": payload["zone"],
                "lap_window": payload["lap_window"],
                "regulation": None,
            })

        client = WatsonxAIEmbeddingClient()
        result = retrieve_chunk(zone.zone_type, chunks, client, threshold=float(self.threshold))
        if result is None:
            self.status = "No chunk met threshold — emitting null (validator enforces low-confidence path)"
            reg_payload = None
        else:
            chunk, score = result
            self.status = (
                f"Retrieved {chunk.source.section} score={score:.3f} "
                f"({chunk.text[:60]}...)"
            )
            reg_payload = chunk.model_dump(mode="json")

        return Data(data={
            "zone": payload["zone"],
            "lap_window": payload["lap_window"],
            "regulation": reg_payload,
        })
