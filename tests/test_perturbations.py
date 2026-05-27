"""Tests for analysis.perturbations (FR-8 task 2.2).

Pure functions over ``list[LapFeatures]`` — no pipeline, no network. The
edge-case semantics tested here mirror the spec table in
``docs/plans/whatif-semantics.md`` (deleted in the FR-8 ship PR per
plan-file-lifecycle).
"""

from __future__ import annotations

from analysis.perturbations import (
    DEPLOY_MIN_THRESHOLD_MJ,
    OVERRIDE_DEPLOY_MJ_PER_LAP,
    apply_delay_first_deploy,
    apply_extend_override,
    apply_perturbation,
    apply_skip_harvest_zone,
)
from analysis.torcs_energy import BATTERY_CAPACITY_MJ
from ingest.schema import LapFeatures, WhatIfRequest


# ──────────────────────────────────────────────────────────────────────────────
# Fixture helpers — multi-lap synthetic LapFeatures
# ──────────────────────────────────────────────────────────────────────────────


def _lap(
    n: int,
    *,
    harvest: float = 1.0,
    deploy: float = 1.5,
    soc_start: float = 1.0,
    soc_end: float = 0.9,
    override_uses: int = 0,
    recharge_zones: list[int] | None = None,
) -> LapFeatures:
    return LapFeatures(
        lap_number=n,
        soc_start=soc_start,
        soc_end=soc_end,
        harvest_mj=harvest,
        deploy_mj=deploy,
        lap_time=85.0,
        sector1_time=28.0,
        sector2_time=29.0,
        sector3_time=28.0,
        avg_speed=210.0,
        max_speed=320.0,
        override_uses=override_uses,
        boost_uses=0,
        recharge_zones=recharge_zones if recharge_zones is not None else [2],
        soc_source="derived",
    )


def _five_lap_session() -> list[LapFeatures]:
    """A clean five-lap synthetic session where every lap has a real deploy
    event (≥ DEPLOY_MIN_THRESHOLD_MJ). Lets us test shift / skip / extend
    without bumping into the 1-lap truncation that real torcs_baseline.jsonl
    hits."""
    return [
        _lap(1, harvest=1.0, deploy=1.5),
        _lap(2, harvest=1.2, deploy=1.4),
        _lap(3, harvest=0.8, deploy=1.8),
        _lap(4, harvest=1.1, deploy=1.3),
        _lap(5, harvest=0.9, deploy=1.6),
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Perturbation 1 — delay_first_deploy
# ──────────────────────────────────────────────────────────────────────────────


def test_delay_first_deploy_shifts_when_destination_lap_exists():
    laps = _five_lap_session()
    perturbed, note = apply_delay_first_deploy(laps, n=2)
    # source lap (1) is zeroed
    assert perturbed[0].deploy_mj == 0.0
    # destination lap (1+2=3) absorbs the shifted deploy on top of its own
    assert perturbed[2].deploy_mj == round(0.8 * 0 + 1.8 + 1.5, 6)
    # Lap 2 untouched
    assert perturbed[1].deploy_mj == 1.4
    # Honest happy-path: no note
    assert note is None


def test_delay_first_deploy_energy_conserved_when_within_session():
    laps = _five_lap_session()
    perturbed, _ = apply_delay_first_deploy(laps, n=1)
    original_total = sum(L.deploy_mj for L in laps)
    perturbed_total = sum(L.deploy_mj for L in perturbed)
    # SHIFT preserves session-level total (whatif-semantics.md §Common conventions)
    assert abs(original_total - perturbed_total) < 1e-9


def test_delay_first_deploy_truncates_past_end_of_session_with_note():
    laps = _five_lap_session()
    perturbed, note = apply_delay_first_deploy(laps, n=10)  # past end
    assert perturbed[0].deploy_mj == 0.0
    # No destination lap exists, so the energy is RETAINED, not shifted
    assert note is not None and "retained as SoC headroom" in note
    # All other deploys untouched
    for original, after in zip(laps[1:], perturbed[1:]):
        assert original.deploy_mj == after.deploy_mj


def test_delay_first_deploy_no_op_when_no_deploy_events():
    # Session of pure cruise — every deploy below threshold
    laps = [_lap(i, harvest=0.5, deploy=0.0) for i in range(1, 4)]
    perturbed, note = apply_delay_first_deploy(laps, n=2)
    assert note == "no deploy events to delay in this session"
    # SoC recompute still ran but deploys all zero → laps unchanged on deploy
    assert all(L.deploy_mj == 0.0 for L in perturbed)


def test_delay_first_deploy_n_zero_is_identity():
    laps = _five_lap_session()
    perturbed, note = apply_delay_first_deploy(laps, n=0)
    assert note is None
    for original, after in zip(laps, perturbed):
        assert original.deploy_mj == after.deploy_mj
        assert original.harvest_mj == after.harvest_mj


def test_delay_first_deploy_recomputes_soc_downstream():
    """After shifting deploy, soc_end on the source lap rises and on the
    destination lap falls — the trajectory recompute is wired."""
    laps = _five_lap_session()
    perturbed, _ = apply_delay_first_deploy(laps, n=2)
    # Source lap (1): no deploy → soc_end rises vs original
    assert perturbed[0].soc_end > laps[0].soc_end
    # Destination lap (3): doubled deploy → soc_end falls
    assert perturbed[2].soc_end < laps[2].soc_end


# ──────────────────────────────────────────────────────────────────────────────
# Perturbation 2 — skip_harvest_zone
# ──────────────────────────────────────────────────────────────────────────────


def test_skip_harvest_zone_zeros_target_lap_harvest():
    laps = _five_lap_session()
    perturbed, note = apply_skip_harvest_zone(
        laps, zone_id="z_lroi_l3_s2", zone_lap_number=3,
    )
    # Target lap's harvest zeroed; recharge_zones cleared
    assert perturbed[2].harvest_mj == 0.0
    assert perturbed[2].recharge_zones == []
    # Other laps' harvest untouched
    assert perturbed[0].harvest_mj == 1.0
    assert perturbed[4].harvest_mj == 0.9
    # Note explains the LOST not deferred fate
    assert note is not None and "LOST" in note


def test_skip_harvest_zone_energy_lost_not_deferred():
    """Per whatif-semantics.md §Perturbation 2: total session harvest drops
    by the skipped lap's value. Not redistributed."""
    laps = _five_lap_session()
    perturbed, _ = apply_skip_harvest_zone(
        laps, zone_id="z_test", zone_lap_number=3,
    )
    original_total = sum(L.harvest_mj for L in laps)
    perturbed_total = sum(L.harvest_mj for L in perturbed)
    assert abs((original_total - 0.8) - perturbed_total) < 1e-9


def test_skip_harvest_zone_downstream_soc_floors_lower():
    laps = _five_lap_session()
    perturbed, _ = apply_skip_harvest_zone(
        laps, zone_id="z_test", zone_lap_number=2,
    )
    # Laps 2..5 should all see lower (or equal) soc_end vs original
    for i in range(1, 5):
        assert perturbed[i].soc_end <= laps[i].soc_end


def test_skip_harvest_zone_unknown_lap_returns_no_op_with_note():
    laps = _five_lap_session()
    perturbed, note = apply_skip_harvest_zone(
        laps, zone_id="z_ghost", zone_lap_number=99,
    )
    assert note is not None and "not found" in note
    # No change to the laps
    for original, after in zip(laps, perturbed):
        assert original.harvest_mj == after.harvest_mj


def test_skip_harvest_zone_already_zero_is_no_op():
    laps = [
        _lap(1, harvest=1.0, deploy=1.5),
        _lap(2, harvest=0.0, deploy=1.4),  # already zero
    ]
    perturbed, note = apply_skip_harvest_zone(
        laps, zone_id="z_zero", zone_lap_number=2,
    )
    assert note is not None and "no-op" in note


# ──────────────────────────────────────────────────────────────────────────────
# Perturbation 3 — extend_override
# ──────────────────────────────────────────────────────────────────────────────


def test_extend_override_adds_deploy_to_next_lap_default():
    laps = _five_lap_session()
    perturbed, note = apply_extend_override(
        laps, zone_id="z_uo_l2_s1", zone_lap_number=2, extra_laps=1,
    )
    # Lap 3 gets the configured Overtake-style deploy increment.
    assert perturbed[2].deploy_mj == round(1.8 + OVERRIDE_DEPLOY_MJ_PER_LAP, 6)
    # Seed lap 2's override_uses bumped
    assert perturbed[1].override_uses == 1
    # Other deploys untouched
    assert perturbed[0].deploy_mj == 1.5
    assert perturbed[3].deploy_mj == 1.3


def test_extend_override_multi_lap_extends_all_when_budget_allows():
    """Three-lap extension on a session where each subsequent lap has
    enough SoC budget for the full configured extension."""
    # Build a session where lap 1 has high SoC, so lap 2/3/4 inherit
    # plenty of headroom even after the extension stacking.
    laps = [
        _lap(1, harvest=0.5, deploy=0.5, soc_start=1.0, soc_end=1.0),
        _lap(2, harvest=0.5, deploy=0.5, soc_start=1.0, soc_end=1.0),
        _lap(3, harvest=0.5, deploy=0.5, soc_start=1.0, soc_end=1.0),
        _lap(4, harvest=0.5, deploy=0.5, soc_start=1.0, soc_end=1.0),
    ]
    perturbed, note = apply_extend_override(
        laps, zone_id="z_test", zone_lap_number=1, extra_laps=3,
    )
    # Laps 2/3/4 each get the configured deploy increment.
    for i in (1, 2, 3):
        assert perturbed[i].deploy_mj == round(0.5 + OVERRIDE_DEPLOY_MJ_PER_LAP, 6)


def test_extend_override_truncates_when_session_ends():
    laps = _five_lap_session()
    # Seed on lap 4, request 3 extra laps — only lap 5 exists
    perturbed, note = apply_extend_override(
        laps, zone_id="z_test", zone_lap_number=4, extra_laps=3,
    )
    assert note is not None and "session ended" in note
    # Lap 5 got the extension; nothing further to extend
    assert perturbed[4].deploy_mj == round(1.6 + OVERRIDE_DEPLOY_MJ_PER_LAP, 6)


def test_extend_override_truncates_when_battery_exhausted():
    # Battery empty entering the extension target
    laps = [
        _lap(1, harvest=0.5, deploy=0.5, soc_start=1.0, soc_end=0.5),
        # Lap 2: very low soc_start so the configured increment would underflow
        _lap(2, harvest=0.0, deploy=BATTERY_CAPACITY_MJ * 0.05, soc_start=0.05, soc_end=0.0),
    ]
    perturbed, note = apply_extend_override(
        laps, zone_id="z_test", zone_lap_number=1, extra_laps=1,
    )
    # Either capped or hit the "battery exhausted" branch
    assert note is not None
    # Extension never increases deploy past what the available budget allows
    assert perturbed[1].deploy_mj <= BATTERY_CAPACITY_MJ * 0.05 + OVERRIDE_DEPLOY_MJ_PER_LAP + 1e-9


def test_extend_override_unknown_lap_returns_no_op():
    laps = _five_lap_session()
    perturbed, note = apply_extend_override(
        laps, zone_id="z_ghost", zone_lap_number=99,
    )
    assert note is not None and "not found" in note


# ──────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ──────────────────────────────────────────────────────────────────────────────


def test_dispatcher_routes_delay_first_deploy():
    laps = _five_lap_session()
    req = WhatIfRequest(perturbation="delay_first_deploy", n=1)
    perturbed, _ = apply_perturbation(laps, req)
    assert perturbed[0].deploy_mj == 0.0


def test_dispatcher_routes_skip_harvest_zone_with_lookup():
    laps = _five_lap_session()
    req = WhatIfRequest(perturbation="skip_harvest_zone", zone_id="z_l3_s2")
    perturbed, _ = apply_perturbation(
        laps, req, zone_lap_lookup={"z_l3_s2": 3},
    )
    assert perturbed[2].harvest_mj == 0.0


def test_dispatcher_routes_extend_override_with_lookup():
    laps = _five_lap_session()
    req = WhatIfRequest(
        perturbation="extend_override", zone_id="z_uo_l2_s1", extra_laps=1,
    )
    perturbed, _ = apply_perturbation(
        laps, req, zone_lap_lookup={"z_uo_l2_s1": 2},
    )
    assert perturbed[1].override_uses == 1


def test_dispatcher_handles_missing_zone_lookup_gracefully():
    laps = _five_lap_session()
    req = WhatIfRequest(perturbation="skip_harvest_zone", zone_id="z_ghost")
    perturbed, note = apply_perturbation(laps, req, zone_lap_lookup={})
    assert note is not None and "not found" in note


# ──────────────────────────────────────────────────────────────────────────────
# Schema validators (cross-field per whatif-semantics.md)
# ──────────────────────────────────────────────────────────────────────────────


def test_whatifrequest_rejects_delay_first_deploy_without_n():
    import pytest
    with pytest.raises(ValueError, match="requires `n`"):
        WhatIfRequest(perturbation="delay_first_deploy")


def test_whatifrequest_rejects_skip_harvest_zone_without_zone_id():
    import pytest
    with pytest.raises(ValueError, match="requires `zone_id`"):
        WhatIfRequest(perturbation="skip_harvest_zone")


def test_whatifrequest_rejects_extend_override_without_zone_id():
    import pytest
    with pytest.raises(ValueError, match="requires `zone_id`"):
        WhatIfRequest(perturbation="extend_override")


def test_whatifrequest_cache_key_deterministic_across_runs():
    """Schema produces a stable JSON dump for the same fields — the
    sha256 cache key (computed in api/main.py:whatif handler) is stable
    across runs. Test the underlying invariant: model_dump_json output
    matches across reconstruction."""
    a = WhatIfRequest(perturbation="delay_first_deploy", n=2)
    b = WhatIfRequest(perturbation="delay_first_deploy", n=2)
    assert a.model_dump_json() == b.model_dump_json()
