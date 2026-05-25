# OVERRIDE - BeMyApp Portal Copy

> Final text for every BeMyApp submission portal field.
>
> Source-of-truth for positioning: `docs/00-thesis.md` line 3 (the locked sentence).
> Source-of-truth for product story: `README.md` opening + `docs/00-abstract-override.md` shot-list.
> Source-of-truth for technical detail: `docs/03-architecture.md`, `docs/04-api.md`, `docs/05-security.md`.
>
> Every figure here is verified against `docs/plans/qa-results.md`. If you change a number in this doc, change it in `qa-results.md` too.

---

## 1. Project name (portal field: **Name** / **Project Title**)

```
OVERRIDE
```

> All-caps; one word; no tagline appended. The wordmark in `assets/logo.png` matches.

---

## 2. Short tagline (portal field: **Subtitle** / **Tagline** — typically ≤ 80–100 chars)

**Tagline** (≤ 25 chars):
```
AI race strategy Copilot
```


**Project Description** (≤ 100 chars):
```
Explainable strategy intelligence copilot that helps teams & fans understand hybrid energy decision.
```


**Social cards / Open Graph / Youtube Video Description** (≤ 200 chars):
```
OVERRIDE - explainable AI for 2026 F1 hybrid energy decisions. Telemetry reasoning + FIA regulation grounding + counterfactual strategy review. Decision support, never replacement. Built on IBM Granite + watsonx.ai.
```


---

## 3. One-sentence pitch (portal field: **Summary** / **Elevator pitch** / **Description (short)**)

```
OVERRIDE is an explainable AI race-strategy copilot that helps teams and fans understand 2026 hybrid energy decisions through telemetry reasoning, regulation grounding, and counterfactual strategy review.
```

> This is the **locked positioning sentence** from `docs/00-thesis.md` line 3. Do not edit; every prior doc references it verbatim.

---

## 4. Problem statement (portal field: **Problem** / **Why does this matter?** — typically 1–3 paragraphs)

```
In 2026, Formula 1 entered the deepest technical regulation reset in a decade. The combustion engine drops to roughly half of total output. The MGU-K triples in power to 350 kW. The MGU-H — the single most efficient recovery path of the previous era — is gone. DRS is replaced by Override Mode, deployable anywhere within a one-second gap. Active aerodynamics moves between Z-Mode and X-Mode. Sustainable fuel changes engine behavior under load.

For race engineers, every lap is now an energy management decision: where to harvest, where to deploy, when to trigger Override, when to accept a slower exit to refill the pack. The search space for a coherent energy plan has exploded. For broadcasters and fans, energy-budget decisions are invisible on broadcast but measurable in telemetry.

Most public racing AI surfaces metrics or runs as closed team tooling. Those systems can be useful, but they rarely give users an open, auditable way to reason over 2026 hybrid-energy telemetry, dynamic regulation grounding, and counterfactual strategy review in one place. That is the gap OVERRIDE is built into.
```

---

## 5. Solution statement (portal field: **Solution** / **What it does**)

```
OVERRIDE is a copilot, not a strategist. It takes a reproducible session export — TORCS Lab capture, committed sample fixture, FastF1-style replay export, or completed live TORCS capture — aggregates lap-level energy features, detects inefficient deployment zones, then explains each one with a verbatim citation from the 2026 FIA technical regulations parsed by Docling.

Two modes:
• Engineer Mode — full reasoning chains, regulation citations, validator + Guardian safety scores, and counterfactual strategy review.
• Fan Mode — same intelligence, plain language, no acronyms.

Counterfactual strategy review. For any detected zone, the engineer can ask: what if I delay my first deploy by N laps? What if I skip this harvest opportunity entirely? What if I extend the next Override by one lap? OVERRIDE re-runs the full pipeline against the perturbed session and renders a side-by-side Before / After diff — same reasoning, same Guardian gate, same regulation citation against the alternate strategy. The cache is keyed by a deterministic hash of the request, so the same exploration is cheap to revisit.

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
Quick start with podman-compose — ~2 minutes after credentials are set:

1. Clone the repo. Copy .env.example to .env and fill in your watsonx.ai credentials (WATSONX_API_KEY, WATSONX_PROJECT_ID, WATSONX_URL).
2. podman-compose up         # UI + API at http://localhost:8000

Optional services:
• podman-compose up override torcs       — adds the IBM SkillsBuild TORCS lab container for live driving at http://localhost:6080.
• podman-compose up override jaeger      — adds Jaeger at http://localhost:16686 when OVERRIDE_TRACING=otlp is enabled.
• podman-compose up override langflow    — adds the Langflow design canvas at http://localhost:7860.

Drop data/sessions/sample_torcs.json, or either real TORCS capture under data/samples/, onto the upload zone. The pipeline runs end-to-end in about 8 seconds. The recommendation card shows cause, consequence, recommendation, a dynamic FIA citation, validator status, and Guardian safety score. Use counterfactual strategy review to rerun the same safety path against an alternate energy choice.

If running podman-compose up override torcs and driving the lab live, the upload page surfaces a "Live TORCS detected" banner with per-run "Ingest" buttons. One click pipes the JSONL through ingest/torcs_parser.py and lands a fresh session on the dashboard.

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
- `ibm-granite/granite-timeseries-ttm-r2` - optional forecast through an isolated Docker service; graceful degradation keeps the pipeline running without it

**Other stack:**
- Python 3.12, FastAPI, Pydantic v2
- React 18 + TypeScript + Vite + Tailwind + Recharts
- OpenTelemetry + Jaeger (profile-gated in compose)
- Podman / Docker compose — multi-stage Node-20 → Python-3.12 image, three services, two profiles (`torcs`, `observability`)
- IBM SkillsBuild TORCS lab container — bundled as a profile-gated compose service for live driving; gym_torcs source committed under `RaceYourCode/` for one-clone reproducibility
- pytest collection: 439 tests (435 local + 4 network-marked)

**Categories**:
- Sports & Racing / Sports analytics
- Explainable AI
- AI for Good (decision support, transparency)
- Open source

---

## 8. Team (portal field: **Team** / **Contributors**)

```
Patrick Ejelle-Ndille — Founder, architect, and lead engineer.
Email: patrick@broadcomms.net
Submission to the IBM SkillsBuild AI Builders Challenge, May 2026 cohort.
Designed and built end-to-end by Patrick Ejelle-Ndille.
Development accelerated using IBM Bob.
```

## 9. Demo links (portal fields: **Demo video** / **Live demo URL** / **Repository**)

| Field | Value |
|---|---|
| Demo video | `https://override-video.patrickndille.com` - stable forwarding link for the completed 3-minute submission video |
| GitHub repository | `https://github.com/broadcomms/override-may-2026` |
| Live demo | `https://override.patrickndille.com` - hosted review environment for the submitted project. For live TORCS driving, clone the repo and run `podman-compose up override torcs` locally. |

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
| Banner / cover image | `assets/banner.png` | 1920×600 |
| Square logo | `assets/logo-icon.png` | 2048×2048 — portal will downscale |
| Wordmark | `assets/logo.png` | 4800×1600 — only if portal asks for "long" logo |
| Open Graph preview | `assets/brand/logo-on-dark.png` | for social sharing if portal generates OG metadata |

---

## Reviewer Q&A

If a judge or organizer asks any of these post-submission, here are the pre-approved one-liners:

| Question | Answer |
|---|---|
| "Why is TTM-R2 optional?" | "TTM-R2 enhances the debrief with a 5-lap state-of-charge forecast, but it is not required for the core demo. OVERRIDE is designed to degrade gracefully: when the isolated TTM-R2 service is unavailable or a session has fewer than 30 completed laps, the pipeline continues from observed telemetry with `forecast=None`. That keeps the explanation, regulation grounding, validation, Guardian scoring, Fan Mode, and counterfactual strategy review available." |
| "Why FastAPI runtime, not Langflow?" | "Langflow is the design + demo layer. Production runtime is FastAPI for performance, type safety (Pydantic v2 throughout), and observability. Langflow visually documents the architecture and powers the demo recording; it does not gate the production code path. See ADR-001." |
| "Where's the test data from?" | "Three lanes, all reproducible: (1) Synthetic TORCS-shaped JSON committed in `data/sessions/sample_torcs.json` (deterministic, 5 laps, fires `low-roi-deploy`); (2) Real TORCS-lab captures emitted by the bundled telemetry logger, committed under `data/samples/torcs_baseline.jsonl` (median harvest ≈ 3.8 MJ/lap — in-budget reference) and `torcs_modified.jsonl` (median ≈ 9.3 MJ/lap — over the 8.5 MJ cap, exercises the harvest_cap validator rule organically); (3) FastF1 historical replays from public sources. No live team telemetry. No broadcast video. No proprietary feeds." |
| "Do you support live driving?" | "Yes — `podman-compose up override torcs` boots the IBM SkillsBuild TORCS lab container alongside OVERRIDE. Drive in a browser via noVNC at :6080; the bundled telemetry logger writes JSONL into a shared volume; the UI surfaces a 'Live TORCS detected' banner with one-click ingest via `POST /api/sessions/torcs-live`. The pipeline (ingest → reasoning → Guardian → grounding) runs against the captured laps the same way it runs against pre-recorded fixtures. The demo video uses fixtures for determinism; the live path is for judges exploring the cloned repo." |
| "How do you handle regulations changing?" | "We never hardcode article numbers. The validator's `citation_existence` rule requires the cited passage to appear character-for-character in the source chunk. When the FIA ships a new Issue, only `data/regs/extracted_chunks.json` regenerates via `scripts/build_chunks.py`. Code doesn't move." |
| "What's the safety story?" | "Two-pass: deterministic Pass-1 (5 rule classes including verbatim citation existence + banned-language filter) plus Granite Guardian Pass-2 (two BYOC criteria: energy_safety and regulation_consistency). Below threshold triggers regeneration; after retries exhausted, ships with `final_confidence: low` plus a 'Treat as exploratory' banner. The layered defense rejection card is a demo asset, not a hidden failure mode." |
| "Why no live data feed?" | "Live trackside inference would require licensed F1 data we don't have. Replay-first makes the system deterministic, demoable, and honest about what it is — a strategy exploration tool, not a production race-control system. Per the IBM SkillsBuild challenge guidance: decision support, not replacement." |
