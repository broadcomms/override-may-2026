# AGENTS.md - Ask Mode Rules

This file provides guidance to agents when working with code in this repository.

## Critical Non-Obvious Documentation Context

**Intentional stub**: `core/forecasting.py` is docstring-only — TTM-R2 deferred to v1.1. Pipeline runs end-to-end without it. This is intentional architecture, not a limitation.

**Documentation hierarchy**: `docs/04-schema.md` is single source of truth for data contracts. `docs/03-architecture.md` + `.mmd` define component relationships. If docs conflict with code, docs are authoritative.

**Regulation citation architecture**: System never hardcodes FIA article numbers anywhere (code/prompts/schemas/tests/UI). Before G-4: generic phrasing only. After G-4: citations render dynamically from `RegulationSource` struct populated by Docling. This is architectural, not just a coding rule.

**Two-pass validation is architectural**: Pass 1 (deterministic `core/validator.yaml`) always precedes Pass 2 (AI-based `guardian/byoc_criteria.yaml`). Both results shown to user. This defense-in-depth approach is a core design decision, not implementation detail.

**TTM-R2 graceful degradation**: Pipeline designed to run end-to-end without forecasting. TTM enhances but doesn't gate. Sessions <30 laps skip forecast; reasoning continues from observed data. This is intentional architecture.

**Language constraints are challenge requirements**: "supports/explains/highlights/recommends" vs "decides/autonomously/optimal" distinction comes from IBM SkillsBuild Challenge rules (decision support, not replacement). Not just style—affects scoring.

**Counterintuitive folder organization**: `prompts/` contains system prompts that define JSON contracts—these must match Pydantic schemas exactly. If prompt and schema disagree, schema wins. Prompts are not just documentation.

**Model runtime**: `models.json` pinned at G-1 with watsonx.ai model IDs (`ibm/granite-4-h-small`, `ibm/granite-guardian-3-8b`, US-South). Granite runs on watsonx.ai, not local Ollama (see `docs/adrs/ADR-001-watsonx-runtime.md`). Use chat API `/ml/v1/text/chat` — `/ml/v1/text/generation` is deprecated.

**Schema conventions (FIA-aligned, not typical)**: Times in seconds (not ms), energies in MJ (not kJ/J), `lap_number` 1-indexed (not 0-indexed). These match FIA conventions, not typical programming defaults.

**SoC derivation architecture**: When battery SoC not directly available, derive from throttle/brake integrals via `analysis/torcs_energy.derive_lap_energy`. Set `soc_source: "derived"` in `LapFeatures`. Shared constants in `analysis/torcs_energy.py` prevent parser drift between TORCS and FastF1 sources.

**JSONL safe-read pattern**: `ingest/torcs_parser.py` reads while telemetry logger appends. Last line may be partial write without newline. Parser skips incomplete lines silently—this is intentional for live-ingest path.