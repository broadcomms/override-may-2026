# OVERRIDE — Data Schemas

This document describes the shipped typed contracts behind OVERRIDE as of the current app surface. The canonical Python definitions live in [`ingest/schema.py`](../ingest/schema.py), with API-specific request/response models in [`api/main.py`](../api/main.py), error models in [`api/errors.py`](../api/errors.py), and TORCS driver-profile models in [`torcs_driver_profiles.py`](../torcs_driver_profiles.py). The frontend mirrors these contracts in [`ui/src/api/types.ts`](../ui/src/api/types.ts).

If this document disagrees with those files, the code wins and this document should be updated in the same change.

## 1. Conventions

- Times are seconds as `float`.
- Energies are megajoules as `float`.
- Powers are kilowatts as `float`.
- Speeds are km/h as `float`.
- `lap_number` and live `lap` values are 1-indexed.
- Unknown values use `None` / `null`, never sentinel strings.
- JSON keys are snake_case end-to-end.
- Session IDs are short slugs like `s_...`; zone IDs are short slugs like `z_...`.

## 2. Core pipeline types

### `LapFeatures`

One completed lap after ingest normalization.

```python
class LapFeatures(BaseModel):
    lap_number: int
    soc_start: float
    soc_end: float
    harvest_mj: float
    deploy_mj: float
    lap_time: float
    sector1_time: float
    sector2_time: float
    sector3_time: float
    avg_speed: float
    max_speed: float
    override_uses: int
    boost_uses: int
    recharge_zones: list[int]
    soc_source: Literal["measured", "derived"]
```

### `LapWindow`

The bounded model context used by reasoning and optional forecasting.

```python
class LapWindow(BaseModel):
    session_id: str
    laps: list[LapFeatures]   # 1..30
    soc_max: float
    track_id: str | None
```

### `ZoneType` and `Zone`

```python
class ZoneType(str, Enum):
    LOW_ROI_DEPLOY = "low-roi-deploy"
    LATE_RECHARGE = "late-recharge"
    OVER_HARVEST = "over-harvest"
    UNUSED_OVERRIDE = "unused-override"

class Zone(BaseModel):
    zone_id: str
    zone_type: ZoneType
    lap_number: int
    sector: Literal[1, 2, 3]
    severity: Literal["low", "medium", "high"]
    metrics: dict[str, float]
    description: str
```

`metrics` is intentionally flexible in v1. Typical keys:
- `low-roi-deploy`: `deploy_mj`, `time_gain_s`, `roi_mj_per_s`
- `late-recharge`: `harvest_mj`, `lap_time_cost_s`, `available_window_s`
- `over-harvest`: `harvest_mj`, `cap_mj`, `headroom_mj`
- `unused-override`: `gap_to_leader_s`, `available_override_mj`, `straight_length_m`

### `Forecast`

Optional 5-lap SoC forecast. The pipeline must still run when this is `None`.

```python
class Forecast(BaseModel):
    horizon_laps: int              # default 5
    point: list[float]             # len == 5
    lower: list[float]             # len == 5
    upper: list[float]             # len == 5
    mae_validation: float | None
    model_version: str
```

### Regulation types

```python
class RegulationSource(BaseModel):
    document_title: str
    issue: str
    section: str
    public_url: str
    fetched_at: datetime

class RegulationChunk(BaseModel):
    chunk_id: str
    text: str
    source: RegulationSource
    keywords: list[str]
    embedding: list[float] | None

class RegulationCitation(BaseModel):
    passage: str
    source: RegulationSource
```

Hard rule: regulation section labels come from runtime extraction, never hardcoded literals in UI strings, prompts, schemas, or tests.

### Reasoning and fan-mode types

```python
class ReasoningInput(BaseModel):
    session_id: str
    lap_window: LapWindow
    forecast: Forecast | None
    zone: Zone
    regulation: RegulationChunk | None

class ReasoningOutput(BaseModel):
    cause: str
    consequence: str
    recommendation: str
    regulation_citation: RegulationCitation | None
    confidence: Literal["low", "medium", "high"]
    confidence_justification: str
    reasoning_chain: list[str]     # 3..5 steps

class FanOutput(BaseModel):
    headline: str
    what_happened: str
    why_it_mattered: str
    the_rule: str | None
```

When `regulation` is absent, `regulation_citation` must be `None` and confidence must drop to `low`.

## 3. Safety and recommendation types

### `ValidatorResult`

Pass 1 deterministic outcome from `core/validator.py`.

```python
class ValidatorResult(BaseModel):
    passed: bool
    failed_rules: list[str]
    retry_count: int
    notes: list[str]
```

Current rule IDs:
- `energy_bounds`
- `harvest_cap`
- `citation_existence`
- `language_safety`
- `source_consistency`

### `GuardianResult`

Pass 2 AI safety outcome from `core/guardian.py`.

```python
class GuardianResult(BaseModel):
    passed: bool
    pass_threshold: float
    scores: dict[str, float]
    rationales: dict[str, str]
    retry_count: int
    final_confidence: Literal["low", "medium", "high"]
```

### `Recommendation`

The per-zone unit rendered by the UI.

```python
class Recommendation(BaseModel):
    zone: Zone
    reasoning: ReasoningOutput
    fan: FanOutput | None
    validator: ValidatorResult
    guardian: GuardianResult
```

`fan` is lazily populated and may stay `None` until a `mode=fan|both` read.

## 4. Session types

### `SessionSource` and `SessionStatus`

```python
class SessionSource(str, Enum):
    UPLOAD = "upload"
    TORCS_LIVE = "torcs_live"

class SessionStatus(str, Enum):
    COMPLETED = "completed"
    ACTIVE = "active"
    CANCELLED = "cancelled"
```

`source` and `session_source` are different:
- `source`: telemetry/parser shape, currently `torcs` or `fastf1`
- `session_source`: ingest path, currently `upload` or `torcs_live`

### `SessionSummary`

```python
class SessionSummary(BaseModel):
    session_id: str
    uploaded_at: datetime
    source: Literal["torcs", "fastf1"]
    lap_count: int
    forecast_available: bool
    zone_count: int
    track_id: str | None
    note: str | None
    session_source: SessionSource
    status: SessionStatus
    track_name: str | None
    target_laps: int | None
    started_at: datetime | None
    completed_at: datetime | None
    telemetry_file: str | None
    driver_profile_id: str | None
    driver_profile_name: str | None
    driver_profile_origin: Literal["shipped_default", "user_saved", "session_snapshot"] | None
```

### `Session`

```python
class Session(BaseModel):
    summary: SessionSummary
    laps: list[LapFeatures]
    forecast: Forecast | None
    recommendations: list[Recommendation]
    regulation_source: RegulationSource | None
    driver_config_snapshot: TorcsDriverConfigSnapshot | None
```

### `TorcsDriverConfigSnapshot`

The profile/config embedded into a launched live session.

```python
class TorcsDriverConfigSnapshot(BaseModel):
    driver_profile_id: str
    driver_profile_name: str
    driver_profile_origin: Literal["shipped_default", "user_saved", "session_snapshot"]
    config: TorcsDriverConfigWire
```

## 5. What-if contracts

### `WhatIfRequest`

```python
PerturbationKind = Literal[
    "delay_first_deploy",
    "skip_harvest_zone",
    "extend_override",
]

class WhatIfRequest(BaseModel):
    perturbation: PerturbationKind
    zone_id: str | None
    n: int | None
    extra_laps: int = 1
```

Validation rules:
- `delay_first_deploy` requires `n`
- `skip_harvest_zone` requires `zone_id`
- `extend_override` requires `zone_id`

### `WhatIfResult`

```python
class WhatIfResult(BaseModel):
    request: WhatIfRequest
    cache_key: str
    original: list[Recommendation]
    perturbed: list[Recommendation]
    note: str | None
```

The result is cached on disk per session and request hash.

## 6. Live telemetry contracts

These are API-layer models defined in `api/main.py` and used by `/cockpit` and the active-session page.

### `LiveLapStats`

One completed live lap emitted over SSE.

```python
class LiveLapStats(BaseModel):
    lap: int
    lap_time_s: float
    avg_speed_kmh: float
    max_speed_kmh: float
    harvest_mj: float
    deploy_mj: float
    soc_end: float
    fuel_used_kg: float | None
```

### `LiveLapSnapshot`

One in-progress lap snapshot emitted at roughly 4 Hz.

```python
class LiveLapSnapshot(BaseModel):
    lap: int
    lap_time_s: float
    speed_kmh: float
    avg_speed_kmh: float
    max_speed_kmh: float
    dist_from_start_m: float
    lap_progress_pct: float
    sector: Literal[1, 2, 3] | None
    throttle_frac: float | None
    brake_frac: float | None
    steer_frac: float | None
    gear: int | None
    fuel_kg: float | None
    fuel_used_kg: float | None
    harvest_mj: float
    deploy_mj: float
    soc_estimate: float
    soc_source: Literal["derived"]
    balance_label: Literal["spending", "recovering", "balanced"]
```

### Live stream event union

`GET /api/sessions/{session_id}/stream` emits JSON SSE frames with one of these shapes:

- `{"event":"connected","session_id":...,"status":...}`
- `{"event":"snapshot","snapshot": LiveLapSnapshot}`
- `{"event":"lap", ...LiveLapStats}`
- `{"event":"no_telemetry","message":...}`
- `{"event":"race_ended","reason":...,"total_laps":...}`

## 7. TORCS control and driver-profile contracts

### `TorcsStartRaceRequest`

```python
class TorcsStartRaceRequest(BaseModel):
    track: str = "aalborg"
    laps: int = 75
    track_name: str | None
    notes: str | None
    driver_profile_id: str = "baseline"
    launch_mode: Literal["cockpit_practice", "headless_quickrace"] | None
    auto_launch_torcs: bool = False
```

### `TorcsControlPlaneStatus`

```python
class TorcsControlPlaneStatus(BaseModel):
    enabled: bool
    reachable: bool
    starting: bool = False
    active: bool = False
    state: str | None
    session_id: str | None
    last_error: str | None
    last_exit_code: int | None
    track: str | None
    laps: int | None
    launch_mode: Literal["cockpit_practice", "headless_quickrace"] | None
    detail: str | None
```

### Track metadata

```python
class TorcsTrack(BaseModel):
    name: str
    category: str
    display_name: str
    author: str | None
    description: str | None
    length_m: float | None
    width_m: float | None
    pits: int | None
    preview_url: str | None
    map_url: str | None
```

### Driver profile surface

```python
class TorcsDriverProfileSummary(BaseModel):
    profile_id: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    origin: Literal["shipped_default", "user_saved", "session_snapshot"]
    read_only: bool

class TorcsDriverProfile(BaseModel):
    profile_id: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    origin: Literal["shipped_default", "user_saved", "session_snapshot"]
    config: TorcsDriverConfigWire
    read_only: bool
```

`TorcsDriverConfigWire` is the validated runtime config shared with the TORCS driver. Its top-level sections are:
- `speed`
- `steering`
- `throttle`
- `braking`
- `gear`
- `traction`
- `launch_guard`
- `recovery`

The exact field-level contract lives in:
- [`RaceYourCode/gym_torcs/driver_config_contract.py`](../RaceYourCode/gym_torcs/driver_config_contract.py)
- [`ui/src/api/types.ts`](../ui/src/api/types.ts)

## 8. Metadata and error contracts

### `VersionResponse`

```python
class VersionResponse(BaseModel):
    build: str
    git_sha: str | None
    runtime: Literal["watsonx"]
    watsonx_region: str
    granite_instruct: str
    granite_guardian: str
    granite_embedding: str
    granite_ttm_r2: str
    regulation_source_present: bool
```

### `ApiError`

```python
class ApiError(BaseModel):
    error_code: ErrorCode
    message: str
    detail: str | None
    request_id: str
```

Current `ErrorCode` values:
- `INVALID_FILE_FORMAT`
- `FILE_TOO_LARGE`
- `PARSE_FAILED`
- `FORECAST_UNAVAILABLE`
- `MODEL_UNAVAILABLE`
- `RATE_LIMITED`
- `NOT_FOUND`
- `INTERNAL_ERROR`
- `CONTROL_DISABLED`
- `CONTROL_UNREACHABLE`
- `CONTROL_FAILED`
- `RACE_ACTIVE`
- `READ_ONLY_PROFILE`
- `PERSISTENCE_FAILED`

Every API error response uses this shape. `X-Request-Id` mirrors `request_id`.
