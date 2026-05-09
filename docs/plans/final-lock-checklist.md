# P5 — Final lock checklist

> Pre-submission walkthrough for the OVERRIDE submission to the IBM SkillsBuild AI Builders Challenge.
> **Deadline: 2026-05-31, 11:00 PM ET** (verify on the BeMyApp portal — ET vs PT has tripped past submissions).
>
> This is a **durable runbook** — execute top-to-bottom on **May 30** (T-24h) and **May 31** (submission day). High-stress moment; pre-written wins over improvising.
>
> Sister doc for portal copy: [`submission-portal-copy.md`](./submission-portal-copy.md).
> Source-of-truth doc for QA evidence: [`qa-results.md`](./qa-results.md).
>
> Per `.bob/rules.md`: this plan file is deleted in the commit that ships the final submission.

---

## T-72h (Friday May 28) — pre-flight prep

### Code freeze prep
- [ ] All Phase 4 video assets uploaded to YouTube (unlisted) — URL captured
- [ ] All Phase 4 portal copy reviewed against `submission-portal-copy.md`
- [ ] No PRs in flight on `main` — branch is stable/demoable
- [ ] `dev` branch (if used) merged into `main` if anything pending
- [ ] No `.env`, no credentials, no API keys committed (run `git ls-files | xargs grep -lE "WATSONX_API_KEY|sk-|api_key.*=" 2>/dev/null` and verify it returns nothing real)

### Repo hygiene
- [ ] Plan files for shipped features deleted per `.bob/rules.md`:
  - `docs/plans/p2.5-docling-kicker.md`
  - `docs/plans/p3.6-jaeger-trace-capture.md`
  - `docs/plans/zone-patterns.md`
  - `docs/plans/phase-1-foundation-implementation.md`
- [ ] Plan files KEPT (active work or durable runbook): `README.md`, `discord-pitch-feedback.md`, `quick-follow-up-on-github-invite.md`, `qa-results.md`, `final-lock-checklist.md` (this file), `submission-portal-copy.md`, `video-script.md`
- [ ] No `__pycache__/` or `node_modules/` committed
- [ ] No 0-byte placeholder files left in `assets/`

### Test suite green
```bash
cd /Users/patrickndille/overdrive-may-2026
.venv/bin/pytest tests/ -q -m "not network"
# expect: 231 passed, 4 deselected
```
- [ ] Unit suite green
- [ ] UI typecheck green: `cd ui && npm run typecheck`
- [ ] UI build green: `cd ui && npm run build`

---

## T-24h (Saturday May 30) — clean-machine walk

The single most important pre-submission check. **Pretend you've never seen the project before.** Borrow a spouse's laptop, an old machine, or use a fresh user account.

### Setup — does the README quickstart actually work?

Following ONLY what the README says, in order:

1. [ ] Clone the repo from a fresh terminal
2. [ ] Create the Python venv per the Quickstart
3. [ ] `pip install -r requirements.txt` — completes without errors
4. [ ] Copy `.env.example` → `.env`, fill in watsonx credentials
5. [ ] Run `scripts/test_watsonx.py` — gate G-1 closes (~5 sec, prints success)
6. [ ] Start uvicorn: `uvicorn api.main:app --reload --port 8000`
7. [ ] In a second terminal: `cd ui && npm install && npm run dev`
8. [ ] Open `http://localhost:3000` — UI renders without console errors
9. [ ] Drop `data/sessions/sample_torx.json` onto the upload zone
10. [ ] Pipeline runs end-to-end (~8 sec); recommendation card renders with citation

If any step fails, **fix the README, not the code** (ship a robust quickstart over a robust justification).

### Smoke test — live pipeline still produces real output
- [ ] Engineer mode card shows: cause, consequence, recommendation, citation block, validator badge (green ✓), guardian badge (`AI Safety Review: 1.00 / 1.00`)
- [ ] Citation passage matches a real chunk from `data/regs/extracted_chunks.sample.json` (verify by grep)
- [ ] `regulation_citation.source.section` is rendered dynamically (e.g. `C5.2.6`) — not hardcoded
- [ ] Mode toggle (Engineer/Fan) cross-fades smoothly; Fan card shows headline + what-happened + why-it-mattered
- [ ] No console errors in browser DevTools

### README cold-read — does it stand alone?

Have someone who hasn't seen the project (spouse, friend, peer) read the README top-to-bottom and answer 3 questions in 60 seconds:
- [ ] What does OVERRIDE do?
- [ ] Who is it for?
- [ ] What's IBM Granite's role?

If they can't answer all 3 from the README alone, **the README needs a fix, not the reader**.

### Asset audit — every screenshot is the LATEST polish-pass version
```bash
ls -la assets/screenshots/
# verify: dashboard, engineer-mode, fan-mode, reasoning-card, guardian-rejection, langflow-canvas, jaeger-trace
# all non-zero, all post-P3.5-polish (snap-out hover, 3px citation accent, etc.)
```
- [ ] All 7 required screenshots present + non-zero
- [ ] Engineer mode screenshot shows the polished citation block (3px granite-blue left border)
- [ ] Fan mode screenshot is from the same session as engineer mode (consistency)
- [ ] Langflow canvas screenshot shows all 9 OVERRIDE custom components wired (no orphan If-Else)
- [ ] Jaeger trace screenshot shows the per-stage span tree with attribute drill-down

### Brand assets check
- [ ] `assets/logo.png` (4800×1600 wordmark)
- [ ] `assets/logo-icon.png` (2048×2048 icon)
- [ ] `assets/brand/` contains all 18 brand variants
- [ ] `ui/public/favicon.svg` + `ui/public/logo-icon.png` wired (browser tab favicon + UI header icon both render)
- [ ] `assets/demo.gif` plays as ≤8s loop, ≤6 MB, 960×540

### Documentation cross-check
- [ ] `docs/03-architecture.md` matches actual codebase (no missing folders, no extra phantom modules)
- [ ] `docs/03-architecture.mmd` renders to `assets/architecture.png` cleanly
- [ ] `docs/04-api.md` endpoint list matches `api/main.py` reality (Tier 1 only — Tier 2 marked deferred)
- [ ] `docs/04-schema.md` Pydantic shapes match `ingest/schema.py`
- [ ] `docs/06-roadmap.md` reflects actual phase completion (P3.7 complete, etc.)
- [ ] `docs/regulation-source.md` references Issue 18 (current ground-truth)
- [ ] No `<TODO>` / `<PENDING>` / `<your-username>` placeholders left anywhere in `docs/` or `README.md` (grep)

```bash
grep -rE "TODO|PENDING|<your|<YOUTUBE_LINK|FIXME|XXX" docs/ README.md 2>&1 | grep -v "qa-results\|final-lock\|submission-portal"
# Expect empty (the three checklist files allow themselves to mention placeholders)
```

### Live UI capture for any final re-screenshots
If any of the 7 screenshots looks stale vs. the current polish:
- [ ] Re-capture at 2× DPI per `docs/04-ui-ux-design.md §11`
- [ ] Save to `assets/screenshots/` with original filename (so README references resolve)

---

## T-12h (Sunday May 31, morning) — final code freeze

### Models locked
- [ ] `models.json` lists exact model IDs (no version drift)
- [ ] `requirements.txt` pins `ibm-watsonx-ai==1.5.11` and OTel packages
- [ ] `requirements-langflow.txt` pins `langflow==1.9.2`
- [ ] watsonx project quota verified — no surprise rate limits during demo recording

### Last commit hygiene
```bash
git status                       # clean — no uncommitted changes
git log --oneline -5             # last 5 commits readable
git ls-files --modified          # empty
git diff main..HEAD --stat       # if branched, verify diff is the submission diff
```
- [ ] All commits have meaningful messages (no `wip` / `fix typo` clutter at the top)
- [ ] No force-push protection issues — `main` is in expected state
- [ ] Tag the submission commit: `git tag -a v1.0.0-submission -m "IBM SkillsBuild AI Builders Challenge submission"`

### Final test sweep
```bash
.venv/bin/pytest tests/ -q -m "not network"     # 231 expected
.venv/bin/pytest tests/ -q -m "network" --co     # show network-marked tests; do NOT run unless watsonx budget allows
cd ui && npm run typecheck && npm run build
```
- [ ] Unit suite green
- [ ] UI build green; bundle size ~178 KB gzipped (sanity check no dependency bloat)

---

## T-2h (Sunday May 31, afternoon) — submission portal final check

### BeMyApp portal fields — see `submission-portal-copy.md`
- [ ] Project name: **OVERRIDE**
- [ ] Tagline: locked (per `submission-portal-copy.md`)
- [ ] Problem statement: pasted from `submission-portal-copy.md`, no edits
- [ ] Solution statement: pasted from `submission-portal-copy.md`, no edits
- [ ] How to try it: pasted from `submission-portal-copy.md`, no edits
- [ ] Tech stack: tagged (IBM Granite, Docling, Langflow, FastAPI, React, watsonx.ai)
- [ ] Banner image uploaded: `assets/banner.png` (1920×600 if portal asks)
- [ ] Logo uploaded: `assets/logo.png` (square or wordmark per portal field name)
- [ ] Demo video URL: YouTube unlisted link (verified working from incognito tab)
- [ ] GitHub repo URL: public if portal allows (or unlisted if private during judging)
- [ ] License: Apache 2.0
- [ ] Team members listed
- [ ] Submission category / track: confirmed (verify with the rubric — see [BeMyApp May 2026 challenge brief](#))

### Cross-platform verification
- [ ] Open the portal page in incognito Chrome — embeds work, video plays
- [ ] Open the portal page on mobile (iOS Safari + Android Chrome if possible) — banner + logo render, video plays
- [ ] All external links work (GitHub, YouTube, FIA source citations)

### Pre-publish dry run
- [ ] Click "Save as draft" — verify draft state shows everything correctly
- [ ] Read every field one more time, ON the published preview, NOT in the editor (catches HTML escaping issues)

---

## T-0 (Sunday May 31, 8 PM ET — 3h before deadline)

### Submit early; debug if needed
- [ ] Click **PUBLISH** at 8 PM ET (not 10:55 PM ET — submission portals are flaky under load near deadlines)
- [ ] Confirmation email received within 5 minutes — screenshot + save
- [ ] Refresh the public submission page — verify it appears in the listing
- [ ] If anything fails: there's still 3h of margin; redo from T-2h

### Backup — if portal is down
- [ ] Email the BeMyApp organizer with: project name + GitHub URL + YouTube URL + a copy of the portal-copy document
- [ ] Screenshot the portal failure (timestamp + URL visible)

---

## Post-submit (Sunday May 31 evening)

### Confirmations
- [ ] Submission visible in your BeMyApp account dashboard
- [ ] Email confirmation archived
- [ ] Discord #may-challenge-and-lab post (optional but useful — first-10-teams bonus already locked from May 23 push)

### Repo final touches
- [ ] Push the `v1.0.0-submission` tag to GitHub
- [ ] Create a GitHub Release from the tag with the same body as `submission-portal-copy.md`'s "How to try it" section
- [ ] (Optional) Public-flag the repo if it was private during judging
- [ ] (Optional) Pin the README at the top of the repo

### Self-checklist for the next 48h
- [ ] Don't make any code changes until after judging announcement (avoids accidental "submitted code != judged code" scenarios)
- [ ] Discord channel for organizer messages — check daily
- [ ] Keep the YouTube video as **unlisted, not private** — judges access via the portal link

---

## Things that go wrong (and quick fixes)

| Failure mode | Quick fix |
|---|---|
| Pipeline test fails on T-24h | Don't panic. Re-read the QA results doc — was it always passing? Did `models.json` change? Roll back the offending commit. |
| README quickstart breaks on clean machine | Update the README, **not** the workflow. Common cause: missing env var, missing data file, incorrect `pip` version. Document the fix in the README. |
| YouTube upload pending after 1h | Re-export at lower bitrate (10 Mbps is plenty for 1080p talking-head). |
| Portal banner image rejected | Resize to portal's exact spec (BeMyApp typically wants 1280×640 or 1920×1080); re-upload. |
| watsonx credentials expired | Regenerate API key in IBM Cloud → update `.env` → re-run `test_watsonx.py`. |
| Demo.gif over 6 MB | Re-export with `gifsicle -O3 --lossy=80 input.gif > output.gif` or use `ffmpeg -i input.mov -vf "scale=960:-1,fps=15" -loop 0 output.gif`. |
| Last-second Discord ask from organizer | Reply within 1h. The first response time signals professionalism. |

---

## "I'm done" definition

Your submission is **locked** when:
1. ✅ The submission appears in the BeMyApp public listing
2. ✅ The confirmation email is in your inbox
3. ✅ The GitHub repo is at the `v1.0.0-submission` tag
4. ✅ All four `docs/plans/*.md` files (qa-results, video-script, final-lock-checklist, submission-portal-copy) are committed in their final state
5. ✅ You can show your spouse/friend the published submission and they understand what OVERRIDE does in 30 seconds

The clock stops when condition 1 is met. Everything else is post-submit hygiene.
