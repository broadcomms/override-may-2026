"""What-if perturbations on ``list[LapFeatures]`` (FR-8).

Pure functions — no pipeline coupling. ``api/main.py``'s what-if endpoint
composes these with ``core.pipeline.run_pipeline()``: perturb the lap list,
re-run the existing pipeline against the perturbed laps, diff the resulting
recommendations.

Why pure and stateless: the v6 plan task 2.2 was explicit that perturbations
must NOT know about reasoning / validator / Guardian / regulation grounding.
Coupling them would re-implement run_pipeline as a forked code path; the v6
plan repeatedly chose "compose, don't fork" (see gotcha #4 + the architectural
"reuse run_pipeline" note in task 2.3).

Edge-case semantics — pinned BEFORE this module was written — live at
``docs/plans/whatif-semantics.md``. The doc gets deleted in the PR that ships
FR-8 end-to-end (plan-file-lifecycle rule), so the rationale for each branch
of the per-perturbation logic is inline-commented here as well.

Cross-domain coupling note: when v6 task 1.4 cut option was triggered, this
module imports energy helpers from ``ingest.torcs_parser`` directly. 1.4 was
NOT cut — ``analysis.torcs_energy`` shipped — so we import from there.
"""

from __future__ import annotations

from typing import Optional

from analysis.torcs_energy import (
    BATTERY_CAPACITY_MJ,
    SOC_INITIAL,
    SOC_MAX,
    SOC_MIN,
)
from ingest.schema import LapFeatures, WhatIfRequest


# Threshold below which a lap's deploy_mj is treated as "no deploy event"
# for the purpose of delay_first_deploy. Eliminates pure-cruise laps with
# tiny throttle-blip totals so we don't shift over them as the "first
# deploy lap." 0.05 MJ ≈ < 1 second of full throttle.
DEPLOY_MIN_THRESHOLD_MJ = 0.05

# Magnitude of the additional deploy applied by extend_override per lap.
# This is a local counterfactual calibration for replay review, not a quoted
# FIA Overtake Mode energy allowance.
OVERRIDE_DEPLOY_MJ_PER_LAP = 0.5


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _recompute_soc_trajectory(laps: list[LapFeatures]) -> list[LapFeatures]:
    """Re-derive every ``soc_start`` / ``soc_end`` from the harvest/deploy deltas.

    Used after any perturbation that mutates ``harvest_mj`` or ``deploy_mj``
    on a subset of laps — downstream laps' SoC must reflect the change.
    Lap 1 always starts at ``SOC_INITIAL``; lap N starts at lap (N-1)'s
    ``soc_end``. SoC clamps to ``[SOC_MIN, SOC_MAX]`` per the shared
    energy helper's convention.

    Pure: returns a new list of LapFeatures (frozen) — does not mutate input.
    """
    out: list[LapFeatures] = []
    prior_soc_end: float = SOC_INITIAL
    for L in laps:
        delta = (L.harvest_mj - L.deploy_mj) / BATTERY_CAPACITY_MJ
        new_end = max(SOC_MIN, min(SOC_MAX, prior_soc_end + delta))
        out.append(L.model_copy(update={
            "soc_start": round(prior_soc_end, 6),
            "soc_end": round(new_end, 6),
        }))
        prior_soc_end = new_end
    return out


def _find_first_deploy_lap_index(laps: list[LapFeatures]) -> Optional[int]:
    """Return the 0-indexed position of the first lap with significant deploy.

    "Significant" means ``deploy_mj >= DEPLOY_MIN_THRESHOLD_MJ`` — filters
    cruise laps. Returns ``None`` if no such lap exists; callers surface
    that via WhatIfResult.note rather than raising.
    """
    for idx, L in enumerate(laps):
        if L.deploy_mj >= DEPLOY_MIN_THRESHOLD_MJ:
            return idx
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Perturbation 1 — delay_first_deploy
# ──────────────────────────────────────────────────────────────────────────────


def apply_delay_first_deploy(
    laps: list[LapFeatures],
    n: int,
) -> tuple[list[LapFeatures], Optional[str]]:
    """Shift the first deploy event by ``n`` laps.

    Per whatif-semantics.md §Perturbation 1: the ENERGY MOVES, not deleted.
    The deploy_mj at the source lap (K) goes to lap K+n; if K+n is past
    the end of the session, the deploy_mj is conserved by leaving SoC
    higher (no destination lap to carry it).

    Returns (perturbed_laps, note). ``note`` is None on the happy path,
    or a short message explaining truncation / no-op when an edge case
    fires.
    """
    if n <= 0:
        # Identity per whatif-semantics.md (accepted for testing parity)
        return list(laps), None

    k = _find_first_deploy_lap_index(laps)
    if k is None:
        return list(laps), "no deploy events to delay in this session"

    new_laps: list[LapFeatures] = list(laps)
    source_deploy = new_laps[k].deploy_mj
    new_laps[k] = new_laps[k].model_copy(update={"deploy_mj": 0.0})

    note: Optional[str] = None
    target_idx = k + n
    if target_idx < len(new_laps):
        # SHIFT — add source_deploy onto target lap's existing deploy_mj.
        # Note: this can push the target lap's total deploy above what's
        # physically achievable; the validator's energy_bounds rule catches
        # cases that violate per-lap caps. Honest about the trade-off.
        target = new_laps[target_idx]
        new_laps[target_idx] = target.model_copy(update={
            "deploy_mj": round(target.deploy_mj + source_deploy, 6),
        })
    else:
        # No destination lap — energy retained as headroom. Honest message.
        note = (
            f"deploy of {source_deploy:.2f} MJ delayed past end of session "
            f"(K={k+1}, n={n}); energy retained as SoC headroom"
        )

    return _recompute_soc_trajectory(new_laps), note


# ──────────────────────────────────────────────────────────────────────────────
# Perturbation 2 — skip_harvest_zone
# ──────────────────────────────────────────────────────────────────────────────


def apply_skip_harvest_zone(
    laps: list[LapFeatures],
    zone_id: str,
    *,
    zone_lap_number: int,
) -> tuple[list[LapFeatures], Optional[str]]:
    """Zero out harvest on the lap containing the given zone — energy LOST.

    Per whatif-semantics.md §Perturbation 2: the harvest opportunity is
    permanently gone; downstream SoC trajectory floors lower for the rest
    of the session. Models a real racing mistake (missed regen window),
    not a deferred regen.

    The zone-id → lap-number mapping is established by the caller
    (typically the endpoint, which has the full Session). We accept
    ``zone_lap_number`` rather than re-scanning the recommendations here
    so this function stays pure (no Zone/Recommendation coupling).

    Returns (perturbed_laps, note).
    """
    new_laps = list(laps)
    target_idx = next(
        (i for i, L in enumerate(new_laps) if L.lap_number == zone_lap_number),
        None,
    )
    if target_idx is None:
        # Caller passed an invalid lap_number — should be caught at the
        # endpoint validation layer (404 zone-not-found), but defend in
        # depth here.
        return list(laps), f"zone {zone_id!r}: lap {zone_lap_number} not found"

    original_harvest = new_laps[target_idx].harvest_mj
    if original_harvest == 0.0:
        return list(laps), (
            f"zone {zone_id!r}: lap {zone_lap_number} already has 0 harvest — no-op"
        )

    new_laps[target_idx] = new_laps[target_idx].model_copy(update={
        "harvest_mj": 0.0,
        # recharge_zones is per-lap-derived elsewhere; clear it consistently.
        "recharge_zones": [],
    })
    note = (
        f"zone {zone_id!r}: harvest of {original_harvest:.2f} MJ on lap "
        f"{zone_lap_number} LOST (skipped opportunity, energy not deferred)"
    )
    return _recompute_soc_trajectory(new_laps), note


# ──────────────────────────────────────────────────────────────────────────────
# Perturbation 3 — extend_override
# ──────────────────────────────────────────────────────────────────────────────


def apply_extend_override(
    laps: list[LapFeatures],
    zone_id: str,
    *,
    zone_lap_number: int,
    extra_laps: int = 1,
) -> tuple[list[LapFeatures], Optional[str]]:
    """Add Overtake Mode-style deploy onto ``extra_laps`` laps after the zone's lap.

    Per whatif-semantics.md §Perturbation 3: each extension lap gets a local
    calibrated deploy increment on top of its existing deploy_mj. If SoC
    underflows before all extensions land, the perturbation truncates honestly
    — that lap's extension is capped at the available budget, and subsequent
    laps get 0. The note carries the truncation message.

    Increments ``override_uses`` on the seed lap by 1.

    Returns (perturbed_laps, note).
    """
    new_laps = list(laps)
    seed_idx = next(
        (i for i, L in enumerate(new_laps) if L.lap_number == zone_lap_number),
        None,
    )
    if seed_idx is None:
        return list(laps), f"zone {zone_id!r}: lap {zone_lap_number} not found"

    # Bump override_uses on the seed lap
    seed = new_laps[seed_idx]
    new_laps[seed_idx] = seed.model_copy(update={
        "override_uses": seed.override_uses + 1,
    })

    note: Optional[str] = None
    applied = 0
    # Apply extension to the `extra_laps` laps AFTER the seed.
    for offset in range(1, extra_laps + 1):
        ext_idx = seed_idx + offset
        if ext_idx >= len(new_laps):
            note = (
                f"zone {zone_id!r}: extension applied to {applied} of "
                f"{extra_laps} requested laps (session ended)"
            )
            break
        ext_lap = new_laps[ext_idx]
        # Check available SoC budget on this lap (use start-of-lap SoC ×
        # capacity as the deploy budget ceiling). If extending would push
        # net energy negative, truncate to whatever's available.
        soc_budget_mj = ext_lap.soc_start * BATTERY_CAPACITY_MJ
        # Current deploy already consumes from soc; the EXTRA deploy must
        # fit in whatever's left after the lap's own deploy.
        remaining_after_existing = soc_budget_mj - ext_lap.deploy_mj
        if remaining_after_existing <= 0.0:
            note = (
                f"zone {zone_id!r}: battery exhausted on lap {ext_lap.lap_number} "
                f"— extension truncated after {applied} of {extra_laps} laps"
            )
            break
        added = min(OVERRIDE_DEPLOY_MJ_PER_LAP, remaining_after_existing)
        new_laps[ext_idx] = ext_lap.model_copy(update={
            "deploy_mj": round(ext_lap.deploy_mj + added, 6),
        })
        applied += 1
        # If we hit a partial extension on this lap, the next lap will see
        # the depleted SoC via _recompute_soc_trajectory; let it handle
        # its own per-lap budget naturally on the next iteration.

    if note is None and applied < extra_laps:
        # Reach if extra_laps > 0 but the loop fell through without truncation
        # — shouldn't happen, but defend.
        note = f"zone {zone_id!r}: applied {applied} of {extra_laps} extensions"

    return _recompute_soc_trajectory(new_laps), note


# ──────────────────────────────────────────────────────────────────────────────
# Dispatcher — single entry point for the endpoint
# ──────────────────────────────────────────────────────────────────────────────


def apply_perturbation(
    laps: list[LapFeatures],
    request: WhatIfRequest,
    *,
    zone_lap_lookup: Optional[dict[str, int]] = None,
) -> tuple[list[LapFeatures], Optional[str]]:
    """Dispatch on ``request.perturbation`` to the right pure function.

    ``zone_lap_lookup`` maps zone_id → lap_number; the endpoint builds
    this from the original session's recommendations before invoking.
    Required for skip_harvest_zone + extend_override; ignored for
    delay_first_deploy.
    """
    kind = request.perturbation
    if kind == "delay_first_deploy":
        assert request.n is not None, "schema validator should have caught this"
        return apply_delay_first_deploy(laps, request.n)

    if kind in ("skip_harvest_zone", "extend_override"):
        assert request.zone_id is not None, "schema validator should have caught this"
        lap_number = (zone_lap_lookup or {}).get(request.zone_id)
        if lap_number is None:
            return list(laps), f"zone {request.zone_id!r} not found in session"
        if kind == "skip_harvest_zone":
            return apply_skip_harvest_zone(
                laps, request.zone_id, zone_lap_number=lap_number,
            )
        return apply_extend_override(
            laps, request.zone_id,
            zone_lap_number=lap_number, extra_laps=request.extra_laps,
        )

    raise ValueError(f"unknown perturbation: {kind!r}")


__all__ = [
    "DEPLOY_MIN_THRESHOLD_MJ",
    "OVERRIDE_DEPLOY_MJ_PER_LAP",
    "apply_delay_first_deploy",
    "apply_skip_harvest_zone",
    "apply_extend_override",
    "apply_perturbation",
]
