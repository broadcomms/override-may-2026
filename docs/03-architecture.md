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
├── docker-compose.yml             # Four services, three profiles (torcs, observability, langflow)
├── Dockerfile                     # Multi-stage Node-20 → Python-3.12 → single image
│
├── assets/
│   ├── banner.png                 # 1920×600 BeMyApp banner
│   ├── banner.svg
│   ├── logo.png                   # 512×512
│   ├── logo.svg
│   ├── architecture.png           # Rendered from Mermaid (see top of this doc)
│   ├── demo.gif                   # ≤8s, ≤6MB, looped
│   └── screenshots/
│       ├── engineer-mode.png
│       ├── fan-mode.png
│       ├── guardian-rejection.png
│       ├── langflow-canvas.png
│       └── jaeger-trace.png
│
├── data/
│   ├── samples/                   # Real TORCS-lab captures (baseline + modified .jsonl)
│   ├── regs/                      # FIA public PDFs (Section C Issue 18, Section B Issue 06)
│   │                              # + extracted_chunks.sample.json (Docling output, committed)
│   ├── sessions/                  # Persisted Session JSONs (host-mounted in compose)
│   └── README.md                  # Data sources + licensing note
│
├── scripts/
│   ├── build_chunks.py            # Re-run Docling on a new FIA Issue
│   ├── test_watsonx.py            # G-1 connectivity gate
│   └── torcs_container_init.sh    # Compose entrypoint override for the TORCS lab image
│                                  # (absorbs Ollama chown + VS Code hang bugs from RESULTS.md)
│
├── RaceYourCode/                  # Committed unzip of gym_torcs from hands-on-labs/01_torcs_lab/
│   └── gym_torcs/                 # Lab driver source; bind-mounted into the torcs compose service
│
├── ingest/
│   ├── __init__.py
│   ├── torcs_parser.py            # TORCS JSONL → lap features (calibrated; safe-read for live tail)
│   ├── fastf1_parser.py           # FastF1 session → lap features
│   └── schema.py                  # Pydantic cross-cutting schemas (incl. WhatIfRequest/Result)
│
├── analysis/
│   ├── __init__.py
│   ├── zone_detector.py           # Pure-Python heuristics
│   ├── feature_engineering.py
│   ├── perturbations.py           # FR-8 — delay_first_deploy / skip_harvest_zone / extend_override
│   └── torcs_energy.py            # Shared 2026-hybrid bookkeeping constants + SoC math
│
├── core/
│   ├── __init__.py
│   ├── pipeline.py                # End-to-end orchestrator (run_pipeline)
│   ├── reasoning.py               # Granite 4.x Instruct via WatsonxChatClient Protocol
│   ├── fan_mode.py                # Plain-language translator (lazy, per-zone)
│   ├── regs.py                    # Docling reg retrieval + chunker
│   ├── guardian.py                # Granite Guardian BYOC scorer (Pass-2)
│   ├── forecasting.py             # TTM-R2 wrapper — STUB; v1.1 (graceful-degradation guardrail)
│   ├── validator.py               # Pass-1 deterministic checks
│   ├── validator.yaml             # Pass-1 rule set
│   └── llm_clients/
│       └── ollama.py              # OllamaChatClient — implements WatsonxChatClient Protocol
│                                  # (selected via OVERRIDE_LLM_RUNTIME=ollama)
│
├── api/                           # FastAPI production runtime (see docs/04-api.md)
│   ├── main.py                    # Endpoints: /api/sessions, /api/sessions/torcs-live,
│   │                              # /api/sessions/{id}/what-if, /api/torcs-status, /api/health
│   │                              # + StaticFiles mount serving the built UI from ui/dist
│   └── storage.py                 # Session persistence (atomic writes via tempfile + os.replace)
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
│   └── override.flow.json         # Exported Langflow canvas (design layer, not runtime)
│
├── ui/                            # React + Vite + TypeScript
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── api/                   # client.ts, types.ts (fixture-mode synthesis included)
│   │   ├── components/            # FileUpload, WhatIfDiff, etc. (WhatIfRail is inline in RecommendationCard.tsx)
│   │   ├── pages/                 # UploadPage (with live-TORCS banner), SessionPage
│   │   └── styles/
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts             # @fixtures alias → ../tests/fixtures/
│
├── tests/
│   ├── test_torcs_parser.py       # Golden + calibration-regression
│   ├── test_perturbations.py      # FR-8 unit tests
│   ├── test_llm_clients_ollama.py # Mocked HTTP layer + startup-probe behavior
│   ├── test_api.py                # Endpoint integration (incl. live-ingest + what-if)
│   ├── test_zone_detector.py
│   ├── test_validator.py
│   ├── test_guardian.py
│   ├── test_regs.py
│   ├── test_pipeline.py
│   └── fixtures/                  # Including torcs_engineer_demo.json (real-TORCS-derived)
│
└── docs/                          # numbered scheme, all sections cross-referenced
    ├── 03-architecture.md         # this file
    ├── 03-architecture.mmd        # Mermaid source
    ├── 03-prd.md
    ├── 04-{schema,api,ui-ux-design,langflow-canvas}.md
    ├── 05-{risk-register,security}.md
    ├── 06-{roadmap,testing}.md
    ├── 07-deployment.md
    ├── adrs/                      # ADR-001 watsonx runtime, ADR-002 TORCS sandbox,
    │                              # ADR-003 LLM-runtime abstraction
    ├── plans/                     # per-feature plans, deleted on ship
    └── user/                      # CHANGELOG, end-user documentation
```

CI workflows are not in v1.0 scope (see README "What's coming next"). The quality gate is `pytest -q -m "not network"` + `npm run build`, walked at the T-72h pre-flight in [`docs/plans/final-lock-checklist.md`](plans/final-lock-checklist.md).
### Branch strategy
- `main` — only stable, demoable code.
- `dev` — daily working branch.
- Tag `v0.0.1` for first prototype.
- Tag `v0.1.0` when core features are complete.
- Tag `v1.0.0` when ready for production.