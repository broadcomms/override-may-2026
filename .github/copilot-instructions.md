# GitHub Copilot Instructions — OVERRIDE

OVERRIDE is an explainable AI race-strategy copilot for 2026 hybrid energy decisions (telemetry reasoning, regulation grounding, what-if analysis). IBM SkillsBuild AI Builders Challenge submission (May 2026).

---

## Commands

Python 3.12 venv at `.venv`. Use venv binaries directly — do not rely on `source`.

```bash
# Backend deps
.venv/bin/pip install -r requirements.txt

# Run all unit tests (network tests skipped by default)
.venv/bin/pytest

# Run a single test file or single test
.venv/bin/pytest tests/test_pipeline.py
.venv/bin/pytest tests/test_pipeline.py::test_name -xvs

# Run network-marked tests (live watsonx / FastF1 calls)
.venv/bin/pytest -m network

# watsonx connectivity smoke test (~5s)
.venv/bin/python scripts/test_watsonx.py
.venv/bin/python scripts/test_watsonx_embedding.py

# FastAPI dev server
.venv/bin/uvicorn api.main:app --reload --port 8000

# UI (React + Vite + TypeScript) — separate terminal
cd ui && npm install && npm run dev       # dev on :3000
cd ui && npm run typecheck               # tsc --noEmit (no eslint)
cd ui && npm run build

# Re-extract regulation chunks from PDFs in data/regs/
.venv/bin/python scripts/build_chunks.py

# Render architecture diagram
npx -p @mermaid-js/mermaid-cli mmdc -i docs/03-architecture.mmd -o assets/architecture.png
```

---

## Architecture

The pipeline is a linear async chain orchestrated by `core/pipeline.py`:

```
ingest/ (TORCS JSONL or FastF1 → LapFeatures)
  → analysis/ (zone detection, feature engineering)
  → core/forecasting.py (Granite TTM-R2 — OPTIONAL, graceful-degradation)
  → core/reasoning.py (Granite 4.x Instruct)
  → core/regs.py (Docling extraction + Granite Embedding retrieval)
  → core/validator.py (Pass-1 deterministic, rules in core/validator.yaml)
  → core/guardian.py (Pass-2 BYOC scoring, criteria in guardian/byoc_criteria.yaml)
  → core/fan_mode.py (engineer→fan translation, lazy per request)
```

`api/main.py` (FastAPI) wraps `run_pipeline` and also serves the built React UI from `ui/dist` via StaticFiles. `api/storage.py` handles atomic session persistence.

**LLM runtime split.** Granite Instruct (`ibm/granite-4-h-small`) and Granite Guardian (`ibm/granite-guardian-3-8b`) use `/ml/v1/text/chat`. Granite Embedding (`ibm/granite-embedding-278m-multilingual`) uses `/ml/v1/text/embeddings`. The legacy `/ml/v1/text/generation` endpoint is deprecated — do not use it. Model IDs and project binding are pinned in `models.json`. TTM-R2 and Docling run locally.

**LLM abstraction.** `core/llm_clients/` implements the `WatsonxChatClient` Protocol. All LLM clients are **injected** — tests pass fakes; production passes the real impls. Set `OVERRIDE_LLM_RUNTIME=ollama` to swap in `ollama.py` for local dev without watsonx credentials.

**Langflow.** Lives in a separate venv (`.venv-langflow`, Python <3.12 constraint). It is the design/demo layer; FastAPI is the production runtime.

**Two-pass safety.** Pass 1 (deterministic, no LLM) always runs before Pass 2 (Guardian BYOC scoring). Both results are surfaced in the UI.

**Observability.** `api/observability.py` wraps OpenTelemetry. Off by default; set `OVERRIDE_TRACING=otlp` to enable and view traces in Jaeger.

---

## Key Conventions

### Testing patterns
- LLM clients are injected via Protocol — tests pass fake/stub implementations, never hit the network
- Synthetic `LapFeatures` fixtures are built inline in each test file (see `_lap()` helper pattern in `test_pipeline.py`)
- Captured JSON fixtures in `tests/fixtures/` (`engineer_happy_demo.json`, `fan_mode_demo.json`, etc.) are used for round-trip schema validation
- `@pytest.mark.network` gates any test that calls live watsonx or FastF1 endpoints

### Key environment variables
- `WATSONX_PROJECT_ID`, `WATSONX_API_KEY` — required for production; see `.env.example`
- `OVERRIDE_LLM_RUNTIME=ollama` — swaps all LLM calls to local Ollama (no watsonx credentials needed)
- `OVERRIDE_TRACING=otlp` — enables OpenTelemetry tracing to Jaeger
- `OVERRIDE_UI_ORIGIN` — CORS allowed origin (default: dev frontend)
- `MAX_SESSION_LAPS` — truncation cap per FR-1.3 (default: 120)

### Intentional stub — do not "fix"
`core/forecasting.py` is a docstring-only stub. TTM-R2 is deferred to v1.1. The pipeline runs end-to-end without it — sessions with <30 laps skip the forecast and lower reported confidence.

### Do not recreate
`.github/workflows/ci.yml` was intentionally deleted. CI is deferred to v1.1.

### Schema (`ingest/schema.py` + `docs/04-schema.md` are the single source of truth)
- Times → **seconds** (float), energies → **MJ** (float), powers → **kW** (float), speeds → **km/h** (float)
- `lap_number` is **1-indexed**
- Use `Optional[T]` with `None` for unknowns — never sentinel strings like `"N/A"`
- All JSON keys `snake_case`; the frontend maps to camelCase at the boundary
- When SoC isn't directly exposed by the source, derive from throttle/brake integrals and set `soc_source: "derived"` on `LapFeatures`

### Regulation citations
**Never hardcode FIA article numbers** anywhere (code, prompts, schemas, tests, UI strings). Citations render dynamically from Docling extraction via the `RegulationSource` struct at runtime.

### Language guardrail
Use **"supports / explains / highlights / recommends"** — never "decides / autonomously / optimal". This is decision support, not replacement (IBM challenge requirement).

### Prompt contracts
`prompts/*.system.md` defines the JSON shape the LLM must produce. These must match the corresponding Pydantic schema (`ReasoningOutput`, `FanOutput`, etc.). When prompt and schema disagree, the schema wins and the prompt is updated.

### Documentation
- Plans go in `docs/plans/` and are **deleted** in the same PR that ships the feature
- ADRs in `docs/adrs/` are cumulative — edit the existing ADR, never append "but actually"
- Keep `docs/03-architecture.md` and `docs/03-architecture.mmd` in sync with structural changes

### Branch strategy
- `main` — stable/demoable only
- `dev` — daily working branch

### Secrets
Credentials live in `.env` (gitignored). See `.env.example`. Never commit secrets.
