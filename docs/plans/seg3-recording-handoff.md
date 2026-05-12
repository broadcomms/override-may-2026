# Segment 3 retake — recording handoff (v6 plan task 2.9)

> **Plan-file lifecycle:** delete this in the same PR as Week 3 step 3.6
> (the full video re-record). It documents the click flow for the user-side
> recording of Segment 3's retake. Headless verification was done programmatically;
> the actual screen capture requires user hands on the keyboard.

## Why 2.9 is "pre-record" instead of "record"

Per the v6 plan task 2.9 ("Pre-record Segment 3 retake (~1h, end of Week 2)"):

> *"End of Week 2, immediately after FR-8 UI lands. Record the what-if click
> flow once. If anything looks off (cross-fade, layout, timing), discover it
> now — not during the Week 3 video block when retake time is at a premium.
> The retake itself is cheap; the discovery window is what matters."*

**The goal is discovery, not the final Segment 3 video** — that lands in
Week 3 step 3.6. The pre-record proves the click flow works end-to-end
with the new fixture + WhatIfPanel UI so any layout / timing / cross-fade
issues surface a week before they could threaten the video schedule.

## What was verified programmatically (2.9 status: discovery complete)

Headless-Chrome screenshot at 1440×900 against `vite dev` (fixture mode),
URL `http://localhost:3000/session/s_torcs_engineer_demo?fixture=1` —
captured 2026-05-11 23:01 UTC. Renders cleanly with:

| Element | Verified |
|---|---|
| Header: `OVERRIDE · torcs-baseline · 1 laps · uploaded ...` | ✓ |
| Session note (italic muted): the regeneration explanation | ✓ |
| Mode toggle: Engineer (active, orange) / Fan | ✓ |
| Energy Curve panel: empty observed line (1 lap), forecast badge `"Forecast unavailable — TTM-R2 deferred to v1.1"` | ✓ |
| Zone heatmap: S3 cell colored HIGH severity (red), L1 column label | ✓ |
| Recommendations (2) header + first card visible | ✓ |
| First card: `L1 · S3 · late-recharge · high severity`, with `CAUSE` field starting `"Lap 1 harvested 3.77 MJ when the battery was already at full charge (0 MJ headroom)"` | ✓ |

What's NOT verified in headless (requires interaction):
- Click the "What if…" rail expander
- Select a perturbation radio
- Click "Run ▶"
- Watch WhatIfDiff render below the card
- Cross-fade timing
- Dismiss flow

## Exact click sequence for the recording

**Setup** (one terminal each):

```bash
# Terminal 1: backend (the API isn't strictly needed in fixture mode but keep it for parity)
.venv/bin/uvicorn api.main:app --port 8000 --log-level warning

# Terminal 2: UI dev server (fixture mode)
cd ui && VITE_USE_FIXTURE=1 npm run dev

# Browser: open
http://localhost:3000/session/s_torcs_engineer_demo?fixture=1
```

**Recording target:** 1080p or higher, 60fps, screen-recorder of choice (OBS,
ScreenStudio, native Mac/Windows screen capture). Mouse cursor visible. Aim
for **one clean take of ~30–45 seconds** covering the click flow below.
Re-take freely until the cursor work is smooth.

**Click choreography** (~30–45s total):

| Time | Action | What you should see |
|---|---|---|
| 0:00–0:03 | Page loads at `/session/s_torcs_engineer_demo?fixture=1` | Energy curve + zone heatmap + two recommendation cards |
| 0:03–0:08 | Scroll the first recommendation card into view (`L1 · S3 · late-recharge`) | Card visible with cause/consequence/recommendation/citation |
| 0:08–0:12 | Hover the citation block | Watch the 3px granite-blue left border highlight |
| 0:12–0:18 | Click the `▸ What if…` disclosure at the bottom of the card | Rail opens with three radios + "Run ▶" button |
| 0:18–0:22 | Click the `skip_harvest_zone` radio | Radio selection animates to that row |
| 0:22–0:27 | Click `Run ▶` | Loading banner appears: "Running what-if scenario…" |
| 0:27–0:32 | Wait for fixture synthesis to complete (~400 ms) | `WhatIfDiff` renders below the card |
| 0:32–0:40 | Pan to the WhatIfDiff Before/After cards | Before: original metrics (red↓ on harvest_mj). After: harvest = 0.00 MJ with the orange "After · z_lrch_full_l1_s3" header |
| 0:40–0:45 | Read the warning banner with the energy-LOST note | "zone 'z_lrch_full_l1_s3': harvest of 3.77 MJ on lap 1 LOST..." |

## What to watch for (discovery checklist)

The whole point of 2.9 is to surface issues NOW. Score each item green / red:

| Check | Pass criteria | If red → |
|---|---|---|
| Cross-fade timing on the disclosure expand | Feels snappy (~240 ms), not laggy | Check `--motion-mode` token in `ui/src/styles/tokens.css`; bump if too slow |
| WhatIfDiff side-by-side layout legible at 1080p | Both Before + After cards visible without horizontal scroll | Reduce metric-grid column count from 3→2, or use `grid-cols-1 lg:grid-cols-2` |
| Color tone on metric deltas (red ↓ green ↑) | High contrast against dark surface | Confirm `--color-danger` / `--color-success` from tokens.css |
| Loading banner length matches synthesis delay (~400 ms) | Banner appears + disappears smoothly | If too brief, bump fixture-mode `setTimeout` in `client.ts:runWhatIf` |
| Note banner readability | The "harvest LOST" text is legible without zoom | Check warning/5 tint contrast; bump opacity if illegible |
| Cursor path | Smooth movement, no jitter | OBS / recorder smoothing setting |
| Total run-time | 30–45 s | If longer, you're hovering too long — re-take |

## Save the take

```bash
mkdir -p recordings/seg3-pre-record
# Save as <recording_app>'s default format; .mov or .mp4
mv ~/Downloads/<your-recording>.mov recordings/seg3-pre-record/take-1.mov
```

`recordings/` is `.dockerignore`'d and the v6 plan's 3.4 git policy block
will set the final `.gitignore` rule for `*.mov` masters during Week 3.
For now, leave the file on disk; the Week 3 work decides whether to track
it (final.mp4 only) or gitignore everything.

## What's left for Week 3 step 3.6 (the real video re-record)

This pre-record is just **Segment 3**. The full 2:55 video needs all seven
segments re-recorded with the updated script — that's Week 3's 12h block
including voiceover, edit timeline, MP4 export, YouTube upload. The
docs/plans/video-script.md Segment 3 block needs updating to include the
what-if beat (currently doesn't mention it); that text update lands in 3.6,
not here.

## Status

- ✓ Discovery via headless verification (`/tmp/seg3_captures/01-session-engineer.png`)
- ✓ Click sequence documented above
- ✓ Watch-for checklist enumerated
- ⏳ User-side recording (depends on screen-capture hands)
- ⏳ docs/plans/video-script.md update (Week 3 step 3.6 — final video)
