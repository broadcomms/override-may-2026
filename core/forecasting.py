"""TTM-R2 time-series forecasting (FR-3, optional per graceful-degradation guardrail).

Local-only enhancement using IBM Granite TimeSeries TTM-R2.  Falls back
gracefully when ``tsfm_public`` is unavailable or the session doesn't qualify.

Eligibility gate
----------------
- ``len(laps) < max(TTM_MIN_LAPS, TTM_CONTEXT_LENGTH)`` → return None.

The conservative ``max(...)`` ensures neither gate can be bypassed individually:
``TTM_MIN_LAPS`` is the product quality floor; ``TTM_CONTEXT_LENGTH`` is the
model's required input size.  Lower both together to experiment.

TTM_CONTEXT_LENGTH (env, default 30)
--------------------------------------
Controls how many laps the model sees.  Also gates eligibility:
``len(laps) >= TTM_CONTEXT_LENGTH`` must hold so the model gets a full window.
Evaluation range: 30, 20, 15, 10, 5.  Product default stays at 30 until the
short-context evaluation recommends a change.

tsfm_public availability
------------------------
``granite-tsfm`` requires ``torch<2.11`` and ``transformers<5``.  The
production stack pins ``torch==2.11.0`` and ``transformers==5.8.0``.  Install
the library in a compatible environment (torch==2.10.x, transformers==4.x) to
enable live forecasting.  In the standard dev environment the import guard
catches the ``ImportError`` / ``RuntimeError`` and returns None — the rest of
the pipeline is unaffected.

Install command (compatible environment only)::

    pip install "git+https://github.com/ibm-granite/granite-tsfm"

See ``models.json`` for model IDs and revision SHA.
See ``docs/adrs/ADR-001-watsonx-runtime.md`` for the local-vs-watsonx decision.
See ``docs/06-roadmap.md`` P2.2 for the TTM-R2 context and forecast horizon.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import numpy as np

from ingest.schema import Forecast, LapFeatures

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

_PREDICTION_LENGTH = 5    # horizon per FR-3 (fixed)
_NUM_CHANNELS = 5         # soc_end, harvest_mj, deploy_mj, lap_time, avg_speed


# ──────────────────────────────────────────────────────────────────────────────
# Config helpers (read .env at call time so tests can override)
# ──────────────────────────────────────────────────────────────────────────────


def _ttm_min_laps() -> int:
    try:
        return int(os.environ.get("TTM_MIN_LAPS", "30"))
    except ValueError:
        return 30


def _ttm_context_length() -> int:
    """How many laps to feed into TTM-R2 as the rolling context window.

    Configurable via ``TTM_CONTEXT_LENGTH`` (default 30).  Change this for
    short-context evaluation experiments.  Both ``TTM_MIN_LAPS`` and
    ``TTM_CONTEXT_LENGTH`` must be set together to lower the effective gate.
    """
    try:
        return int(os.environ.get("TTM_CONTEXT_LENGTH", "30"))
    except ValueError:
        return 30


def _ttm_max_interval_width() -> float:
    try:
        return float(os.environ.get("TTM_MAX_INTERVAL_WIDTH", "0.15"))
    except ValueError:
        return 0.15


def _ttm_repo() -> str:
    return os.environ.get("TTM_R2_REPO", "ibm-granite/granite-timeseries-ttm-r2")


def _ttm_revision() -> str:
    return os.environ.get("TTM_REVISION", "d6a79570cac0f33d526601cd3a0fc7c80a8f9a2f")


# ──────────────────────────────────────────────────────────────────────────────
# Input preparation
# ──────────────────────────────────────────────────────────────────────────────


def _build_input(
    laps: list[LapFeatures],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build a normalized ``[T, C]`` float32 array from lap features.

    Channels (C=5): soc_end, harvest_mj, deploy_mj, lap_time, avg_speed

    Returns ``(normalized, mins, scales)`` so predictions can be denormalized.
    """
    arr = np.array(
        [
            [lap.soc_end, lap.harvest_mj, lap.deploy_mj, lap.lap_time, lap.avg_speed]
            for lap in laps
        ],
        dtype=np.float32,
    )
    mins = arr.min(axis=0, keepdims=True)
    maxs = arr.max(axis=0, keepdims=True)
    scale = np.where(maxs - mins < 1e-8, 1.0, maxs - mins)
    return (arr - mins) / scale, mins.squeeze(0), scale.squeeze(0)


# ──────────────────────────────────────────────────────────────────────────────
# Model singleton (lazy-loaded, never raises outside _load_model)
# ──────────────────────────────────────────────────────────────────────────────

_MODEL_CACHE: dict = {}


def _load_model(context_length: int):
    """Load and cache TinyTimeMixerForPrediction for the given context length.

    Returns None when ``tsfm_public`` is unavailable or the model fails to
    load.  The result (model or None) is cached per ``(repo, context_length)``
    so subsequent calls with the same config are instant.
    """
    cache_key = (_ttm_repo(), context_length, _PREDICTION_LENGTH)
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]

    model = None
    try:
        from tsfm_public.models.tinytimemixer import TinyTimeMixerForPrediction  # type: ignore[import]

        repo = _ttm_repo()
        revision = _ttm_revision()
        logger.info("forecasting: loading TTM-R2 from %s@%s (context=%d)", repo, revision[:8], context_length)
        model = TinyTimeMixerForPrediction.from_pretrained(
            repo,
            revision=revision,
            context_length=context_length,
            prediction_length=_PREDICTION_LENGTH,
            num_input_channels=_NUM_CHANNELS,
        )
        model.eval()
        logger.info("forecasting: TTM-R2 loaded successfully (context=%d)", context_length)
    except ImportError:
        logger.warning(
            "forecasting: tsfm_public not installed "
            "(granite-tsfm requires torch<2.11 and transformers<5; "
            "our stack pins torch==2.11.0 / transformers==5.x — "
            "install in a compatible env to enable live TTM-R2). "
            "Returning None."
        )
    except Exception as exc:
        logger.warning(
            "forecasting: TTM-R2 model load failed: %s: %s — returning None",
            type(exc).__name__,
            exc,
        )

    _MODEL_CACHE[cache_key] = model
    return model


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────


def forecast_lap_window(laps: list[LapFeatures]) -> Optional[Forecast]:
    """Attempt a 5-lap SoC forecast using TTM-R2.

    Returns ``None`` when:

    - ``len(laps) < max(TTM_MIN_LAPS, TTM_CONTEXT_LENGTH)`` — session too short
      (graceful degradation per FR-3; conservative gate protects both quality
      floor and model input requirements)
    - ``tsfm_public`` not installed (version conflict in standard dev env)
    - Model load or inference fails for any reason
    - Prediction-interval width exceeds ``TTM_MAX_INTERVAL_WIDTH`` (forecast too uncertain)

    Never raises — all failures are logged and return ``None``.

    Matches the ``ForecastFn = Callable[[list[LapFeatures]], Optional[Forecast]]``
    signature in ``core/pipeline.py`` so it can be passed directly as
    ``forecast_fn=forecast_lap_window`` in ``run_pipeline``.

    Environment variables
    ---------------------
    ``TTM_MIN_LAPS``       — product quality floor (default 30)
    ``TTM_CONTEXT_LENGTH`` — model input window length (default 30)
    ``TTM_MAX_INTERVAL_WIDTH`` — max acceptable prediction-interval width (default 0.15)
    """
    context_length = _ttm_context_length()
    min_laps = _ttm_min_laps()
    effective_min = max(min_laps, context_length)

    if len(laps) < effective_min:
        logger.debug(
            "forecasting: %d laps < effective_min=%d "
            "(TTM_MIN_LAPS=%d, TTM_CONTEXT_LENGTH=%d) — skipping forecast",
            len(laps),
            effective_min,
            min_laps,
            context_length,
        )
        return None

    model = _load_model(context_length)
    if model is None:
        return None

    try:
        import torch  # type: ignore[import]

        # Use the most recent context_length laps as the rolling input window
        window = laps[-context_length:]
        x_norm, mins, scales = _build_input(window)

        # [1, T, C] batch tensor
        input_tensor = torch.tensor(x_norm, dtype=torch.float32).unsqueeze(0)

        with torch.no_grad():
            output = model(past_values=input_tensor)

        # prediction_outputs: [1, horizon, C] — channel 0 is soc_end
        preds_norm = output.prediction_outputs[0].cpu().numpy()  # [horizon, C]

        soc_scale = float(scales[0])
        soc_min = float(mins[0])

        def _denorm(arr: np.ndarray) -> list[float]:
            raw = arr * soc_scale + soc_min
            return [float(max(0.0, min(1.0, v))) for v in raw]

        point = _denorm(preds_norm[:, 0])

        # Prediction intervals: use model output when available, else naïve ±σ band
        if hasattr(output, "prediction_interval") and output.prediction_interval is not None:
            pi = output.prediction_interval[0].cpu().numpy()  # [horizon, 2]
            lower = _denorm(pi[:, 0])
            upper = _denorm(pi[:, 1])
        else:
            observed = np.array([lap.soc_end for lap in window])
            sigma = max(0.02, min(0.10, float(observed[-10:].std())))
            lower = [float(max(0.0, p - sigma)) for p in point]
            upper = [float(min(1.0, p + sigma)) for p in point]

        # Reject if the median prediction-interval width is too wide
        widths = [u - l for u, l in zip(upper, lower)]
        median_width = sorted(widths)[len(widths) // 2]
        max_width = _ttm_max_interval_width()
        if median_width > max_width:
            logger.info(
                "forecasting: interval width %.3f > TTM_MAX_INTERVAL_WIDTH=%.3f — returning None",
                median_width,
                max_width,
            )
            return None

        repo = _ttm_repo()
        revision = _ttm_revision()
        return Forecast(
            point=point,
            lower=lower,
            upper=upper,
            model_version=f"{repo}@{revision[:8]}",
        )

    except Exception as exc:
        logger.warning(
            "forecasting: TTM-R2 inference failed: %s: %s — returning None",
            type(exc).__name__,
            exc,
        )
        return None


__all__ = ["forecast_lap_window", "_ttm_context_length", "_ttm_min_laps"]
