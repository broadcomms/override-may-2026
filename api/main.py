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
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.fan_mode import FanModeParseError, translate_to_fan_mode
from core.guardian import WatsonxAIGuardianClient, WatsonxGuardianClient
from core.pipeline import run_pipeline
from core.reasoning import WatsonxAIChatClient, WatsonxChatClient
from core.regs import (
    DEFAULT_CHUNKS_PATH,
    WatsonxAIEmbeddingClient,
    WatsonxEmbeddingClient,
    load_chunks,
)
from ingest.fastf1_parser import parse_fastf1_session  # noqa: F401  — surfaced for future use
from ingest.schema import (
    LapFeatures,
    Recommendation,
    RegulationSource,
    Session,
)

from .errors import api_error, map_watsonx_exception, new_request_id
from .observability import setup_tracing
from .storage import delete_session, load_session, save_session

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


# ──────────────────────────────────────────────────────────────────────────────
# Dependency providers (override-able for tests)
# ──────────────────────────────────────────────────────────────────────────────


def get_chat_client() -> WatsonxChatClient:
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
        source: Annotated[Literal["torx", "fastf1"], Form()] = "torx",
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

            # Persist the cache (write back to disk)
            updated_rec = rec.model_copy(update={"fan": fan})
            updated_recs = [updated_rec if r.zone.zone_id == zone_id else r for r in session.recommendations]
            updated_session = session.model_copy(update={"recommendations": updated_recs})
            save_session(updated_session)
            rec = updated_rec

        # Engineer-only mode → strip the fan field for a clean response
        if mode == "engineer":
            rec = rec.model_copy(update={"fan": None})

        return rec.model_dump(mode="json")

    @app.delete("/api/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def remove_session(
        session_id: str = PathParam(..., pattern=r"^s_[A-Za-z0-9_]+$"),
    ):
        delete_session(session_id)
        # Always 204 (idempotent)

    return app


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

    For Tier-1 we accept TWO concrete shapes — the canonical schema's
    `laps` field as JSON. The Torx parser and the live FastF1 path both
    produce this shape; an upload is treated as already-parsed lap rows
    in JSON form. Real Torx-JSON ingestion plugs in once `ingest/torx_parser.py`
    is implemented (post-G-2).
    """
    import json

    if source == "torx":
        # Expect Torx-shaped JSON. Until torx_parser.py is implemented,
        # accept the canonical schema shape directly.
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
