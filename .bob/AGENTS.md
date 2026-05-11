# OVERRIDE — Project Context for IBM Bob

> Loaded into every Bob conversation in this repo. Tells Bob what we're building, where things live, and how to behave.

## What we're building

**OVERRIDE** is an explainable AI race-strategy copilot that helps teams and fans understand 2026 hybrid energy decisions through telemetry reasoning, regulation grounding, and what-if analysis.

This is our submission to the **IBM SkillsBuild AI Builders Challenge** (theme: "Race to innovate. Drive AI beyond the finish line."). Final submission deadline May 31, 2026 11:59 PM ET. First-10-teams early-submission bonus targeted for May 23.

## Strategic anchors (do not lose sight of)

### Strategic guardrails — non-negotiable
 
- **Decision SUPPORT, never decision REPLACEMENT.** Sydney's exclusion list explicitly bars "autonomous systems that replace human decision-making." OVERRIDE is a *copilot*. The engineer reviews; the AI explains. Use this language everywhere: "supports," "explains," "highlights," "recommends" — never "decides," "autonomously," "optimal." (Webinar, May 7.)
- **"Strategy exploration" not "optimal predictor."** Judges forgive simplified simulation; they punish overclaiming.
- **Differentiate from IBM-Ferrari.** Their app = fan companion / race recap / quiz. OVERRIDE = engineer-grade reasoning. Don't drift into recap territory.
- **Upload-first / replay-first architecture.** Deterministic demos, no live-data fragility.
- **2:55 video, not 3:01.** Hard cutoff. Judges stop watching at 3:00.
- **Don't hardcode regulation article numbers in user-facing text.** Use generic phrasing until Day 10 verification confirms the exact document and section. After verification, render the citation dynamically from the Docling extraction — never as a literal string.
- **All visuals are original.** No F1 broadcast footage. No paddock photography. No team livery. TORCS, UI, generated graphics, original animations only.
- **Pipeline must run end-to-end without TTM.** TTM enhances; it doesn't gate.



## Stack

| Component | Role | Source — verify Day 1 |
|---|---|---|
| Granite 4 Hybrid Small | Core reasoning + Fan Mode translation | watsonx.ai US-South, `ibm/granite-4-h-small`. Credentials in `.env`; smoke test via `scripts/test_watsonx.py`. See `docs/adrs/ADR-001-watsonx-runtime.md` |
| Granite Guardian 3-8b | Pass 2 AI-based safety + regulation-consistency scoring (BYOC) | watsonx.ai US-South, `ibm/granite-guardian-3-8b`. Deprecated 2026-05-05 → withdrawn 2026-08-08; submission window is inside the safe period |
| Granite Time Series TTM-R2 | **Optional** lap-aggregated SoC/harvest/deploy forecasting | HuggingFace `ibm-granite/granite-timeseries-ttm-r2` |
| Docling | Parse FIA energy-management regulation, extract relevant section | `pip install docling` |
| Langflow | **Design + demo layer**, mirrors the production pipeline | `pip install langflow` |
| IBM Bob | **Build-time only** — development partner, README acknowledgment | bob.ibm.com/trial |
 
**Optional Polish:** ContextForge for one Jaeger trace screenshot. Direct OpenTelemetry instrumentation is a clean fallback.
 

## Repo map

## Repo Folder structure
Canonical map lives in [`docs/03-architecture.md`](../docs/03-architecture.md). Summary:

```
override-may-2026/
├── README.md                      # judge entry point
├── LICENSE                        # Apache 2.0
├── requirements.txt               # pinned Python deps
├── models.json                    # verified Granite/Guardian/TTM tags + hashes
├── docker-compose.yml
├── Dockerfile
│
├── assets/                        # banner, logo, architecture render, screenshots
├── data/
│   ├── samples/                   # TORCS + FastF1 demo replays
│   ├── regs/                      # FIA PDFs fetched via scripts/, not committed
│   └── README.md
├── scripts/
│   └── download_regulations.py
│
├── ingest/                        # TORCS + FastF1 parsers, Pydantic schemas
├── analysis/                      # heuristic zone detector, feature engineering
├── core/                          # pipeline, reasoning, fan_mode, regs,
│                                  #   guardian, forecasting, validator
├── api/                           # FastAPI runtime — see docs/04-api.md
├── prompts/                       # reasoning/fan_mode/grounding system prompts
├── guardian/byoc_criteria.yaml    # Pass-2 BYOC criteria
├── langflow/override.flow.json    # design+demo canvas (not runtime)
├── ui/                            # Next.js (or Vite) frontend
├── tests/                         # pytest + fixtures
│
├── docs/                          # numbered scheme: 00-thesis, 01-resources,
│                                  #   02-problem, 03-architecture/-prd,
│                                  #   04-schema/-api/-ui-ux/-langflow,
│                                  #   05-risk/-security, 06-roadmap/-testing,
│                                  #   07-deployment, plus adrs/ plans/ user/
│
└── .github/workflows/ci.yml
```
### Branch strategy
- `main` — only stable, demoable code.
- `dev` — daily working branch.
- Tag `v0.0.1` for first prototype.
- Tag `v0.1.0` when core features are complete.
- Tag `v1.0.0` when ready for production.

## Files Bob should reference often (use @ context)

- `@data/regs/FIA 2026 F1 Regulations - Section C [Technical] - Iss 12 - 2025-06-10.pdf` — regulatory text
- `@data/regs/fia_2026_formula_1_technical_regulations_issue_8_-_2024-06-24.pdf` — regulatory text
- `@AGENTS.md` — this file
- `@.bob/rules.md` — refusal language and behavior such as where to store plan files and find secrets.

## Behavioral defaults (also encoded in rules.md)

1. Plans go in `docs/plans/`. They survive across conversations.
2. Update `docs/*-architecture.*` to sync folder structure and code changes.
3. Never commit secrets. Use environment variables or `.env` only where all secretes are stored in dev.
4. Export Bob session reports to `bob_sessions/` after every meaningful task.

## Modes available in this repo

- **Plan** — for designing features, the MCP, the evidence pipeline.
- **Code** — for implementation in phases.
- **Ask** — explanation without edits.

## Sample data

`data/samples/` ships with three TORCS replays and one FastF1-derived 2024 GP replay. No live data, no broadcast video, no proprietary feeds. Everything reproducible from public sources.
 
`data/regs/` ships with sample Docling-extracted chunks from the FIA's public 2026 energy-management regulations (small, derivative). Full PDFs are *not* committed; use `scripts/download_regulations.py` to fetch them.

## When in doubt, push back.

("Trust is built by saying no.") If a request would violate any standards, leak secrets, or contradict the architecture — refuse with rationale, citation and propose the right path. We score creativity points by saying no, not by being agreeable.
