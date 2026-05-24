# OVERRIDE - HTTP API

This document describes the shipped FastAPI surface in [`api/main.py`](../api/main.py). Schema shapes are documented in [`04-schema.md`](./04-schema.md).

## 1. Service overview

- Runtime: Python 3.12 + FastAPI + Uvicorn
- Default local URL: `http://localhost:8000`
- Container URL: same origin serves both `/api/*` and the built SPA
- Authentication: none on the OVERRIDE app surface itself
- CORS: `OVERRIDE_UI_ORIGIN` only
- Request correlation: every response carries `X-Request-Id`

Two important architectural notes:

1. Langflow is not the production API runtime.
2. Fan Mode and what-if are follow-up reads on top of the same persisted session, not separate pipeline families.

## 2. Endpoint map

### Metadata

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Liveness probe |
| `GET` | `/api/version` | Build and model metadata |
| `GET` | `/api/regulation-source` | Canonical regulation-source metadata when verified |

### Sessions and debriefs

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/sessions` | Upload replay and run the full pipeline |
| `GET` | `/api/sessions` | Paginated session history |
| `GET` | `/api/sessions/{session_id}` | Load one full `Session` |
| `GET` | `/api/sessions/{session_id}/report` | Load or build the cached `RaceReport` |
| `GET` | `/api/sessions/{session_id}/laps/{lap_number}` | Load or build one cached `LapAnalysis` |
| `POST` | `/api/sessions/{session_id}/copilot` | Ask the stateless session copilot a grounded question |
| `POST` | `/api/sessions/{session_id}/copilot/stream` | Stream a grounded copilot answer into the chat widget |
| `GET` | `/api/sessions/{session_id}/zones/{zone_id}` | Load one `Recommendation`; lazy fan-mode fill via `mode=fan|both` |
| `POST` | `/api/sessions/{session_id}/what-if` | Re-run the pipeline on a perturbation |
| `DELETE` | `/api/sessions/{session_id}` | Delete one session, optionally its source telemetry JSONL |
| `POST` | `/api/sessions/bulk-delete` | Delete many sessions in one call |

### Live telemetry and captures

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/sessions/{session_id}/stream` | SSE stream for an active TORCS-backed session |
| `GET` | `/api/torcs-status` | Paginated list of capture files on the shared telemetry volume |
| `POST` | `/api/sessions/torcs-live` | Parse one capture file and persist the completed session |
| `DELETE` | `/api/torcs/runs/{run_id}` | Delete one capture file from the shared telemetry volume |

### TORCS control plane

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/torcs/control-status` | Surface daemon config/reachability/state |
| `GET` | `/api/torcs/tracks` | List available TORCS tracks |
| `GET` | `/api/torcs/tracks/{category}/{track_name}/assets/{kind}` | Proxy preview/map art |
| `POST` | `/api/torcs/start-race` | Create active stub session and ask the daemon to launch a race |
| `POST` | `/api/torcs/stop-race` | Stop the active race |
| `POST` | `/api/torcs/recover` | Reset the simulator/daemon to a stable state |

### TORCS driver profiles

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/torcs/driver-profiles` | List driver profiles |
| `POST` | `/api/torcs/driver-profiles` | Create a new profile |
| `POST` | `/api/torcs/driver-profiles/validate` | Validate a config payload |
| `GET` | `/api/torcs/driver-profiles/{profile_id}` | Load one profile |
| `PATCH` | `/api/torcs/driver-profiles/{profile_id}` | Update one profile |
| `DELETE` | `/api/torcs/driver-profiles/{profile_id}` | Delete one user-created profile |
| `POST` | `/api/torcs/driver-profiles/{profile_id}/duplicate` | Duplicate an existing profile |

## 3. Intentionally absent endpoints

The current app does not expose the following older/planned routes:

- `GET /api/sessions/{id}/laps`
- `GET /api/sessions/{id}/forecast`
- `GET /api/sessions/{id}/zones`
- `GET /api/sessions/{id}/zones/{zone_id}/stream`

Those views are served through the full `Session` payload or the live SSE surface instead.

## 4. Success and error conventions

- Success responses return the schema directly, not an envelope.
- Errors return `ApiError`.
- `GET /api/torcs/control-status` and `GET /api/torcs-status` are designed to remain `200` even when the TORCS side is unavailable; the UI branches on payload flags rather than transport failures.

Important status codes:

| Status | Meaning |
|---|---|
| `200` | Successful read or idempotent action |
| `201` | Resource created or launch accepted |
| `204` | Successful delete |
| `400` | Bad upload or parse failure |
| `404` | Missing session, zone, run, or regulation-source metadata |
| `409` | Active race conflict or read-only profile mutation |
| `413` | Upload exceeds `MAX_UPLOAD_SIZE_MB` |
| `422` | Request validation failure |
| `500` | Unexpected internal/model parse failure |
| `502` | TORCS daemon responded with an unexpected failure |
| `503` | watsonx unavailable or TORCS control plane unavailable/unreachable |

## 5. Replay upload flow

### `POST /api/sessions`

Multipart fields:

| Field | Type | Notes |
|---|---|---|
| `file` | binary | Required |
| `source` | `torcs` or `fastf1` | Required |
| `track_id` | string | Optional |
| `soc_max` | float | Optional, defaults to `4.0` |

Behavior:

1. Enforces the configured upload-size limit.
2. Parses TORCS uploads by content sniffing, not just filename suffix.
3. Runs the full pipeline.
4. Persists the session to disk.
5. Returns the full `Session`.

Failure highlights:
- `PARSE_FAILED` if the parser cannot derive lap rows.
- `MODEL_UNAVAILABLE` when watsonx credentials, quota, or connectivity fail.

## 6. Session history and detail

### `GET /api/sessions`

Query params:
- `limit`: default `50`, max `200`
- `offset`: default `0`

Behavior:
- Sorted newest first
- Returns `SessionListResponse`
- Actively enriches `ACTIVE` TORCS-live sessions with current lap count from their telemetry file

### `GET /api/sessions/{session_id}`

Returns the persisted full `Session`.

### `GET /api/sessions/{session_id}/report`

Behavior:
- loads `data/sessions/{session_id}/report.json` when present
- otherwise builds a deterministic `RaceReport`, caches it, and returns it

### `GET /api/sessions/{session_id}/laps/{lap_number}`

Behavior:
- loads `data/sessions/{session_id}/laps/{lap_number}.json` when present
- otherwise builds a deterministic `LapAnalysis`, caches it, and returns it
- returns `404` when the requested lap does not exist in the session

### `POST /api/sessions/{session_id}/copilot`

Request body:

```json
{
  "question": "Compare lap 2 and lap 4",
  "recent_turns": [
    {
      "role": "user",
      "content": "Why was conservative mode recommended?",
      "timestamp": "2026-05-20T12:00:00+00:00"
    }
  ],
  "context": {
    "mode": "live_race",
    "lap_number": 3,
    "live": {
      "latest_snapshot": null,
      "completed_laps": [],
      "insights": [],
      "race_state": "active"
    }
  }
}
```

Behavior:
- reads the persisted session plus optional client-supplied UI context; no transcript persistence on the server in this milestone
- accepts `context.mode` values `session`, `lap`, or `live_race`
- when `context.mode="live_race"`, the client may attach the latest snapshot, recent closed laps, live insights, and race state from the shared live stream
- retrieves focused session/live context, routes the prompt through Granite-backed orchestration, and validates a structured `CopilotAnswer`
- returns `engine="granite"` on the main path and `engine="deterministic"` only when model output cannot be structured
- returns grounded answer text, supporting lap links, confidence, and follow-up suggestions
- returns `404` when the session does not exist

### `POST /api/sessions/{session_id}/copilot/stream`

Request body:
- same shape as `POST /api/sessions/{session_id}/copilot`

Behavior:
- opens a `text/event-stream` response for the shell-level race-engineer widget
- emits `start`, then one or more `delta` events, then a final `complete` event carrying the full structured `CopilotAnswer`
- emits `error` if the streamed request fails after the event stream has already opened
- uses the same Granite-backed orchestration and deterministic fallback rules as the non-streaming endpoint
- remains stateless on the server; transcript slice + current route context still come from the client

### `GET /api/sessions/{session_id}/zones/{zone_id}`

Query param:
- `mode`: `engineer` | `fan` | `both`, default `engineer`

Behavior:
- `engineer` strips any fan payload from the response
- `fan` and `both` lazily translate and persist `recommendation.fan`
- fan writes are serialized per session to avoid concurrent lost updates

## 7. What-if API

### `POST /api/sessions/{session_id}/what-if`

Accepts `WhatIfRequest` and returns `WhatIfResult`.

Behavior:
- Validates target zone existence when the perturbation requires one
- Caches results under `data/sessions/{session_id}/whatif/{cache_key}.json`
- Reuses the full production pipeline rather than a second reasoning path

Current perturbations:
- `delay_first_deploy`
- `skip_harvest_zone`
- `extend_override`

## 8. Live telemetry stream

### `GET /api/sessions/{session_id}/stream`

Server-Sent Events for live TORCS sessions.

Event shapes:

```json
{"event":"connected","session_id":"s_torcs_live_...","status":"active"}
{"event":"snapshot","snapshot":{...}}
{"event":"insight","insight":{"insight_id":"li_energy_pressure_v1_l3_s2","rule_id":"energy_pressure_v1","kind":"strategy_recommendation","severity":"high","headline":"Energy pressure building","message":"...","recommended_action":"...","confidence":"high","evidence":["..."],"lap":3,"sector":2}}
{"event":"lap","lap":1,"lap_time_s":...}
{"event":"no_telemetry","message":"..."}
{"event":"race_ended","reason":"file_stall","total_laps":5}
```

Important behavior:
- Waits briefly for a telemetry file when an active stub session was just launched
- Deduplicates snapshots by a compact signature
- Emits deterministic live `insight` events and suppresses consecutive duplicates for the same `insight_id` when severity/message do not change
- Detects end-of-race by file-stall heuristics
- Returns `404` only when the session itself does not exist

## 9. TORCS capture ingest

### `GET /api/torcs-status`

Query params:
- `limit`
- `offset`

Returns:
- `available`
- `runs`
- `total`
- `limit`
- `offset`

Each run includes:
- `run_id`
- `size_bytes`
- `lap_count_estimate`
- `started_at`
- `last_written_at`
- `duration_seconds`
- `ingested_session_id`

### `POST /api/sessions/torcs-live`

Accepts:

```json
{
  "run_id": "s_torcs_live_...",
  "track_name": "Aalborg",
  "target_laps": 75,
  "notes": "optional"
}
```

Behavior:
- Reads `OVERRIDE_TELEMETRY_DIR/<run_id>.jsonl`
- Parses it through `parse_torcs_session()`
- Re-runs the full pipeline
- If the `run_id` matches a previously-created active stub session, updates that session instead of creating a new one

### `DELETE /api/torcs/runs/{run_id}`

- Idempotent
- Deletes only the capture file, not any already-ingested session

## 10. TORCS control plane

### `GET /api/torcs/control-status`

Always `200`, returning `TorcsControlPlaneStatus`.

Use this endpoint to understand:
- whether the control plane is configured
- whether the daemon is reachable
- whether the daemon is still warming up
- current race state
- active session ID
- last failure detail

### `POST /api/torcs/start-race`

Accepts `TorcsStartRaceRequest`.

Behavior:

1. Resolves the requested driver profile.
2. Writes an `ACTIVE` stub `Session` on disk before launch.
3. Calls the TORCS daemon.
4. If the daemon launch succeeds, returns session and launch metadata.
5. If the daemon is transiently unreachable but the same session appears in daemon status or the telemetry file materializes, reconciles instead of failing immediately.

Returned payload includes:
- `session_id`
- `pid`
- `torcs_pid`
- `telemetry_dir`
- `track`
- `laps`
- `launch_mode`
- `state`
- driver-profile and note hints for the UI

### `POST /api/torcs/stop-race`

- Idempotent
- Returns the daemon payload directly

### `POST /api/torcs/recover`

- Asks the daemon to restore a stable simulator state
- Used when the GUI/driver side needs an operator-safe reset

### `GET /api/torcs/tracks`

- Returns empty list when the control plane is disabled or unreachable
- Otherwise proxies daemon track metadata, including preview/map asset URLs when available

### `GET /api/torcs/tracks/{category}/{track_name}/assets/{kind}`

- `kind` is `preview` or `map`
- Proxies binary image content from the daemon

## 11. TORCS driver profiles

Profiles are backed by:
- shipped read-only defaults in `config/torcs_driver_profiles/`
- mutable local storage in `data/torcs_driver_profiles/`

Important semantics:
- shipped defaults are read-only and return `READ_ONLY_PROFILE` on mutation
- `POST /duplicate` always creates a mutable copy
- `POST /validate` returns the normalized `TorcsDriverConfigWire` shape on success

## 12. Errors worth handling explicitly in the UI

- `CONTROL_DISABLED`: hide launch controls and explain missing config
- `CONTROL_UNREACHABLE`: show daemon warm-up or connectivity failure
- `RACE_ACTIVE`: tell the operator to stop the current race first
- `READ_ONLY_PROFILE`: prevent mutating shipped defaults
- `PERSISTENCE_FAILED`: live-session launch contract could not be written locally
- `MODEL_UNAVAILABLE`: watsonx path unavailable

## 13. Verification state

Verified against the current repo surface:
- endpoint implementations in [`api/main.py`](../api/main.py)
- shared schemas in [`ingest/schema.py`](../ingest/schema.py)
- frontend client usage in [`ui/src/api/client.ts`](../ui/src/api/client.ts)
