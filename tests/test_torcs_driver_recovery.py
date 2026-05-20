from RaceYourCode.gym_torcs.torcs_jm_par import (
    DEFAULT_MAX_STEPS,
    STEPS_PER_LAP_BUDGET,
    _stabilize_steering_command,
    apply_recovery,
    calculate_steering,
    calculate_throttle,
    coordinate_longitudinal_controls,
    drive_modular,
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


def test_calculate_steering_avoids_full_lock_for_moderate_heading_error() -> None:
    server_state = {
        "angle": 0.16,
        "trackPos": -0.09,
        "speedX": 46.0,
        "track": [0.0] * 8 + [87.0, 100.0, 82.0] + [0.0] * 8,
    }

    steer = calculate_steering(server_state, previous_steer=0.0)

    assert 0.0 < steer < 1.0


def test_calculate_steering_rate_limits_full_sign_flip() -> None:
    server_state = {
        "angle": -0.18,
        "trackPos": -0.08,
        "speedX": 44.0,
        "track": [0.0] * 8 + [87.0, 100.0, 77.0] + [0.0] * 8,
    }

    steer = calculate_steering(server_state, previous_steer=0.7)

    assert -0.2 < steer < 0.7


def test_stabilize_steering_holds_tiny_neutral_sign_reversal() -> None:
    steer = _stabilize_steering_command(raw_steer=-0.08, previous_steer=0.003, speed_kmh=70.0)

    assert 0.0 <= steer < 0.003


def test_stabilize_steering_still_allows_large_reversal_to_cross_zero() -> None:
    steer = _stabilize_steering_command(raw_steer=-0.45, previous_steer=0.05, speed_kmh=70.0)

    assert steer < 0.0


def test_calculate_steering_damps_lateral_motion_in_same_direction() -> None:
    baseline_state = {
        "angle": 0.14,
        "trackPos": 0.02,
        "speedX": 57.0,
        "speedY": 0.0,
        "track": [0.0] * 8 + [79.0, 92.0, 74.0] + [0.0] * 8,
    }
    sliding_state = dict(baseline_state, speedY=1.4)

    baseline_steer = calculate_steering(baseline_state, previous_steer=0.0)
    damped_steer = calculate_steering(sliding_state, previous_steer=0.0)

    assert damped_steer < baseline_steer


def test_calculate_steering_adds_extra_cross_track_help_on_uphill_crest() -> None:
    base_state = {
        "angle": 0.025,
        "trackPos": -0.31,
        "speedX": 56.0,
        "speedY": 0.75,
        "pitch": 0.0,
        "track": [0.0] * 8 + [24.7, 24.1, 23.4] + [0.0] * 8,
    }
    crest_state = dict(base_state, pitch=0.08)

    base_steer = calculate_steering(base_state, previous_steer=0.0)
    crest_steer = calculate_steering(crest_state, previous_steer=0.0)

    assert crest_steer > base_steer


def test_calculate_steering_keeps_recovery_bias_while_far_off_line() -> None:
    server_state = {
        "angle": -0.05,
        "trackPos": -0.68,
        "speedX": 28.0,
        "speedY": 0.5,
        "pitch": 0.14,
        "track": [0.0] * 19,
    }

    steer = calculate_steering(server_state, previous_steer=0.1)

    assert steer > 0.12


def test_coordinate_longitudinal_controls_cuts_throttle_when_braking() -> None:
    server_state = {"speedX": 31.0, "speedY": 1.2, "trackPos": 0.42}
    driver_action = {"steer": 0.41, "accel": 0.3, "brake": 0.4}

    accel, brake = coordinate_longitudinal_controls(server_state, driver_action, target_speed=35.0)

    assert accel == 0.0
    assert brake == 0.4


def test_coordinate_longitudinal_controls_holds_throttle_until_corner_settles() -> None:
    server_state = {"speedX": 39.0, "speedY": 1.4, "trackPos": -0.52}
    driver_action = {"steer": 0.36, "accel": 0.7, "brake": 0.0}

    accel, brake = coordinate_longitudinal_controls(server_state, driver_action, target_speed=36.0)

    assert accel == 0.0
    assert brake == 0.0


def test_coordinate_longitudinal_controls_holds_throttle_during_large_recovery_even_after_steer_unwinds() -> None:
    server_state = {"speedX": 28.0, "speedY": 0.82, "trackPos": -0.74, "angle": 0.03}
    driver_action = {"steer": 0.18, "accel": 0.9, "brake": 0.0}

    accel, brake = coordinate_longitudinal_controls(server_state, driver_action, target_speed=36.0)

    assert accel == 0.0
    assert brake == 0.0


def test_coordinate_longitudinal_controls_applies_light_brake_during_fast_large_slide() -> None:
    server_state = {"speedX": 44.0, "speedY": 1.7, "trackPos": -0.48, "angle": 0.15}
    driver_action = {"steer": 0.33, "accel": 0.7, "brake": 0.0}

    accel, brake = coordinate_longitudinal_controls(server_state, driver_action, target_speed=36.0)

    assert accel == 0.0
    assert brake == 0.25


def test_coordinate_longitudinal_controls_keeps_coasting_while_still_far_off_line_at_low_speed() -> None:
    server_state = {"speedX": 26.0, "speedY": 0.02, "trackPos": -0.59, "angle": -0.04}
    driver_action = {"steer": 0.08, "accel": 0.9, "brake": 0.0}

    accel, brake = coordinate_longitudinal_controls(server_state, driver_action, target_speed=36.0)

    assert accel == 0.0
    assert brake == 0.0


def test_coordinate_longitudinal_controls_holds_throttle_for_large_yaw_recovery_before_track_pos_reaches_old_threshold() -> None:
    server_state = {"speedX": 32.0, "speedY": 2.2, "trackPos": -0.33, "angle": -0.31}
    driver_action = {"steer": -0.44, "accel": 0.9, "brake": 0.0}

    accel, brake = coordinate_longitudinal_controls(server_state, driver_action, target_speed=36.0)

    assert accel == 0.0
    assert brake == 0.0


def test_drive_modular_does_not_command_accel_and_brake_together() -> None:
    class _State:
        def __init__(self, data):
            self.d = data

    class _Controller:
        def __init__(self, server_state, driver_action):
            self.S = _State(server_state)
            self.R = _State(driver_action)

    server_state = {
        "angle": 0.15,
        "trackPos": -0.62,
        "speedX": 34.0,
        "speedY": 1.5,
        "wheelSpinVel": [10.0, 10.0, 10.0, 10.0],
        "track": [0.0] * 8 + [42.0, 60.0, 54.0] + [0.0] * 8,
    }
    driver_action = {"steer": 0.0, "accel": 0.3, "brake": 0.0, "gear": 1}

    controller = _Controller(server_state, driver_action)
    drive_modular(controller)

    assert not (controller.R.d["accel"] > 0.0 and controller.R.d["brake"] > 0.0)
