# AGENTS.md - Code Mode Rules

This file provides guidance to agents when working with code in this repository.

## Critical Non-Obvious Coding Rules

**Intentional stub (do NOT "fix")**: `core/forecasting.py` is docstring-only — TTM-R2 deferred to v1.1. Pipeline runs end-to-end without it.

**Schema is source of truth**: All Pydantic schemas defined in `docs/04-schema.md` §1-12. Implementation files reference schemas, never define them inline. If prompt contract and schema disagree, schema wins—update prompt.

**NEVER hardcode FIA article numbers** anywhere. Before G-4: use generic phrasing, `RegulationSource` fields are `None`. After G-4: citations render from `RegulationSource` struct populated by Docling at runtime. See `docs/04-schema.md` §6.

**Two-pass validation order**: Pass 1 (`core/validator.py` using `core/validator.yaml`) MUST complete before Pass 2 (`core/guardian.py` using `guardian/byoc_criteria.yaml`). Both results persist to output—never skip Pass 1.

**TTM-R2 graceful degradation**: All forecasting code must handle `forecast=None`. Sessions <30 laps skip TTM; reasoning continues from observed data only. Never gate pipeline on TTM availability.

**SoC derivation**: When `soc_start`/`soc_end` not directly available, derive from throttle/brake integrals via `analysis/torcs_energy.derive_lap_energy`. Set `soc_source: "derived"` in `LapFeatures`. Shared constants in `analysis/torcs_energy.py` prevent parser drift.

**Prompt output contracts**: JSON shapes in `prompts/*.system.md` must match Pydantic schemas exactly. Reasoning output → `ReasoningOutput`, Fan Mode → `FanOutput`, Grounding → see `docs/04-schema.md` §5.

**Unit conventions (FIA-aligned, not typical)**: Times=seconds (float), energies=MJ (float), powers=kW (float), speeds=km/h (float). `lap_number` is 1-indexed. Use `Optional[T]` with `None` for unknowns—never sentinel strings.

**Language safety (IBM challenge requirement)**: Never use "decides/autonomously/optimal/you must/always/definitely will" in generated text. Use "supports/explains/highlights/recommends/could explore/consider". This is decision support, not replacement.

**watsonx.ai runtime (not Ollama)**: Granite models served via watsonx.ai US-South. Model IDs (`ibm/granite-4-h-small`, `ibm/granite-guardian-3-8b`) pinned in `models.json`. Use chat API `/ml/v1/text/chat` — `/ml/v1/text/generation` is deprecated. Smoke test: `scripts/test_watsonx.py`.

**JSONL safe-read**: `ingest/torcs_parser.py` reads while telemetry logger appends. Last line may be partial write without newline. Parser skips incomplete lines silently.

**No MCP or Browser tools**: Code mode does not have access to MCP servers or browser automation tools.