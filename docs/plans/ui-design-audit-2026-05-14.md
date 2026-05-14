# UI design audit + modernization plan — 2026-05-14

> **Audience:** the architect (review + approve), then the coder (implement).
> **Author hat:** designer. The brief was *"redesign how we present the layout so OVERRIDE feels premium, strategic, credible — without faking it."*
> **Source of the audit:** the Upload page screenshot supplied 2026-05-14, plus every UI source file under `ui/src/` and the in-flight design spec at [`docs/04-ui-ux-design.md`](../04-ui-ux-design.md).
> **Lifecycle:** delete this file in the same PR that ships the last accepted change. Per `.bob/rules.md`.
> **Submission ceiling:** May 27–28 target. Don't propose anything that takes longer than the slack remaining in [`overide-complete-plan-to-submission.md`](./overide-complete-plan-to-submission.md). Hour budget claimed below ~ **14 h**, sized to fit Week-3 polish.

---

## 0. The verdict in one paragraph

OVERRIDE's pipeline is engineer-grade — the entry page is not. The Upload screen reads as four functional modules stacked at equal weight (drop zone, sample replays, race control, live-TORCS list), each in the same hairline-bordered card, in a single 672px-wide column on a 1900px-wide canvas. Premium is not a coat of paint — it is **restraint and hierarchy**. The dashed dropzone shouts at the viewer; the engineer-bait (sample replays) is a row of unstyled pills; the credibility line ("Decision support, never replacement. Built on IBM watsonx.ai.") is in 12px muted grey at the bottom of the page below an empty black rectangle. The page is *full* but says *nothing*. The fix is to re-frame the chrome (header → workspace → footer), promote what matters (samples + credibility + a peek at the actual product), demote what doesn't (the noVNC iframe lives on its own surface, not on the landing page), and unify the visual language so the eye can find the action in under a second.

---

## 1. Scope of this audit

| In scope | Out of scope |
|---|---|
| `UploadPage` (the screenshot — the entry surface) | Backend APIs, schemas, model choices |
| `SessionPage` (the destination — where the value is delivered) | Re-wiring `core/`, `analysis/`, `ingest/` |
| `SessionsPage` (history list) | Adding TTM-R2 (still a v1.1 stub per the graceful-degradation guardrail) |
| `SiteHeader` / `SiteFooter` / chrome | New API routes |
| Design tokens (palette, type, spacing, motion) | Mobile-first redesign (desktop-first per PRD §6) |
| Data viz on the session detail page | The Langflow canvas (separate surface) |
| Brand wordmark + favicon polish | The two-pass safety architecture (already correct — only how we *render* it changes) |

Anything that requires changes to `docs/04-schema.md` or `docs/04-api.md` is called out explicitly and gated behind "needs architect sign-off."

---

## 2. What I read before drafting

| File | What it told me |
|---|---|
| [`docs/00-thesis.md`](../00-thesis.md) | The product is *explainability-as-product*. The visual language must prove it. |
| [`docs/02-problem.md`](../02-problem.md) | Not on disk — referenced in `03-prd.md` §2. |
| [`docs/03-architecture.md`](../03-architecture.md) | Pipeline is shipped. UI is the last 14h of polish budget. |
| [`docs/03-prd.md`](../03-prd.md) | Three audiences sharing one backend (engineer / analyst / fan). Two render surfaces (Engineer + Fan). |
| [`docs/04-ui-ux-design.md`](../04-ui-ux-design.md) | The wireframes are correct but conservative. I will propose enhancements, not contradictions. |
| [`docs/04-api.md`](../04-api.md) | The `/upload` page is fed by `/api/torcs-status` (with pagination), `/api/sessions`, `/api/torcs/control-status`. Nothing on the entry page demands more endpoints. |
| [`ui/src/styles/tokens.css`](../../ui/src/styles/tokens.css) | Tokens already mirror the spec. They are correct as values; the issue is *application*, not definition. |
| [`ui/src/pages/UploadPage.tsx`](../../ui/src/pages/UploadPage.tsx) | The screenshot's source. Confirms my critique below. |
| [`ui/src/pages/SessionPage.tsx`](../../ui/src/pages/SessionPage.tsx) | Three stacked viz blocks; no KPI strip; footer-buried regulation source. |
| [`ui/src/components/FileUpload.tsx`](../../ui/src/components/FileUpload.tsx) | Dashed 2px border, p-12, big arrow — the loudest element on a page where it shouldn't be. |
| [`ui/src/components/TorcsControlPanel.tsx`](../../ui/src/components/TorcsControlPanel.tsx) | A 437-line all-in-one that mixes start/stop control with the live noVNC iframe. |
| [`ui/src/components/RecommendationCard.tsx`](../../ui/src/components/RecommendationCard.tsx) | Card layout is correct per `04-ui-ux-design.md` §4.3. Only minor refinement needed. |
| [`ui/src/components/EnergyCurve.tsx`](../../ui/src/components/EnergyCurve.tsx) | One-line SoC chart. Functional. Underspends the available real estate and the available data. |
| [`ui/src/components/ZoneHeatmap.tsx`](../../ui/src/components/ZoneHeatmap.tsx) | 6px-wide cells, 3px gutter. Reads as decoration, not signal. |

I did **not** read the Langflow canvas, the regulation PDFs, or the test suite — they're upstream of the visual layer and out of scope.

---

## 3. Five named problems on the Upload page (with evidence)

### P1. Equal-weight stack, no hierarchy
Four affordances in a single centered column at `max-w-xl` (672px) on a 1900px canvas:
- Drop zone → [`FileUpload.tsx:30-77`](../../ui/src/components/FileUpload.tsx#L30)
- Sample replay chips → [`FileUpload.tsx:88-105`](../../ui/src/components/FileUpload.tsx#L88)
- Race Control card → [`TorcsControlPanel.tsx:230-431`](../../ui/src/components/TorcsControlPanel.tsx#L230)
- Live TORCS detected card → [`UploadPage.tsx:187-279`](../../ui/src/pages/UploadPage.tsx#L187)

All use the same recipe (`rounded-card border border-… bg-surface/60 p-4`). The eye has no landmark.

**Cost:** the viewer can't tell where to start. For 70% of judges and reviewers, the right first action is **try a sample replay** — but the dashed dropzone above it eats the eye first.

### P2. The dashed dropzone is the loudest element on the page
[`FileUpload.tsx:42`](../../ui/src/components/FileUpload.tsx#L42) — `border-2 border-dashed p-12 text-center` with a big `⤓` glyph at 24px. This is the 2018 SaaS file-upload pattern. For our user mix it is wrong-priority — most reviewers will not upload a file at all in their first session.

### P3. The Race Control panel is doing four jobs in one box
[`TorcsControlPanel.tsx:230-431`](../../ui/src/components/TorcsControlPanel.tsx#L230) carries: status badge + track dropdown + lap input + headless checkbox + manual-setup details + Start/Stop buttons + a TORCS view label + Fullscreen button + a **16:9 noVNC iframe** (which on a fresh page load is a black rectangle until TORCS boots ~90s later).

The black rectangle in the screenshot? That's the iframe before TORCS is alive. It is **the largest visual on the page** and it carries **zero information** at that moment. That is the bug — silence shouting at us.

### P4. The 0.4 alpha + hairline border treatment makes everything feel sketched
`border-accent/40 bg-surface/60` on the Race Control card (`TorcsControlPanel.tsx:232`) + `border-accent/40 bg-surface/60` on the Live TORCS card (`UploadPage.tsx:189`) + `border-border bg-surface/40` on the active-race banner (`SessionPage.tsx:286`). Layered translucent borders against a near-black bg read as low-fi placeholders. Premium products commit: either *no* border (use gap + color), or a *solid* hairline at `--color-border` with no alpha.

### P5. The credibility line is buried
[`App.tsx:91-108`](../../ui/src/App.tsx#L91) — *"Decision support, never replacement. Built on IBM watsonx.ai. Repo ↗"* is in 12px `text-muted` below the fold. This is the **#1 differentiator** OVERRIDE has against AWS F1 Insights, Oracle, and IBM Ferrari. It should be at the **top** of the page, in the chrome, in a way that the first frame of any screenshot already tells the story.

---

## 4. Three named problems on the Session detail page

### S1. No KPI strip — the user reads every card to extract top-line numbers
[`SessionPage.tsx:243-394`](../../ui/src/pages/SessionPage.tsx#L243) goes header → curve → heatmap → recommendation list. A 47-lap Monza session has eight numbers the engineer wants in their first 2 seconds: total harvest MJ, total deploy MJ, lap-count, zone-count, validator pass-rate, Guardian average score, regulation issue, and inferred final SoC. None are shown above the fold.

### S2. The regulation source is in the footer
[`SessionPage.tsx:378-393`](../../ui/src/pages/SessionPage.tsx#L378). This is the load-bearing claim of the entire product ("we grounded this in the real FIA document"). It is visually equivalent to a copyright line. Premium move: promote it to the header, beside the session metadata, with the same gravity as `OVERRIDE · Monza · 47 laps`.

### S3. The energy curve underspends the available chart real estate
[`EnergyCurve.tsx`](../../ui/src/components/EnergyCurve.tsx) renders a 232px-tall single-line SoC chart with a forecast continuation and three zone-marker triangles. The data is much richer than this — `LapFeatures` carries harvest, deploy, fuel, lap-time, override usage. A premium telemetry chart layers two or three of those on the same time axis (think Bloomberg's price-volume splits, McLaren's strategist screens with SoC + harvest + deploy stacked).

---

## 5. Design principles for the redesign

Five rules. Every concrete proposal below is derivable from these.

1. **One hero per surface.** Each page (Upload, Session, Sessions) has *one* element that owns the eye on first frame. Everything else is secondary or tertiary.
2. **Restraint is the brand.** Orange (`--color-accent`) appears on the action you most want the user to take, and **nowhere else**. Currently it's on dropzone hover, sample chip hover, Race-Control border, Live-TORCS border, Ingest buttons, and active-state pills — that's six places without ranking. Spend it once per viewport.
3. **Numbers earn the mono font.** Lap counts, energy MJ, scores, latencies → `JetBrains Mono`. Prose (Cause / Consequence / Recommendation) → Inter. The current code mostly honors this; we'll formalize it as a token: `.font-num`.
4. **Cockpit chrome.** The header is a status strip (you-are-here, what-document-grounds-this, model versions) — not just a wordmark + two nav links. The footer is a credit line, not a placeholder for the brand promise.
5. **Show the destination on the entry.** The Upload page should peek at what the debrief looks like. Not screenshots — *real components* (e.g., a frozen sample-session sparkline + one citation card) below the fold. Linear, Stripe, and Vercel all do this on their entry pages. It makes the value tangible in 5 seconds.

---

## 6. Reference inspiration (and what we steal from each)

I am not proposing to copy any of these — only to triangulate the *feel*. Originals only per `00-thesis.md` §5.

| Reference | What we steal | What we leave |
|---|---|---|
| **Bloomberg Terminal** | Mono numerals dominate; one calm accent (Bloomberg amber → our override-orange); information density without noise | The dated chrome, the literal terminal aesthetic |
| **Linear** | Sharp typography, command-style affordances, restrained motion (120ms snap-out), clean borderless lists divided by hairlines | The colored-status-pill maximalism |
| **Vercel dashboard** | The hairline-on-dark surface treatment, the `bg-surface` → `bg-surface-2` step, the tight chrome | The marketing gradients (cheap on dark) |
| **Stripe / Plaid** | How they render tabular numerics, sparkline KPIs, and "trust" copy in the chrome | Branding-first treatment (we're a tool, not a SaaS landing) |
| **Polestar 2 / Porsche Taycan instrument cluster** | Segmented density (the cluster has 5–8 sub-zones, each visually distinct) without ornament; mono numerals at multiple scales | Skeuomorphic gauges, ambient glow |
| **McLaren Applied strategist screens** (publicly seen on broadcast) | Multi-pane stacked charts (SoC + harvest + deploy on shared time axis); zone-shaded sector boundaries; tabular lap data alongside the chart | We can't license proprietary chart styles — only the layout language is referenced |
| **F1 Manager 2024 UI** | The "strategy console" framing — split panels labelled with small all-caps wayfinding labels; restraint with the team color | The simulator/gamey textures |
| **TradingView / Grafana** | Sparkline KPI strips above the main chart; brush-zoom on time-series; dual-axis layering | The "every chart on one page" maximalism |
| **Apple's San Francisco display** (the typeface — we're using Inter, which was modeled on it) | Tight tabular figures (`font-feature-settings: "tnum"`) on every numeric column | — |

**Color discipline.** Orange is our "where to look" signal. We treat it like Bloomberg treats amber: present in exactly one place per viewport, signalling the primary action or the live moment. We currently spend it on hover-fill, on the Live TORCS card border, on the Race Control card border, on the Ingest button, AND on the brand wordmark. That dilutes it. Audit below.

---

## 7. Information architecture proposal

No new pages. No new routes. Same three: `/upload`, `/sessions`, `/session/:id`. What changes is the **role each surface plays** and the **density per viewport**.

### Current IA (rendered)
```
HEADER:   [OVERRIDE]                                        [Upload] [Sessions]
─────────────────────────────────────────────────────────────────────────────
BODY:     [           empty space — 30% of viewport          ]
          [   1 ▸ "Drop a session replay to begin" hero       ]
          [   2 ▸ Dashed drop zone (LOUD)                      ]
          [   3 ▸ Sample replay pills                          ]
          [   4 ▸ Race Control card (~600px tall)              ]
          [   5 ▸ Live TORCS card                              ]
─────────────────────────────────────────────────────────────────────────────
FOOTER:   Decision support, never replacement. · IBM watsonx.ai · Repo ↗
```

### Proposed IA
```
HEADER:   [◐ OVERRIDE]   Decision support, never replacement.   ●●● [Upload | Sessions | Docs]
          ──────────────────────────────────────────────────────────────────────────
SUBHEAD:  Explainable AI race-strategy copilot · grounded in FIA <issue> · watsonx.ai
─────────────────────────────────────────────────────────────────────────────
BODY (two-pane, wide screens; stacks below 1023px):

  LEFT 60%                                  RIGHT 40%
  ┌──────────────────────────────┐  ┌──────────────────────────┐
  │ "Begin"                      │  │ "Live capture" (only if   │
  │                              │  │  available — progressive   │
  │  [ ▸ Sample debrief (hero)  ]│  │  enhancement)              │
  │  [ ▸ TORCS engineer demo    ]│  │                            │
  │  [ ▸ Layered-defense demo   ]│  │  Race control (collapsed)  │
  │  ──────────────────────────  │  │   [Start race ▸]           │
  │  Bring your own:             │  │   ▸ Manual setup           │
  │  [ Drop a replay or browse ] │  │                            │
  │  Supported · 25MB · 120 laps │  │  Captures on disk (3):     │
  │                              │  │   • baseline-1lap [Open ▸] │
  │                              │  │   • run_…181 [Ingest ▸]    │
  │                              │  │   • s_torcs_…069 [Ingest ▸]│
  └──────────────────────────────┘  └──────────────────────────┘

  Below the fold: "What you'll see" preview strip — one
  energy-curve sparkline + one frozen citation card, real
  components, from a shipped fixture.

─────────────────────────────────────────────────────────────────────────────
FOOTER:   © OVERRIDE · MIT · Apache 2.0 · Built for IBM SkillsBuild May 2026
```

**Why this works.**
- The **hero is now Sample Debrief** — the path of least resistance to seeing value, for the audience (judges) most likely to be on this page.
- **Drop zone is demoted** to *"Bring your own"* secondary action — same data path, lower visual weight.
- **Race Control collapses by default** with a single primary button; the noVNC iframe moves to a disclosure or a dedicated `/race` overlay (see §10).
- The **credibility line is in the chrome**, not the footer.
- **The viewer sees, in the first frame**, a) what the product does (subhead), b) which document grounds it (subhead), c) the recommended first action (hero), d) live-mode optionally (right pane). No vertical scroll required.

### Session detail proposal (current vs proposed)
```
CURRENT
─────────────────────────────────────────────────────────────────────────────
[OVERRIDE · Monza · 47 laps · uploaded 2026-05-12]               [E | F]
                                  Energy Curve  (232px)
                                  Zone Heatmap   (~80px)
                                  Recommendations
                                    [Card 1]
                                    [Card 2]
                                    [Card 3]
Grounded in <doc>, <issue> · § <section>  ↗

PROPOSED
─────────────────────────────────────────────────────────────────────────────
HEADER:   OVERRIDE · Monza · 47 laps · uploaded 2026-05-12        [E | F]
KPI BAR:  Σ Harvest 198.4 MJ · Σ Deploy 192.1 MJ · 3 zones · 0 P1-fails
          AI safety avg 0.87 · final SoC 64% · grounded in <doc> § <section> ↗
─────────────────────────────────────────────────────────────────────────────
BODY:
  [ Energy curve (320px) — SoC line + harvest/deploy stacked area beneath
    + sector tinting + zone markers; brush bar for >60-lap sessions ]

  [ Zone strip (40px tall, full-width) — replaces the 3-row heatmap with
    a single timeline ribbon showing zone severity and override windows ]

  ─── Recommendations (3) ───────────────────────────────────────────────
  [ Card 1 — headline-first, metadata below, citation in a granite-blue
    side rail, badges + what-if rail in a sticky footer-row ]
  [ Card 2 … ]
  [ Card 3 … ]
─────────────────────────────────────────────────────────────────────────────
FOOTER:  Decision support, never replacement · model: granite-4-h-small · trace-id  ↗
```

The session footer changes role: it now carries the **build trust** signals (model id, request id for tracing). The regulation source moves up to the KPI bar because it's the *first* thing a skeptical engineer wants to verify.

---

## 8. Upload page — concrete layout

### 8.1 Wireframe (proposed)

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  ◐ OVERRIDE   Decision support, never replacement.    [Upload] [Sessions]   ║
║  Explainable AI race-strategy copilot · grounded in FIA · IBM watsonx.ai    ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  ┌─────────────────────────────────────────┐ ┌──────────────────────────┐  ║
║  │ BEGIN                                    │ │ LIVE CAPTURE              │  ║
║  │                                          │ │                           │  ║
║  │ ▸ Layered-defense demo            ◆     │ │ STATUS  ● Idle            │  ║
║  │   47 laps · 3 zones · cached            │ │                           │  ║
║  │ ─────────────────────────────────────── │ │ ▸ Start a TORCS race      │  ║
║  │ ▸ TORCS engineer demo                   │ │   Track  [aalborg     ▾]  │  ║
║  │   12 laps · 1 zone · sample             │ │   Laps   [    5         ] │  ║
║  │ ─────────────────────────────────────── │ │   [ Start race  ▸ ]       │  ║
║  │ ▸ Engineer happy-path demo              │ │                           │  ║
║  │   18 laps · 2 zones · sample            │ │ Captures on disk · 3      │  ║
║  │                                          │ │   baseline-1lap  Open ▸  │  ║
║  │ ─── Bring your own ──────────────────── │ │   run_…181       Ingest ▸ │  ║
║  │                                          │ │   s_torcs_…069   Ingest ▸ │  ║
║  │   [ Drop a .json/.parquet, or browse ]  │ │                           │  ║
║  │   ≤ 25 MB · ≤ 120 laps · TORCS·FastF1  │ │ ▸ Open cockpit view (noVNC)│  ║
║  └─────────────────────────────────────────┘ └──────────────────────────┘  ║
║                                                                              ║
║  ─── What you'll see ──────────────────────────────────────────────────── ║
║                                                                              ║
║  ┌───────────────────────────┐  ┌──────────────────────────────────────┐  ║
║  │                           │  │ "Battery used in a slow corner …"    │  ║
║  │  [ SoC sparkline (real)]  │  │  Cause / Consequence / Recommendation │  ║
║  │                           │  │  + citation + validator + Guardian   │  ║
║  └───────────────────────────┘  └──────────────────────────────────────┘  ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  © OVERRIDE · Apache 2.0 · IBM SkillsBuild AI Builders Challenge May 2026   ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

### 8.2 Notes

- **The hero "Begin" panel uses solid bg-surface with no border**. The accent (`--color-accent`) is reserved for the small `◆` glyph on the top-recommended sample, and the "Start race" button on the right pane. Two accent spends per viewport — that's the budget.
- **Sample list is row-style**, not pill-style. Each row shows label + metadata (lap count, zone count, badge: cached / sample). Clicking the row navigates. The first row carries the `◆` marker — that's the path we recommend.
- **The drop zone becomes a single-line "Bring your own"** affordance separated by an em-dash divider. No dashed border. No big arrow. One sentence, drop or click.
- **Live capture panel is a single column on the right**. No more 600px-tall race-control monolith. Track + laps inline; everything else collapsed behind disclosures.
- **NoVNC iframe is removed from this page.** Disclosure link → "Open cockpit view" routes to a new lightweight surface (or modal — TBD; see §15).
- **"What you'll see" preview strip** below the fold renders one real `EnergyCurve` (using a fixture session) and one frozen `RecommendationCard` (`Layered-defense demo` zone-1). This is the entire selling point: "this is what 30 seconds gets you."
- **Decision-support line is in the chrome.** Subhead under the wordmark in the header. Always visible. Becomes a screenshot-grade trust signal.

### 8.3 Wide vs narrow

| Breakpoint | Behavior |
|---|---|
| `≥ 1280px` | Two-pane (Begin / Live capture), preview strip below |
| `1024–1279px` | Two-pane, slightly narrower; preview strip stacks vertically |
| `768–1023px` | Single column: Begin → Live capture → preview strip |
| `< 768px` | Per `04-ui-ux-design.md` §9, density warning + functional single column |

---

## 9. Session detail page — concrete layout

### 9.1 KPI strip (new component)

A single row above the energy curve, full-width inside the existing `max-w-5xl` container. Eight tiles, mono numerals, hairline dividers between groups.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ HARVEST     DEPLOY      LAPS    ZONES   AI SAFETY   FINAL SoC   CITATION   │
│ 198.4 MJ ↑  192.1 MJ ↓  47      3 (1H) │ 0.87 ✓     64%         § 5.13.5 ↗ │
└─────────────────────────────────────────────────────────────────────────────┘
```

Each tile follows the same pattern: `text-[10px] uppercase tracking-wider text-muted` label above a `text-lg font-mono` value. Color treatment:
- Harvest: tinted `text-success` arrow on the value (gained energy).
- Deploy: tinted `text-warning` arrow (spent energy).
- AI Safety: tone follows the lowest score — `text-success` ≥0.85, `text-warning` 0.70–0.84, `text-danger` <0.70.
- Citation tile is **clickable** and opens the `RegulationSource.public_url`. This is the regulation-grounding promotion called out in S2.

### 9.2 Energy curve enhancements

Keep the existing Recharts component; add two layers:

1. **Harvest / deploy stacked area** beneath the SoC line, in `--color-success` and `--color-warning` tints at ~0.15 alpha. Existing data — no new API calls.
2. **Sector tinting** — vertical bands where a zone falls, in severity-tinted backgrounds at ~0.06 alpha. Removes the need for the standalone heatmap (see §9.3).
3. **Brush** for sessions > 60 laps — already an open item in `04-ui-ux-design.md` §13. Reuse Recharts `Brush` component.

Optional v1.1: hover crosshair showing all metrics at the cursor's lap.

### 9.3 Zone strip replaces the heatmap

The S1/S2/S3 × N-laps grid is hard to read at 6px-wide cells. Proposal: collapse it into a single **40px-tall ribbon** running the full width of the chart container, with severity-tinted segments and lap-number ticks. Click a segment → scroll to the matching recommendation card.

```
[█▒░░░░░░▒░░░█░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░]
 1                                              47
```

We keep the sector dimension by stacking three thin 12px rows inside the ribbon (S1 top, S2 middle, S3 bottom) — but as one perceptual unit instead of a table. This survives 60-lap sessions where the current grid breaks.

Alternative: keep the heatmap component but rescale cells to 12px × 16px so it reads. Architect decides.

### 9.4 Recommendation card refinement

Three small changes — no rebuild:

1. **Lead with the headline.** Today the card leads with `L23 · S2 · low-roi-deploy [medium severity]` (mono). Promote the Granite-generated single-sentence summary (currently in the body) to be the H3 above the metadata. The metadata becomes the sub-line.
2. **Citation in a side rail.** Today the citation is full-width below the reasoning. Move it to a 30%-width rail on the right (`md:` breakpoint and up), with the existing granite-blue left border + the verbatim passage + the source line. On narrow screens, it stacks below as today.
3. **Sticky footer of badges.** Validator / Guardian / Confidence chips become a **sticky** row at the card bottom that always reads, no matter how long the reasoning chain is when expanded. Same colors, same content.

### 9.5 Session header rewrite

```
OLD: OVERRIDE · Monza · 47 laps · uploaded 2026-05-12 14:31     [E | F]
NEW:
  OVERRIDE / Monza · 47 laps                                    [E | F]
  Uploaded 2026-05-12 14:31 · TORCS · session s_…a4f9 · trace-id ↗
```

Two-line header. Top line is the navigation; bottom line is the metadata. Adds a `trace-id` link so judges can click into the Jaeger trace (already wired per `docs/plans/p3.6-jaeger-trace-capture.md`).

---

## 10. The noVNC question

The embedded iframe on UploadPage is the single biggest cause of "cheap" perception. Three options. I recommend **(B)**.

| Option | What changes | Cost | Tradeoff |
|---|---|---|---|
| **A. Keep on UploadPage, behind a disclosure** | Wrap the existing iframe block in a `<details>` collapsed by default | 30 min | Easiest; the iframe still loads under the hood, just hidden |
| **B. ★ Move to its own surface (`/cockpit` or modal)** | New route `/cockpit` (or a modal triggered from `/upload`); the iframe lives there, with its own full-page treatment | ~2 h | Clean separation; the entry page becomes premium-feeling without losing the cockpit affordance |
| **C. Remove entirely; keep only start/stop** | Operators use a separate browser tab for the noVNC URL | 15 min | Cleanest; but loses the in-app integration the lab provides |

Option **B** keeps the integration narrative ("you can drive AND analyze in one app") while removing the visual noise from the entry. The cockpit surface can be opinionated: a full-bleed iframe, a thin status strip, a hard "Back to OVERRIDE" exit button, and that's it.

---

## 11. Component refinement — line by line

| Component | Today | Proposed | Why |
|---|---|---|---|
| `FileUpload` dropzone | dashed 2px border, `p-12`, big ⤓, "Drop a .json or .parquet file, or click to browse" | Solid 1px border, `p-6`, no arrow glyph, "Drop a replay, or browse" — one line | Hierarchy: dropzone is secondary, not the page hero |
| Sample chips | Pills with default border, all same weight | Rows with metadata (laps, zones, badge), top row marked with `◆` accent and "Recommended" caption | Promote the path we want judges to take |
| `TorcsControlPanel` | Single 437-line component with iframe inline | Split: `RaceControlCard` (start/stop + form) + `CockpitSurface` (the iframe, on its own route per §10) | Single responsibility per surface |
| Race control track dropdown | Generic `<select>` with optgroups | Same, but width-constrained and given a `font-mono` value display | Mono signals "this is a system identifier, not prose" |
| Status badge | `text-xs text-accent` "Idle / Launching / Live" | Same content, but with a 6px dot + label pattern (already used in `LiveTelemetry.tsx:92`) for consistency | Visual unity across surfaces |
| `RecommendationCard` header | Metadata-led (`L23 · S2 · low-roi-deploy [medium]`) | Headline-led (Granite one-liner) with metadata below | Card reads as a finding, not a key |
| `RecommendationCard` citation | Full-width below reasoning | Right rail (`md:` and up), stacks on narrow | Citation should always be visible — it's the trust signal |
| `RecommendationCard` badges | Inline in the footer | Sticky footer row, always visible | Validator + Guardian are the safety promise |
| `EnergyCurve` | SoC-only line | SoC line + harvest/deploy stacked area + sector tinting | Honest density; same data, more information per pixel |
| `ZoneHeatmap` | 6px × 28px cells, 3px gutter | Either: (a) collapse to 40px-tall full-width ribbon, OR (b) bump cells to 12px × 16px | Today's cells read as decoration, not signal |
| `LiveTelemetry` | OK as-is | Move newest-lap row to a "ticker" pattern: latest lap at the top, animated highlight on update | Live feel without breaking the layout |
| `SessionsPage` row | 12-column grid with checkbox | Same grid, but add a **type tag** to the second column: `[sample]` / `[upload]` / `[torcs-live]` so the demo session is unambiguous | Removes a confusion judges will have |
| Site header | Wordmark + 2 nav links | Wordmark + decision-support subhead + 2 nav links + subtle build/version chip on the right | Premium chrome: chrome carries trust signals |
| Site footer | "Decision support, … · IBM watsonx.ai · Repo ↗" | "© OVERRIDE · Apache 2.0 · IBM SkillsBuild May 2026" — the brand promise moves up | Footer is for credits, not the brand promise |

---

## 12. Token-level changes (tokens.css)

The palette is correct. Three additions, two adjustments. **No** changes to the published spec (`docs/04-ui-ux-design.md` §3) values — only *additions* and *clarifications*.

```css
:root {
  /* existing tokens stay */

  /* NEW — finer surface step for the KPI strip + premium row treatments */
  --color-surface-3: #181818;      /* between surface and surface-2; for hairline-row backgrounds */

  /* NEW — premium card variants */
  --shadow-card-hero: 0 0 0 1px var(--color-border), 0 1px 0 0 rgba(255,255,255,0.02) inset;
  /* the inset rim is what gives "instrument bezel" feel on dark — Polestar / Apple Watch pattern */

  /* NEW — chrome strip (header subhead) */
  --color-chrome-subhead: #B4B4B4;  /* between text-muted and text; reserved for the subhead line */

  /* CLARIFY — tabular figures default */
  /* applied to .font-mono and any .font-num utility */
}

/* NEW utility — tabular-num shortcut */
.font-num {
  font-family: var(--font-mono);
  font-feature-settings: "tnum" 1, "lnum" 1;
  font-variant-numeric: tabular-nums;
}
```

That's all. The redesign is layout + composition, not new color territory.

---

## 13. What to remove (immediate cuts)

Six items the eye will not miss.

1. **The big ⤓ arrow in `FileUpload.tsx:61`.** Replace with no glyph; the text + the dashed → solid border treatment carries the affordance.
2. **The dashed border on the dropzone (`FileUpload.tsx:42` `border-2 border-dashed`).** Solid 1px. Reverse the hierarchy: dashed-border is what we use for *empty states*, not for *primary affordances*.
3. **The "OR TRY A SAMPLE REPLAY" all-caps label (`FileUpload.tsx:90`).** Removed — the samples become the *primary* path, not the alternate path. The label `BEGIN` in the new layout (§8.1) names the affordance properly.
4. **The noVNC iframe on `/upload` (`TorcsControlPanel.tsx:416-424`).** Moves to `/cockpit` per §10 option B.
5. **The "Manual TORCS setup" disclosure under Race Control (`TorcsControlPanel.tsx:316-328`).** Useful copy, but lives on the new `/cockpit` surface, not in the entry-page checklist.
6. **The `border-accent/40 bg-surface/60` recipe on the Live TORCS card (`UploadPage.tsx:189`).** Becomes `border border-border bg-surface` — solid, calm, equal to the other cards. The accent is reserved for the action buttons inside.

And one cut from the Session page:

7. **Per-card "L23 · S2 · low-roi-deploy" mono header overpowering the headline (`RecommendationCard.tsx:107-116`).** Reorder: headline (h3) first, metadata second.

---

## 14. Implementation phasing

Three phases, sequenced so each ships independently and the architect can stop after Phase A if budget runs out.

### Phase A — Chrome + entry-page recomposition (4 h)
**Ships:** the premium feel without touching the session viz.

A1. New site header with decision-support subhead + version chip (`SiteHeader` in `App.tsx`). [1 h]
A2. New `UploadPage` two-pane layout per §8. Components composed from existing primitives. [2 h]
A3. `FileUpload` refinement per row 1–2 of §11. [0.5 h]
A4. Site footer rewrite. [0.5 h]

**Verifiable:** screenshot of `/upload` next to today's — premium delta is unmistakable.

### Phase B — Race Control split + cockpit surface (3 h)
**Ships:** cleaner entry, dedicated cockpit.

B1. Split `TorcsControlPanel` into `RaceControlCard` (form-only) + `CockpitSurface` (noVNC iframe + status). [2 h]
B2. New route `/cockpit` (or modal, per architect choice). [0.5 h]
B3. "Open cockpit view" disclosure link from Race Control. [0.5 h]

**Verifiable:** Race Control card shrinks to ~120px on `/upload`; the noVNC iframe still works on its own surface.

### Phase C — Session detail polish (5 h)
**Ships:** the destination matches the entry.

C1. KPI strip component above the energy curve. [1.5 h]
C2. Energy curve adds harvest/deploy stacked area + sector tinting. [1.5 h]
C3. Zone heatmap → ribbon (or cell rescale — architect decides). [1 h]
C4. `RecommendationCard` headline-led + citation rail. [1 h]

**Verifiable:** `/session/:id` for the layered-defense fixture renders KPIs above the fold, no scroll required to see "this is grounded in <issue> § <section>."

### Phase D — Below-fold preview strip on Upload (2 h)
**Optional; ship only if budget remains.**

D1. Embed real `EnergyCurve` + `RecommendationCard` rendered from a frozen fixture in a `Preview` component on `/upload`. [2 h]

**Total: 14 h.** Fits inside Week-3 polish budget.

---

## 15. Coding briefs (for the implementer)

Numbered to match the phasing in §14. Each brief is self-contained — the implementer should not need to re-read this whole doc to act on one.

### Brief A1 — Site chrome
**Files:** [`ui/src/App.tsx`](../../ui/src/App.tsx#L45) `SiteHeader` and `SiteFooter`.

Change `SiteHeader` to render two rows:
- Row 1 (existing): wordmark + Upload/Sessions nav, height 48px. Add a right-aligned `<button>` that opens a popover showing `GET /api/version` content (build SHA + model versions). Style: `text-[11px] font-mono text-muted hover:text-text`.
- Row 2 (new): a single line — *"Explainable AI race-strategy copilot · grounded in FIA · IBM watsonx.ai"* — at `text-xs text-[var(--color-chrome-subhead)]`. Height 32px, bottom-border `border-border`. On the session page only, this row is replaced by the session-metadata sub-line per §9.5.

Change `SiteFooter` to render the brand line:
*"© OVERRIDE · Apache 2.0 · IBM SkillsBuild May 2026 · Repo ↗ · Decision support, never replacement."*

Order matters: the brand promise becomes the *last* clause so it persists in screenshots but isn't the headline.

**Acceptance:** screenshot of any page top-strip shows the subhead. Lighthouse a11y unchanged.

### Brief A2 — UploadPage two-pane

**Files:** [`ui/src/pages/UploadPage.tsx`](../../ui/src/pages/UploadPage.tsx), new `ui/src/components/SampleReplayList.tsx`, new `ui/src/components/BringYourOwn.tsx`.

Replace the centered single-column layout (`flex flex-col items-center pt-16 px-6`) with a two-column grid at `md:` and up:

```tsx
<div className="max-w-6xl mx-auto px-6 pt-12 grid md:grid-cols-[3fr_2fr] gap-6">
  <BeginPane samples={…} onSample={…} onFile={onFile} isUploading={…} error={…} />
  {(torcsAvailable || isLocalHost()) && (
    <LiveCapturePane runs={torcsRuns} onIngest={…} controlStatus={…} />
  )}
</div>
```

- `BeginPane` composes `SampleReplayList` (row-style list with metadata badges) above `BringYourOwn` (the single-line dropzone). Top sample gets `◆` accent + "Recommended" pill.
- `LiveCapturePane` composes the new `RaceControlCard` (Brief B1) above the existing runs list (refactored to a tight 3-row max with "+N more" disclosure).
- When `!torcsAvailable && !isLocalHost()`, the right pane is omitted; the left pane spans full width.

**Acceptance:**
- The dashed dropzone is gone.
- The screenshot taken at `npm run dev` matches §8.1 wireframe within reason.
- All existing actions still work: file upload, sample replay, TORCS ingest, race start/stop.

### Brief A3 — FileUpload refinement

**Files:** [`ui/src/components/FileUpload.tsx`](../../ui/src/components/FileUpload.tsx).

- Remove the `⤓` glyph (line 61).
- Change `border-2 border-dashed` to `border border-border`.
- Change `p-12` to `p-6`.
- Single-line text: `Drop a replay, or browse — .json / .parquet, up to 25 MB`.
- Hover state: `border-accent/60 bg-accent/[0.03]` — softer than today's `border-accent bg-accent/5`.
- Move the sample-replay rendering OUT of this component (it's now in `SampleReplayList`). `FileUpload` becomes single-purpose.

**Acceptance:** the dropzone no longer dominates the page.

### Brief A4 — SiteFooter
Covered in Brief A1.

### Brief B1 — RaceControlCard + CockpitSurface split

**Files:** new `ui/src/components/RaceControlCard.tsx`, new `ui/src/pages/CockpitPage.tsx`, refactor of [`TorcsControlPanel.tsx`](../../ui/src/components/TorcsControlPanel.tsx).

- `RaceControlCard` keeps the status badge, track dropdown, lap input, headless checkbox, start/stop buttons, and the manual-setup details disclosure. **Removes** the TORCS view label, Fullscreen button, and noVNC iframe (lines 376–428).
- `CockpitPage` is a new route at `/cockpit` with: page-title chrome, status pill, full-bleed 16:9 noVNC iframe (same source URL `vnc_lite.html?autoconnect=1&password=&reconnect=1&scale=true`), Fullscreen button, "Back to OVERRIDE ←" link. No other content.
- Disclosure on `RaceControlCard`: `<a href="/cockpit">Open cockpit view ↗</a>` — opens in the same tab.

**Acceptance:**
- The Upload page no longer renders the iframe.
- `/cockpit` works and reaches the same noVNC URL.
- The hostname guard (`isLocalHost()`) still hides both `RaceControlCard` AND `/cockpit` on the hosted demo.

### Brief B2 — `/cockpit` routing

**Files:** [`ui/src/App.tsx`](../../ui/src/App.tsx).

Add `<Route path="/cockpit" element={<CockpitPage />} />` between `/sessions` and `/session/:sessionId`. Add to `PageTitleManager` map.

**Acceptance:** `/cockpit` renders; broken-iframe state is handled (timeout + reload button).

### Brief C1 — KPI strip

**Files:** new `ui/src/components/KpiStrip.tsx`, [`ui/src/pages/SessionPage.tsx`](../../ui/src/pages/SessionPage.tsx).

Insert above `<EnergyCurve …/>` (current line 304). Tiles:
1. **HARVEST** — `Σ(lap.harvest_mj)` from `session.laps`, `success` tone arrow.
2. **DEPLOY** — `Σ(lap.deploy_mj)` from `session.laps`, `warning` tone arrow.
3. **LAPS** — `session.summary.lap_count`.
4. **ZONES** — `session.recommendations.length` with `(<n>H)` suffix counting high-severity.
5. **AI SAFETY** — average of `min(Object.values(rec.guardian.scores))` across recommendations; tone follows the score band per §9.1.
6. **FINAL SOC** — `session.laps[session.laps.length-1].soc_end * 100`.
7. **CITATION** — `§ <section>` link → `regulation_source.public_url`, opens new tab.
8. **VALIDATOR** — `<passed>/<total>` pass-rate from `recommendations` — replaces the in-card status as a top-line scorecard.

Hide tiles 1, 2, 6 during `status === "active"` (no laps yet).

**Acceptance:** the entire trust narrative is visible in one strip without scrolling.

### Brief C2 — Energy curve enrichment

**Files:** [`ui/src/components/EnergyCurve.tsx`](../../ui/src/components/EnergyCurve.tsx).

Add two layers using existing `LapFeatures`:
1. Stacked `<Area dataKey="harvest_mj" stackId="energy" fill="var(--color-success)" fillOpacity={0.12} />` and matching deploy layer beneath the SoC line, on a secondary Y axis (right-side, 0–10 MJ range).
2. Sector tinting: iterate `recommendations`; for each, draw a `<ReferenceArea x1={lap-0.4} x2={lap+0.4} fill={severityTone}` fillOpacity={0.06}` />`.
3. Brush: add `<Brush dataKey="lap" height={20} stroke="var(--color-border)" />` when `laps.length > 60`.

**Acceptance:** at the layered-defense fixture, all four signals (SoC, harvest, deploy, zone tints) read clearly in one chart.

### Brief C3 — Zone strip (architect decides between ribbon vs rescale)

**Files:** [`ui/src/components/ZoneHeatmap.tsx`](../../ui/src/components/ZoneHeatmap.tsx).

Option a (ribbon): replace the table with a `<svg>` ribbon, 40px tall, three 12px stacked sector rows, lap-position-to-x linear scale. Same a11y treatment per cell.
Option b (rescale): change cell to `w-3 h-4` (12px × 16px), gutter to `2px`. Lap labels every 5 laps with first/last always shown.

**Acceptance:** legible at 47-lap and 12-lap fixture sessions.

### Brief C4 — Recommendation card

**Files:** [`ui/src/components/RecommendationCard.tsx`](../../ui/src/components/RecommendationCard.tsx).

Two structural changes:
1. In `EngineerCard`, move `reasoning.recommendation` (the headline-ish sentence) above the `header` block, rendered as `<h3 className="text-base font-semibold mb-2">{recommendation}</h3>`. Promote the metadata (`L23 · S2 · low-roi-deploy [medium severity]`) to a sub-line below.
2. At `md:` and up, render the citation block (`<Citation rec={rec} />`) in a 30%-width right rail using CSS grid. Stacks below on narrow.
3. Make the footer (`<footer>` at line 143) `sticky bottom-0` with `bg-surface` background so the badges stay visible when the reasoning chain expands.

**Acceptance:** the card reads as "here is the finding" instead of "here are the keys."

### Brief D1 — Preview strip
**Files:** new `ui/src/components/PreviewStrip.tsx`, [`ui/src/pages/UploadPage.tsx`](../../ui/src/pages/UploadPage.tsx).

Render below the two-pane grid. Calls `api.getSession("layered_defense", { fixture: true })` (the fixture path is already wired). Renders the `EnergyCurve` (read-only) and the first `RecommendationCard` (read-only, no what-if rail). Adds a single line above: *"What you'll see — a real debrief from the cached layered-defense fixture."*

**Acceptance:** entry page now previews the destination.

---

## 16. Manual operator tests (for Patrick)

These are the design-validation steps that need a human. Coder cannot do these.

1. **Side-by-side screenshot test (Phase A).** Take a screenshot of `/upload` at 1900×1200 today; take the same screenshot after Phase A. Confirm: dropzone is no longer the loudest element; the decision-support line is visible without scrolling; the sample replays read as the primary path.
2. **Three-second-rule test.** Show the new `/upload` to someone unfamiliar with the project. Ask them, after 3 seconds, "what does this app do?" — they should be able to paraphrase the subhead. If they can't, the chrome subhead copy needs another iteration.
3. **Path-of-least-resistance test.** Same person — "click whatever you would click first." If they click the recommended sample row, the IA is right. If they click the dropzone, the hero hierarchy still isn't strong enough.
4. **Premium-feel A/B (subjective).** Show today's screenshot + the new one to 2–3 people and ask which "feels more like an engineering tool." If <2 prefer the new one, we re-iterate before shipping.
5. **TORCS live-capture flow still works.** End-to-end: drive a race in `/cockpit`, return to `/upload`, see the run in Live Capture, click Ingest, land on the new session page. All five should still take ≤90s combined.
6. **Cockpit fullscreen.** On `/cockpit`, fullscreen should still produce a readable HUD per the current `vnc_lite.html` setup. This is the only place noVNC's status-bar quirk (the absolute-positioned offset hack at `TorcsControlPanel.tsx:416`) needs to survive.
7. **Mobile density warning.** At `< 768px`, the page should be functional but show the existing density warning (per `04-ui-ux-design.md` §9). Confirm we didn't break that.

---

## 17. What changes outside the UI (none required)

- **API:** no new endpoints. The KPI strip and curve enrichment use existing schemas (`LapFeatures`, `Recommendation`, `RegulationSource`).
- **Pipeline:** no changes.
- **Tokens:** the spec at `04-ui-ux-design.md` §3 stays authoritative. The additions in §12 are *internal* utilities; the published palette is unchanged.
- **UI/UX doc:** after architect approval, `04-ui-ux-design.md` §4.1 (Upload wireframe) and §4.2 (Session wireframe) get a synchronized update. Same PR that ships Phase A.

---

## 18. Open questions for the architect

Decide before the coder picks this up.

- **OQ-D1.** `/cockpit` as a route, or as a modal? Route is cleaner; modal keeps state. I lean route.
- **OQ-D2.** Zone heatmap — collapse to ribbon (§9.3), or just rescale cells? Ribbon is more premium; rescale is less risky. I lean ribbon, but it touches more code.
- **OQ-D3.** Phase D (preview strip on `/upload`) is the highest *perceived* lift per hour, but it adds a second data fetch on `/upload`. Worth the latency hit? I lean yes — the fixture path is cached.
- **OQ-D4.** The Decision-Support subhead lives in the chrome on **every page** or just `/upload`? Every page is heavier-handed but reinforces the brand promise. I lean every page.
- **OQ-D5.** Should we add a "What's new in 2026" disclosure on `/upload` (one paragraph: MGU-K 350 kW, Override Mode, 7 MJ qualifying cap) so judges who aren't F1 fans get oriented? Out-of-scope for the audit but a 30-min add. I lean no — keep the chrome lean — but flagging it.
- **OQ-D6.** The session header — keep the existing E/F mode toggle in the same row as the wordmark/metadata, or pull it out into its own toolbar? I lean keep it where it is; the toggle is already discoverable.

---

## 19. Acceptance criteria for the architect

If all six clear, ship Phase A. Repeat the gate at Phase B, C, D.

- [ ] **Hero is unambiguous.** Show the new `/upload` to a stranger; they correctly identify "click the recommended sample" as the primary action within 5 seconds.
- [ ] **Premium delta is visible.** Side-by-side screenshot of `/upload` (before/after Phase A) — at least two of three reviewers agree the new version "feels more like an engineering tool."
- [ ] **No regression on existing flows.** All paths in §16 step 5 still work, with no extra clicks vs today.
- [ ] **Tokens contract intact.** `docs/04-ui-ux-design.md` §3 palette values unchanged. Additions are internal-only.
- [ ] **A11y not regressed.** Axe / Lighthouse a11y score for `/upload` ≥ today's baseline.
- [ ] **Build green.** `npm run typecheck && npm run build` pass; `pytest -q -m "not network"` still at the documented baseline.

---

## 20. Don'ts

- **Don't change the design tokens' published values.** Add `--color-surface-3` and `--color-chrome-subhead` as additions; do not retune `--color-bg`, `--color-accent`, etc.
- **Don't introduce a new component library.** The project is hand-built Tailwind + tokens. Adding Radix / shadcn now is scope creep and won't fit the timeline.
- **Don't add animations beyond the current motion tokens** (`--motion-fast`, `--motion-card`, `--motion-mode`). The premium feel comes from restraint.
- **Don't hardcode FIA article numbers anywhere** — same rule as the rest of the codebase. The KPI strip's citation tile reads `§ <regulation_source.section>` from the struct.
- **Don't break the noVNC iframe wrapper-clip hack** in [`TorcsControlPanel.tsx:416-424`](../../ui/src/components/TorcsControlPanel.tsx#L416). It earns its complexity — preserve it verbatim when moving to `/cockpit`.
- **Don't recreate the deleted CI workflow** (per `AGENTS.md`).
- **Don't backfill the `core/forecasting.py` stub** — TTM is v1.1.

---

## 21. How this brief closes

When Phase A ships (the minimum increment that makes the brand promise legible):
1. Update `docs/04-ui-ux-design.md` §4.1 wireframe to match what we shipped.
2. Capture fresh `/upload` screenshot into `assets/screenshots/upload.png` for the README.
3. Mark the relevant checkboxes in §19 of this file in the PR body.

When Phase D ships (or we hit the budget ceiling without it):
1. Delete this file in the same PR.
2. Reference it from the PR description with the SHA — that's the trail.

Anything I missed, or any concern about the phasing — leave a comment on this file; do not edit prescriptive sections after architect sign-off. Edit the *open questions* freely.

---

*Authored 2026-05-14 by the designer hat. Ready for architect review.*

---

## 22. Architect rulings — 2026-05-14

> **Verdict: APPROVED for Phase A, B, C, D in that order, with three modifications, six open-question rulings, and two non-blocking flags.** Verified against current code: `GET /api/version` exists (`api/main.py:396`), `RegulationSource.public_url` exists (`ingest/schema.py:168`), `Recommendation.guardian.scores` and `getSession(opts)` both exist. §17 "no API changes" claim is accurate; no schema or endpoint additions required.

### 22.1 — Open-question rulings

| ID | Question | Ruling | Reason |
|---|---|---|---|
| OQ-D1 | `/cockpit` as route or modal? | **Route** | State doesn't need to persist across navigations; the noVNC URL re-establishes the iframe on mount. Route lets `isLocalHost()` cleanly 404 the surface on the hosted demo, and the route is cheaper to deeplink in the video. |
| OQ-D2 | Zone heatmap — ribbon (Option a) or rescale (Option b)? | **Ribbon (Option a)** | The current heatmap was always trying to be a ribbon — three sector rows × N laps with severity color. The ribbon preserves all three sectors as one perceptual unit; rescale is a half-measure. Slightly more code; materially better outcome. |
| OQ-D3 | Phase D preview strip — ship it? | **Yes, if Phase A–C clear** | Fixture path is in-process and synchronous; zero real latency. "Show the destination on the entry" is one of the five design principles (§5.5); leaving it out weakens the framing. |
| OQ-D4 | Decision-Support subhead on every page or just `/upload`? | **Every page**, replaced by session metadata on `/session/:id` per §9.5 | Brand promise gets screenshot persistence on every captured frame, without competing with session-specific metadata when there's richer content to show. |
| OQ-D5 | "What's new in 2026" disclosure? | **No** | The credibility line plus "grounded in FIA" in the subhead already implies the 2026 framing. Lean chrome is the brand. |
| OQ-D6 | E/F toggle placement on session page? | **Keep where it is** | Already discoverable; pulling it into a toolbar adds vertical real estate for zero usability gain. |

### 22.2 — Required modifications

Apply before merging the corresponding Brief.

**M1 — Brief C1 "AI SAFETY" tile labeling (Phase C).**
The math is `avg(min(Object.values(rec.guardian.scores)))` — "average across recommendations of per-zone Guardian floor scores." Honest, but mis-labelable. Either:
- (a) Rename the tile **`SAFETY FLOOR`** (or `AI SAFETY (worst-per-zone avg)` if room allows); OR
- (b) Change the math to **global min across all (rec × criterion) pairs** — "the lowest score the AI gave anything in this session," a one-sentence explanation.

Coder's call on visual; both are honest. Document the choice in the `KpiStrip` JSDoc.

**M2 — Brief D1 fixture choice (Phase D).**
The audit uses `layered_defense_demo` both as the hero "Begin" sample AND as the preview-strip source. Layered-defense is the **Pass-2-fails-by-design** rejection demo — great for "see how safety works" but mixed messaging on an entry-page preview. **Swap the preview-strip source to `torcs_engineer_demo`** (the clean happy-path fixture). Hero list still offers layered-defense as one of three options; entry preview shows the optimistic case.

**M3 — Brief A1 version chip — gate `/api/version` popover content (Phase A).**
The popover renders **build SHA + Granite model IDs + git tag** ONLY — never the `WATSONX_PROJECT_ID` or any auth-adjacent field. Before wiring the popover, grep `class VersionResponse` in `api/main.py`, confirm the response shape, and if it carries any field outside the allowlist `{build_sha, models, tag, app_version}` scope the popover render to the allowlist explicitly. The endpoint itself stays unchanged; this is a UI rendering constraint.

### 22.3 — Non-blocking flags (apply during implementation)

**F1 — Brief A1 chip accessibility.** `text-[11px] font-mono text-muted` may not clear WCAG AA contrast on dark surfaces, and 11px is below the 12px floor most a11y tools warn on. Bump to `text-[12px]` and validate against `--color-muted` once it lands. §19's "a11y not regressed" criterion is the gate — this is the one new content surface where it could.

**F2 — Brief C1 tile hiding during `status === "active"`.** Three tiles (Harvest, Deploy, Final SoC) hide when the session is mid-capture. Verify the `SessionSummary.status` enum values before wiring — `"active"` is the **race-control daemon** lifecycle state (ADR-004 §"Six-state race lifecycle"), but `SessionSummary` may use different values for in-flight ingestion (e.g. `"ingesting"`, `"completed"`). Grep `SessionSummary` + `status` in `ingest/schema.py` before deciding the hide condition.

### 22.4 — Phase approval

| Phase | Approval | Pre-merge gates |
|---|---|---|
| A — Chrome + entry-page recomp (4h) | ✅ APPROVED | Apply **M3** + **F1** to Brief A1 |
| B — Race Control split + cockpit surface (3h) | ✅ APPROVED | Apply OQ-D1 (route, not modal) |
| C — Session detail polish (5h) | ✅ APPROVED | Apply **M1** + **F2** to C1; ribbon (Option a) for C3 per OQ-D2 |
| D — Preview strip (2h) | ✅ APPROVED conditional on A+B+C clearing | Apply **M2** (use `torcs_engineer_demo`) |

**Total budget unchanged at 14h.** All four phases ship independently. Phase A alone delivers the "premium feel without touching the session viz" promise and is the natural T-72h fallback if Week 3 runs hot.

### 22.5 — Sign-off on §17 "no API changes"

Verified line-by-line:
- **KPI strip math** uses `lap.harvest_mj`, `lap.deploy_mj`, `session.summary.lap_count`, `rec.guardian.scores`, `lap.soc_end`, `regulation_source.section`, `regulation_source.public_url` — all existing fields.
- **Energy curve enrichment** uses `lap.harvest_mj` and `lap.deploy_mj` (existing); `<ReferenceArea>` and `<Brush>` are Recharts primitives already used in the project.
- **Preview strip** uses the existing fixture-mode `getSession(sessionId, { fixture: true })` path — no new endpoint, no new fetch shape.

**No `docs/04-schema.md` changes. No `docs/04-api.md` changes.** §17 stands.

### 22.6 — §19 acceptance criteria stand as written

The "premium delta is visible" test is intentionally subjective and that's the right call — design quality isn't unit-testable. The remaining five gates (hero unambiguous, no regression on flows, tokens contract intact, a11y not regressed, build green) are objective.

### 22.7 — §20 don'ts stand as written

All six honor the project non-negotiables (`docs/03-architecture.md`, `AGENTS.md`, `.bob/rules.md`, `docs/04-ui-ux-design.md`).

---

*Architect sign-off recorded 2026-05-14. Coder is unblocked for Phase A.*
