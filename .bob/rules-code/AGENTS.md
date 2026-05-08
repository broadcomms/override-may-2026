# AGENTS.md - Code Mode Rules

This file provides guidance to agents when working with code in this repository.

## Critical Non-Obvious Coding Rules

**Empty scaffold warning**: Most Python files are empty stubs. Before implementing, verify the file has content. If empty, implement from scratch following schemas in `docs/04-schema.md`.

**Schema is source of truth**: All Pydantic schemas defined in `docs/04-schema.md` §1-12. Implementation files reference schemas, never define them inline. If prompt contract and schema disagree, schema wins—update prompt.

**Regulation citation implementation**: Never hardcode FIA article numbers. Before G-4 gate: use generic phrasing, `RegulationSource` fields are `None`. After G-4: citations render from `RegulationSource` struct populated by Docling at runtime. See `docs/04-schema.md` §6.

**Two-pass validation order**: Pass 1 (`core/validator.py` using `core/validator.yaml`) MUST complete before Pass 2 (`core/guardian.py` using `guardian/byoc_criteria.yaml`). Both results persist to output—never skip Pass 1.

**TTM-R2 optional path**: All forecasting code must handle `forecast=None` gracefully. Sessions <30 laps skip TTM; reasoning continues from observed data only. Never gate pipeline on TTM availability.

**SoC derivation**: When `soc_start`/`soc_end` not directly available, derive from throttle/brake integrals. Set `soc_source: "derived"` in `LapFeatures`. Document derivation in code comments and `docs/plans/torx-telemetry-map.md`.

**Prompt output contracts**: JSON shapes in `prompts/*.system.md` must match Pydantic schemas exactly. Reasoning output → `ReasoningOutput`, Fan Mode → `FanOutput`, Grounding → see `docs/04-schema.md` §5.

**Unit conventions**: Times=seconds (float), energies=MJ (float), powers=kW (float), speeds=km/h (float). `lap_number` is 1-indexed. Use `Optional[T]` with `None` for unknowns—never sentinel strings.

**Language safety**: Never use "decides/autonomously/optimal/you must/always/definitely will" in generated text. Use "supports/explains/highlights/recommends/could explore/consider". This is decision support, not replacement.

**Model tags**: Exact Ollama tags for Granite models recorded in `models.json` after G-1 gate. Never assume tag strings—read from `models.json` or verify from `github.com/ibm-granite-community`.

**No MCP or Browser tools**: Code mode does not have access to MCP servers or browser automation tools.