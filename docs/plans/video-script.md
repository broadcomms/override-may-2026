# OVERRIDE — Submission video script (locked)

> **Total runtime: 2:55** (175s) at natural narration pace ~130 wpm.
> Total word count: 184 words across 7 segments.
>
> This is the **recording sheet** — read each `VO:` line at natural pace, time
> against the segment budget, watch for stumbles or run-on breaths. Per
> `docs/06-roadmap.md` P4.2: full read under **2:50** is the gate; 5s of
> safety margin is built into segment budgets.
>
> Two corrections from the `docs/00-abstract.md` scaffolding:
> 1. Removed the **TTM-R2 forecast claim** — `core/forecasting.py` is empty
>    stub today. The pipeline runs end-to-end without TTM (graceful
>    degradation per FR-3), so the script reflects what actually ships.
> 2. Removed the **what-if toggle** from the Explainability segment visual
>    list — the endpoint is API Tier 2 (deferred). The disabled-state UI rail
>    can show briefly but not as a working interaction.
>
> All other segment budgets, shot beats, and the cold-open + closing
> structure are inherited verbatim from the abstract.

---

## Segment 1 — Hook (Cold Open) · 0:00–0:20 (20s, 17 words)

**Visual:**
- Black screen (1s)
- Fade in: split-screen — left side a clean simple SoC line (pre-2026 hybrid era), right side a dense 2026-era multi-zone energy map
- Both visuals are **original generated graphics**, not screenshots, not F1 broadcast frames
- Text overlay (A) at 0:04: *"In 2026, F1 hybrid rules change radically."*
- Text overlay (B) at 0:11: *"Every lap is now an energy decision."*
- 0:15–0:20: Cut to OVERRIDE wordmark on dark + tagline card

**VO (starts at 0:05, ends at 0:14):**

> *"In 2026, Formula 1's hybrid rules have changed radically. Every lap is now an energy management decision."*

---

## Segment 2 — Problem Statement · 0:20–0:50 (30s, 30 words)

**Visual:**
- 0:20–0:28: Raw telemetry overload — wall of scrolling numbers, generic dashboard frame (no team livery, no real driver names)
- 0:28–0:38: Confused-engineer schematic figure with a question mark
- 0:38–0:50: Three faded vendor wordmarks fade in then dim — generic "AWS / Oracle / Legacy app" boxes (do **not** use real logos to avoid trademark issues)
- Text overlay at 0:35: *"Today's tools show data, not reasoning."*

**VO (starts at 0:21, ends at 0:34):**

> *"Telemetry tools today show data — not reasoning. AWS, Oracle, and IBM's own Ferrari app shipped for the old rules. There's no open, explainable tool for the 2026 era."*

---

## Segment 3 — Live Demo (Engineer Mode) · 0:50–1:40 (50s, 44 words)

This is the **scoring section** — longest single shot, most cursor work. Practice the click flow once before recording.

**Cursor choreography** (all within `http://localhost:3000`):

| Time | Action | What renders |
|---|---|---|
| 0:50–0:55 | Drag-drop `data/sessions/sample_torx.json` onto the upload zone | Loading shimmer (~5s) |
| 0:55–1:02 | Pause on shimmer — VO covers the wait | "Reasoning over zones · running safety review" copy visible |
| 1:02–1:10 | Energy curve renders, zone heatmap appears below | Recharts SoC line + 5 sector cells colored by zone severity |
| 1:10–1:20 | Cursor moves to a `low-roi-deploy` zone in the heatmap (Lap 1, Sector 2), clicks | Smooth scroll to recommendation card; card snap-out hover lift on arrival |
| 1:20–1:35 | Reasoning card on screen: cause → consequence → recommendation visible. Cursor hovers the citation block | The 3px granite-blue left border + "Citation — verbatim from FIA source" subtitle is in shot |
| 1:35–1:40 | Cursor expands "Reasoning chain (5 steps)" disclosure | Chain unfurls with the snap-out easing |

**VO (starts at 0:51, ends at 1:35):**

> *"Drop in a session replay. OVERRIDE parses telemetry, aggregates lap-level energy features, then detects inefficient deployment zones. Click any zone — Granite 4-h-small Instruct explains the cause, the consequence, and grounds its recommendation in the 2026 FIA technical regulations, parsed with Docling."*

---

## Segment 4 — Explainability (The Hero) · 1:40–2:10 (30s, 41 words)

**Visual:**
- 1:40–1:50: Slow zoom on the reasoning card from segment 3 — frame so cause / consequence / recommendation + the citation block are all visible
- 1:50–2:00: Highlight the **citation passage** (subtle glow or border pulse, 1s) — the verbatim FIA quote is the hero moment
- 2:00–2:10: Cut to the badge row: *✓ Validation* (success-tone), *AI Safety Review: 1.00 / 1.00* (granite-tone), *Confidence: medium* (warning-tone) — three badges in a row, hold

**Do NOT show:** the What-if rail. It's currently a "Coming soon" disabled state — fine in the live UI but pulls focus on a feature we haven't shipped. Crop or scroll past.

**VO (starts at 1:41, ends at 2:09):**

> *"This is the core. Every recommendation cites a verbatim regulation clause. Two safety passes — deterministic validation first, then Granite Guardian scoring on custom safety criteria. If either fails, the system regenerates. The engineer sees the reasoning before any decision."*

---

## Segment 5 — Fan Mode · 2:10–2:30 (20s, 18 words)

**Visual:**
- 2:10–2:13: Cursor moves to the Mode pill in the top-right of the page header
- 2:13–2:14: **Click "Fan"** — the cross-fade transition fires (240ms cubic-bezier snap-out) — ENGINEER → FAN card swap
- 2:14–2:25: Fan card on screen — *headline* + *what happened* + *why it mattered*. Hold for the read.
- Sample fan headline visible: *"The car used battery power too aggressively in low-return corners."*
- 2:25–2:30: Cursor toggles back to Engineer to demonstrate the seamlessness, then returns to Fan

**VO (starts at 2:11, ends at 2:21):**

> *"One click switches to Fan Mode. Same intelligence, plain language — engineers, broadcasters, and fans on the same page."*

---

## Segment 6 — Architecture quick-cut · 2:30–2:42 (12s, 19 words)

**Visual** (4s each, hard cuts):
- 2:30–2:34: `assets/screenshots/langflow-canvas.png` — full Langflow canvas with 9 OVERRIDE custom components wired
- 2:34–2:38: `assets/architecture.png` — the rendered Mermaid diagram from `docs/03-architecture.mmd`
- 2:38–2:42: `assets/screenshots/jaeger-trace.png` — the Jaeger UI showing the per-stage span tree (`pipeline.process_zone` → `regs.retrieve_chunk` → `reasoning.chat` → `guardian.*`)

**VO (starts at 2:31, ends at 2:41):**

> *"Built on IBM watsonx.ai — Granite Instruct, Guardian, and Embedding — plus Docling and Langflow. Open source, Apache 2.0."*

---

## Segment 7 — Closing · 2:42–2:55 (13s, 15 words)

**Visual:**
- 2:42–2:50: OVERRIDE wordmark large, centered, on dark; tagline below: *"Decision support, never replacement. Built for the 2026 hybrid era."*
- 2:50–2:55: GitHub URL appears below the tagline; logo and URL hold to fade-out

**VO (starts at 2:43, ends at 2:51):**

> *"OVERRIDE. Explainable race-strategy AI for the 2026 hybrid era. Code in the description. Built lean."*

---

## Read-aloud pace check

Open this doc + a stopwatch. Read **only the `VO:` lines** in sequence at natural pace. Watch for:

- **Stumbles** — sign of awkward phrasing; mark the line and we'll re-word
- **Mid-segment breaths** — sign of run-on sentences; mark and we'll add a comma break or sentence split
- **Segment overruns** — see decision tree below

### Per-segment timing budget

| # | Segment | Words | VO budget | Visual budget | Total |
|---|---|---:|---:|---:|---:|
| 1 | Hook | 17 | 9s | 11s | 20s |
| 2 | Problem | 30 | 14s | 16s | 30s |
| 3 | Demo | 44 | 22s | 28s | 50s |
| 4 | Explainability | 41 | 19s | 11s | 30s |
| 5 | Fan Mode | 18 | 10s | 10s | 20s |
| 6 | Architecture | 19 | 10s | 2s | 12s |
| 7 | Closing | 15 | 8s | 5s | 13s |
| | **Total** | **184** | **92s** | **83s** | **2:55** |

Pure VO is ~1:32 (92 seconds). The remaining 83s is intentional visual breathing room + transitions + cold-open silence. **Do not rush narration to fill silence** — silence at hard cuts reads as "the system is working" not "we ran out of words."

### Decision tree after the read-through

| Read-through outcome | Action |
|---|---|
| All segments at-budget or under, total ≤ 2:50 | ✅ Lock. Proceed to voiceover recording. |
| One segment 1–3 seconds over budget | Trim 5–10 words from the longest sentence in THAT segment only. Don't compress narration speed. |
| Multiple segments over, total > 3:00 | Cut from Segment 4 (Explainability) — the 38-word draft can drop to 30 by removing the second sentence. |
| Total < 2:35 | Add one beat to Segment 1 (cold open) — let the music breathe. Don't expand VO. |

---

## Recording notes

- **Mic**: condenser if available; otherwise a phone with hand-held technique 6 inches from the mouth, room with soft furnishings (closet works).
- **Pace**: practice each segment twice before recording. Aim for a **conversational** read, not "newsreader." The brand voice per `CLAUDE.md` is *"supports / explains / highlights"* — keep it lower-energy than typical product demos.
- **Stems**: record **per-segment**, not one continuous take. If segment 3 is solid and segment 5 needs a re-take, you don't lose 3 minutes of work.
- **Buffer silence**: leave ~2 seconds of room tone before and after every take so the editor has matching ambient for crossfades.
- **Don'ts**: no exclamation marks, no rising-intonation questions, no "we" if "OVERRIDE" works in its place. The product is the protagonist, not the team.

---

## Visual asset checklist (all already on disk)

| Asset | Path | Used in segment |
|---|---|---|
| Wordmark (full colour, dark bg) | `assets/brand/logo-on-dark.png` | 1, 7 |
| Demo loop GIF (3.0 MB / 960×540) | `assets/demo.gif` | reference for cursor flow rehearsal |
| Engineer mode card | `assets/screenshots/engineer_mode.png` | 3, 4 |
| Fan mode card | `assets/screenshots/fan-mode.png` | 5 |
| Langflow canvas | `assets/screenshots/langflow-canvas.png` | 6 |
| Architecture diagram | `assets/architecture.png` | 6 |
| Jaeger trace | `assets/screenshots/jaeger-trace.png` | 6 |

For segments 1, 2, 7 the cold-open and closing visuals are still original-generated; coordinate with the designer if any motion graphics are needed beyond the static wordmark + tagline cards.

---

## Per `.bob/rules.md`

This is a planning doc that ships a feature (the recorded video). Per the
"plans are deleted in the same PR that ships the feature" rule, **delete
this file in the same commit that uploads the final voiceover stems** — the
script has done its job by then; the video itself is the durable artifact.
