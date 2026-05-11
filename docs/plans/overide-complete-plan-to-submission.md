# OVERRIDE — Completion Plan to Submission

**Submission target:** May 27–28, 2026 (T-16/17d from May 11; first-10-teams bonus on May 23 abandoned in favor of clean ship). Final deadline May 31 11:59 PM ET.

**Total estimate:** ~68h baseline at the weekly-total level / ~82h with 20% slack over 18–19 days (~3.8–4.5h/day). Sub-task sums are ~63h; weekly headers carry ~11h of implicit buffer above sub-tasks; the 82h includes another 20% on top. So if Week 2 lands at 21h vs. its 29h header, that's normal — not "ahead."

## Context

OVERRIDE is feature-complete for Tier-1: the pipeline (ingest → zones → reasoning → validator → Guardian → fan-mode) runs end-to-end, 231 tests pass, the UI Engineer+Fan modes work, the Docling regulation grounding (G-4) is closed against Issue 18. What's still missing from the **original vision** are four specific items, plus several smaller gaps the audit surfaced:

**Major gaps vs vision** (per `docs/03-prd.md`, `docs/06-roadmap.md`, `.bob/AGENTS.md`):
- `ingest/torcs_parser.py` is 0 bytes — TORCS data path never closed (P1.4 incomplete). The lab now runs (`hands-on-labs/01_torcs_lab/`), so the data-source story can finally be honored.
- FR-8 what-if simulation (delay_first_deploy / skip_harvest_zone / extend_override) — required by the PRD, never implemented.
- `Dockerfile`, `docker-compose.yml` empty — `docs/07-deployment.md` treats Docker as the shipping shape.
- `.github/workflows/ci.yml` empty — never spec'd; will be deleted, not implemented.

**Smaller gaps** (from the code-completeness audit):
- Concurrency hazard in the lazy fan-mode `save_session` (`api/main.py:351-372`) — parallel zone-fan fetches race and the last writer wins.
- Five stale plan files violate the project's "delete plan in same PR that ships the feature" rule (`.bob/rules.md`).
- `SessionsPage.tsx` is an empty-state stub citing "Tier 2"; list endpoint helper exists in storage but isn't wired.
- TTM-R2 forecasting (`core/forecasting.py` empty) — **deferred per graceful-degradation guardrail**, just needs a stub docstring + UI badge update.
- P3.6 Jaeger trace screenshot still pending.

**Locked scope decisions** (this session):
| Track | Choice | Rationale |
|---|---|---|
| TORCS | Parser + 2 pre-captured fixtures from the lab + 3-line telemetry logger in `torcs_jm_par.py` | Matches existing fixture-driven demo pattern; demo determinism preserved |
| FR-8 | Full ship — all 3 perturbations, end-to-end | PRD requirement, not optional |
| Docker / CI | Docker yes (multi-stage, single image), CI no | Docker in original spec; CI never was |
| TTM-R2 | Defer to v1.1 — stub file + UI badge + doc updates | Graceful-degradation guardrail makes it explicitly optional |

## Pre-flight gotchas (resolve before coding)

These are the booby-traps the agent doing the work shouldn't have to re-derive. ~30–60 min total to absorb up front; several hours if hit mid-implementation.

1. **TORCS energy-model calibration.** The fastf1 constants (`HARVEST_KJ_PER_BRAKE_SECOND`, `DEPLOY_KJ_PER_FULL_THROTTLE_SECOND`) were tuned for FastF1 timescales and vehicle dynamics. TORCS sensor sample rates, lap durations, and brake/throttle profiles differ. **Copy verbatim and the first capture will likely produce 2 MJ/lap or 24 MJ/lap — either breaks zone detector and the harvest_cap rule.** Calibration step is non-optional: run captured baseline through the parser, scale constants until per-lap harvest/deploy lands in the 4–7 MJ/lap range (under the 8.5 MJ cap parsed from regs). Then lock with a regression test (see 1.6).
2. **gym_torcs `fuel` sensor IS exposed.** Standard gym_torcs observations include `fuel` (plus `distFromStart`, `distRaced`, `curLapTime`). Fuel-burn rate is a better proxy for engine work than a throttle integral — it captures load, gear, and RPM implicitly. Check what the captures emit and prefer `fuel` where available. Still derived (not measured 2026 hybrid state), but stronger signal.
3. **`asyncio.Lock` dict has a TOCTOU race.** Naïve `if session_id not in locks: locks[session_id] = Lock()` is racy under parallel requests. Use `setdefault`:
   ```python
   _session_locks: dict[str, asyncio.Lock] = {}
   lock = _session_locks.setdefault(session_id, asyncio.Lock())
   async with lock:
       ...
   ```
4. **WhatIf cache key — be explicit.** Pydantic frozen models with list fields aren't natively hashable. Spec:
   ```python
   cache_key = hashlib.sha256(request.model_dump_json().encode()).hexdigest()[:16]
   ```
   Stable across runs, deterministic, filename-safe.
5. **`python:3.12-slim` lacks build tools.** pyarrow / docling / some scientific deps need `gcc`/`g++`. Add `RUN apt-get update && apt-get install -y --no-install-recommends build-essential` before the pip install, OR fall back to `python:3.12` base if wheel resolution still fails.
6. **No `version:` in docker-compose.yml.** Deprecated in Compose V2; modern schema is just `services: ...` at the top level.
7. **WSL needs TORCS install too.** Migrating to WSL doesn't carry TORCS over. Budget Docker-container install per the lab's `02.2_torcs_container_setup_guide.pdf`. X-server forwarding may add friction.
8. **Process discipline + branching:**
   - **Feature work lands on `dev` (or feature branches off `dev`).** `main` only updates at the `v1.0.0-submission` tag per `final-lock-checklist.md` T-72h. Avoids force-reset under deadline pressure.
   - **Weekly gate rule:** at the end of each week classify status as **green** (all sub-items shipped → proceed, no cuts), **yellow** (one sub-item slipped to next week → trigger first cut from the list), or **red** (more than one slipped → trigger first two cuts). Mechanical, not aspirational. The 82h slack budget is for *unknown* surprises, not knowable scope creep.

## Execution sequence

### Week 1 (May 11–17) — TORCS + cleanup (~17h)

#### 1.1 — WSL migration + TORCS install (~3–5h, blocker)
Project is moving to WSL Linux. TORCS does NOT auto-carry over.
- Re-clone repo on WSL side; `python3.12 -m venv .venv`; `pip install -r requirements.txt` (pyarrow/docling may need build tools).
- `.venv/bin/pytest -q -m "not network"` — expect 231 green.
- `scripts/test_watsonx.py` — re-confirm G-1.
- `cd ui && npm install && npm run typecheck && npm run build`.
- `grep -rn "/Users/patrick" docs/ scripts/ ui/` — patch any macOS-hardcoded paths.
- **Install TORCS on WSL** per `hands-on-labs/01_torcs_lab/02_setup_guides/02.2_torcs_container_setup_guide.pdf` — Docker container path is the documented one. Verify GUI forwards via WSLg or X server.
- **Create `dev` branch off `main`** if not already present. All Week 1–3 commits land here.

#### 1.2 — TORCS telemetry logger (~1h)
Edit `hands-on-labs/01_torcs_lab/torcs_jm_par.py` to add an env-gated 3-line writer:
```python
if os.getenv("OVERRIDE_LOG_TELEMETRY"):
    with open(os.environ["OVERRIDE_LOG_TELEMETRY"], "a") as f:
        f.write(json.dumps(observation) + "\n")
```
Run twice with different settings, save outputs:
- `OVERRIDE_LOG_TELEMETRY=baseline.jsonl python torcs_jm_par.py` (defaults — Lab Task 1)
- `OVERRIDE_LOG_TELEMETRY=modified.jsonl ...` after `TARGET_SPEED = 150` (Lab Task 3)

Confirm `fuel`, `distFromStart`, `distRaced`, `curLapTime` are in the dumped observations (gotcha #2).

#### 1.3 — Implement `ingest/torcs_parser.py` + calibrate (~3.5h)
Mirror `ingest/fastf1_parser.py:1-340` (reference). Input: TORCS JSONL replay. Output: `list[LapFeatures]`.
- Lap segmentation from `distFromStart` start-line crossings.
- Sector splits from `distFromStart` against track length (1/3 / 2/3 fractions; pull per-track from a small `tracks.json` if time).
- Derive `harvest_mj` / `deploy_mj` from brake-on-time + throttle≥95% time, **scaled by calibrated constants** (below). Use `fuel` as cross-check.
- `soc_start = 1.0`, `soc_end = clamp(soc_start + (harvest - deploy)/BATTERY_CAPACITY_MJ, 0, 1)`, `soc_source = "derived"`.
- `override_uses = 0`, `boost_uses = 0`, `recharge_zones` derived post-hoc from per-sector harvest.
- Emit `note`: "Energy state derived from throttle/brake telemetry (TORCS has no native MGU-K data)."

**Calibration substep (~30 min, gotcha #1).** Run captured baseline through the parser; eyeball per-lap harvest/deploy totals against the 8.5 MJ cap parsed by `core/regs.extract_harvest_cap_mj`. Scale `HARVEST_KJ_PER_BRAKE_SECOND` / `DEPLOY_KJ_PER_FULL_THROTTLE_SECOND` until values land in the 4–7 MJ/lap range. Commit the chosen constants with a comment citing the calibration run. **Test gate locked in 1.6.**

#### 1.4 — `analysis/torcs_energy.py` (~3h)
Extract the 2026 hybrid bookkeeping (SoC/harvest/deploy synthesis) into a separate module so constants and derivation are testable independent of TORCS parsing. Future shared use with fastf1_parser (currently duplicates this math). *Cut candidate if Week 1 runs hot — see cuts list for the consequence.*

#### 1.5 — Commit the two pre-captured fixtures (~30 min)
- `data/samples/torcs_baseline.json` (from Lab Task 1 capture)
- `data/samples/torcs_modified.json` (from Lab Task 3, `TARGET_SPEED=150`)
- Update `api/main.py:_parse_upload` for `source=torcs` so it tries `torcs_parser` first and falls back to canonical-schema passthrough for backward compat with the existing `sample_torcs.json`.
- `mkdir -p data/samples/` first (dir doesn't exist).

#### 1.6 — Tests + calibration regression gate (~1.5h)
- `tests/test_torcs_parser.py` — golden tests against the two captured fixtures; assert lap counts, sector splits non-zero, SoC monotone where expected.
- **Calibration regression test** (locks gotcha #1 permanently):
  ```python
  def test_torcs_baseline_energy_calibration():
      laps = parse_torcs_session("data/samples/torcs_baseline.json")
      harvests = [L.harvest_mj for L in laps]
      deploys = [L.deploy_mj for L in laps]
      assert all(0 <= h <= 8.5 for h in harvests), "harvest violates 8.5 MJ cap"
      assert 3.0 <= statistics.median(harvests) <= 7.0, "median harvest out of realistic range"
      assert 3.0 <= statistics.median(deploys) <= 7.0, "median deploy out of realistic range"
      assert all(0 <= L.soc_end <= 1 for L in laps), "SoC out of bounds"
  ```
  Fires if anyone later tweaks the constants for the wrong reason. ~10 min to write.
- Extend `tests/test_api.py` — POST `torcs_baseline.json` to `/api/sessions?source=torcs` (mocked watsonx clients), verify clean Session round-trips.

#### 1.7 — `docs/adrs/ADR-002-torcs-as-primary-sandbox.md` (~1h)
TORCS is a learning-lab sandbox for proving decision logic; energy model is synthetic; FastF1 path complements with real data but lacks native MGU-K. Cite Sutton-Barto on RL sims as decision-proving environments.

#### 1.8 — Concurrency fix for fan-mode save (~1.5h, **in hard floor**)
`api/main.py:351-372` currently does load → modify → save_session for the whole session per fan request. Two parallel calls clobber each other. Fix:
- Add `save_recommendations_only(session_id, recommendations)` to `api/storage.py` that writes just `recommendations.json` via `tempfile + os.replace` (atomic on POSIX).
- Replace the full `save_session` call in `get_zone` with the new helper.
- Add a per-session `asyncio.Lock` using `setdefault` (gotcha #3) to serialize fan-mode writes against the same session.
- Test: `tests/test_api.py` — fire 5 concurrent `?mode=fan` requests on the same session, assert all 5 fan fields land.

#### 1.9 — Stale plan deletion (~5 min)
Delete in the same PR as the TORCS work (per `.bob/rules.md`):
- `docs/plans/phase-1-foundation-implementation.md` (P1 shipped)
- `docs/plans/zone-patterns.md` (P2.1 shipped)
- `docs/plans/p2.5-docling-kicker.md` (G-4 closed)
- `docs/plans/discord-pitch-feedback.md` (P1.2 closed)
- `docs/plans/quick-follow-up-on-github-invite.md` (moot now that lab is in repo)

Keep `docs/plans/previous-co-work-conversations.md` (transparency about development process — rubric-positive). Already in `.dockerignore`.

#### 1.10 — Post-rename stale-text scan (~5–10 min)
The Torx→TORCS rename (commit f4191df) may have left stale visible text in screenshots. Scan only — actual re-captures defer to Week 3 (so we don't re-shoot the same screenshot twice once FR-8 changes the Engineer card).
```bash
grep -rn -i "torx" ui/ assets/ recordings/ 2>&1 | grep -v node_modules
```
Document which assets need re-capture in Week 3 step 3.5.

#### 1.11 — TTM-R2 deferral cleanup (~30 min)
- Replace 0-byte `core/forecasting.py` with the docstring stub (3 lines, references roadmap P2.2 + ADR-001).
- Update `ui/src/components/EnergyCurve.tsx` empty-state — currently "No lap data to chart." When `forecast === null` AND laps are present, render "5-lap forecast (TTM-R2) deferred to v1.1 — pipeline runs end-to-end without forecasting per the graceful-degradation guardrail."
- README "Limitations": add "TTM-R2 5-lap SoC forecasting (FR-3): deferred to v1.1 per the graceful-degradation guardrail."
- `docs/03-prd.md` FR-3: append "v1.0 ships with forecast=None; v1.1 wires TTM-R2 inference."
- `docs/02-ai-and-technical-approach.md` and `docs/02-problem-and-solution.md`: change "six IBM technologies" → "five" with TTM-R2 in a "v1.1" row.

### Week 2 (May 18–24) — What-if FR-8 + observability (~29h: 21h sub-tasks + 8h integration contingency)

Week 2 is the integration-heavy block (FR-8 touches schema + perturbation + endpoint + UI + tests + cache). The +8h contingency above sub-task totals is honest budget for realistic integration friction (schema-vs-endpoint mismatch, cache-eviction edge cases, fixture-mode synthesis surprises). Track it explicitly so the buffer doesn't burn silent.

#### 2.1 — `docs/plans/whatif-semantics.md` (~30 min, **blocking 2.2**)
Write BEFORE coding. Resolve the three ambiguities:
- `delay_first_deploy(n)`: if the first deploy IS on lap 1, perturbation **shifts** it to lap 1+n (energy budget conserved), not skipped.
- `skip_harvest_zone(zone_id)`: harvest in that zone is zeroed; SoC trajectory recomputes downstream from the perturbation point (energy is **lost**, not deferred).
- `extend_override(zone_id, laps=1)`: default duration 1 lap; deploys an additional 0.5 MJ in the lap after the original zone.
- Schema-hashable WhatIfRequest payload for caching.

#### 2.2 — Schema + perturbation functions (~4h)
- Add `WhatIfRequest`, `WhatIfResult` to `ingest/schema.py` (Pydantic, frozen).
- New module `analysis/perturbations.py` — three pure functions `apply_<name>(laps, request) → laps`. No pipeline knowledge. Unit-test each in isolation.
- **If 1.4 was cut:** import energy helpers from `ingest/torcs_parser.py` directly; document the cross-domain coupling in the module docstring; tag for v1.1 cleanup.

#### 2.3 — Endpoint (~3h)
`POST /api/sessions/{session_id}/what-if` in `api/main.py`:
- Validate session exists, load it.
- Apply perturbation function to `session.laps`.
- Hash the request per gotcha #4 → check disk cache at `data/sessions/{id}/whatif/{hash}.json`.
- If miss: call `run_pipeline(perturbed_laps, ...)` (reuse `core/pipeline.py:269-310` — do NOT write a parallel pipeline). Persist result to cache.
- Return `WhatIfResult` with original + perturbed Recommendation pairs.
- Reuses existing watsonx clients via `api/main.py:112-121` dependency providers.

#### 2.4 — UI (~6h)
- `ui/src/components/WhatIfPanel.tsx`: three radio options for perturbation type + parameter input + "Run scenario" button.
- `ui/src/components/WhatIfDiff.tsx`: side-by-side Recommendation cards (original vs perturbed). NO animation; clear "Before / After" labeling per UI doc §4.3.
- Wire into `SessionPage.tsx` Engineer mode only (FR-8.3); hide in Fan mode.
- `ui/src/api/client.ts` adds `runWhatIf(sessionId, request)` including fixture-mode synthesis for offline UI dev.

#### 2.5 — Tests (~3h)
- `tests/test_perturbations.py` — golden tests for each perturbation function.
- `tests/test_api.py` — what-if endpoint happy path + cache hit + invalid zone_id 404.

#### 2.6 — P3.6 observability screenshot (~2h)
- `OVERRIDE_TRACING=otlp OTEL_EXPORTER_OTLP_ENDPOINT=localhost:4317` with local Jaeger (`docker run jaegertracing/all-in-one`).
- POST `data/samples/torcs_baseline.json` → capture `assets/screenshots/jaeger-trace.png` showing reason → validate → guardian → regs.
- README: add to "What it looks like" table.
- Delete `docs/plans/p3.6-jaeger-trace-capture.md` in the same PR (plan-file lifecycle).

#### 2.7 — Sessions list discipline cleanup (~30 min)
Don't wire `GET /api/sessions` (Tier-2 stays Tier-2). Update `ui/src/pages/SessionsPage.tsx` body to match the FR-8/TTM v1.1 framing pattern — explicit, intentional, not "coming soon".

#### 2.8 — Regenerate engineer_happy_demo fixture against real TORCS (~1h, **high-value add**)
After 2.3 lands, pipe `data/samples/torcs_baseline.json` through the full pipeline (reasoning + Pass-1 + Pass-2 + Fan + one what-if) and save as `tests/fixtures/torcs_engineer_demo.json`. Update `ui/src/api/client.ts` `fixtureNameForSessionId` routing so `s_torcs_engineer_demo` resolves to it. Upgrades rubric story from "we have a TORCS parser, here's a synthetic demo" → "the demo you're watching is a real lab session piped through the full pipeline." Watsonx cost: ~$0.05–0.10 (pipeline + Fan translation across 5 zones).

#### 2.9 — Pre-record Segment 3 retake (~1h)
End of Week 2, immediately after FR-8 UI lands. Record the what-if click flow once. If anything looks off (cross-fade, layout, timing), discover it now — not during the Week 3 video block when retake time is at a premium.

### Week 3 (May 25–28) — Docker + video + submit (~22h)

#### 3.1 — Multi-stage Dockerfile + compose (~4–6h)
Stage 1 `node:20-alpine`:
- Copy `ui/package*.json`; `npm ci`; copy `ui/`; `npm run build` → `ui/dist/`.

Stage 2 `python:3.12-slim` (gotcha #5):
- `RUN apt-get update && apt-get install -y --no-install-recommends build-essential` first. Fall back to `python:3.12` if pyarrow/docling wheels still fail.
- pip install from `requirements.txt`.
- Copy `core/`, `api/`, `ingest/`, `analysis/`, `prompts/`, `data/regs/extracted_chunks.sample.json`, `models.json`, `core/validator.yaml`, `guardian/byoc_criteria.yaml`.
- Copy `ui/dist/` from stage 1 into `/app/ui/dist/`.
- Mount `ui/dist/` via `StaticFiles` in `api/main.py` so single image serves both API and UI at port 8000.
- `HEALTHCHECK CMD curl -f http://localhost:8000/api/health || exit 1` per `docs/04-api.md` §8.
- `ENTRYPOINT ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]`.

`docker-compose.yml` (gotcha #6 — NO `version:` line):
- `override` service: build context `.`, port `8000:8000`, `env_file: .env`, volume `./data/sessions:/app/data/sessions` for persistence.
- `jaeger` service: `jaegertracing/all-in-one`, ports `16686:16686` + `4317:4317`, under `profiles: [observability]` so default `docker compose up` doesn't pull it; `docker compose --profile observability up` brings it.

`.dockerignore`:
```
.git
.venv
.venv-langflow
ui/node_modules
ui/dist
__pycache__
*.pyc
.pytest_cache
recordings/
data/regs/*.pdf
data/regs/extracted/
.env
hands-on-labs/
docs/plans/previous-co-work-conversations.md
*.DS_Store
```

Delete empty `.github/workflows/ci.yml` (empty placeholder is misleading; CI not in scope).

README quickstart collapses to:
```bash
cp .env.example .env  # fill WATSONX_API_KEY + WATSONX_PROJECT_ID
docker compose up
```
With a note: "Local-venv path still documented below for hacking on the code."

#### 3.2 — README + docs final polish (~2h)
- Refresh the live-performance table with current measurements after FR-8 + Docker.
- "What's coming next" section: TTM-R2 v1.1, Sessions list v1.1, CI v1.1, Section B Sporting Regs v1.1.
- Verify zero hardcoded FIA article numbers: `grep -rE "C5\.18|article [0-9]" --include="*.py" --include="*.tsx" --include="*.md"`.
- One line: "CI workflows planned for v1.1. Current quality gate: pytest -q (231/231 unit + 4/4 network) + npm run typecheck && npm run build per docs/plans/final-lock-checklist.md T-72h pre-flight."

#### 3.3 — `recordings/` git policy decision (~10 min)
Decide before video re-record:
- `recordings/*.mov` (masters, ~200 MB total) — `.gitignore` them; not part of the repo deliverable.
- `recordings/voiceover-seg-*.m4a` (stems, ~10 MB) — track them; submission-grade evidence a reviewer might want.
- `recordings/final.mp4` — track if it fits; reference the YouTube URL otherwise.
Add the chosen rules to `.gitignore` and commit.

#### 3.4 — Submission portal copy refresh (~30 min)
`docs/plans/submission-portal-copy.md` was drafted pre-TORCS, pre-FR-8. Walk through with current truth before T-2h paste:
- "How it works" paragraph — mention TORCS as primary lab data source alongside FastF1.
- Tech stack section — five IBM technologies (TTM-R2 v1.1 row), Docker as shipping shape.
- "What we built" framing — include what-if interactive counterfactuals.

#### 3.5 — Video re-record (~12h, with retake buffer) + asset re-captures (~30 min)
Per the locked 2:55 script in `docs/plans/video-script.md`, re-shoot:
- Segment 3 (demo flow): include the what-if toggle moment — pick a zone, run a perturbation, see the side-by-side diff. (Pre-recorded in 2.9; redo only if retake required.)
- Segment 4 (explainability): refresh against current Engineer Mode card + new Jaeger screenshot beat.
- Segment 7 (closing): voiceover pace check; tighten if it positions OVERRIDE smaller than what's now shipped.
- Audit every cursor stroke for stale filenames (`sample_torx` etc. — should be `torcs` everywhere post-f4191df).
- Final cut ≤2:55; upload to YouTube **unlisted** with public switch reserved for T-0.

**Asset re-captures** (deferred from 1.10): re-shoot the screenshots flagged in the Week 1 scan, now that the FR-8 what-if rail is in its active state (not the disabled stub).
- `assets/screenshots/upload.png` (post-rename text)
- `assets/screenshots/dashboard.png` + `engineer-mode.png` (now showing the what-if panel active)
- `assets/demo.gif` (re-export only if visible `sample_torx` text found)

Budget breakdown for video: rewrite voiceover lines (~30 min) + pace check (~15 min) + voiceover record with retakes (~45 min) + Segment 3 screen-capture retakes (~45 min) + Segment 4 (~30 min) + edit timeline (~1.5h) + export MP4 (~20 min) + YouTube upload (~20 min) + retake-of-retakes contingency (~3–4h). Total ~12h realistic.

### Final lock (May 29–31) — Phase 5 (~6h)

Execute `docs/plans/final-lock-checklist.md` as-written, plus these additions:

- **T-72h (May 29):** Code freeze. `pytest -q -m "not network"` green. `npm run build` green. No credentials in git. All stale plan files deleted. Tag `v1.0.0-submission`.
  - **NEW:** Fresh-clone smoke — `git clone <your repo> /tmp/override-fresh && cd /tmp/override-fresh && docker compose up`; verify port 8000 serves UI; upload a TORCS sample → end-to-end clean. Catches "I forgot to commit a file" failure.
  - **NEW:** `git ls-files | xargs wc -c 2>/dev/null | sort -rn | head -20` — catches large files accidentally tracked (rogue .mov, brand asset bloat).
  - **NEW:** Risk register sweep — walk `docs/05-risk-register.md`; mark resolved (R1, R3, R4, R13, R14, R16) closed; update likelihood on de-risked items (R5 not triggered, R18 mitigated via Essentials upgrade). ~15 min; signals to judges that risk discipline was maintained through the build.
  - **NEW:** Watsonx burn check — expected total over the 19-day window: $1–10 USD on Essentials (Week 2 retesting + Jaeger captures the hot spot). CA$10 budget alerts on Runtime + Studio cover surprises.
  - **NEW:** Merge `dev` → `main` only at this gate. Tag from `main`.
- **T-24h (May 30):** Clean-machine walk with `docker compose up` on a fresh user account. README cold-read. All 7 screenshots present and current.
- **T-2h (May 31 afternoon):** BeMyApp portal copy from `docs/plans/submission-portal-copy.md` (already refreshed in 3.4). Banner, logo, demo GIF uploaded. Video URL switched public. Preview page read in incognito.
- **T-0 (May 31 8 PM ET):** **Publish.** Confirmation email check. Lock at 11 PM ET (1h buffer before 11:59 PM deadline).

## Critical files modified (by area)

| Area | Paths |
|---|---|
| TORCS data path | `hands-on-labs/01_torcs_lab/torcs_jm_par.py`, `ingest/torcs_parser.py`, `analysis/torcs_energy.py`, `api/main.py:_parse_upload`, `data/samples/torcs_*.json` (new), `tests/test_torcs_parser.py` (new), `docs/adrs/ADR-002-torcs-as-primary-sandbox.md` (new) |
| FR-8 what-if | `ingest/schema.py` (+WhatIfRequest/Result), `analysis/perturbations.py` (new), `api/main.py` (new endpoint), `api/storage.py` (whatif cache helpers), `ui/src/components/WhatIfPanel.tsx` + `WhatIfDiff.tsx` (new), `ui/src/api/client.ts`, `ui/src/pages/SessionPage.tsx`, `tests/test_perturbations.py` (new), `tests/test_api.py` (extend), `docs/plans/whatif-semantics.md` (new, deleted on PR merge) |
| Concurrency fix | `api/main.py:351-372`, `api/storage.py` (new `save_recommendations_only`), `tests/test_api.py` |
| TTM-R2 deferral | `core/forecasting.py` (stub docstring), `ui/src/components/EnergyCurve.tsx` (empty-state text), `README.md`, `docs/03-prd.md`, `docs/02-ai-and-technical-approach.md`, `docs/02-problem-and-solution.md` |
| Docker | `Dockerfile`, `docker-compose.yml`, `.dockerignore` (new), `api/main.py` (mount StaticFiles), `README.md` |
| Cleanup | Delete `.github/workflows/ci.yml`, `docs/plans/phase-1-foundation-implementation.md`, `docs/plans/zone-patterns.md`, `docs/plans/p2.5-docling-kicker.md`, `docs/plans/discord-pitch-feedback.md`, `docs/plans/quick-follow-up-on-github-invite.md`, `docs/plans/p3.6-jaeger-trace-capture.md` (after Week 2) |
| Observability | `assets/screenshots/jaeger-trace.png` (new), `README.md` (link it) |
| SessionsPage discipline | `ui/src/pages/SessionsPage.tsx` (v1.1 framing) |
| Asset refresh (Week 3) | `assets/screenshots/upload.png`, `dashboard.png`, `engineer-mode.png`, `assets/demo.gif` (conditional) |
| Demo fixture upgrade | `tests/fixtures/torcs_engineer_demo.json` (new), `ui/src/api/client.ts` (routing) |
| Submission assets | `recordings/` (new takes per 3.3 policy), `docs/plans/submission-portal-copy.md` (refresh), YouTube (unlisted → public), BeMyApp portal |

## Existing utilities to reuse (don't reinvent)

- **Parser pattern:** `ingest/fastf1_parser.py:1-340` — copy its derivation constants and `parse_fastf1_lap` shape for torcs_parser. **Then calibrate** (gotcha #1).
- **Pipeline orchestration:** `core/pipeline.py:269-310` `run_pipeline(...)` — already accepts `forecast_fn=None`; what-if just calls it with perturbed laps.
- **Watsonx client deps:** `api/main.py:112-121` `get_chat_client / get_embedding_client / get_guardian_client` — reuse via `Depends()` in the what-if endpoint.
- **Storage atomic write pattern:** none today (gap); model the new `save_recommendations_only` after `api/storage.py:51-84` + tempfile/os.replace.
- **Session/Recommendation Pydantic shapes:** `ingest/schema.py` — extend, don't fork.
- **UI fixture switching:** `ui/src/api/client.ts:166-185` — what-if needs the same `{ fixture }` pattern; add a `runWhatIf` method that synthesizes a diff from the fan_mode fixture in fixture mode.
- **Empty-state component:** `ui/src/components/EmptyStates.tsx` — already used for grounding-pending banner; reuse for TTM-R2 deferral badge and SessionsPage v1.1 framing.

## Verification (weekly gates with green/yellow/red rule)

**End of Week 1:**
- `.venv/bin/pytest -q -m "not network"` — expect ~241 green (231 baseline + 10 new TORCS tests).
- Launch `uvicorn api.main:app --port 8000` + `cd ui && npm run dev`.
- Drop `data/samples/torcs_baseline.json` on the upload page → session lands on dashboard, recommendations render, regulation citation links work.
- Toggle Fan mode on all zones simultaneously; verify all fans persist (concurrency fix).
- `git log --oneline -8` on `dev` shows the five stale plans deleted alongside the features shipping them.
- **Apply green/yellow/red rule** (gotcha #8): green → proceed; yellow → trigger cut #1; red → trigger cuts #1+#2.

**End of Week 2:**
- ~260 tests green.
- POST a what-if request via curl: get a perturbed Recommendation diff back.
- UI: pick a zone, change `delay_first_deploy` to 2, see the Before/After cards diff correctly.
- Run with `OVERRIDE_TRACING=otlp` + Jaeger; screenshot captured.
- Segment 3 retake recorded (2.9) — review for cross-fade / layout / timing issues.
- **Apply green/yellow/red rule.**

**End of Week 3:**
- `docker compose up` on a fresh clone → port 8000 serves both UI and API → upload a TORCS fixture → end-to-end clean.
- Video timed at ≤2:55.
- YouTube unlisted URL plays in incognito.
- **Apply green/yellow/red rule.** Final week — yellow/red here means a same-day catch-up rather than a cut.

**Final lock day:** `final-lock-checklist.md` walked end-to-end + the four NEW T-72h sub-steps (fresh-clone smoke, large-file scan, risk register sweep, watsonx burn check).

## Cuts if time slips

In order of what gets dropped first:
1. **Second TORCS fixture** (`torcs_modified.json`) — ship just the baseline; one fixture is enough for the video.
2. **WhatIfPanel UI polish** (animation, parameter sliders) — ship radios + button only.
3. **Demo fixture regeneration** (2.8) — keep the existing engineer_happy_demo synthetic fixture.
4. **Jaeger screenshot** (2.6) — fall back to a code-only mention in README "Observability" section.
5. **`analysis/torcs_energy.py` extraction** (1.4) — keep the derivation inline in `ingest/torcs_parser.py` if time-boxed. **Consequence:** `analysis/perturbations.py` (2.2) then imports energy helpers directly from `ingest/torcs_parser.py` — accept the cross-domain coupling, document in module docstring, plan v1.1 cleanup.
6. **`tracks.json` per-track sector splits** — hardcode 1/3 / 2/3 across all TORCS tracks.

**Hard floor** (cannot cut without missing vision):
- TORCS parser running end-to-end (with the calibration regression test from 1.6)
- FR-8 all three perturbations
- Docker compose up working
- Concurrency fix for fan-mode save (1.8) — visible failure mode in a multi-zone demo otherwise
- Video re-recorded with the what-if beat

## Out of scope (defer to v1.1, document not implement)

- TTM-R2 forecasting (graceful-degradation guardrail makes it optional).
- GET /api/sessions list endpoint + real SessionsPage.
- Section B Sporting Regulations grounding (only Section C Technical lands in v1).
- GitHub Actions CI.
- Live TORCS-during-demo capture (logger is committed but not wired into the video).
- Authentication / multi-user (single-user replay-first per `05-security.md`).