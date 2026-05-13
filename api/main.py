"""FastAPI runtime — endpoints per `docs/04-api.md`.

Implemented:
  GET    /api/health                                    liveness
  GET    /api/version                                   build + model IDs
  POST   /api/sessions                                  upload + run pipeline
  GET    /api/sessions                                  list summaries (paginated; Phase 1)
  GET    /api/sessions/{id}                             full debrief
  GET    /api/sessions/{id}/zones/{zid}?mode=...        per-zone (lazy fan)
  POST   /api/sessions/{id}/what-if                     FR-8 perturbation
  POST   /api/sessions/torcs-live                       volume-ingest (metadata-enriched)
  GET    /api/torcs-status                              live-ingest discovery (timestamps + duration)
  GET    /api/regulation-source                         G-4 metadata
  DELETE /api/sessions/{id}                             local cleanup

Still deferred to v1.1: `/laps` and `/zones` list endpoints (low rubric
value, not on the path for Sessions History UI).

Auth: none (single-user, replay-first per §1 + §10). CORS allows
`OVERRIDE_UI_ORIGIN` only.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time

# Load .env at module import so uvicorn picks up watsonx credentials etc.
# Tests bypass this by setting env vars directly.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal, Optional

import httpx
import pandas as pd
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Path as PathParam,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from analysis.perturbations import apply_perturbation
from core.fan_mode import FanModeParseError, translate_to_fan_mode
from core.guardian import WatsonxAIGuardianClient, WatsonxGuardianClient
from core.llm_clients import OllamaChatClient, probe_ollama_reachable
from core.pipeline import run_pipeline
from core.reasoning import WatsonxAIChatClient, WatsonxChatClient
from core.regs import (
    DEFAULT_CHUNKS_PATH,
    WatsonxAIEmbeddingClient,
    WatsonxEmbeddingClient,
    load_chunks,
)
from ingest.fastf1_parser import parse_fastf1_session  # noqa: F401  — surfaced for future use
from ingest.torcs_parser import parse_torcs_session
from ingest.schema import (
    LapFeatures,
    Recommendation,
    RegulationSource,
    Session,
    SessionSource,
    SessionStatus,
    SessionSummary,
    WhatIfRequest,
    WhatIfResult,
)

from .errors import api_error, map_watsonx_exception, new_request_id
from .observability import setup_tracing
from .storage import (
    delete_session,
    list_sessions as storage_list_sessions,
    load_session,
    save_recommendations_only,
    save_session,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────


def _max_upload_bytes() -> int:
    try:
        mb = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "25"))
    except ValueError:
        mb = 25
    return mb * 1024 * 1024


def _ui_origin() -> str:
    return os.environ.get("OVERRIDE_UI_ORIGIN", "http://localhost:3000")


def _chunks_path() -> Path:
    """Resolve the chunks JSON path. Honors `OVERRIDE_CHUNKS_PATH` env var
    so tests can point at a fixture without touching the real corpus."""
    raw = os.environ.get("OVERRIDE_CHUNKS_PATH")
    return Path(raw) if raw else DEFAULT_CHUNKS_PATH


_BUILD_STARTED_AT = time.monotonic()

# Per-session asyncio.Lock for serializing the lazy fan-mode read-modify-write
# in get_zone. Use setdefault to avoid the TOCTOU race where two parallel
# requests for a new session_id both check `not in` and both create new locks.
_fan_locks: dict[str, asyncio.Lock] = {}


# ──────────────────────────────────────────────────────────────────────────────
# Dependency providers (override-able for tests)
# ──────────────────────────────────────────────────────────────────────────────


def get_chat_client() -> WatsonxChatClient:
    """Factory — returns the chat client per ``OVERRIDE_LLM_RUNTIME`` env var.

    Default ``watsonx`` returns the existing ``WatsonxAIChatClient`` (no
    behavior change for v1.0 demo + video). ``ollama`` returns the new
    ``OllamaChatClient`` — fails LOUD at boot if the Ollama endpoint isn't
    reachable (gotcha: silent 60-second connection-refused on the first
    reasoning call is hostile; surface misconfiguration at the front door).

    Guardian + Embedding stay watsonx-only regardless of ``OVERRIDE_LLM_RUNTIME``
    — granite4:350m doesn't expose the BYOC scoring API or the multilingual
    embedding model. ``WATSONX_API_KEY`` is required even in ollama mode.
    See ``docs/adrs/ADR-003-llm-runtime-abstraction.md``.
    """
    runtime = (os.environ.get("OVERRIDE_LLM_RUNTIME") or "watsonx").strip().lower()
    if runtime == "ollama":
        base_url = os.environ.get("OVERRIDE_OLLAMA_BASE_URL") or "http://torcs:11434"
        ok, err = probe_ollama_reachable(base_url)
        if not ok:
            raise RuntimeError(
                f"OVERRIDE_LLM_RUNTIME=ollama but Ollama at {base_url!r} is not reachable: "
                f"{err}. Either bring up the TORCS lab container "
                f"(`podman compose --profile torcs up` or `./scripts/run_torcs_lab.sh`), "
                f"or point OVERRIDE_OLLAMA_BASE_URL at a reachable ollama instance, "
                f"or set OVERRIDE_LLM_RUNTIME=watsonx (default)."
            )
        return OllamaChatClient(base_url=base_url)
    if runtime != "watsonx":
        logger.warning(
            "OVERRIDE_LLM_RUNTIME=%r unrecognized; defaulting to watsonx", runtime,
        )
    return WatsonxAIChatClient()


def get_embedding_client() -> WatsonxEmbeddingClient:
    return WatsonxAIEmbeddingClient()


def get_guardian_client() -> WatsonxGuardianClient:
    return WatsonxAIGuardianClient()


# ──────────────────────────────────────────────────────────────────────────────
# Response shapes
# ──────────────────────────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: Literal["ok"]
    uptime_s: float


class TorcsLiveRequest(BaseModel):
    """Body for POST /api/sessions/torcs-live (v6 plan task 3.2).

    Defined at module scope so FastAPI's body-vs-query inference picks
    it up as a JSON body (in-function Pydantic models can confuse the
    OpenAPI introspector).

    Phase 1 additions: optional metadata captured at ingest time and
    embedded in the resulting SessionSummary (track_name, target_laps,
    notes). All three are operator-supplied and have no effect on the
    pipeline beyond surface presentation in history + comparison views.
    """
    run_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$", min_length=1, max_length=64)
    track_name: Optional[str] = Field(default=None, max_length=80)
    target_laps: Optional[int] = Field(default=None, ge=0, le=999)
    notes: Optional[str] = Field(default=None, max_length=500)


class SessionListResponse(BaseModel):
    """Paginated session-history page.

    Returned by GET /api/sessions. Newest sessions first; pagination via
    query params `limit` and `offset`.
    """
    sessions: list[SessionSummary]
    total: int = Field(ge=0, description="Total session count across all pages.")
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)


class TorcsStartRaceRequest(BaseModel):
    """Body for POST /api/torcs/start-race — proxied to the daemon's /control/start.

    Operator-supplied; OVERRIDE generates the session_id (not the caller).
    Phase 2.5: ``auto_launch_torcs`` controls whether the daemon launches
    the TORCS GUI itself or expects an operator-launched TORCS already
    running in noVNC.
    """
    track: str = Field(default="aalborg", pattern=r"^[a-z0-9_-]+$", max_length=40)
    laps: int = Field(default=5, ge=1, le=200)
    track_name: Optional[str] = Field(default=None, max_length=80)
    notes: Optional[str] = Field(default=None, max_length=500)
    auto_launch_torcs: bool = Field(
        default=False,
        description=(
            "When False (default, Phase 2.6 correction): the daemon spawns only "
            "the SCR client and expects the operator to have launched TORCS GUI "
            "manually in noVNC first (with scr_server as the configured driver). "
            "This is the 3D-rendering path — torcs -r is documented as headless "
            "and cannot show a 3D window regardless of XML config. "
            "When True: auto-launch via `torcs -r quickrace.xml` (headless, no 3D, "
            "but useful for batch testing and CI)."
        ),
    )


class TorcsControlPlaneStatus(BaseModel):
    """Returned by GET /api/torcs/control-status — reflects whether the
    in-container daemon is configured + reachable. UI uses this to render
    the Start/Stop buttons; when disabled or unreachable the buttons stay
    hidden.

    Phase 2.5: the daemon's race state machine (idle / launching /
    waiting_scr / connecting / active / stopping / cleanup) is surfaced
    via ``state`` for state-aware UI badges. `last_error` lets the UI
    distinguish graceful race-completion (last_error=null) from actual
    subprocess failures (last_error="...exit=N").
    """
    enabled: bool = Field(description="True when TORCS_CONTROL_URL + SECRET are both set on the override service.")
    reachable: bool = Field(description="True when the daemon's /health responded 200.")
    active: bool = Field(default=False, description="True when state == 'active' (compat field for old clients).")
    state: Optional[str] = Field(default=None, description="Daemon-side race state: idle | launching | waiting_scr | connecting | active | stopping | cleanup.")
    session_id: Optional[str] = None
    last_error: Optional[str] = None
    last_exit_code: Optional[int] = None
    detail: Optional[str] = Field(default=None, description="When not reachable, the reason for the UI to show.")


class TorcsTrack(BaseModel):
    name: str
    category: str  # road | oval | dirt


class TorcsTracksResponse(BaseModel):
    tracks: list[TorcsTrack]


class LiveLapStats(BaseModel):
    """One emitted record on the live-telemetry SSE stream.

    Emitted once per completed lap as the SSE generator detects new
    start-line crossings in the active session's JSONL capture.
    Energy values use ``analysis.torcs_energy`` constants — same math
    as the post-hoc parser, so live + final numbers stay in agreement.
    """
    lap: int = Field(ge=1, description="1-indexed lap number, FIA convention.")
    lap_time_s: float = Field(ge=0)
    avg_speed_kmh: float = Field(ge=0)
    max_speed_kmh: float = Field(ge=0)
    harvest_mj: float = Field(ge=0)
    deploy_mj: float = Field(ge=0)
    soc_end: float = Field(ge=0, le=1)
    fuel_used_kg: Optional[float] = Field(
        default=None,
        description="Δ fuel sensor reading across the lap; None if the parser couldn't extract it.",
    )


class VersionResponse(BaseModel):
    build: str
    git_sha: Optional[str]
    runtime: Literal["watsonx"]
    watsonx_region: str
    granite_instruct: str
    granite_guardian: str
    granite_embedding: str
    granite_ttm_r2: str
    regulation_source_present: bool


# ──────────────────────────────────────────────────────────────────────────────
# App
# ──────────────────────────────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Factory so tests can build an app with overridden dependencies."""
    app = FastAPI(
        title="OVERRIDE",
        version="0.1.0",
        description="Explainable AI race-strategy copilot — Tier 1 API surface.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[_ui_origin()],
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )

    # OpenTelemetry — no-op when OVERRIDE_TRACING=off (default).
    # Set OVERRIDE_TRACING=otlp + OTEL_EXPORTER_OTLP_ENDPOINT=localhost:4317
    # alongside a Jaeger / OTel Collector to capture the trace screenshot
    # for the README per docs/06-roadmap.md P3.6.
    setup_tracing(app)

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        rid = request.headers.get("X-Request-Id") or new_request_id()
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        # Pass-through if detail already looks like an ApiError payload
        if isinstance(exc.detail, dict) and "error_code" in exc.detail:
            payload = exc.detail
        else:
            payload = {
                "error_code": "INTERNAL_ERROR" if exc.status_code >= 500 else "NOT_FOUND",
                "message": str(exc.detail) if exc.detail else "Error",
                "detail": None,
                "request_id": getattr(request.state, "request_id", new_request_id()),
            }
        rid = payload.get("request_id") or new_request_id()
        return JSONResponse(
            status_code=exc.status_code,
            content=payload,
            headers={"X-Request-Id": rid},
        )

    # ── Endpoints ────────────────────────────────────────────────────────────

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", uptime_s=round(time.monotonic() - _BUILD_STARTED_AT, 2))

    @app.get("/api/version", response_model=VersionResponse)
    async def version() -> VersionResponse:
        chunks, meta = load_chunks(_chunks_path())
        return VersionResponse(
            build="v0.1.0",
            git_sha=os.environ.get("GIT_SHA"),
            runtime="watsonx",
            watsonx_region=_extract_region(os.environ.get("WATSONX_URL", "")),
            granite_instruct=os.environ.get("GRANITE_INSTRUCT", "ibm/granite-4-h-small"),
            granite_guardian=os.environ.get("GRANITE_GUARDIAN", "ibm/granite-guardian-3-8b"),
            granite_embedding=os.environ.get(
                "GRANITE_EMBEDDING", "ibm/granite-embedding-278m-multilingual"
            ),
            granite_ttm_r2=os.environ.get("TTM_R2_REPO", "ibm-granite/granite-timeseries-ttm-r2"),
            regulation_source_present=meta.get("g4_status") == "closed",
        )

    @app.get("/api/regulation-source")
    async def regulation_source(request: Request):
        chunks, meta = load_chunks(_chunks_path())
        if not chunks or meta.get("g4_status") != "closed":
            raise api_error(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="NOT_FOUND",
                message="Regulation source not yet verified (G-4 pending).",
                detail=f"g4_status={meta.get('g4_status')!r}",
                request_id=getattr(request.state, "request_id", None),
            )
        return chunks[0].source.model_dump(mode="json")

    @app.post("/api/sessions", status_code=status.HTTP_201_CREATED)
    async def create_session(
        request: Request,
        file: UploadFile = File(...),
        source: Annotated[Literal["torcs", "fastf1"], Form()] = "torcs",
        track_id: Annotated[Optional[str], Form()] = None,
        soc_max: Annotated[float, Form()] = 4.0,
        chat_client: WatsonxChatClient = Depends(get_chat_client),
        embedding_client: WatsonxEmbeddingClient = Depends(get_embedding_client),
        guardian_client: WatsonxGuardianClient = Depends(get_guardian_client),
    ):
        rid = getattr(request.state, "request_id", new_request_id())

        # Read upload, enforce size limit
        body = await file.read()
        if len(body) > _max_upload_bytes():
            raise api_error(
                status_code=413,  # Content Too Large
                error_code="FILE_TOO_LARGE",
                message=f"Upload exceeds {_max_upload_bytes() // 1024 // 1024} MB limit.",
                request_id=rid,
            )
        if not body:
            raise api_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="INVALID_FILE_FORMAT",
                message="Empty upload.",
                request_id=rid,
            )

        # Parse the uploaded file into LapFeatures
        try:
            laps = _parse_upload(body, source=source, filename=file.filename or "")
        except (ValueError, KeyError) as e:
            raise api_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="PARSE_FAILED",
                message=f"Could not parse uploaded {source} file.",
                detail=str(e)[:300],
                request_id=rid,
            )
        if not laps:
            raise api_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="PARSE_FAILED",
                message="Upload produced 0 valid lap rows.",
                request_id=rid,
            )

        # Run the pipeline
        try:
            session = await run_pipeline(
                laps=laps,
                soc_max=soc_max,
                chat_client=chat_client,
                embedding_client=embedding_client,
                guardian_client=guardian_client,
                source=source,
                track_id=track_id,
                chunks_path=_chunks_path(),
            )
        except HTTPException:
            raise
        except Exception as e:
            raise map_watsonx_exception(e, request_id=rid)

        # Persist + return
        save_session(session)
        return session.model_dump(mode="json")

    @app.get("/api/sessions", response_model=SessionListResponse)
    async def list_sessions_endpoint(
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        """List session summaries, newest first.

        Phase 1 ship — replaces the SessionsPage v1.1 stub. Backs the
        Session History view at /sessions in the UI. Pagination via
        ``limit`` (default 50, max 200) and ``offset``.

        Phase 2 v1.0 enrichment: for sessions with ``status=ACTIVE``
        (stub rows written by /api/torcs/start-race), the persisted
        ``lap_count`` is 0 until the ingest path runs the full pipeline.
        We patch in a LIVE lap_count by reading the JSONL on the shared
        torcs-telemetry volume — so the /sessions row reflects the same
        progress the operator sees in the live SSE table at /session/{id}.
        Reads are bounded by one IO per active session; there's at most
        one active session at a time in v1.0, so the cost is negligible.
        """
        page, total = storage_list_sessions(limit=limit, offset=offset)

        # Live-enrich ACTIVE sessions
        tdir = _telemetry_dir()
        enriched: list[SessionSummary] = []
        for s in page:
            if s.status == SessionStatus.ACTIVE and s.telemetry_file:
                jsonl_path = tdir / s.telemetry_file
                if jsonl_path.is_file():
                    try:
                        live = _get_current_lap(_read_jsonl_safe(jsonl_path))
                    except Exception:
                        live = s.lap_count  # fall back gracefully
                    if live != s.lap_count:
                        s = s.model_copy(update={"lap_count": live})
            enriched.append(s)

        return SessionListResponse(
            sessions=enriched,
            total=total,
            limit=limit,
            offset=offset,
        )

    @app.get("/api/sessions/{session_id}")
    async def get_session(
        request: Request,
        session_id: str = PathParam(..., pattern=r"^s_[A-Za-z0-9_]+$"),
    ):
        rid = getattr(request.state, "request_id", new_request_id())
        session = load_session(session_id)
        if session is None:
            raise api_error(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="NOT_FOUND",
                message=f"Session {session_id} not found.",
                request_id=rid,
            )
        return session.model_dump(mode="json")

    @app.get("/api/sessions/{session_id}/zones/{zone_id}")
    async def get_zone(
        request: Request,
        session_id: str = PathParam(..., pattern=r"^s_[A-Za-z0-9_]+$"),
        zone_id: str = PathParam(..., pattern=r"^z_[A-Za-z0-9_]+$"),
        mode: Literal["engineer", "fan", "both"] = Query("engineer"),
        chat_client: WatsonxChatClient = Depends(get_chat_client),
    ):
        rid = getattr(request.state, "request_id", new_request_id())
        session = load_session(session_id)
        if session is None:
            raise api_error(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="NOT_FOUND",
                message=f"Session {session_id} not found.",
                request_id=rid,
            )

        rec = next((r for r in session.recommendations if r.zone.zone_id == zone_id), None)
        if rec is None:
            raise api_error(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="NOT_FOUND",
                message=f"Zone {zone_id} not found in session {session_id}.",
                request_id=rid,
            )

        # Lazy Fan Mode: only call when requested AND not already cached
        if mode in ("fan", "both") and rec.fan is None:
            try:
                fan = await asyncio.to_thread(
                    translate_to_fan_mode, rec.reasoning, client=chat_client
                )
            except FanModeParseError as e:
                raise api_error(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    error_code="INTERNAL_ERROR",
                    message="Fan Mode translation produced malformed output.",
                    detail=str(e)[:200],
                    request_id=rid,
                )
            except Exception as e:
                raise map_watsonx_exception(e, request_id=rid)

            # Persist the cache. Serialize the read-modify-write per session so
            # parallel ?mode=fan requests on different zones don't clobber each
            # other (each one would otherwise overwrite recommendations.json
            # from its stale snapshot). The watsonx call above is intentionally
            # outside the lock so different-zone translations stay concurrent.
            lock = _fan_locks.setdefault(session_id, asyncio.Lock())
            async with lock:
                current = load_session(session_id)
                if current is None:
                    # Session deleted between the unlocked read and the locked
                    # write — surface the now-correct 404 rather than recreate.
                    raise api_error(
                        status_code=status.HTTP_404_NOT_FOUND,
                        error_code="NOT_FOUND",
                        message=f"Session {session_id} not found.",
                        request_id=rid,
                    )
                updated_recs = [
                    r.model_copy(update={"fan": fan}) if r.zone.zone_id == zone_id else r
                    for r in current.recommendations
                ]
                # Atomic write — only recommendations.json, not the full session.
                # Index/summary/laps/forecast are session-creation invariants.
                save_recommendations_only(session_id, updated_recs)
            rec = next(r for r in updated_recs if r.zone.zone_id == zone_id)

        # Engineer-only mode → strip the fan field for a clean response
        if mode == "engineer":
            rec = rec.model_copy(update={"fan": None})

        return rec.model_dump(mode="json")

    @app.post("/api/sessions/{session_id}/what-if")
    async def what_if(
        request: Request,
        body: WhatIfRequest,
        session_id: str = PathParam(..., pattern=r"^s_[A-Za-z0-9_]+$"),
        chat_client: WatsonxChatClient = Depends(get_chat_client),
        embedding_client: WatsonxEmbeddingClient = Depends(get_embedding_client),
        guardian_client: WatsonxGuardianClient = Depends(get_guardian_client),
    ):
        """FR-8 what-if perturbations — pin three exploratory scenarios.

        Spec lives at ``docs/plans/whatif-semantics.md`` (deleted in this PR
        per plan-file-lifecycle). The handler composes three pure pieces:
          1. ``analysis.perturbations.apply_perturbation`` mutates the lap
             list per the request (delay_first_deploy / skip_harvest_zone /
             extend_override).
          2. ``core.pipeline.run_pipeline`` runs the FULL pipeline against
             the perturbed laps — same reasoning + Pass-1 + Pass-2 + Fan
             path as ``POST /api/sessions``. No fork.
          3. Result cached on disk at
             ``data/sessions/{id}/whatif/{sha256(request)[:16]}.json``
             so a judge clicking the same scenario repeatedly during demo
             exploration doesn't re-spend watsonx tokens.

        Returns a ``WhatIfResult`` pairing original + perturbed
        Recommendation lists for the UI's side-by-side diff renderer.
        """
        rid = getattr(request.state, "request_id", new_request_id())

        original = load_session(session_id)
        if original is None:
            raise api_error(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="NOT_FOUND",
                message=f"Session {session_id} not found.",
                request_id=rid,
            )

        # Validate the zone exists in the session when the perturbation needs it.
        # Builds the zone_id → lap_number lookup the dispatcher consumes.
        zone_lookup: dict[str, int] = {
            r.zone.zone_id: r.zone.lap_number for r in original.recommendations
        }
        if body.zone_id is not None and body.zone_id not in zone_lookup:
            raise api_error(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="NOT_FOUND",
                message=f"Zone {body.zone_id} not found in session {session_id}.",
                request_id=rid,
            )

        # Cache key per gotcha #4 — sha256 of the canonical Pydantic JSON.
        # 16 hex chars is more than enough; filename-safe; deterministic
        # across runs.
        import hashlib
        cache_key = hashlib.sha256(body.model_dump_json().encode()).hexdigest()[:16]

        sessions_root = _sessions_root_for_request()
        whatif_dir = sessions_root / session_id / "whatif"
        cache_path = whatif_dir / f"{cache_key}.json"

        # Cache hit → fast path; no pipeline re-run, no watsonx tokens.
        if cache_path.exists():
            return WhatIfResult.model_validate_json(cache_path.read_text()).model_dump(mode="json")

        # Cache miss — apply the perturbation, re-run the pipeline.
        perturbed_laps, note = apply_perturbation(
            original.laps, body, zone_lap_lookup=zone_lookup,
        )

        try:
            perturbed_session = await run_pipeline(
                laps=perturbed_laps,
                soc_max=4.0,  # matches POST /api/sessions default; per gotcha pipeline reads from LapFeatures bounds
                chat_client=chat_client,
                embedding_client=embedding_client,
                guardian_client=guardian_client,
                source=original.summary.source,
                track_id=original.summary.track_id,
                chunks_path=_chunks_path(),
            )
        except Exception as e:
            raise map_watsonx_exception(e, request_id=rid)

        result = WhatIfResult(
            request=body,
            cache_key=cache_key,
            original=list(original.recommendations),
            perturbed=list(perturbed_session.recommendations),
            note=note,
        )

        # Persist to cache. Best-effort — a write failure shouldn't fail the
        # request (the user has the data in the response).
        try:
            whatif_dir.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(result.model_dump_json(indent=2))
        except OSError as e:
            logger.warning("what_if cache write failed (%s): %s", cache_path, e)

        return result.model_dump(mode="json")

    @app.delete("/api/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def remove_session(
        session_id: str = PathParam(..., pattern=r"^s_[A-Za-z0-9_]+$"),
    ):
        delete_session(session_id)
        # Always 204 (idempotent)

    @app.get("/api/sessions/{session_id}/stream")
    async def stream_session(
        request: Request,
        session_id: str = PathParam(..., pattern=r"^s_[A-Za-z0-9_]+$"),
    ):
        """Server-Sent Events: live lap-completion stream for an ACTIVE session.

        v1.1 §3 ship. Polls the session's underlying JSONL capture at 1 Hz,
        emits ``LiveLapStats`` for each newly-completed lap, closes the
        stream when the race ends.

        Race-end detection — **file-stall heuristic**:
        - Track the JSONL file's mtime + the last-detected lap count.
        - If mtime hasn't advanced AND lap count hasn't advanced for
          ``STALL_SECONDS_THRESHOLD`` seconds, emit ``{"event":"race_ended"}``
          and close.

        Disconnect handling: ``await request.is_disconnected()`` short-circuits
        each iteration so a closed browser tab releases the generator within
        ~1 s rather than leaking until the stall timeout fires.

        Endpoint returns 404 only when the session itself doesn't exist; an
        ACTIVE session with no resolvable telemetry_file emits a single
        ``{"event":"no_telemetry"}`` and closes.
        """
        STALL_SECONDS_THRESHOLD = 10.0
        POLL_INTERVAL_S = 1.0

        session = load_session(session_id)
        if session is None:
            raise api_error(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="NOT_FOUND",
                message=f"Session {session_id} not found.",
                request_id=getattr(request.state, "request_id", new_request_id()),
            )

        def _sse(payload: dict) -> str:
            return f"data: {json.dumps(payload)}\n\n"

        async def event_generator():
            try:
                # First yield: snapshot the session state so the client knows
                # the connection is live and can render an initial empty state.
                yield _sse({
                    "event": "connected",
                    "session_id": session_id,
                    "status": session.summary.status.value if hasattr(session.summary.status, "value") else str(session.summary.status),
                })

                tfile = _find_telemetry_file(session_id)
                if tfile is None:
                    yield _sse({
                        "event": "no_telemetry",
                        "message": (
                            "This session has no telemetry_file (or the underlying "
                            "JSONL is missing). Live streaming requires the torcs-live "
                            "ingest path with an active capture."
                        ),
                    })
                    return

                emitted_laps = 0
                last_mtime: Optional[float] = None
                stall_started: Optional[float] = None

                while True:
                    if await request.is_disconnected():
                        break

                    try:
                        cur_mtime = tfile.stat().st_mtime
                    except OSError:
                        yield _sse({"event": "race_ended", "reason": "file_gone"})
                        break

                    observations = _read_jsonl_safe(tfile)
                    completed = _get_current_lap(observations)

                    # Emit any newly-completed laps
                    while emitted_laps < completed:
                        next_lap = emitted_laps + 1
                        stats = _aggregate_lap(observations, next_lap)
                        if stats is not None:
                            yield _sse({"event": "lap", **stats.model_dump()})
                        emitted_laps = next_lap
                        # Yield control between lap emits so a multi-lap
                        # catch-up doesn't block the disconnect check.
                        await asyncio.sleep(0)

                    # File-stall race-end heuristic
                    now = time.monotonic()
                    progressed = (last_mtime is None) or (cur_mtime > last_mtime)
                    if progressed:
                        last_mtime = cur_mtime
                        stall_started = None
                    else:
                        if stall_started is None:
                            stall_started = now
                        elif now - stall_started >= STALL_SECONDS_THRESHOLD:
                            yield _sse({
                                "event": "race_ended",
                                "reason": "file_stall",
                                "total_laps": emitted_laps,
                            })
                            break

                    await asyncio.sleep(POLL_INTERVAL_S)
            except asyncio.CancelledError:
                # Client disconnected or server shutdown — clean exit, don't
                # surface as an error.
                pass

        # Cloudflare's edge auto-disables buffering for text/event-stream
        # (confirmed against their documented behavior). The X-Accel-Buffering
        # header is a belt-and-suspenders signal for any nginx-like proxy
        # also in the path.
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ── Live TORCS ingest (v6 plan task 3.2, hard floor) ─────────────────────

    # ── Phase 2 control plane: proxy to the torcs-container daemon ──────────

    @app.get("/api/torcs/control-status", response_model=TorcsControlPlaneStatus)
    async def torcs_control_status():
        """Reports whether the in-container TORCS control daemon is
        configured and reachable. The UI calls this on /upload to decide
        whether to render the Start/Stop race buttons. Always returns 200
        so the UI can branch on `enabled` + `reachable` without 404 noise.
        """
        url, secret = _torcs_control_config()
        if url is None or secret is None:
            return TorcsControlPlaneStatus(
                enabled=False,
                reachable=False,
                detail="TORCS_CONTROL_URL + SECRET not set; control plane disabled.",
            )
        try:
            status_code, body = await _call_torcs_daemon("GET", "/control/status", timeout=3.0)
        except HTTPException as e:
            # _call_torcs_daemon raises HTTPException only for unreachable;
            # surface as reachable=False so the UI hides the buttons rather
            # than showing an angry error banner.
            detail = "Control daemon not reachable yet — torcs container may still be booting."
            if hasattr(e, "detail") and isinstance(e.detail, dict):
                detail = e.detail.get("detail", detail) or detail
            return TorcsControlPlaneStatus(enabled=True, reachable=False, detail=detail)
        if status_code != 200:
            return TorcsControlPlaneStatus(
                enabled=True, reachable=False,
                detail=f"Daemon returned HTTP {status_code}",
            )
        return TorcsControlPlaneStatus(
            enabled=True,
            reachable=True,
            active=bool(body.get("active", False)),
            state=body.get("state"),
            session_id=body.get("session_id"),
            last_error=body.get("last_error"),
            last_exit_code=body.get("last_exit_code"),
        )

    @app.get("/api/torcs/tracks", response_model=TorcsTracksResponse)
    async def torcs_tracks():
        """List available TORCS tracks on the lab container's filesystem.

        Phase 2.5 — feeds the UI track dropdown. The daemon scans
        /usr/local/torcs/share/games/torcs/tracks/ once on first call and
        returns the cached list grouped by category (road | oval | dirt).
        Empty tracks list when the control plane is disabled or unreachable
        — the UI falls back to a curated hardcoded list in that case.
        """
        url, secret = _torcs_control_config()
        if url is None or secret is None:
            return TorcsTracksResponse(tracks=[])
        try:
            status_code, body = await _call_torcs_daemon("GET", "/control/tracks", timeout=5.0)
        except HTTPException:
            return TorcsTracksResponse(tracks=[])
        if status_code != 200 or not isinstance(body.get("tracks"), list):
            return TorcsTracksResponse(tracks=[])
        out: list[TorcsTrack] = []
        for t in body["tracks"]:
            if isinstance(t, dict) and isinstance(t.get("name"), str) and isinstance(t.get("category"), str):
                out.append(TorcsTrack(name=t["name"], category=t["category"]))
        return TorcsTracksResponse(tracks=out)

    @app.post("/api/torcs/start-race", status_code=status.HTTP_201_CREATED)
    async def torcs_start_race(req: TorcsStartRaceRequest):
        """Generate a session_id, ask the daemon to spawn gym_torcs.

        Phase 2 v1.0 enhancement: also persists a *stub* Session with
        ``status=ACTIVE`` and ``telemetry_file=<session_id>.jsonl`` so
        ``/session/{id}`` immediately renders the LiveTelemetry panel.
        The eventual ``POST /api/sessions/torcs-live`` with the same
        ``run_id`` will UPDATE this row (the pipeline accepts
        ``session_id=`` to override the auto-generated slug) rather
        than inserting a new one — keeps the end-to-end id chain coherent.
        """
        # OVERRIDE owns session_id generation so the daemon's input
        # validation is the only validator that sees this value — keeps
        # the trust boundary small.
        import secrets as _secrets
        session_id = f"s_torcs_live_{int(time.time())}_{_secrets.token_hex(4)}"
        telemetry_filename = f"{session_id}.jsonl"

        status_code, body = await _call_torcs_daemon(
            "POST",
            "/control/start",
            json_body={
                "session_id": session_id,
                "track": req.track,
                "laps": req.laps,
                # Make the JSONL filename deterministic so the eventual
                # torcs-live ingest's run_id matches the daemon-issued
                # session_id 1:1.
                "telemetry_filename": telemetry_filename,
                # Phase 2.5: daemon launches TORCS itself by default.
                "auto_launch_torcs": req.auto_launch_torcs,
            },
            # Launch + SCR-port poll can take up to ~20s on first run; give
            # the daemon time to finish before this proxy call times out.
            timeout=30.0,
        )
        if status_code == 409:
            raise api_error(
                status_code=status.HTTP_409_CONFLICT,
                error_code="RACE_ACTIVE",
                message="A TORCS race is already running.",
                detail=body.get("detail", "Stop the active race first via POST /api/torcs/stop-race."),
                request_id=new_request_id(),
            )
        if status_code >= 400:
            raise api_error(
                status_code=status.HTTP_502_BAD_GATEWAY,
                error_code="CONTROL_FAILED",
                message=f"TORCS daemon refused start (HTTP {status_code}).",
                detail=str(body)[:300],
                request_id=new_request_id(),
            )
        # Write a stub Session with status=ACTIVE so /session/<id> renders
        # the LiveTelemetry panel from the moment the user clicks Start.
        # Empty laps/recommendations — the eventual torcs-live POST
        # replaces them with real pipeline output via run_pipeline(session_id=...).
        try:
            stub_summary = SessionSummary(
                session_id=session_id,
                uploaded_at=datetime.now(timezone.utc),
                source="torcs",
                lap_count=0,
                forecast_available=False,
                zone_count=0,
                track_id=f"torcs-live/{session_id}",
                session_source=SessionSource.TORCS_LIVE,
                status=SessionStatus.ACTIVE,
                track_name=req.track_name,
                target_laps=req.laps,
                started_at=datetime.now(timezone.utc),
                completed_at=None,
                telemetry_file=telemetry_filename,
                note=req.notes,
            )
            stub_session = Session(
                summary=stub_summary,
                laps=[],
                forecast=None,
                recommendations=[],
                regulation_source=None,
            )
            save_session(stub_session)
        except Exception:
            # Stub-write failures shouldn't fail the race-start — the
            # daemon's gym_torcs is already running. Log and continue;
            # the ingest path will create the session row as before.
            logger.exception("torcs_start_race: stub session write failed (non-fatal)")

        return {
            "session_id": session_id,
            "pid": body.get("pid"),
            "telemetry_dir": body.get("telemetry_dir"),
            "track": req.track,
            "laps": req.laps,
            # Phase 2.5: forward the TORCS wrapper PID + state from the
            # daemon's StartRaceResponse so the UI can render a useful
            # success message ("Daemon spawned torcs pid=N + scr-client
            # pid=M") instead of a "?" for the torcs side.
            "torcs_pid": body.get("torcs_pid"),
            "state": body.get("state"),
            # The UI uses these to compose a deep-link or to remember the
            # operator-supplied metadata for the eventual torcs-live POST.
            "track_name_hint": req.track_name,
            "notes_hint": req.notes,
        }

    @app.post("/api/torcs/stop-race")
    async def torcs_stop_race():
        """Stop the active race (idempotent — no active race → 200 with
        status="no_active_race", not an error)."""
        status_code, body = await _call_torcs_daemon("POST", "/control/stop", timeout=15.0)
        if status_code >= 400:
            raise api_error(
                status_code=status.HTTP_502_BAD_GATEWAY,
                error_code="CONTROL_FAILED",
                message=f"TORCS daemon refused stop (HTTP {status_code}).",
                detail=str(body)[:300],
                request_id=new_request_id(),
            )
        return body

    @app.get("/api/torcs-status")
    async def torcs_status():
        """List JSONL replays available on the shared ``torcs-telemetry``
        volume — produced by ``RaceYourCode/gym_torcs/torcs_jm_par.py`` when
        ``OVERRIDE_LOG_TELEMETRY`` is set inside the torcs compose service.

        Response is always 200; ``available: false`` when the dir doesn't
        exist or holds no JSONL files. The UI's UploadPage banner polls
        this to enable/disable the "Ingest live TORCS run" affordance
        without surfacing 404s during the no-torcs-profile common case.
        """
        tdir = _telemetry_dir()
        if not tdir.is_dir():
            return {"available": False, "runs": []}
        runs = []
        for p in sorted(tdir.glob("*.jsonl"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                stat = p.stat()
            except OSError:
                continue
            size = stat.st_size
            # Cheap lap-count estimate: gym_torcs ticks at ~50 Hz, lap is
            # ~100 s typical → ~5000 ticks/lap. Surfaced as a guide for the
            # UI banner, not authoritative.
            tick_estimate = max(1, size // 1000)  # ~1 KB/tick observed
            # Phase 1: surface capture window from first-observation `t`
            # (logger injection) with mtime fallback. duration_seconds
            # gives the UI a glance at how long the run actually ran.
            last_written = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            started = _extract_start_time(p) or last_written
            duration = (last_written - started).total_seconds()
            runs.append({
                "run_id": p.stem,
                "size_bytes": size,
                "lap_count_estimate": tick_estimate // 5000,
                "started_at": started.isoformat(),
                "last_written_at": last_written.isoformat(),
                "duration_seconds": max(0.0, duration),
            })
        return {"available": bool(runs), "runs": runs}

    @app.post("/api/sessions/torcs-live", status_code=status.HTTP_201_CREATED)
    async def torcs_live(
        request: Request,
        body: TorcsLiveRequest,
        chat_client: WatsonxChatClient = Depends(get_chat_client),
        embedding_client: WatsonxEmbeddingClient = Depends(get_embedding_client),
        guardian_client: WatsonxGuardianClient = Depends(get_guardian_client),
    ):
        """Ingest a JSONL replay from the shared ``torcs-telemetry`` volume.

        Body: ``{"run_id": "<slug>"}``. Reads
        ``/app/data/telemetry/<run_id>.jsonl``, parses via
        ``ingest.torcs_parser.parse_torcs_session`` (JSONL safe-read per
        gotcha #12 handles partial tail lines and JSONDecodeError mid-stream),
        runs the full pipeline, persists via ``save_session``, returns the
        full Session.

        404 NOT_FOUND when the run_id doesn't resolve to a readable file —
        the UI's UploadPage banner enabled the option from a stale status
        snapshot, or the user typed a bad slug via curl.

        Same dependency providers as POST /api/sessions (compose,
        don't fork). Honors OVERRIDE_LLM_RUNTIME via the chat-client
        factory; emits OTel spans through the existing pipeline
        instrumentation.
        """
        rid = getattr(request.state, "request_id", new_request_id())

        tdir = _telemetry_dir()
        jsonl_path = tdir / f"{body.run_id}.jsonl"
        if not jsonl_path.is_file():
            raise api_error(
                status_code=status.HTTP_404_NOT_FOUND,
                error_code="NOT_FOUND",
                message=f"Telemetry run {body.run_id!r} not found at {jsonl_path}.",
                detail=(
                    "Ensure the TORCS compose service is up "
                    "(`podman compose --profile torcs up`) AND "
                    "OVERRIDE_LOG_TELEMETRY was set when running torcs_jm_par.py."
                ),
                request_id=rid,
            )

        try:
            laps = parse_torcs_session(jsonl_path)
        except (ValueError, FileNotFoundError) as e:
            raise api_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                error_code="PARSE_FAILED",
                message=f"Could not parse TORCS replay {body.run_id!r}.",
                detail=str(e)[:300],
                request_id=rid,
            )

        # Phase 2 v1.0 — if a stub Session row was pre-created by
        # /api/torcs/start-race (run_id is the daemon-issued session_id),
        # adopt that session_id so the eventual write UPDATES the stub
        # instead of inserting a fresh row under a new pipeline-generated
        # slug. Recognized by the s_torcs_live_ prefix; falls back to
        # auto-generation for legacy curl-driven ingest (run_id="baseline"
        # etc.) — backward-compatible.
        adopt_session_id: Optional[str] = (
            body.run_id if body.run_id.startswith("s_torcs_live_") else None
        )

        try:
            session = await run_pipeline(
                laps=laps,
                soc_max=4.0,
                chat_client=chat_client,
                embedding_client=embedding_client,
                guardian_client=guardian_client,
                source="torcs",
                track_id=f"torcs-live/{body.run_id}",
                chunks_path=_chunks_path(),
                session_id=adopt_session_id,
            )
        except HTTPException:
            raise
        except Exception as e:
            raise map_watsonx_exception(e, request_id=rid)

        # Phase 1 enrichment: stamp the summary with session_source +
        # lifecycle metadata. SessionSummary is frozen — build a new
        # one via model_copy, then a new Session to wrap it. The
        # pipeline doesn't know about these fields by design (keeps
        # core.pipeline domain-pure).
        stat = jsonl_path.stat()
        last_written = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        started = _extract_start_time(jsonl_path) or last_written
        enriched_summary = session.summary.model_copy(update={
            "session_source": SessionSource.TORCS_LIVE,
            "status": SessionStatus.COMPLETED,
            "track_name": body.track_name,
            "target_laps": body.target_laps,
            "started_at": started,
            "completed_at": last_written,
            "telemetry_file": jsonl_path.name,
            "note": body.notes or session.summary.note,
        })
        enriched_session = session.model_copy(update={"summary": enriched_summary})

        save_session(enriched_session)
        return enriched_session.model_dump(mode="json")

    # ── Static UI mount (v6 plan task 3.1) ───────────────────────────────────
    # The container image builds ui/dist via Stage 1 of the Dockerfile and
    # COPYs it to /app/ui/dist. When that directory exists, mount it so the
    # single image + single port serves both the API (/api/*) and the SPA
    # (/, /upload, /session/:id, etc).
    #
    # Local-dev path: developers running `uvicorn api.main:app` from the
    # repo root without a build skip this — vite dev server at :3000 proxies
    # /api/* to :8000, so the SPA serving stays a frontend concern.
    #
    # Routes:
    #   /assets/*       → built JS/CSS/fonts from ui/dist/assets/
    #   /favicon.*      → built favicon
    #   /<spa-route>    → ui/dist/index.html (React Router takes over)
    # API routes registered above (/api/*) win over the SPA catchall because
    # they're registered earlier; the catchall is the LAST handler.
    _ui_dist = Path(__file__).resolve().parent.parent / "ui" / "dist"
    if _ui_dist.is_dir():
        # Hashed-bundle assets — long-cache-friendly subpath.
        app.mount(
            "/assets",
            StaticFiles(directory=str(_ui_dist / "assets")),
            name="ui-assets",
        )
        _index_html = _ui_dist / "index.html"

        @app.get("/{full_path:path}", include_in_schema=False)
        async def _spa_catchall(full_path: str):
            """Serve index.html for any non-/api/* path so React Router
            handles client-side routes (e.g. /session/s_torcs_engineer_demo).
            Bare files (favicon.ico, logo.png, manifest.json) in ui/dist root
            also get served here."""
            if full_path.startswith("api/"):
                # Defensive: FastAPI route precedence should already prevent
                # this branch, but guard against future route changes.
                raise HTTPException(status_code=404)
            candidate = _ui_dist / full_path
            if candidate.is_file():
                return FileResponse(str(candidate))
            return FileResponse(str(_index_html))

        logger.info("ui-static: mounted ui/dist at /")
    else:
        logger.info(
            "ui-static: %s missing — running API-only "
            "(vite dev server expected on :3000 in dev mode)",
            _ui_dist,
        )

    return app


def _sessions_root_for_request() -> Path:
    """Resolve the sessions storage root the same way api/storage.py does.

    Duplicated locally to keep the storage helpers minimal-surface and
    avoid leaking the path resolution into every API call site. Matches
    storage._sessions_root() exactly.
    """
    raw = os.environ.get("SESSIONS_DIR")
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parent.parent / "data" / "sessions"


def _torcs_control_config() -> tuple[Optional[str], Optional[str]]:
    """Return (base_url, secret) for the TORCS control daemon if configured.

    Returns (None, None) when either env var is unset — the proxy endpoints
    use this to short-circuit with a clear ``CONTROL_DISABLED`` error
    instead of trying to contact a nonexistent daemon.
    """
    url = os.environ.get("TORCS_CONTROL_URL") or None
    secret = os.environ.get("TORCS_CONTROL_SECRET") or None
    return (url, secret)


async def _call_torcs_daemon(
    method: str,
    path: str,
    *,
    json_body: Optional[dict] = None,
    timeout: float = 10.0,
) -> tuple[int, dict]:
    """Proxy a request to the TORCS control daemon with bearer auth.

    Returns (status_code, response_body). Body is always a dict (decoded
    JSON or wrapped error). Raises HTTPException only for ``CONTROL_DISABLED``
    (config-time) and ``CONTROL_UNREACHABLE`` (network-level); other
    responses pass through with their status codes for the caller to
    re-raise as appropriate. Keeps the proxy layer's exception surface
    narrow and predictable.
    """
    url, secret = _torcs_control_config()
    if url is None or secret is None:
        raise api_error(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_code="CONTROL_DISABLED",
            message="TORCS control plane is not configured on this OVERRIDE instance.",
            detail=(
                "Set TORCS_CONTROL_URL + TORCS_CONTROL_SECRET in .env and "
                "bring up `podman compose --profile torcs up` to enable "
                "interactive race control. The live-ingest path "
                "(POST /api/sessions/torcs-live) still works regardless."
            ),
            request_id=new_request_id(),
        )
    headers = {"Authorization": f"Bearer {secret}"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method, f"{url}{path}", headers=headers, json=json_body)
    except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
        raise api_error(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_code="CONTROL_UNREACHABLE",
            message="TORCS control daemon is not reachable.",
            detail=(
                f"Could not reach {url}{path}: {e}. The torcs compose "
                "service may still be starting (boot takes ~90 s on first "
                "run; the daemon waits for noVNC before listening)."
            ),
            request_id=new_request_id(),
        )
    try:
        body = resp.json() if resp.content else {}
    except (ValueError, json.JSONDecodeError):
        body = {"raw": resp.text[:500]}
    return resp.status_code, body


def _find_telemetry_file(session_id: str) -> Optional[Path]:
    """Resolve the JSONL capture backing an ACTIVE session.

    For sessions ingested via ``POST /api/sessions/torcs-live``, the
    summary records ``telemetry_file`` (basename). The file lives in
    the shared ``torcs-telemetry`` volume directory. Returns None when
    the session has no associated capture (uploads, fastf1 sessions,
    or a torcs_live session whose file was deleted post-ingest).

    NOTE: For Phase 3 v1.0, the live-stream endpoint expects callers to
    have a telemetry file that is *still being written to*. The session
    is created by the torcs-live POST after the capture exists; the live
    stream is for the next race (Phase 2 control daemon will close that
    loop). v1.0 reality: judges who want live streaming run
    ``torcs_jm_par.py`` with ``OVERRIDE_LOG_TELEMETRY=/path/to/dir/`` set
    and pass the resolved run_id, opening the SSE stream BEFORE the
    capture ends. Documented in the API doc.
    """
    summary_path = _sessions_root_for_request() / session_id / "summary.json"
    if not summary_path.is_file():
        return None
    try:
        data = json.loads(summary_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    fname = data.get("telemetry_file")
    if not fname:
        return None
    candidate = _telemetry_dir() / fname
    return candidate if candidate.is_file() else None


def _read_jsonl_safe(path: Path, *, max_lines: Optional[int] = None) -> list[dict]:
    """Read a JSONL file with the gotcha #12 safe-read pattern.

    Skips incomplete tail lines (no trailing ``\\n``) and json.JSONDecodeError
    on individual lines without raising. Returns the list of valid
    observations. ``max_lines`` caps the read for cheap progress polling.
    """
    out: list[dict] = []
    try:
        with path.open("r") as f:
            for line in f:
                if not line.endswith("\n"):
                    break  # incomplete tail; the writer is still going
                try:
                    obs = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if isinstance(obs, dict):
                    out.append(obs)
                if max_lines is not None and len(out) >= max_lines:
                    break
    except OSError:
        return out
    return out


def _first_segment_is_partial(observations: list[dict]) -> bool:
    """True if the JSONL starts mid-lap.

    Phase 2 reality: when the operator clicks "Start race" AFTER having
    launched TORCS manually in noVNC and started the race there, the SCR
    client (torcs_jm_par.py) connects 30-60+ s into lap 1. Its first
    observation has ``distFromStart`` already deep into the lap (e.g.
    2700m on a 3km track). Without compensation, the segment from connect
    to first wraparound shows up as a "partial L1" with only ~8s of data
    — confusing in the live-telemetry table. This helper lets the lap
    counter and the aggregator skip that partial.

    Threshold: 100m past the start-line. Picks up "joined mid-lap" while
    tolerating ~3s of pre-race jitter where the car is still on the grid.
    """
    for obs in observations:
        d = obs.get("distFromStart")
        if isinstance(d, list) and d:
            d = d[0]
        if isinstance(d, (int, float)):
            return float(d) > 100.0
    return False


def _get_current_lap(observations: list[dict]) -> int:
    """Count COMPLETE laps captured in the stream.

    A start-line crossing is when ``distFromStart`` jumps backward by
    a large margin (end of lap N → start of lap N+1). Returns the number
    of laps we have FULL data for: if the JSONL started mid-lap (partial
    first segment), we subtract 1 from the wraparound count so the first
    wraparound — which only completed the partial — doesn't inflate the
    displayed lap number.
    """
    wraparounds = 0
    prev_dist: Optional[float] = None
    for obs in observations:
        raw = obs.get("distFromStart")
        if isinstance(raw, list) and raw:
            raw = raw[0]
        if not isinstance(raw, (int, float)):
            continue
        if prev_dist is not None and raw < prev_dist * 0.5 and prev_dist > 100.0:
            # Wraparound = lap completed
            wraparounds += 1
        prev_dist = float(raw)
    if _first_segment_is_partial(observations):
        return max(0, wraparounds - 1)
    return wraparounds


def _aggregate_lap(observations: list[dict], lap_index: int) -> Optional[LiveLapStats]:
    """Compute ``LiveLapStats`` for the lap_index-th completed lap (1-indexed).

    Uses ``analysis.torcs_energy.derive_lap_energy`` for energy math so
    the live emit and the final ``LapFeatures`` agree. Returns None
    when the observations span doesn't contain a complete lap_index'th
    lap (caller skips and waits for the next poll).
    """
    from analysis.torcs_energy import (
        BATTERY_CAPACITY_MJ,
        DEPLOY_KJ_PER_FULL_THROTTLE_SECOND,
        HARVEST_KJ_PER_BRAKE_SECOND,
        SOC_INITIAL,
        THROTTLE_DEPLOY_THRESHOLD,
    )

    # Segment observations into laps by start-line crossings.
    laps: list[list[dict]] = [[]]
    prev_dist: Optional[float] = None
    for obs in observations:
        raw = obs.get("distFromStart")
        if isinstance(raw, list) and raw:
            raw = raw[0]
        if not isinstance(raw, (int, float)):
            continue
        dist = float(raw)
        if prev_dist is not None and dist < prev_dist * 0.5 and prev_dist > 100.0:
            laps.append([])
        laps[-1].append(obs)
        prev_dist = dist

    # Skip the partial first segment if we joined mid-lap (Phase 2 fix).
    # Without this, "L1" in the live table would show ~8s of an incomplete
    # lap when the operator clicked Start race after the race was already
    # underway in TORCS GUI.
    partial = _first_segment_is_partial(observations)
    if partial and laps:
        laps = laps[1:]

    if lap_index < 1 or lap_index > len(laps):
        return None
    lap = laps[lap_index - 1]
    if len(lap) < 2:
        return None

    def _scalar(o: dict, k: str) -> Optional[float]:
        v = o.get(k)
        if isinstance(v, list) and v:
            v = v[0]
        return float(v) if isinstance(v, (int, float)) else None

    # Lap time from curLapTime
    first_t = _scalar(lap[0], "curLapTime") or 0.0
    last_t = _scalar(lap[-1], "curLapTime") or 0.0
    lap_time_s = max(0.0, last_t - first_t)

    # Speed stats (TORCS speedX is m/s → km/h)
    speeds_kmh = [
        v * 3.6 for v in (_scalar(o, "speedX") for o in lap) if v is not None
    ]
    avg_speed = sum(speeds_kmh) / len(speeds_kmh) if speeds_kmh else 0.0
    max_speed = max(speeds_kmh) if speeds_kmh else 0.0

    # Brake / throttle integration → harvest / deploy. Single-sector
    # approximation here (live stream doesn't need per-sector breakdown);
    # post-hoc parser does the per-sector split via ingest/torcs_parser.py.
    # dt between consecutive ticks.
    brake_s = 0.0
    throttle_s = 0.0
    fuel_first: Optional[float] = None
    fuel_last: Optional[float] = None
    for i, obs in enumerate(lap):
        prev_t = _scalar(lap[i - 1], "curLapTime") if i > 0 else None
        cur_t = _scalar(obs, "curLapTime")
        dt = (cur_t - prev_t) if (prev_t is not None and cur_t is not None and cur_t > prev_t) else 0.02
        brake = _scalar(obs, "brake") or 0.0
        accel = _scalar(obs, "accel") or 0.0
        if brake > 0.05:
            brake_s += dt
        # accel is 0-1; threshold is 95% (THROTTLE_DEPLOY_THRESHOLD is on 0-100 scale)
        if accel * 100.0 >= THROTTLE_DEPLOY_THRESHOLD:
            throttle_s += dt
        fuel = _scalar(obs, "fuel")
        if fuel is not None:
            if fuel_first is None:
                fuel_first = fuel
            fuel_last = fuel

    harvest_mj = (HARVEST_KJ_PER_BRAKE_SECOND * brake_s) / 1000.0
    deploy_mj = (DEPLOY_KJ_PER_FULL_THROTTLE_SECOND * throttle_s) / 1000.0
    # Walk SoC across all prior laps + this one to get the right end value.
    soc = SOC_INITIAL
    for li in range(lap_index):
        prev_lap = laps[li]
        b_s = 0.0
        t_s = 0.0
        for j, obs in enumerate(prev_lap):
            prev_t = _scalar(prev_lap[j - 1], "curLapTime") if j > 0 else None
            cur_t = _scalar(obs, "curLapTime")
            dt = (cur_t - prev_t) if (prev_t is not None and cur_t is not None and cur_t > prev_t) else 0.02
            br = _scalar(obs, "brake") or 0.0
            ac = _scalar(obs, "accel") or 0.0
            if br > 0.05:
                b_s += dt
            if ac * 100.0 >= THROTTLE_DEPLOY_THRESHOLD:
                t_s += dt
        h = (HARVEST_KJ_PER_BRAKE_SECOND * b_s) / 1000.0
        d = (DEPLOY_KJ_PER_FULL_THROTTLE_SECOND * t_s) / 1000.0
        soc = max(0.0, min(1.0, soc + (h - d) / BATTERY_CAPACITY_MJ))

    fuel_used: Optional[float] = None
    if fuel_first is not None and fuel_last is not None and fuel_last <= fuel_first:
        fuel_used = round(fuel_first - fuel_last, 4)

    return LiveLapStats(
        lap=lap_index,
        lap_time_s=round(lap_time_s, 3),
        avg_speed_kmh=round(avg_speed, 2),
        max_speed_kmh=round(max_speed, 2),
        harvest_mj=round(harvest_mj, 4),
        deploy_mj=round(deploy_mj, 4),
        soc_end=round(soc, 6),
        fuel_used_kg=fuel_used,
    )


def _extract_start_time(jsonl_path: Path) -> Optional[datetime]:
    """Pull the wall-clock start of a TORCS capture from its first observation.

    The Phase 1 logger injects ``t = time.time()`` into every observation
    (see RaceYourCode/gym_torcs/torcs_jm_par.py). The first observation's
    ``t`` is the most accurate start time we have. Falls back to None on
    any failure — caller is expected to substitute file mtime.

    Honors gotcha #12's JSONL safe-read: tolerates leading-line malformed
    JSON without raising. Reads at most ~4 KB to find a valid first
    observation.
    """
    try:
        with jsonl_path.open("rb") as fh:
            head = fh.read(4096)
    except OSError:
        return None
    for line in head.splitlines():
        try:
            obs = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        t = obs.get("t") if isinstance(obs, dict) else None
        if isinstance(t, (int, float)) and t > 0:
            try:
                return datetime.fromtimestamp(t, tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                return None
    return None


def _telemetry_dir() -> Path:
    """Where the live-ingest path reads JSONL from.

    In compose (Mode 2 — `podman compose --profile torcs up`), the
    ``torcs-telemetry`` named volume mounts at /app/data/telemetry in
    the override service and at /home/student/workspace/gym_torcs/telemetry
    in the torcs service — gym_torcs writes, override reads. In local
    dev (no compose), defaults to ./data/telemetry which the developer
    populates manually.

    Honors ``OVERRIDE_TELEMETRY_DIR`` env override for the v6 §3.2 test
    pattern (tests mount a tmp_path and set the env var without
    relying on container paths).
    """
    raw = os.environ.get("OVERRIDE_TELEMETRY_DIR")
    if raw:
        return Path(raw)
    # Inside the container image, /app/data/telemetry is the compose mount
    # point. Outside the container (local dev / tests with no env var
    # override), fall back to a sibling of data/sessions.
    container_default = Path("/app/data/telemetry")
    if container_default.is_dir():
        return container_default
    return Path(__file__).resolve().parent.parent / "data" / "telemetry"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _extract_region(url: str) -> str:
    """Pull the region slug out of a watsonx URL.

    `https://us-south.ml.cloud.ibm.com` → `us-south`
    """
    if not url:
        return "unknown"
    try:
        host = url.split("//", 1)[1]
        return host.split(".", 1)[0]
    except (IndexError, ValueError):
        return "unknown"


def _parse_upload(body: bytes, *, source: str, filename: str) -> list[LapFeatures]:
    """Parse uploaded bytes into LapFeatures.

    TORCS path (post-v6 1.3): dispatch is content-sniffing, not filename-only.
    If the first parseable line of the body is a gym_torcs-shaped tick (has
    ``curLapTime`` / ``distFromStart`` / ``speedX`` keys), route to
    ``ingest.torcs_parser.parse_torcs_session``. Otherwise treat as the
    canonical ``LapFeatures``-list shape. Suffix-only dispatch was fragile —
    review caught that a fixture committed as ``data/samples/torcs_*.json``
    (no `l` in the suffix) would fall through to canonical-schema passthrough
    and crash on the wrong shape. Sniffing lets either filename work; the
    `.jsonl` extension hint is preserved as a fast-path for the live-ingest
    endpoint.

    FastF1 path: accepts a parquet cache file or the canonical JSON.
    """
    import json

    if source == "torcs":
        if _is_torcs_jsonl(body, filename=filename):
            import tempfile

            with tempfile.NamedTemporaryFile(
                suffix=".jsonl", delete=False
            ) as fh:
                fh.write(body)
                tmp_path = fh.name
            try:
                return parse_torcs_session(tmp_path)
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        # Already-parsed canonical shape (passthrough).
        return _parse_lap_features_json(body)
    if source == "fastf1":
        # Accept either a parquet file (cached FastF1 lap features) or
        # the canonical lap-features JSON.
        if filename.endswith(".parquet"):
            import io

            df = pd.read_parquet(io.BytesIO(body))
            return [LapFeatures.model_validate(row) for row in df.to_dict(orient="records")]
        return _parse_lap_features_json(body)
    raise ValueError(f"unknown source: {source!r}")


# Sentinel gym_torcs keys — a tick has these even when other sensors are absent.
# Used by _is_torcs_jsonl to distinguish per-tick replays from canonical shape.
_TORCS_TICK_SIGNATURE_KEYS = ("curLapTime", "distFromStart", "speedX")


def _is_torcs_jsonl(body: bytes, *, filename: str) -> bool:
    """Decide whether the upload is a raw TORCS JSONL replay vs a canonical
    ``{"laps": [...]}`` payload. Filename hint is a fast-path; content
    sniffing is the source of truth.
    """
    import json as _json

    # Fast-path: explicit .jsonl suffix → trust the user.
    if filename.endswith(".jsonl"):
        return True
    # Content sniff: peek the first non-empty line.
    head = body[:8192]
    try:
        first_line = head.decode("utf-8", errors="replace").splitlines()
    except Exception:
        return False
    for line in first_line:
        line = line.strip()
        if not line:
            continue
        try:
            obj = _json.loads(line)
        except _json.JSONDecodeError:
            return False
        if isinstance(obj, dict) and any(k in obj for k in _TORCS_TICK_SIGNATURE_KEYS):
            return True
        # First parseable JSON wasn't a tick → it's the canonical wrapper
        # (a {"laps": [...]} dict or a [...] list).
        return False
    return False


def _parse_lap_features_json(body: bytes) -> list[LapFeatures]:
    import json

    text = body.decode("utf-8")
    payload = json.loads(text)
    # Accept either a bare list of lap dicts or a {"laps": [...]} wrapper
    if isinstance(payload, dict) and "laps" in payload:
        rows = payload["laps"]
    elif isinstance(payload, list):
        rows = payload
    else:
        raise ValueError("expected JSON list or {'laps': [...]} wrapper")
    return [LapFeatures.model_validate(r) for r in rows]


# Default app instance (used by uvicorn)
app = create_app()


__all__ = ["create_app", "app"]
