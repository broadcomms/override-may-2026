# OVERRIDE — Implementation Roadmap

> Hour-budgeted, incremental work plan. Calendar dates are **external anchors only** (challenge events, submission deadline). Internal work is sized in hours of focused effort and ordered by phase + dependency, not by day.

---

## 0. External anchors (fixed dates, do not move)

| Date | Event | Action |
|---|---|---|
| Thu May 7, 2026 | Challenge kickoff (already attended) | Roadmap start |
| Fri May 8, 2026 — 9:30 AM ET | BeMyApp team-formation webinar | Attend, recon competition |
| Mon May 11, 2026 — 10:00 AM ET | IBM Tech Talk | Attend, capture judge taste signals |
| Fri May 23, 2026 — TBD | First-10-teams early-submission bonus deadline | **Soft target** for full submission |
| Sun May 31, 2026 — 11:59 PM ET | Final submission deadline | **Hard lock** at 11:00 PM ET (1h buffer) |

Everything else is hours of work, scheduled at the operator's discretion. Total effort budget: **~90 focused hours** across five phases.

---

## 1. How to read this document

Each work unit has the form:

```
P<phase>.<n>  <title>                                         (~Xh)
  Deliverable : <file or artifact>
  Done when   : <verifiable criterion>
  Depends on  : <prior unit IDs>
  Notes       : <optional caveats>
```

A unit is "in progress" once started and "done" only when its Done-when criterion passes. Verification gates are **hard stops** — work below the gate cannot proceed until the gate passes. Phase gates allow scope cuts when reality diverges from plan.

---

## 2. Effort summary

| Phase | Focus | Effort |
|---|---|---|
| 1. Foundation | Setup, ingestion, exploratory data | ~14h |
| 2. Core AI Pipeline | Heuristics, TTM, reasoning, grounding, safety, glue | ~28h |
| 3. Orchestration + UI | Langflow, Engineer Mode, Fan Mode, polish, QA | ~30h |
| 4. Submission Assets | Design, video, BeMyApp portal | ~14h |
| 5. Final Lock | Polish + lock | ~4h |
| **Total** | | **~90h** |

---

## 3. Phase 1 — Foundation (~14h)

Goal: every dependency installed, repo initialized, telemetry schema understood, ingestion working on real TORCS output.

### P1.1 Setup & onboarding (~2h)
- **Deliverable**: green local environment, public repo, `models.json` populated, watsonx.ai connectivity verified.
- **Done when**:
  - watsonx.ai project + API key configured in `.env`; `WATSONX_URL`, `WATSONX_PROJECT_ID`, `WATSONX_API_KEY`, and Granite model IDs all set.
  - `scripts/test_watsonx.py` returns `✓ watsonx.ai smoke test passed for all configured models` — both `ibm/granite-4-h-small` and `ibm/granite-guardian-3-8b` reachable.
  - Granite model IDs + watsonx region + project-id-var pinned in `models.json` (`runtime: "watsonx"`).
  - `hf download ibm-granite/granite-timeseries-ttm-r2` completes (TTM-R2 stays local; revision SHA recorded in `models.json`).
  - Python deps installed in `.venv` (Python 3.12) and locked: `docling fastf1 huggingface_hub[cli] transformers fastapi uvicorn python-multipart pandas pydantic ibm-watsonx-ai`. Langflow lives in a separate dependency set (`requirements-langflow.txt`) — usable via the host venv path or via `podman-compose up override langflow` against `Dockerfile.langflow`.
  - Repo `<username>-override-may-2026` exists, public, Apache 2.0.
- **Verification gate G-1**: `models.json` has `runtime: "watsonx"` with both Granite model IDs and TTM-R2 revision. `scripts/test_watsonx.py` exit code 0. Until then, no reasoning code is written. Triggers risk R16. See `docs/adrs/ADR-001-watsonx-runtime.md` for why we moved off local Ollama.

### P1.2 Discord pitch (~1h)
- **Deliverable**: pitch posted in `#may-challenge-and-lab`, organizer reactions captured verbatim.
- **Done when**: post timestamped, any organizer reply quoted in `docs/plans/discord-pitch-feedback.md`.
- **Notes**: do this early — it gives the longest window to course-correct (risk R10).

### P1.3 TORCS lab + telemetry mapping (~4h)
- **Deliverable**: TORCS baseline AI driver run + completed `results.md` (required for submission eligibility per webinar) + telemetry-mapping note in `docs/plans/torcs-telemetry-map.md`.
- **Done when**:
  - Baseline TORCS run produces logs.
  - Confirmed which fields TORCS exposes: speed, throttle, brake, position, lap_time, fuel/energy proxies.
  - Decision recorded: does TORCS expose battery SoC directly, or do we derive it from throttle/brake integral?
- **Verification gate G-2 (risk R1 decision)**: SoC source is decided and the derivation, if synthetic, is documented in code comments and in the mapping note.

### P1.4 Data ingestion layer (~5h)
- **Deliverable**: `ingest/torcs_parser.py`, `ingest/fastf1_parser.py`, `ingest/schema.py`.
- **Done when**:
  - `torcs_parser.py` reads a TORCS JSON log and returns `list[LapFeatures]` with the canonical schema below.
  - `fastf1_parser.py` reads a FastF1 session and returns the same `list[LapFeatures]` schema (energy state derived from telemetry).
  - Both parsers tested against at least one real input each.
- **Canonical lap-feature schema** (Pydantic in `ingest/schema.py`):
  ```
  lap_number, soc_start, soc_end, harvest_mj, deploy_mj,
  lap_time, sector1_time, sector2_time, sector3_time,
  avg_speed, max_speed, override_uses, boost_uses, recharge_zones
  ```
- **Depends on**: P1.3.

### P1.5 Exploratory analysis (~2h)
- **Deliverable**: notebook or `analysis/explore.py` producing three exploratory plots.
- **Done when**:
  - Plotted: SoC over lap, harvest distribution by sector, lap-time vs deploy correlation.
  - Identified **4 inefficient-zone patterns** to detect later (low-roi-deploy, late-recharge, over-harvest, unused-override). Patterns documented in `docs/plans/zone-patterns.md`.
- **Depends on**: P1.4.

---

## 4. Phase 2 — Core AI Pipeline (~28h)

Goal: end-to-end deterministic pipeline from session upload → reasoning JSON output, with regulation grounding and two-pass safety.

### P2.1 Heuristic zone detector (~4h)
- **Deliverable**: `analysis/zone_detector.py`, `analysis/feature_engineering.py`.
- **Done when**:
  - Implements the four patterns from P1.5 in pure Python (no AI).
  - Returns a list of `Zone` objects with `type`, `lap_number`, `severity`, supporting metrics.
  - Unit-tested in `tests/test_zone_detector.py` with at least one fixture per pattern.
- **Notes**: this is the baseline the rest of the pipeline rests on. Granite reasons over these zones; it does not replace them.
- **Depends on**: P1.4, P1.5.

### P2.2 TTM-R2 forecasting (~5h, optional enhancement) ✅ COMPLETED 2026-05-21
- **Deliverable**: `core/forecasting.py`, `Dockerfile.ttm`, `ttm_service.py`, HTTP client wrapper.
- **Done when**:
  - ✅ Loads `ibm-granite/granite-timeseries-ttm-r2` via `tsfm_public`.
  - ✅ Inputs: 30-lap context window, 5 channels (SoC, harvest, deploy, lap_time, avg_speed).
  - ✅ Output: 5-lap forecast horizon with prediction intervals.
  - ✅ **Graceful degradation logic**: `if lap_count < 30 OR ci_width > threshold → return None`. Pipeline never blocks on TTM.
  - ✅ Model version pinned, context/forecast lengths documented in README.
  - ✅ Deployed as Docker service per ADR-004 to resolve torch dependency conflict.
  - ⏳ Validation on held-out TORCS replay: SoC MAE pending (requires `.venv-ttm` evaluation run).
- **Verification gate G-3 (risk R2 decision)**: ✅ **ARCHITECTURE COMPLETE 2026-05-21** — Implementation finished with comprehensive test coverage (12 functions, 425 lines). Deployed as separate Docker service (`podman-compose up override ttm`) per ADR-004. MAE evaluation pending in `.venv-ttm` environment; graceful degradation ensures pipeline runs end-to-end regardless of forecast availability. See `docs/adrs/ADR-004-ttm-deployment.md`.
- **Depends on**: P1.4.

### P2.3 Granite reasoning integration (~4h)
- **Deliverable**: `core/reasoning.py`.
- **Done when**:
  - Calls Granite Instruct via watsonx.ai chat API using `prompts/reasoning.system.md`.
  - Inputs: zone + lap context + (optional) TTM forecast + retrieved regulation snippet (placeholder until G-4).
  - Output: structured JSON matching the reasoning prompt's schema (`cause`, `consequence`, `recommendation`, `regulation_citation`, `confidence`, `reasoning_chain`).
  - Tested on 3–5 TORCS zone examples; outputs eyeballed for correctness.
- **Depends on**: P2.1, P1.1.

### P2.4 Reasoning refinement (~4h)
- **Deliverable**: refined `prompts/reasoning.system.md`, `tests/eval_reasoning.py` evaluation harness.
- **Done when**:
  - Chain-of-thought scaffolding added.
  - Regulation citation forced in every output where a passage exists.
  - Temperature controls separated: low for reasoning, slightly higher for Fan Mode prose.
  - Eval harness: 10 known scenarios × 3 reasoning attempts each, manually scored on accuracy + clarity. Score baseline recorded.
- **Depends on**: P2.3.

### P2.5 Docling + regulation verification gate (~5h) ✅ G-4 closed 2026-05-08
- **Deliverable**: `scripts/download_regulations.py`, `scripts/build_chunks.py`, `core/regs.py`, `data/regs/extracted_chunks.sample.json`, `docs/regulation-source.md`.
- **Verification gate G-4 (risk R13/R14) — closed 2026-05-08**:
  1. ✅ Document identified: **FIA 2026 Formula 1 Technical Regulations — Section C, Issue 12, 10 June 2025**.
  2. ✅ Article in scope: **Article C5 (Power Unit)**, with subsections C5.2, C5.2.14, C5.17, C5.18, C5.19, C5.20.
  3. ✅ Recorded in `docs/regulation-source.md`. Sporting Regulations are out of scope until a separate G-4-equivalent verification (tracked as `unused-override` open item).
- **Done when** (all ✅):
  - `docs/regulation-source.md` records document + article + section subscope.
  - `scripts/download_regulations.py` fetches the public PDF (PDFs gitignored; large Docling-extracted MD files also gitignored — only `extracted_chunks.sample.json` is committed).
  - `scripts/build_chunks.py` runs Docling (PyPdfium backend, OCR off, table-structure off, `\bC5\b` section filter) → 48 chunks → watsonx embedding pass (Granite Embedding 278M, 768-dim).
  - `data/regs/extracted_chunks.sample.json` committed with `g4_status: "closed"`.
  - `core/regs.py` performs keyword + embedding-based retrieval over the chunks. Score = 0.6 cosine + 0.4 keyword overlap; threshold 0.4.
  - Section labels (`C5.17`, `C5.18`, etc.) are extracted from the Docling text at runtime — never hardcoded in code, prompts, or schema defaults.
- **Depends on**: P2.3.

### P2.6 Two-pass safety architecture (~4h)
- **Deliverable**: `core/validator.py`, `core/guardian.py`.
- **Done when**:
  - **Pass 1 (deterministic)** implements the rule set in `core/validator.yaml`:
    - Energy bounds (SoC stays in [0, max]).
    - Harvest cap (≤ verified value MJ/lap from G-4).
    - Citation existence (passage findable verbatim in retrieved chunks).
    - Language safety (no "you must," "optimal," "always," "definitely will").
    - Source consistency (citation source matches a chunk source).
    - On fail → regenerate with stricter prompt, max 2 retries.
  - **Pass 2 (Granite Guardian BYOC)** uses `guardian/byoc_criteria.yaml`:
    - Two custom criteria: `energy_safety`, `regulation_consistency`.
    - Pass threshold: both ≥ 0.70.
    - On fail → regenerate with explicit citation requirement, max 2 retries.
    - After 2 failures: ship with "low confidence" badge; never block silently.
  - UI badges: "Validation: ✓ passed" green + "AI Safety Review: 0.84 / 1.00" score, both visible.
  - Guardian threshold calibrated against 20 sample outputs.
- **Verification gate G-5 (risk R4 decision)**: if Guardian rejects more than ~50% of well-formed outputs, threshold is loosened to 0.65 or rubric language is softened. Pass 1 must remain functional regardless.
- **Depends on**: P2.4, P2.5.

### P2.7 End-to-end pipeline glue (~2h)
- **Deliverable**: `core/pipeline.py` orchestrating: ingest → forecast (optional) → detect → ground → reason → validate → guardian → JSON output.
- **Done when**:
  - Runs successfully on **5 different TORCS replays + 2 FastF1 replays**.
  - Output is deterministic across runs on the same input (with temperature pinned).
- **Phase gate Φ-1 (risk R5 decision)**: if pipeline is not producing clean output by end of P2.7, **cut scope**:
  - Drop Fan Mode UI; keep Engineer Mode only.
  - Fan Mode becomes a single example card in the demo video.
- **Depends on**: P2.6.

---

## 5. Phase 3 — Orchestration + UI (~30h)

Goal: visible product. Langflow canvas + working Engineer Mode UI + Fan Mode UI + captured assets.

### P3.1 Langflow canvas (~4h)
- **Deliverable**: `langflow/override.flow.json`, exported PNG at 2× DPI.
- **Done when**:
  - 11 nodes laid out per `docs/04-langflow-canvas.md`:
    Upload → Ingest → Zone Detector → (TTM optional) → Granite Reasoning ← Docling Reg Retriever; Reasoning → Pass 1 Validator → Pass 2 Guardian → Mode Router → (Engineer | Fan Translator) → UI Output.
  - Subgraph groupings applied per the visual styling spec.
  - Loops wired: validator-fail → regenerate, guardian-fail → regenerate.
  - Canvas executes a simplified end-to-end sample flow once for the demo recording.
  - Clean 2× DPI screenshot saved for README + video.
- **Notes**: README and video both call out: *"Langflow used for orchestration design and demonstration; FastAPI used for production runtime."* Avoid implying Langflow is the runtime path.
- **Depends on**: P2.7.

### P3.2 Engineer Mode UI framework (~6h)
- **Deliverable**: `ui/` Next.js (or Vite + React) app skeleton.
- **Done when**:
  - Stack: Next.js 14 + Tailwind + shadcn/ui (or Vite + React if faster).
  - Routes: `/upload`, `/session/[id]`.
  - Components scaffolded: telemetry chart (Recharts), energy curve, zone heatmap, recommendation card.
  - Aesthetic: dark motorsport palette — carbon black `#0A0A0A`, override-orange `#FF4500`, sustainable-fuel green `#00C853`, white text. JetBrains Mono for telemetry numbers, Inter for prose.
  - File upload posts to FastAPI `/api/sessions` and renders a result page.
- **Depends on**: P2.7.

### P3.3 Engineer Mode polish (~5h)
- **Deliverable**: production-quality recommendation card + energy curve + what-if toggle.
- **Done when**:
  - Recommendation card shows: zone, collapsible reasoning chain, regulation citation (highlighted, dynamic — never hardcoded article string), Pass-1 validation badge, Pass-2 Guardian score badge, confidence label.
  - Energy curve: SoC trajectory + (if TTM available) 5-lap forecast as dotted continuation. If TTM unavailable: gentle "forecast unavailable" empty state, no error.
  - "What-if" toggle: replay with one parameter changed (e.g., delay first deploy by 1 lap). Re-renders updated forecast and reasoning.
- **Depends on**: P3.2.

### P3.4 Fan Mode UI (~5h, conditional on Φ-1)
- **Deliverable**: Fan Mode rendering of the same backend pipeline.
- **Done when**:
  - Same backend pipeline; different rendering layer.
  - Plain-language wrapper using `prompts/fan_mode.system.md`.
  - Acronyms hidden (MGU-K → "energy recovery system"). Raw kJ numbers replaced with bars/icons.
  - "Why this mattered" summary card per zone.
  - Mode toggle in header: single click switches Engineer ↔ Fan.
- **Notes**: skipped entirely if phase gate Φ-1 cut scope.
- **Depends on**: P3.3.

### P3.5 UI polish + asset capture (~4h)
- **Deliverable**: clean UI + screenshots in `assets/screenshots/`.
- **Done when**:
  - Visual hierarchy tight, panel count minimized, whitespace breathing.
  - Empty states, loading skeletons, error boundaries in place.
  - Screenshots captured at 2× DPI:
    - Dashboard
    - Engineer Mode reasoning card
    - Fan Mode summary (or example-card surrogate if Φ-1 cut)
    - Validator + Guardian badges
    - Langflow canvas
    - Docling-extracted reg passage
- **Depends on**: P3.3 (and P3.4 if not cut).

### P3.6 Observability decision (~3h)
- **Deliverable**: one Jaeger or OpenTelemetry trace screenshot for the README.
- **Done when**:
  - **Decision point (risk R6)**: is the project on track to ship within the next ~20h?
    - **Yes** → wire ContextForge as MCP gateway, capture Jaeger trace screenshot.
    - **No** → skip ContextForge entirely; instrument FastAPI directly with OpenTelemetry, capture trace screenshot.
  - Either way: trace screenshot saved to `assets/screenshots/jaeger-trace.png`.
- **Depends on**: P3.2.

### P3.7 End-to-end QA (~3h)
- **Deliverable**: `docs/plans/qa-results.md`.
- **Done when**:
  - 10 different sessions run through the deployed UI; durations recorded.
  - All pipeline bugs surfaced are fixed.
  - Tested on a clean machine (or fresh Docker container) — verify one-command setup works.
  - Verified graceful degradation: short replay (< 30 laps, TTM unavailable) → still produces useful output.
  - All model versions locked in `requirements.txt` and `models.json`.
- **Depends on**: P3.5, P3.6.

---

## 6. Phase 4 — Submission Assets (~14h)

Goal: every artifact required by the BeMyApp portal is produced, polished, and uploaded.

### P4.1 Design assets (~4h)
- **Deliverable**: banner, logo, architecture render, brand swatch.
- **Done when**:
  - Banner: 1920×600 px. Composition: dark carbon background, "OVERRIDE" wordmark in override-orange, faint energy-curve graphic, tagline. PNG + SVG.
  - Logo: square 512×512 px. Geometric "O" suggesting an energy-recovery icon. PNG + SVG.
  - Architecture diagram: rendered from `docs/03-architecture.mmd` to `assets/architecture.png` via:
    `npx -p @mermaid-js/mermaid-cli mmdc -i docs/03-architecture.mmd -o assets/architecture.png`
  - Brand-palette swatch image saved to `assets/palette.png`.

### P4.2 Video script + voiceover (~4h)
- **Deliverable**: locked script in `docs/plans/video-script.md`, recorded voiceover stems.
- **Done when**:
  - Script finalized per the `docs/00-abstract.md` shot list.
  - Read-aloud pace check: full script under **2:50** read time. If over, cut words, not screens.
  - Voiceover recorded in a quiet room (condenser mic if available, otherwise phone with hand-held technique). Target 2:55.
- **Verification gate G-6 (risk R7)**: video runtime ≤ 2:55. Hard cutoff. Cut explainability beat from 30s → 22s if needed; trim cold open second.

### P4.3 Video edit (~4h)
- **Deliverable**: final MP4 uploaded to YouTube as **unlisted**.
- **Done when**:
  - Screen recordings captured: OBS, 1920×1080 @ 60fps, mouse highlights on.
  - Edit in DaVinci Resolve or CapCut. Locked at 2:55. Captions added.
  - **All footage original**: TORCS simulator output, UI recordings, generated charts, Langflow canvas, original animations. **No F1 broadcast footage.** Royalty-free instrumental music only. (Risk R15.)
  - Exported H.264 MP4 ≤ 1080p.
  - YouTube upload: **unlisted** initially; processing complete; link verified in incognito.
- **Notes**: switch to **public** at the start of P4.4, not before — protects against YouTube processing failures on submission moment (risk R8).
- **Depends on**: P4.2.

### P4.4 Submission portal (~2h) 🎯
- **Deliverable**: BeMyApp project page published.
- **Done when**:
  - YouTube video switched to **public**. Verified in incognito.
  - GitHub repo: name `<username>-override-may-2026` (per Lucas's webinar instruction), public, README complete, `LICENSE` present (Apache 2.0). FIA PDFs **not** committed; only `extracted_chunks.sample.json` + `download_regulations.py` + `data/regs/README.md`.
  - BeMyApp project page filled:
    - Banner uploaded
    - Logo uploaded
    - Project name: OVERRIDE
    - 1–2 sentence summary (locked positioning sentence)
    - Issue + Solution sections
    - Video link
    - GitHub repo link
    - Team members
  - **PUBLISH clicked.** This is what counts as a submission per Lucas. First-10-teams bonus eligible if hit before May 23.
- **Depends on**: P3.7, P4.1, P4.3.

---

## 7. Phase 5 — Final Lock (~4h)

Goal: a calm pre-deadline polish window. No new features.

### P5.1 Polish pass (~2h)
- **Done when**:
  - README read cold, top to bottom, awkward sentences fixed.
  - Video re-watched; if any segment is wrong, only that segment re-recorded.
  - Demo stress-tested on a fresh machine.
  - Discord checked for any unresolved organizer questions.

### P5.2 Final lock (~2h)
- **Done when**:
  - All artifacts verified public and accessible from a logged-out browser.
  - Submission checklist (below) walked end to end.
  - **Lock at 11:00 PM ET on May 31** — full hour buffer before 11:59 PM deadline.
  - Walk away from the laptop.

---

## 8. Verification gates (must-pass)

| Gate | What it gates | Risk it covers |
|---|---|---|
| **G-1** | No reasoning code until watsonx.ai connectivity verified and model IDs pinned in `models.json` | R16 |
| **G-2** | No ingestion code until SoC source decided + documented | R1 |
| **G-3** | TTM stays optional unless MAE is acceptable | R2 |
| **G-4** ✅ | No reasoning ships with hardcoded reg article numbers; verified source recorded. Closed 2026-05-08 — see `docs/regulation-source.md` | R13, R14 |
| **G-5** | Pass 1 must remain functional even if Guardian threshold is loosened | R4 |
| **G-6** | Video ≤ 2:55, hard | R7 |

---

## 9. Phase gates (scope cuts)

| Gate | Trigger | Action |
|---|---|---|
| **Φ-1** (after P2.7) | Pipeline is not producing clean output | Drop Fan Mode UI; Fan Mode becomes one demo card |
| **Φ-2** (P3.6 decision) | More than ~20h remaining work after P3.6 trigger | Skip ContextForge; use direct OpenTelemetry |
| **Φ-3** (anytime in P3) | UI work running over budget | Tighten Engineer Mode panel count; defer non-essential animations |

---

## 10. Submission checklist (P5.2 walks this)

- [ ] GitHub repo public, named `<username>-override-may-2026`.
- [ ] `README.md` includes: problem, AI/technical approach, why-it-matters in racing context.
- [ ] `LICENSE` present, Apache 2.0.
- [ ] FIA PDFs **not** committed. `download_regulations.py` + `data/regs/README.md` + `extracted_chunks.sample.json` are.
- [ ] No hardcoded FIA article numbers in user-facing strings or prompts.
- [ ] All visuals original. No broadcast footage.
- [ ] Video public on YouTube, ≤ 2:55, captions, royalty-free music.
- [ ] BeMyApp page published with banner, logo, summary, issue, solution, video link, repo link, team members.
- [ ] `models.json` and `requirements.txt` lock all model + dependency versions.
- [ ] Pipeline runs end-to-end **without** TTM on a clean machine.
- [ ] Pass 1 validator + Pass 2 Guardian both visible in the UI.
- [ ] Engineer Mode + Fan Mode toggle works (or Fan Mode example card visible if Φ-1 cut).
- [ ] One trace screenshot (Jaeger or OpenTelemetry) in README architecture section.

---

## 11. Branch + tag strategy

- `main` — stable, demoable code only.
- `dev` — daily working branch.
- `v0.0.1` — first prototype tag (after P2.7).
- `v0.1.0` — core features complete (after P3.5).
- `v1.0.0` — submission cut (at P4.4).

---

## 12. Working principles

- **Plans clutter the repo.** Working notes and per-feature plans live in `docs/plans/` and are deleted in the same PR that ships the feature.
- **ADRs are cumulative.** Edit existing ADRs in `docs/adrs/` rather than appending "but actually."
- **Decision support, never replacement.** Use *supports / explains / highlights / recommends*, never *decides / autonomously / optimal*.
- **TTM enhances; it does not gate.** The pipeline must always run end-to-end without it.
- **Citations are dynamic.** Render from the Docling extraction, never as a literal string in code or prompts.
- **Originals only in user-facing media.** No F1 broadcast footage, no team livery, no paddock photography.
