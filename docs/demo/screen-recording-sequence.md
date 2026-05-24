# OVERRIDE Screen Recording Sequence

Use this as the capture checklist for the 2:55 video. The canonical flow is live-cockpit first, completed debrief second.

## Pre-Flight

1. Start the app with the services needed for the capture:
   ```bash
   podman-compose up override torcs jaeger
   ```
2. Use Chrome at 1280x720 or 1440x900. Hide bookmarks and close unrelated tabs.
3. Open `http://localhost:8000/upload`.
4. Confirm the upload page shows race control, demo fixtures, and captures on disk.
5. Keep a completed live capture ready so the ingest/debrief section does not depend on waiting for a long race during recording.

## Capture Flow

| Step | Time Budget | Action | Capture Goal |
|---:|---:|---|---|
| 1 | 18s | Show generated 2026 energy split graphic and logo card | Set the stakes before any UI |
| 2 | 22s | Cut to telemetry-overload graphic, then `/upload` | Problem is not data volume; it is reasoning |
| 3 | 10s | On `/upload`, verify track/driver/laps and click **Start race** | Judges see a real user action, not terminal work |
| 4 | 28s | Hold on `/cockpit` while telemetry updates | TORCS frame, timing rail, hybrid rail, and live state |
| 5 | 10s | Scroll to AI Race Engineer and toggle Engineer/Fan | Same live moment, two audiences |
| 6 | 8s | Return to `/upload` and click **Ingest** on a completed capture | Live run becomes an analyzable session |
| 7 | 15s | Show parsing state and completed session landing | Pipeline is functional, not mocked |
| 8 | 18s | Hold KPI strip and post-race report | Outcome is summarized for an engineer |
| 9 | 22s | Scroll to recommendation card, expand reasoning chain, frame citation and badges | Explainability and safety are the hero |
| 10 | 18s | Open What-if rail and show before/after diff | Strategy exploration reruns through the pipeline |
| 11 | 12s | Toggle to Fan Mode and hold plain-language recommendation | Fan/broadcast value |
| 12 | 13s | Cut Langflow -> architecture -> Jaeger -> logo | Stack, observability, close |

## Cursor Notes

- Move slowly and intentionally; every click should read on screen.
- Avoid racing through the recommendation section. The citation and badges are the trust proof.
- If a live launch stalls, switch immediately to the already-captured cockpit screenshot/video segment and continue with the completed capture.
- If the TTM forecast is unavailable because the session has fewer than 30 laps, leave the badge visible. It demonstrates graceful degradation.

## Fallback Static Sequence

If live screen recording misbehaves, assemble the same story from these screenshots in order:

1. `temp/screenshots/01-upload.png`
2. `temp/screenshots/05-cockpit.png`
3. `temp/screenshots/06-ai-race-engineer.png`
4. `temp/screenshots/06-ai-race-fan-mode.png`
5. `temp/screenshots/10-ingest-complete-session.png`
6. `temp/screenshots/12-session-details.png`
7. `temp/screenshots/16-recommendation-card-chain-of-reasoning.png`
8. `temp/screenshots/19-what-if-analysis.png`
9. `temp/screenshots/25-fan-mode-recommendation.png`
10. `assets/screenshots/langflow-canvas.png`
11. `assets/architecture.png`
12. `assets/screenshots/jaeger-trace.png`

