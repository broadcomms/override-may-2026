# AGENTS.md - Plan Mode Rules

This file provides guidance to agents when working with code in this repository.

## Critical Non-Obvious Architecture Constraints

**Early-stage scaffold**: Most files are empty stubs. When planning, base decisions on `docs/04-schema.md` (schemas), `docs/03-architecture.md` (structure), `docs/06-roadmap.md` (phases/gates), not on empty implementation files.

**Verification gates are hard stops**: Roadmap has gates G-1 through G-4. Work below a gate cannot proceed until gate passes. G-1: model tags verified. G-2: SoC source decided. G-4: regulation document selected. Plan around these dependencies.

**Two-pass validation is architectural**: Pass 1 (deterministic) always precedes Pass 2 (AI-based). Both results shown to user. This defense-in-depth is core design—don't plan to merge or skip passes.

**TTM-R2 graceful degradation**: Pipeline MUST run end-to-end without forecasting. Plan all components to handle `forecast=None`. Sessions <30 laps skip TTM; reasoning continues from observed data. This is intentional, not a limitation to fix.

**Regulation citation architecture**: System never hardcodes FIA article numbers anywhere (code, prompts, schemas, tests, UI). Before G-4: generic phrasing. After G-4: citations render from `RegulationSource` at runtime. This affects every component that touches regulations.

**Language constraints are requirements**: "supports/explains/highlights/recommends" vs "decides/autonomously/optimal" distinction comes from IBM challenge rules. Affects prompts, UI copy, documentation. Not negotiable.

**Schema is single source of truth**: All Pydantic schemas in `docs/04-schema.md`. Implementation files reference schemas, never define inline. If planning new features, update schema doc first, then plan implementation.

**Counterintuitive dependencies**: Langflow is design/demo layer only—production runtime is FastAPI. Don't plan Langflow as critical path. TTM-R2 enhances but doesn't gate. Guardian Pass 2 can fail; Pass 1 still ships.

**Plan file lifecycle**: Plans go in `docs/plans/`. Delete plan file in same PR that ships feature. Don't accumulate dead plans. ADRs in `docs/adrs/` are cumulative—edit existing ADR, don't append "but actually".

**Architecture sync requirement**: `docs/03-architecture.md` and `docs/03-architecture.mmd` must stay in sync with code/folder changes. Plan to update both when adding components.

**Branch strategy**: `main` = stable/demoable only. `dev` = daily work. Plan features to land on `dev` first, merge to `main` only when demoable.

**Model version verification**: Exact Ollama tags recorded in `models.json` at G-1. Never plan assuming tag strings—verification gate exists because tags change.