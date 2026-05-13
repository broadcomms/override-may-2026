# OVERRIDE — BeMyApp portal copy (ready to paste)

> Pre-approved text for every BeMyApp submission portal field. Paste directly; **do not wordsmith under deadline pressure**. Each section below is labelled with the portal field it maps to.
>
> Source-of-truth for positioning: `docs/00-thesis.md` line 3 (the locked sentence).
> Source-of-truth for product story: `README.md` opening + `docs/00-abstract.md` shot-list.
> Source-of-truth for technical detail: `docs/03-architecture.md`, `docs/04-api.md`, `docs/05-security.md`.
>
> Every figure here is verified against `docs/plans/qa-results.md`. If you change a number in this doc, change it in `qa-results.md` too.
>
> Per `.bob/rules.md`: this plan file is deleted in the commit that ships the final submission.

---

## 1. Project name (portal field: **Name** / **Project Title**)

```
OVERRIDE
```

> All-caps; one word; no tagline appended. The wordmark in `assets/logo.png` matches.

---

## 2. Short tagline (portal field: **Subtitle** / **Tagline** — typically ≤ 80–100 chars)

**Use this version when the field is small** (≤ 80 chars):
```
Explainable AI copilot for 2026 F1 hybrid energy strategy.
```
(58 characters)

**Use this version when the field allows more** (≤ 140 chars):
```
An explainable AI race-strategy copilot for the 2026 F1 hybrid energy era — telemetry reasoning, regulation grounding, what-if analysis.
```
(135 characters)

**Use this version on social cards / Open Graph** (≤ 200 chars):
```
OVERRIDE — explainable AI for 2026 F1 hybrid energy decisions. Telemetry reasoning + FIA regulation grounding + what-if analysis. Decision support, never replacement. Built on IBM Granite + watsonx.ai.
```
(199 characters)

---

## 3. One-sentence pitch (portal field: **Summary** / **Elevator pitch** / **Description (short)**)

```
OVERRIDE is an explainable AI race-strategy copilot that helps teams and fans understand 2026 hybrid energy decisions through telemetry reasoning, regulation grounding, and what-if analysis.
```

> This is the **locked positioning sentence** from `docs/00-thesis.md` line 3. Do not edit; every prior doc references it verbatim.

---

## 4. Problem statement (portal field: **Problem** / **Why does this matter?** — typically 1–3 paragraphs)

```
In 2026, Formula 1 entered the deepest technical regulation reset in a decade. The combustion engine drops to roughly half of total output. The MGU-K triples in power to 350 kW. The MGU-H — the single most efficient recovery path of the previous era — is gone. DRS is replaced by Override Mode, deployable anywhere within a one-second gap. Active aerodynamics moves between Z-Mode and X-Mode. Sustainable fuel changes engine behavior under load.

For race engineers, every lap is now an energy management decision: where to harvest, where to deploy, when to trigger Override, when to accept a slower exit to refill the pack. The search space for a coherent energy plan has exploded. For broadcasters and fans, the spectacle is harder to follow — entire chess matches now hide inside the energy budget.

The publicly visible AI in this space — AWS F1 Insights, Oracle's Red Bull strategy stack, IBM's own Ferrari fan app — was built for the 2014–2025 hybrid rules. None reason explicitly over the 2026 regulations. None ship as open source. None let a user run a what-if against a session they brought themselves. There is no open, explainable tool for the 2026 era. That is the gap OVERRIDE is built into.
```

---

## 5. Solution statement (portal field: **Solution** / **What it does**)

```
OVERRIDE is a copilot, not a strategist. It takes a session replay — TORCS Lab simulator capture, FastF1 historical, or a live drive in the bundled IBM SkillsBuild TORCS container — aggregates lap-level energy features, detects inefficient deployment zones, then explains each one with a verbatim citation from the 2026 FIA technical regulations parsed by Docling.

Two modes:
• Engineer Mode — full reasoning chains, regulation citations, validator + Guardian safety scores, what-if exploration.
• Fan Mode — same intelligence, plain language, no acronyms.

What-if simulation (FR-8). For any detected zone, the engineer can ask: what if I delay my first deploy by N laps? What if I skip this harvest opportunity entirely? What if I extend the next Override by one lap? OVERRIDE re-runs the full pipeline against the perturbed session and renders a side-by-side Before / After diff — same reasoning, same Guardian gate, same regulation citation against the alternate strategy. The cache is keyed by a deterministic hash of the request, so the same exploration is cheap to revisit.

Two-pass safety architecture:
• Pass 1 — deterministic validation of citation-existence (verbatim match), banned-language filter, and section-consistency rules.
• Pass 2 — Granite Guardian 3-8b classifier scoring two custom criteria: energy_safety and regulation_consistency. Below 0.7 triggers regeneration with a stricter prompt; up to 2 retries, then ships with `final_confidence: low` and a "Treat as exploratory" banner.

When the system catches itself shipping a malformed recommendation, the rejection is shown to the user — that is the layered defense story, not a hidden detail.

Every output is grounded in the actual FIA Issue 18 technical regulations (parsed at runtime by Docling, stored as a 384-chunk vector index, retrieved via Granite Embedding 278m). Article numbers are never hardcoded — they are read from the source PDF and rendered dynamically. When the regulations change mid-season (the FIA already issued multiple Issues in 2026), only the chunks file is regenerated. Code does not move.

Decision support, never replacement. The engineer is always the decision-maker.
```

---

## 6. How to try it (portal field: **How to use** / **Get started** / **Demo**)

```
Quick start with Podman compose (the shipping shape) — ~2 minutes after credentials are set:

1. Clone the repo. Copy .env.example to .env and fill in your watsonx.ai credentials (WATSONX_API_KEY, WATSONX_PROJECT_ID, WATSONX_URL). The IBM SkillsBuild challenge provides Essentials-tier access.
2. podman compose up         # one image, UI + API at http://localhost:8000

Three modes via profile flags:
• podman compose up                                — OVERRIDE alone (fixture-driven demo).
• podman compose --profile torcs up                — adds the IBM SkillsBuild TORCS lab container (drive in a browser at http://localhost:6080). First pull is ~10 GB and 10–15 min; subsequent runs are fast.
• podman compose --profile observability up        — adds Jaeger UI at http://localhost:16686. Set OVERRIDE_TRACING=otlp in .env to wire traces. Docker compose works equivalently.

Drop data/sessions/sample_torcs.json (or either real TORCS capture under data/samples/) onto the upload zone. The pipeline runs end-to-end in about 8 seconds. The recommendation card shows cause / consequence / recommendation with a verbatim FIA citation, plus validator and Guardian safety badges. Click any zone to explore counterfactuals (FR-8 what-if).

If running --profile torcs and driving the lab live, the upload page surfaces a "Live TORCS detected" banner with per-run "Ingest" buttons — one click pipes the JSONL through ingest/torcs_parser.py and lands a fresh session on the dashboard.

Local-venv path (for hacking on the code):
  python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
  .venv/bin/python scripts/test_watsonx.py    # G-1 gate
  .venv/bin/uvicorn api.main:app --reload --port 8000
  cd ui && npm install && npm run dev          # http://localhost:3000

Optional: route chat through the TORCS container's bundled Ollama (granite4:350m) by setting OVERRIDE_LLM_RUNTIME=ollama. Guardian + Embedding stay on watsonx; this is the v1.1 migration preview. See docs/adrs/ADR-003-llm-runtime-abstraction.md.

Full architecture, schema, and API documentation: docs/03-architecture.md, docs/04-schema.md, docs/04-api.md.
```

---

## 7. Tech stack (portal field: **Technologies** / **Tags** — usually multi-select chips)

Tag with these (combine ANDs as the portal allows):

**Required IBM Challenge tags (verify on portal):**
- IBM Granite
- IBM watsonx.ai
- Docling
- Langflow

**Models used (verbatim from `models.json`):**
- `ibm/granite-4-h-small` — reasoning + fan translation
- `ibm/granite-guardian-3-8b` — Pass-2 BYOC scoring
- `ibm/granite-embedding-278m-multilingual` — regulation retrieval (768-dim vectors)
- `ibm-granite/granite-timeseries-ttm-r2` — optional forecast (HuggingFace, local; not shipped in this submission per FR-3 graceful degradation)

**Other stack:**
- Python 3.12, FastAPI, Pydantic v2
- React 18 + TypeScript + Vite + Tailwind + Recharts
- OpenTelemetry + Jaeger (profile-gated in compose)
- Podman / Docker compose — multi-stage Node-20 → Python-3.12 image, three services, two profiles (`torcs`, `observability`)
- IBM SkillsBuild TORCS lab container — bundled as a profile-gated compose service for live driving; gym_torcs source committed under `RaceYourCode/` for one-clone reproducibility
- Hybrid LLM runtime: `OVERRIDE_LLM_RUNTIME=watsonx` (default) routes chat to watsonx.ai; `=ollama` routes to the lab container's bundled `granite4:350m` for the v1.1 migration preview (ADR-003)
- pytest (301 unit tests + 4 network integration tests = 305 green)

**Categories** (verify what BeMyApp offers — likely):
- Sports & Racing / Sports analytics
- Explainable AI
- AI for Good (decision support, transparency)
- Open source

---

## 8. Team (portal field: **Team** / **Contributors**)

```
Patrick Ejelle-Ndille — Solo founder & lead engineer.
Email: patrick@broadcomms.net
Submission to the IBM SkillsBuild AI Builders Challenge, May 2026 cohort.
Built solo over 23 days. Development accelerated using IBM Bob.
```

> Edit team list per actual contributor count if collaborators added before submission.

---

## 9. Demo links (portal fields: **Demo video** / **Live demo URL** / **Repository**)

| Field | Value |
|---|---|
| Demo video (YouTube unlisted) | `<PASTE_YOUTUBE_URL_HERE>` — verify it plays in incognito tab before publishing |
| GitHub repository | `<PASTE_GITHUB_URL_HERE>` |
| Live demo (hosted via Cloudflare Tunnel) | `https://override.patrickndille.com` — public, fixture-driven demo path. Description note: "Ephemeral hosted demo for the IBM SkillsBuild judging window only (May 27 – May 31, 2026); routes revoked post-May-31. Fronted by a Cloudflare Tunnel from local WSL; same compose stack as the local-clone path. For the live TORCS drive affordance, judges can request access at `torcs.patrickndille.com` (Cloudflare Access — one-time PIN to a whitelisted email). The Jaeger trace UI at `jaeger.patrickndille.com` is similarly gated. See `docs/07-deployment.md` for the full posture." If the hosted URL is unavailable mid-judging, the README's `podman compose up` path is the canonical fallback (rubric story is unchanged). |

> Replace placeholders during the T-2h step in `final-lock-checklist.md`. The hosted URL above is the v6-plan-amended Cloudflare Tunnel target (post-pre-flight pivot from the original Hetzner CX32 VM plan — see `docs/07-deployment.md` §1 for the history). If the Tunnel route is dropped before T-2h, swap the row to "OVERRIDE runs locally — see README; use the YouTube link as the primary demo asset" and the architectural promise is unaffected (cuts list item #4 fallback).

---

## 10. License (portal field: **License**)

```
Apache 2.0
```

License text in `LICENSE` at repo root. All code original. Brand assets (logo, icon, banner) created by an independent designer per the brief in `docs/logo-design-brief.md`; usage rights apply per the standard BeMyApp submission terms.

---

## 11. Acknowledgments (portal field: **Acknowledgements** / **Credits** — usually optional but improves judging signal)

```
Built for the IBM SkillsBuild AI Builders Challenge, May 2026, organized by BeMyApp. Development accelerated using IBM Bob. Foundation laid by the IBM TORCS Learning Lab simulator. Grounded in IBM Granite 4.x Instruct, Granite Guardian 3-8b, Granite Embedding 278m-multilingual, with Docling for FIA regulation extraction and Langflow for the visual design canvas.

`RaceYourCode/gym_torcs/*` derives from Gym-TORCS (https://github.com/ugo-nama-kun/gym_torcs — MIT-licensed, © 2016 Naoto Yoshida), bundled via the IBM SkillsBuild hands-on-labs/01_torcs_lab distribution. Original LICENSE preserved at `RaceYourCode/gym_torcs/LICENSE`.

All visuals original. No F1 broadcast footage, no team livery, no FIA trademark imagery. Regulations parsed from the publicly published 2026 FIA Formula 1 Technical Regulations (Section C, Issue 18, dated 2026-05-07).

Not affiliated with Formula 1, the FIA, or any team. Open-source educational/research project.
```

---

## 12. Banner & logo (portal fields: **Banner image** / **Logo** / **Cover image**)

| Field | Source file | Spec |
|---|---|---|
| Banner / cover image | `assets/banner.png` | 1920×600 (verify portal accepts; resize to portal spec if asked) |
| Square logo | `assets/logo-icon.png` | 2048×2048 — portal will downscale |
| Wordmark | `assets/logo.png` | 4800×1600 — only if portal asks for "long" logo |
| Open Graph preview | `assets/brand/logo-on-dark.png` | for social sharing if portal generates OG metadata |

---

## 13. Final pre-publish read

Before clicking PUBLISH, read EVERY field above one more time on the portal **preview page** (not the editor). Common bugs caught here:

- HTML/markdown escaping issues (`&amp;` instead of `&`, broken hyphens)
- Smart-quote vs. straight-quote inconsistencies
- Numbers that drifted (e.g., "8 second pipeline" should be "8.2 second pipeline")
- Acronyms not expanded on first use ("FIA" expanded to "Fédération Internationale de l'Automobile" once if the portal audience may not know it; otherwise "FIA" is fine)

If you find a typo, fix it ONCE in this doc, then re-paste — never edit on the portal alone (you lose the change for future submissions / re-submits).

---

## Field-mapping cheat sheet

If the BeMyApp portal has unusual field names, here's the mapping:

| Portal might say | Use section |
|---|---|
| "Project Name" / "Title" / "Headline" | §1 |
| "Tagline" / "Subtitle" / "One-liner" | §2 (pick length variant) |
| "Summary" / "Description (short)" / "Elevator pitch" | §3 |
| "Problem" / "Background" / "Why does this matter" / "Challenge" | §4 |
| "Solution" / "What it does" / "Description (long)" / "How does it solve the problem" | §5 |
| "Get started" / "How to use" / "Try it" / "Demo instructions" | §6 |
| "Technologies" / "Stack" / "Tools" / "Tags" | §7 |
| "Team" / "Contributors" / "Author" | §8 |
| "Video" / "Demo video" / "Pitch video" | §9 (YouTube unlisted) |
| "Repository" / "Source code" / "GitHub" | §9 |
| "License" / "Open source license" | §10 |
| "Acknowledgements" / "Credits" / "Built with" | §11 |
| "Banner" / "Cover" / "Hero image" | §12 |
| "Logo" / "Icon" | §12 |

---

## Prepared statements for follow-up Q&A (judges DM, Discord, organizer email)

If a judge or organizer asks any of these post-submission, here are the pre-approved one-liners:

| Question | Answer |
|---|---|
| "Why didn't you ship TTM-R2 forecasting?" | "TTM-R2 is documented as optional in the FR-3 graceful degradation guarantee. The pipeline runs end-to-end without it. Sessions that lack a forecast lower their reported confidence accordingly. Shipping it would have added ~5 hours of build time without changing the explainability story, which is the rubric-relevant feature." |
| "Why FastAPI runtime, not Langflow?" | "Langflow is the design + demo layer. Production runtime is FastAPI for performance, type safety (Pydantic v2 throughout), and observability. Langflow visually documents the architecture and powers the demo recording; it does not gate the production code path. See ADR-001." |
| "Where's the test data from?" | "Three lanes, all reproducible: (1) Synthetic TORCS-shaped JSON committed in `data/sessions/sample_torcs.json` (deterministic, 5 laps, fires `low-roi-deploy`); (2) Real TORCS-lab captures emitted by the bundled telemetry logger, committed under `data/samples/torcs_baseline.jsonl` (median harvest ≈ 3.8 MJ/lap — in-budget reference) and `torcs_modified.jsonl` (median ≈ 9.3 MJ/lap — over the 8.5 MJ cap, exercises the harvest_cap validator rule organically); (3) FastF1 historical replays from public sources. No live team telemetry. No broadcast video. No proprietary feeds." |
| "Do you support live driving?" | "Yes — `podman compose --profile torcs up` boots the IBM SkillsBuild TORCS lab container alongside OVERRIDE. Drive in a browser via noVNC at :6080; the bundled telemetry logger writes JSONL into a shared volume; the UI surfaces a 'Live TORCS detected' banner with one-click ingest via `POST /api/sessions/torcs-live`. The pipeline (ingest → reasoning → Guardian → grounding) runs against the captured laps the same way it runs against pre-recorded fixtures. The demo video uses fixtures for determinism; the live path is for judges exploring the cloned repo." |
| "How do you handle regulations changing?" | "We never hardcode article numbers. The validator's `citation_existence` rule requires the cited passage to appear character-for-character in the source chunk. When the FIA ships a new Issue, only `data/regs/extracted_chunks.json` regenerates via `scripts/build_chunks.py`. Code doesn't move." |
| "What's the safety story?" | "Two-pass: deterministic Pass-1 (5 rule classes including verbatim citation existence + banned-language filter) plus Granite Guardian Pass-2 (two BYOC criteria: energy_safety and regulation_consistency). Below threshold triggers regeneration; after retries exhausted, ships with `final_confidence: low` plus a 'Treat as exploratory' banner. The layered defense rejection card is a demo asset, not a hidden failure mode." |
| "What's the cost per session?" | "On watsonx.ai Essentials tier, ~$0.05 per session for the full 5-zone pipeline including Pass-2 retries and Fan translation. Verified end-to-end at 8.2 seconds for a single zone in the live Langflow demo." |
| "Why no live data feed?" | "Live trackside inference would require licensed F1 data we don't have. Replay-first makes the system deterministic, demoable, and honest about what it is — a strategy exploration tool, not a production race-control system. Per the IBM SkillsBuild challenge guidance: decision support, not replacement." |
