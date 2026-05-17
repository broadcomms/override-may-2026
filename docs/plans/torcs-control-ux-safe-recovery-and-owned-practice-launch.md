# TORCS Control UX: Safe Recovery First, Then OVERRIDE-Owned Practice Launch

## Summary
Implement this as a **staged rollout**.

Stage 1 stabilizes operations:
- add **safe simulator recovery** from the existing TORCS control plane
- move the user off “stranded in menu / frozen simulator / manual container command” failure modes
- keep recovery inside the `torcs` container boundary, **not** through Podman from the web app

Stage 2 replaces the manual menu setup:
- make **Upload** the authoritative race setup and launch surface
- make **Cockpit** the live-operation and recovery surface
- hard-lock OVERRIDE to the single supported path:
  `Race -> Practice -> scr_server 1 -> configured track/laps -> start race`
- patch TORCS config and use a narrow deterministic GUI bridge only for the final `Practice -> New Race` launch step

## Implementation Changes

### Stage 1: Operator recovery and runtime controls
- Add a new daemon-level recovery action that:
  - stops any active SCR client
  - kills any stale `torcs-bin`
  - lets the kiosk supervisor relaunch TORCS cleanly
  - waits until the simulator surface is back in a known standby state
  - clears stale daemon state and returns a fresh `idle` control status
- Surface this as **Reset simulator** in Cockpit and as a smaller fallback action on Upload when the control plane is reachable but unhealthy.
- Keep **Stop race** as the normal in-race action; use **Reset simulator** for frozen menu / crashed runtime / bad post-race state.
- Do **not** add a web button that runs `podman-compose up -d --force-recreate torcs` directly. That stays outside the app boundary.
- Do **not** add “shut down the whole app” from the UI in this slice. Replace that need with:
  - stop race
  - reset simulator
  - leave cockpit / return to Upload
- Defer **mute audio** until after recovery is stable. It is lower-value than reset, and WSLg/Pulse behavior is environment-specific.

### Stage 2: OVERRIDE owns the Practice setup flow
- Make **Upload** the authoritative pre-race setup page:
  - track selector
  - laps input
  - 3D cockpit vs headless mode
  - launch CTA
  - simulator status / recovery banner
- Make **Cockpit** the authoritative live-ops page:
  - stop race
  - reset simulator
  - open debrief
  - readonly display of current track / target laps / mode
  - no primary setup editing here
- Remove the current “manual TORCS setup” disclosure from the main user path once Practice ownership ships.
- Keep the supported 3D path constrained to **Practice only**.
- Hard-lock driver selection to:
  - `scr_server 1`
  - current branded car/category pairing already used by the shipped demo path
- Replace user-driven Practice configuration with daemon-owned config patching:
  - patch `practice.xml` for track, category, laps, focused driver, display mode
  - own the track/lap values in OVERRIDE instead of reading them from the TORCS HUD or user memory
- For 3D mode, launch by:
  - ensuring GUI TORCS is running in kiosk mode
  - applying patched `practice.xml`
  - sending a deterministic GUI sequence to reach `Practice -> New Race`
  - waiting for the SCR-ready state
  - spawning the SCR client
- For headless mode, keep the existing quickrace-style daemon path.

### Track metadata and map ownership
- Extend the current track scan beyond `name/category`.
- Extract and cache, at minimum:
  - display name
  - category
  - author
  - description
  - width
  - length
  - pits
  - preview/background asset presence
  - raceline/map asset presence
- Use TORCS-owned files as the source of truth, but surface them as OVERRIDE API data and assets.
- Add track preview support on Upload so the user configures from OVERRIDE instead of the TORCS menu.
- Use existing TORCS `raceline.png` / track assets first; do not attempt custom vector map generation in the first ownership slice.

## Public API / Interface Changes
- Add daemon endpoint:
  - `POST /control/recover`
- Add OVERRIDE proxy endpoint:
  - `POST /api/torcs/recover`
- Extend track listing shape end-to-end:
  - current `TorcsTrack` becomes enriched metadata, not just `name/category`
- Add track asset access from OVERRIDE:
  - either explicit asset endpoints or stable asset URLs returned from the track list response
- Extend start-race request with an explicit launch mode:
  - `cockpit_practice`
  - `headless_quickrace`
- Keep backward compatibility:
  - existing callers without the new mode keep current behavior until UI migration completes
- UI contract:
  - Upload = setup + launch
  - Cockpit = operate + recover
  - manual TORCS menu flow is removed from the primary happy path after Stage 2

## Test Plan
- Daemon tests:
  - `recover` from idle is safe and idempotent
  - `recover` during active race stops SCR first, then resets TORCS runtime
  - practice config patching writes the requested track/laps and preserves `scr_server`
  - enriched track scan returns metadata for installed tracks
- API tests:
  - `POST /api/torcs/recover` proxies cleanly and returns stable status
  - `GET /api/torcs/tracks` returns enriched metadata, not just names
  - `POST /api/torcs/start-race` honors the new launch mode
- UI tests:
  - Upload shows launch controls and recovery banner
  - Cockpit shows reset/stop/debrief actions but not the old setup-led happy path
  - degraded states render actionable recovery messaging
- Manual acceptance:
  - user quits out of TORCS menu after a run, clicks **Reset simulator**, and returns to a clean standby state
  - TORCS freeze/crash is recoverable without shell access
  - Upload-configured track/laps launch a Practice run without requiring the user to navigate the TORCS menus
  - finished race returns to a debrief-ready state without leaving the operator stranded

## Assumptions and Defaults
- Safe recovery means **simulator/runtime recovery inside the existing container**, not Podman control from the web app.
- No UI control for shutting down the `override` app/container in this feature.
- **Mute audio is deferred** until after recovery and Practice ownership are stable.
- Default long-run target becomes **75 laps**, still configurable in the UI.
- The supported product path is a single controlled TORCS mode:
  **Practice with `scr_server 1`**.
- Upload remains the launch/configuration center; Cockpit remains the live-operation center.
