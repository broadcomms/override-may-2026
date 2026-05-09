"""OpenTelemetry tracing for the OVERRIDE production runtime.

Per `docs/04-api.md §8` and risk R6 (P3.6 ContextForge decision): we use
direct OpenTelemetry instrumentation rather than ContextForge for
velocity. The trace screenshot ships in the README per roadmap P3.5.

Architecture:
  - One TracerProvider per process; initialized lazily on first call to
    `setup_tracing()` from api.main on app startup.
  - OTLP gRPC exporter to a local Jaeger / OTel Collector (default
    `localhost:4317`). Configurable via the standard OTel env vars
    `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`.
  - Console exporter as fallback when `OVERRIDE_TRACING=console` — useful
    for offline debugging without standing up Jaeger.
  - When `OVERRIDE_TRACING=off` (default unless explicitly enabled), all
    span APIs become no-ops via NoOpTracerProvider — zero overhead.
  - FastAPI auto-instrumentation wraps every HTTP request with a span;
    manual spans inside core/{reasoning,guardian,regs,pipeline} carry the
    LLM-call detail for the `jaeger-trace.png` demo asset.

Helpers:
  - `traced_span(name, **attrs)` context manager — for ad-hoc spans.
  - `trace_llm_call(operation, model_id, **extra)` decorator — wraps a
    sync LLM call with consistent attributes (operation, model_id,
    duration_ms, success).
"""

from __future__ import annotations

import functools
import logging
import os
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Optional, TypeVar

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "override-api")

# Three modes:
#   "otlp"    — export via OTLP gRPC to OTEL_EXPORTER_OTLP_ENDPOINT (default
#               localhost:4317). Use this when running Jaeger.
#   "console" — print spans to stderr. Useful for local debugging.
#   "off"     — no-op tracer, zero overhead. Default unless flipped.
TRACING_MODE = os.environ.get("OVERRIDE_TRACING", "off").lower()

_initialized = False


# ──────────────────────────────────────────────────────────────────────────────
# Setup
# ──────────────────────────────────────────────────────────────────────────────


def setup_tracing(app: Any | None = None) -> None:
    """Initialize the global OpenTelemetry TracerProvider once per process.

    Idempotent — safe to call multiple times. When `app` is a FastAPI
    instance, also wires the FastAPI auto-instrumentor for HTTP-level
    spans (see `04-api.md §8`).

    No-op when `OVERRIDE_TRACING=off` (the default).
    """
    global _initialized
    if _initialized:
        if app is not None:
            _instrument_fastapi(app)
        return

    if TRACING_MODE == "off":
        logger.info("setup_tracing: OVERRIDE_TRACING=off — tracing disabled")
        _initialized = True
        return

    # Lazy imports — these aren't cheap.
    from opentelemetry import trace
    from opentelemetry.sdk.resources import SERVICE_NAME as RESOURCE_SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
        SimpleSpanProcessor,
    )

    resource = Resource.create({RESOURCE_SERVICE_NAME: SERVICE_NAME})
    provider = TracerProvider(resource=resource)

    if TRACING_MODE == "console":
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        logger.info("setup_tracing: console exporter active")
    elif TRACING_MODE == "otlp":
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        try:
            otlp = OTLPSpanExporter(endpoint=endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(otlp))
            logger.info("setup_tracing: OTLP exporter → %s", endpoint)
        except Exception as e:  # pragma: no cover
            logger.warning(
                "setup_tracing: OTLP exporter failed (%s) — falling back to console",
                e,
            )
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    else:
        logger.warning(
            "setup_tracing: unknown OVERRIDE_TRACING=%r — falling back to off",
            TRACING_MODE,
        )

    trace.set_tracer_provider(provider)
    _initialized = True

    if app is not None:
        _instrument_fastapi(app)


def _instrument_fastapi(app: Any) -> None:
    """Wrap a FastAPI app with auto-instrumentation. Idempotent."""
    if TRACING_MODE == "off":
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        logger.info("setup_tracing: FastAPI auto-instrumentation active")
    except Exception as e:  # pragma: no cover
        logger.warning("setup_tracing: FastAPI instrumentation failed: %s", e)


# ──────────────────────────────────────────────────────────────────────────────
# Span helpers — safe to call when tracing is disabled (no-op)
# ──────────────────────────────────────────────────────────────────────────────


@contextmanager
def traced_span(name: str, **attributes: Any) -> Iterator[Any]:
    """Context manager that opens a span. No-op when tracing is off.

    Usage:
        with traced_span("reason", zone_id=zone.zone_id, model_id="ibm/granite-4-h-small"):
            raw = client.chat(...)
    """
    if TRACING_MODE == "off":
        yield None
        return
    from opentelemetry import trace

    tracer = trace.get_tracer(SERVICE_NAME)
    with tracer.start_as_current_span(name) as span:
        for k, v in attributes.items():
            if v is not None:
                _set_attr(span, k, v)
        try:
            yield span
        except Exception as exc:
            from opentelemetry.trace import Status, StatusCode

            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise


def _set_attr(span: Any, key: str, value: Any) -> None:
    """Coerce values into OTel-acceptable attribute types and set them."""
    if isinstance(value, (str, bool, int, float)):
        span.set_attribute(key, value)
    elif isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value):
        span.set_attribute(key, list(value))
    else:
        span.set_attribute(key, str(value))


F = TypeVar("F", bound=Callable[..., Any])


def trace_llm_call(operation: str, model_id_attr: str = "model_id") -> Callable[[F], F]:
    """Decorator that wraps a synchronous LLM call with a span.

    Records:
      - `override.operation` — e.g. "reasoning.chat", "guardian.score"
      - `override.model_id` — pulled from kwargs[model_id_attr] if present,
        else from the bound method's `client.model_id` if accessible
      - `override.duration_ms`
      - `override.success` — bool
    """
    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if TRACING_MODE == "off":
                return fn(*args, **kwargs)
            attrs = {"override.operation": operation}
            mid = kwargs.get(model_id_attr)
            if mid:
                attrs["override.model_id"] = mid
            with traced_span(operation, **attrs) as span:
                t0 = time.monotonic()
                try:
                    result = fn(*args, **kwargs)
                    if span is not None:
                        _set_attr(span, "override.duration_ms",
                                  round((time.monotonic() - t0) * 1000, 2))
                        _set_attr(span, "override.success", True)
                    return result
                except Exception:
                    if span is not None:
                        _set_attr(span, "override.duration_ms",
                                  round((time.monotonic() - t0) * 1000, 2))
                        _set_attr(span, "override.success", False)
                    raise
        return wrapper  # type: ignore[return-value]
    return decorator


__all__ = [
    "SERVICE_NAME",
    "TRACING_MODE",
    "setup_tracing",
    "traced_span",
    "trace_llm_call",
]
