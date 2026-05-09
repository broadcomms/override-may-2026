# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project context

OVERRIDE is an explainable AI race-strategy copilot that helps teams and fans understand 2026 hybrid energy decisions through telemetry reasoning, regulation grounding, and what-if analysis. Submission for the IBM SkillsBuild AI Builders Challenge (May 2026).

`.bob/AGENTS.md` and `.bob/rules.md` are canonical project context — written for IBM Bob but apply to any agent in this repo. Read them before non-trivial work.

## Repo state

Phase 1 setup is complete: `requirements.txt`, `models.json`, `.env.example`, `LICENSE` are populated and watsonx.ai connectivity is verified (gate G-1 closed). Files **still pending implementation**: `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`, every `tests/test_*.py`, `ingest/*.py`, `core/*.py`, `api/main.py`, `ui/package.json`. Don't infer build/test commands from filenames — verify the file has content first.

Files that do have content: `README.md`, `.bob/AGENTS.md`, `.bob/rules.md`, the `docs/*.md` series, `prompts/*.system.md`, `guardian/byoc_criteria.yaml`, `core/validator.yaml`, and the two FIA PDFs in `data/regs/`.

## Architecture

See `docs/03-architecture.md` (folder tree, legend) and `docs/03-architecture.mmd` (Mermaid source). Render the diagram with:

    npx -p @mermaid-js/mermaid-cli mmdc -i docs/03-architecture.mmd -o assets/architecture.png

The pipeline: ingest (Torx / FastF1 → lap features) → analysis (zone detection, feature engineering) → forecasting (Granite TTM-R2, **optional**) → reasoning (Granite 4.x Instruct) → grounding (Docling over FIA regs, retrieval via Granite Embedding) → guardian (Granite Guardian BYOC scoring) → fan-mode translation. Langflow is the design/demo layer; FastAPI (`api/`) is the production runtime.

**Runtime split.** Granite Instruct, Guardian, and Embedding all run on **IBM watsonx.ai** (US-South); only TTM-R2 and Docling run locally. See `docs/adrs/ADR-001-watsonx-runtime.md`.

## Non-negotiable guardrails

- **Decision support, never replacement.** Use "supports / explains / highlights / recommends" — never "decides / autonomously / optimal."
- **Pipeline must run end-to-end without TTM.** TTM enhances; it doesn't gate.
- **Don't hardcode FIA regulation article numbers in user-facing text.** Render citations dynamically from the Docling extraction.
- **All visuals original.** No F1 broadcast footage, paddock photography, or team livery.
- **"Strategy exploration," not "optimal predictor."** Don't overclaim.

## Behavioral defaults

- Plans go in `docs/plans/`. Delete the plan file in the same PR that ships the feature.
- ADRs in `docs/adrs/` are cumulative — edit the existing ADR rather than appending "but actually."
- Keep `docs/03-architecture.md` and `docs/03-architecture.mmd` in sync with code/folder changes.
- Secrets only in `.env` (gitignored). Never commit.
- `main` is stable/demoable only; `dev` is the daily branch.
