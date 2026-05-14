The Race Control panel isn't showing because your override container is running an image built before the Phase 2 commits landed. The frontend changes (TorcsControlPanel component) and backend changes (proxy endpoints) are both baked into the override container's static bundle + Python — so they need a rebuild.
     
# Rebuild both containers
podman-compose build override
# torcs uses the image as-is + mounts the deamon source via volume
# we just recreate torcs to re-source the env + python files.
podman-compose up -d --force-recreate override torcs
# Wait ~90s for boot for torcs to comeup 

# Confirm deamon is reachable + wiring is good.
curl -sf http://localhost:8000/api/torcs/control-status | jq
# Expect: {"enabled":true,"reachable":true,"active":false,"session_id":null,"detail":null}

# Use the OVERRIDE-side proxy (not the daemon directly) so the stub Session lands
curl -sf -X POST http://localhost:8000/api/torcs/start-race \
    -H 'Content-Type: application/json' \
    -d '{"track":"aalborg","laps":3,"track_name":"Aalborg","notes":"better-fix smoke"}' | j

# The response.session_id is now queryable IMMEDIATELY:
SID=$(curl -sf http://localhost:8000/api/torcs/control-status | jq -r .session_id)
curl -sf http://localhost:8000/api/sessions/$SID | jq '.summary | {session_id, status, session_source, telemetry_file}'
# Expect: status="active", telemetry_file="$SID.jsonl", session_source="torcs_live"

In the browser

  1. Refresh localhost:8000/upload
  2. Click Start race (your TORCS GUI is already running with scr_server driver from before)
  3. The Race Control panel shows Live + a session_id + a "View live →" link
  4. Click View live → — this time you should land on /session/<id> with the LiveTelemetry panel rendering ("Waiting for the
  first lap to complete…")
  5. As the AI driver completes laps, rows populate in the live table
  6. When you're done driving, refresh the upload page → the JSONL appears in "LIVE TORCS DETECTED" → click Ingest →
  7. After ingestion: /session/<id> reloads with status=completed → live panel collapses → engineer dashboard + recommendations
  appear

---
Full test plan — all three phases
  
Phase 1 — Session boundaries + history + comparison

You're already seeing this work. The /sessions screenshot shows 10 captured sessions with per-run files (differenttorcs-live/baseline-1lap vs torcs-live/baseline track IDs, distinct timestamps).
  
Test 1.1 — Per-run filenames

podman exec torcs ls -la /home/student/workspace/gym_torcs/telemetry/
# Expect: multiple files named `run_YYYYMMDDTHHMMSS.jsonl` (the directory-mode
# auto-generation) PLUS the older baseline.jsonl
  
Test 1.2 — Session metadata embedded at ingest

Click "Ingest →" on the baseline-1lap row → lands on the session detail page. Then:
  
SID=$(curl -sf http://localhost:8000/api/sessions | jq -r '.sessions[0].session_id')
curl -sf http://localhost:8000/api/sessions/$SID | jq '.summary | {session_source, status, track_name, target_laps, started_at, completed_at, telemetry_file}'

# Expect: session_source="torcs_live", status="completed", started_at + completed_at populated,

# telemetry_file="baseline-1lap.jsonl"

Test 1.3 — Session comparison
  
On /sessions:
1. Check the boxes on any two rows
2. The "Compare" button at the top right enables
3. Click it → navigates to /sessions/compare?a=...&b=...
4. See side-by-side panels with inline deltas (lap count diff, harvest/deploy/zone deltas in green/red)
5. Click "Open debrief →" on either panel to drill into that session
  
Phase 3 — SSE live telemetry stream
  
This requires an active session (one whose underlying JSONL is still being written to). The cleanest way to demonstrate it
without Phase 2:

Test 3.1 — Start a long race from inside the noVNC terminal

In the noVNC browser tab → open a terminal (Applications > Terminal Emulator or right-click desktop):
  
cd /home/student/workspace/gym_torcs
OVERRIDE_LOG_TELEMETRY=/home/student/workspace/gym_torcs/telemetry/ \
    python3 torcs_jm_par.py
# This starts a long-running TORCS race. Leave it running.
  
Test 3.2 — Ingest the in-progress capture mid-race
  
Wait ~30s for TORCS to launch and a lap or two of telemetry to land. Back in your OVERRIDE browser tab on /upload:
- The "LIVE TORCS DETECTED" banner shows the new run_*.jsonl file
- Click "Ingest →" — lands on the session detail page
  
Test 3.3 — Verify SSE stream

The ingested session's status is completed by default (Phase 3's active status comes from the Phase 2 control daemon path; the bare-terminal path doesn't set it). To see the live panel, you need Phase 2 — proceed to that section.
  
Alternative: raw curl SSE test (works without Phase 2)
  
To prove the SSE endpoint itself works, manually patch the session's status:
  
SID=$(curl -sf http://localhost:8000/api/sessions | jq -r '.sessions[0].session_id')
# Tail the SSE stream:
curl -N http://localhost:8000/api/sessions/$SID/stream
# Expect: "data: {\"event\":\"connected\",...}" then either lap events
# (if file is still growing) or "data: {\"event\":\"race_ended\",...}"
# within ~10s (file-stall heuristic)
  
Phase 2 — Start/Stop race + LiveTelemetry end-to-end

After the rebuild above, this is the polished flow that ties everything together.

Test 2.1 — Control plane visible on /upload

Refresh localhost:8000/upload. Expected new section above LIVE TORCS DETECTED:

┌─ RACE CONTROL ─────────────────────────  Idle ┐
│ [Start race]  [Stop race]                     │
└────────────────────────────────────────────────┘

The badge reads Idle when daemon is reachable + no race active.
  
Test 2.2 — Start a race from the UI

Click Start race. Expected:
1. Button greys out (busy state)
2. Within ~2s, the badge flips to Live with a session_id shown
3. A message appears: "Race started — pid XXXX, session_id s_torcs_live_NNN_abcd. Drive in noVNC at http://localhost:6080..."
4. The Stop race button enables
  
Now look at the noVNC tab — TORCS should be running, the AI driver visible on the track.

Test 2.3 — Navigate to the active session's live view

Click the View live → shortcut next to the session_id. This opens /session/<id> where the LiveTelemetry panel appears at the
top of the page (above the energy curve and recommendation cards), pulsing the green "Live" dot and showing per-lap stats as
each lap completes:

┌─ ● LIVE RACE TELEMETRY                  Live ┐
│ Waiting for the first lap to complete…       │
└───────────────────────────────────────────────┘

Once Lap 1 finishes (~30-60s), the table populates with lap_time_s, avg/max speed, harvest/deploy MJ, SoC %. Newest lap at top,the table grows as more laps complete.
  
Test 2.4 — Stop the race from the UI

Back on /upload, click Stop race. Expected:
1. Daemon receives SIGTERM, gym_torcs gets 5s grace
2. Status flips to Idle, button greys out
3. Brief message: "Race stopped (exit -15)."
  
In the noVNC tab, TORCS process is gone.
  
Test 2.5 — Daemon idempotency
  
Click Stop race again with nothing running. Should produce "No active race." with no error.
  
Test 2.6 — Verify session lifecycle propagated

Refresh /sessions. The session you just ran should appear, marked with the live chip in the source column.

Phase 2 + 3 combined — the full "judges don't touch the terminal" flow

This is the polished demo flow Segment 3 of the video will show:
  
1. Open localhost:8000/upload and localhost:6080/vnc.html side by side
2. Click Start race in OVERRIDE → TORCS launches in noVNC, badge flips to Live
3. Click View live → to navigate to the active session's page
4. Watch lap rows populate in real time
5. Click Stop race mid-race OR let it complete naturally
6. Live panel fades out, replaced by the engineer dashboard + recommendations
  
That's the full Phase 1 + Phase 2 + Phase 3 integration. If this flow works end-to-end in ~5 minutes on your hardware, all three phases are verified shipped. 

If anything in Phase 2 misbehaves
  
Most common cause: the TORCS_CONTROL_SECRET value in your .env got changed between the daemon's first boot and the most recent recreate. The two containers must share the exact same secret. To verify:

podman exec torcs sh -c 'echo "torcs:    ${#TORCS_CONTROL_SECRET} chars"'
podman exec override sh -c 'echo "override: ${#TORCS_CONTROL_SECRET} chars"'
# Both should print 43 (URL-safe token_urlsafe(32))

If they differ, podman-compose up -d --force-recreate torcs override to re-read the env.