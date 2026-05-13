# Interactive TORCS Integration - Final Buildable Specification (v3)

**Status:** Ready for Implementation  
**Created:** 2026-05-13  
**Parent:** [`interactive-torcs-integration-v2.md`](interactive-torcs-integration-v2.md)

---

## Executive Summary

This is the **buildable specification** for interactive TORCS integration. All technical corrections from the architecture review have been applied.

**Core Problem:** Users cannot distinguish between individual TORCS race sessions.

**Solution:** Three-phase implementation (7 weeks, 140 hours):
- **Phase 1** (2 weeks): Per-run telemetry files + session metadata
- **Phase 2** (3 weeks): HTTP control daemon for programmatic race control  
- **Phase 3** (2 weeks): Live telemetry streaming via SSE

---

## Critical Technical Corrections Applied

### Phase 1 Corrections (Session Boundaries)

**1.1A - datetime.utcnow() deprecated**
```python
# WRONG (v2)
timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S")

# CORRECT (v3)
timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%f")
# Added %f for microsecond precision (prevents collisions)
```

**1.1B - Path resolution edge cases**
```python
def _resolve_telemetry_path() -> Path:
    path_str = os.environ.get("OVERRIDE_LOG_TELEMETRY", "telemetry/default.jsonl")
    path = Path(path_str)
    
    # Robust dir detection
    if path_str.endswith("/") or path.is_dir() or not path.suffix:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%f")
        path.mkdir(parents=True, exist_ok=True)  # Create if missing
        return path / f"run_{timestamp}.jsonl"
    
    return path

_override_log = _resolve_telemetry_path()
os.makedirs(os.path.dirname(_override_log) or ".", exist_ok=True)  # Parent dirs
_override_fh = open(_override_log, "a", buffering=1)  # Line-buffered
```

**1.2 - SessionSource/SessionStatus split**
```python
class SessionSource(str, Enum):
    UPLOAD = "upload"           # File dropped via UI
    TORCS_LIVE = "torcs_live"   # Live-ingest endpoint
    FASTF1 = "fastf1"           # Historical replay

class SessionStatus(str, Enum):
    COMPLETED = "completed"
    ACTIVE = "active"           # Only for TORCS_LIVE
    CANCELLED = "cancelled"     # Only for TORCS_LIVE

class SessionSummary(BaseModel):
    # ... existing fields ...
    session_source: SessionSource = SessionSource.UPLOAD
    status: SessionStatus = SessionStatus.COMPLETED
    track_name: Optional[str] = None
    target_laps: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    telemetry_file: Optional[str] = None
```

**1.3A - FastAPI Form/Body mixing fixed**
```python
# WRONG (v2) - Cannot mix JSON body with Form parameters
async def torcs_live(
    body: TorcsLiveRequest,
    track_name: Annotated[Optional[str], Form()] = None,  # Won't work!
):

# CORRECT (v3) - Single JSON body
class TorcsLiveRequest(BaseModel):
    run_id: str = Field(..., pattern=r"^[A-Za-z0-9_-]+$")
    track_name: Optional[str] = None
    target_laps: Optional[int] = Field(None, ge=1, le=100)
    notes: Optional[str] = None

async def torcs_live(body: TorcsLiveRequest):
    # Access body.track_name, body.target_laps, body.notes
```

**1.3B - st_ctime unreliable on Linux**
```python
def _extract_start_time(jsonl_path: Path, stat: os.stat_result) -> datetime:
    """Extract start time from first observation's timestamp.
    
    st_ctime is metadata change time on Linux, not creation time.
    Parse first line instead.
    """
    try:
        with jsonl_path.open() as f:
            first_line = f.readline()
            if first_line.endswith("\n"):
                first_obs = json.loads(first_line)
                if "t" in first_obs:  # Unix timestamp
                    return datetime.fromtimestamp(first_obs["t"], tz=timezone.utc)
    except (json.JSONDecodeError, KeyError, OSError):
        pass
    
    # Fallback to mtime
    return datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
```

---

### Phase 2 Corrections (Control Daemon)

**2.2A - StartRaceRequest schema defined**
```python
class StartRaceRequest(BaseModel):
    """Request to start a new TORCS race."""
    session_id: str = Field(..., pattern=r"^[A-Za-z0-9_-]+$")
    track: str = Field(..., pattern=r"^[a-z0-9-]+$")  # Whitelist-friendly
    laps: int = Field(..., ge=1, le=100)
```

**2.2B - Race condition fixed with asyncio.Lock**
```python
_control_lock = asyncio.Lock()

@app.post("/control/start")
async def start_race(req: StartRaceRequest):
    async with _control_lock:  # Prevents TOCTOU race
        if _active_process and _active_process.poll() is None:
            raise HTTPException(status_code=409, ...)
        _active_process = subprocess.Popen(...)
```

**2.2C - Auth returns proper 401/403**
```python
def _verify_auth(authorization: Optional[str] = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization required")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, ...)
    
    # Timing-attack resistant comparison
    if not secrets.compare_digest(authorization[7:], CONTROL_SECRET):
        raise HTTPException(status_code=403, detail="Invalid secret")
```

**2.3A - Compose command waits for VNC**
```yaml
command: >
  bash -c "
    /usr/local/bin/torcs_init.sh &
    pip install --quiet fastapi uvicorn
    until curl -sf http://localhost:6080 >/dev/null 2>&1; do sleep 1; done
    cd /home/student/workspace/gym_torcs &&
    uvicorn control_daemon:app --host 0.0.0.0 --port 7000
  "
```

**2.4A - httpx dependency + timeout**
```python
# Add to requirements.txt
httpx>=0.27.0

# Use with timeout
async with httpx.AsyncClient(
    base_url=os.environ.get("TORCS_CONTROL_URL", "http://torcs:7000"),
    headers={"Authorization": f"Bearer {os.environ['TORCS_CONTROL_SECRET']}"},
    timeout=httpx.Timeout(10.0, connect=2.0)
) as client:
    resp = await client.post("/control/start", json={...})
```

---

### Phase 3 Corrections (Live Telemetry)

**3.1A - All helpers defined**
```python
def _find_telemetry_file(session_id: str) -> Optional[Path]:
    """Find telemetry file for session."""
    tdir = _telemetry_dir()
    for p in tdir.glob(f"{session_id}_*.jsonl"):
        return p
    return None

def _get_current_lap(telemetry_file: Path, last_position: int) -> tuple[int, int]:
    """Get current lap number. Returns (lap, new_position)."""
    with open(telemetry_file) as f:
        f.seek(last_position)
        lines = f.readlines()
        new_position = f.tell()
    
    for line in reversed(lines):
        if line.endswith("\n"):
            try:
                obs = json.loads(line)
                return (obs.get("lap", 0), new_position)
            except json.JSONDecodeError:
                continue
    return (0, last_position)

def _aggregate_lap(telemetry_file: Path, lap: int) -> dict:
    """Aggregate telemetry for completed lap."""
    lap_ticks = []
    with open(telemetry_file) as f:
        for line in f:
            if not line.endswith("\n"):
                continue
            try:
                tick = json.loads(line)
                if tick.get("lap") == lap:
                    lap_ticks.append(tick)
            except json.JSONDecodeError:
                continue
    
    # Compute stats...
    return {"lap": lap, "lap_time": ..., "avg_speed_kmh": ..., ...}
```

**3.1B - Latency claim corrected**
```python
# v2 claimed: "<100ms latency per lap"
# v3 reality: "<1 second latency per lap" (1Hz polling)

async def event_generator():
    while True:
        # ... check for new laps ...
        await asyncio.sleep(1.0)  # 1Hz → <1s latency
```

**3.1C - Client disconnect handling**
```python
async def event_generator():
    try:
        while True:
            if await request.is_disconnected():
                break  # Clean exit
            # ... stream events ...
    except asyncio.CancelledError:
        pass  # Client disconnected
```

---

## Section 4: Failure Modes & Recovery

| Failure | Phase | Recovery |
|---------|-------|----------|
| **Control daemon crashes mid-race** | 2 | Override endpoint timeout (10s) returns 503; UI shows "TORCS control unreachable"; race continues, telemetry writes, manual ingest via `/api/sessions/torcs-live` |
| **gym_torcs hangs without writing** | 1, 3 | Control daemon enforces 10-min max race timeout; SSE detects no new lines for >30s, emits `stall_detected` event |
| **JSONL corruption (incomplete tail)** | 1, 3 | Already handled by gotcha #12 safe-read in `torcs_parser.py`; SSE mirrors same `try/except JSONDecodeError` |
| **Disk fills up mid-race** | 1 | gym_torcs writer logs error, stops appending; existing data preserved; race "completes" prematurely; daemon marks cancelled |
| **Two clients call start simultaneously** | 2 | `asyncio.Lock` ensures serialization; second request gets 409 Conflict |
| **SSE client disconnects** | 3 | Generator checks `await request.is_disconnected()` each loop; cleans up file handles |
| **Override container restart during race** | 2 | Daemon is single source of truth; continues writing telemetry; on restart, status endpoint reflects daemon state |
| **Daemon receives SIGTERM during race** | 2 | Daemon forwards SIGTERM to gym_torcs, waits 5s for graceful exit, then SIGKILL; marks session cancelled |

---

## Implementation Roadmap

### Sprint 1-2: Session Boundaries (Weeks 1-2, 40h)
- [ ] Apply Phase 1 corrections to `torcs_jm_par.py`
- [ ] Extend `SessionSummary` schema with lifecycle fields
- [ ] Update `/api/sessions/torcs-live` endpoint
- [ ] Enhance `/api/torcs-status` with metadata
- [ ] Build session history page
- [ ] Build session comparison component
- [ ] Integration tests

**Deliverable:** Per-run sessions with metadata tracking

### Sprint 3-5: Control Daemon (Weeks 3-5, 60h)
- [ ] Implement `control_daemon.py` with all corrections
- [ ] Update `docker-compose.yml` with daemon config
- [ ] Add control endpoints to OVERRIDE API
- [ ] Add `httpx` to requirements
- [ ] Build UI control panel (local-only)
- [ ] Security tests
- [ ] Documentation

**Deliverable:** Programmatic TORCS control (local dev only)

### Sprint 6-7: Live Streaming (Weeks 6-7, 40h)
- [ ] Implement SSE streaming endpoint with all helpers
- [ ] Build live telemetry component
- [ ] Add connection status indicators
- [ ] Handle race-end detection
- [ ] Performance testing
- [ ] Documentation

**Deliverable:** Real-time lap updates during races

---

## Deployment Constraints

### Local Development
- ✅ Full feature set available
- ✅ Control panel functional
- ✅ Live streaming works
- ✅ VNC at `localhost:6080/vnc.html` (separate tab)

### Hosted Demo (override.patrickndille.com)
- ❌ No control panel (security constraint)
- ❌ No embedded VNC (mixed-content blocking)
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
- ✅ Backward compatible with v1.0
- ✅ All technical bugs fixed

---

## Dependencies

**New Python packages:**
```
httpx>=0.27.0
```

**TORCS container additions:**
```bash
pip install fastapi uvicorn
```

**Environment variables:**
```bash
TORCS_CONTROL_SECRET=change-this-in-production
TORCS_CONTROL_URL=http://torcs:7000
OVERRIDE_LOG_TELEMETRY=/path/to/telemetry/
```

---

## References

- Parent plan: [`interactive-torcs-integration-v2.md`](interactive-torcs-integration-v2.md)
- Architecture: [`docs/03-architecture.md`](../03-architecture.md)
- Schema: [`docs/04-schema.md`](../04-schema.md)
- API: [`docs/04-api.md`](../04-api.md)
- Deployment: [`docs/07-deployment.md`](../07-deployment.md)

---

## Approval & Next Steps

**Status:** Ready for implementation

**After v1.0 submission (May 31):**
1. Create feature branch: `feature/session-boundaries`
2. Begin Sprint 1 (Phase 1 implementation)
3. Update project board with tasks

**Priority Order (by ROI):**
1. **Phase 1** - Highest impact, visible to all judges
2. **Phase 3** - Visual demo impact for local-clone judges
3. **Phase 2** - Infrastructure convenience

This specification is **buildable** - all runtime failures identified in review have been corrected.