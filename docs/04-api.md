# OVERRIDE — HTTP API

> The contract between the OVERRIDE Next.js (or Vite) UI and the FastAPI production runtime. All request and response shapes are defined in [`04-schema.md`](./04-schema.md); this document defines endpoints, semantics, and error behavior.

---

## 1. Service overview

- **Runtime**: Python 3.11 + FastAPI + Uvicorn.
- **Base URL (dev)**: `http://localhost:8000`.
- **Base URL (compose)**: `http://api:8000` from inside the Docker network; the Next.js app proxies via `/api/*`.
- **Authentication**: **none.** OVERRIDE is a single-user, replay-first tool with no accounts and no PII. If multi-user becomes a concern, an API-key header is the planned migration path; see §10.
- **Content type**: `application/json` everywhere except `POST /api/sessions` (multipart) and the optional SSE streaming endpoint.
- **CORS**: dev allows `http://localhost:3000`; prod allows the configured `OVERRIDE_UI_ORIGIN` env var only.

---

## 2. Path layout

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/api/health` | Liveness probe |
| `GET`  | `/api/version` | Build + model versions |
| `POST` | `/api/sessions` | Upload a replay; create a session |
| `GET`  | `/api/sessions` | List session summaries (most recent first) |
| `GET`  | `/api/sessions/{session_id}` | Full debrief for one session |
| `GET`  | `/api/sessions/{session_id}/laps` | Lap-level features (chart data) |
| `GET`  | `/api/sessions/{session_id}/forecast` | Forecast object, or 404-with-reason if unavailable |
| `GET`  | `/api/sessions/{session_id}/zones` | All recommendations for the session |
| `GET`  | `/api/sessions/{session_id}/zones/{zone_id}` | One recommendation, full detail |
| `GET`  | `/api/sessions/{session_id}/zones/{zone_id}/stream` | Optional SSE stream of reasoning generation |
| `POST` | `/api/sessions/{session_id}/whatif` | Run a what-if perturbation |
| `POST` | `/api/sessions/torcs-live` | Ingest a JSONL capture from the shared TORCS-telemetry volume |
| `GET`  | `/api/torcs-status` | Discover what TORCS runs are available on the shared volume |
| `GET`  | `/api/sessions/{session_id}/stream` | Live per-lap SSE stream for an `active` session |
| `GET`  | `/api/regulation-source` | The canonical source metadata for the deployed regulation extraction |
| `DELETE` | `/api/sessions/{session_id}` | Remove a session (local cleanup) |

All `GET` responses are cacheable for 5 minutes by default (`Cache-Control: max-age=300, private`); the upload and what-if responses are not cacheable.

---

## 3. Standard response envelope

OVERRIDE does not wrap success responses — endpoints return the schema directly. Errors return `ApiError` from [`04-schema.md` §12](./04-schema.md#12-errors) with the appropriate HTTP status. Unknown-resource 404s use `error_code: "NOT_FOUND"`.

| Status | When |
|---|---|
| `200` | Successful read |
| `201` | Resource created (only `POST /api/sessions`) |
| `202` | Accepted but not yet ready (reserved; not used in v1) |
| `204` | Successful delete |
| `400` | `INVALID_FILE_FORMAT`, `PARSE_FAILED` |
| `404` | Session or zone not found, or forecast not available |
| `413` | `FILE_TOO_LARGE` |
| `422` | Validation error from FastAPI request parsing |
| `429` | `RATE_LIMITED` (reserved; see §9) |
| `500` | `INTERNAL_ERROR` |
| `503` | `MODEL_UNAVAILABLE` (watsonx.ai unreachable / auth failed / quota exceeded, or HF TTM-R2 missing) |

Every response carries `X-Request-Id` (also echoed inside `ApiError.request_id`).

---

## 4. Endpoints

### 4.1 `GET /api/health`

Liveness probe. No external dependencies.

**Response 200**

```json
{
  "status": "ok",
  "uptime_s": 18432.5
}
```

### 4.2 `GET /api/version`

Surfaces the locked model versions for transparency in the demo.

**Response 200**

```json
{
  "build": "v0.1.0",
  "git_sha": "abc1234",
  "models": {
    "runtime": "watsonx",
    "watsonx_region": "us-south",
    "granite_instruct": "ibm/granite-4-h-small",
    "granite_guardian": "ibm/granite-guardian-3-8b",
    "granite_ttm_r2": "ibm-granite/granite-timeseries-ttm-r2@<revision>"
  },
  "regulation_source_present": true
}
```

`regulation_source_present` is `true` once verification gate **G-4** has passed and a `RegulationSource` is configured.

### 4.3 `POST /api/sessions`

Upload a replay. Multipart form. Triggers the full pipeline synchronously: ingest → detect → forecast (optional) → ground → reason → validate → guardian.

**Request**

| Form field | Type | Notes |
|---|---|---|
| `file` | binary | `.json` (TORCS) or `.parquet` / `.csv` (FastF1 export) |
| `source` | `"torcs" \| "fastf1"` | declared explicitly; never sniffed |
| `track_id` | string, optional | informational only |

**Limits**

- Max upload size: **25 MB** (returned as `413 FILE_TOO_LARGE` if exceeded).
- Max laps per session: **120** (silently truncated to the most recent 120, with a `note` in `SessionSummary`).
- Per-IP concurrency: **2 in-flight uploads**. Excess returns `429 RATE_LIMITED`.

**Response 201** — full `Session` per [`04-schema.md` §11](./04-schema.md#11-api-surface-types). Median latency target: **< 30 s**, the figure quoted in the README/abstract. Worst-case timeout: 120 s.

**Errors**

- `400 INVALID_FILE_FORMAT` — `source` does not match the file's actual format.
- `400 PARSE_FAILED` — file passed format check but the parser could not derive a valid `LapFeatures` row for any lap.
- `413 FILE_TOO_LARGE`.
- `429 RATE_LIMITED`.
- `503 MODEL_UNAVAILABLE` — watsonx.ai unreachable, auth failure, quota exceeded, or HuggingFace TTM-R2 missing locally.

**Sample success response**

```json
{
  "summary": {
    "session_id": "s_20260512_a4f9",
    "uploaded_at": "2026-05-12T14:31:08Z",
    "source": "torcs",
    "lap_count": 47,
    "forecast_available": true,
    "zone_count": 3,
    "track_id": "monza"
  },
  "laps": [ /* LapFeatures × 47 */ ],
  "forecast": { /* Forecast or null */ },
  "recommendations": [ /* Recommendation × 3, ordered by lap_number */ ],
  "regulation_source": { /* RegulationSource */ }
}
```

### 4.4 `GET /api/sessions`

Lists `SessionSummary` objects sorted by `uploaded_at` descending. Wired
in Phase 1 (was deferred to Tier 2 in earlier v6 plan); backs the Session
History UI at `/sessions`.

**Query parameters**

| Param | Type | Default | Notes |
|---|---|---|---|
| `limit` | int | `50` | clamped to `[1, 200]`; `> 200` returns `422` |
| `offset` | int | `0` | `>= 0`; `< 0` returns `422` |

**Response 200** — `SessionListResponse`:

```json
{
  "sessions": [ /* SessionSummary × N (newest first) */ ],
  "total": 47,
  "limit": 50,
  "offset": 0
}
```

Each `SessionSummary` includes the Phase 1 lifecycle fields documented
in [`04-schema.md` §11](./04-schema.md#11-api-surface-types): `session_source`
(`upload` | `torcs_live`), `status` (`completed` | `active` | `cancelled`),
plus optional `track_name`, `target_laps`, `started_at`, `completed_at`,
`telemetry_file`. Sessions persisted before Phase 1 inherit `session_source=upload`
and `status=completed` defaults — backward-compatible.

### 4.5 `GET /api/sessions/{session_id}`

Full `Session` per [`04-schema.md` §11](./04-schema.md#11-api-surface-types). Same shape as `POST /api/sessions` 201 response. Unknown `session_id` → `404` with `error_code: "NOT_FOUND"`.

### 4.6 `GET /api/sessions/{session_id}/laps`

Lap-level data only, optimized for chart rendering. Returned without recommendations or forecast to keep payloads small.

**Response 200** — `LapsResponse` per [`04-schema.md` §11](./04-schema.md#11-api-surface-types).

```json
{
  "session_id": "s_20260512_a4f9",
  "laps": [ /* LapFeatures × N */ ]
}
```

### 4.7 `GET /api/sessions/{session_id}/forecast`

**Response 200** — `Forecast` per [`04-schema.md` §5](./04-schema.md#5-forecasting).

**Response 404** — `ApiError` with `error_code: "FORECAST_UNAVAILABLE"`. The body's `message` is *"Forecast unavailable for this session."* The `detail` field carries the specific reason — one of:

- `"insufficient_laps: TTM-R2 requires at least 30 laps; this session has N."`
- `"low_confidence: prediction-interval width exceeded threshold."`

The UI uses `message` for the headline empty state and may surface `detail` in a tooltip. Do not localize without coordinating with the UI.

The 404 here is intentional: the forecast resource genuinely does not exist for this session. It is **not** a server error.

### 4.8 `GET /api/sessions/{session_id}/zones`

All recommendations.

**Response 200** — `ZonesResponse` per [`04-schema.md` §11](./04-schema.md#11-api-surface-types).

```json
{
  "session_id": "s_20260512_a4f9",
  "recommendations": [ /* Recommendation × N */ ],
  "regulation_source": { /* RegulationSource or null */ }
}
```

### 4.9 `GET /api/sessions/{session_id}/zones/{zone_id}`

One recommendation in full.

**Query parameters**

| Param | Type | Default | Notes |
|---|---|---|---|
| `mode` | `"engineer" \| "fan" \| "both"` | `"engineer"` | controls whether `recommendation.fan` is populated |

**Response 200** — `Recommendation`. When `mode != "engineer"`, the response is generated through `core/fan_mode.py` synchronously; latency is dominated by the LLM call (~2–5 s).

### 4.10 `GET /api/sessions/{session_id}/zones/{zone_id}/stream` (optional)

Server-Sent Events stream of the Granite reasoning generation, intended for the demo recording. Off by default; gated on env var `OVERRIDE_ENABLE_SSE=1`.

**Event types**

```
event: token
data: {"text": "Battery"}

event: token
data: {"text": " state"}

event: done
data: {"recommendation_id": "z_t16_l23"}
```

The final `done` event signals that the full `Recommendation` is now retrievable via §4.9. Nothing in the stream is normative — clients that don't need streaming use §4.9 directly.

### 4.11 `POST /api/sessions/{session_id}/whatif`

Run a perturbation against one zone.

**Request body** — `WhatIfRequest` per [`04-schema.md` §11](./04-schema.md#11-api-surface-types).

```json
{
  "zone_id": "z_t16_l23",
  "parameter": "delay_first_deploy",
  "delta": 1
}
```

**Response 200** — `WhatIfResult`. The full pipeline runs on the perturbed zone, so the response includes both passes' outcomes. A what-if that fails Pass 1 or Pass 2 is **returned**, not hidden — the UI shows the failure inline.

### 4.12 `POST /api/sessions/torcs-live`

Ingest a JSONL telemetry capture from the shared `torcs-telemetry` named volume (mounted at `/app/data/telemetry/` inside the override container, written by `gym_torcs/torcs_jm_par.py` from inside the torcs container when `OVERRIDE_LOG_TELEMETRY` is set). Avoids the multipart-upload path for the live-driving workflow — judges drive in noVNC at `:6080`, the JSONL lands in the volume, and one POST creates a Session from the freshest run.

**Request body** (`application/json`)

```json
{
  "run_id": "baseline",
  "track_name": "Monza",
  "target_laps": 10,
  "notes": "calibration lap, baseline setup"
}
```

Required:
- `run_id` — `^[A-Za-z0-9_-]+$`, 1–64 chars (path resolves as `/app/data/telemetry/{run_id}.jsonl`)

Optional Phase 1 metadata (all embed into the resulting `SessionSummary`):
- `track_name` — string ≤ 80 chars
- `target_laps` — int 0–999
- `notes` — string ≤ 500 chars (written to `summary.note`)

**Response 201** — full `Session` per [`04-schema.md` §11](./04-schema.md#11-api-surface-types), identical shape to `POST /api/sessions`. The pipeline runs end-to-end (`ingest/torcs_parser.parse_torcs_session` → analysis → reasoning → Pass-1 + Pass-2 → optional fan-mode hydration) using the same `Depends()` wired watsonx clients as the multipart upload path.

`session.summary` is enriched at the API boundary (the pipeline itself stays domain-pure) with:
- `session_source = "torcs_live"`
- `status = "completed"`
- `track_name`, `target_laps`, `notes` from the request body
- `started_at` — UTC datetime, parsed from the first observation's `t` field (the Phase 1 logger injection in `RaceYourCode/gym_torcs/torcs_jm_par.py`). Falls back to file `st_mtime` if the capture is older or `t` is unparseable.
- `completed_at` — UTC datetime from file `st_mtime` (last-written timestamp)
- `telemetry_file` — basename of the originating JSONL (e.g. `"baseline.jsonl"`)

**Response 400** — `error_code: "EMPTY_RUN"` when the file exists but yields zero observations after the JSONL safe-read skips incomplete tails.

**Response 404** — `error_code: "RUN_NOT_FOUND"` when no file exists at the resolved path. The discovery helper at §4.13 is the right way to enumerate before POSTing.

The parser tolerates incomplete tail lines and malformed observations silently per the safe-read pattern (a `torcs_jm_par.py` process may still be appending while this endpoint reads). See `ingest/torcs_parser.py` for the guarantee.

> **Streaming is v1.1.** This endpoint is lap-paced batch ingest only — judges call it once after a drive session ends. SSE pushing per-lap zone detections as `torcs_jm_par.py` writes them is documented as v1.1 alongside TTM-R2.

### 4.13 `GET /api/torcs-status`

Discovery helper for the live-ingest path. Lists every `*.jsonl` file in `/app/data/telemetry/` (the override side of the shared `torcs-telemetry` volume), sorted by mtime descending. Used by the UploadPage banner to enable/disable per-run "Ingest" buttons without polling. Returns `200` always (no `404` for "empty volume" — just `available: false`), so the UI can call it on every page load without error-state branching.

**Response 200**

```json
{
  "available": true,
  "runs": [
    {
      "run_id": "baseline",
      "size_bytes": 64753245,
      "lap_count_estimate": 12,
      "started_at": "2026-05-12T18:12:31+00:00",
      "last_written_at": "2026-05-12T18:23:45+00:00",
      "duration_seconds": 674.0
    }
  ]
}
```

Phase 1 enrichment per run:
- `lap_count_estimate` — cheap heuristic from file size (~5000 ticks per lap at 50 Hz).
- `started_at` — UTC ISO-8601, derived from the first observation's `t` field via `_extract_start_time` (logger injection). Falls back to `last_written_at` if `t` is absent.
- `last_written_at` — UTC ISO-8601, from file `st_mtime`.
- `duration_seconds` — `last_written_at − started_at`, clamped to ≥ 0.

When the `torcs` compose profile isn't running, the named volume still exists but is empty → `{ "available": false, "runs": [] }`. The UI uses this to hide the banner entirely, making the live-TORCS affordance pure progressive enhancement.

### 4.14 `GET /api/regulation-source`

The canonical regulation source metadata for the deployed extraction. The UI shows this in a footer/tooltip so users can see exactly which document version grounds the recommendations.

**Response 200**

```json
{
  "document_title": "FIA 2026 Formula 1 Technical Regulations",
  "issue": "Issue 12 — 2025-06-10",
  "section": "C.5.4",
  "public_url": "https://www.fia.com/...",
  "fetched_at": "2026-05-16T11:02:00Z"
}
```

**Response 404** when verification gate **G-4** has not yet passed and no source is configured. The UI uses this to show a banner: *"Regulation grounding unavailable — citations will be generic until verification completes."*

The `section` value is read from the Docling extraction at startup; it is **never** hardcoded in the API layer.

### 4.15 `GET /api/sessions/{session_id}/stream` (Server-Sent Events)

Live per-lap telemetry stream for a session in `status="active"`. Phase 3 ship; v1.0 emits via the `torcs-live` ingest path when the underlying JSONL is still being appended to.

**Response 200** — `Content-Type: text/event-stream`. Each event is a JSON object on a single `data: …` line. Event discriminator is `event`.

**Event types:**

```jsonc
// Always emitted first — confirms the connection is live.
{ "event": "connected", "session_id": "s_torcs_...", "status": "active" }

// Per-lap stats — one emit per newly-completed lap, in order.
// Payload shape is LiveLapStats (see 04-schema.md §11).
{ "event": "lap", "lap": 1, "lap_time_s": 92.5, "avg_speed_kmh": 180.2,
  "max_speed_kmh": 240.5, "harvest_mj": 4.2, "deploy_mj": 3.8,
  "soc_end": 0.85, "fuel_used_kg": 0.3 }

// Terminal — emitted once when the file-stall heuristic fires.
// Client should treat this as end-of-stream; server closes immediately after.
{ "event": "race_ended", "reason": "file_stall", "total_laps": 12 }

// Terminal — emitted when the session has no resolvable telemetry_file.
// Client should treat as end-of-stream.
{ "event": "no_telemetry", "message": "..." }
```

**Race-end detection — file-stall heuristic.** The server polls the underlying JSONL's `mtime` + completed-lap count every second. If neither advances for 10 seconds, the stream emits `race_ended` with `reason: "file_stall"` and closes. No control-daemon dependency; works with the bare `torcs_jm_par.py` workflow today.

**Disconnect handling.** `await request.is_disconnected()` is checked at each poll iteration; a closed browser tab releases the generator within ~1 s, well under the stall timeout.

**Response 404** — `error_code: "NOT_FOUND"` when the session doesn't exist.

**Caveats:**
- This endpoint is `O(file_size)` per poll — it re-reads the JSONL each tick to count laps. Suitable for typical race durations (≤ 100 MB). v1.1 may move to a tail-cursor implementation.
- The `LiveLapStats` energy math uses a single-sector approximation; the post-race `LapFeatures` (via `ingest/torcs_parser.py`) splits into three sectors. Live totals should agree with post-race totals to within a few percent.
- Cloudflare Tunnel auto-disables buffering for `text/event-stream` per CF documentation; SSE works through the hosted demo URL. The `X-Accel-Buffering: no` header is set as belt-and-suspenders for nginx-shape proxies.

### 4.16 `DELETE /api/sessions/{session_id}`

Remove the session and its derived artifacts from local storage. Used in the demo to keep the list clean. Returns `204 No Content`. Idempotent — `204` even if the session was already gone.

---

## 5. Pipeline timing budget

The README and demo abstract both quote "*a debrief in under 30 seconds*". `POST /api/sessions` is the endpoint that promise lives on. Phase budget:

| Stage | Budget | Notes |
|---|---|---|
| Ingest + aggregate | ≤ 1 s | pure Python, single pass over the file |
| Zone detection | ≤ 0.5 s | heuristics |
| TTM-R2 forecast | ≤ 4 s | optional; skipped if `lap_count < 30` |
| Docling retrieval | ≤ 1 s | keyword search + watsonx Granite Embedding for the per-query vector (~200–500 ms); chunks are pre-embedded at boot, not per request |
| Granite reasoning (per zone) | ≤ 6 s | parallelized **across** zones with `asyncio.gather` |
| Pass 1 validator | ≤ 0.2 s | deterministic; runs after reasoning, before Guardian |
| Pass 2 Guardian (per zone) | ≤ 4 s | sequential **after** reasoning for the same zone; parallel **across** zones |
| Fan Mode translation | deferred | run lazily on first `mode=fan` request, not on upload |

A 3-zone session should land at **~12–18 s end-to-end**, well inside the 30 s headline. Sessions with regenerations or 5+ zones approach the 30 s ceiling.

---

## 6. Concurrency model

- Reasoning calls run in parallel **across** zones via `asyncio.gather`. Within a single zone the order is reasoning → validator → Guardian, sequentially. Guardian calls run in parallel **across** zones once each zone's reasoning has completed. Three zones therefore make up to three concurrent reasoning calls, then up to three concurrent Guardian calls.
- watsonx.ai handles its own concurrency, but to stay inside our quota the server enforces a process-wide semaphore of `OVERRIDE_LLM_CONCURRENCY` (default 4) on outbound watsonx calls.
- The upload endpoint runs the whole pipeline synchronously inside the request. Long-running `202 Accepted` + polling is **not** in scope for v1; if needed it becomes ADR-003.

---

## 7. Storage

- Sessions are stored on local disk under `data/sessions/{session_id}/`:
  - `summary.json` — `SessionSummary`
  - `laps.parquet` — `LapFeatures` rows
  - `forecast.json` — `Forecast` or absent
  - `recommendations.json` — `Recommendation[]`
- Original uploaded files are **not** retained after parsing; only the derived artifacts. This keeps the data footprint small and avoids accidentally committing replay files.
- A simple JSON index at `data/sessions/_index.json` powers `GET /api/sessions`.
- No database in v1.

---

## 8. Observability

- Every request is logged with `X-Request-Id`, path, method, status, duration, and any failed validator/guardian rule IDs.
- OpenTelemetry instrumentation (FastAPI middleware + manual spans around LLM calls) is wired regardless of whether ContextForge is used; one trace screenshot is required for the README per roadmap **P3.6**.
- Log format: JSON on one line per record. No PII; uploaded file contents never appear in logs.
- Healthcheck on Docker: `GET /api/health` every 30 s, 3 consecutive failures = unhealthy.

---

## 9. Rate limiting

- Per-IP: **30 req/min** burst, **300 req/hour** sustained, enforced via in-memory token bucket.
- Per-IP upload concurrency: **2 in-flight** as noted in §4.3.
- Returns `429 RATE_LIMITED` with a `Retry-After` header (seconds).
- Limits are intentionally generous because OVERRIDE is single-user; their purpose is to keep the watsonx.ai quota healthy under runaway demo loops, not to police users.

---

## 10. Authentication (out of scope for v1)

Documented as a placeholder so we can wire it later without breaking anything.

- Planned mechanism: `X-API-Key` header, validated against `OVERRIDE_API_KEY` env var.
- When introduced, all `/api/sessions*` routes become protected; `/api/health` and `/api/version` stay public.
- Until then, no auth checks — keep this in mind when deploying anywhere that's not local.

---

## 11. UI contract notes

- The Next.js app proxies `/api/*` to the FastAPI service. The browser never speaks directly to FastAPI in dev or prod.
- The mode toggle in the header (Engineer ↔ Fan) calls `GET /api/sessions/{id}/zones/{zone_id}?mode=...` lazily — it does **not** re-upload the session.
- Loading skeletons, empty states ("forecast unavailable", "no zones detected", "low confidence"), and Guardian-fail badges are rendered from the schemas above; the API guarantees those fields are present (or explicitly null) so the UI never has to guess.
- The "what-if" toggle is one POST per perturbation; the result replaces the recommendation card in place.

---

## 12. Open items

- **Streaming**: SSE endpoint (§4.10) is optional and may be cut if it complicates the demo more than it helps. Decision tracked under roadmap P3.5.
- **What-if catalog**: only three `parameter` values in v1 (`delay_first_deploy`, `skip_harvest_zone`, `extend_override`). Adding more is a P3.5 follow-up.
- **Background jobs**: if 30 s ever stops being achievable inline, the upload becomes async with `202` + polling. Tracked as ADR-003 candidate.
- **Multi-user**: out of scope. If introduced, all session routes become tenant-scoped and storage moves off the local filesystem.
