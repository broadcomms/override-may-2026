from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from RaceYourCode.gym_torcs.driver_config_contract import (
    DEFAULT_DRIVER_CONFIG,
    TorcsDriverConfigWire,
    validate_driver_config,
)


DriverProfileOrigin = Literal["shipped_default", "user_saved", "session_snapshot"]
DEFAULT_DRIVER_PROFILE_ID = "baseline"


class TorcsDriverProfileSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    profile_id: str = Field(pattern=r"^[a-z0-9_-]+$", min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=500)
    created_at: datetime
    updated_at: datetime
    origin: DriverProfileOrigin
    read_only: bool = False


class TorcsDriverProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    profile_id: str = Field(pattern=r"^[a-z0-9_-]+$", min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=500)
    created_at: datetime
    updated_at: datetime
    origin: DriverProfileOrigin
    config: TorcsDriverConfigWire
    read_only: bool = False

    def to_summary(self) -> TorcsDriverProfileSummary:
        return TorcsDriverProfileSummary(
            profile_id=self.profile_id,
            name=self.name,
            description=self.description,
            created_at=self.created_at,
            updated_at=self.updated_at,
            origin=self.origin,
            read_only=self.read_only,
        )


class TorcsDriverConfigSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    driver_profile_id: str = Field(pattern=r"^[a-z0-9_-]+$", min_length=1, max_length=80)
    driver_profile_name: str = Field(min_length=1, max_length=80)
    driver_profile_origin: DriverProfileOrigin
    config: TorcsDriverConfigWire


class TorcsDriverProfileCreate(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=500)
    config: TorcsDriverConfigWire


class TorcsDriverProfileUpdate(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=500)
    config: Optional[TorcsDriverConfigWire] = None

    @model_validator(mode="after")
    def _require_change(self) -> "TorcsDriverProfileUpdate":
        if self.name is None and self.description is None and self.config is None:
            raise ValueError("at least one field must be supplied")
        return self


class TorcsDriverProfileDuplicateRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=500)


class DriverProfileNotFoundError(FileNotFoundError):
    pass


class DriverProfileReadOnlyError(PermissionError):
    pass


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def _driver_profiles_root() -> Path:
    raw = os.environ.get("TORCS_DRIVER_PROFILES_DIR")
    if raw:
        return Path(raw)
    return _repo_root() / "data" / "torcs_driver_profiles"


def _shipped_driver_profiles_root() -> Path:
    raw = os.environ.get("TORCS_DRIVER_SHIPPED_PROFILES_DIR")
    if raw:
        return Path(raw)
    return _repo_root() / "config" / "torcs_driver_profiles"


def _profile_file(root: Path, profile_id: str) -> Path:
    return root / f"{profile_id}.json"


def _index_path(root: Path) -> Path:
    return root / "_index.json"


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "driver-profile"


def _read_profile(path: Path, *, read_only: bool) -> TorcsDriverProfile:
    data = json.loads(path.read_text())
    profile = TorcsDriverProfile.model_validate(data)
    return profile if profile.read_only == read_only else profile.model_copy(update={"read_only": read_only})


def _scan_profiles(root: Path, *, read_only: bool) -> list[TorcsDriverProfile]:
    if not root.is_dir():
        return []
    out: list[TorcsDriverProfile] = []
    for path in sorted(root.glob("*.json")):
        if path.name == "_index.json":
            continue
        out.append(_read_profile(path, read_only=read_only))
    return out


def _read_user_index(root: Path) -> list[dict]:
    path = _index_path(root)
    if not path.exists():
        return []
    return json.loads(path.read_text())


def _write_user_index(root: Path, entries: list[dict]) -> None:
    path = _index_path(root)
    root.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2))


def _update_user_index(summary: TorcsDriverProfileSummary, *, root: Optional[Path] = None) -> None:
    base = root or _driver_profiles_root()
    entries = [entry for entry in _read_user_index(base) if entry.get("profile_id") != summary.profile_id]
    entries.append(summary.model_dump(mode="json"))
    entries.sort(key=lambda entry: (entry.get("origin") != "shipped_default", entry.get("name", "")))
    _write_user_index(base, entries)


def _remove_user_index_entry(profile_id: str, *, root: Optional[Path] = None) -> None:
    base = root or _driver_profiles_root()
    entries = [entry for entry in _read_user_index(base) if entry.get("profile_id") != profile_id]
    _write_user_index(base, entries)


def build_driver_config_snapshot(profile: TorcsDriverProfile) -> TorcsDriverConfigSnapshot:
    return TorcsDriverConfigSnapshot(
        driver_profile_id=profile.profile_id,
        driver_profile_name=profile.name,
        driver_profile_origin=profile.origin,
        config=profile.config,
    )


def load_driver_profile(profile_id: str) -> Optional[TorcsDriverProfile]:
    user_path = _profile_file(_driver_profiles_root(), profile_id)
    if user_path.is_file():
        return _read_profile(user_path, read_only=False)

    shipped_path = _profile_file(_shipped_driver_profiles_root(), profile_id)
    if shipped_path.is_file():
        return _read_profile(shipped_path, read_only=True)

    return None


def resolve_driver_profile(profile_id: Optional[str]) -> TorcsDriverProfile:
    resolved_id = profile_id or DEFAULT_DRIVER_PROFILE_ID
    profile = load_driver_profile(resolved_id)
    if profile is None:
        raise DriverProfileNotFoundError(resolved_id)
    return profile


def list_driver_profiles() -> list[TorcsDriverProfileSummary]:
    shipped = [profile.to_summary() for profile in _scan_profiles(_shipped_driver_profiles_root(), read_only=True)]
    user = [profile.to_summary() for profile in _scan_profiles(_driver_profiles_root(), read_only=False)]
    summaries = shipped + user
    return sorted(summaries, key=lambda summary: (summary.origin != "shipped_default", summary.name.lower(), summary.profile_id))


def create_driver_profile(payload: TorcsDriverProfileCreate) -> TorcsDriverProfile:
    root = _driver_profiles_root()
    root.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    profile_id = _slugify(payload.name)
    if load_driver_profile(profile_id) is not None:
        profile_id = f"{profile_id}-{secrets.token_hex(3)}"
    profile = TorcsDriverProfile(
        profile_id=profile_id,
        name=payload.name,
        description=payload.description,
        created_at=now,
        updated_at=now,
        origin="user_saved",
        config=validate_driver_config(payload.config),
        read_only=False,
    )
    _profile_file(root, profile.profile_id).write_text(
        json.dumps(profile.model_dump(mode="json", exclude={"read_only"}), indent=2)
    )
    _update_user_index(profile.to_summary(), root=root)
    return profile


def update_driver_profile(profile_id: str, payload: TorcsDriverProfileUpdate) -> TorcsDriverProfile:
    existing = load_driver_profile(profile_id)
    if existing is None:
        raise DriverProfileNotFoundError(profile_id)
    if existing.read_only or existing.origin == "shipped_default":
        raise DriverProfileReadOnlyError(profile_id)
    updated = existing.model_copy(update={
        "name": payload.name if payload.name is not None else existing.name,
        "description": payload.description if payload.description is not None else existing.description,
        "config": validate_driver_config(payload.config) if payload.config is not None else existing.config,
        "updated_at": datetime.now(timezone.utc),
    })
    root = _driver_profiles_root()
    _profile_file(root, profile_id).write_text(
        json.dumps(updated.model_dump(mode="json", exclude={"read_only"}), indent=2)
    )
    _update_user_index(updated.to_summary(), root=root)
    return updated


def delete_driver_profile(profile_id: str) -> bool:
    existing = load_driver_profile(profile_id)
    if existing is None:
        raise DriverProfileNotFoundError(profile_id)
    if existing.read_only or existing.origin == "shipped_default":
        raise DriverProfileReadOnlyError(profile_id)
    path = _profile_file(_driver_profiles_root(), profile_id)
    existed = path.exists()
    if existed:
        path.unlink()
    _remove_user_index_entry(profile_id)
    return existed


def duplicate_driver_profile(profile_id: str, payload: TorcsDriverProfileDuplicateRequest) -> TorcsDriverProfile:
    existing = load_driver_profile(profile_id)
    if existing is None:
        raise DriverProfileNotFoundError(profile_id)
    return create_driver_profile(
        TorcsDriverProfileCreate(
            name=payload.name or f"{existing.name} Copy",
            description=payload.description if payload.description is not None else existing.description,
            config=existing.config,
        )
    )


def validate_driver_profile_config(config: TorcsDriverConfigWire) -> TorcsDriverConfigWire:
    return validate_driver_config(config)


__all__ = [
    "DEFAULT_DRIVER_PROFILE_ID",
    "DriverProfileNotFoundError",
    "DriverProfileOrigin",
    "DriverProfileReadOnlyError",
    "TorcsDriverConfigSnapshot",
    "TorcsDriverProfile",
    "TorcsDriverProfileCreate",
    "TorcsDriverProfileDuplicateRequest",
    "TorcsDriverProfileSummary",
    "TorcsDriverProfileUpdate",
    "build_driver_config_snapshot",
    "create_driver_profile",
    "delete_driver_profile",
    "duplicate_driver_profile",
    "list_driver_profiles",
    "load_driver_profile",
    "resolve_driver_profile",
    "update_driver_profile",
    "validate_driver_profile_config",
]
