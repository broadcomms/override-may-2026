# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Build/Test Commands

```bash
# Python 3.12 venv at .venv — use venv binaries directly
.venv/bin/pip install -r requirements.txt

# Run full test suite (419 tests: 415 unit, 4 network-marked)
.venv/bin/pytest

# Run single test file or specific test
.venv/bin/pytest tests/test_pipeline.py
.venv/bin/pytest tests/test_pipeline.py::test_name -xvs

# Include network tests (live watsonx/FastF1 calls)
.venv/bin/pytest -m network

# watsonx.ai smoke test (gate G-1, ~5s)
.venv/bin/python scripts/test_watsonx.py

# Run FastAPI server
.venv/bin/uvicorn api.main:app --reload --port 8000

# UI (separate terminal, Node 20)
cd ui && npm install && npm run dev        # dev server :3000
cd ui && npm run typecheck                 # tsc --noEmit (no eslint)
cd ui && npm run build                     # production build

# Render architecture diagram
npx -p @mermaid-js/mermaid-cli mmdc -i docs/03-architecture.mmd -o assets/architecture.png
```

## Critical Non-Obvious Rules

**Intentional stub (do NOT "fix")**: `core/forecasting.py` is docstring-only — TTM-R2 deferred to v1.1. Pipeline runs end-to-end without it.

**Deleted (do NOT recreate)**: `.github/workflows/ci.yml` removed — CI deferred to v1.1.

**NEVER hardcode FIA article numbers** anywhere (code/prompts/schemas/tests/UI). Before G-4: generic phrasing. After G-4: citations render from `RegulationSource` at runtime via Docling.

**Language safety (IBM challenge requirement)**: Use "supports/explains/highlights/recommends" — NEVER "decides/autonomously/optimal". This is decision support, not replacement.

**Two-pass validation order**: Pass 1 (`core/validator.yaml` deterministic) MUST complete before Pass 2 (`guardian/byoc_criteria.yaml` AI-based). Both results shown to user.

**TTM-R2 graceful degradation**: All code must handle `forecast=None`. Sessions <30 laps skip TTM; reasoning continues from observed data.

**watsonx.ai runtime (not Ollama)**: Granite Instruct + Guardian served via watsonx.ai US-South. Model IDs (`ibm/granite-4-h-small`, `ibm/granite-guardian-3-8b`) pinned in `models.json`. Use chat API `/ml/v1/text/chat` — `/ml/v1/text/generation` is deprecated. Smoke test: `scripts/test_watsonx.py`.

**Unit conventions (FIA-aligned, not typical)**: Times=seconds (float), energies=MJ (float), powers=kW (float), speeds=km/h (float). `lap_number` is 1-indexed. Use `Optional[T]` with `None` for unknowns—never sentinel strings.

**SoC derivation flag**: When battery SoC not directly available, derive from throttle/brake integrals via `analysis/torcs_energy.derive_lap_energy`. Set `soc_source: "derived"` in `LapFeatures`. Shared constants in `analysis/torcs_energy.py` prevent parser drift.

**Prompt contracts must match schemas**: JSON shapes in `prompts/*.system.md` must match Pydantic schemas in `docs/04-schema.md` exactly. If they disagree, schema wins—update prompt.

**JSONL safe-read**: `ingest/torcs_parser.py` reads while telemetry logger appends. Last line may be partial write without newline. Parser skips incomplete lines silently.

**Branch strategy**: `main` = stable/demoable only. `dev` = daily work. Plans in `docs/plans/` deleted when feature ships. ADRs in `docs/adrs/` cumulative—edit existing, don't append.

**Architecture sync**: Keep `docs/03-architecture.md` and `.mmd` in sync with code changes.

## Reference Files

- `CLAUDE.md` — Claude Code guidance with common commands
- `docs/04-schema.md` — Pydantic schemas (single source of truth)
- `docs/03-architecture.md` — folder structure and component map
- `docs/adrs/ADR-001-watsonx-runtime.md` — watsonx.ai migration rationale
- `docs/adrs/ADR-002-torcs-as-primary-sandbox.md` — synthetic energy model