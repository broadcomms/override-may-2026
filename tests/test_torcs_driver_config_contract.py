from __future__ import annotations

import json

import pytest

from RaceYourCode.gym_torcs.driver_config_contract import (
    DEFAULT_DRIVER_CONFIG,
    load_driver_config_from_env,
    validate_driver_config,
)
from RaceYourCode.gym_torcs.torcs_jm_par import calculate_target_speed


def test_load_driver_config_from_env_returns_default_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("OVERRIDE_DRIVER_CONFIG_PATH", raising=False)

    loaded = load_driver_config_from_env()

    assert loaded == DEFAULT_DRIVER_CONFIG


def test_load_driver_config_from_env_reads_json_file(tmp_path, monkeypatch) -> None:
    path = tmp_path / "driver-config.json"
    payload = DEFAULT_DRIVER_CONFIG.model_dump(mode="json")
    payload["speed"]["target_speed_kmh"] = 91.0
    path.write_text(json.dumps(payload))
    monkeypatch.setenv("OVERRIDE_DRIVER_CONFIG_PATH", str(path))

    loaded = load_driver_config_from_env()

    assert loaded.speed.target_speed_kmh == 91.0
    assert loaded.gear.gear_speeds_kmh == DEFAULT_DRIVER_CONFIG.gear.gear_speeds_kmh


def test_validate_driver_config_rejects_non_ascending_gears() -> None:
    payload = DEFAULT_DRIVER_CONFIG.model_dump(mode="json")
    payload["gear"]["gear_speeds_kmh"] = [0.0, 20.0, 20.0, 80.0, 100.0, 180.0]

    with pytest.raises(ValueError):
        validate_driver_config(payload)


def test_calculate_target_speed_uses_explicit_runtime_config() -> None:
    payload = DEFAULT_DRIVER_CONFIG.model_dump(mode="json")
    payload["speed"]["target_speed_kmh"] = 40.0
    payload["speed"]["min_target_speed_kmh"] = 10.0
    config = validate_driver_config(payload)

    target = calculate_target_speed({}, config=config)

    assert target == 40.0