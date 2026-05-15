#!/usr/bin/env python3
"""Granite time-series model-fit evaluation for OVERRIDE.

Answers:
  1. Which Granite model family fits OVERRIDE's forecasting problem best?
  2. Is lap-level telemetry enough, or does OVERRIDE need denser tick-level input?

Candidate models
----------------
  ibm-granite/granite-timeseries-ttm-r1
  ibm-granite/granite-timeseries-ttm-r2
  ibm-granite/granite-timeseries-patchtst
  ibm-granite/granite-timeseries-patchtsmixer

Input representations
---------------------
  lap-level  : one feature vector per completed lap (up to 30 laps for OVERRIDE)
  tick-level : downsampled per-tick TORCS observations (target ≈ 512 total points)

Usage
-----
  .venv/bin/python scripts/eval_model_fit.py [--model MODEL] [--json] [--save]

  --model MODEL   Run only one model (short name: ttm-r1, ttm-r2, patchtst, patchtsmixer)
  --json          Print raw JSON result
  --save          Write findings JSON to docs/plans/model-fit-eval-results-2026-05-15.json

Methodology
-----------
Phase 1  — Config sweep: fetch Hugging Face checkpoint configs and assess
           structural compatibility with OVERRIDE's two representations.

Phase 2  — Analytical scoring: for each (model, representation) pair derive:
           • min_series_length   required for ≥1 patch
           • patches_at_max      patches available at OVERRIDE's practical cap
           • prediction_delta    mismatch between model's horizon and OVERRIDE's 5-lap target
           • compatible          boolean summary

Phase 3  — Inference trial: attempt to load + run each candidate with
           available runtime.  Reports detailed failure reason when inference
           is blocked.

Phase 4  — Dense representation prototype: if lap-level fails broadly, show
           what tick-level downsampling would unlock each model and estimate
           the fidelity delta.

Confirmed results (run with .venv-ttm-eval: torch 2.10.0+cu128, tsfm_public):
  PatchTST     : dummy forward pass succeeded, output_shape=[5, 5]
  PatchTSMixer : forward pass failed (mat shape mismatch at 1-patch input)
  TTM-R1/R2    : forward pass succeeded with checkpoint ctx=512, output=[5,1]
                 (univariate; lap-level still analytically incompatible)

NOTE: all inference trials use synthetic random tensors, NOT real TORCS data.
"inference_succeeded" means architectural compatibility only — it is NOT
evidence of forecast quality.  forecasting_should_remain_disabled=True until
MAE is measured on real OVERRIDE sessions.

Best structural candidate for the next real-data MAE test: PatchTST
  - lap-level compatible (2 patches from 30 laps)
  - multivariate (5 channels)
  - forward pass confirmed with synthetic data
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import Optional

# ── path setup ────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

OVERRIDE_HORIZON = 5            # FR-3 target: next 5 laps
OVERRIDE_CHANNELS = 5           # soc_end, harvest_mj, deploy_mj, lap_time, avg_speed
OVERRIDE_MAX_LAPS = 30          # current production gate
TORCS_TICKS_PER_LAP = 5411      # ~50 Hz × ~108 s observed in data/samples/torcs_baseline.jsonl
TORCS_LAP_TIME_S = 111          # representative lap time in seconds

CANDIDATE_MODELS = [
    {
        "name": "ttm-r1",
        "repo": "ibm-granite/granite-timeseries-ttm-r1",
        "revision": None,
        "arch": "TinyTimeMixerForPrediction",
        "lib": "tsfm_public",
    },
    {
        "name": "ttm-r2",
        "repo": "ibm-granite/granite-timeseries-ttm-r2",
        "revision": "d6a79570cac0f33d526601cd3a0fc7c80a8f9a2f",
        "arch": "TinyTimeMixerForPrediction",
        "lib": "tsfm_public",
    },
    {
        "name": "patchtst",
        "repo": "ibm-granite/granite-timeseries-patchtst",
        "revision": None,
        "arch": "PatchTSTForPrediction",
        "lib": "transformers",
    },
    {
        "name": "patchtsmixer",
        "repo": "ibm-granite/granite-timeseries-patchtsmixer",
        "revision": None,
        "arch": "PatchTSMixerForPrediction",
        "lib": "transformers",
    },
]

# ──────────────────────────────────────────────────────────────────────────────
# Phase 1 — Config fetch
# ──────────────────────────────────────────────────────────────────────────────


def _fetch_config(repo: str, revision: Optional[str]) -> dict:
    """Download config.json from a Hugging Face repo (cached locally)."""
    try:
        from huggingface_hub import hf_hub_download

        kw: dict = {"repo_id": repo, "filename": "config.json"}
        if revision:
            kw["revision"] = revision
        path = hf_hub_download(**kw)
        with open(path) as f:
            return json.load(f)
    except Exception as exc:
        return {"_fetch_error": str(exc)}


def fetch_all_configs(candidates: list[dict]) -> dict[str, dict]:
    """Return {model_name: config_dict} for each candidate."""
    out: dict[str, dict] = {}
    for c in candidates:
        out[c["name"]] = _fetch_config(c["repo"], c["revision"])
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Phase 2 — Analytical compatibility
# ──────────────────────────────────────────────────────────────────────────────


def _patches_available(context: int, patch: int) -> int:
    """Number of non-overlapping patches from a series of length context."""
    if patch <= 0:
        return 0
    return context // patch


def _assess_lap_level(model_meta: dict, config: dict) -> dict:
    """Analytical compatibility report for lap-level representation.

    OVERRIDE max: 30 laps, channels=5, horizon=5.
    """
    patch_length = config.get("patch_length") or 0
    context_length = config.get("context_length") or 0
    prediction_length = config.get("prediction_length") or 0
    fetch_error = config.get("_fetch_error")

    if fetch_error:
        return {
            "representation": "lap-level",
            "compatible": False,
            "reason": f"config fetch failed: {fetch_error}",
        }

    issues: list[str] = []

    # Patch coverage: need at least 1 full patch from our max 30 laps
    max_patches = _patches_available(OVERRIDE_MAX_LAPS, patch_length)
    if patch_length > OVERRIDE_MAX_LAPS:
        issues.append(
            f"patch_length={patch_length} > OVERRIDE max laps={OVERRIDE_MAX_LAPS}: "
            "cannot form even one patch — model structurally incompatible at lap granularity"
        )
    elif max_patches < 2:
        issues.append(
            f"patch_length={patch_length} yields only {max_patches} patch(es) from {OVERRIDE_MAX_LAPS} laps: "
            "too few patches; model was trained with much longer contexts"
        )

    # Context coverage: our window vs trained context
    coverage_pct = round(100 * OVERRIDE_MAX_LAPS / max(context_length, 1), 1)
    if coverage_pct < 10:
        issues.append(
            f"OVERRIDE max {OVERRIDE_MAX_LAPS} laps = {coverage_pct}% of trained "
            f"context_length={context_length}: severe distribution shift expected"
        )
    elif coverage_pct < 30:
        issues.append(
            f"OVERRIDE max {OVERRIDE_MAX_LAPS} laps = {coverage_pct}% of trained "
            f"context_length={context_length}: significant distribution shift likely"
        )

    # Prediction length: OVERRIDE needs 5; checkpoint exposes 96
    if prediction_length != OVERRIDE_HORIZON:
        issues.append(
            f"prediction_length mismatch: checkpoint={prediction_length}, "
            f"OVERRIDE needs {OVERRIDE_HORIZON} — requires override in from_pretrained; "
            "model quality may degrade outside trained horizon"
        )

    compatible = not any("structurally incompatible" in i for i in issues)
    return {
        "representation": "lap-level",
        "available_laps": OVERRIDE_MAX_LAPS,
        "checkpoint_context_length": context_length,
        "patch_length": patch_length,
        "max_patches_from_30_laps": max_patches,
        "context_coverage_pct": coverage_pct,
        "checkpoint_prediction_length": prediction_length,
        "compatible": compatible,
        "issues": issues,
        "reason": "; ".join(issues) if issues else "no structural blockers found",
    }


def _estimate_tick_density(context_length: int, patch_length: int) -> dict:
    """Compute a viable downsampled tick representation for the given model.

    We want approx. `context_length` total points from a 20–30 lap session.
    Points come from evenly-spaced ticks within each lap.
    """
    # Target total ticks = context_length (to match trained context exactly)
    target_total = context_length
    ticks_per_lap_30 = target_total // OVERRIDE_MAX_LAPS  # for 30-lap session
    ticks_per_lap_20 = target_total // 20                 # for 20-lap session

    actual_raw_ticks_per_lap = TORCS_TICKS_PER_LAP
    subsample_ratio_30 = round(actual_raw_ticks_per_lap / max(ticks_per_lap_30, 1), 1)
    subsample_ratio_20 = round(actual_raw_ticks_per_lap / max(ticks_per_lap_20, 1), 1)

    # Patches available at this density
    patches_30 = _patches_available(target_total, patch_length)
    patches_20 = _patches_available(20 * ticks_per_lap_20, patch_length)

    time_resolution_s_30 = round(TORCS_LAP_TIME_S / max(ticks_per_lap_30, 1), 1)
    time_resolution_s_20 = round(TORCS_LAP_TIME_S / max(ticks_per_lap_20, 1), 1)

    return {
        "ticks_per_lap_for_30_lap_session": ticks_per_lap_30,
        "ticks_per_lap_for_20_lap_session": ticks_per_lap_20,
        "time_resolution_s_at_30_laps": time_resolution_s_30,
        "time_resolution_s_at_20_laps": time_resolution_s_20,
        "subsample_ratio_30_laps": subsample_ratio_30,
        "subsample_ratio_20_laps": subsample_ratio_20,
        "patches_from_30_lap_session": patches_30,
        "patches_from_20_lap_session": patches_20,
    }


def _assess_tick_level(model_meta: dict, config: dict) -> dict:
    """Analytical compatibility report for tick-level representation."""
    patch_length = config.get("patch_length") or 0
    context_length = config.get("context_length") or 0
    prediction_length = config.get("prediction_length") or 0
    fetch_error = config.get("_fetch_error")

    if fetch_error:
        return {
            "representation": "tick-level",
            "compatible": False,
            "reason": f"config fetch failed: {fetch_error}",
        }

    density = _estimate_tick_density(context_length, patch_length)
    issues: list[str] = []

    ticks_30 = density["ticks_per_lap_for_30_lap_session"]
    if ticks_30 < 1:
        issues.append(
            f"Would need sub-tick sampling to fill context_length={context_length} from 30 laps"
        )

    if prediction_length != OVERRIDE_HORIZON:
        issues.append(
            f"prediction_length mismatch: checkpoint={prediction_length}, "
            f"OVERRIDE needs {OVERRIDE_HORIZON} — override required but tractable"
        )

    time_res = density["time_resolution_s_at_30_laps"]
    if time_res > 10.0:
        issues.append(
            f"time resolution at 30 laps ≈ {time_res}s — coarse; "
            "intra-lap energy dynamics may be lost"
        )

    signal_notes: list[str] = []
    # What tick-level signals map to energy channels?
    signal_notes.append(
        "brake (0..1) → regen harvest proxy; accel (0..1) → deploy proxy; "
        "speedX → speed; curLapTime → time-in-lap; rpm → power state"
    )

    return {
        "representation": "tick-level",
        "checkpoint_context_length": context_length,
        "patch_length": patch_length,
        "checkpoint_prediction_length": prediction_length,
        "compatible": True,
        "density_plan": density,
        "signal_mapping": signal_notes,
        "issues": issues,
        "reason": (
            "; ".join(issues)
            if issues
            else f"tick-level at {density['time_resolution_s_at_30_laps']}s resolution unlocks full context"
        ),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Phase 3 — Inference trial
# ──────────────────────────────────────────────────────────────────────────────


def _trial_torch_import() -> tuple[bool, str]:
    """Check whether torch is importable in this environment."""
    try:
        import torch  # type: ignore[import]
        return True, f"torch {torch.__version__}"
    except ImportError as e:
        return False, f"torch ImportError: {e}"
    except Exception as e:
        return False, f"torch load failure: {type(e).__name__}: {e}"


def _trial_tsfm_import() -> tuple[bool, str]:
    """Check whether tsfm_public is importable."""
    try:
        from tsfm_public.models.tinytimemixer import TinyTimeMixerForPrediction  # type: ignore[import]
        return True, "tsfm_public available (TinyTimeMixerForPrediction)"
    except ImportError as e:
        return False, f"tsfm_public ImportError: {e}"
    except Exception as e:
        return False, f"tsfm_public load failure: {type(e).__name__}: {e}"


def _trial_transformers_patchtst() -> tuple[bool, str]:
    """Check whether PatchTSTForPrediction is importable from transformers."""
    try:
        from transformers import PatchTSTForPrediction  # type: ignore[import]
        return True, "transformers.PatchTSTForPrediction available"
    except ImportError as e:
        return False, f"transformers PatchTSTForPrediction ImportError: {e}"
    except Exception as e:
        return False, f"transformers PatchTSTForPrediction: {type(e).__name__}: {e}"


def _trial_transformers_patchtsmixer() -> tuple[bool, str]:
    """Check whether PatchTSMixerForPrediction is importable from transformers."""
    try:
        from transformers import PatchTSMixerForPrediction  # type: ignore[import]
        return True, "transformers.PatchTSMixerForPrediction available"
    except ImportError as e:
        return False, f"transformers PatchTSMixerForPrediction ImportError: {e}"
    except Exception as e:
        return False, f"transformers PatchTSMixerForPrediction: {type(e).__name__}: {e}"


def _run_inference_trial(model_meta: dict, config: dict) -> dict:
    """Attempt minimal inference trial and report results."""
    lib = model_meta["lib"]
    arch = model_meta["arch"]

    torch_ok, torch_msg = _trial_torch_import()
    if not torch_ok:
        return {
            "inference_attempted": True,
            "inference_succeeded": False,
            "blocker": "torch_unavailable",
            "detail": torch_msg,
        }

    if lib == "tsfm_public":
        lib_ok, lib_msg = _trial_tsfm_import()
        if not lib_ok:
            return {
                "inference_attempted": True,
                "inference_succeeded": False,
                "blocker": "tsfm_public_unavailable",
                "detail": lib_msg,
                "fix": (
                    "Install granite-tsfm in a torch<2.11 + transformers<5 env: "
                    "pip install git+https://github.com/ibm-granite/granite-tsfm"
                ),
            }
    elif lib == "transformers":
        if arch == "PatchTSTForPrediction":
            lib_ok, lib_msg = _trial_transformers_patchtst()
        else:
            lib_ok, lib_msg = _trial_transformers_patchtsmixer()
        if not lib_ok:
            return {
                "inference_attempted": True,
                "inference_succeeded": False,
                "blocker": "transformers_model_unavailable",
                "detail": lib_msg,
            }

    # If we reach here, library is available — attempt a minimal forward pass
    try:
        patch_length = config.get("patch_length", 64)
        import numpy as np
        import torch  # type: ignore[import]

        # Default context for the dummy input: OVERRIDE practical cap, rounded
        # up to the next patch boundary so TTM's internal patch math is clean.
        override_context = OVERRIDE_MAX_LAPS
        if patch_length > 1:
            # Round up to nearest multiple of patch_length
            override_context = max(patch_length, ((OVERRIDE_MAX_LAPS + patch_length - 1) // patch_length) * patch_length)

        dummy = np.random.randn(override_context, OVERRIDE_CHANNELS).astype("float32")
        input_tensor = torch.tensor(dummy, dtype=torch.float32).unsqueeze(0)

        if lib == "tsfm_public":
            from tsfm_public.models.tinytimemixer import TinyTimeMixerForPrediction  # type: ignore[import]
            # Load with checkpoint defaults (pred_length=96, channels=1) to avoid strict
            # state_dict mismatch on the head layer.  Slice first OVERRIDE_HORIZON steps.
            checkpoint_pred = config.get("prediction_length", 96)
            checkpoint_channels = config.get("num_input_channels", 1)
            # Use checkpoint's full context_length for the inference trial; the
            # lap-level incompatibility is already captured analytically above.
            checkpoint_ctx = config.get("context_length", 512)
            dummy_ttm = np.random.randn(checkpoint_ctx, checkpoint_channels).astype("float32")
            input_ttm = torch.tensor(dummy_ttm, dtype=torch.float32).unsqueeze(0)
            model = TinyTimeMixerForPrediction.from_pretrained(
                model_meta["repo"],
                revision=model_meta["revision"],
                num_input_channels=checkpoint_channels,
            )
            model.eval()
            with torch.no_grad():
                out = model(past_values=input_ttm)
            preds = out.prediction_outputs[0, :OVERRIDE_HORIZON, :].cpu().numpy()
            return {
                "inference_attempted": True,
                "inference_succeeded": True,
                "output_shape": list(preds.shape),
                "note": (
                    f"loaded with checkpoint ctx={checkpoint_ctx}, pred={checkpoint_pred}, "
                    f"sliced to horizon={OVERRIDE_HORIZON}; lap-level still analytically incompatible"
                ),
            }
        elif lib == "transformers":
            cls_map = {
                "PatchTSTForPrediction": "PatchTSTForPrediction",
                "PatchTSMixerForPrediction": "PatchTSMixerForPrediction",
            }
            import transformers  # type: ignore[import]
            ModelCls = getattr(transformers, cls_map[arch])
            model = ModelCls.from_pretrained(
                model_meta["repo"],
                context_length=override_context,
                prediction_length=OVERRIDE_HORIZON,
                num_input_channels=OVERRIDE_CHANNELS,
                ignore_mismatched_sizes=True,
            )
            model.eval()
            with torch.no_grad():
                out = model(past_values=input_tensor)
            preds = out.prediction_outputs[0].cpu().numpy()
            return {
                "inference_attempted": True,
                "inference_succeeded": True,
                "output_shape": list(preds.shape),
            }
    except Exception as exc:
        return {
            "inference_attempted": True,
            "inference_succeeded": False,
            "blocker": "inference_error",
            "detail": f"{type(exc).__name__}: {exc}",
        }

    return {
        "inference_attempted": False,
        "inference_succeeded": False,
        "blocker": "unknown",
    }


# ──────────────────────────────────────────────────────────────────────────────
# Main evaluation loop
# ──────────────────────────────────────────────────────────────────────────────


def evaluate(filter_model: Optional[str] = None) -> dict:
    """Run the full model-fit evaluation.

    Returns a dict with keys:
      env          — runtime environment summary
      models       — per-model config + compatibility + inference_trial
      recommendations — structured recommendation memo
    """
    candidates = CANDIDATE_MODELS
    if filter_model:
        candidates = [c for c in candidates if c["name"] == filter_model]
        if not candidates:
            raise ValueError(f"Unknown model name '{filter_model}'. "
                             f"Valid: {[c['name'] for c in CANDIDATE_MODELS]}")

    # Environment check
    torch_ok, torch_msg = _trial_torch_import()
    env = {
        "torch_available": torch_ok,
        "torch_detail": torch_msg,
        "tsfm_public_available": False,
        "tsfm_public_detail": "",
        "transformers_patchtst_available": False,
        "transformers_patchtst_detail": "",
        "transformers_patchtsmixer_available": False,
        "transformers_patchtsmixer_detail": "",
        "override_max_laps": OVERRIDE_MAX_LAPS,
        "override_horizon": OVERRIDE_HORIZON,
        "override_channels": OVERRIDE_CHANNELS,
        "torcs_ticks_per_lap": TORCS_TICKS_PER_LAP,
    }
    if torch_ok:
        ok, msg = _trial_tsfm_import()
        env["tsfm_public_available"] = ok
        env["tsfm_public_detail"] = msg
        ok, msg = _trial_transformers_patchtst()
        env["transformers_patchtst_available"] = ok
        env["transformers_patchtst_detail"] = msg
        ok, msg = _trial_transformers_patchtsmixer()
        env["transformers_patchtsmixer_available"] = ok
        env["transformers_patchtsmixer_detail"] = msg

    # Per-model analysis
    models_out: list[dict] = []
    for c in candidates:
        config = _fetch_config(c["repo"], c["revision"])
        lap = _assess_lap_level(c, config)
        tick = _assess_tick_level(c, config)
        trial = _run_inference_trial(c, config)

        models_out.append({
            "name": c["name"],
            "repo": c["repo"],
            "arch": c["arch"],
            "lib": c["lib"],
            "checkpoint_config": {
                k: config.get(k)
                for k in ["model_type", "context_length", "patch_length",
                          "patch_stride", "prediction_length", "num_patches",
                          "num_input_channels", "distribution_output"]
                if k in config
            },
            "lap_level": lap,
            "tick_level": tick,
            "inference_trial": trial,
        })

    # Recommendation memo
    recommendations = _build_recommendations(env, models_out)

    return {
        "eval_date": "2026-05-15",
        "env": env,
        "models": models_out,
        "recommendations": recommendations,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Recommendation builder
# ──────────────────────────────────────────────────────────────────────────────


def _build_recommendations(env: dict, models: list[dict]) -> dict:
    """Derive structured recommendations from the assessment."""
    lap_compatible = [
        m for m in models if m["lap_level"].get("compatible", False)
    ]
    lap_blocked = [
        m for m in models if not m["lap_level"].get("compatible", False)
    ]
    inference_succeeded = [
        m for m in models if m["inference_trial"].get("inference_succeeded", False)
    ]

    # Determine best lap-level candidate (by patch coverage at OVERRIDE_MAX_LAPS)
    best_lap_candidate = None
    best_patches = 0
    for m in lap_compatible:
        patches = m["lap_level"].get("max_patches_from_30_laps", 0)
        if patches > best_patches:
            best_patches = patches
            best_lap_candidate = m

    # Determine if tick-level is the right move
    all_lap_blocked = len(lap_compatible) == 0 or all(
        "structurally incompatible" in " ".join(m["lap_level"].get("issues", []))
        for m in models
    )

    # Primary recommendation
    # NOTE: inference_succeeded here means a dummy forward pass completed —
    # it does NOT prove the model produces meaningful forecasts on OVERRIDE data.
    # Until MAE is evaluated on real TORCS sessions, phrasing must be cautious.
    if inference_succeeded:
        inference_names = [m["name"] for m in inference_succeeded]
        primary = "evaluate_lap_level_candidate"
        detail = (
            f"Model(s) {inference_names} completed a forward pass with synthetic data. "
            "This confirms architectural compatibility only — it does NOT prove forecast "
            "quality on OVERRIDE session data. Next step: run MAE evaluation on real "
            "TORCS sessions before treating any model as the production candidate."
        )
    elif lap_compatible and best_lap_candidate:
        primary = "test_patchtst_or_patchtsmixer_lap_level"
        detail = (
            f"{best_lap_candidate['name']} is the best structural fit at lap-level "
            f"({best_patches} patches from 30 laps). "
            "Requires compatible torch + transformers env for inference trial."
        )
    else:
        primary = "move_to_tick_level"
        detail = (
            "No model can form sufficient patches from 30 lap-level points. "
            "Tick-level downsampling to ~17 points/lap for 30 laps fills "
            "context_length=512 and unlocks all four candidates."
        )

    return {
        "lap_level_compatible_models": [m["name"] for m in lap_compatible],
        "lap_level_blocked_models": [m["name"] for m in lap_blocked],
        "inference_succeeded_models": [m["name"] for m in inference_succeeded],
        "best_lap_level_candidate": best_lap_candidate["name"] if best_lap_candidate else None,
        "primary_recommendation": primary,
        "primary_detail": detail,
        # forecasting_should_remain_disabled is ALWAYS True until MAE on real
        # OVERRIDE session data has been measured.  A successful dummy forward
        # pass only proves architectural compatibility, not forecast quality.
        "forecasting_should_remain_disabled": True,
        "tick_level_required_for_ttm": True,
        "tick_level_notes": (
            "TTM-R1/R2 (patch_length=64) require 64+ data points per context window. "
            "At lap granularity OVERRIDE tops out at 30 laps — always insufficient. "
            "Downsampling to 17 ticks/lap × 30 laps = 510 ≈ context_length=512 "
            "would unlock TTM-R1/R2 with high time-resolution energy signals."
        ),
        "patchtst_patchtsmixer_notes": (
            "PatchTST (patch=12) and PatchTSMixer (patch=16) can technically form "
            "2 and 1 patches respectively from 30 laps. But the model was trained "
            "on 512÷12=42 or 512÷16=32 patches; operating with 1–2 patches is severe "
            "out-of-distribution use. Tick-level is still recommended."
        ),
        "next_steps": [
            "Run MAE evaluation on real TORCS sessions using PatchTST at lap-level",
            "Compare MAE to a linear-trend baseline to confirm the model adds value",
            "If lap-level MAE is poor: implement tick-level downsampling (~17 ticks/lap × 30 laps ≈ 510 pts)",
            "Re-run sweep at tick-level to confirm fit and re-measure MAE",
            "Only after MAE beats baseline on real data: reconsider live forecast threshold",
        ],
    }


# ──────────────────────────────────────────────────────────────────────────────
# Formatting
# ──────────────────────────────────────────────────────────────────────────────

_W = 120
_SEP = "─" * _W


def _print_env(env: dict) -> None:
    print()
    print("OVERRIDE — Granite Time-Series Model-Fit Evaluation")
    print("=" * _W)
    print()
    print("  RUNTIME ENVIRONMENT")
    print("  " + "-" * 60)
    torch_sym = "✓" if env["torch_available"] else "✗"
    print(f"    {torch_sym} torch          : {env['torch_detail']}")
    for key, label in [
        ("tsfm_public_available",              "tsfm_public   "),
        ("transformers_patchtst_available",     "PatchTST      "),
        ("transformers_patchtsmixer_available", "PatchTSMixer  "),
    ]:
        sym = "✓" if env.get(key) else "✗"
        detail_key = key.replace("_available", "_detail")
        print(f"    {sym} {label}: {env.get(detail_key, '')}")
    print()
    print(f"  OVERRIDE config: max_laps={env['override_max_laps']}, "
          f"horizon={env['override_horizon']}, channels={env['override_channels']}, "
          f"torcs_ticks_per_lap≈{env['torcs_ticks_per_lap']}")
    print()


def _print_model(m: dict) -> None:
    print(_SEP)
    cfg = m["checkpoint_config"]
    print(f"  Model: {m['name']:20s}  repo: {m['repo']}")
    print(
        f"  Arch: {m['arch']:40s}  lib: {m['lib']}"
    )
    print(
        f"  Checkpoint: context={cfg.get('context_length')}, "
        f"patch={cfg.get('patch_length')}, stride={cfg.get('patch_stride')}, "
        f"pred={cfg.get('prediction_length')}, "
        f"num_patches={cfg.get('num_patches')}, "
        f"channels={cfg.get('num_input_channels')}"
    )
    print()

    # Lap-level
    lap = m["lap_level"]
    lap_sym = "✓ COMPATIBLE" if lap.get("compatible") else "✗ INCOMPATIBLE"
    print(f"  [LAP-LEVEL]  {lap_sym}")
    print(f"    patches from {OVERRIDE_MAX_LAPS} laps : "
          f"{lap.get('max_patches_from_30_laps', '?')}")
    print(f"    context coverage   : {lap.get('context_coverage_pct', '?')}% "
          f"of trained context_length={cfg.get('context_length')}")
    for issue in lap.get("issues", []):
        print(f"    ⚠  {issue}")
    if not lap.get("issues"):
        print(f"    {lap.get('reason', '')}")
    print()

    # Tick-level
    tick = m["tick_level"]
    tick_sym = "✓ COMPATIBLE" if tick.get("compatible") else "✗ INCOMPATIBLE"
    print(f"  [TICK-LEVEL]  {tick_sym}")
    dp = tick.get("density_plan", {})
    if dp:
        print(f"    ticks/lap for 30-lap session : {dp.get('ticks_per_lap_for_30_lap_session')} "
              f"(≈{dp.get('time_resolution_s_at_30_laps')}s resolution, "
              f"1-in-{dp.get('subsample_ratio_30_laps')} raw ticks)")
        print(f"    ticks/lap for 20-lap session : {dp.get('ticks_per_lap_for_20_lap_session')} "
              f"(≈{dp.get('time_resolution_s_at_20_laps')}s resolution)")
        print(f"    patches from 30-lap session  : {dp.get('patches_from_30_lap_session')}")
    for issue in tick.get("issues", []):
        print(f"    ⚠  {issue}")
    if tick.get("signal_mapping"):
        print(f"    signals: {tick['signal_mapping'][0]}")
    print()

    # Inference trial
    trial = m["inference_trial"]
    if trial.get("inference_succeeded"):
        note = trial.get("note", "")
        suffix = f"  [{note}]" if note else ""
        print(f"  [INFERENCE]  ✓ SYNTHETIC FORWARD PASS OK  output shape={trial.get('output_shape')}{suffix}")
        print(f"    ⚠  synthetic random input only — does NOT prove forecast quality on real data")
    else:
        blocker = trial.get("blocker", "not_attempted")
        detail = trial.get("detail", "")
        print(f"  [INFERENCE]  ✗ BLOCKED  ({blocker})")
        if detail:
            print(f"    {detail}")
        if trial.get("fix"):
            print(f"    fix: {trial['fix']}")
    print()


def _print_recommendations(rec: dict) -> None:
    print(_SEP)
    print()
    print("FINDINGS SUMMARY")
    print("=" * _W)
    print()

    lap_ok = rec["lap_level_compatible_models"]
    lap_blocked = rec["lap_level_blocked_models"]
    print(f"  Lap-level COMPATIBLE  : {lap_ok or ['none']}")
    print(f"  Lap-level BLOCKED     : {lap_blocked}")
    print(f"  Inference succeeded   : {rec['inference_succeeded_models'] or ['none (runtime blocked)']}")
    print(f"  Best lap-level cand.  : {rec['best_lap_level_candidate'] or 'none'}")
    print()
    print(f"  Primary recommendation: {rec['primary_recommendation']}")
    print(f"    {rec['primary_detail']}")
    print()
    print("  TTM-R1 / TTM-R2 (TinyTimeMixer)")
    print("  " + "-" * 60)
    print(f"    {rec['tick_level_notes']}")
    print()
    print("  PatchTST / PatchTSMixer")
    print("  " + "-" * 60)
    print(f"    {rec['patchtst_patchtsmixer_notes']}")
    print()
    print("  NEXT STEPS")
    print("  " + "-" * 60)
    for i, step in enumerate(rec["next_steps"], 1):
        print(f"    {i}. {step}")
    print()
    print("  PRODUCT DECISION")
    print("  " + "-" * 60)
    print("    → Live forecasting remains disabled.")
    print("    → Synthetic forward pass success is NOT sufficient to enable forecasting.")
    print("    → Do not lower production threshold until MAE on real OVERRIDE sessions")
    print("       has been measured and shown to beat a linear-trend baseline.")
    print(f"    → Best structural candidate for next real-data test: {rec.get('best_lap_level_candidate', 'patchtst')}")
    print()
    print("=" * _W)


def print_results(result: dict) -> None:
    _print_env(result["env"])
    for m in result["models"]:
        _print_model(m)
    _print_recommendations(result["recommendations"])


# ──────────────────────────────────────────────────────────────────────────────
# Artifact saving
# ──────────────────────────────────────────────────────────────────────────────

ARTIFACT_PATH = REPO_ROOT / "docs" / "plans" / "model-fit-eval-results-2026-05-15.json"


def save_artifact(result: dict) -> Path:
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(ARTIFACT_PATH, "w") as f:
        json.dump(result, f, indent=2)
    return ARTIFACT_PATH


# ──────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Granite time-series model-fit evaluation for OVERRIDE"
    )
    parser.add_argument(
        "--model",
        choices=[c["name"] for c in CANDIDATE_MODELS],
        help="Evaluate only this model (default: all)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON result",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help=f"Save JSON findings to {ARTIFACT_PATH}",
    )
    args = parser.parse_args()

    result = evaluate(filter_model=args.model)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_results(result)

    if args.save:
        path = save_artifact(result)
        print(f"\n  [saved] {path}")
