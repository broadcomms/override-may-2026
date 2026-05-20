# OVERRIDE — UI / UX Design

This document describes the shipped product surface in `ui/` as it exists today. It covers the user-facing app. Backend contracts live in [`04-api.md`](./04-api.md) and [`04-schema.md`](./04-schema.md).

## 1. Audience modes

| Audience | Surface | Job |
|---|---|---|
| Operator / engineer | Upload, Sessions, Session detail, Cockpit, Driver Lab | Run analysis, inspect reasoning, launch or ingest TORCS sessions, tune driver profiles |
| Broadcaster / analyst | Session detail, Session compare | Explain race-energy moments with grounded evidence or fan-language summaries |
| Curious fan | Upload sample replays, Session detail Fan mode | Understand the battery story without telemetry jargon |

The same backend session model feeds both Engineer and Fan renderings.

## 2. Current information architecture

```text
/
├── /upload
├── /driver-lab
├── /sessions
├── /sessions/compare?a=<id>&b=<id>
├── /cockpit
└── /session/:session_id
    ├── /laps/:lap_number
    ├── ?fixture=1
    └── ?zone=<zone_id>
```

Route behavior:
- `/` redirects to `/upload`
- `/driver-lab` and `/cockpit` are meaningful only when the TORCS surface is available for the host/deployment
- `?fixture=1` forces UI fixture mode for the current tab
- `?zone=...` deep-links to a recommendation card

## 3. Shared chrome

### Header

- Wordmark and logo icon
- Nav: `Upload`, conditional `Driver Lab`, `Sessions`
- Build/version chip that lazily loads `/api/version`
- Second-row brand line: explainable AI race-strategy copilot, grounded in FIA, watsonx.ai

### Footer

- Apache 2.0
- IBM SkillsBuild project framing
- repo link
- explicit decision-support wording

### Accessibility

- Skip-to-content link in `App.tsx`
- keyboard-focusable route surfaces and dialogs
- deep links into recommendation cards
- no modal-only destructive flows; delete actions use explicit confirm dialogs

## 4. Visual system

The current UI keeps the shipped dark motorsport identity:

- Background: carbon-black family
- Accent: override orange
- Success: energy-safe green
- Warning/danger: amber and red for guardrail states
- Mono usage: telemetry, lap IDs, build/version metadata
- Rounded cards and pills

Key tokens remain:
- `--color-bg`, `--color-surface`, `--color-surface-2`, `--color-border`
- `--color-text`, `--color-text-muted`
- `--color-accent`, `--color-success`, `--color-warning`, `--color-danger`
- `--font-sans`, `--font-mono`

## 5. Page surfaces

### `/upload`

This is now a two-lane entry surface:

- Left lane: sample replays plus the bring-your-own upload path
- Right lane: race-control card, live capture list, and capture deletion
- Below the fold: preview strip using the cached TORCS engineer fixture

Important behaviors:
- Sample replay cards are the fastest on-ramp
- Upload accepts user files and navigates to `/session/:id`
- Live captures page through the shared telemetry volume
- Capture rows show `Ingest` or `Open session` depending on whether the JSONL has already been ingested
- The live lane collapses when the host cannot expose TORCS and there are no runs to show

### `/driver-lab`

Driver-profile management surface for the managed TORCS path.

Capabilities:
- load shipped and user-saved profiles
- edit a mutable draft
- validate config before save
- duplicate a profile
- create a new profile from the current draft
- delete user-created profiles

The page exists to support live managed driving, not offline session analysis.

### `/sessions`

Paginated session history with row-level and bulk management.

Capabilities:
- newest-first session browsing
- multi-select
- compare exactly two sessions
- single delete
- bulk delete
- optional removal of source telemetry JSONL when deleting TORCS-live sessions

Empty state drives the user back toward `/upload`.

### `/sessions/compare`

Side-by-side session summary comparison.

Focus:
- high-level pipeline stats rather than per-zone diffing
- uploaded time, source, track, driver profile, lap count, zone count, totals
- quick drill-in links back to each session debrief

### `/session/:session_id`

This is the debrief surface and the primary explainability view.

For completed sessions it renders:
- session header
- note banner when present
- driver-profile snapshot chips when present
- grounding-pending banner when regulation grounding is unavailable
- KPI strip
- post-race report panel
- report export action via browser print/save-to-PDF
- shell-level AI race engineer widget with persistent transcript and grounded lap links
- energy curve
- zone heatmap
- recommendation list
- what-if diff results inline under the triggering card
- regulation-source footer

For active sessions it renders:
- live telemetry panel first
- KPI strip with active-safe tiles
- suppression of empty post-race charts/cards until ingest completes
- next-step guidance telling the operator to ingest the race once finished

### `/cockpit`

Live operator surface around the TORCS display or headless capture state.

Current layout:
- command strip with race state, session, lap, fullscreen, stop race
- timing rail
- center frame for noVNC or headless placeholder
- hybrid-energy rail
- lap timeline
- deterministic live strategy insight block with Engineer/Fan toggle and recent insight trace

Important UX rule:
- cockpit insight is explicitly labelled as a live deterministic signal until completed-lap analysis exists
- full grounded recommendations still belong to the completed session flow

### `/session/:session_id/laps/:lap_number`

Dedicated lap drill-down route for post-race review.

Current layout:
- back-link to the session debrief
- lap headline and deterministic summary
- lap metrics strip
- sector callouts
- evidence list
- matching recommendations for that lap
- if structured live insights are unavailable, the cockpit falls back to the older deterministic battery-signal copy rather than leaving the panel blank

### Global AI race engineer widget

The app now mounts a persistent AI race engineer widget at the shell level instead of a page-local session panel.

Current behavior:
- stays mounted while the user moves between session debrief, lap detail, and cockpit routes in the same browser tab
- persists per-session transcript state in `sessionStorage`
- shows a real chat stream with user turns, streamed assistant turns, supporting-lap links, and follow-up chips
- keeps completed-session and live-race grounding separate via route-aware context badges
- uses Granite-backed grounded answers on the main path and surfaces deterministic fallback explicitly when the model response cannot be structured
- on `/cockpit`, reuses the same live SSE telemetry source as the cockpit rails so the widget does not open a competing stream
- carries a launcher unread badge when a response lands while the drawer is closed

## 6. Mode behavior

### Session page mode toggle

- `Engineer`: always available
- `Fan`: lazily fetched per zone and cached per session
- Fan-mode failures do not block the page; the affected zone falls back to Engineer rendering with a small warning

### Cockpit mode toggle

- `Engineer`: structured deterministic live insights with evidence + fallback deterministic signal language
- `Fan`: plain-language live summary of the same deterministic insight
- neither pretends to be a completed grounded recommendation

## 7. Recommendation-card behavior

The current card structure is headline-led:

- headline is `reasoning.recommendation`
- metadata row shows lap, sector, zone type, and severity
- cause/consequence render in the main column
- reasoning chain is collapsible
- citation lives in a right rail on wider layouts
- sticky footer keeps validator, Guardian, and final-confidence badges visible

Two failure modes have explicit treatments:

1. Terminal validator failure:
   - the normal headline layout is replaced
   - failed rules and notes are surfaced directly
2. Shipped low-confidence recommendation after Guardian failure:
   - recommendation still renders
   - low-confidence banner marks it exploratory

## 8. What-if interaction

What-if is available from Engineer cards only.

Flow:
1. user opens the rail
2. user chooses one perturbation
3. UI calls the what-if endpoint
4. result renders as a before/after diff under that card
5. user can dismiss the diff and return to the base card

Current diff view:
- before and after mini-cards
- metric deltas
- pass/fail badges for both sides
- perturbation label
- optional note for truncated or edge-case outcomes

## 9. Data-visualization surfaces

### Energy curve

- observed SoC line
- optional forecast continuation and band
- harvest/deploy areas on a secondary axis
- zone markers and severity-tinted vertical bands
- brush for long sessions

### Zone heatmap

- three sector rows
- lap columns
- severity-coded filled cells
- click-through into recommendation cards

### KPI strip

Summarizes the session in compact, high-visibility tiles above the main detail surfaces.

### Live telemetry widgets

- live lap timeline
- timing rail
- hybrid-energy rail
- deterministic live insight block
- recent live insight trace (latest 5 unique insights)

## 10. Fixtures and demo affordances

The UI intentionally supports fixture mode for:
- fast design iteration
- demo recording fallback
- offline exploration without burning watsonx quota

Fixture usage surfaces:
- sample replay list
- upload-page preview strip
- session routes with `?fixture=1`
- cockpit-intelligence replay via the fixture-mode mock live stream

## 11. Responsive and operational constraints

- `/upload` collapses from a two-lane grid to one column on smaller widths
- cockpit keeps the center surface dominant and wraps supporting rails below it on narrower screens
- hosted environments without TORCS hide or redirect away from TORCS-only affordances
- destructive actions are always confirmed before disk changes

## 12. Source of truth

This UI document should stay aligned with:
- [`ui/src/App.tsx`](../ui/src/App.tsx)
- [`ui/src/pages/UploadPage.tsx`](../ui/src/pages/UploadPage.tsx)
- [`ui/src/pages/DriverLabPage.tsx`](../ui/src/pages/DriverLabPage.tsx)
- [`ui/src/pages/SessionsPage.tsx`](../ui/src/pages/SessionsPage.tsx)
- [`ui/src/pages/SessionComparePage.tsx`](../ui/src/pages/SessionComparePage.tsx)
- [`ui/src/pages/CockpitPage.tsx`](../ui/src/pages/CockpitPage.tsx)
- [`ui/src/pages/SessionPage.tsx`](../ui/src/pages/SessionPage.tsx)
