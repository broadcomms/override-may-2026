# AGENTS.md - Ask Mode Rules

This file provides guidance to agents when working with code in this repository.

## Critical Non-Obvious Documentation Context

**Early-stage scaffold**: Most implementation files are empty stubs. When explaining code, verify file has content first. If empty, explain based on schemas in `docs/04-schema.md` and architecture in `docs/03-architecture.md`.

**Documentation hierarchy**: `docs/04-schema.md` is single source of truth for data contracts. `docs/03-architecture.md` + `.mmd` define component relationships. `docs/06-roadmap.md` shows implementation phases with verification gates. If docs conflict with empty code files, docs are authoritative.

**Regulation citation architecture**: System never hardcodes FIA article numbers. Before G-4 gate: generic phrasing only. After G-4: citations render dynamically from `RegulationSource` struct populated by Docling. This is architectural, not just a coding rule—affects prompts, schemas, tests, UI.

**Two-pass validation is architectural**: Pass 1 (deterministic `core/validator.yaml`) always precedes Pass 2 (AI-based `guardian/byoc_criteria.yaml`). Both results shown to user. This defense-in-depth approach is a core design decision, not implementation detail.

**TTM-R2 graceful degradation**: Pipeline designed to run end-to-end without forecasting. TTM enhances but doesn't gate. Sessions <30 laps skip forecast; reasoning continues from observed data. This is intentional architecture, not a limitation.

**Language constraints are challenge requirements**: "supports/explains/highlights/recommends" vs "decides/autonomously/optimal" distinction comes from IBM SkillsBuild Challenge rules (decision support, not replacement). Not just style—affects scoring.

**Counterintuitive folder organization**: `prompts/` contains system prompts that define JSON contracts—these must match Pydantic schemas in implementation files. If prompt and schema disagree, schema wins. Prompts are not just documentation.

**Model version verification**: `models.json` is populated at G-1 with watsonx.ai model IDs + project-id-var (`ibm/granite-4-h-small`, `ibm/granite-guardian-3-8b`, US-South). Granite reasoning runs on watsonx.ai, not local Ollama (see `docs/adrs/ADR-001-watsonx-runtime.md`). Smoke test via `scripts/test_watsonx.py`.

**Schema conventions non-standard**: Times in seconds (not ms), energies in MJ (not kJ/J), `lap_number` 1-indexed (not 0-indexed). These match FIA conventions, not typical programming defaults.

**Branch strategy**: `main` = stable/demoable only. `dev` = daily work. Plans in `docs/plans/` deleted when feature ships. ADRs in `docs/adrs/` are cumulative—edit existing, don't append.