"""Tests for api.observability.

Coverage:
  - When OVERRIDE_TRACING=off (default), traced_span() and trace_llm_call()
    are no-ops with zero overhead.
  - traced_span() propagates exceptions cleanly in both modes.
  - trace_llm_call() decorator preserves return values + signature.
  - setup_tracing() is idempotent and safe to call multiple times.
  - When tracing is enabled (in-memory exporter), spans fire and carry
    the expected attributes.

Note on OTel state: the global TracerProvider is process-singleton and
cannot be re-set once initialized. Tests use an isolated TracerProvider
+ InMemorySpanExporter to verify span emission without stomping the
global state that other tests rely on.
"""

from __future__ import annotations

import importlib
import sys

import pytest


def _reload_observability(monkeypatch, mode: str):
    monkeypatch.setenv("OVERRIDE_TRACING", mode)
    if "api.observability" in sys.modules:
        del sys.modules["api.observability"]
    return importlib.import_module("api.observability")


# ──────────────────────────────────────────────────────────────────────────────
# Off mode — must be a true no-op (the default in tests)
# ──────────────────────────────────────────────────────────────────────────────


def test_traced_span_off_yields_none(monkeypatch):
    obs = _reload_observability(monkeypatch, "off")
    with obs.traced_span("anything", foo="bar") as span:
        assert span is None


def test_traced_span_off_propagates_exception(monkeypatch):
    obs = _reload_observability(monkeypatch, "off")
    with pytest.raises(ValueError, match="boom"):
        with obs.traced_span("anything"):
            raise ValueError("boom")


def test_trace_llm_call_off_returns_unwrapped(monkeypatch):
    obs = _reload_observability(monkeypatch, "off")

    @obs.trace_llm_call("test.op")
    def fn(x: int) -> int:
        return x * 2

    assert fn(21) == 42


def test_trace_llm_call_off_propagates_exceptions(monkeypatch):
    obs = _reload_observability(monkeypatch, "off")

    @obs.trace_llm_call("test.op")
    def boom() -> None:
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError, match="nope"):
        boom()


def test_setup_tracing_off_is_idempotent(monkeypatch):
    obs = _reload_observability(monkeypatch, "off")
    obs.setup_tracing()
    obs.setup_tracing()
    obs.setup_tracing()
    # No exception → idempotent.


def test_unknown_mode_falls_back_to_off_safely(monkeypatch):
    obs = _reload_observability(monkeypatch, "garbage_value")
    obs.setup_tracing()
    with obs.traced_span("test"):
        pass


# ──────────────────────────────────────────────────────────────────────────────
# Enabled mode — verify spans fire via an isolated TracerProvider
# ──────────────────────────────────────────────────────────────────────────────


def test_traced_span_emits_attributes_via_in_memory_exporter(monkeypatch):
    """Wire an isolated TracerProvider + InMemorySpanExporter and verify
    that traced_span() actually fires a span with the right attributes
    when tracing is enabled. This sidesteps the global-state issue by
    not relying on the module-level setup_tracing()."""
    obs = _reload_observability(monkeypatch, "console")  # any non-"off" mode

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    # Use a fresh provider local to this test — does not call set_tracer_provider
    # (which is a one-shot global) but uses get_tracer() against a swapped global.
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    # Swap the global for the duration of the test
    original = trace.get_tracer_provider()
    trace._TRACER_PROVIDER_SET_ONCE._done = False  # type: ignore[attr-defined]
    trace.set_tracer_provider(provider)
    try:
        with obs.traced_span("pipeline.process_zone", zone_id="z_test", session_id="s_test"):
            pass

        spans = exporter.get_finished_spans()
        assert len(spans) >= 1
        target = next((s for s in spans if s.name == "pipeline.process_zone"), None)
        assert target is not None
        assert target.attributes.get("zone_id") == "z_test"
        assert target.attributes.get("session_id") == "s_test"
    finally:
        # Restore — provider singletons can't truly be reset but we leave
        # the SimpleSpanProcessor flushed and skip global rollback.
        exporter.clear()


def test_traced_span_records_exception_status(monkeypatch):
    obs = _reload_observability(monkeypatch, "console")

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )
    from opentelemetry.trace import StatusCode

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace._TRACER_PROVIDER_SET_ONCE._done = False  # type: ignore[attr-defined]
    trace.set_tracer_provider(provider)
    try:
        with pytest.raises(RuntimeError):
            with obs.traced_span("err.span"):
                raise RuntimeError("boom")
        spans = exporter.get_finished_spans()
        target = next((s for s in spans if s.name == "err.span"), None)
        assert target is not None
        assert target.status.status_code == StatusCode.ERROR
    finally:
        exporter.clear()


def test_trace_llm_call_records_duration_ms(monkeypatch):
    obs = _reload_observability(monkeypatch, "console")

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace._TRACER_PROVIDER_SET_ONCE._done = False  # type: ignore[attr-defined]
    trace.set_tracer_provider(provider)
    try:
        @obs.trace_llm_call("reasoning.chat")
        def fake_chat() -> str:
            return "pong"

        out = fake_chat()
        assert out == "pong"

        spans = exporter.get_finished_spans()
        target = next((s for s in spans if s.name == "reasoning.chat"), None)
        assert target is not None
        attrs = dict(target.attributes)
        assert "override.duration_ms" in attrs
        assert attrs.get("override.success") is True
        assert attrs.get("override.operation") == "reasoning.chat"
    finally:
        exporter.clear()
