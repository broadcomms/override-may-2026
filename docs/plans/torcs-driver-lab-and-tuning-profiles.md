# TORCS Driver Lab And Tuning Profiles

**Status:** Proposed  
**Date:** 2026-05-17  
**Owner:** Architecture  
**Primary runtime path:** `RaceYourCode/gym_torcs/torcs_jm_par.py`

## Why this plan exists

We want OVERRIDE to support structured experimentation on the baseline TORCS
driver instead of forcing users to edit Python manually. The user goal is not
just "start a race", but:

- inspect the baseline driver's tuning surface
- adjust the values with precision
- save named configurations
- launch a race using a chosen configuration
- preserve the exact configuration used for later review and comparison

The current product already has the right high-level split:

- `/upload` is the authoritative pre-race setup surface
- `/cockpit` is the live race-ops surface

That split should stay intact. The new capability should add a dedicated
driver-tuning surface, then feed the selected profile back into `/upload`.

## Current-state findings

### 1. The live race path does not use `gym_torcs.py`

The OVERRIDE control plane launches the SCR client by spawning
`torcs_jm_par.py` directly from the daemon:

- `RaceYourCode/gym_torcs/control_daemon.py:895` launches the SCR client
- `RaceYourCode/gym_torcs/control_daemon.py:900-917` injects env vars and runs
  `python3 torcs_jm_par.py`

So the real UI-backed tuning target is `torcs_jm_par.py`, not the Gym wrapper.

### 2. `torcs_jm_par.py` already has a user-facing tuning section

The active baseline driver exposes a top-level "USER CONFIGURABLE PARAMETERS"
block:

- `TARGET_SPEED`
- `MIN_TARGET_SPEED`
- `STEER_GAIN`
- `CENTERING_GAIN`
- `TRACK_SENSOR_GAIN`
- `BRAKE_THRESHOLD`
- `GEAR_SPEEDS`
- `ENABLE_TRACTION_CONTROL`
- `OFFTRACK_TRACKPOS`
- `OFFTRACK_ANGLE`
- `RECOVERY_SPEED_KMH`
- `LAUNCH_GUARD_S`

Source: `RaceYourCode/gym_torcs/torcs_jm_par.py:502-514`

### 3. Important behavior is still hidden in hardcoded literals

The current file exposes only part of the real tuning surface. Several
behavior-defining numbers are still embedded inside helper functions:

- target-speed shaping constants in `calculate_target_speed`
- throttle ramp and low-speed boost constants in `calculate_throttle`
- overspeed and corner-brake constants in `apply_brakes`
- traction slip threshold and accel cut in `traction_control`
- launch stabilization constants in `apply_launch_guard`
- wall/off-track recovery thresholds and command values in `apply_recovery`

Source: `RaceYourCode/gym_torcs/torcs_jm_par.py:527-697`

If the UI only exposes the top-level constants, it will look complete while
still hiding meaningful behavior. That would be misleading for experimentation.

### 4. There is a second layer of protocol-level settings

There are also lower-level controls that influence how the client interacts
with TORCS:

- track sensor angle vector in the UDP init string  
  Source: `RaceYourCode/gym_torcs/torcs_jm_par.py:101-103`
- default action packet fields and limits  
  Source: `RaceYourCode/gym_torcs/torcs_jm_par.py:366-399`
- step-budget logic derived from lap count  
  Source: `RaceYourCode/gym_torcs/torcs_jm_par.py:596-603`

These should be treated as expert settings, not day-one primary controls.

### 5. `gym_torcs.py` contains experiment knobs, but they are not on the live OVERRIDE path

`gym_torcs.py` includes values like:

- `terminal_judge_start`
- `termination_limit_progress`
- `default_speed`
- `vision`
- `throttle`
- `gear_change`

Sources:

- `RaceYourCode/gym_torcs/gym_torcs.py:13-16`
- `RaceYourCode/gym_torcs/gym_torcs.py:21-25`

These are relevant for RL-style experiments, but they do not currently affect
the daemon-launched live race flow. We should not expose them as if they change
OVERRIDE-managed races unless we explicitly wire them into the live runtime.

### 6. The UI and docs currently assume there is no settings page

The current UX doc says:

- `/upload` is setup and launch
- `/cockpit` is live observation and stop
- "There is no auth, no settings page, no profile, no dashboard analytics."

Source: `docs/04-ui-ux-design.md`

This means the new page is a deliberate product expansion, not just a small UI
adjustment.

## Research and standards that should shape the design

### 1. Safety and validation should be explicit

NHTSA's **Automated Driving Systems 2.0: A Vision for Safety** emphasizes:

- documented system safety processes
- defined operational design domain and capability limits
- validation methods
- data recording
- consumer education and training

Relevant excerpts:

- design decisions, changes, testing, and data should be traceable and transparent
- the operating domain should define capability limits and boundaries
- testing should validate expected behavior
- training should cover capabilities, limitations, engagement, disengagement,
  fallback scenarios, and HMI

Sources:

- [NHTSA ADS 2.0 PDF](https://www.nhtsa.gov/sites/nhtsa.gov/files/documents/13069a-ads2.0_090617_v9a_tag.pdf)
- [NHTSA AV TEST Initiative](https://www.nhtsa.gov/automated-vehicle-test-tracking-tool)

Design implication for OVERRIDE:

- every tuning value needs type, description, bounds, and units
- the exact configuration used in a run must be persisted with that run
- the UI should make it obvious which settings are baseline, changed, unsafe,
  or expert-only
- the tuning surface should be pre-run, not mid-race

### 2. Parameter systems work best when they are typed, declared, and schema-backed

ROS 2 and Autoware both push toward:

- declared parameters instead of open-ended freeform values
- parameter descriptors with type, range, and constraints
- config files as the startup source of truth
- separate default configs from user-customized launch configs

Sources:

- [ROS 2 parameters](https://docs.ros.org/en/humble/Concepts/Basic/About-Parameters.html)
- [Autoware parameter workflow](https://autowarefoundation.github.io/autoware-documentation/main/contributing/coding-guidelines/ros-nodes/parameters/)
- [Autoware control / vehicle interface docs](https://autowarefoundation.github.io/autoware-documentation/latest/design/autoware-interfaces/components/control/)

Design implication for OVERRIDE:

- do not edit Python source files from the UI
- create a typed driver-profile schema
- validate profile files before launch
- keep shipped defaults separate from user-tuned profiles

### 3. The lab itself recommends controlled, one-parameter-at-a-time experimentation

The TORCS lab material explicitly teaches:

- change a parameter
- rerun the agent
- observe the effect
- record what changed and what happened

Source:

- `hands-on-labs/01_torcs_lab/01_torcs_lab/01_torcs_lab.md`

Design implication for OVERRIDE:

- show baseline vs edited values
- support reset-to-baseline
- preserve run-to-profile provenance
- eventually support profile diffing in session compare

## Recommendation

Build a dedicated **Driver Lab** page and a typed **driver profile** system,
while keeping `/upload` as the canonical place to launch races.

### Recommended UX shape

- Add a new route: `/driver`
- Label it in the UI as `Driver Lab`
- Keep `/upload` responsible for track, laps, launch mode, and start
- Add a `Driver profile` selector to `/upload`
- Add a `Tune driver` link from `/upload` to `/driver`
- Keep `/cockpit` read-only for driver settings during a live run

This is better than stuffing every field into `RaceControlCard`, because the
driver surface is too large, too technical, and too experiment-heavy for the
existing launch card.

## Proposed control taxonomy

### Tier 1: MVP user-editable controls

These are the controls that should ship first because they are already
conceptually user-facing and materially change behavior.

| Group | Fields |
|---|---|
| Speed shaping | `target_speed_kmh`, `min_target_speed_kmh` |
| Steering | `steer_gain`, `centering_gain`, `track_sensor_gain` |
| Braking | `brake_threshold_rad` |
| Gearing | `gear_speeds_kmh[6]` |
| Stability | `enable_traction_control` |
| Recovery | `offtrack_trackpos_threshold`, `offtrack_angle_threshold_rad`, `recovery_speed_kmh`, `launch_guard_s` |

### Tier 2: Advanced heuristics now hidden in literals

These should become configurable in code, but can live behind an `Advanced`
disclosure in the UI.

| Group | Current hardcoded behavior |
|---|---|
| Target-speed shaping | center-distance clamp/factor, curvature clamp/penalty, visible-road penalty |
| Throttle | accel ramp-up, accel decay, steer penalty factor, low-speed boost trigger |
| Braking | overspeed margin, brake divisor, brake cap, corner-brake fixed values |
| Traction control | slip threshold, accel cut |
| Launch guard | alignment thresholds and temporary steer clamp |
| Recovery | stuck threshold, reverse threshold, fallback brake/accel/steer values |

### Tier 3: Expert-only protocol settings

These should be visible only after the core tuning flow is stable.

| Group | Fields |
|---|---|
| Sensor geometry | track sensor angles, focus angles |
| Runtime budget | `steps_per_lap_budget`, `default_max_steps` |
| Client transport | host, port, SID, stage, debug |
| Command limits | steer/accel/brake/clutch/gear/focus protocol bounds |

### Out of scope for the first slice

Do not expose `gym_torcs.py`-only wrapper settings in the live OVERRIDE path
until they are truly wired into daemon-launched races.

## Proposed architecture

### 0. Critical implementation decisions to settle first

These are not optional cleanup items. They are prerequisites because the
current compose topology does not let the earlier draft work as written.

#### 0A. Cross-container config transport

Current reality:

- the OVERRIDE API and the TORCS daemon communicate over HTTP
- they do **not** currently share a general-purpose filesystem mount
- the only shared live volume today is telemetry

Sources:

- `docker-compose.yml` mounts `./data/sessions` only into `override`
- `docker-compose.yml` mounts `torcs-telemetry` into both services
- `RaceYourCode/gym_torcs/control_daemon.py:900-917` launches the SCR client
  fully inside the `torcs` container

Therefore the implementation should **not** depend on the API writing a config
artifact and the daemon reading that same path.

Chosen approach:

- OVERRIDE resolves and validates the chosen profile
- OVERRIDE sends the **effective config object** inline to the daemon in the
  `POST /control/start` body
- the daemon materializes that JSON inside the `torcs` container
- the daemon passes the resulting in-container path to `torcs_jm_par.py` via
  `OVERRIDE_DRIVER_CONFIG_PATH`

Why this is the preferred design:

- no new cross-container shared volume required just for launch
- the daemon remains the owner of runtime materialization
- the SCR client still gets a simple file path
- OVERRIDE can separately persist the same config snapshot for provenance

#### 0B. Persistent profile-library storage

The earlier draft proposed `data/torcs_driver_profiles/`, but that is only
correct if the path is actually mounted into the `override` container.

Chosen approach:

- add a new persistent bind mount for profile storage
- use `./data/torcs_driver_profiles:/app/data/torcs_driver_profiles:Z`

Alternative acceptable refactor:

- widen the existing mount to `./data:/app/data:Z`

But the plan should assume **persistent mounted storage**, not container-local
filesystem.

#### 0C. Provenance merge on live ingest

Current reality:

- `POST /api/torcs/start-race` writes an ACTIVE stub session
- `POST /api/sessions/torcs-live` later rebuilds the completed session from
  pipeline output
- the torcs-live enrichment path only re-applies a fixed metadata set today

Sources:

- `api/main.py:1286-1298`
- `api/main.py:1504-1524`
- `api/main.py:1671-1726`

Chosen approach:

- profile provenance fields must be added to `SessionSummary`
- stub-session creation must stamp them at launch time
- torcs-live ingest must explicitly merge/preserve them when replacing the stub

If we do not implement that merge in the same slice, profile provenance will
disappear after normal ingest.

### 1. New shared schema

Add a new typed domain model for the live baseline driver, but split it across
two layers.

#### 1A. Rich OVERRIDE-owned profile schema

These models belong to the OVERRIDE app because they describe product-level
profile management, persistence, and UX:

- `TorcsDriverConfig`
- `TorcsDriverProfile`
- `TorcsDriverProfileSummary`
- `TorcsDriverConfigSnapshot`

#### 1B. Thin shared wire/runtime contract

The daemon is intentionally self-contained and the `torcs` container only sees
the `RaceYourCode/` tree at runtime. So the plan should not assume the daemon
can import rich OVERRIDE app models.

Chosen contract split:

- keep the rich profile schema in the OVERRIDE app
- add a thin shared runtime contract under `RaceYourCode/gym_torcs/`
- recommended file: `RaceYourCode/gym_torcs/driver_config_contract.py`

That shared contract should define only what both runtimes actually need:

- `TorcsDriverConfigWire`
- validation helpers for the effective runtime config
- serialization/deserialization helpers used by daemon and SCR client

Flow:

- OVERRIDE resolves rich profile models to `TorcsDriverConfigWire`
- daemon validates incoming `driver_config` against the same wire contract
- `torcs_jm_par.py` loads the materialized JSON through the same contract

Recommended shape:

- nested sections: `speed`, `steering`, `braking`, `gear`, `traction`,
  `recovery`, `advanced`
- explicit units in field names where it improves clarity
- Pydantic validation for ranges and cross-field rules

Examples of cross-field rules:

- `min_target_speed_kmh <= target_speed_kmh`
- `gear_speeds_kmh` length is exactly 6
- `gear_speeds_kmh` must be strictly ascending
- angle thresholds must stay within a documented safe range

### 2. New persistence surface

Do not store profiles inside the Python file.

Chosen persistence:

- `data/torcs_driver_profiles/_index.json`
- `data/torcs_driver_profiles/{profile_id}.json`

Deployment requirement:

- mount that directory into the `override` container as persistent storage
- do not rely on container-local `/app/...` paths without a compose mount

#### 2A. Shipped baseline profile seeding

The baseline profile should **not** be seeded by writing a mutable default into
the persistent data store on first run. That would blur immutable shipped
defaults and mutable user-saved profiles.

Chosen approach:

- keep shipped default profiles in a source-controlled, read-only repo path
- recommended path: `config/torcs_driver_profiles/`
- persistent storage under `data/torcs_driver_profiles/` is for user-created
  or duplicated profiles only

Runtime behavior:

- list APIs return the union of shipped defaults and saved profiles
- the baseline profile is read-only and cannot be overwritten in place
- "Save as" from a shipped default creates a new user-saved profile in the
  persistent store

Each profile should store:

- `profile_id`
- `name`
- `description`
- `created_at`
- `updated_at`
- `origin`
  - `shipped_default`
  - `user_saved`
  - `session_snapshot`
- `config`

Also add one shipped baseline profile that exactly matches today's runtime.

### 3. Race launch contract change

Extend the start-race path so Upload selects a profile before launch.

Recommended request additions:

- `driver_profile_id`

Optional future extension:

- `driver_config_override`

For the first slice, `driver_profile_id` is enough.

Internal launch contract change:

- OVERRIDE resolves `driver_profile_id` to a validated effective config
- OVERRIDE snapshots that config into session storage immediately
- OVERRIDE sends the effective config object to the daemon as part of the
  daemon start request

This keeps launch provenance and runtime materialization decoupled.

### 4. Control-daemon change

The daemon should stay the owner of process launch, but it needs one more
input: the effective driver configuration.

Chosen approach:

- extend `/control/start` to accept `driver_config`
- materialize `driver_config` to a validated JSON file inside the `torcs`
  container during launch
- pass the resulting in-container path into the SCR client process
- keep `OVERRIDE_DRIVER_CONFIG_PATH` as the SCR-client-facing contract only

Suggested env var:

- `OVERRIDE_DRIVER_CONFIG_PATH`

This is better than embedding large JSON in env vars, avoids a new shared
artifact mount between containers, and still keeps the SCR runtime simple.

### 5. Driver runtime refactor

Refactor `torcs_jm_par.py` so its behavior comes from a config object loaded
at startup, not module-level scattered literals.

Recommended shape inside the script:

- `DriverConfig` dataclass or typed object
- `load_driver_config_from_env()`
- `DEFAULT_DRIVER_CONFIG`
- all helper functions consume `config`

Important requirement:

- default config must preserve today's behavior exactly

### 6. Session provenance

Every launched run should persist the exact config snapshot it used.

Recommended session artifact:

- `data/sessions/{session_id}/driver_config.json`

Recommended summary additions:

- `driver_profile_id`
- `driver_profile_name`
- `driver_profile_origin`

Recommended full-session addition:

- add `driver_config_snapshot` to the full `Session` payload returned by
  `GET /api/sessions/{id}`

Required implementation detail:

- torcs-live ingest must preserve these fields when the completed session
  replaces the ACTIVE stub
- add an explicit merge helper instead of relying on ad hoc `model_copy`
  updates scattered across launch and ingest paths

#### 6A. Stub-session contract

Because cockpit will read active profile provenance from the persisted session
identified by `session_id`, stub-session persistence is no longer best-effort
metadata. It becomes part of the launch contract.

Chosen approach:

- create the stub session and session-level config snapshot **before**
  redirecting the user into cockpit
- if stub creation fails, `start-race` fails instead of continuing with a
  profileless active session contract
- if the daemon launch then fails after the stub exists, delete the stub and
  its session-level config snapshot before returning the error to the caller

Status policy:

- `cancelled` is reserved for runs that were successfully launched and then
  later aborted or stopped after entering the live session lifecycle
- pre-launch or launch-time failures should not leave history clutter behind as
  synthetic cancelled sessions

The important point is that cockpit must never depend on a row that may or may
not exist without a defined fallback path.

This matters because a later profile edit must not rewrite history.

### 7. UI surface

Add:

- `ui/src/pages/DriverLabPage.tsx`
- a profile editor component
- a profile list / duplicate / save-as flow
- Upload integration for selecting a profile
- Cockpit and Session read-only display of the active profile

Chosen cockpit contract:

- keep daemon `/control/status` focused on runtime state only
- do **not** extend daemon status with resolved profile metadata in phase 1
- cockpit should fetch the active stub/completed session by `session_id` and
  read profile provenance from the persisted session summary

Why:

- profile provenance is OVERRIDE-owned metadata, not daemon-owned runtime state
- this avoids duplicating profile truth across the daemon status contract and
  session persistence
- it aligns with the existing stub-session model already keyed by `session_id`

Recommended page structure:

- profile picker
- baseline/reset actions
- grouped numeric controls with units and safe bounds
- advanced disclosure
- live JSON preview or compact "effective config" summary
- save, save as, discard, return to upload

## Proposed API additions

Recommended new endpoints:

- `GET /api/torcs/driver-profiles`
- `GET /api/torcs/driver-profiles/{profile_id}`
- `POST /api/torcs/driver-profiles`
- `PATCH /api/torcs/driver-profiles/{profile_id}`
- `DELETE /api/torcs/driver-profiles/{profile_id}`
- `POST /api/torcs/driver-profiles/{profile_id}/duplicate`
- `POST /api/torcs/driver-profiles/validate`

Recommended extension:

- `POST /api/torcs/start-race` accepts `driver_profile_id`
- daemon `POST /control/start` accepts `driver_config`
- `GET /api/sessions/{id}` includes `driver_config_snapshot` on the full
  session payload

Optional later optimization:

- add `GET /api/sessions/{id}/driver-config` only if the full session payload
  becomes too heavy for compare-time retrieval

## Implementation phases

### Phase -1: Resolve transport and persistence

- add persistent compose storage for the profile library
- choose and implement daemon-side config materialization from request body
- extend start-request and daemon-request schemas accordingly
- add tests proving the effective config can cross from OVERRIDE to `torcs`
  without a shared config filesystem

### Phase 0: Freeze and codify the baseline

- create the baseline profile file matching current live behavior
- add unit tests that prove the default config preserves current outputs
- inventory all hardcoded driver literals before any UI work
- add the shared wire/runtime contract in `RaceYourCode/gym_torcs/`

### Phase 1: Refactor runtime without product changes

- refactor `torcs_jm_par.py` to load a typed config object
- preserve exact current defaults
- add tests around helper functions and config validation

### Phase 2: Add profile persistence and API support

- add profile schemas
- add profile storage
- add CRUD endpoints
- extend `start-race` with `driver_profile_id`
- extend `SessionSummary` with profile provenance fields
- extend the full `Session` payload with `driver_config_snapshot`
- update stub-session creation and completed-session enrichment together so
  provenance survives the full live-ingest lifecycle
- make stub creation + session snapshot persistence a launch invariant, not
  best-effort post-launch enrichment

### Phase 3: Wire launch through the daemon

- OVERRIDE resolves `driver_profile_id` to an effective config
- OVERRIDE snapshots that config into the session directory
- daemon materializes the effective config inside `torcs`
- daemon passes `OVERRIDE_DRIVER_CONFIG_PATH` to the SCR client

### Phase 4: Ship the Driver Lab page

- add `/driver`
- add grouped controls and profile management
- add Upload profile selector and `Tune driver` entry point
- update product docs in the same slice so `/upload` is documented as the
  launch owner and `/cockpit` as live-ops only

### Phase 5: Surface provenance in review flows

- show chosen profile on Upload, Cockpit, Session, and Compare
- add simple config diff presentation for compared sessions
- use the `driver_config_snapshot` already present on the full `Session`
  payload instead of introducing a second compare-only fetch path first

### Phase 6: Expand into advanced controls

- move hidden literals into schema-backed advanced fields
- optionally expose protocol-level sensor geometry behind expert mode

## Validation and test plan

### Unit tests

- default config equals current behavior
- invalid profile shapes are rejected
- gear thresholds must be ascending
- profile snapshot written per race
- config loader handles missing/invalid env paths safely

### API tests

- CRUD profile endpoints
- `start-race` rejects unknown profile IDs
- `start-race` snapshots the chosen config
- `start-race` fails loudly when stub-session persistence fails
- session summaries expose the chosen profile metadata
- torcs-live ingest preserves launch-time profile provenance on completion
- `GET /api/sessions/{id}` returns `driver_config_snapshot`

### Daemon tests

- `_launch_scr_client` forwards config path
- control start materializes the inline config into a torcs-local artifact
- control start fails loudly when the inline config is invalid or missing
- daemon validates the thin wire/runtime contract, not the rich OVERRIDE
  profile schema

### UI tests

- Upload shows active profile and launches with it
- Driver Lab saves and reloads profiles
- advanced controls stay hidden by default
- Cockpit shows active profile read-only
- Cockpit resolves active profile provenance from the persisted session
  summary keyed by `session_id`
- Compare reads per-session config snapshots from the full `Session` payload
  and can diff them without a second endpoint

### Manual acceptance

- user changes `target_speed_kmh` from baseline, saves profile, launches race,
  and sees the saved profile attached to the resulting session
- user resets to baseline and gets the current shipped behavior back
- user opens an older session after editing a profile and still sees the old
  session's original snapshot

## Documentation changes required when implementation starts

- update `docs/03-architecture.md`
- update `docs/03-architecture.mmd`
- update `docs/04-api.md`
- update `docs/04-schema.md`
- update `docs/04-ui-ux-design.md`
- update `docker-compose.yml` comments and mounts if profile persistence adds a
  new bound data path
- update `.gitignore` if persistent user-saved profile artifacts should remain
  local-only like session artifacts

## File-level handoff

Expected code touch set:

- `RaceYourCode/gym_torcs/torcs_jm_par.py`
- `RaceYourCode/gym_torcs/control_daemon.py`
- `api/main.py`
- `api/storage.py`
- `ingest/schema.py`
- `ui/src/App.tsx`
- `ui/src/api/client.ts`
- `ui/src/api/types.ts`
- `ui/src/pages/UploadPage.tsx`
- `ui/src/components/RaceControlCard.tsx`
- `ui/src/pages/CockpitPage.tsx`
- new driver-lab UI components and hooks
- new tests for driver config, daemon launch wiring, and profile APIs

## Final recommendation

Proceed with a **separate Driver Lab page**, but keep **Upload as the only
launch surface**.

That gives us:

- a cleaner mental model
- a real saved-profile workflow
- no false promise that `gym_torcs.py` settings affect live runs
- strong provenance for experiments
- a path to gradually expose deeper heuristics without cluttering the race UI

The important correction after review is sequencing:

- solve config transport first
- solve persistent profile storage first
- solve stub-to-completed-session provenance merge in the same slice as the
  new summary fields

Only after those are fixed should the UI profile editor and richer launch flow
be layered on top.

## References

- Local lab guide: `hands-on-labs/01_torcs_lab/01_torcs_lab/01_torcs_lab.md`
- Live driver runtime: `RaceYourCode/gym_torcs/torcs_jm_par.py`
- Live control plane: `RaceYourCode/gym_torcs/control_daemon.py`
- Current UI architecture: `docs/04-ui-ux-design.md`
- NHTSA ADS 2.0: [Automated Driving Systems: A Vision for Safety](https://www.nhtsa.gov/sites/nhtsa.gov/files/documents/13069a-ads2.0_090617_v9a_tag.pdf)
- NHTSA transparency pattern: [AV TEST Initiative](https://www.nhtsa.gov/automated-vehicle-test-tracking-tool)
- ROS 2 parameter model: [ROS 2 Parameters](https://docs.ros.org/en/humble/Concepts/Basic/About-Parameters.html)
- Autoware parameter workflow: [Autoware Parameters](https://autowarefoundation.github.io/autoware-documentation/main/contributing/coding-guidelines/ros-nodes/parameters/)
