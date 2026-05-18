/**
 * TypeScript mirrors of the Pydantic schemas in docs/04-schema.md.
 *
 * Single source of truth lives in `ingest/schema.py`; this file mirrors
 * those types for the frontend. If a Pydantic schema changes, this file
 * MUST be updated in the same PR.
 *
 * Conventions match the schema doc §2 — snake_case keys, MJ for energies,
 * seconds for times, km/h for speeds, lap_number 1-indexed.
 */

// ──────────────────────────────────────────────────────────────────────────────
// §3 Lap-level features
// ──────────────────────────────────────────────────────────────────────────────

export type SocSource = "measured" | "derived";

export interface LapFeatures {
  lap_number: number;
  soc_start: number;            // [0, 1]
  soc_end: number;              // [0, 1]
  harvest_mj: number;
  deploy_mj: number;
  lap_time: number;
  sector1_time: number;
  sector2_time: number;
  sector3_time: number;
  avg_speed: number;            // km/h
  max_speed: number;            // km/h
  override_uses: number;
  boost_uses: number;
  recharge_zones: number[];     // sector indices
  soc_source: SocSource;
}

export interface LapWindow {
  session_id: string;
  laps: LapFeatures[];          // 1-30
  soc_max: number;              // MJ
  track_id: string | null;
}

// ──────────────────────────────────────────────────────────────────────────────
// §4 Zone detection
// ──────────────────────────────────────────────────────────────────────────────

export type ZoneType =
  | "low-roi-deploy"
  | "late-recharge"
  | "over-harvest"
  | "unused-override";

export type Severity = "low" | "medium" | "high";

export interface Zone {
  zone_id: string;
  zone_type: ZoneType;
  lap_number: number;
  sector: 1 | 2 | 3;
  severity: Severity;
  metrics: Record<string, number>;
  description: string;
}

// ──────────────────────────────────────────────────────────────────────────────
// §5 Forecasting
// ──────────────────────────────────────────────────────────────────────────────

export interface Forecast {
  horizon_laps: number;         // always 5
  point: number[];              // length 5
  lower: number[];
  upper: number[];
  mae_validation: number | null;
  model_version: string;
}

// ──────────────────────────────────────────────────────────────────────────────
// §6 Regulation grounding
// ──────────────────────────────────────────────────────────────────────────────

export interface RegulationSource {
  document_title: string;
  issue: string;
  section: string;              // read from Docling at runtime, never hardcoded
  public_url: string;
  fetched_at: string;           // ISO-8601
}

export interface RegulationCitation {
  passage: string;              // verbatim, ≤25 words
  source: RegulationSource;
}

// ──────────────────────────────────────────────────────────────────────────────
// §7 Reasoning
// ──────────────────────────────────────────────────────────────────────────────

export type Confidence = "low" | "medium" | "high";

export interface ReasoningOutput {
  cause: string;
  consequence: string;
  recommendation: string;
  regulation_citation: RegulationCitation | null;
  confidence: Confidence;
  confidence_justification: string;
  reasoning_chain: string[];    // 3-5 steps
}

// ──────────────────────────────────────────────────────────────────────────────
// §8 / §9 Validator + Guardian results (Pass-1, Pass-2)
// ──────────────────────────────────────────────────────────────────────────────

export interface ValidatorResult {
  passed: boolean;
  failed_rules: string[];
  retry_count: number;          // 0-2
  notes: string[];
}

export interface GuardianResult {
  passed: boolean;
  pass_threshold: number;       // default 0.70
  scores: Record<string, number>;
  rationales: Record<string, string>;
  retry_count: number;
  final_confidence: Confidence;
}

// ──────────────────────────────────────────────────────────────────────────────
// §10 Fan Mode
// ──────────────────────────────────────────────────────────────────────────────

export interface FanOutput {
  headline: string;             // ≤14 words
  what_happened: string;
  why_it_mattered: string;
  the_rule: string | null;      // null when no citation
}

// ──────────────────────────────────────────────────────────────────────────────
// §11 API surface
// ──────────────────────────────────────────────────────────────────────────────

export interface Recommendation {
  zone: Zone;
  reasoning: ReasoningOutput;
  fan: FanOutput | null;
  validator: ValidatorResult;
  guardian: GuardianResult;
}

export type SessionSourceKind = "upload" | "torcs_live";
export type SessionStatusKind = "completed" | "active" | "cancelled";
export type DriverProfileOrigin = "shipped_default" | "user_saved" | "session_snapshot";

export interface TorcsDriverSpeedConfig {
  target_speed_kmh: number;
  min_target_speed_kmh: number;
  centre_clamp_m: number;
  centre_factor: number;
  curvature_clamp: number;
  curvature_penalty: number;
  visible_road_threshold_m: number;
  visible_road_penalty: number;
}

export interface TorcsDriverSteeringConfig {
  steer_gain: number;
  centering_gain: number;
  track_sensor_gain: number;
}

export interface TorcsDriverThrottleConfig {
  steer_speed_penalty_kmh: number;
  accel_ramp_up: number;
  accel_decay: number;
  low_speed_boost_cutoff_kmh: number;
  low_speed_boost_denominator_offset: number;
}

export interface TorcsDriverBrakingConfig {
  overspeed_margin_kmh: number;
  overspeed_divisor_kmh: number;
  overspeed_cap: number;
  angle_threshold_rad: number;
  angle_min_speed_kmh: number;
  angle_brake_force: number;
  track_pos_threshold: number;
  track_pos_min_speed_kmh: number;
  track_pos_brake_force: number;
}

export interface TorcsDriverGearConfig {
  gear_speeds_kmh: number[];
}

export interface TorcsDriverTractionConfig {
  enabled: boolean;
  slip_threshold: number;
  accel_cut: number;
}

export interface TorcsDriverLaunchGuardConfig {
  duration_s: number;
  track_pos_limit: number;
  angle_limit_rad: number;
  steer_angle_gain: number;
  steer_track_pos_gain: number;
  steer_clip: number;
}

export interface TorcsDriverRecoveryConfig {
  offtrack_trackpos_threshold: number;
  offtrack_angle_threshold_rad: number;
  angle_recovery_speed_cap_kmh: number;
  stuck_time_threshold_s: number;
  recovery_speed_kmh: number;
  steer_back_angle_gain: number;
  steer_back_track_pos_gain: number;
  high_speed_brake_force: number;
  damaged_reverse_speed_threshold_kmh: number;
  damaged_reverse_accel: number;
  damaged_reverse_track_pos_gain: number;
  damaged_reverse_steer_clip: number;
  backward_relaunch_speed_threshold_kmh: number;
  backward_relaunch_accel: number;
  backward_relaunch_angle_gain: number;
  backward_relaunch_track_pos_gain: number;
  backward_relaunch_steer_clip: number;
  fallback_accel: number;
  fallback_brake: number;
}

export interface TorcsDriverConfigWire {
  speed: TorcsDriverSpeedConfig;
  steering: TorcsDriverSteeringConfig;
  throttle: TorcsDriverThrottleConfig;
  braking: TorcsDriverBrakingConfig;
  gear: TorcsDriverGearConfig;
  traction: TorcsDriverTractionConfig;
  launch_guard: TorcsDriverLaunchGuardConfig;
  recovery: TorcsDriverRecoveryConfig;
}

export interface TorcsDriverProfileSummary {
  profile_id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  origin: DriverProfileOrigin;
  read_only: boolean;
}

export interface TorcsDriverProfile {
  profile_id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  origin: DriverProfileOrigin;
  config: TorcsDriverConfigWire;
  read_only: boolean;
}

export interface TorcsDriverProfilesResponse {
  profiles: TorcsDriverProfileSummary[];
}

export interface TorcsDriverConfigSnapshot {
  driver_profile_id: string;
  driver_profile_name: string;
  driver_profile_origin: DriverProfileOrigin;
  config: TorcsDriverConfigWire;
}

export interface TorcsDriverConfigValidateResponse {
  valid: true;
  config: TorcsDriverConfigWire;
}

export interface SessionSummary {
  session_id: string;
  uploaded_at: string;          // ISO-8601
  source: "torcs" | "fastf1";
  lap_count: number;
  forecast_available: boolean;
  zone_count: number;
  track_id: string | null;
  note: string | null;
  // Phase 1 lifecycle fields — backward-compatible (defaults: upload + completed)
  session_source: SessionSourceKind;
  status: SessionStatusKind;
  track_name: string | null;
  target_laps: number | null;
  started_at: string | null;     // ISO-8601
  completed_at: string | null;   // ISO-8601
  telemetry_file: string | null;
  driver_profile_id: string | null;
  driver_profile_name: string | null;
  driver_profile_origin: DriverProfileOrigin | null;
}

export interface SessionListResponse {
  sessions: SessionSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface SessionListParams {
  limit?: number;
  offset?: number;
}

/**
 * Phase 3 live-telemetry events emitted by GET /api/sessions/{id}/stream.
 * The discriminator is `event`. Lap events carry the LiveLapStats payload
 * (see api/main.py:LiveLapStats); snapshot events carry LiveLapSnapshot for
 * the in-progress lap; the other three are state markers.
 */
export type LiveStreamEvent =
  | { event: "connected"; session_id: string; status: string }
  | { event: "snapshot"; snapshot: LiveLapSnapshot }
  | { event: "no_telemetry"; message: string }
  | {
      event: "lap";
      lap: number;
      lap_time_s: number;
      avg_speed_kmh: number;
      max_speed_kmh: number;
      harvest_mj: number;
      deploy_mj: number;
      soc_end: number;
      fuel_used_kg: number | null;
    }
  | { event: "race_ended"; reason?: string; total_laps?: number };

export interface LiveLapStats {
  lap: number;
  lap_time_s: number;
  avg_speed_kmh: number;
  max_speed_kmh: number;
  harvest_mj: number;
  deploy_mj: number;
  soc_end: number;
  fuel_used_kg: number | null;
}

/** In-progress lap state emitted by the SSE stream at ~4 Hz. */
export interface LiveLapSnapshot {
  lap: number;
  lap_time_s: number;
  speed_kmh: number;
  avg_speed_kmh: number;
  max_speed_kmh: number;
  dist_from_start_m: number;
  lap_progress_pct: number;
  sector: 1 | 2 | 3 | null;
  throttle_frac: number | null;
  brake_frac: number | null;
  steer_frac: number | null;
  gear: number | null;
  fuel_kg: number | null;
  fuel_used_kg: number | null;
  harvest_mj: number;
  deploy_mj: number;
  soc_estimate: number;
  soc_source: "derived";
  balance_label: "spending" | "recovering" | "balanced";
}

// ─────────────────────────────────────────────────────────────────────────────
// Phase 2 — TORCS control plane (Start/Stop race)
// ─────────────────────────────────────────────────────────────────────────────

// Phase 2.5 — daemon-side race lifecycle. `active` retained on the
// response for backward compat; `state` is the precise value.
export type TorcsRaceState =
  | "idle"
  | "launching"
  | "waiting_scr"
  | "connecting"
  | "active"
  | "stopping"
  | "cleanup";

export type TorcsLaunchMode = "cockpit_practice" | "headless_quickrace";

export interface TorcsControlStatus {
  enabled: boolean;        // env configured on override?
  reachable: boolean;      // daemon /health responded?
  starting: boolean;       // true = normal boot window (daemon never yet reachable); false = genuine failure if also !reachable
  active: boolean;         // (compat) state === "active"
  state: TorcsRaceState | null;
  session_id: string | null;
  // Phase 2.5: distinguishes graceful race-completion (last_error=null,
  // last_exit_code=0) from actual subprocess failures (last_error="...").
  last_error: string | null;
  last_exit_code: number | null;
  track?: string | null;
  laps?: number | null;
  launch_mode?: TorcsLaunchMode | null;
  detail: string | null;
}

export interface TorcsTrack {
  name: string;
  category: "road" | "oval" | "dirt";
  display_name: string;
  author?: string | null;
  description?: string | null;
  length_m?: number | null;
  width_m?: number | null;
  pits?: number | null;
  preview_url?: string | null;
  map_url?: string | null;
}

export interface TorcsTracksResponse {
  tracks: TorcsTrack[];
}

export interface TorcsStartRaceParams {
  track?: string;          // default "aalborg"
  laps?: number;           // default 75 — long-run demo default
  track_name?: string;     // free-form, ≤80 chars
  notes?: string;          // free-form, ≤500 chars
  driver_profile_id?: string;
  launch_mode?: TorcsLaunchMode;
  auto_launch_torcs?: boolean;  // backward-compatible shim for older callers
}

export interface TorcsStartRaceResponse {
  session_id: string;
  pid: number;                       // SCR-client PID
  telemetry_dir: string;
  track: string;
  laps: number;
  track_name_hint?: string | null;   // OVERRIDE-side echo (optional)
  notes_hint?: string | null;
  driver_profile_id_hint?: string | null;
  driver_profile_name_hint?: string | null;
  launch_mode?: TorcsLaunchMode | null;
  torcs_pid?: number | null;         // Phase 2.5 — populated when auto_launch=true
  state?: TorcsRaceState | null;     // Phase 2.5 — daemon state after launch (usually "active")
}

export interface TorcsStopRaceResponse {
  status: "stopped" | "no_active_race";
  session_id: string | null;
  // Phase 2.5 two-subprocess stop: separate exit codes for SCR client and TORCS.
  scr_exit_code?: number | null;
  torcs_exit_code?: number | null;
  // Backward-compat: pre-Phase-2.5 daemon only returned `exit_code` (singular).
  exit_code?: number | null;
}

export interface TorcsRecoverResponse {
  status: "recovered" | "no_active_race";
  session_id: string | null;
  scr_exit_code?: number | null;
  torcs_exit_code?: number | null;
  state?: TorcsRaceState | null;
}

export interface Session {
  summary: SessionSummary;
  laps: LapFeatures[];
  forecast: Forecast | null;
  recommendations: Recommendation[];
  regulation_source: RegulationSource | null;
  driver_config_snapshot: TorcsDriverConfigSnapshot | null;
}

// ──────────────────────────────────────────────────────────────────────────────
// §12 Errors
// ──────────────────────────────────────────────────────────────────────────────

export type ErrorCode =
  | "INVALID_FILE_FORMAT"
  | "FILE_TOO_LARGE"
  | "PARSE_FAILED"
  | "FORECAST_UNAVAILABLE"
  | "MODEL_UNAVAILABLE"
  | "RATE_LIMITED"
  | "NOT_FOUND"
  | "INTERNAL_ERROR"
  | "CONTROL_DISABLED"
  | "CONTROL_UNREACHABLE"
  | "CONTROL_FAILED"
  | "RACE_ACTIVE"
  | "READ_ONLY_PROFILE"
  | "PERSISTENCE_FAILED";

export interface ApiError {
  error_code: ErrorCode;
  message: string;
  detail: string | null;
  request_id: string;
}

// ──────────────────────────────────────────────────────────────────────────────
// /api/version + /api/health response types
// ──────────────────────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: "ok";
  uptime_s: number;
}

export interface VersionResponse {
  build: string;
  git_sha: string | null;
  runtime: "watsonx";
  watsonx_region: string;
  granite_instruct: string;
  granite_guardian: string;
  granite_embedding: string;
  granite_ttm_r2: string;
  regulation_source_present: boolean;
}

export type ZoneMode = "engineer" | "fan" | "both";

// ──────────────────────────────────────────────────────────────────────────────
// §8 / FR-8 What-if perturbations
// (Mirrors WhatIfRequest / WhatIfResult in ingest/schema.py.)
// ──────────────────────────────────────────────────────────────────────────────

export type PerturbationKind =
  | "delay_first_deploy"
  | "skip_harvest_zone"
  | "extend_override";

export interface WhatIfRequest {
  perturbation: PerturbationKind;
  zone_id?: string | null;        // required for skip_harvest_zone / extend_override
  n?: number | null;              // required for delay_first_deploy; 1-10
  extra_laps?: number;            // optional for extend_override; default 1; 1-5
}

export interface TorcsRunSummary {
  run_id: string;
  size_bytes: number;
  lap_count_estimate: number;
  // Phase 1 enrichment (already shipped by the backend; surfacing here)
  started_at?: string | null;
  last_written_at?: string | null;
  duration_seconds?: number | null;
  // Phase 4: non-null when an existing Session references this JSONL via
  // its telemetry_file. UI uses this to mark the row as ingested rather
  // than offering a duplicate Ingest button that would 409 on the second
  // click.
  ingested_session_id?: string | null;
}

export interface TorcsStatusResponse {
  available: boolean;
  runs: TorcsRunSummary[];
  // Phase 4 pagination (default page size 50, max 200). Older endpoints
  // returning the legacy shape will leave these undefined.
  total?: number;
  limit?: number;
  offset?: number;
}

export interface BulkDeleteSessionsResponse {
  deleted: number;
  telemetry_removed: number;
}

export interface WhatIfResult {
  request: WhatIfRequest;
  cache_key: string;              // sha256(...)[:16]
  original: Recommendation[];
  perturbed: Recommendation[];
  note: string | null;            // honest edge-case message; null on happy path
}
