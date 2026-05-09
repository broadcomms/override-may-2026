"""ApiError schema + watsonx-error → HTTP-status mapping.

Per `docs/04-api.md` §3 + §12. Every error returned by FastAPI uses
`ApiError` with one of the documented `error_code` values. Status codes
mapped per §3 table.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Literal, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


ErrorCode = Literal[
    "INVALID_FILE_FORMAT",
    "FILE_TOO_LARGE",
    "PARSE_FAILED",
    "FORECAST_UNAVAILABLE",
    "MODEL_UNAVAILABLE",
    "RATE_LIMITED",
    "NOT_FOUND",
    "INTERNAL_ERROR",
]


class ApiError(BaseModel):
    """Per `docs/04-schema.md §12`. Every endpoint returns this on failure."""

    error_code: ErrorCode
    message: str = Field(min_length=1, description="human-readable, safe to display in UI")
    detail: Optional[str] = Field(
        default=None, description="diagnostic; never PII; never stack traces in prod"
    )
    request_id: str = Field(min_length=1, description="for log correlation")


def new_request_id() -> str:
    """Short request ID: `req_<8 hex>`."""
    return f"req_{uuid.uuid4().hex[:8]}"


def api_error(
    *,
    status_code: int,
    error_code: ErrorCode,
    message: str,
    detail: Optional[str] = None,
    request_id: Optional[str] = None,
) -> HTTPException:
    """Construct an HTTPException whose detail is an `ApiError` payload.

    FastAPI's exception handler (registered in `api.main`) renders this
    as JSON with the right status code + the ApiError body shape.
    """
    rid = request_id or new_request_id()
    payload = ApiError(
        error_code=error_code,
        message=message,
        detail=detail,
        request_id=rid,
    )
    return HTTPException(status_code=status_code, detail=payload.model_dump(mode="json"))


# ──────────────────────────────────────────────────────────────────────────────
# Watsonx → HTTP error mapping
# ──────────────────────────────────────────────────────────────────────────────


_QUOTA_RE = re.compile(r"quota|token.?quota|rate.?limit", re.IGNORECASE)
_AUTH_RE = re.compile(r"unauthor|forbidden|invalid.?api.?key|401|403", re.IGNORECASE)


def map_watsonx_exception(exc: Exception, *, request_id: Optional[str] = None) -> HTTPException:
    """Translate any exception raised inside the pipeline (watsonx
    SDK errors, parse errors, etc.) into a clean HTTP error.

    Per `docs/04-api.md §3 + §4.3`:
      - watsonx 429 (rate limit) → 503 MODEL_UNAVAILABLE
      - watsonx 401/403 (auth)   → 503 MODEL_UNAVAILABLE
      - quota exhausted          → 503 MODEL_UNAVAILABLE with detail
      - any other watsonx error  → 503 MODEL_UNAVAILABLE
      - reasoning/Guardian parse → 500 INTERNAL_ERROR (model misbehaved)
      - everything else          → 500 INTERNAL_ERROR
    """
    rid = request_id or new_request_id()
    msg = str(exc)
    text = f"{type(exc).__name__}: {msg}"
    logger.exception("pipeline error (request_id=%s): %s", rid, text)

    # Late-import to avoid a hard dependency at module load
    try:
        from ibm_watsonx_ai.wml_client_error import (  # type: ignore[import-not-found]
            ApiRequestFailure,
        )
    except Exception:  # pragma: no cover
        ApiRequestFailure = ()  # type: ignore[assignment, misc]

    if isinstance(exc, ApiRequestFailure):  # type: ignore[arg-type]
        body = msg
        if _QUOTA_RE.search(body):
            return api_error(
                status_code=503,
                error_code="MODEL_UNAVAILABLE",
                message="Reasoning service unreachable: watsonx token quota exhausted.",
                detail="Try again after the quota window resets, or check the watsonx tier.",
                request_id=rid,
            )
        if _AUTH_RE.search(body):
            return api_error(
                status_code=503,
                error_code="MODEL_UNAVAILABLE",
                message="Reasoning service unreachable: watsonx authentication failed.",
                detail="Check WATSONX_API_KEY and WATSONX_PROJECT_ID in .env.",
                request_id=rid,
            )
        return api_error(
            status_code=503,
            error_code="MODEL_UNAVAILABLE",
            message="Reasoning service unreachable: watsonx returned an error.",
            detail=msg[:200] if msg else None,
            request_id=rid,
        )

    # Reasoning/Guardian/FanMode parse errors
    name = type(exc).__name__
    if name in {"ReasoningParseError", "GuardianParseError", "FanModeParseError"}:
        return api_error(
            status_code=500,
            error_code="INTERNAL_ERROR",
            message="Model returned malformed output; the recommendation could not be assembled.",
            detail=name,
            request_id=rid,
        )

    return api_error(
        status_code=500,
        error_code="INTERNAL_ERROR",
        message="An unexpected error occurred.",
        detail=name,
        request_id=rid,
    )


__all__ = [
    "ApiError",
    "ErrorCode",
    "api_error",
    "map_watsonx_exception",
    "new_request_id",
]
