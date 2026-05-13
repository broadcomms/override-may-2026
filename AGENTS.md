# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Critical Non-Obvious Rules

**Repo state (substantially shipped)**: `api/`, `core/`, `ingest/`, `analysis/`, `tests/`, `ui/`, `scripts/`, and `langflow/override_components/` all contain working code. `requirements.txt`, `Dockerfile`, `Dockerfile.langflow`, `docker-compose.yml`, `models.json`, `core/validator.yaml`, `guardian/byoc_criteria.yaml`, `prompts/*.system.md` are populated. 305 tests green (301 unit + 4 network-marked).

**Intentional stubs (do NOT treat as work-in-progress)**: `core/forecasting.py` is a docstring-only stub — TTM-R2 is deferred to v1.1 per the graceful-degradation guardrail; the pipeline runs end-to-end without it.

**Removed (do NOT recreate)**: `.github/workflows/ci.yml` was deleted (CI deferred to v1.1; never spec'd for v1). The empty placeholder was misleading.

**Regulation citation rule**: NEVER hardcode FIA article numbers in code, prompts, schemas, tests, or UI strings. Before gate G-4, use generic phrasing. After G-4, citations render dynamically from Docling extraction at runtime via `RegulationSource` struct only.

**Language constraints**: Use "supports/explains/highlights/recommends"—NEVER "decides/autonomously/optimal". This is decision support, not replacement (IBM challenge requirement).

**TTM-R2 graceful degradation**: Pipeline MUST run end-to-end without TTM forecasting. TTM enhances but doesn't gate. Sessions <30 laps skip forecast; reasoning continues from observed data.

**Two-pass validation architecture**: Pass 1 (deterministic `core/validator.yaml`) always runs first. Pass 2 (Granite Guardian BYOC `guardian/byoc_criteria.yaml`) scores after. Both results shown to user.

**Model version verification**: Granite Instruct + Guardian are served via **watsonx.ai** (US-South), not local Ollama. Model IDs (`ibm/granite-4-h-small`, `ibm/granite-guardian-3-8b`) and project ID are pinned in `models.json` at gate G-1. See `docs/adrs/ADR-001-watsonx-runtime.md` for the migration rationale. Smoke-test via `scripts/test_watsonx.py`. Use the watsonx **chat** API (`/ml/v1/text/chat`) — the legacy `/ml/v1/text/generation` is deprecated.

**Schema conventions**: Times in seconds (float), energies in MJ (float), powers in kW (float), speeds in km/h (float). `lap_number` is 1-indexed. Use `Optional[T]` with `None` for unknowns—never sentinel strings like "N/A". All JSON keys `snake_case`.

**SoC derivation flag**: When battery state-of-charge not directly exposed by source, derive from throttle/brake integrals and set `soc_source: "derived"` in `LapFeatures`. Document derivation in code comments and `docs/plans/torcs-telemetry-map.md`.

**Branch strategy**: `main` = stable/demoable only. `dev` = daily working branch. Plans go in `docs/plans/`, delete when feature ships. ADRs in `docs/adrs/` are cumulative—edit existing ADR, don't append "but actually".

**Architecture sync**: Keep `docs/03-architecture.md` and `docs/03-architecture.mmd` in sync with code/folder changes. Render diagram: `npx -p @mermaid-js/mermaid-cli mmdc -i docs/03-architecture.mmd -o assets/architecture.png`

**Secrets**: Only in `.env` (gitignored). Never commit.

## Reference Files

- `.bob/AGENTS.md` — comprehensive project context for IBM Bob
- `.bob/rules.md` — behavioral rules (plan file lifecycle, ADR editing)
- `CLAUDE.md` — Claude Code specific guidance
- `docs/03-architecture.md` — folder structure and component map
- `docs/04-schema.md` — Pydantic schemas (single source of truth)
- `docs/06-roadmap.md` — hour-budgeted implementation plan with verification gates