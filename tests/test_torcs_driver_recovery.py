from RaceYourCode.gym_torcs.torcs_jm_par import (
    DEFAULT_MAX_STEPS,
    STEPS_PER_LAP_BUDGET,
    apply_recovery,
    calculate_throttle,
    derive_max_steps,
)


def test_calculate_throttle_keeps_positive_launch_drive_when_speed_is_negative() -> None:
    server_state = {"speedX": -0.5}
    driver_action = {"steer": 0.0, "accel": 0.0}

    accel = calculate_throttle(server_state, driver_action, target_speed=85)

    assert accel == 1.0


def test_apply_recovery_keeps_forward_gear_during_clean_launch_backroll() -> None:
    server_state = {
        "curLapTime": 3.0,
        "speedX": -3.0,
        "trackPos": 0.1,
        "angle": 0.2,
        "damage": 0.0,
        "stucktimer": 0.0,
    }
    driver_action = {"gear": 1, "accel": 0.0, "brake": 0.0, "steer": 0.0}

    engaged = apply_recovery(server_state, driver_action)

    assert engaged is True
    assert driver_action["gear"] == 1
    assert driver_action["accel"] == 1.0
    assert driver_action["brake"] == 0.0


def test_apply_recovery_uses_reverse_only_after_damage_stop() -> None:
    server_state = {
        "curLapTime": 30.0,
        "speedX": -0.2,
        "trackPos": 0.95,
        "angle": 1.2,
        "damage": 123.0,
        "stucktimer": 0.0,
    }
    driver_action = {"gear": 1, "accel": 0.0, "brake": 0.0, "steer": 0.0}

    engaged = apply_recovery(server_state, driver_action)

    assert engaged is True
    assert driver_action["gear"] == -1
    assert driver_action["accel"] == 0.2


def test_derive_max_steps_scales_with_requested_laps() -> None:
    assert derive_max_steps(None) == DEFAULT_MAX_STEPS
    assert derive_max_steps("0") == DEFAULT_MAX_STEPS
    assert derive_max_steps("75") == 75 * STEPS_PER_LAP_BUDGET
