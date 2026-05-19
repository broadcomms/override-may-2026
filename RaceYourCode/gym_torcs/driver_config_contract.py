from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class SpeedConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    target_speed_kmh: float = Field(ge=0.0)
    min_target_speed_kmh: float = Field(ge=0.0)
    centre_clamp_m: float = Field(gt=0.0)
    centre_factor: float = Field(ge=0.0)
    curvature_clamp: float = Field(ge=0.0)
    curvature_penalty: float = Field(ge=0.0)
    visible_road_threshold_m: float = Field(ge=0.0)
    visible_road_penalty: float = Field(ge=0.0)

    @model_validator(mode="after")
    def _validate_bounds(self) -> "SpeedConfig":
        if self.min_target_speed_kmh > self.target_speed_kmh:
            raise ValueError("min_target_speed_kmh must be <= target_speed_kmh")
        return self


class SteeringConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    steer_gain: float
    centering_gain: float
    track_sensor_gain: float
    lateral_speed_damping_gain: float = Field(default=0.10, ge=0.0)
    crest_centering_gain: float = Field(default=0.10, ge=0.0)


class ThrottleConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    steer_speed_penalty_kmh: float = Field(ge=0.0)
    accel_ramp_up: float = Field(ge=0.0)
    accel_decay: float = Field(ge=0.0)
    low_speed_boost_cutoff_kmh: float
    low_speed_boost_denominator_offset: float = Field(gt=0.0)


class BrakingConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    overspeed_margin_kmh: float = Field(ge=0.0)
    overspeed_divisor_kmh: float = Field(gt=0.0)
    overspeed_cap: float = Field(ge=0.0, le=1.0)
    angle_threshold_rad: float = Field(ge=0.0, le=3.2)
    angle_min_speed_kmh: float = Field(ge=0.0)
    angle_brake_force: float = Field(ge=0.0, le=1.0)
    track_pos_threshold: float = Field(ge=0.0)
    track_pos_min_speed_kmh: float = Field(ge=0.0)
    track_pos_brake_force: float = Field(ge=0.0, le=1.0)


class GearConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    gear_speeds_kmh: list[float] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def _validate_ascending(self) -> "GearConfig":
        if any(b <= a for a, b in zip(self.gear_speeds_kmh, self.gear_speeds_kmh[1:])):
            raise ValueError("gear_speeds_kmh must be strictly ascending")
        return self


class TractionConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    slip_threshold: float = Field(ge=0.0)
    accel_cut: float = Field(ge=0.0)


class LaunchGuardConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    duration_s: float = Field(ge=0.0)
    track_pos_limit: float = Field(ge=0.0)
    angle_limit_rad: float = Field(ge=0.0, le=3.2)
    steer_angle_gain: float
    steer_track_pos_gain: float
    steer_clip: float = Field(ge=0.0, le=1.0)


class RecoveryConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    offtrack_trackpos_threshold: float = Field(ge=0.0)
    offtrack_angle_threshold_rad: float = Field(ge=0.0, le=3.2)
    angle_recovery_speed_cap_kmh: float = Field(ge=0.0)
    stuck_time_threshold_s: float = Field(ge=0.0)
    recovery_speed_kmh: float = Field(ge=0.0)
    steer_back_angle_gain: float
    steer_back_track_pos_gain: float
    high_speed_brake_force: float = Field(ge=0.0, le=1.0)
    damaged_reverse_speed_threshold_kmh: float = Field(ge=0.0)
    damaged_reverse_accel: float = Field(ge=0.0, le=1.0)
    damaged_reverse_track_pos_gain: float
    damaged_reverse_steer_clip: float = Field(ge=0.0, le=1.0)
    backward_relaunch_speed_threshold_kmh: float
    backward_relaunch_accel: float = Field(ge=0.0, le=1.0)
    backward_relaunch_angle_gain: float
    backward_relaunch_track_pos_gain: float
    backward_relaunch_steer_clip: float = Field(ge=0.0, le=1.0)
    fallback_accel: float = Field(ge=0.0, le=1.0)
    fallback_brake: float = Field(ge=0.0, le=1.0)


class TorcsDriverConfigWire(BaseModel):
    """Thin runtime contract shared by OVERRIDE, the daemon, and SCR client."""

    model_config = ConfigDict(frozen=True)

    speed: SpeedConfig
    steering: SteeringConfig
    throttle: ThrottleConfig
    braking: BrakingConfig
    gear: GearConfig
    traction: TractionConfig
    launch_guard: LaunchGuardConfig
    recovery: RecoveryConfig


DEFAULT_DRIVER_CONFIG = TorcsDriverConfigWire(
    speed=SpeedConfig(
        target_speed_kmh=85.0,
        min_target_speed_kmh=35.0,
        centre_clamp_m=120.0,
        centre_factor=0.45,
        curvature_clamp=80.0,
        curvature_penalty=0.30,
        visible_road_threshold_m=20.0,
        visible_road_penalty=0.50,
    ),
    steering=SteeringConfig(
        steer_gain=9.0,
        centering_gain=0.35,
        track_sensor_gain=0.60,
        lateral_speed_damping_gain=0.14,
        crest_centering_gain=0.10,
    ),
    throttle=ThrottleConfig(
        steer_speed_penalty_kmh=8.0,
        accel_ramp_up=0.4,
        accel_decay=0.2,
        low_speed_boost_cutoff_kmh=10.0,
        low_speed_boost_denominator_offset=0.1,
    ),
    braking=BrakingConfig(
        overspeed_margin_kmh=12.0,
        overspeed_divisor_kmh=35.0,
        overspeed_cap=0.7,
        angle_threshold_rad=0.55,
        angle_min_speed_kmh=45.0,
        angle_brake_force=0.3,
        track_pos_threshold=0.6,
        track_pos_min_speed_kmh=30.0,
        track_pos_brake_force=0.4,
    ),
    gear=GearConfig(gear_speeds_kmh=[0.0, 20.0, 40.0, 80.0, 100.0, 180.0]),
    traction=TractionConfig(enabled=True, slip_threshold=2.0, accel_cut=0.1),
    launch_guard=LaunchGuardConfig(
        duration_s=15.0,
        track_pos_limit=0.5,
        angle_limit_rad=0.8,
        steer_angle_gain=-0.25,
        steer_track_pos_gain=-0.10,
        steer_clip=0.35,
    ),
    recovery=RecoveryConfig(
        offtrack_trackpos_threshold=0.85,
        offtrack_angle_threshold_rad=0.60,
        angle_recovery_speed_cap_kmh=20.0,
        stuck_time_threshold_s=20.0,
        recovery_speed_kmh=25.0,
        steer_back_angle_gain=-0.8,
        steer_back_track_pos_gain=-0.8,
        high_speed_brake_force=0.6,
        damaged_reverse_speed_threshold_kmh=2.0,
        damaged_reverse_accel=0.2,
        damaged_reverse_track_pos_gain=0.35,
        damaged_reverse_steer_clip=0.7,
        backward_relaunch_speed_threshold_kmh=-2.0,
        backward_relaunch_accel=0.8,
        backward_relaunch_angle_gain=-0.35,
        backward_relaunch_track_pos_gain=-0.15,
        backward_relaunch_steer_clip=0.5,
        fallback_accel=0.2,
        fallback_brake=0.1,
    ),
)


def validate_driver_config(payload: Any) -> TorcsDriverConfigWire:
    if isinstance(payload, TorcsDriverConfigWire):
        return payload
    return TorcsDriverConfigWire.model_validate(payload)


def load_driver_config_from_path(path: str | os.PathLike[str]) -> TorcsDriverConfigWire:
    raw = Path(path)
    data = json.loads(raw.read_text())
    return validate_driver_config(data)


def load_driver_config_from_env(
    env_var: str = "OVERRIDE_DRIVER_CONFIG_PATH",
    *,
    default: TorcsDriverConfigWire = DEFAULT_DRIVER_CONFIG,
) -> TorcsDriverConfigWire:
    raw_path = os.environ.get(env_var)
    if not raw_path:
        return default
    return load_driver_config_from_path(raw_path)


def dump_driver_config_json(config: TorcsDriverConfigWire) -> str:
    return json.dumps(config.model_dump(mode="json"), indent=2)


__all__ = [
    "DEFAULT_DRIVER_CONFIG",
    "TorcsDriverConfigWire",
    "ValidationError",
    "dump_driver_config_json",
    "load_driver_config_from_env",
    "load_driver_config_from_path",
    "validate_driver_config",
]