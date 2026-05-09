# Phase 1 Foundation - Implementation Plan

> Detailed execution plan for Phase 1 (~14h) of the OVERRIDE roadmap. This plan breaks down P1.1 through P1.5 into actionable steps with clear verification criteria.

---

## Current State Assessment

**What we have (post-P1.1):**
- ✅ Complete documentation (`docs/*.md`)
- ✅ Architecture defined (`docs/03-architecture.md`, `.mmd`)
- ✅ Schemas documented (`docs/04-schema.md`)
- ✅ Prompts written (`prompts/*.system.md`)
- ✅ Validation rules (`core/validator.yaml`, `guardian/byoc_criteria.yaml`)
- ✅ AGENTS.md files (root + 5 mode-specific)
- ✅ `models.json` populated; `runtime: "watsonx"`; `scripts/test_watsonx.py` smoke-passes (gate G-1 closed)
- ✅ `requirements.txt` locked (127 packages); `ibm-watsonx-ai` installed
- ✅ TTM-R2 downloaded; HuggingFace revision pinned
- ✅ `.env.example` complete (watsonx + reasoning + retry + TTM + session limits)
- ✅ `LICENSE` Apache 2.0; `.gitignore` correct
- ✅ Embedding model decided (`ibm/granite-embedding-278m-multilingual`, dim 768) — see ADR-001

**What's still missing (Phase 1 + 2 work ahead):**
- ❌ Sample data in `data/samples/` (P1.3, blocked on Torx access)
- ❌ `ingest/*.py` stubs (P1.4)
- ❌ `analysis/zone_detector.py` (P2.1)
- ❌ `Dockerfile` / `docker-compose.yml` (P3.7)
- ❌ `ui/package.json` (P3.2)

---

## Phase 1 Execution Plan

### P1.1 Setup & Onboarding (~2h) — COMPLETE

> Migration note: P1.1 originally pulled Granite via local Ollama. After 12 GB of pulls, CPU latency was prohibitive (~1 min per inference vs. our 30 s pipeline budget). Migrated to watsonx.ai 2026-05-08; rationale in `docs/adrs/ADR-001-watsonx-runtime.md`.

**Objective:** Green local environment, watsonx.ai connectivity verified, deps installed.

**Tasks:**

1. **watsonx.ai connectivity** (Gate G-1)
   - Provision watsonx.ai project (US-South region used for this build)
   - Fill `.env` from `.env.example`: `WATSONX_API_KEY`, `WATSONX_URL`, `WATSONX_PROJECT_ID`, `GRANITE_INSTRUCT`, `GRANITE_GUARDIAN`
   - If project lookup fails, run `scripts/find_watsonx_region.py` to probe all regions
   - Run: `.venv/bin/python scripts/test_watsonx.py` — must return ✓ for both Granite Instruct and Guardian
   - Pin model IDs + region + project-id-var in `models.json` (`runtime: "watsonx"`)

2. **Install Python dependencies**
   - Create venv: `/opt/homebrew/bin/python3.12 -m venv .venv`
   - Install: `.venv/bin/pip install -r requirements.txt`
   - Lock: `.venv/bin/pip freeze` (header preserved on top)
   - Smoke-test imports: `.venv/bin/python -c "import docling, fastapi, pandas, pydantic, transformers, huggingface_hub, fastf1, uvicorn, matplotlib, pyarrow, ibm_watsonx_ai"`
   - Note: Langflow is in a separate Python 3.11 venv (`.venv-langflow`) per `requirements-langflow.txt`. The langflow constraint `Python<3.12` is the reason for the split. Per `docs/04-langflow-canvas.md` it's the design + demo layer, not the runtime.

3. **Download TTM-R2** (the one model that runs locally)
   - Run: `.venv/bin/hf download ibm-granite/granite-timeseries-ttm-r2`
   - Record HuggingFace revision in `models.json` (`huggingface.granite_ttm_r2.revision`)

4. **Repository setup**
   - Verify repo public, Apache 2.0 LICENSE present
   - `.env.example` covers all required vars
   - `.gitignore` covers `.env`, `__pycache__/`, `data/regs/*.pdf`, `data/sessions/`, etc.

**Deliverables:**
- `models.json` with watsonx model IDs + TTM-R2 revision (Gate G-1)
- `requirements.txt` with pinned versions
- `requirements-langflow.txt` for the design/demo venv
- `.env.example` covering watsonx + reasoning + TTM-R2 + session limits
- `scripts/test_watsonx.py`, `scripts/find_watsonx_region.py`

**Done When:**
- [x] `models.json` has `runtime: "watsonx"` and both Granite model IDs
- [x] `scripts/test_watsonx.py` exits 0 (both models reachable)
- [x] TTM-R2 downloaded; HF revision recorded
- [x] Python deps install without errors (127 packages locked)
- [x] Repo public with Apache 2.0 license

---

### P1.2 Discord Pitch (~1h)

**Objective:** Post pitch in Discord, capture organizer feedback.

**Tasks:**

1. **Craft Pitch Message**
   - Reference existing draft in `@docs/00-abstract.md` §Discord Pitch (lines 200-219)
   - Format: Problem → Solution → Why IBM Granite → Differentiator
   - Keep under 500 words
   - Include: "Explainable AI race-strategy copilot for 2026 F1 hybrid energy decisions"

2. **Post to Discord**
   - Channel: `#may-challenge-and-lab`
   - Timestamp the post
   - Monitor for organizer replies

3. **Capture Feedback**
   - Create `docs/plans/discord-pitch-feedback.md`
   - Quote any organizer replies verbatim
   - Note any concerns or suggestions
   - Update roadmap if major pivots needed

**Deliverables:**
- Discord post timestamped
- `docs/plans/discord-pitch-feedback.md` with captured feedback

**Done When:**
- [x] Pitch posted in Discord with timestamp (2026-05-08)
- [x] Communications log captured in `docs/plans/discord-pitch-feedback.md`; access-request thread to Makenna acknowledged (queue delay only). GitHub-invite follow-up scheduled for May 11 — see `docs/plans/quick-follow-up-on-github-invite.md`.

---

### P1.3 Torx Lab + Telemetry Mapping (~4h)

**Objective:** Run Torx baseline, understand telemetry schema, decide SoC derivation strategy.

**Tasks:**

1. **Run Torx Baseline**
   - Access IBM Torx Learning Lab
   - Run baseline AI driver on a simple track
   - Export session logs (JSON format)
   - Save to `data/samples/torx-baseline-run-1.json`
   - Complete `results.md` in project root (required for submission eligibility)

2. **Analyze Torx Telemetry Schema**
   - Inspect exported JSON structure
   - Document available fields:
     - Speed, throttle, brake, position, lap_time
     - Fuel/energy proxies
     - **Critical:** Does Torx expose battery SoC directly?
   - Create `docs/plans/torx-telemetry-map.md`
   - **Note:** FastF1 data is pre-2026, so 2026-specific features (Override Mode, super-clipping, X-Mode/Z-Mode) don't exist in source. FastF1-derived `override_uses`, `boost_uses` will be 0/approximated. Parser exists to demo pipeline against open historical data, not argue real 2026 strategy.

3. **SoC Derivation Decision (Gate G-2)**
   - **If Torx exposes SoC directly:** Use it, set `soc_source: "measured"`
   - **If Torx doesn't expose SoC:** Derive from throttle/brake integrals
     - Document derivation formula in `docs/plans/torx-telemetry-map.md`
     - Set `soc_source: "derived"` in schema
     - Add code comments explaining derivation
   - **Gate G-2 passes when:** Decision documented and derivation (if needed) is specified

4. **Collect Additional Samples**
   - Run 2-3 more Torx sessions with different strategies
   - Save to `data/samples/torx-*.json`
   - Aim for variety: aggressive deploy, conservative harvest, mixed

**Deliverables:**
- `data/samples/torx-baseline-run-1.json` (and 2-3 more samples)
- `results.md` completed
- `docs/plans/torx-telemetry-map.md` with SoC decision (Gate G-2)

**Done When:**
- [ ] Baseline Torx run produces logs
- [ ] Confirmed which fields Torx exposes
- [ ] SoC source decision recorded in `docs/plans/torx-telemetry-map.md`
- [ ] Gate G-2 passes: derivation documented if synthetic
- [ ] 3-4 sample Torx sessions saved to `data/samples/`

---

### P1.4 Data Ingestion Layer (~5h)

**Objective:** Implement parsers that convert Torx/FastF1 to canonical `LapFeatures` schema.

**Tasks:**

1. **Implement `ingest/schema.py`**
   - Create Pydantic models from `docs/04-schema.md` §3:
     - `LapFeatures` (all fields per schema)
     - `LapWindow`
   - Add validation rules (lap_number >= 1, SoC in [0,1], etc.)
   - Include `soc_source: Literal["measured", "derived"]`

2. **Implement `ingest/torx_parser.py`**
   - Function: `parse_torx_session(json_path: str) -> list[LapFeatures]`
   - Read Torx JSON
   - Extract per-lap data
   - Apply SoC derivation if needed (per G-2 decision)
   - Return list of `LapFeatures` sorted by `lap_number` ascending
   - Handle errors gracefully (invalid JSON, missing fields)

3. **Implement `ingest/fastf1_parser.py`**
   - Function: `parse_fastf1_session(year: int, gp: str, session_type: str) -> list[LapFeatures]`
   - Use FastF1 library: `fastf1.get_session(year, gp, session_type)` (e.g., `2024, 'Monza', 'R'`)
   - Derive energy state from telemetry (throttle/brake)
   - Set `soc_source: "derived"` (FastF1 doesn't expose battery directly)
   - Return same `LapFeatures` schema
   - Document derivation in code comments
   - **Note:** Pre-2026 data means `override_uses`, `boost_uses` will be 0/approximated

4. **Create Test Fixtures**
   - `tests/fixtures/torx-sample.json` (minimal valid Torx session)
   - `tests/fixtures/fastf1-sample.json` (minimal valid FastF1 export)

5. **Write Unit Tests**
   - `tests/test_ingest.py`:
     - Test Torx parser on real sample
     - Test FastF1 parser on real sample
     - Test schema validation (invalid lap_number, SoC out of bounds)
     - Test error handling (malformed JSON)
   - Run: `pytest tests/test_ingest.py -v`

**Deliverables:**
- `ingest/schema.py` with Pydantic models
- `ingest/torx_parser.py` with parser function
- `ingest/fastf1_parser.py` with parser function
- `tests/test_ingest.py` with passing tests
- Test fixtures in `tests/fixtures/`

**Done When:**
- [ ] `torx_parser.py` reads Torx JSON and returns `list[LapFeatures]` with canonical schema (blocked on Torx access)
- [x] `fastf1_parser.py` reads FastF1 session and returns `list[LapFeatures]` with same schema
- [x] FastF1 parser tested via synthetic LapInputs fixtures (real-network test deferred until cache pre-warmed)
- [x] All tests in `tests/test_ingest.py` pass — 36/36 green
- [x] SoC derivation documented in code comments + `ingest/fastf1_parser.py` module docstring
- [x] Pydantic validation constraints added: `Field(ge=1)` for `lap_number`, `Field(ge=0, le=1)` for SoC, `Field(gt=0)` for times, `Field(ge=0)` for energies/counts

---

### P1.5 Exploratory Analysis (~2h)

**Objective:** Understand data patterns, identify 4 inefficient-zone patterns for detector.

**Tasks:**

1. **Create Analysis Script**
   - `analysis/explore.py` or Jupyter notebook
   - Load parsed Torx samples using `ingest/torx_parser.py`
   - Generate exploratory plots

2. **Generate Three Key Plots**
   - **Plot 1:** SoC trajectory over laps
     - X-axis: lap_number, Y-axis: soc_start/soc_end
     - Identify depletion patterns
   - **Plot 2:** Harvest distribution by sector
     - Bar chart: harvest_mj per sector (1, 2, 3)
     - Identify low-recovery zones
   - **Plot 3:** Lap time vs deploy correlation
     - Scatter: deploy_mj vs lap_time
     - Identify low-ROI deploy moments

3. **Identify Inefficient-Zone Patterns**
   - Document **4 patterns** in `docs/plans/zone-patterns.md`:
     1. **Low-ROI deploy:** Battery used in slow corners (low time gain per MJ)
     2. **Late-recharge:** Harvest opportunity used too late or in low-recovery window
     3. **Over-harvest:** Lap harvest approaches cap with no strategic need
     4. **Unused-override:** Close-following window where Override Mode could have been triggered but wasn't
   - For each pattern, specify:
     - Detection heuristic (e.g., `deploy_mj > threshold AND corner_speed < threshold`)
     - Severity thresholds (low/medium/high)
     - Required metrics for `Zone` object

4. **Save Plots**
   - Export plots to `assets/screenshots/` (portfolio assets, not throwaway)
   - Add `analysis/exploratory-plots/` to `.gitignore` if using for scratch work
   - Include plot references in `docs/plans/zone-patterns.md`

**Deliverables:**
- `analysis/explore.py` (or notebook)
- Three exploratory plots saved
- `docs/plans/zone-patterns.md` with 4 identified patterns

**Done When:**
- [ ] Plotted: SoC over lap, harvest distribution by sector, lap-time vs deploy correlation (deferred — not gating downstream work; produce on demand from FastF1 fixture)
- [x] Identified **4 inefficient-zone patterns** (low-roi-deploy, late-recharge, over-harvest, unused-override)
- [x] Patterns documented in `docs/plans/zone-patterns.md` with detection heuristics, severity thresholds, schema-required metrics keys, and FastF1-data caveats; calibration plan recorded for the post-G-2 sweep

---

## Phase 1 Completion Criteria

Phase 1 is complete when:

1. ✅ **Gate G-1 passed:** `models.json` contains verified Granite tags
2. ✅ **Gate G-2 passed:** SoC derivation strategy documented
3. ✅ All dependencies installed and verified
4. ✅ Torx baseline run completed, `results.md` submitted
5. ✅ 3-4 Torx sample sessions in `data/samples/`
6. ✅ Ingestion parsers implemented and tested
7. ✅ 4 zone patterns identified and documented
8. ✅ All Phase 1 tests passing

**Next Phase:** Phase 2 - Core AI Pipeline (~28h)

---

## Risk Mitigation

**R1 (SoC derivation):** Addressed by Gate G-2 - decision documented before implementation
**R16 (Model tags):** Addressed by Gate G-1 - tags verified before any reasoning code
**R10 (Positioning):** Addressed by P1.2 - early Discord pitch for feedback

---

## Notes

- Plans live in `docs/plans/` and are deleted when feature ships
- Use `@docs/plans/phase-1-foundation-implementation.md` in Code mode
- Update this plan if reality diverges from estimates
- Phase 1 is foundation - no AI reasoning yet, just data pipeline