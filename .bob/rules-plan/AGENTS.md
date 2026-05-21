# AGENTS.md - Plan Mode Rules

This file provides guidance to agents when working with code in this repository.

## Critical Non-Obvious Architecture Constraints

**Intentional stub**: `core/forecasting.py` is docstring-only — TTM-R2 deferred to v1.1. Pipeline runs end-to-end without it. This is intentional architecture, not a limitation to fix.

**Verification gates are hard stops**: Roadmap has gates G-1 through G-4. Work below a gate cannot proceed until gate passes. G-1: model tags verified. G-2: SoC source decided. G-4: regulation document selected. Plan around these dependencies.

**Two-pass validation is architectural**: Pass 1 (deterministic) always precedes Pass 2 (AI-based). Both results shown to user. This defense-in-depth is core design—don't plan to merge or skip passes.

**TTM-R2 graceful degradation**: Pipeline MUST run end-to-end without forecasting. Plan all components to handle `forecast=None`. Sessions <30 laps skip TTM; reasoning continues from observed data. This is intentional, not a limitation to fix.

**Regulation citation architecture**: System never hardcodes FIA article numbers anywhere (code, prompts, schemas, tests, UI). Before G-4: generic phrasing. After G-4: citations render from `RegulationSource` at runtime. This affects every component that touches regulations.

**Language constraints are requirements**: "supports/explains/highlights/recommends" vs "decides/autonomously/optimal" distinction comes from IBM challenge rules. Affects prompts, UI copy, documentation. Not negotiable.

**Schema is single source of truth**: All Pydantic schemas in `docs/04-schema.md`. Implementation files reference schemas, never define inline. If planning new features, update schema doc first, then plan implementation.

**Counterintuitive dependencies**: Langflow is design/demo layer only—production runtime is FastAPI. Don't plan Langflow as critical path. TTM-R2 enhances but doesn't gate. Guardian Pass 2 can fail; Pass 1 still ships.

**Plan file lifecycle**: Plans go in `docs/plans/`. Delete plan file in same PR that ships feature. Don't accumulate dead plans. ADRs in `docs/adrs/` are cumulative—edit existing ADR, don't append "but actually".

**Architecture sync requirement**: `docs/03-architecture.md` and `docs/03-architecture.mmd` must stay in sync with code/folder changes. Plan to update both when adding components.

**Model runtime**: Granite served via watsonx.ai (`ibm/granite-4-h-small`, `ibm/granite-guardian-3-8b`); IDs pinned in `models.json` at G-1. Original Ollama path superseded by `docs/adrs/ADR-001-watsonx-runtime.md`. Plan around the watsonx chat API `/ml/v1/text/chat` (not deprecated `/ml/v1/text/generation`).

**SoC derivation architecture**: When battery SoC not directly available, derive from throttle/brake integrals via `analysis/torcs_energy.derive_lap_energy`. Set `soc_source: "derived"` in `LapFeatures`. Shared constants in `analysis/torcs_energy.py` prevent parser drift between TORCS and FastF1 sources.

**JSONL safe-read pattern**: `ingest/torcs_parser.py` reads while telemetry logger appends. Last line may be partial write without newline. Parser skips incomplete lines silently—this is intentional for live-ingest path.