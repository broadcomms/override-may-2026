# OVERRIDE — UI / UX Design

> Visual and interaction spec for the OVERRIDE web app. Backend contracts are in [`04-schema.md`](./04-schema.md) and [`04-api.md`](./04-api.md). Langflow canvas spec lives in [`04-langflow-canvas.md`](./04-langflow-canvas.md) — that document covers orchestration, this one covers the user-facing product.

---

## 1. Audiences and primary jobs

| Audience | Mode | Primary job |
|---|---|---|
| Race engineer / strategist | Engineer | Inspect a session debrief: see flagged inefficient zones, audit reasoning, verify regulation citation, run what-if |
| Broadcaster / analyst | Engineer (light) → Fan | Pull a plain-language explanation of an energy moment they can quote on air |
| Curious fan | Fan | Watch a replay's strategy story unfold without acronyms or numeric wall |

One backend pipeline serves all three — only the rendering layer changes.

---

## 2. Information architecture

```
/                              (auto-redirects to /upload if no sessions, else /sessions)
├── /upload                    (drop a replay, see progress, navigate to session on success)
├── /sessions                  (history of past sessions, list of SessionSummary)
└── /session/[session_id]      (full debrief view; Engineer ↔ Fan toggle in header)
        └── ?zone=<zone_id>    (deep-link to a specific recommendation card)
```

There is no auth, no settings page, no profile, no dashboard analytics. Every screen is read-mostly with one upload action and one mode toggle.

---

## 3. Design tokens

### Palette

| Token | Value | Usage |
|---|---|---|
| `--color-bg` | `#0A0A0A` (carbon black) | page background |
| `--color-surface` | `#141414` | cards, panels |
| `--color-surface-2` | `#1F1F1F` | nested surfaces, hover |
| `--color-border` | `#2A2A2A` | hairlines, separators |
| `--color-text` | `#F5F5F5` | primary text |
| `--color-text-muted` | `#9A9A9A` | labels, captions |
| `--color-accent` | `#FF4500` (override-orange) | brand, primary actions, zone highlight |
| `--color-success` | `#00C853` (sustainable-fuel green) | Pass-1 validator pass, "OK" states |
| `--color-warning` | `#F9A825` | low-confidence badge, regulation banner |
| `--color-danger` | `#D32F2F` | validator/guardian fail, error toasts |
| `--color-granite-blue` | `#052FAD` | Granite badge, BYOC score chip |

### Typography

| Token | Family | Where |
|---|---|---|
| `--font-sans` | Inter (variable) | prose, headings, UI labels |
| `--font-mono` | JetBrains Mono (variable) | telemetry numbers, lap times, MJ values, code |

Heading scale (Inter): `40 / 32 / 24 / 20 / 16` px, weight 600 for h1–h2, 500 for h3+. Body: `15 / 22` (size/line-height). Captions: `13 / 18`.

### Spacing & radius

- Spacing scale: `4 8 12 16 24 32 48 64`.
- Card radius: `12 px`. Pill/badge radius: `999 px`. Input radius: `8 px`.
- Elevation: flat by default; one optional `box-shadow: 0 1px 0 #2A2A2A` for sticky headers.

### Motion

- Hover: 120 ms ease-out.
- Card expand/collapse: 200 ms ease-out, height + opacity.
- Mode toggle: 240 ms cross-fade between Engineer card and Fan card.
- Reduce motion: respect `prefers-reduced-motion: reduce` and switch to instant transitions.

---

## 4. Page layouts

Wireframes are described in text — we are not blocking implementation on figma. Each layout is a 12-column grid, max-width 1280 px, gutters 24 px.

### 4.1 `/upload`

```
┌────────────────────────────────────────────────────────────────────┐
│  [OVERRIDE wordmark]                  [history]  [docs ↗]          │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│              Drop a session replay to begin                        │
│              ─────────────────────────────                          │
│                                                                    │
│         ┌───────────────────────────────────────┐                  │
│         │                                       │                  │
│         │        ⤓  Drag a .json or .parquet    │                  │
│         │           file here, or browse        │                  │
│         │                                       │                  │
│         │       Supported: TORCS, FastF1         │                  │
│         │       Max 25 MB, up to 120 laps       │                  │
│         │                                       │                  │
│         └───────────────────────────────────────┘                  │
│                                                                    │
│         Or try a sample replay:                                    │
│         [ Monza 2024 (FastF1) ]  [ TORCS demo session ]             │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

States:
- **Idle** — call-to-action centered, sample chips below.
- **Hovering with file** — drop zone glows orange (`--color-accent`).
- **Uploading** — drop zone replaced with progress bar (indeterminate), copy: *"Parsing 47 laps… reasoning over 3 zones… running safety review…"* (steps populated in real time from upload progress events).
- **Error** — `ApiError.message` displayed inline, retry button.

The sample replays trigger the same `POST /api/sessions` endpoint with a server-side fixture — they let judges click through the demo without uploading anything.

### 4.2 `/session/[session_id]` — Engineer Mode

Three-region layout: header / main / detail. Detail is a side rail that opens when a zone is selected.

```
┌────────────────────────────────────────────────────────────────────┐
│ OVERRIDE  ·  Monza · 47 laps · uploaded 2026-05-12  | [E][F]  [×]  │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  Energy Curve  (lap 1 → 47, with 5-lap forecast as dotted ext.)    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ ████████████████████████████████████░░░░░ ░░░░░ ░░░░░ ░░░░░ │  │
│  │ ▲ zone @ L23      ▲ zone @ L31    ▲ zone @ L40                │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  Zone Heatmap (sectors × laps)                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ S1 ░░░░░▓░░░░░░░░░░░░░░░▓░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │  │
│  │ S2 ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │  │
│  │ S3 ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░▓░░░░░░░░░░░░░░░░░░░░░░░ │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  Recommendations (3)                                               │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ [card 1]  L23 · S2 · low-roi-deploy · medium severity         │  │
│  │ [card 2]  L31 · S3 · late-recharge · high severity            │  │
│  │ [card 3]  L40 · S1 · unused-override · low severity           │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  Footer: Grounded in <document_title>, <issue> · <section>         │
└────────────────────────────────────────────────────────────────────┘
```

Header right side carries the **mode toggle** `[E][F]` (Engineer / Fan), the model-version popover (calls `GET /api/version`), and a session-delete `[×]`.

### 4.3 Recommendation card (Engineer)

```
┌──────────────────────────────────────────────────────────────────┐
│  L23  ·  Sector 2  ·  low-roi-deploy            [medium severity]│
│  ──────────────────────────────────────────────                  │
│  Cause                                                           │
│   Battery deployment was used in a low-throughput corner where  │
│   the time gain was minimal.                                     │
│                                                                  │
│  Consequence                                                     │
│   Approximately 0.05 s lap-time benefit for ~0.18 MJ deployed,   │
│   reducing energy available for the following straight.          │
│                                                                  │
│  Recommendation                                                  │
│   Consider delaying first deploy by one lap to reserve charge    │
│   for the next Override Mode window on lap 24.                   │
│                                                                  │
│  Reasoning chain  ▼                                              │
│   1. Lap 23 deploy event detected at 0.18 MJ in S2.              │
│   2. Lap-time delta vs. lap 22 +0.05 s.                          │
│   3. Forecast indicates SoC headroom narrows by L25.             │
│                                                                  │
│  Citation                                                        │
│   "Energy released from the ES into the MGU-K shall not exceed   │
│    [...]"                                                        │
│   <document_title>, <issue> · <section>            [open ↗]      │
│                                                                  │
│  ┌────────────┐  ┌────────────────────┐  ┌───────────────┐       │
│  │ ✓ Validation │  │ AI Safety Review  │  │ Confidence:   │       │
│  │              │  │ 0.84 / 1.00       │  │ medium        │       │
│  └────────────┘  └────────────────────┘  └───────────────┘       │
│                                                                  │
│  What if  ▾                                                      │
│   ( ) Delay first deploy by 1 lap                                │
│   ( ) Skip harvest in S2                                         │
│   ( ) Extend Override on next attack                             │
│                                                       [Run ▶]    │
└──────────────────────────────────────────────────────────────────┘
```

Behaviors:
- **Reasoning chain** is collapsed by default; expand on click.
- **Citation passage** is rendered verbatim from `regulation_citation.passage`. The source line shows `document_title`, `issue`, and `section` from `RegulationSource` — never hardcoded. The `[open ↗]` link uses `RegulationSource.public_url`.
- **Validation badge** is green when `ValidatorResult.passed`, red with the failed rule list when not. Failed rules are listed as small chips.
- **AI Safety Review badge** shows the lower of the two Guardian criterion scores. Hover reveals both scores and rationales.
- **Confidence chip** color: green for high, yellow for medium, gray for low.
- **What-if** is a radio set + Run button. Submitting calls `POST /api/sessions/{id}/what-if` and replaces the card body in place with a `WhatIfResult` view (split: original on the left, modified on the right). A "Reset" link returns to the original card.

### 4.4 Recommendation card (Fan)

Same backend, different render.

```
┌──────────────────────────────────────────────────────────────────┐
│  Lap 23                                              [Engineer]  │
│  ──────────────────────────────────────────────                  │
│                                                                  │
│  Battery used in a slow corner that didn't pay off               │
│                                                                  │
│  What happened                                                   │
│   In a tight corner, the car used a chunk of its battery boost   │
│   even though the corner is too slow for the boost to help much. │
│                                                                  │
│  Why it mattered                                                 │
│   That cost about half a tenth, and left less battery for the    │
│   next long straight where it would have made a bigger gain.     │
│                                                                  │
│  The rule                                                        │
│   Per-lap battery use is capped, so spending it where it doesn't │
│   help means less is available where it does.                    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

No raw energy numbers. No acronyms. No reasoning chain. No what-if (Fan Mode is read-only; the toggle returns the user to Engineer Mode for what-ifs).

If `confidence == "low"`, `what_happened` is prefixed with *"It looks like…"* per `prompts/fan_mode.system.md`.

### 4.5 Mode toggle behavior

- Header pill: `[ Engineer | Fan ]`. Active side filled with `--color-accent`.
- Switching to Fan calls `GET /api/sessions/{id}/zones/{zone_id}?mode=fan` for any expanded card; cards keep their current selection.
- Engineer ↔ Fan does **not** re-upload, re-detect, re-ground, or re-validate. It only changes rendering and (for Fan) calls the lazy translation step.
- Keyboard: `E` / `F` shortcuts.

---

## 5. Energy curve

- X-axis: `lap_number` (1-indexed).
- Y-axis: state-of-charge as a percentage (`soc_end × 100`).
- Solid line: observed SoC.
- Dotted continuation: 5-lap forecast `Forecast.point` with shaded prediction interval (`Forecast.lower`, `Forecast.upper`).
- Red triangles below the X-axis mark zones; clicking jumps to the recommendation card.
- Brush at the bottom for zoom (mouse + keyboard arrow).

**Empty state.** When `forecast == null`, the dotted continuation is replaced with a muted hint label *"Forecast unavailable for this session."* with the specific reason (insufficient laps or low forecast confidence) in a tooltip on hover. No error styling — the chart still draws the observed data.

---

## 6. Zone heatmap

- Three rows (S1, S2, S3) × N columns (laps).
- Cell color encodes severity: empty (no zone), yellow (low), orange (medium), red (high). Single-symbol fallback for color-blind users via shape variation.
- Click a cell to scroll the matching recommendation card into view and expand it.

---

## 7. Empty / loading / error states

| State | When | UI |
|---|---|---|
| Empty session | After upload, no zones detected | "*No inefficient zones detected. The session was clean.*" — green check icon. |
| No forecast | `forecast_available == false` | Hint label on the energy curve as above. |
| Low confidence | Reasoning shipped after Pass-2 retries failed | Confidence chip is gray; card body shows a small inline banner: *"This recommendation passed Pass-1 validation but did not meet the AI safety threshold after retries. Treat as exploratory."* |
| Validator failed permanently | After 2 retries, Pass-1 still fails | Card is shown but body content is the validator's `failed_rules` list — no Granite reasoning is displayed. Header chip is red. This case is rare and intentional: judges and engineers see the *system catching itself*, not a black-box failure. |
| Regulation source unavailable | Verification gate G-4 not yet passed | Top-of-page banner: *"Regulation grounding unavailable — citations will be generic until verification completes."* The citation line in cards renders generic phrasing. |
| Model unavailable | API returns 503 | Toast: *"Reasoning service unreachable. Check your watsonx.ai credentials and connection, then try again."* Retry button. |

Loading skeletons:
- Energy curve: gray bars matching the chart shape.
- Recommendation cards: three pulsing card outlines.
- Citation passage: line skeleton in the citation slot.

---

## 8. Accessibility

- All text meets WCAG 2.1 AA contrast against `--color-bg` and `--color-surface`. The override-orange accent on black exceeds AA for ≥18 px text.
- Charts include text alternatives: every chart has an adjacent `<details>` element titled "Chart data" containing a small data table — same data, screen-reader friendly.
- Mode toggle, zone selection, and what-if controls are all keyboard-reachable; focus rings use `--color-accent` outline 2 px.
- Card actions use semantic buttons with `aria-expanded` for collapsibles.
- Heatmap cells include `aria-label` (e.g., *"Sector 2, lap 23, low-roi-deploy, medium severity"*).
- `prefers-reduced-motion` honored as noted in §3.

---

## 9. Responsive behavior

OVERRIDE is a desktop-first product — judges, engineers, and broadcasters review it on a laptop. The following breakpoints are supported, but mobile is **not** a launch target:

| Breakpoint | Behavior |
|---|---|
| ≥ 1280 px | Full layout per §4.2 |
| 1024–1279 px | Heatmap collapses below the energy curve (was inline) |
| 768–1023 px | Recommendation cards become single-column; what-if rail moves below the card body |
| < 768 px | "Best viewed on a wider screen" banner; layout still functions but density warnings shown |

No native app, no mobile-specific styles beyond fluid typography.

---

## 10. Engineer ↔ Fan parity guarantees

The two modes are not feature parity — they are intentionally asymmetric.

| Capability | Engineer | Fan |
|---|---|---|
| See cause / consequence / recommendation | ✓ | rewritten |
| See reasoning chain | ✓ | hidden |
| See verbatim regulation passage | ✓ | hidden |
| See document title + section | ✓ | shown as paraphrase |
| See validator + Guardian badges | ✓ | hidden |
| See confidence chip | ✓ | "It looks like" prefix only |
| See what-if controls | ✓ | redirected to Engineer Mode |
| See raw MJ / kJ numbers | ✓ | qualitative descriptors only |

The shared core is reasoning. Everything else is a UI choice driven by audience.

---

## 11. Asset capture targets (roadmap P3.5)

The following screenshots are required at 2× DPI in `assets/screenshots/`:

- `dashboard.png` — `/session/[id]` Engineer view with three recommendations visible.
- `engineer-mode.png` — close-up of one expanded recommendation card.
- `fan-mode.png` — same zone, Fan rendering.
- `reasoning-card.png` — reasoning chain expanded, citation visible.
- `guardian-rejection.png` — a validator-failed-permanently card (intentionally captured to show the system catching itself).
- `langflow-canvas.png` — captured from the Langflow canvas spec (see [`04-langflow-canvas.md`](./04-langflow-canvas.md)).
- `jaeger-trace.png` — observability trace per roadmap P3.6.

---

## 12. Out of scope

- Real-time / streaming UI updates (the SSE endpoint exists but is for the demo recording only — see [`04-api.md` §4.10](./04-api.md#410-get-apisessionssession_idzoneszone_idstream-optional)).
- User accounts, sharing, comments, presence.
- Mobile-native layout.
- Multi-session comparison views.
- Custom themes, dark/light toggle (we are dark-only on purpose).

---

## 13. Open items

- **Heatmap density**: at >60 laps the cells get crowded; either add horizontal scroll or aggregate to 2-lap bins. Decide during P3.5.
- **What-if catalog**: only three perturbations in v1; expand list is a P3.5 follow-up tied to API §12 open items.
- **Sample replays**: need to choose which TORCS + FastF1 sessions ship as one-click samples; coordinate with `data/samples/` curation.
