# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project context

OVERRIDE is an explainable AI race-strategy copilot for 2026 hybrid energy decisions (telemetry reasoning, regulation grounding, what-if analysis). Submission for the IBM SkillsBuild AI Builders Challenge (May 2026).

Canonical project context lives in `AGENTS.md` (repo root) and `.bob/AGENTS.md` / `.bob/rules.md`. Read them before non-trivial work. Numbered design docs are in `docs/` (`00-thesis`, `02-problem`, `03-architecture`, `03-prd`, `04-schema`, `04-api`, `04-ui-ux-design`, `05-risk`, `05-security`, `06-roadmap`, `06-testing`, `07-deployment`); ADRs are cumulative in `docs/adrs/`.

## Repo state

Most of the pipeline is implemented. `api/`, `core/`, `ingest/`, `analysis/`, `tests/`, `ui/`, `scripts/`, and `langflow/override_components/` all contain working code; `models.json`, `.env.example`, `requirements.txt`, `pytest.ini`, `core/validator.yaml`, `guardian/byoc_criteria.yaml`, and `prompts/*.system.md` are populated.

Known empties / not-yet-shipped: `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`, `core/forecasting.py` (TTM-R2 is **optional**; the pipeline runs without it), `ingest/torcs_parser.py` (TORCS replay path is currently driven through the synthetic JSON fixture / FastF1 path). Verify file has content before assuming a command exists.

## Common commands

Python 3.12 venv at `.venv`. Use the venv binaries directly (don't rely on `source`).

```bash
# Install / refresh deps
.venv/bin/pip install -r requirements.txt

# Run the full test suite (231+ unit tests, network tests skipped by default)
.venv/bin/pytest

# Run a single test file / single test
.venv/bin/pytest tests/test_pipeline.py
.venv/bin/pytest tests/test_pipeline.py::test_name -xvs

# Include network-marked tests (live watsonx / FastF1 calls)
.venv/bin/pytest -m network

# watsonx.ai connectivity smoke test (gate G-1, ~5s)
.venv/bin/python scripts/test_watsonx.py
.venv/bin/python scripts/test_watsonx_embedding.py   # embedding endpoint check

# Rebuild Docling-extracted regulation chunks from PDFs in data/regs/
.venv/bin/python scripts/build_chunks.py

# Run the FastAPI runtime
.venv/bin/uvicorn api.main:app --reload --port 8000

# UI (Vite + React + TS) — separate terminal
cd ui && npm install && npm run dev     # dev server on :3000
cd ui && npm run typecheck              # tsc --noEmit (no eslint configured)
cd ui && npm run build                  # tsc -b && vite build

# Render the architecture diagram
npx -p @mermaid-js/mermaid-cli mmdc -i docs/03-architecture.mmd -o assets/architecture.png
```

Langflow lives in a separate venv (`.venv-langflow`, Python <3.12 constraint) — see README "Optional: Langflow design canvas". It is the design/demo layer; FastAPI is the production runtime.

## Architecture

Pipeline (see `docs/03-architecture.md` for the folder map):

`ingest/` (TORCS JSON / FastF1 → `LapFeatures`) → `analysis/` (zone detection, feature engineering) → `core/forecasting.py` (Granite TTM-R2, **optional**) → `core/reasoning.py` (Granite 4.x Instruct) → `core/regs.py` (Docling extraction + Granite Embedding retrieval) → `core/validator.py` (Pass-1 deterministic, rules in `core/validator.yaml`) → `core/guardian.py` (Pass-2 BYOC, criteria in `guardian/byoc_criteria.yaml`) → `core/fan_mode.py` (engineer→fan translation). `core/pipeline.py` orchestrates; `api/main.py` exposes it as FastAPI.

**Runtime split (ADR-001).** Granite Instruct, Guardian, and Embedding all run on **IBM watsonx.ai (US-South)** via the **chat** API `/ml/v1/text/chat` (the legacy `/ml/v1/text/generation` is deprecated). Only TTM-R2 and Docling chunk extraction run locally. Model IDs and project bindings are pinned in `models.json`; credentials live in `.env`.

**Two-pass safety.** Pass 1 (deterministic validator, no LLM) always runs first; Pass 2 (Granite Guardian BYOC scoring) runs after. Both results are surfaced to the UI.

**Observability.** Direct OpenTelemetry instrumentation (`api/observability.py`). Off by default; toggle with `OVERRIDE_TRACING=otlp` and view in Jaeger (see `docs/plans/p3.6-jaeger-trace-capture.md`).

## Schema conventions (`docs/04-schema.md` is the source of truth)

- Times in seconds (float), energies in MJ (float), powers in kW (float), speeds in km/h (float).
- `lap_number` is 1-indexed.
- `Optional[T]` with `None` for unknowns — never sentinel strings like `"N/A"`.
- All JSON keys `snake_case`.
- When SoC isn't directly exposed, derive from throttle/brake integrals and set `soc_source: "derived"` on `LapFeatures`.

## Non-negotiable guardrails

- **Decision support, never replacement.** Use "supports / explains / highlights / recommends" — never "decides / autonomously / optimal."
- **Pipeline must run end-to-end without TTM.** TTM enhances; it doesn't gate. Sessions with too few laps skip the forecast and lower reported confidence.
- **Never hardcode FIA regulation article numbers** in code, prompts, schemas, tests, or UI strings. Citations render dynamically from the Docling extraction at runtime via the `RegulationSource` struct only.
- **All visuals original.** No F1 broadcast footage, paddock photography, or team livery.
- **"Strategy exploration," not "optimal predictor."** Don't overclaim.

## Behavioral defaults

- Plans go in `docs/plans/`. Delete the plan file in the same PR that ships the feature.
- ADRs in `docs/adrs/` are cumulative — edit the existing ADR rather than appending "but actually."
- Keep `docs/03-architecture.md` and `docs/03-architecture.mmd` in sync with code/folder changes.
- Secrets only in `.env` (gitignored). Never commit.
- `main` is stable/demoable only; `dev` is the daily branch.
