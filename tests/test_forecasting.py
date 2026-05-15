"""Tests for core/forecasting.py.

All tests mock tsfm_public and torch so they run in the standard dev
environment where granite-tsfm cannot be installed alongside our pinned
torch==2.11.0 / transformers==5.x stack.

Coverage targets (FR-3 graceful-degradation guardrail):
  - below TTM_MIN_LAPS threshold → None (no crash)
  - at/above threshold + functional model → Forecast returned
  - ImportError on tsfm_public → None (graceful)
  - RuntimeError during inference → None (graceful)
  - prediction interval too wide → None (quality gate)
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Optional
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from ingest.schema import Forecast, LapFeatures


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _make_laps(n: int) -> list[LapFeatures]:
    laps = []
    soc = 1.0
    for i in range(n):
        harvest = 3.70
        deploy = 3.76
        soc_end = round(max(0.10, soc + (harvest - deploy) / 4.0), 4)
        laps.append(
            LapFeatures(
                lap_number=i + 1,
                soc_start=soc,
                soc_end=soc_end,
                harvest_mj=harvest,
                deploy_mj=deploy,
                lap_time=110.0,
                sector1_time=31.9,
                sector2_time=29.7,
                sector3_time=48.4,
                avg_speed=83.0,
                max_speed=102.5,
                override_uses=0,
                boost_uses=0,
                recharge_zones=[2],
                soc_source="derived",
            )
        )
        soc = soc_end
    return laps


def _mock_tsfm_module(point_preds: np.ndarray) -> ModuleType:
    """Build a minimal tsfm_public stub returning ``point_preds`` [horizon, C]."""
    output = MagicMock()
    output.prediction_outputs = [MagicMock()]
    output.prediction_outputs[0].cpu.return_value.numpy.return_value = point_preds
    output.prediction_interval = None

    model = MagicMock()
    model.eval.return_value = None
    model.return_value = output

    tsfm_models = MagicMock()
    tsfm_models.TinyTimeMixerForPrediction.from_pretrained.return_value = model

    tsfm_pub = ModuleType("tsfm_public")
    tsfm_pub.models = MagicMock()
    tsfm_pub.models.tinytimemixer = tsfm_models  # type: ignore[attr-defined]

    sys.modules["tsfm_public"] = tsfm_pub
    sys.modules["tsfm_public.models"] = tsfm_pub.models
    sys.modules["tsfm_public.models.tinytimemixer"] = tsfm_models
    return tsfm_pub


def _clear_tsfm_module():
    for key in list(sys.modules.keys()):
        if key.startswith("tsfm_public"):
            del sys.modules[key]


# ──────────────────────────────────────────────────────────────────────────────
# Test: below threshold
# ──────────────────────────────────────────────────────────────────────────────


def test_below_min_laps_returns_none(monkeypatch):
    """Fewer laps than TTM_MIN_LAPS should return None immediately."""
    monkeypatch.setenv("TTM_MIN_LAPS", "30")
    import importlib
    import core.forecasting as fc
    importlib.reload(fc)

    laps = _make_laps(10)
    result = fc.forecast_lap_window(laps)
    assert result is None


# ──────────────────────────────────────────────────────────────────────────────
# Test: import error → graceful None
# ──────────────────────────────────────────────────────────────────────────────


def test_import_error_returns_none(monkeypatch):
    """When tsfm_public is not importable, forecast returns None."""
    _clear_tsfm_module()

    # Reload to clear singleton cache
    import importlib
    import core.forecasting as fc
    importlib.reload(fc)

    monkeypatch.setenv("TTM_MIN_LAPS", "5")

    laps = _make_laps(10)
    # tsfm_public not in sys.modules → ImportError inside _load_model
    result = fc.forecast_lap_window(laps)
    assert result is None

    _clear_tsfm_module()


# ──────────────────────────────────────────────────────────────────────────────
# Test: runtime error → graceful None
# ──────────────────────────────────────────────────────────────────────────────


def test_runtime_error_during_inference_returns_none(monkeypatch):
    """RuntimeError during model inference should return None, not raise."""
    import importlib
    import core.forecasting as fc
    importlib.reload(fc)

    monkeypatch.setenv("TTM_MIN_LAPS", "5")

    # Stub tsfm_public but make inference raise
    output = MagicMock()
    output.prediction_outputs = [MagicMock()]
    output.prediction_outputs[0].cpu.side_effect = RuntimeError("CUDA OOM")

    model = MagicMock()
    model.eval.return_value = None
    model.return_value = output

    tsfm_models = MagicMock()
    tsfm_models.TinyTimeMixerForPrediction.from_pretrained.return_value = model

    tsfm_pub = ModuleType("tsfm_public")
    tsfm_pub.models = MagicMock()
    tsfm_pub.models.tinytimemixer = tsfm_models  # type: ignore[attr-defined]

    sys.modules["tsfm_public"] = tsfm_pub
    sys.modules["tsfm_public.models"] = tsfm_pub.models
    sys.modules["tsfm_public.models.tinytimemixer"] = tsfm_models

    laps = _make_laps(10)
    result = fc.forecast_lap_window(laps)
    assert result is None

    _clear_tsfm_module()
    importlib.reload(fc)


# ──────────────────────────────────────────────────────────────────────────────
# Test: interval too wide → None
# ──────────────────────────────────────────────────────────────────────────────


def test_interval_too_wide_returns_none(monkeypatch):
    """When prediction interval width exceeds TTM_MAX_INTERVAL_WIDTH, return None."""
    import importlib

    _clear_tsfm_module()
    import core.forecasting as fc
    importlib.reload(fc)

    monkeypatch.setenv("TTM_MIN_LAPS", "5")
    monkeypatch.setenv("TTM_MAX_INTERVAL_WIDTH", "0.10")

    # SoC channel 0: normalized preds around 0.5
    preds = np.full((5, 5), 0.5, dtype=np.float32)
    _mock_tsfm_module(preds)
    importlib.reload(fc)  # reload after injecting stub

    laps = _make_laps(10)
    # Sigma will be computed from observed SoC variation; actual width depends
    # on data. Override max_interval_width to 0.0 to force rejection.
    monkeypatch.setenv("TTM_MAX_INTERVAL_WIDTH", "0.0")
    importlib.reload(fc)

    result = fc.forecast_lap_window(laps)
    assert result is None

    _clear_tsfm_module()
    importlib.reload(fc)


# ──────────────────────────────────────────────────────────────────────────────
# Test: successful forecast
# ──────────────────────────────────────────────────────────────────────────────


def test_successful_forecast_returns_forecast(monkeypatch):
    """Enough laps + working model → valid Forecast returned."""
    import importlib

    _clear_tsfm_module()

    monkeypatch.setenv("TTM_MIN_LAPS", "5")
    monkeypatch.setenv("TTM_MAX_INTERVAL_WIDTH", "0.20")

    # Normalized preds: 5-step horizon, 5 channels
    preds = np.full((5, 5), 0.5, dtype=np.float32)
    _mock_tsfm_module(preds)

    # Also mock torch.no_grad + torch.tensor to avoid CUDA load errors
    torch_mock = MagicMock()
    torch_mock.no_grad.return_value.__enter__ = MagicMock(return_value=None)
    torch_mock.no_grad.return_value.__exit__ = MagicMock(return_value=False)
    tensor_mock = MagicMock()
    tensor_mock.unsqueeze.return_value = tensor_mock
    torch_mock.tensor.return_value = tensor_mock
    torch_mock.float32 = "float32"
    sys.modules["torch"] = torch_mock

    import core.forecasting as fc
    importlib.reload(fc)

    laps = _make_laps(35)
    result = fc.forecast_lap_window(laps)

    assert result is not None
    assert isinstance(result, Forecast)
    assert len(result.point) == 5
    assert len(result.lower) == 5
    assert len(result.upper) == 5
    assert all(0.0 <= p <= 1.0 for p in result.point)
    assert all(l <= p <= u for l, p, u in zip(result.lower, result.point, result.upper))
    assert "granite-timeseries-ttm-r2" in result.model_version

    _clear_tsfm_module()
    del sys.modules["torch"]
    importlib.reload(fc)


# ──────────────────────────────────────────────────────────────────────────────
# Test: _build_input shape
# ──────────────────────────────────────────────────────────────────────────────


def test_build_input_shape():
    """_build_input returns normalized array with correct shape."""
    import importlib
    import core.forecasting as fc
    importlib.reload(fc)

    laps = _make_laps(30)
    norm, mins, scales = fc._build_input(laps)

    assert norm.shape == (30, 5), f"Expected (30,5) got {norm.shape}"
    assert norm.min() >= 0.0 - 1e-6
    assert norm.max() <= 1.0 + 1e-6
    assert mins.shape == (5,)
    assert scales.shape == (5,)


# ──────────────────────────────────────────────────────────────────────────────
# Test: fixture validates against Forecast schema
# ──────────────────────────────────────────────────────────────────────────────


def test_forecast_demo_fixture_validates():
    """The forecast_demo.json fixture must validate against the Forecast schema."""
    import json
    from pathlib import Path

    fixture_path = Path(__file__).parent / "fixtures" / "forecast_demo.json"
    assert fixture_path.exists(), "forecast_demo.json fixture missing"

    with open(fixture_path) as f:
        data = json.load(f)

    forecast_data = data["session"]["forecast"]
    assert forecast_data is not None, "forecast_demo fixture must have non-null forecast"

    forecast = Forecast.model_validate(forecast_data)
    assert len(forecast.point) == 5
    assert len(forecast.lower) == 5
    assert len(forecast.upper) == 5
    assert forecast.model_version.startswith("ibm-granite/granite-timeseries-ttm-r2")

    # All 35 laps should have proper LapFeatures structure
    laps_data = data["session"]["laps"]
    assert len(laps_data) == 35
    for lap_d in laps_data:
        LapFeatures.model_validate(lap_d)

    assert data["session"]["summary"]["forecast_available"] is True
