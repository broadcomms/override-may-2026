# OVERRIDE — Langflow Canvas Specification

> **Scope clarification.** Langflow is the **design + demo layer**, not the production runtime. Production calls run through Python/FastAPI for performance and reliability. The Langflow canvas mirrors the pipeline architecture, executes a simplified end-to-end sample flow for the demo video, and serves as orchestration documentation. README and demo video both make this distinction explicit. Production runtime semantics are defined in [`04-api.md`](./04-api.md); component contracts are in [`04-schema.md`](./04-schema.md).

---

## Nodes (left to right, top to bottom)

| # | Node label | Component type | Purpose |
|---|---|---|---|
| 1 | `Upload Session File` | Custom Component (FileInput) | Accepts TORCS JSON or FastF1 export |
| 2 | `Ingest & Aggregate` | Custom Component (Python) | Parse + lap-level features (`LapFeatures`) |
| 3 | `Zone Detector` | Custom Component (Python) | Heuristic inefficient-zone detection (`Zone[]`) |
| 4 | `TTM-R2 Forecast` | Custom Component (HuggingFace model wrapper) | 5-lap SoC trajectory (optional) |
| 5 | `Docling Reg Retriever` | Custom Component (Docling) | Find energy-management chunks (`RegulationChunk`) |
| 6 | `Granite Reasoning` | Granite Instruct | Causal reasoning chain (`ReasoningOutput`) |
| 7 | `Pass 1: Validator` | Custom Component (Python) | Deterministic validation (`ValidatorResult`) |
| 8 | `Pass 2: Guardian Score` | Granite Guardian | BYOC scoring (`GuardianResult`) |
| 9 | `Mode Router` | Conditional Router | Engineer vs Fan |
| 10 | `Fan Translator` | Granite Instruct | Plain-language rewrite (`FanOutput`) |
| 11 | `UI Output` | API Output | JSON to frontend (`Recommendation`) |

## Connections

```
1 → 2 → 3 → 6
        2 → 4 → 6   (4 is dashed/optional)
        5 → 6
6 → 7 (Pass 1) → 8 (Pass 2) → 9
9 (engineer branch) → 11
9 (fan branch) → 10 → 11
```

Loops:
- `7 → 6` if Pass 1 fails (regenerate with stricter prompt, max 2 retries).
- `8 → 6` if Pass 2 score < 0.7 (regenerate with explicit citation requirement, max 2 retries).

## Visual styling

- Group 2–4 in a "Telemetry Pipeline" subgraph (light blue background).
- Group 5 alone in a "Regulation Grounding" subgraph (light orange).
- Group 6 in a "Reasoning" subgraph (light green).
- Group 7–8 in a "Two-Pass Safety" subgraph (light yellow).
- Group 9–10 in a "Output Modes" subgraph (light purple).
- Save as `langflow/override.flow.json`. Export PNG at 2× DPI for the README.

## Demo behavior

- The canvas executes one end-to-end sample flow for the demo recording (one TORCS replay → one `Recommendation`).
- The canvas does **not** serve user uploads in production. The React/Vite UI calls FastAPI per [`04-api.md`](./04-api.md).
