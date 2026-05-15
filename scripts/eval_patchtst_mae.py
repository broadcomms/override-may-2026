#!/usr/bin/env python3
"""PatchTST vs linear-trend baseline MAE evaluation on OVERRIDE TORCS session data.

Answers: does PatchTST beat a linear-trend baseline on real OVERRIDE-shaped data?

This is the evidence step after the structural model-fit sweep (c368469).
A successful synthetic forward pass proved architectural compatibility only.
This script tests actual forecast quality on real-shaped lap data.

Important caveats (read before interpreting results)
------------------------------------------------------
1. HEAD IS RANDOMLY INITIALIZED.  PatchTST is loaded with
   ``ignore_mismatched_sizes=True`` because OVERRIDE needs prediction_length=5
   but the checkpoint's head was trained for prediction_length=96 and
   num_input_channels=7 (vs. OVERRIDE's 5).  HuggingFace re-initializes the
   non-matching layers randomly at load time.  The encoder weights are
   pretrained and preserved, but the decoder head that maps encoder output to
   forecast values is random.  Any MAE result for PatchTST here reflects
   pretrained-encoder features + random projection, NOT a fine-tuned model.

2. NO REAL SESSIONS ABOVE 30 LAPS.  The stored TORCS sessions in
   data/sessions/ all have 1–4 completed laps — far below the 30-lap gate.
   The 35-lap forecast_demo fixture is the only real OVERRIDE-shaped data
   with sufficient history.  Three synthetic sessions (varied energy patterns,
   35 laps each) are included for evaluation breadth but are not real races.

3. FORECASTING STAYS DISABLED.  ``forecasting_should_remain_disabled=True``
   regardless of these results.  Even a MAE win here would require review
   before any product change.

Dataset
-------
  - forecast_demo (fixture, 35 laps, real TORCS SoC trajectory)
  - synthetic_steady_decline (35 laps, slow consistent SoC drop)
  - synthetic_mixed_recovery (35 laps, alternating harvest/deploy balance)
  - synthetic_late_pressure (35 laps, aggressive depletion from lap 20)

Evaluation method
-----------------
For each session of N laps (N ≥ 35):
  Window A: history=laps[0:30], actual=laps[30:35]
  Window B: history=laps[5:35], actual=laps[35:40]  (40-lap sessions only)

For each window:
  1. Build [context_length=36, channels=5] input (pad if < 36 laps).
  2. Run PatchTST → next-5 soc_end predictions.
  3. Run linear-trend baseline → next-5 soc_end predictions.
  4. Compare both against actual soc_end values.
  5. Record MAE for each.

Usage
-----
  .venv-ttm-eval/bin/python scripts/eval_patchtst_mae.py [--save] [--json]

  --save   Write results to docs/plans/patchtst-mae-results-2026-05-15.json
  --json   Print raw JSON to stdout

Requires: torch 2.10.x, transformers (PatchTSTForPrediction), numpy
          Use .venv-ttm-eval which already has these installed.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Optional

# ── path setup ────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ingest.schema import LapFeatures  # noqa: E402

# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────

PATCHTST_REPO = "ibm-granite/granite-timeseries-patchtst"
PATCH_LENGTH = 12   # checkpoint default; context_length must be a multiple
CONTEXT_LENGTH = 36  # 3 full patches from 30-lap window (36 = ceil(30/12)*12)
HORIZON = 5          # next-5-lap forecast
CHANNELS = 5         # soc_end, harvest_mj, deploy_mj, lap_time, avg_speed

ARTIFACT_PATH = REPO_ROOT / "docs" / "plans" / "patchtst-mae-results-2026-05-15.json"

# ──────────────────────────────────────────────────────────────────────────────
# Session builders
# ──────────────────────────────────────────────────────────────────────────────


def _load_fixture_laps() -> tuple[str, list[LapFeatures]]:
    """Load the 35-lap forecast_demo fixture."""
    path = REPO_ROOT / "tests" / "fixtures" / "forecast_demo.json"
    with open(path) as f:
        data = json.load(f)
    laps_raw = data["session"]["laps"]
    session_id = data["session"]["summary"]["session_id"]
    laps = [LapFeatures.model_validate(lap) for lap in laps_raw]
    return session_id, laps


def _make_laps(
    n: int,
    *,
    harvest_base: float = 3.70,
    deploy_base: float = 3.76,
    harvest_amp: float = 0.05,
    deploy_amp: float = 0.04,
    late_pressure_lap: Optional[int] = None,
    lap_time_base: float = 109.8,
) -> list[LapFeatures]:
    """Generate a synthetic TORCS lap sequence of length n."""
    laps: list[LapFeatures] = []
    soc = 1.0
    for i in range(n):
        harvest = harvest_base + harvest_amp * math.sin(i * 0.4)
        deploy = deploy_base + deploy_amp * math.sin(i * 0.3 + 0.5)
        # Late-stint depletion: aggressive deployment from a certain lap
        if late_pressure_lap is not None and i >= late_pressure_lap:
            deploy += 0.10 + 0.02 * (i - late_pressure_lap) / max(n - late_pressure_lap, 1)
        soc_end = round(max(0.10, min(1.0, soc + (harvest - deploy) / 4.0)), 4)
        lap_time = lap_time_base + 1.2 * math.sin(i * 0.2)
        avg_speed = 83.2 - 0.3 * (i / max(n - 1, 1))
        laps.append(
            LapFeatures(
                lap_number=i + 1,
                soc_start=soc,
                soc_end=soc_end,
                harvest_mj=round(harvest, 4),
                deploy_mj=round(deploy, 4),
                lap_time=round(lap_time, 3),
                sector1_time=round(lap_time * 0.29, 3),
                sector2_time=round(lap_time * 0.27, 3),
                sector3_time=round(lap_time * 0.44, 3),
                avg_speed=round(avg_speed, 1),
                max_speed=round(avg_speed + 19.5, 1),
                override_uses=0,
                boost_uses=0,
                recharge_zones=[2],
                soc_source="derived",
            )
        )
        soc = soc_end
    return laps


def _build_sessions() -> list[tuple[str, list[LapFeatures], str]]:
    """Return (session_id, laps, description) for each session to evaluate."""
    sessions = []

    # Primary: 35-lap fixture (real TORCS SoC trajectory)
    try:
        sid, laps = _load_fixture_laps()
        sessions.append((sid, laps, "35-lap real TORCS fixture (primary control)"))
    except Exception as exc:
        print(f"[warn] forecast_demo fixture not available: {exc}")

    # Synthetic sessions for evaluation breadth (35 laps each)
    sessions.append((
        "synthetic_steady_decline",
        _make_laps(35, harvest_base=3.68, deploy_base=3.80),
        "35-lap synthetic: steady SoC decline",
    ))
    sessions.append((
        "synthetic_mixed_recovery",
        _make_laps(35, harvest_base=3.72, deploy_base=3.72, harvest_amp=0.12, deploy_amp=0.08),
        "35-lap synthetic: mixed harvest/deploy balance",
    ))
    sessions.append((
        "synthetic_late_pressure",
        _make_laps(35, harvest_base=3.70, deploy_base=3.74, late_pressure_lap=20),
        "35-lap synthetic: aggressive depletion from lap 20",
    ))

    return sessions


# ──────────────────────────────────────────────────────────────────────────────
# Model loading
# ──────────────────────────────────────────────────────────────────────────────

_PATCHTST_MODEL = None


def _load_patchtst():
    """Load PatchTST once and cache.

    Uses ignore_mismatched_sizes=True because checkpoint head was trained for
    prediction_length=96, num_input_channels=7 while OVERRIDE needs pred=5, ch=5.
    The head is re-initialized randomly; encoder weights are preserved.
    """
    global _PATCHTST_MODEL
    if _PATCHTST_MODEL is not None:
        return _PATCHTST_MODEL

    try:
        import torch
        from transformers import PatchTSTForPrediction  # type: ignore[import]

        # Seed the random initialization for reproducible results
        torch.manual_seed(42)
        model = PatchTSTForPrediction.from_pretrained(
            PATCHTST_REPO,
            context_length=CONTEXT_LENGTH,
            prediction_length=HORIZON,
            num_input_channels=CHANNELS,
            ignore_mismatched_sizes=True,
        )
        model.eval()
        _PATCHTST_MODEL = model
        return model
    except Exception as exc:
        return None, str(exc)


# ──────────────────────────────────────────────────────────────────────────────
# Input preparation
# ──────────────────────────────────────────────────────────────────────────────


def _build_input(laps: list[LapFeatures]):
    """Build a [CONTEXT_LENGTH, CHANNELS] float32 array from lap features.

    Pads with the first lap's values if len(laps) < CONTEXT_LENGTH.
    Uses min-max normalization per channel (matching core/forecasting.py).

    Returns (normalized_arr, mins, scales).
    """
    import numpy as np

    arr = [[lap.soc_end, lap.harvest_mj, lap.deploy_mj, lap.lap_time, lap.avg_speed]
           for lap in laps]

    # Pad to CONTEXT_LENGTH if fewer laps available
    while len(arr) < CONTEXT_LENGTH:
        arr.insert(0, arr[0])  # repeat earliest lap at front
    arr = arr[-CONTEXT_LENGTH:]  # take the last CONTEXT_LENGTH rows

    a = np.array(arr, dtype="float32")
    mins = a.min(axis=0, keepdims=True)
    maxs = a.max(axis=0, keepdims=True)
    scale = np.where(maxs - mins < 1e-8, 1.0, maxs - mins)
    return (a - mins) / scale, mins.squeeze(0), scale.squeeze(0)


# ──────────────────────────────────────────────────────────────────────────────
# Forecasters
# ──────────────────────────────────────────────────────────────────────────────


def _patchtst_forecast(laps: list[LapFeatures], model) -> Optional[list[float]]:
    """Run PatchTST on the lap window and return next-HORIZON soc_end predictions.

    Returns None on any failure.
    """
    try:
        import numpy as np
        import torch

        x_norm, mins, scales = _build_input(laps)
        inp = torch.tensor(x_norm, dtype=torch.float32).unsqueeze(0)  # [1, T, C]

        with torch.no_grad():
            out = model(past_values=inp)

        preds_norm = out.prediction_outputs[0].cpu().numpy()  # [horizon, channels]

        soc_scale = float(scales[0])
        soc_min = float(mins[0])
        return [
            float(max(0.0, min(1.0, preds_norm[i, 0] * soc_scale + soc_min)))
            for i in range(HORIZON)
        ]
    except Exception:
        return None


def _linear_trend_forecast(laps: list[LapFeatures]) -> list[float]:
    """Linear regression on soc_end; always returns a result."""
    soc = [lap.soc_end for lap in laps]
    n = len(soc)
    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(soc) / n
    denom = sum((x - x_mean) ** 2 for x in xs)
    slope = sum((xs[i] - x_mean) * (soc[i] - y_mean) for i in range(n)) / max(denom, 1e-10)
    intercept = y_mean - slope * x_mean
    return [max(0.0, min(1.0, intercept + slope * (n + k))) for k in range(1, HORIZON + 1)]


# ──────────────────────────────────────────────────────────────────────────────
# Metrics
# ──────────────────────────────────────────────────────────────────────────────


def _mae(predicted: list[float], actual: list[float]) -> float:
    n = min(len(predicted), len(actual))
    if n == 0:
        return float("nan")
    return sum(abs(p - a) for p, a in zip(predicted[:n], actual[:n])) / n


# ──────────────────────────────────────────────────────────────────────────────
# Evaluation
# ──────────────────────────────────────────────────────────────────────────────


def _evaluate_window(
    session_id: str,
    window_label: str,
    history: list[LapFeatures],
    actual_next: list[LapFeatures],
    model,
) -> dict:
    """Evaluate one (history → next 5 laps) window."""
    actual_soc = [lap.soc_end for lap in actual_next[:HORIZON]]

    # PatchTST
    patchtst_pred = _patchtst_forecast(history, model) if model is not None else None
    patchtst_available = patchtst_pred is not None
    patchtst_mae = _mae(patchtst_pred, actual_soc) if patchtst_pred else float("nan")

    # Linear-trend baseline
    baseline_pred = _linear_trend_forecast(history)
    baseline_mae = _mae(baseline_pred, actual_soc)

    # Winner
    if not patchtst_available or math.isnan(patchtst_mae):
        winner = "baseline (patchtst unavailable)"
    elif patchtst_mae < baseline_mae:
        winner = "patchtst"
    elif patchtst_mae > baseline_mae:
        winner = "baseline"
    else:
        winner = "tie"

    return {
        "session_id": session_id,
        "window_label": window_label,
        "lap_count": len(history),
        "history_window": f"laps {history[0].lap_number}–{history[-1].lap_number}",
        "patchtst_forecast_available": patchtst_available,
        "patchtst_predicted_soc": [round(v, 4) for v in patchtst_pred] if patchtst_pred else None,
        "baseline_predicted_soc": [round(v, 4) for v in baseline_pred],
        "actual_soc": [round(v, 4) for v in actual_soc],
        "patchtst_mae": round(patchtst_mae, 5) if not math.isnan(patchtst_mae) else None,
        "baseline_mae": round(baseline_mae, 5),
        "winner": winner,
    }


def evaluate(model) -> dict:
    """Run the full evaluation and return structured results."""
    sessions = _build_sessions()
    rows: list[dict] = []

    for session_id, all_laps, description in sessions:
        n = len(all_laps)

        # Window A: last 30 laps as history, next 5 as target
        # This is the canonical evaluation at the current 30-lap gate.
        if n >= 30 + HORIZON:
            history_a = all_laps[:30]
            actual_a = all_laps[30:30 + HORIZON]
            rows.append(_evaluate_window(session_id, "window_A_laps1-30", history_a, actual_a, model))

        # Window B (bonus, 35-lap sessions only): history = laps 5-34, target = laps 35-39
        # Only valid if session has 40+ laps; skipped for 35-lap sessions.
        if n >= 35 + HORIZON:
            history_b = all_laps[5:35]
            actual_b = all_laps[35:35 + HORIZON]
            rows.append(_evaluate_window(session_id, "window_B_laps6-35", history_b, actual_b, model))

    # Aggregate
    patchtst_maes = [r["patchtst_mae"] for r in rows if r["patchtst_mae"] is not None]
    baseline_maes = [r["baseline_mae"] for r in rows]
    patchtst_wins = sum(1 for r in rows if r["winner"] == "patchtst")
    total_windows = len(rows)
    patchtst_successes = sum(1 for r in rows if r["patchtst_forecast_available"])

    agg: dict = {
        "sessions_evaluated": len(sessions),
        "evaluation_windows": total_windows,
        "patchtst_successes": patchtst_successes,
        "patchtst_mean_mae": round(statistics.mean(patchtst_maes), 5) if patchtst_maes else None,
        "patchtst_median_mae": round(statistics.median(patchtst_maes), 5) if patchtst_maes else None,
        "baseline_mean_mae": round(statistics.mean(baseline_maes), 5) if baseline_maes else None,
        "baseline_median_mae": round(statistics.median(baseline_maes), 5) if baseline_maes else None,
        "patchtst_wins": patchtst_wins,
        "patchtst_win_rate": round(patchtst_wins / total_windows, 3) if total_windows else 0,
    }

    # Recommendation
    forecasting_stays_disabled = True  # Always True; no synthetic pass changes this
    if not patchtst_maes:
        rec_key = "patchtst_unavailable"
        rec_detail = "PatchTST could not run. Forecasting stays disabled."
    elif patchtst_wins == 0:
        rec_key = "forecasting_stays_disabled"
        rec_detail = (
            f"PatchTST did not beat the linear-trend baseline in any of "
            f"{total_windows} evaluation windows (win rate 0/{total_windows}). "
            "Root cause: PatchTST head is randomly re-initialized due to "
            "prediction_length/channel mismatch with the checkpoint. "
            "The model would need fine-tuning on OVERRIDE session data before "
            "it could provide useful forecasts. Forecasting stays disabled."
        )
    elif patchtst_wins < total_windows / 2:
        rec_key = "forecasting_stays_disabled"
        rec_detail = (
            f"PatchTST wins {patchtst_wins}/{total_windows} windows "
            f"(win rate {patchtst_wins/total_windows:.0%}). "
            "Insufficient evidence to justify enabling forecasting. "
            "Fine-tuning or tick-level representation required before next evaluation."
        )
    else:
        rec_key = "investigate_further"
        rec_detail = (
            f"PatchTST wins {patchtst_wins}/{total_windows} windows. "
            "Warrants further investigation before any product change. "
            "Verify on additional real sessions and check interval stability."
        )

    agg["recommendation_key"] = rec_key
    agg["recommendation_detail"] = rec_detail
    agg["forecasting_should_remain_disabled"] = forecasting_stays_disabled
    agg["data_constraints"] = (
        "No real TORCS sessions above 30 laps exist in data/sessions/ "
        "(all stored sessions have 1–4 laps). The forecast_demo fixture "
        "is real TORCS SoC data but was captured as a reproducible fixture, "
        "not a live session. Synthetic sessions add evaluation breadth only."
    )
    agg["model_constraint"] = (
        "PatchTST loaded with ignore_mismatched_sizes=True: the prediction "
        "head is randomly re-initialized (checkpoint trained for pred=96, "
        "ch=7; OVERRIDE needs pred=5, ch=5). Encoder weights are pretrained. "
        "Any MAE result reflects encoder features + random projection, not "
        "a fine-tuned model."
    )

    return {"eval_date": "2026-05-15", "model": PATCHTST_REPO, "windows": rows, "aggregate": agg}


# ──────────────────────────────────────────────────────────────────────────────
# Display
# ──────────────────────────────────────────────────────────────────────────────

_W = 100
_SEP = "─" * _W


def _print_results(result: dict) -> None:
    agg = result["aggregate"]
    print()
    print("OVERRIDE — PatchTST vs Linear-Trend MAE Evaluation")
    print("=" * _W)
    print()
    print("  MODEL CAVEATS")
    print("  " + "-" * 60)
    print(f"    {agg['model_constraint']}")
    print()
    print(f"    {agg['data_constraints']}")
    print()

    print("  PER-WINDOW RESULTS")
    print("  " + "-" * 60)
    hdr = f"  {'Session':<40} {'Window':<22} {'PatchTST MAE':>14} {'Baseline MAE':>14} {'Winner':<20}"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for r in result["windows"]:
        sid = r["session_id"][:38]
        win = r["window_label"][:20]
        p_mae = f"{r['patchtst_mae']:.5f}" if r["patchtst_mae"] is not None else "   N/A     "
        b_mae = f"{r['baseline_mae']:.5f}"
        winner = r["winner"]
        print(f"  {sid:<40} {win:<22} {p_mae:>14} {b_mae:>14}  {winner:<20}")

    print()
    print("  AGGREGATE")
    print("  " + "-" * 60)
    print(f"    Sessions evaluated    : {agg['sessions_evaluated']}")
    print(f"    Evaluation windows    : {agg['evaluation_windows']}")
    print(f"    PatchTST successes    : {agg['patchtst_successes']}")
    print(f"    PatchTST mean MAE     : {agg['patchtst_mean_mae']}")
    print(f"    PatchTST median MAE   : {agg['patchtst_median_mae']}")
    print(f"    Baseline mean MAE     : {agg['baseline_mean_mae']}")
    print(f"    Baseline median MAE   : {agg['baseline_median_mae']}")
    print(f"    PatchTST wins         : {agg['patchtst_wins']}/{agg['evaluation_windows']} "
          f"({agg['patchtst_win_rate']:.0%})")
    print()
    print("  RECOMMENDATION")
    print("  " + "-" * 60)
    print(f"    [{agg['recommendation_key']}]")
    print()
    for line in agg["recommendation_detail"].split(". "):
        if line.strip():
            print(f"    {line.strip()}.")
    print()
    print(f"    forecasting_should_remain_disabled: {agg['forecasting_should_remain_disabled']}")
    print()
    print("=" * _W)
    print()


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="PatchTST MAE evaluation")
    parser.add_argument("--save", action="store_true", help="Save JSON artifact")
    parser.add_argument("--json", action="store_true", help="Print raw JSON")
    args = parser.parse_args()

    print("[loading] PatchTST model…", end=" ", flush=True)
    model = _load_patchtst()
    if isinstance(model, tuple):
        # _load_patchtst returned (None, error_str)
        print(f"FAILED: {model[1]}")
        model = None
    else:
        print("OK" if model is not None else "UNAVAILABLE")

    result = evaluate(model)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        _print_results(result)

    if args.save:
        ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(ARTIFACT_PATH, "w") as f:
            json.dump(result, f, indent=2)
        print(f"  [saved] {ARTIFACT_PATH}")


if __name__ == "__main__":
    main()
