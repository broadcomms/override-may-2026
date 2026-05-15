"""TTM-R2 time-series forecasting (FR-3, optional per graceful-degradation guardrail).

Local-only enhancement using IBM Granite TimeSeries TTM-R2.  Falls back
gracefully when ``tsfm_public`` is unavailable or the session doesn't qualify.

Eligibility gate
----------------
- ``len(laps) < TTM_MIN_LAPS`` (default 30) → return None immediately.

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

_CONTEXT_LENGTH = 30      # laps fed into TTM-R2 (rolling window)
_PREDICTION_LENGTH = 5    # horizon per FR-3
_NUM_CHANNELS = 5         # soc_end, harvest_mj, deploy_mj, lap_time, avg_speed


# ──────────────────────────────────────────────────────────────────────────────
# Config helpers (read .env at call time so tests can override)
# ──────────────────────────────────────────────────────────────────────────────


def _ttm_min_laps() -> int:
    try:
        return int(os.environ.get("TTM_MIN_LAPS", "30"))
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


def _load_model():
    """Load and cache TinyTimeMixerForPrediction.

    Returns None when ``tsfm_public`` is unavailable or the model fails to
    load.  The result (model or None) is cached so subsequent calls are
    instant.
    """
    cache_key = (_ttm_repo(), _CONTEXT_LENGTH, _PREDICTION_LENGTH)
    if cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]

    model = None
    try:
        from tsfm_public.models.tinytimemixer import TinyTimeMixerForPrediction  # type: ignore[import]

        repo = _ttm_repo()
        revision = _ttm_revision()
        logger.info("forecasting: loading TTM-R2 from %s@%s", repo, revision[:8])
        model = TinyTimeMixerForPrediction.from_pretrained(
            repo,
            revision=revision,
            context_length=_CONTEXT_LENGTH,
            prediction_length=_PREDICTION_LENGTH,
            num_input_channels=_NUM_CHANNELS,
        )
        model.eval()
        logger.info("forecasting: TTM-R2 loaded successfully")
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

    - ``len(laps) < TTM_MIN_LAPS`` — session too short (graceful degradation per FR-3)
    - ``tsfm_public`` not installed (version conflict in standard dev env)
    - Model load or inference fails for any reason
    - Prediction-interval width exceeds ``TTM_MAX_INTERVAL_WIDTH`` (forecast too uncertain)

    Never raises — all failures are logged and return ``None``.

    Matches the ``ForecastFn = Callable[[list[LapFeatures]], Optional[Forecast]]``
    signature in ``core/pipeline.py`` so it can be passed directly as
    ``forecast_fn=forecast_lap_window`` in ``run_pipeline``.
    """
    min_laps = _ttm_min_laps()
    if len(laps) < min_laps:
        logger.debug(
            "forecasting: %d laps < TTM_MIN_LAPS=%d — skipping forecast",
            len(laps),
            min_laps,
        )
        return None

    model = _load_model()
    if model is None:
        return None

    try:
        import torch  # type: ignore[import]

        # Use the most recent _CONTEXT_LENGTH laps
        window = laps[-_CONTEXT_LENGTH:]
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


__all__ = ["forecast_lap_window"]
