# Architecture

OVERRIDE now ships in three connected shapes:

1. A replay-first web app served by FastAPI + the built React/Vite bundle.
2. A managed live TORCS workflow with a control daemon, shared telemetry volume, cockpit UI, and post-race ingest.
3. A Langflow design/demo layer that mirrors the production pipeline but does not replace it.

The production path is `ui/` → `api/main.py` → `core/pipeline.py`. Langflow remains documentation and demo tooling.

## Architecture Diagram

See [`docs/03-architecture.mmd`](../docs/03-architecture.mmd) for the Mermaid source.

```sh
npx -p @mermaid-js/mermaid-cli mmdc -i docs/03-architecture.mmd -o assets/architecture.png
```

![Architecture](../assets/architecture.png)

Legend:
- Dashed edge: optional path or graceful-degradation path.
- Green: deterministic safety layer.
- Blue: model-backed reasoning and scoring.
- Orange: user-facing surfaces.

## Runtime Topology

### 1. Web application surface

- `ui/` is a React 18 + Vite + TypeScript SPA with routes for `/upload`, `/driver-lab`, `/sessions`, `/sessions/compare`, `/cockpit`, and `/session/:session_id`.
- In development, Vite serves the UI and proxies `/api/*` to FastAPI.
- In the container image, `api/main.py` mounts `ui/dist` so the API and SPA ship from the same origin on `:8000`.

### 2. Replay analysis path

- `POST /api/sessions` accepts a TORCS replay or FastF1-derived payload.
- `ingest/torcs_parser.py` and `ingest/fastf1_parser.py` normalize data into `LapFeatures`.
- `core/pipeline.py` truncates to the most recent 30 laps for model context, detects zones, optionally forecasts, retrieves regulation chunks, reasons, validates, and scores.
- The result is persisted under `data/sessions/{session_id}/` via `api/storage.py` and returned as a `Session`.

### 3. Live TORCS path

- The `torcs` compose service runs the SkillsBuild TORCS environment plus `RaceYourCode/gym_torcs/control_daemon.py`.
- `POST /api/torcs/start-race` creates an `ACTIVE` stub session before asking the daemon to launch a managed race.
- TORCS telemetry is written to the shared `torcs-telemetry` volume.
- `GET /api/sessions/{id}/stream` tails that JSONL file, emits live snapshots and completed laps over SSE, and closes when the file stalls.
- `POST /api/sessions/torcs-live` parses the finished JSONL, re-runs the full pipeline, and upgrades the stub session to a completed debrief.

### 4. Driver profile path

- Shipped defaults live in `config/torcs_driver_profiles/`.
- User-saved profiles live in `data/torcs_driver_profiles/`.
- `torcs_driver_profiles.py` owns CRUD, validation, duplication, and snapshotting.
- Selected profiles are stamped into live-session launch metadata and preserved in the completed session payload as `driver_config_snapshot`.

### 5. External model and regulation dependencies

- Granite Instruct, Granite Guardian, and Granite Embedding run through watsonx.ai.
- Regulation chunks are loaded from `data/regs/extracted_chunks.sample.json` and retrieved deterministically by `core/regs.py`.
- TTM-R2 remains optional. If forecasting is unavailable or low-confidence, the pipeline continues with observed evidence only.

## Core Backend Flow

### Replay/session creation

1. API parses upload or live-capture JSONL into `LapFeatures`.
2. `analysis/zone_detector.py` emits deterministic `Zone` objects.
3. `core/forecasting.py` may return a `Forecast`, otherwise `None`.
4. `core/regs.py` retrieves the best matching regulation chunk for each zone.
5. `core/reasoning.py` produces a `ReasoningOutput`.
6. `core/validator.py` runs Pass 1 deterministic validation.
7. `core/guardian.py` runs Pass 2 Guardian scoring.
8. `core/pipeline.py` applies retry directives when either pass fails, then assembles `Recommendation` and `Session`.

### Lazy follow-up flows

- Fan Mode is not generated during the initial pipeline run. `GET /api/sessions/{id}/zones/{zid}?mode=fan|both` generates and caches it on demand.
- What-if runs are not a forked pipeline. `analysis/perturbations.py` mutates lap features, then `core/pipeline.py` is re-run and cached under `data/sessions/{id}/whatif/`.
- Session history enrichment is live-aware. Active TORCS rows patch in completed-lap counts from the shared telemetry file without waiting for final ingest.

## Safety Architecture

### Pass 1: deterministic validator

- Source: [`core/validator.py`](../core/validator.py) + [`core/validator.yaml`](../core/validator.yaml)
- Checks: energy bounds, harvest-cap logic, citation existence, language safety, and citation/source consistency.
- On failure, `core/pipeline.py` retries reasoning with a stricter directive.

### Pass 2: Granite Guardian BYOC

- Source: [`core/guardian.py`](../core/guardian.py) + [`guardian/byoc_criteria.yaml`](../guardian/byoc_criteria.yaml)
- Criteria: `energy_safety` and `regulation_consistency`.
- Guardian scoring never replaces Pass 1; it follows it.
- If retries are exhausted, the recommendation still ships with low confidence instead of disappearing silently.

## Persistence Layout

Session storage is intentionally file-based.

```text
data/sessions/
├── _index.json
└── {session_id}/
    ├── summary.json
    ├── laps.parquet
    ├── forecast.json                  # optional
    ├── recommendations.json
    ├── regulation_source.json         # optional
    ├── driver_config.json             # optional
    └── whatif/
        └── {cache_key}.json
```

Design implications:
- No database is required for the demo or local workflow.
- Session history, comparison, and lazy fan-mode writes all operate on this disk layout.
- `save_recommendations_only()` performs atomic rewrites for concurrent fan-mode requests.

## Frontend Surface Map

- `/upload`: sample replays, bring-your-own upload, live capture controls, capture list, preview strip.
- `/driver-lab`: driver-profile editor for shipped defaults and user-saved variants.
- `/sessions`: history, pagination, selection, bulk delete, compare launch.
- `/sessions/compare`: side-by-side comparison of two sessions.
- `/cockpit`: live race surface with control strip, noVNC/headless frame, timing rail, hybrid rail, lap timeline, and deterministic live insight.
- `/session/:session_id`: completed or active session detail with KPI strip, live telemetry panel for active sessions, Engineer/Fan recommendation rendering, heatmap, energy curve, and what-if diffs.

## Repo Map

```text
overdrive-may-2026/
├── api/                              # FastAPI runtime, storage, errors, tracing
├── analysis/                         # Deterministic telemetry enrichment + perturbations
├── core/                             # Pipeline, reasoning, validation, Guardian, regs, forecasting
├── ingest/                           # Source parsers + shared Pydantic schemas
├── ui/                               # React/Vite app
├── RaceYourCode/gym_torcs/           # TORCS driver + control daemon sidecar code
├── config/torcs_driver_profiles/     # Shipped read-only driver profiles
├── data/
│   ├── regs/                         # Regulation chunks sample
│   ├── samples/                      # Real TORCS lab captures
│   ├── sessions/                     # Persisted app sessions
│   └── torcs_driver_profiles/        # User-created driver profiles
├── langflow/override_components/     # Langflow mirror components
├── prompts/                          # System prompts for reasoning/fan/grounding
├── guardian/                         # BYOC scoring criteria
├── scripts/                          # Utility, evaluation, and runtime support scripts
└── tests/                            # 419 collected tests as of 2026-05-19
```

## Verification Snapshot

- `npm --prefix ui run build` succeeds against the current UI bundle.
- `pytest --collect-only -q -s tests` currently collects **419 tests**, including **4** network-marked tests.
- The documentation below should be kept aligned with:
  - [`docs/04-schema.md`](./04-schema.md)
  - [`docs/04-api.md`](./04-api.md)
  - [`docs/04-ui-ux-design.md`](./04-ui-ux-design.md)
  - [`docs/07-deployment.md`](./07-deployment.md)

## Branch Strategy

- `main`: stable, demoable state only.
- `dev`: daily working branch.
- ADRs are cumulative and edited in place under `docs/adrs/`.
- Ship plans belong in `docs/plans/` and should be deleted when the feature is complete.
