"""FastAPI runtime — Tier 1 endpoints per `docs/04-api.md`.

Implemented (Tier 1):
  GET  /api/health                                    liveness
  GET  /api/version                                   build + model IDs
  POST /api/sessions                                  upload + run pipeline
  GET  /api/sessions/{id}                             full debrief
  GET  /api/sessions/{id}/zones/{zid}?mode=...        per-zone (lazy fan)
  GET  /api/regulation-source                         G-4 metadata
  DELETE /api/sessions/{id}                           local cleanup

Tier 2 endpoints (`/api/sessions` list, `/laps`, `/zones` list) are
deferred to a follow-up PR per the P2.7 review.

Auth: none (single-user, replay-first per §1 + §10). CORS allows
`OVERRIDE_UI_ORIGIN` only.
"""

from __future__ import annotations

import asyncio
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
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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
    WhatIfRequest,
    WhatIfResult,
)

from .errors import api_error, map_watsonx_exception, new_request_id
from .observability import setup_tracing
from .storage import (
    delete_session,
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
