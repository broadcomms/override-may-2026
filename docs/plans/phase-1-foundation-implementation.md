# Phase 1 Foundation - Implementation Plan

> Detailed execution plan for Phase 1 (~14h) of the OVERRIDE roadmap. This plan breaks down P1.1 through P1.5 into actionable steps with clear verification criteria.

---

## Current State Assessment

**What we have:**
- ✅ Complete documentation (`docs/*.md`)
- ✅ Architecture defined (`docs/03-architecture.md`, `.mmd`)
- ✅ Schemas documented (`docs/04-schema.md`)
- ✅ Prompts written (`prompts/*.system.md`)
- ✅ Validation rules (`core/validator.yaml`, `guardian/byoc_criteria.yaml`)
- ✅ Folder structure in place
- ✅ AGENTS.md files created

**What's missing (blockers for Phase 1):**
- ❌ `models.json` empty (Gate G-1 blocker)
- ❌ `requirements.txt` empty
- ❌ All Python files are stubs
- ❌ No sample data in `data/samples/`
- ❌ Docker files empty
- ❌ UI package.json empty

---

## Phase 1 Execution Plan

### P1.1 Setup & Onboarding (~2h)

**Objective:** Green local environment, verified model tags, dependencies installed.

**Tasks:**

1. **Verify Granite Model Tags** (Gate G-1 - CRITICAL)
   - Visit `github.com/ibm-granite-community` to find current Granite 4.x Instruct tags
   - Visit `github.com/ibm-granite-community` to find current Granite Guardian tags
   - Record exact tags with SHA hashes in `models.json`
   - Test: `ollama pull <verified-instruct-tag>` and `ollama run <tag> "Hello"`
   - Test: `ollama pull <verified-guardian-tag>` and `ollama run <tag> "Test"`
   - **Gate G-1 passes when:** `models.json` contains verified tags with hashes

2. **Install Python Dependencies**
   - Create `requirements.txt` with pinned versions:
     ```
     docling>=1.0.0
     langflow>=1.0.0
     fastf1>=3.0.0
     huggingface_hub>=0.20.0
     transformers>=4.36.0
     fastapi>=0.109.0
     uvicorn>=0.27.0
     pandas>=2.1.0
     pydantic>=2.5.0
     pytest>=7.4.0
     python-dotenv>=1.0.0
     ```
   - Run: `pip install -r requirements.txt`
   - Verify: `python -c "import docling, fastapi, pandas, pydantic"`

3. **Download TTM-R2 Model**
   - Run: `huggingface-cli download ibm-granite/granite-timeseries-ttm-r2`
   - Record model hash in `models.json`
   - Verify: Model files exist in HF cache

4. **Repository Setup**
   - Verify repo is public
   - Verify LICENSE is Apache 2.0
   - Create `.env.example` with required vars
   - Create `.gitignore` if missing (ignore `.env`, `*.pyc`, `__pycache__/`, `data/regs/*.pdf`)

**Deliverables:**
- `models.json` with verified tags (Gate G-1)
- `requirements.txt` with pinned versions
- `.env.example`
- All dependencies installed and verified

**Done When:**
- [ ] `models.json` is not empty and contains verified Granite tags with hashes
- [ ] `ollama run <instruct-tag> "Hello"` returns output
- [ ] `ollama run <guardian-tag> "Test"` returns output
- [ ] `huggingface-cli download ibm-granite/granite-timeseries-ttm-r2` completes
- [ ] All Python deps install without errors
- [ ] Repo is public with Apache 2.0 license

---

### P1.2 Discord Pitch (~1h)

**Objective:** Post pitch in Discord, capture organizer feedback.

**Tasks:**

1. **Craft Pitch Message**
   - Use positioning from `docs/00-thesis.md`
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
- [ ] Pitch posted in Discord with timestamp
- [ ] Any organizer replies captured in `docs/plans/discord-pitch-feedback.md`

---

### P1.3 Torx Lab + Telemetry Mapping (~4h)

**Objective:** Run Torx baseline, understand telemetry schema, decide SoC derivation strategy.

**Tasks:**

1. **Run Torx Baseline**
   - Access IBM Torx Learning Lab
   - Run baseline AI driver on a simple track
   - Export session logs (JSON format)
   - Save to `data/samples/torx-baseline-run-1.json`
   - Complete `results.md` (required for submission eligibility)

2. **Analyze Torx Telemetry Schema**
   - Inspect exported JSON structure
   - Document available fields:
     - Speed, throttle, brake, position, lap_time
     - Fuel/energy proxies
     - **Critical:** Does Torx expose battery SoC directly?
   - Create `docs/plans/torx-telemetry-map.md`

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
   - Return list of `LapFeatures` keyed on `lap_number`
   - Handle errors gracefully (invalid JSON, missing fields)

3. **Implement `ingest/fastf1_parser.py`**
   - Function: `parse_fastf1_session(session_id: str) -> list[LapFeatures]`
   - Use FastF1 library to load session
   - Derive energy state from telemetry (throttle/brake)
   - Set `soc_source: "derived"` (FastF1 doesn't expose battery directly)
   - Return same `LapFeatures` schema
   - Document derivation in code comments

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
- [ ] `torx_parser.py` reads Torx JSON and returns DataFrame with canonical schema
- [ ] `fastf1_parser.py` reads FastF1 session and returns same schema
- [ ] Both parsers tested against at least one real input each
- [ ] All tests in `tests/test_ingest.py` pass
- [ ] SoC derivation documented in code comments

---

### P1.5 Exploratory Analysis (~2h)

**Objective:** Understand data patterns, identify 3 inefficient-zone patterns for detector.

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
   - Document 3 patterns in `docs/plans/zone-patterns.md`:
     1. **Low-ROI deploy:** Battery used in slow corners (low time gain per MJ)
     2. **Late-lap recharge:** Harvest opportunity used too late or in low-recovery window
     3. **Over-harvest:** Lap harvest approaches cap with no strategic need
   - For each pattern, specify:
     - Detection heuristic (e.g., `deploy_mj > threshold AND corner_speed < threshold`)
     - Severity thresholds (low/medium/high)
     - Required metrics for `Zone` object

4. **Save Plots**
   - Export plots to `analysis/exploratory-plots/`
   - Include in `docs/plans/zone-patterns.md` as references

**Deliverables:**
- `analysis/explore.py` (or notebook)
- Three exploratory plots saved
- `docs/plans/zone-patterns.md` with 3 identified patterns

**Done When:**
- [ ] Plotted: SoC over lap, harvest distribution by sector, lap-time vs deploy correlation
- [ ] Identified 3 inefficient-zone patterns
- [ ] Patterns documented in `docs/plans/zone-patterns.md` with detection heuristics

---

## Phase 1 Completion Criteria

Phase 1 is complete when:

1. ✅ **Gate G-1 passed:** `models.json` contains verified Granite tags
2. ✅ **Gate G-2 passed:** SoC derivation strategy documented
3. ✅ All dependencies installed and verified
4. ✅ Torx baseline run completed, `results.md` submitted
5. ✅ 3-4 Torx sample sessions in `data/samples/`
6. ✅ Ingestion parsers implemented and tested
7. ✅ 3 zone patterns identified and documented
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