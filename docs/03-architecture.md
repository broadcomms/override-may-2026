# Architecture

## Architecture Diagram (Mermaid)
See [`docs/03-architecture.mmd`](../docs/03-architecture.mmd) for the Mermaid diagram.
```sh
# Generate the architecture diagram using mairmaid
# #TODO: wire this into pre-commit hook so it updates on every edit.
 npx -p @mermaid-js/mermaid-cli mmdc -i docs/03-architecture.mmd -o assets/architecture.png
```
![Architecture](../assets/architecture.png)

**Legend:**
- Optional/dashed: TTM forecaster (graceful degradation).
- Green: deterministic Pass 1 validator (always passes before AI scoring).
- Blue (dark): Granite components.
- Blue (light): Docling.
- Orange: UI surfaces.

## Repo Folder structure
```
override-may-2026/
├── README.md                      # The judge entry point — see §3
├── LICENSE                        # Apache 2.0 (matches Granite licensing)
├── CODE_OF_CONDUCT.md
├── .gitignore
├── requirements.txt               # Pinned versions
├── models.json                    # Granite/Guardian/TTM model versions + hashes
├── docker-compose.yml             # One-command setup
├── Dockerfile
│
├── assets/
│   ├── banner.png                 # 1920×600 BeMyApp banner
│   ├── banner.svg
│   ├── logo.png                   # 512×512
│   ├── logo.svg
│   ├── architecture.png           # Rendered from Mermaid §4
│   ├── demo.gif                   # ≤8s, ≤6MB, looped
│   └── screenshots/
│       ├── engineer-mode.png
│       ├── fan-mode.png
│       ├── reasoning-card.png
│       ├── guardian-rejection.png
│       ├── langflow-canvas.png
│       └── jaeger-trace.png
│
├── data/
│   ├── samples/                   # 3–5 small Torx replay JSONs for demo
│   ├── regs/                      # FIA public PDFs — fetched via scripts/, not committed
│   │                              # canonical document selected at G-4 verification gate
│   └── README.md                  # Data sources + licensing note
│
├── scripts/
│   └── download_regulations.py    # fetch FIA public PDFs locally
│
├── ingest/
│   ├── __init__.py
│   ├── torx_parser.py             # Torx simulator log → lap features
│   ├── fastf1_parser.py           # FastF1 session → lap features
│   └── schema.py                  # Pydantic cross-cutting schemas
│
├── analysis/
│   ├── __init__.py
│   ├── zone_detector.py           # Pure-Python heuristics
│   └── feature_engineering.py
│
├── core/
│   ├── __init__.py
│   ├── pipeline.py                # End-to-end orchestrator (P2.7)
│   ├── reasoning.py               # Granite 4.x Instruct
│   ├── fan_mode.py                # Plain-language translator
│   ├── regs.py                    # Docling reg retrieval
│   ├── guardian.py                # Granite Guardian BYOC scorer
│   ├── forecasting.py             # TTM-R2 wrapper
│   ├── validator.py               # Pass-1 deterministic checks
│   └── validator.yaml             # Pass-1 rule set
│
├── api/                           # FastAPI production runtime (see docs/04-api.md)
│   ├── main.py
│   └── routes/
│
├── prompts/
│   ├── reasoning.system.md
│   ├── fan_mode.system.md
│   └── grounding.system.md
│
├── guardian/
│   └── byoc_criteria.yaml         # Pass-2 BYOC criteria
│
├── langflow/
│   └── override.flow.json         # Exported Langflow canvas
│
├── ui/                            # Next.js or Vite app
│   ├── app/
│   ├── components/
│   ├── public/
│   └── package.json
│
├── tests/
│   ├── test_ingest.py
│   ├── test_zone_detector.py
│   ├── test_reasoning.py
│   ├── test_validator.py
│   └── fixtures/
│
├── docs/                          # numbered scheme, all sections cross-referenced
│   ├── 00-thesis.md
│   ├── 00-abstract.md
│   ├── 00-abstract-00-f1-rule-change.md
│   ├── 00-ibm-skillsbuild-challage-may-2026.md
│   ├── 01-resources-link.md
│   ├── 02-problem-and-solution.md
│   ├── 02-project-description.md
│   ├── 02-ai-and-technical-approach.md
│   ├── 02-why-solution-matters-to-context-of-racing.md
│   ├── 03-architecture.md         # this file
│   ├── 03-architecture.mmd        # Mermaid source
│   ├── 03-prd.md
│   ├── 04-schema.md               # data contracts
│   ├── 04-api.md                  # HTTP API
│   ├── 04-ui-ux-design.md         # UI / UX spec
│   ├── 04-langflow-canvas.md      # orchestration spec (design-only, not runtime)
│   ├── 05-risk-register.md
│   ├── 05-security.md
│   ├── 06-roadmap.md
│   ├── 06-testing.md
│   ├── 07-deployment.md
│   ├── adrs/                      # ADRs accumulate here as decisions get made
│   ├── plans/                     # per-feature plans, deleted on ship
│   └── user/                      # CHANGELOG, end-user documentation
│
└── .github/
    └── workflows/
        └── ci.yml                  # Basic lint + tests
```
### Branch strategy
- `main` — only stable, demoable code.
- `dev` — daily working branch.
- Tag `v0.0.1` for first prototype.
- Tag `v0.1.0` when core features are complete.
- Tag `v1.0.0` when ready for production.