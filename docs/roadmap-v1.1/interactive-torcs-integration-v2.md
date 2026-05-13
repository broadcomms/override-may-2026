# Interactive TORCS Integration - Revised Plan (v2)

**Status:** Planning - Addressing Security & Architecture Review  
**Created:** 2026-05-13  
**Revised:** 2026-05-13 (post-review)  
**Priority:** High - Addresses session management gaps with security-first approach

---

## Executive Summary

**Original Vision:** Embed VNC viewer in public UI with interactive TORCS controls.

**Security Reality Check:** The original plan had three critical flaws:
1. **VNC exposure risk** - Embedding noVNC in public UI reintroduces the takeover vector
2. **Privilege escalation** - `podman exec` from API requires host socket access
3. **Session semantics conflation** - Mixing race lifecycle with pipeline output

**Revised Approach:** Focus on the **actual user pain point** (session boundaries) with security-first, incremental enhancements that don't compromise the deployment model.

---

## Core Problem Statement

From the original request:
> "When the user starts a new race and ends it, it does not show that this was a different session. The baseline keeps growing and we cannot distinguish session from the run."

**What Users Actually Need:**
- ✅ Per-run telemetry files (not one continuous baseline)
- ✅ Session metadata (track, laps, timestamps)
- ✅ Session history and comparison
- ✅ Clear boundaries between races

**What Users Don't Need (Yet):**
- ❌ Embedded VNC in public UI (security risk)
- ❌ Complex control-plane architecture (over-engineered for v1)
- ❌ Real-time streaming (explicitly deferred to v1.1 per roadmap)

---

## Architectural Corrections

### Issue 1: VNC Embedding is a Security Regression

**Original Plan:** Embed noVNC client in public UI

**Problem:** From [`docs/07-deployment.md`](../07-deployment.md):
> "⚠️ noVNC has no authentication. Exposing port 6080 publicly is a takeover vector."

**Why It Fails:**
- Hosted demo (`https://override.patrickndille.com`) can't load `ws://localhost:6080` (mixed-content blocking)
- Exposing `:6080` publicly reintroduces the security issue we just fixed
- Proxying through API still exposes unauthenticated VNC

**Revised Decision:**
- **Local dev:** VNC stays at `localhost:6080/vnc.html` (separate tab)
- **Hosted demo:** Fixture mode only (no live TORCS)
- **Future:** Consider authenticated VNC proxy in v2.0+

### Issue 2: `podman exec` Requires Privilege Escalation

**Original Plan:** Call `podman exec` from FastAPI to control TORCS

**Problem:** The `override` container has no Podman access

**Two Options:**

| Approach | Security | Complexity | Decision |
|----------|----------|------------|----------|
| Mount Podman socket | ❌ Container escape risk | ✅ Simple | ❌ **Rejected** |
| Control daemon in TORCS | ✅ Isolated | ⚠️ Moderate | ✅ **Accepted** |

**Revised Decision:** HTTP control daemon inside TORCS container (Phase 2)

### Issue 3: Session Semantics Conflation

**Original Plan:** Add `SessionStatus` to existing `Session` model

**Problem:** Two different concepts:
1. **Pipeline Session** (existing): Output of `run_pipeline()` with laps/zones/recommendations
2. **Race Session** (new): Lifecycle of a TORCS race (preparing/active/completed)

**Revised Decision:** Extend `SessionSummary` directly with optional lifecycle fields (backward compatible)

---

## Revised Three-Phase Plan

### Phase 1: Session Boundaries (2 weeks, Low Risk)

**Goal:** Fix session tracking without architectural changes

**Key Changes:**
1. Auto-generate telemetry filenames from `OVERRIDE_LOG_TELEMETRY` directory
2. Capture session metadata at ingest time
3. Build session history and comparison UI

**No new security surface, no VNC changes, no control-plane complexity.**

See detailed implementation below.

### Phase 2: Control Daemon (3 weeks, Moderate Risk)

**Goal:** Enable programmatic TORCS control via secure daemon

**Key Changes:**
1. HTTP daemon inside TORCS container (port 7000, internal-only)
2. Shared-secret authentication
3. Start/stop race API endpoints
4. UI control panel (local dev only)

**Security:** No privilege escalation, no public exposure

See detailed implementation below.

### Phase 3: Live Telemetry (2 weeks, Low Risk)

**Goal:** Real-time lap updates during active races

**Key Changes:**
1. SSE streaming endpoint (per-lap updates, not per-tick)
2. Live stats component
3. Automatic race-end detection

**Performance:** <100ms latency per lap

See detailed implementation below.

---

## Phase 1: Session Boundaries (Detailed)

### 1.1 Auto-Generated Telemetry Files

**Current Behavior:**
```python
# torcs_jm_par.py
_override_log = os.environ.get("OVERRIDE_LOG_TELEMETRY", "telemetry/default.jsonl")
_override_fh = open(_override_log, "a")  # Always appends to same file
```

**New Behavior:**
```python
def _resolve_telemetry_path() -> Path:
    """Resolve telemetry file path with auto-generation support."""
    path_str = os.environ.get("OVERRIDE_LOG_TELEMETRY", "telemetry/default.jsonl")
    path = Path(path_str)
    
    # If path ends in / or is a directory, auto-generate filename
    if path_str.endswith("/") or path.is_dir():
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        return path / f"run_{timestamp}.jsonl"
    
    # Otherwise honor literal path (backward compatible)
    return path

_override_log = _resolve_telemetry_path()
_override_fh = open(_override_log, "a", buffering=1)  # Line-buffered
```

**Benefits:**
- ✅ 5 lines of code
- ✅ Backward compatible
- ✅ No new env vars
- ✅ Fixes buffer-flush bug for future streaming

**Compose Change:**
```yaml
# docker-compose.yml - torcs service
environment:
  OVERRIDE_LOG_TELEMETRY: /home/student/workspace/gym_torcs/telemetry/
  # Trailing slash triggers auto-generation
```

### 1.2 Session Metadata Schema

**Extend [`ingest/schema.py`](../../ingest/schema.py):**

```python
class SessionStatus(str, Enum):
    COMPLETED = "completed"  # Default for all existing sessions
    ACTIVE = "active"        # Race in progress (Phase 2)
    CANCELLED = "cancelled"  # Race stopped early (Phase 2)

class SessionSummary(BaseModel):
    # ... existing fields ...
    
    # Lifecycle fields (optional, backward compatible)
    status: SessionStatus = SessionStatus.COMPLETED
    track_name: Optional[str] = None
    target_laps: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    telemetry_file: Optional[str] = None
```

**No parallel `SessionMetadata` class - extend existing schema directly.**

### 1.3 Enhanced Live Ingest Endpoint

**Update [`api/main.py`](../../api/main.py):**

```python
@app.post("/api/sessions/torcs-live")
async def torcs_live(
    request: Request,
    body: TorcsLiveRequest,
    # NEW: Optional metadata
    track_name: Annotated[Optional[str], Form()] = None,
    target_laps: Annotated[Optional[int], Form()] = None,
    notes: Annotated[Optional[str], Form()] = None,
    # ... existing dependencies ...
):
    """Ingest JSONL replay with optional metadata."""
    # ... existing parsing logic ...
    
    # Extract timestamps from file
    stat = jsonl_path.stat()
    started_at = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc)
    completed_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    
    # Run pipeline
    session = await run_pipeline(...)
    
    # Enrich summary with metadata
    session.summary.track_name = track_name
    session.summary.target_laps = target_laps
    session.summary.started_at = started_at
    session.summary.completed_at = completed_at
    session.summary.telemetry_file = body.run_id + ".jsonl"
    if notes:
        session.summary.note = notes
    
    save_session(session)
    return session.model_dump(mode="json")
```

### 1.4 Enhanced `/api/torcs-status`

**Add per-run metadata:**

```python
@app.get("/api/torcs-status")
async def torcs_status():
    """List JSONL replays with metadata."""
    runs = []
    for p in sorted(tdir.glob("*.jsonl"), key=lambda x: x.stat().st_mtime, reverse=True):
        stat = p.stat()
        started_at = datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc)
        last_written = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        
        runs.append({
            "run_id": p.stem,
            "size_bytes": stat.st_size,
            "lap_count_estimate": (stat.st_size // 1000) // 5000,
            "started_at": started_at.isoformat(),
            "last_written_at": last_written.isoformat(),
            "duration_seconds": (last_written - started_at).total_seconds(),
        })
    
    return {"available": bool(runs), "runs": runs}
```

### 1.5 Session History UI

**New page: [`ui/src/pages/SessionHistoryPage.tsx`](../../ui/src/pages/SessionHistoryPage.tsx)**

```typescript
export function SessionHistoryPage() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  
  useEffect(() => {
    api.listSessions().then(setSessions);
  }, []);
  
  return (
    <div className="session-history">
      <h1>Session History</h1>
      <div className="session-grid">
        {sessions.map(session => (
          <SessionCard key={session.session_id} session={session} />
        ))}
      </div>
    </div>
  );
}
```

### 1.6 Session Comparison UI

**New component: [`ui/src/components/SessionComparison.tsx`](../../ui/src/components/SessionComparison.tsx)**

```typescript
export function SessionComparison({ sessionIds }: { sessionIds: [string, string] }) {
  const [sessions, setSessions] = useState<[Session, Session] | null>(null);
  
  useEffect(() => {
    Promise.all(sessionIds.map(id => api.getSession(id)))
      .then(([a, b]) => setSessions([a, b]));
  }, [sessionIds]);
  
  // Render side-by-side comparison with lap times, energy deployment, zones
}
```

**Phase 1 Deliverables:**
- ✅ Per-run telemetry files
- ✅ Session metadata capture
- ✅ Session history page
- ✅ Session comparison UI
- ✅ Backward compatible

**Estimated Effort:** 2 weeks (40 hours)

---

## Phase 2: Control Daemon (Detailed)

### 2.1 Control Daemon Architecture

**Decision:** HTTP daemon inside TORCS container with shared-secret auth

```
OVERRIDE Container                    TORCS Container
     │                                     │
     │ POST /api/torcs/start-race         │
     │ Authorization: Bearer <secret>     │
     ├────────────────────────────────────►│
     │                                     │
     │                              Control Daemon (:7000)
     │                                     │
     │                              ├─► Validate secret
     │                              ├─► Set env vars
     │                              ├─► Launch gym_torcs
     │                              └─► Return {pid, status}
     │                                     │
     │◄────────────────────────────────────┤
     │ {session_id, status: "started"}    │
```

### 2.2 Control Daemon Implementation

**New file: [`RaceYourCode/gym_torcs/control_daemon.py`](../../RaceYourCode/gym_torcs/control_daemon.py)**

```python
"""HTTP control daemon for TORCS container."""

from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel, Field
import subprocess
import os

app = FastAPI(title="TORCS Control Daemon")

CONTROL_SECRET = os.environ.get("TORCS_CONTROL_SECRET", "")
if not CONTROL_SECRET:
    raise RuntimeError("TORCS_CONTROL_SECRET not set")

_active_process: Optional[subprocess.Popen] = None
_active_session_id: Optional[str] = None


def _verify_auth(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401)
    if authorization[7:] != CONTROL_SECRET:
        raise HTTPException(status_code=403)


@app.post("/control/start", dependencies=[Depends(_verify_auth)])
async def start_race(req: StartRaceRequest) -> dict:
    global _active_process, _active_session_id
    
    if _active_process and _active_process.poll() is None:
        raise HTTPException(status_code=409, detail="Race already active")
    
    env = os.environ.copy()
    env["OVERRIDE_SESSION_ID"] = req.session_id
    env["OVERRIDE_TRACK"] = req.track
    env["OVERRIDE_LAPS"] = str(req.laps)
    env["OVERRIDE_LOG_TELEMETRY"] = "/home/student/workspace/gym_torcs/telemetry/"
    
    _active_process = subprocess.Popen(
        ["python3", "/home/student/workspace/gym_torcs/torcs_jm_par.py"],
        env=env
    )
    _active_session_id = req.session_id
    
    return {"session_id": req.session_id, "pid": _active_process.pid}


@app.post("/control/stop", dependencies=[Depends(_verify_auth)])
async def stop_race() -> dict:
    if _active_process:
        _active_process.terminate()
        _active_process.wait(timeout=5)
    return {"status": "stopped"}


@app.get("/health")
async def health():
    return {"status": "ok"}
```

### 2.3 Compose Changes

**Update [`docker-compose.yml`](../../docker-compose.yml):**

```yaml
services:
  override:
    environment:
      TORCS_CONTROL_URL: http://torcs:7000
      TORCS_CONTROL_SECRET: ${TORCS_CONTROL_SECRET}
  
  torcs:
    environment:
      TORCS_CONTROL_SECRET: ${TORCS_CONTROL_SECRET}
    command: >
      bash -c "
        /usr/local/bin/torcs_init.sh &
        cd /home/student/workspace/gym_torcs &&
        uvicorn control_daemon:app --host 0.0.0.0 --port 7000
      "
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:7000/health"]
```

**Add to [`.env.example`](../../.env.example):**

```bash
TORCS_CONTROL_SECRET=change-this-in-production
```

### 2.4 OVERRIDE API Integration

**Add to [`api/main.py`](../../api/main.py):**

```python
@app.post("/api/torcs/start-race")
async def start_torcs_race(
    track: str = Form(...),
    laps: int = Form(default=10),
) -> dict:
    session_id = f"s_torcs_live_{int(time.time())}_{secrets.token_hex(4)}"
    
    async with httpx.AsyncClient(
        base_url=os.environ["TORCS_CONTROL_URL"],
        headers={"Authorization": f"Bearer {os.environ['TORCS_CONTROL_SECRET']}"}
    ) as client:
        resp = await client.post("/control/start", json={
            "session_id": session_id,
            "track": track,
            "laps": laps
        })
        resp.raise_for_status()
    
    return {"session_id": session_id, "status": "started"}
```

### 2.5 UI Control Panel (Local-Only)

**New component: [`ui/src/components/TorcsControlPanel.tsx`](../../ui/src/components/TorcsControlPanel.tsx)**

```typescript
export function TorcsControlPanel() {
  const [isLocal, setIsLocal] = useState(false);
  
  useEffect(() => {
    setIsLocal(window.location.hostname === 'localhost');
  }, []);
  
  if (!isLocal) {
    return (
      <div className="control-unavailable">
        <p>TORCS control is only available in local development.</p>
        <p>Clone the repo and run: <code>podman compose --profile torcs up</code></p>
      </div>
    );
  }
  
  return (
    <div className="torcs-control">
      {/* Start/stop race controls */}
      <a href="http://localhost:6080/vnc.html" target="_blank">
        Open VNC Viewer →
      </a>
    </div>
  );
}
```

**Phase 2 Deliverables:**
- ✅ HTTP control daemon
- ✅ Shared-secret auth
- ✅ Start/stop API endpoints
- ✅ UI control panel (local-only)
- ✅ No privilege escalation

**Estimated Effort:** 3 weeks (60 hours)

---

## Phase 3: Live Telemetry (Detailed)

### 3.1 SSE Streaming Endpoint

**Add to [`api/main.py`](../../api/main.py):**

```python
@app.get("/api/sessions/{session_id}/stream")
async def stream_telemetry(session_id: str):
    """Stream live telemetry via Server-Sent Events (per-lap updates)."""
    
    async def event_generator():
        telemetry_file = _find_telemetry_file(session_id)
        last_lap = 0
        
        while True:
            # Check if race is still active
            status = await _get_race_status()
            if not status["active"] or status["session_id"] != session_id:
                yield f"data: {json.dumps({'event': 'race_ended'})}\n\n"
                break
            
            # Read completed laps
            current_lap = _get_current_lap(telemetry_file)
            if current_lap > last_lap:
                lap_stats = _aggregate_lap(telemetry_file, current_lap)
                yield f"data: {json.dumps(lap_stats)}\n\n"
                last_lap = current_lap
            
            await asyncio.sleep(1.0)  # 1 Hz polling
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

### 3.2 Live Stats Component

**New component: [`ui/src/components/LiveTelemetry.tsx`](../../ui/src/components/LiveTelemetry.tsx)**

```typescript
export function LiveTelemetry({ sessionId }: { sessionId: string }) {
  const [laps, setLaps] = useState<LapStats[]>([]);
  
  useEffect(() => {
    const eventSource = new EventSource(`/api/sessions/${sessionId}/stream`);
    
    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.event === 'race_ended') {
        eventSource.close();
      } else if (data.lap) {
        setLaps(prev => [...prev, data]);
      }
    };
    
    return () => eventSource.close();
  }, [sessionId]);
  
  return (
    <div className="live-telemetry">
      {/* Display lap history table */}
    </div>
  );
}
```

**Phase 3 Deliverables:**
- ✅ SSE streaming (1 Hz, per-lap)
- ✅ Live stats component
- ✅ Automatic race-end detection
- ✅ <100ms latency per lap

**Estimated Effort:** 2 weeks (40 hours)

---

## Implementation Roadmap

**Total Duration:** 7 weeks (140 hours)

### Sprint 1-2: Session Boundaries (Weeks 1-2)
- Extend `OVERRIDE_LOG_TELEMETRY` with auto-generation
- Add lifecycle fields to `SessionSummary`
- Enhance `/api/sessions/torcs-live` and `/api/torcs-status`
- Build session history and comparison UI
- Integration tests

### Sprint 3-5: Control Daemon (Weeks 3-5)
- Implement `control_daemon.py`
- Update `docker-compose.yml`
- Add control endpoints to OVERRIDE API
- Build UI control panel (local-only)
- Security tests

### Sprint 6-7: Live Streaming (Weeks 6-7)
- Implement SSE streaming endpoint
- Build live telemetry component
- Performance testing
- Documentation

---

## Security Model

### Phase 1: No New Attack Surface
- Extends existing ingest endpoint
- Backward compatible

### Phase 2: Control Daemon
- **Attack Surface:** HTTP daemon on internal network
- **Mitigation:**
  - Shared-secret authentication
  - Internal-only (no external port)
  - Input validation
  - Rate limiting

### Phase 3: Live Streaming
- **Attack Surface:** SSE endpoint
- **Mitigation:**
  - Read-only file access
  - Automatic timeout
  - Rate limiting

---

## Deployment Constraints

### Local Development
- ✅ Full feature set
- ✅ Control panel works
- ✅ Live streaming works

### Hosted Demo
- ❌ No control panel (security)
- ✅ Session history works
- ✅ Session comparison works
- ✅ Fixture mode for demos

---

## Success Metrics

- ✅ Clear session boundaries
- ✅ Session comparison capability
- ✅ Programmatic race control (local)
- ✅ Live race progress (local)
- ✅ Zero privilege escalation
- ✅ No public VNC exposure
- ✅ Backward compatible

---

## Approval & Next Steps

**Questions for Review:**
1. Does the phased approach address all security concerns?
2. Is the local-only control panel acceptable?
3. Should we proceed with Phase 1 immediately?
4. Any additional requirements for Phase 2/3?

**After Approval:**
- Create feature branch: `feature/session-boundaries`
- Begin Sprint 1 implementation
- Update project board