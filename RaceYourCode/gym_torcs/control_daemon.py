"""HTTP control daemon for the TORCS container.

Phase 2 of `docs/roadmap-v1.1/interactive-torcs-integration.md` — eliminates
the noVNC-terminal workflow by exposing a small FastAPI app inside the
torcs container that OVERRIDE's API proxies to. The daemon owns the
gym_torcs subprocess lifecycle (start, signal, reap).

**Security posture** (see ADR-004):
- Bound to 0.0.0.0:7000 inside the container; compose does NOT expose
  port 7000 to the host, so this is only reachable over the compose
  ``override-net`` network (override → torcs).
- Shared-secret bearer auth via `TORCS_CONTROL_SECRET`. Constant-time
  comparison with ``secrets.compare_digest``.
- Single-active-race invariant: one ``asyncio.Lock`` wraps the entire
  TOCTOU window in /control/start so two simultaneous requests cannot
  spawn two competing gym_torcs processes.
- SIGTERM with 5 s grace, SIGKILL fallback; ensures gym_torcs doesn't
  leak the SCR UDP port when the daemon itself is signaled.

This module deliberately stays self-contained — it imports nothing from
OVERRIDE's `core/` or `ingest/` packages. The torcs container's Python
environment is the IBM SkillsBuild lab image plus `pip install fastapi
uvicorn` at compose-startup time; pulling OVERRIDE deps in would bloat
that install.
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import signal
import subprocess
import time
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

logger = logging.getLogger("torcs.control_daemon")

# ──────────────────────────────────────────────────────────────────────────────
# Auth (constant-time compare; never reverts to ==)
# ──────────────────────────────────────────────────────────────────────────────

CONTROL_SECRET = os.environ.get("TORCS_CONTROL_SECRET", "")
if not CONTROL_SECRET:
    # Fail-loud on missing secret. The compose stack sets this from .env;
    # if it's empty, every request would otherwise compare empty-vs-empty
    # → effectively auth-disabled.
    raise RuntimeError(
        "TORCS_CONTROL_SECRET is empty. Refusing to start the control "
        "daemon with disabled auth. Set it in .env and re-run compose."
    )


def _verify_auth(authorization: Optional[str] = Header(default=None)) -> None:
    """Bearer-token auth.

    Returns 401 when no token / wrong scheme; 403 when token mismatches.
    Uses ``secrets.compare_digest`` so timing-attack-resistant.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    token = authorization[len("Bearer ") :]
    if not secrets.compare_digest(token.encode(), CONTROL_SECRET.encode()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


# ──────────────────────────────────────────────────────────────────────────────
# Subprocess state (guarded by a single lock)
# ──────────────────────────────────────────────────────────────────────────────

# All mutations + checks go through this lock. Wrapping the ENTIRE TOCTOU
# window in /control/start is load-bearing — two simultaneous requests must
# not both pass the "is anything running" check and both spawn gym_torcs.
_control_lock = asyncio.Lock()
_active_process: Optional[subprocess.Popen] = None
_active_session_id: Optional[str] = None
_active_started_at: Optional[float] = None

GYM_TORCS_DIR = "/home/student/workspace/gym_torcs"
TELEMETRY_DIR = f"{GYM_TORCS_DIR}/telemetry/"  # trailing slash → directory-mode
TORCS_SCRIPT = f"{GYM_TORCS_DIR}/torcs_jm_par.py"


def _process_alive() -> bool:
    """True if the active process exists and hasn't exited yet."""
    return _active_process is not None and _active_process.poll() is None


def _process_exit_code() -> Optional[int]:
    """None if process is still running OR no process; else the exit code."""
    if _active_process is None:
        return None
    return _active_process.poll()


# ──────────────────────────────────────────────────────────────────────────────
# Request / response shapes
# ──────────────────────────────────────────────────────────────────────────────


class StartRaceRequest(BaseModel):
    """Body for POST /control/start.

    All fields are operator-supplied and have light validation. Track names
    and session_ids use restricted character sets to keep the eventual
    filesystem paths predictable.
    """
    session_id: str = Field(pattern=r"^s_[A-Za-z0-9_]+$", min_length=3, max_length=80)
    track: str = Field(default="aalborg", pattern=r"^[a-z0-9_-]+$", max_length=40)
    laps: int = Field(default=10, ge=1, le=200)


class StartRaceResponse(BaseModel):
    session_id: str
    pid: int
    telemetry_dir: str


class StatusResponse(BaseModel):
    active: bool
    session_id: Optional[str] = None
    pid: Optional[int] = None
    uptime_s: Optional[float] = None
    exit_code: Optional[int] = None  # populated when last race exited; reset on next start


class StopResponse(BaseModel):
    status: str  # "stopped" | "no_active_race"
    session_id: Optional[str] = None
    exit_code: Optional[int] = None


# ──────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="TORCS Control Daemon",
    description=(
        "Internal control plane for the IBM SkillsBuild TORCS lab container. "
        "Reached only over the compose override-net (no host port exposed). "
        "See ADR-004 for the security model."
    ),
)


@app.get("/health")
async def health() -> dict:
    """Unauthenticated liveness probe used by the compose healthcheck."""
    return {"status": "ok"}


@app.get(
    "/control/status",
    response_model=StatusResponse,
    dependencies=[Depends(_verify_auth)],
)
async def control_status() -> StatusResponse:
    """Polled by OVERRIDE to render live-race state on /upload."""
    async with _control_lock:
        if _process_alive():
            uptime = time.monotonic() - (_active_started_at or time.monotonic())
            return StatusResponse(
                active=True,
                session_id=_active_session_id,
                pid=_active_process.pid if _active_process else None,
                uptime_s=round(uptime, 1),
            )
        return StatusResponse(active=False, exit_code=_process_exit_code())


@app.post(
    "/control/start",
    response_model=StartRaceResponse,
    dependencies=[Depends(_verify_auth)],
    status_code=status.HTTP_201_CREATED,
)
async def control_start(req: StartRaceRequest) -> StartRaceResponse:
    """Spawn a new gym_torcs subprocess for the given race configuration.

    Holds ``_control_lock`` across BOTH the check and the Popen so a
    second concurrent request cannot pass the check after the first
    request started Popen — the second request will see _process_alive()
    True and 409.
    """
    global _active_process, _active_session_id, _active_started_at

    async with _control_lock:
        if _process_alive():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Race already active for session {_active_session_id}.",
            )

        env = os.environ.copy()
        env["OVERRIDE_SESSION_ID"] = req.session_id
        env["OVERRIDE_TRACK"] = req.track
        env["OVERRIDE_LAPS"] = str(req.laps)
        # Directory-mode telemetry path — Phase 1 logger auto-generates
        # `run_{YYYYMMDDTHHMMSS}.jsonl` inside this dir, so each race
        # produces a distinct capture file.
        env["OVERRIDE_LOG_TELEMETRY"] = TELEMETRY_DIR

        try:
            proc = subprocess.Popen(
                ["python3", TORCS_SCRIPT],
                env=env,
                cwd=GYM_TORCS_DIR,
                # Detach from the daemon's stdin; keep stdout/stderr piped
                # so a crashed gym_torcs surfaces useful tail in logs.
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,  # new process group for clean signal targeting
            )
        except (OSError, FileNotFoundError) as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to spawn gym_torcs: {e}",
            )

        _active_process = proc
        _active_session_id = req.session_id
        _active_started_at = time.monotonic()
        logger.info(
            "control_start: spawned pid=%s session_id=%s track=%s laps=%s",
            proc.pid, req.session_id, req.track, req.laps,
        )

    return StartRaceResponse(
        session_id=req.session_id,
        pid=proc.pid,
        telemetry_dir=TELEMETRY_DIR,
    )


@app.post(
    "/control/stop",
    response_model=StopResponse,
    dependencies=[Depends(_verify_auth)],
)
async def control_stop() -> StopResponse:
    """Cleanly stop the active race.

    Two-stage termination per ADR-004:
    1. SIGTERM, wait 5 s for graceful shutdown.
    2. If still alive: SIGKILL, wait 2 s, give up.

    Idempotent: stopping with no active race returns 200 + ``no_active_race``,
    not an error. Lets the UI fire-and-forget on "Stop Race" clicks
    without first checking status.
    """
    global _active_process, _active_session_id, _active_started_at

    async with _control_lock:
        if not _process_alive():
            return StopResponse(status="no_active_race", exit_code=_process_exit_code())

        proc = _active_process
        sid = _active_session_id
        assert proc is not None  # _process_alive() guarantees this

        logger.info("control_stop: SIGTERM pid=%s session_id=%s", proc.pid, sid)
        proc.terminate()
        try:
            # subprocess.wait blocks the event loop — run in thread to keep
            # FastAPI responsive to other requests during the 5 s grace.
            await asyncio.wait_for(asyncio.to_thread(proc.wait), timeout=5.0)
            exit_code = proc.returncode
        except asyncio.TimeoutError:
            logger.warning("control_stop: SIGTERM grace expired, SIGKILL pid=%s", proc.pid)
            proc.kill()
            try:
                await asyncio.wait_for(asyncio.to_thread(proc.wait), timeout=2.0)
                exit_code = proc.returncode
            except asyncio.TimeoutError:
                # Should be physically impossible after SIGKILL on Linux.
                logger.error("control_stop: SIGKILL didn't reap pid=%s", proc.pid)
                exit_code = -9

        _active_started_at = None
        return StopResponse(status="stopped", session_id=sid, exit_code=exit_code)


# ──────────────────────────────────────────────────────────────────────────────
# Lifecycle: ensure gym_torcs doesn't outlive the daemon
# ──────────────────────────────────────────────────────────────────────────────


def _reap_on_signal(signum: int, _frame) -> None:
    """SIGTERM/SIGINT handler — kills the active gym_torcs before exit.

    Without this, a `podman stop torcs` would shut down uvicorn but leave
    gym_torcs holding the SCR UDP port; the next container start would
    fail to bind.
    """
    logger.info("daemon received signal=%s; reaping subprocess if any", signum)
    proc = _active_process
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    pass
        except OSError:
            pass
    # Re-raise the default behavior so uvicorn exits cleanly.
    raise SystemExit(0)


# Register at module import so uvicorn (which runs this file as
# `control_daemon:app`) honors the handler from the first request onward.
signal.signal(signal.SIGTERM, _reap_on_signal)
signal.signal(signal.SIGINT, _reap_on_signal)
