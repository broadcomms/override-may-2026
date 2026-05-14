# Coder handoff — 2026-05-14

> **Audience:** Claude Code (CLI) implementer working on `overdrive-may-2026`.
> **Purpose:** A focused punch-list against the v6 master plan after an architect-side audit found that most of Weeks 1–3 implementation is already shipped. This document supersedes the implication of "follow the v6 plan top to bottom" — it tells you exactly what still needs hands.
> **Lifecycle:** delete this file in the same PR that closes the last action item below (per `.bob/rules.md`).
> **Today is 2026-05-14.** Submission target May 27–28; final deadline May 31 11:59 PM ET.

---

## 1. Snapshot — what's already shipped (do NOT re-implement)

Audit performed 2026-05-14 against `\\wsl.localhost\ubuntu-24.04\home\patrick\overdrive-may-2026\`. Verified by file presence + key-symbol grep. Reference back to v6 plan §x.y in parens.

| Area | Status | Evidence |
|---|---|---|
| WSL/Podman migration (§1.1) | ✅ | Per `CLAUDE.md` post-edit |
| `RaceYourCode/gym_torcs/` in repo + MIT LICENSE preserved (§1.1b) | ✅ | `RaceYourCode/gym_torcs/LICENSE` on disk; README §"Acknowledgements" line 295 cites it |
| `OVERRIDE_LOG_TELEMETRY` env-gated logger in `torcs_jm_par.py` (§1.2) | ✅ | `RaceYourCode/gym_torcs/torcs_jm_par.py:551–584` |
| `ingest/torcs_parser.py` with JSONL safe-read (§1.3 + gotcha #12) | ✅ | File exists; line 87 skips incomplete tail; line 92 swallows `JSONDecodeError` |
| `analysis/torcs_energy.py` (§1.4) | ✅ | File exists |
| TORCS fixtures + `_parse_upload(source="torcs")` wiring (§1.5) | ✅ | `data/samples/torcs_baseline.jsonl`, `torcs_modified.jsonl`; `api/main.py:1778` |
| Calibration regression test (§1.6) | ✅ | `tests/test_torcs_parser.py:234` `test_torcs_baseline_energy_calibration` |
| ADR-002 (§1.7) | ✅ | `docs/adrs/ADR-002-torcs-as-primary-sandbox.md`, Accepted 2026-05-11 |
| Fan-mode concurrency fix (§1.8 + gotcha #3) | ✅ | `api/storage.py:88 save_recommendations_only`, `api/main.py:133 _fan_locks`, `:605 setdefault` |
| Stale-plan deletion (§1.9) | ✅ | All 5 originally-listed files absent from `docs/plans/` |
| `WhatIfRequest` / `WhatIfResult` schema (§2.2) | ✅ | `ingest/schema.py:405,454` |
| `analysis/perturbations.py` (§2.2) | ✅ | File exists |
| What-if endpoint (§2.3) | ✅ | `api/main.py` matches `/what-if` |
| What-if UI (§2.4) — note: built as `WhatIfRail` inline in `RecommendationCard.tsx`, NOT a separate `WhatIfPanel.tsx` | ✅ (with naming drift, see §3 follow-ups) | `ui/src/components/RecommendationCard.tsx:151,345` |
| Perturbation tests (§2.5) | ✅ | `tests/test_perturbations.py` |
| Jaeger trace screenshots (§2.6) | ✅ | `assets/screenshots/jaeger-trace.png`, `jaeger-trace-span.png` |
| `torcs_engineer_demo` fixture regenerated (§2.8) | ✅ | `tests/fixtures/torcs_engineer_demo.json` |
| Ollama LLM client + ADR-003 (§2.10) | ✅ | `core/llm_clients/ollama.py`, `docs/adrs/ADR-003-llm-runtime-abstraction.md` |
| `Dockerfile` multi-stage (§3.1) | ✅ | File exists, header documents v6 plan §3.1 lineage |
| `docker-compose.yml` with `profiles: [torcs]` + `[observability]` + `OVERRIDE_OLLAMA_BASE_URL` (§3.1) | ✅ | `docker-compose.yml:39,91,200,57` |
| `scripts/torcs_container_init.sh` (§3.1b) | ✅ | File exists |
| `/api/sessions/torcs-live` endpoint (§3.2) | ✅ | `api/main.py` references torcs-live |
| ADR-004 TORCS control plane | ✅ | `docs/adrs/ADR-004-torcs-control-plane.md`, Accepted 2026-05-13 |

**Test count baseline per `CLAUDE.md`:** 301 unit + 4 network = 305. Verify in Step 2.1 below.

---

## 2. Verify before doing anything (15 min)

These are ground-truth checks. The audit above is grep-and-glob; you need to run things to be sure.

### 2.1 Tests green at the documented baseline (5 min)

```bash
cd ~/overdrive-may-2026                          # WSL Ubuntu
.venv/bin/pytest -q -m "not network"             # expect: 301 passed, 4 deselected
.venv/bin/pytest -q -m network --co              # expect: 4 collected (do NOT run; preserves watsonx budget)
```

**If count ≠ 301:**
- Higher: `CLAUDE.md` is stale — open this file, update its `## Repo state` block, and update `docs/plans/qa-results.md` §1's `231 unit + 4 network = 235 green` line to whatever the current count is. The two must agree.
- Lower: a test got deleted or skipped between the CLAUDE.md edit and now. Investigate before continuing.

### 2.2 watsonx + UI smoke (5 min)

```bash
.venv/bin/python scripts/test_watsonx.py        # gate G-1, ~5s
.venv/bin/python scripts/test_watsonx_embedding.py
cd ui && npm run typecheck && npm run build      # tsc + vite build
```

All four must pass cleanly. If watsonx scripts fail with auth errors, your `.env` drifted — re-pull credentials from IBM Cloud.

### 2.3 Container build sanity (5 min)

```bash
podman --version                                 # need 4.4+ for pasta backend (v6 plan §1.1)
podman compose version                           # built-in V2; fall back to `podman-compose` package if missing
podman compose build override                    # multi-stage build to completion
podman compose up -d override                    # default profile (no TORCS pull)
curl -sf http://localhost:8000/api/health         # 200 OK
podman compose down
```

If the build fails on missing build-essential (gotcha #5), confirm the Dockerfile installs gcc/g++ before `pip install`. If healthcheck fails, capture `podman logs override` and stop — that's a real blocker that bumps everything.

---

## 3. Action items — what to actually do (priority order)

Three real items found. Estimate: ~45–75 min total.

### A. Rename stale "Torx" in `langflow/override_langflow_canvas.json` (15 min) — §1.10 closeout

The langflow canvas has 3 visible "Torx" strings that will appear in the Week-3 `langflow-canvas.png` screenshot re-capture:

- Line 281: `"description": "Parse a Torx JSON or FastF1 export..."` → change to `"Parse a TORCS JSON or FastF1 export..."`
- Line 362: `"info": "Absolute path to the Torx JSON..."` → change to `"Absolute path to the TORCS JSON..."`
- Line 427: `"info": "Parser to use. 'torx' for Torx JSON..."` → change to `"Parser to use. 'torcs' for TORCS JSON..."`

**Important:** the runtime expects whichever string was wired before. Before changing line 427, grep `parser.*torx` across `langflow/` and `core/` to make sure no runtime code depends on the literal `"torx"` parser key — if it does, fix the runtime first OR keep the `"torx"` key value and only change the surrounding `info` text. The other two lines (281, 362) are display-only and safe to change.

**Acceptance:**
- `grep -rn -i "torx" .` returns ONLY: `docs/plans/overide-complete-plan-to-submission.md` (legitimate rename history) and `hands-on-labs/01_torcs_lab/05_webiner/*.txt` (upstream lab transcripts, not ours to edit).
- `npm run build` in `ui/` still passes.
- Langflow demo still parses sessions if exercised end-to-end (or note in commit message that this is display-only).

### B. Update `qa-results.md` §1 with the verified test count (5 min) — §2 follow-up

After Step 2.1 above:
- Edit `docs/plans/qa-results.md` line 37 — replace `**231 unit tests + 4 network-marked integration tests = 235 green**` with the verified current count, dated 2026-05-14.
- This satisfies the `final-lock-checklist.md` T-72h "count recorded" rule that the architect-edit pass just installed.

### C. Add a `GET /api/torcs-status` shape audit (15–30 min) — §3.2 verification + plan-doc accuracy

The v6 plan §3.2 calls out `GET /api/torcs-status` as the UI gate for the "Live TORCS detected" banner. Verify it exists and returns a useful shape:

```bash
.venv/bin/uvicorn api.main:app --port 8000 &
sleep 2
curl -s http://localhost:8000/api/torcs-status | jq .
kill %1
```

**Expected shape (write the endpoint to match if it doesn't already):**
```json
{
  "available": true,
  "telemetry_dir": "/app/data/telemetry",
  "captures": [
    {"run_id": "baseline", "path": "...", "size_bytes": 12345, "modified_at": "2026-05-14T..."}
  ]
}
```

If the endpoint is missing, write it in `api/main.py` near the other torcs-live route — read `data/telemetry/*.jsonl` (default path; honor the same env override `/app/data/telemetry/` uses inside the container), return the file list + a top-level `available` boolean. Then wire `ui/src/pages/UploadPage.tsx` to call it on mount and show the banner when `available: true`.

If it already exists, just confirm it works and move on.

**Acceptance:**
- `curl /api/torcs-status` returns the documented shape.
- `ui/src/pages/UploadPage.tsx` shows the "Live TORCS detected" banner only when `available: true`.
- One unit test in `tests/test_api.py` covering empty-dir → `available: false` and one-file-present → `available: true`.

---

## 4. Architect follow-ups (NOT for the coder — context only)

These are mine. Listed so you know what's coming and don't accidentally touch them:

1. **Write `docs/plans/whatif-semantics.md` retroactively** OR fold the semantics into `docs/04-api.md`. The plan §2.1 called this "blocking 2.2" but 2.2 already shipped — the doc is now a retroactive record of what was built, and probably belongs in 04-api.md rather than a transient plan file.
2. **Reconcile v6 plan §2.7 with current code.** Plan said "Don't wire `GET /api/sessions`"; the Phase-1 ship wired it. Update §2.7 to record the decision change.
3. **Reconcile v6 plan §2.4 `WhatIfPanel` vs shipped `WhatIfRail`.** Possibly just a rename in the plan; possibly worth a one-line ADR.
4. **Update `seg3-recording-handoff.md`** if the WhatIfRail click sequence is materially different from the documented WhatIfPanel flow.

I'll handle each before the Week 3 final-polish window (May 25+).

---

## 5. Don'ts

- **Don't recreate `.github/workflows/ci.yml`.** Per `CLAUDE.md` + `AGENTS.md`, it was deleted intentionally and CI deferred to v1.1.
- **Don't fill in `core/forecasting.py`.** Intentional v1.1 stub.
- **Don't hardcode FIA article numbers** anywhere — citations render dynamically from Docling at runtime via `RegulationSource`.
- **Don't add new tests that depend on live watsonx without the `@pytest.mark.network` marker.**
- **Don't edit files in `hands-on-labs/01_torcs_lab/`** — those are upstream IBM lab assets and stay verbatim.

---

## 6. How to close this brief

When all three action items (A, B, C) ship — typically one PR — delete this file in the same commit. That keeps the plans/ folder aligned with `.bob/rules.md`. Reference this brief in the PR description so the architect-side audit is traceable.

If you discover a real gap NOT listed here while doing A/B/C, add it as a section "D" below before fixing it, so the trail of "audit-confirmed gaps vs. discovered gaps" stays clean.
