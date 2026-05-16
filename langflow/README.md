# OVERRIDE — Langflow Canvas

> Langflow is the **design + demo layer** for OVERRIDE, not the production runtime.
> Production calls go through `api/main.py` (FastAPI). This canvas mirrors the
> pipeline architecture so a reviewer can step through ingest → analysis →
> reasoning → guardian visually, and so the demo video has a one-shot
> end-to-end execution.
>
> Spec: [`docs/04-langflow-canvas.md`](../docs/04-langflow-canvas.md). Models &
> runtime: [`docs/adrs/ADR-001-watsonx-runtime.md`](../docs/adrs/ADR-001-watsonx-runtime.md).

This directory ships **executable Custom Components** + an assembly guide.
The actual `override.flow.json` is exported by you from the Langflow UI
after assembling the canvas — Langflow's flow JSON schema is internal and
breaks across versions, so we don't hand-author it.

---

## 1. Quickstart — compose mode (recommended, ~5 min)

The fastest documented path is `podman-compose up override langflow`. It builds a
Langflow image (langflow 1.9.2 + OVERRIDE's runtime deps), bind-mounts
`core/`, `ingest/`, `analysis/`, `guardian/`, `prompts/`, and the components
themselves at `/workspace/...`, and reads watsonx credentials from `.env`.

```bash
cp .env.example .env          # fill WATSONX_API_KEY + WATSONX_PROJECT_ID
podman-compose up override langflow
```

First build is ~3–5 min (`Dockerfile.langflow` layers `requirements.txt`
onto the official `langflowai/langflow` base). Subsequent starts are
fast — code is bind-mounted, so editing a component on the host shows
up after a Langflow UI reload, no rebuild needed.

Langflow opens at http://localhost:7860. Skip to §3 (assemble the canvas).

> Service selection is explicit. Pair it with TORCS using
> `podman-compose up override torcs langflow`, which brings up the
> live TORCS lab alongside the canvas (handy if you want the canvas's
> File Input node to pick up a freshly-driven JSONL capture from the
> shared `torcs-telemetry` volume — files live in `/app/data/telemetry/`
> on the override side, mounted into langflow at `/workspace/data/telemetry/`
> if you add that volume entry).

## 1b. Alternative — separate venv on the host (~10 min)

For hacking on the components directly with a local Python toolchain (no
container rebuild on every edit), the historical venv path still works:

### 1b.1 Separate venv

Langflow supports Python 3.10–3.13 on Linux. The repo's `requirements-langflow.txt`
pins `langflow==1.9.2`, which works under 3.12. The split exists to keep
Langflow's ~200 transitive deps out of the production runtime's pip set
— a dependency-graph hedge, not an interpreter version conflict.

```bash
python3.12 -m venv .venv-langflow
.venv-langflow/bin/pip install -r requirements-langflow.txt
```

### 1b.2 Make the OVERRIDE codebase importable

The Custom Components do `from core.regs import ...`, `from ingest.schema import ...`, etc. Langflow needs the project root on `PYTHONPATH`:

```bash
export PYTHONPATH="$(pwd):$PYTHONPATH"
```

Run this from the OVERRIDE project root before starting Langflow. (You can also add it to `~/.zshrc` if you want it permanent.)

### 1b.3 watsonx credentials

The components that touch Granite (Reg Retriever, Reasoning, Guardian, Fan Translator) read credentials from environment variables — same as the FastAPI runtime. Source `.env` before starting Langflow:

```bash
set -a && source .env && set +a
```

This exposes `WATSONX_API_KEY`, `WATSONX_URL`, `WATSONX_PROJECT_ID`,
`GRANITE_INSTRUCT`, `GRANITE_GUARDIAN`, `GRANITE_EMBEDDING`.

### 1b.4 Pre-built regulation chunks

The Reg Retriever loads `data/regs/extracted_chunks.json`. If you haven't
run Docling extraction yet, the component falls back to the committed
`data/regs/extracted_chunks.sample.json` — which is the canonical demo
chunks file (Issue 18 Section C, 384 chunks).

---

## 2. Launch Langflow (venv path)

```bash
LANGFLOW_COMPONENTS_PATH="$(pwd)/langflow/override_components" \
PYTHONPATH="$(pwd):$PYTHONPATH" \
.venv-langflow/bin/langflow run
```

> **Don't rename `override_components/` back to `components/`.** Langflow's
> custom-component loader treats a folder named literally `components` as
> an internal wrapper and flattens it out of the registry shape, which
> corrupts the schema the frontend expects. The frontend then tries to
> read `.template` off field-names like `description` / `icon` / `outputs`
> and the React tree throws `Cannot read properties of undefined (reading 'match')`.
> Any folder name except `components/` works.

Langflow opens at http://localhost:7860. Under the component palette
("Custom" section), you should see:

- Ingest & Aggregate
- Zone Detector
- TTM-R2 Forecast
- Docling Reg Retriever
- Granite Reasoning
- Pass 1: Validator
- Pass 2: Guardian Score
- Fan Translator

If they don't appear, double-check that the directory exists at
`langflow/override_components/` and that `LANGFLOW_COMPONENTS_PATH` matches.

---

## 3. Assemble the canvas (~20 min)

Drop these 11 nodes onto the canvas, left-to-right, top-to-bottom (per
`docs/04-langflow-canvas.md §Nodes`):

| # | Node label | Component | Notes |
|---|---|---|---|
| 1 | Upload Session File | Built-in **File Input** (Langflow stock) | |
| 2 | Ingest & Aggregate | OVERRIDE custom (`ingest.py`) | source=torcs, soc_max=4.0 |
| 3 | Zone Detector | OVERRIDE custom (`zone_detector.py`) | |
| 4 | TTM-R2 Forecast | OVERRIDE custom (`ttm_forecast.py`) | enabled=False (graceful degradation) |
| 5 | Docling Reg Retriever | OVERRIDE custom (`reg_retriever.py`) | |
| 6 | Granite Reasoning | OVERRIDE custom (`reasoning.py`) | |
| 7 | Pass 1: Validator | OVERRIDE custom (`validator.py`) | |
| 8 | Pass 2: Guardian Score | OVERRIDE custom (`guardian.py`) | |
| 9 | Mode Router | Built-in **Conditional Router** | conditions: input["mode"] == "engineer" / "fan" |
| 10 | Fan Translator | OVERRIDE custom (`fan_translator.py`) | |
| 11 | UI Output | Built-in **JSON Output** or **Text Output** | |

### Connections

```
1 (FileInput.path) → 2 (Ingest.file_path)
2 (Ingest.lap_window) → 3 (ZoneDetector.lap_window)
2 (Ingest.lap_window) → 4 (TTMForecast.lap_window)        # dashed: optional
3 (ZoneDetector.zone) → 5 (RegRetriever.zone_payload)
5 (RegRetriever.regulation) → 6 (Reasoning.regulation_payload)
4 (TTMForecast.forecast) → 6 (Reasoning.forecast_payload)
6 (Reasoning.reasoning_bundle) → 7 (Validator.reasoning_bundle)
7 (Validator.validator_bundle) → 8 (Guardian.validator_bundle)
8 (Guardian.guardian_bundle) → 9 (ModeRouter.input)
9 (engineer branch) → 11 (UIOutput)
9 (fan branch) → 10 (FanTranslator.guardian_bundle)
10 (FanTranslator.fan_bundle) → 11 (UIOutput)
```

### Subgraph styling (per spec)

Group nodes into 5 colored subgraphs in Langflow's group panel:

| Subgraph | Nodes | Color |
|---|---|---|
| Telemetry Pipeline | 2, 3, 4 | light blue |
| Regulation Grounding | 5 | light orange |
| Reasoning | 6 | light green |
| Two-Pass Safety | 7, 8 | light yellow |
| Output Modes | 9, 10 | light purple |

> Langflow's group color is set via right-click → "Group" → color picker.
> If your Langflow version doesn't support per-group colors, that's fine
> for the screenshot — leave them as default Langflow grouping.

---

## 4. Run the demo flow once

1. Click the **File Input** node and pick `data/sessions/sample_torcs.json`
   (or any TORCS export from `data/sessions/`).
2. In the **Mode Router** node, set the routing key to `"engineer"` for
   the first capture.
3. Click **Run** on the canvas.
4. Each node should turn green and show a status line (e.g. *"Detected 5 zones"*,
   *"Pass-1 PASSED"*, *"Pass-2 score=0.85"*).
5. Inspect the UI Output node — it should show a `Recommendation`-shaped JSON.

If a node turns red, click it for the traceback. Common fixes:

- **`ImportError: No module named 'core'`** — `PYTHONPATH` not set in
  the shell that launched Langflow. Restart Langflow with the env var.
- **`RuntimeError: missing WATSONX_API_KEY`** — `.env` not sourced in
  Langflow's shell. Source it and restart.
- **`No chunks at data/regs/extracted_chunks.json`** — fine; the component
  falls back to the `.sample.json` automatically.

---

## 5. Export the flow + screenshot (~5 min)

### Save the flow JSON

In Langflow UI:
1. Click the menu → **Export Flow** → save as `langflow/override.flow.json`.
2. Commit alongside the `assets/screenshots/langflow-canvas.png`.

### Capture the canvas screenshot

1. Zoom-fit the canvas so all 11 nodes are visible.
2. Capture at 2× DPI (per `docs/04-ui-ux-design.md §11`).
3. Save as `assets/screenshots/langflow-canvas.png` (currently a 0-byte placeholder).

For best framing: include the subgraph colors + at least one node's
expanded status line showing live execution numbers (e.g. the Reasoning
node's "3-step chain, confidence=medium, citation=present").

### Optional: capture the fan-mode variant

For the demo video, you may want to capture both engineer and fan branches
running. Re-run the flow with the Mode Router set to `"fan"` and save the
second screenshot as `langflow-canvas-fan.png` (optional — not required
for submission).

---

## 6. Cleanup

After the screenshot is committed:

```bash
# Stop Langflow (Ctrl-C in the terminal that ran it)
# Optional — keep the venv around for re-recording
```

Per `.bob/rules.md`, any `docs/plans/p3.1-*.md` plan file goes away in the
same PR that ships the captured screenshot. (P3.1 doesn't have a plan
file in `docs/plans/` — the assembly guidance lives in this README, which
is a permanent operator runbook, not a temporary plan.)

---

## Component reference

Each file is a thin adapter — the heavy lifting is in `core/` and `ingest/`,
shared with the FastAPI runtime. Total custom-component LoC: ~600.

| Component | File | Underlying production function |
|---|---|---|
| Ingest & Aggregate | `components/ingest.py` | Mirrors `api/main.py::_parse_upload` (canonical lap-features JSON or FastF1 parquet). Switches to `ingest.torcs_parser.parse_torcs` once G-2 lands. |
| Zone Detector | `components/zone_detector.py` | `analysis.zone_detector.detect_zones` |
| TTM-R2 Forecast | `components/ttm_forecast.py` | `core.forecasting.forecast_soc` (optional, post-G-3 — component emits null when module is empty) |
| Docling Reg Retriever | `components/reg_retriever.py` | `core.regs.retrieve_chunk` + `core.regs.load_chunks` |
| Granite Reasoning | `components/reasoning.py` | `core.reasoning.reason_about_zone` |
| Pass 1: Validator | `components/validator.py` | `core.validator.validate` |
| Pass 2: Guardian Score | `components/guardian.py` | `core.guardian.score_recommendation` |
| Fan Translator | `components/fan_translator.py` | `core.fan_mode.translate_to_fan_mode` |

The canvas is a one-shot demo — it does NOT replicate the production
retry loops or cross-zone parallelism (those live in `core.pipeline.run_pipeline`).
For an end-to-end retry-loop demo, run the FastAPI service directly and
record the engineer-mode UI.
