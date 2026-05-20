/**
 * Typed API client for OVERRIDE's Tier-1 surface (docs/04-api.md §4).
 *
 * Two modes:
 *   - live  — fetch /api/* (proxied to FastAPI :8000 in dev per vite.config.ts)
 *   - fixture — return one of the captured demo fixtures shaped as a
 *               Session. Lets us iterate on UI without burning watsonx
 *               quota or running the orchestrator. Toggle via env var
 *               VITE_USE_FIXTURE=1 (set in .env.development.local) or by
 *               passing { fixture: true } to specific call sites.
 *
 * Three fixtures are bundled, each with a deliberate shape:
 *   - `fan_mode_demo.json`        — Session captured from a clean live
 *                                   pipeline run; every zone has `.fan`
 *                                   populated. Default UI dev surface.
 *                                   Honest about validator state — every
 *                                   zone here happens to have hit Pass-1
 *                                   `citation_existence` after retries
 *                                   (real Granite output couldn't satisfy
 *                                   the verbatim rule on the first attempt).
 *   - `engineer_happy_demo.json`  — Derived from fan_mode_demo with Lap 1
 *                                   promoted to a happy-path Pass-1+Pass-2
 *                                   outcome. Mixed state (Lap 1 happy +
 *                                   Laps 2-5 rejection) → single screenshot
 *                                   tells both halves of the safety story.
 *                                   Used for the engineer-mode.png asset.
 *   - `layered_defense_demo.json` — Single-zone capture of the "system
 *                                   catches its own mistake" path. Used
 *                                   for the guardian-rejection.png asset.
 */

import engineerHappyFixtureRaw from "@fixtures/engineer_happy_demo.json";
import fanModeFixtureRaw from "@fixtures/fan_mode_demo.json";
import forecastDemoFixtureRaw from "@fixtures/forecast_demo.json";
import layeredDefenseFixtureRaw from "@fixtures/layered_defense_demo.json";
import torcsEngineerFixtureRaw from "@fixtures/torcs_engineer_demo.json";
import type {
  ApiError,
  CopilotAnswer,
  CopilotMessage,
  HealthResponse,
  LiveStreamEvent,
  LapAnalysis,
  BulkDeleteSessionsResponse,
  RaceReport,
  Recommendation,
  RegulationSource,
  Session,
  SessionListParams,
  SessionListResponse,
  SessionSummary,
  TorcsDriverConfigValidateResponse,
  TorcsDriverConfigWire,
  TorcsDriverProfile,
  TorcsDriverProfilesResponse,
  TorcsControlStatus,
  TorcsRecoverResponse,
  TorcsStartRaceParams,
  TorcsStartRaceResponse,
  TorcsStatusResponse,
  TorcsStopRaceResponse,
  TorcsTracksResponse,
  VersionResponse,
  WhatIfRequest,
  WhatIfResult,
  ZoneMode,
} from "./types";

// ──────────────────────────────────────────────────────────────────────────────
// Error class
// ──────────────────────────────────────────────────────────────────────────────

export class OverrideApiError extends Error {
  readonly status: number;
  readonly payload: ApiError;

  constructor(status: number, payload: ApiError) {
    super(payload.message);
    this.name = "OverrideApiError";
    this.status = status;
    this.payload = payload;
  }
}

// ──────────────────────────────────────────────────────────────────────────────
// Fixture → Session adapters
// ──────────────────────────────────────────────────────────────────────────────

export type FixtureName = "fan_mode" | "engineer_happy" | "layered_defense" | "torcs_engineer" | "forecast_demo";

/**
 * The fan_mode fixture is shaped as a literal Session under `.session` —
 * captured via `scripts/capture_fan_mode_demo.py` after a full pipeline
 * run. No re-shaping needed.
 */
function fanModeSession(): Session {
  const wrapper = fanModeFixtureRaw as unknown as { session: Session };
  return wrapper.session;
}

/**
 * The engineer_happy fixture is also shaped as `.session` — derived
 * from fan_mode_demo with Lap 1 promoted to a happy-path outcome.
 */
function engineerHappySession(): Session {
  const wrapper = engineerHappyFixtureRaw as unknown as { session: Session };
  return wrapper.session;
}

/**
 * The torcs_engineer fixture is the v6 plan task 2.8 upgrade — a session
 * captured by piping `data/samples/torcs_baseline.jsonl` through the FULL
 * watsonx pipeline (real Granite reasoning, real Pass-1 + Pass-2 + Fan).
 * Replaces the synthetic engineer_happy_demo as the "real-TORCS-lap"
 * demo asset. Routed by /session/s_torcs_engineer_demo?fixture=1.
 */
function torcsEngineerSession(): Session {
  const wrapper = torcsEngineerFixtureRaw as unknown as { session: Session };
  return wrapper.session;
}

/**
 * The layered_defense fixture was captured before the orchestrator
 * existed (P2.6) — it stores the run as `{ stages: { reasoning,
 * pass_1_validator, pass_2_guardian } }`. We re-shape it into a Session.
 * Pure to its single demo purpose: the "system catches its own mistake"
 * narrative for the demo video's explainability beat.
 */
function layeredDefenseSession(): Session {
  const f = layeredDefenseFixtureRaw as unknown as {
    stages: {
      detection: { n_zones: number; target_zone_id: string; target_zone_type: string };
      reasoning: { output: Recommendation["reasoning"] };
      pass_1_validator: Recommendation["validator"];
      pass_2_guardian: { result: Recommendation["guardian"] };
    };
    input: { session_id: string; soc_max_mj: number; track_id: string; n_laps: number };
    captured_at: string;
  };
  const recommendation: Recommendation = {
    zone: {
      zone_id: f.stages.detection.target_zone_id,
      zone_type: f.stages.detection.target_zone_type as Recommendation["zone"]["zone_type"],
      lap_number: 1,
      sector: 2,
      severity: "high",
      metrics: { deploy_mj: 0.3, time_gain_s: 0.0, roi_mj_per_s: 30 },
      description: "Lap 1: deployed 0.30 MJ for +0.00 s of advantage (ROI 30.0 MJ/s).",
    },
    reasoning: f.stages.reasoning.output,
    fan: null,
    validator: f.stages.pass_1_validator,
    guardian: f.stages.pass_2_guardian.result,
  };
  const summary: SessionSummary = {
    session_id: f.input.session_id,
    uploaded_at: f.captured_at,
    source: "fastf1",
    lap_count: f.input.n_laps,
    forecast_available: false,
    zone_count: f.stages.detection.n_zones,
    track_id: f.input.track_id,
    note:
      "Layered-defense demo — Pass-1 caught a fabricated citation; Pass-2 said both criteria 'No risk'. The system surfaces the failure rather than silently dropping it.",
    // Phase 1 lifecycle defaults (fixtures predate the field; UPLOAD/COMPLETED is the right shape)
    session_source: "upload",
    status: "completed",
    track_name: null,
    target_laps: null,
    started_at: null,
    completed_at: null,
    telemetry_file: null,
    driver_profile_id: null,
    driver_profile_name: null,
    driver_profile_origin: null,
  };
  const reg = recommendation.reasoning.regulation_citation;
  return {
    summary,
    laps: [],
    forecast: null,
    recommendations: [recommendation],
    regulation_source: reg ? reg.source : null,
    driver_config_snapshot: null,
  };
}

/**
 * The forecast_demo fixture is a synthetic 35-lap TORCS session demonstrating
 * TTM-R2 5-lap SoC forecast and low-roi-deploy zone detection. Used for
 * the "Forecast strategy demo" entry in SampleReplayList.
 */
function forecastDemoSession(): Session {
  const wrapper = forecastDemoFixtureRaw as unknown as { session: Session };
  return wrapper.session;
}

export function fixtureSession(name: FixtureName = "fan_mode"): Session {
  switch (name) {
    case "forecast_demo":
      return forecastDemoSession();
    case "torcs_engineer":
      return torcsEngineerSession();
    case "layered_defense":
      return layeredDefenseSession();
    case "engineer_happy":
      return engineerHappySession();
    case "fan_mode":
    default:
      return fanModeSession();
  }
}

/** Pull the fixture name from a session_id slug. Lets the UI route
 * /session/s_torcs_engineer_demo → torcs_engineer fixture without an
 * extra query-string toggle. Order matters — torcs_engineer must beat
 * the generic "engineer" match. */
function fixtureNameForSessionId(sessionId: string): FixtureName {
  if (sessionId.includes("forecast_demo")) return "forecast_demo";
  if (sessionId.includes("torcs_engineer")) return "torcs_engineer";
  if (sessionId.includes("layered_defense")) return "layered_defense";
  if (sessionId.includes("engineer_happy")) return "engineer_happy";
  return "fan_mode";
}

function fixtureLiveStreamEvents(sessionId: string): Array<{ delayMs: number; event: LiveStreamEvent }> {
  return [
    {
      delayMs: 0,
      event: { event: "connected", session_id: sessionId, status: "active" },
    },
    {
      delayMs: 180,
      event: {
        event: "snapshot",
        snapshot: {
          lap: 4,
          lap_time_s: 18.4,
          speed_kmh: 232.0,
          avg_speed_kmh: 198.2,
          max_speed_kmh: 247.5,
          dist_from_start_m: 1680,
          lap_progress_pct: 56.0,
          sector: 2,
          throttle_frac: 0.92,
          brake_frac: 0,
          steer_frac: 0.08,
          gear: 6,
          fuel_kg: 86.4,
          fuel_used_kg: 0.22,
          harvest_mj: 0.18,
          deploy_mj: 0.56,
          soc_estimate: 0.48,
          soc_source: "derived",
          balance_label: "spending",
        },
      },
    },
    {
      delayMs: 360,
      event: {
        event: "lap",
        lap: 3,
        lap_time_s: 36.4,
        avg_speed_kmh: 201.8,
        max_speed_kmh: 246.2,
        harvest_mj: 0.31,
        deploy_mj: 0.82,
        soc_end: 0.52,
        fuel_used_kg: 0.47,
      },
    },
    {
      delayMs: 540,
      event: {
        event: "insight",
        insight: {
          insight_id: "li_energy_pressure_v1_l3_s2",
          rule_id: "energy_pressure_v1",
          kind: "strategy_recommendation",
          severity: "high",
          headline: "Energy pressure building",
          message: "Deploy exceeded harvest by 0.51 MJ on lap 3, and battery reserve is trending tighter.",
          recommended_action: "Recommend a recover lap before repeating the same deployment pattern.",
          confidence: "high",
          evidence: [
            "Lap 3 closed with 0.82 MJ deploy vs 0.31 MJ harvest.",
            "SoC is tracking around 48%.",
          ],
          lap: 3,
          sector: 2,
        },
      },
    },
    {
      delayMs: 900,
      event: {
        event: "insight",
        insight: {
          insight_id: "li_battery_prediction_v1_l3_s0",
          rule_id: "battery_prediction_v1",
          kind: "prediction",
          severity: "medium",
          headline: "Battery reserve trending down",
          message: "Recent SoC slope would bring the reserve near 35% around lap 5 if the same energy pattern continues.",
          recommended_action: "Recommend conservative deployment until the reserve trend flattens.",
          confidence: "medium",
          evidence: [
            "Recent SoC drops average 7.0% per lap.",
            "Latest completed lap ended at 52% SoC.",
          ],
          lap: 3,
          sector: null,
        },
      },
    },
  ];
}

// ──────────────────────────────────────────────────────────────────────────────
// Fixture-mode synthesis for FR-8 what-if (offline dev + recording fallback)
// ──────────────────────────────────────────────────────────────────────────────

/**
 * Crudely synthesize a WhatIfResult from a fixture session. Goal isn't
 * realism — it's letting WhatIfRail + WhatIfDiff render against
 * deterministic data without a live backend. The diff component's job is
 * to highlight changed fields, so the synthesis nudges the perturbed
 * recommendations in the direction the real perturbation would
 * (delay_first_deploy → lower deploy on first zone, skip_harvest_zone →
 * zero harvest on the target zone, extend_override → higher deploy).
 * Same direction, not same magnitude.
 */
function _synthesizeFixtureWhatIf(
  sessionId: string,
  request: WhatIfRequest,
  opts: ApiOpts | undefined,
): WhatIfResult {
  const session = fixtureSession(resolveFixtureName(opts, sessionId));
  const original = session.recommendations;

  // Find the target zone (or first deploy lap for delay_first_deploy)
  const targetId =
    request.perturbation === "delay_first_deploy"
      ? original[0]?.zone.zone_id ?? null
      : request.zone_id ?? null;

  const perturbed: Recommendation[] = original.map((rec) => {
    if (!targetId || rec.zone.zone_id !== targetId) return rec;
    // Nudge the metrics dict to surface a visible diff for the renderer
    const metrics = { ...rec.zone.metrics };
    if (request.perturbation === "delay_first_deploy") {
      metrics.deploy_mj = Math.max(0, (metrics.deploy_mj ?? 1.5) * 0.4);
    } else if (request.perturbation === "skip_harvest_zone") {
      metrics.harvest_mj = 0;
    } else if (request.perturbation === "extend_override") {
      metrics.deploy_mj = (metrics.deploy_mj ?? 1.5) + 0.5;
    }
    return {
      ...rec,
      zone: { ...rec.zone, metrics },
    };
  });

  // Deterministic 16-char "hash" for fixture mode — not real sha256, just
  // a stable identifier per (perturbation, zone, n, extra_laps) tuple so
  // the UI can demonstrate the cache_key field without crypto deps.
  const cache_key = (
    `f_${request.perturbation}_${request.zone_id ?? ""}_${request.n ?? ""}_${request.extra_laps ?? 1}`
      .replace(/[^a-z0-9]/gi, "0")
      .toLowerCase()
      .padEnd(16, "0")
      .slice(0, 16)
  );

  const targetZoneFound =
    !targetId || original.some((r) => r.zone.zone_id === targetId);
  const note = targetZoneFound
    ? null
    : `fixture-mode: zone ${targetId} not found in session — synthesis no-op`;

  return { request, cache_key, original, perturbed, note };
}


// ──────────────────────────────────────────────────────────────────────────────
// Mode toggle
// ──────────────────────────────────────────────────────────────────────────────

const USE_FIXTURE_DEFAULT =
  // import.meta.env is Vite's typed env shim
  (import.meta.env.VITE_USE_FIXTURE ?? "") === "1";

interface ApiOpts {
  fixture?: boolean;
  fixtureName?: FixtureName;
  signal?: AbortSignal;
}

function resolveFixture(opts?: ApiOpts): boolean {
  return opts?.fixture ?? USE_FIXTURE_DEFAULT;
}

function resolveFixtureName(opts?: ApiOpts, sessionId?: string): FixtureName {
  if (opts?.fixtureName) return opts.fixtureName;
  if (sessionId) return fixtureNameForSessionId(sessionId);
  return "fan_mode";
}

// ──────────────────────────────────────────────────────────────────────────────
// fetch wrapper that throws OverrideApiError on non-2xx
// ──────────────────────────────────────────────────────────────────────────────

async function jsonFetch<T>(
  input: RequestInfo,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(input, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok) {
    let payload: ApiError;
    try {
      payload = (await res.json()) as ApiError;
    } catch {
      payload = {
        error_code: "INTERNAL_ERROR",
        message: `HTTP ${res.status} ${res.statusText}`,
        detail: null,
        request_id: res.headers.get("X-Request-Id") ?? "unknown",
      };
    }
    throw new OverrideApiError(res.status, payload);
  }
  return (await res.json()) as T;
}

function _synthesizeFixtureRaceReport(sessionId: string, opts?: ApiOpts): RaceReport {
  const session = fixtureSession(resolveFixtureName(opts, sessionId));
  const laps = session.laps;
  const keyMoments = session.recommendations.slice(0, 3).map((rec, index) => ({
    insight_id: `li_fixture_report_${index + 1}`,
    rule_id: `fixture_report_${rec.zone.zone_type}`,
    kind: "explanation" as const,
    severity: rec.zone.severity,
    headline: rec.reasoning.recommendation,
    message: `Lap ${rec.zone.lap_number}, sector ${rec.zone.sector}: ${rec.reasoning.cause} ${rec.reasoning.consequence}`,
    recommended_action: rec.reasoning.recommendation,
    confidence: rec.guardian.final_confidence,
    evidence: rec.reasoning.reasoning_chain.slice(0, 3),
    lap: rec.zone.lap_number,
    sector: rec.zone.sector,
  }));

  const bestLap = laps.length > 0 ? laps.reduce((best, lap) => (lap.lap_time < best.lap_time ? lap : best), laps[0]) : null;
  const finalSoc = laps.length > 0 ? laps[laps.length - 1].soc_end * 100 : 0;

  return {
    session_id: session.summary.session_id,
    title: `Race report · ${session.summary.track_name ?? session.summary.track_id ?? "fixture"}`,
    executive_summary: `Fixture session reviewed ${laps.length} laps and highlighted ${session.recommendations.length} explainability moments.`,
    driver_score: 82,
    battery_efficiency_score: 78,
    consistency_score: 80,
    risk_score: 24,
    key_moments: keyMoments,
    ai_commentary: [
      bestLap
        ? `Best lap was ${bestLap.lap_number} at ${bestLap.lap_time.toFixed(2)}s.`
        : "No completed laps are available in this fixture.",
      `Final battery reserve closed at ${finalSoc.toFixed(0)}%.`,
      "Use the lap route to inspect one lap at a time with the same deterministic evidence trail.",
    ],
    generated_at: new Date().toISOString(),
  };
}

function _synthesizeFixtureLapAnalysis(sessionId: string, lapNumber: number, opts?: ApiOpts): LapAnalysis {
  const session = fixtureSession(resolveFixtureName(opts, sessionId));
  const lap = session.laps.find((item) => item.lap_number === lapNumber) ?? session.laps[0];
  if (!lap) {
    throw new OverrideApiError(404, {
      error_code: "NOT_FOUND",
      message: `Lap ${lapNumber} not found in fixture session.`,
      detail: null,
      request_id: "fixture",
    });
  }
  const related = session.recommendations.filter((rec) => rec.zone.lap_number === lap.lap_number);
  return {
    session_id: session.summary.session_id,
    lap_number: lap.lap_number,
    headline:
      related[0]?.reasoning.recommendation
      ?? `Lap ${lap.lap_number} ${lap.harvest_mj >= lap.deploy_mj ? "rebuilt" : "spent"} energy reserve`,
    summary: `Lap ${lap.lap_number} ran ${lap.lap_time.toFixed(2)}s with SoC moving from ${(lap.soc_start * 100).toFixed(0)}% to ${(lap.soc_end * 100).toFixed(0)}%.`,
    sector_callouts: [
      `Sector 1: ${lap.sector1_time.toFixed(2)}s`,
      `Sector 2: ${lap.sector2_time.toFixed(2)}s`,
      `Sector 3: ${lap.sector3_time.toFixed(2)}s`,
    ],
    evidence: [
      `Harvest ${lap.harvest_mj.toFixed(2)} MJ vs deploy ${lap.deploy_mj.toFixed(2)} MJ.`,
      `Average speed ${lap.avg_speed.toFixed(1)} km/h; max speed ${lap.max_speed.toFixed(1)} km/h.`,
      ...related.flatMap((rec) => rec.reasoning.reasoning_chain.slice(0, 2)),
    ],
    generated_at: new Date().toISOString(),
  };
}

function _synthesizeFixtureCopilotAnswer(
  sessionId: string,
  question: string,
  recentTurns: CopilotMessage[],
  opts?: ApiOpts,
): CopilotAnswer {
  const session = fixtureSession(resolveFixtureName(opts, sessionId));
  const normalized = question.toLowerCase();
  if (normalized.includes("compare lap")) {
    return {
      answer: "Lap comparison is available in fixture mode. Use the lap drill-down route to inspect the two laps side by side with energy and pace evidence.",
      engine: "deterministic",
      supporting_laps: session.laps.slice(0, 2).map((lap) => lap.lap_number),
      confidence: "medium",
      suggestions: ["Ask about battery trend", "Ask why the recommendation was surfaced"],
    };
  }
  if (normalized.includes("battery") || normalized.includes("energy")) {
    const lastLap = session.laps[session.laps.length - 1];
    return {
      answer: `Fixture battery trend closed at ${Math.round(lastLap.soc_end * 100)}% SoC after ${session.laps.length} laps, which makes it a good debrief prompt for energy balance.`,
      engine: "deterministic",
      supporting_laps: [session.laps[0]?.lap_number ?? 1, lastLap.lap_number],
      confidence: "medium",
      suggestions: ["Compare two laps", "Ask why the strategy recommendation was surfaced"],
    };
  }
  const anchor = session.recommendations[0];
  return {
    answer: recentTurns.length > 0
      ? `Using the fixture session plus your recent turns, the best anchor is lap ${anchor.zone.lap_number}: ${anchor.reasoning.recommendation}`
      : `The fixture copilot points first to lap ${anchor.zone.lap_number}: ${anchor.reasoning.recommendation}`,
    engine: "deterministic",
    supporting_laps: [anchor.zone.lap_number],
    confidence: anchor.reasoning.confidence,
    suggestions: ["Ask about battery trend", "Compare two laps", "Ask about sector 3"],
  };
}

// ──────────────────────────────────────────────────────────────────────────────
// Public API
// ──────────────────────────────────────────────────────────────────────────────

export const api = {
  async health(opts?: ApiOpts): Promise<HealthResponse> {
    if (resolveFixture(opts)) {
      return { status: "ok", uptime_s: 0 };
    }
    return jsonFetch<HealthResponse>("/api/health", { signal: opts?.signal });
  },

  async version(opts?: ApiOpts): Promise<VersionResponse> {
    if (resolveFixture(opts)) {
      return {
        build: "v0.1.0-fixture",
        git_sha: null,
        runtime: "watsonx",
        watsonx_region: "us-south",
        granite_instruct: "ibm/granite-4-h-small",
        granite_guardian: "ibm/granite-guardian-3-8b",
        granite_embedding: "ibm/granite-embedding-278m-multilingual",
        granite_ttm_r2: "ibm-granite/granite-timeseries-ttm-r2",
        regulation_source_present: true,
      };
    }
    return jsonFetch<VersionResponse>("/api/version", { signal: opts?.signal });
  },

  async regulationSource(opts?: ApiOpts): Promise<RegulationSource | null> {
    if (resolveFixture(opts)) {
      return fixtureSession(resolveFixtureName(opts)).regulation_source;
    }
    try {
      return await jsonFetch<RegulationSource>("/api/regulation-source", {
        signal: opts?.signal,
      });
    } catch (e) {
      if (e instanceof OverrideApiError && e.status === 404) {
        return null;        // G-4 pending → caller renders the banner
      }
      throw e;
    }
  },

  async createSession(
    args: { file: File; source: "torcs" | "fastf1"; trackId?: string; socMax?: number },
    opts?: ApiOpts,
  ): Promise<Session> {
    if (resolveFixture(opts)) {
      // Simulate a brief network delay so loading skeletons appear
      await new Promise((r) => setTimeout(r, 250));
      return fixtureSession(resolveFixtureName(opts));
    }
    const body = new FormData();
    body.append("file", args.file);
    body.append("source", args.source);
    if (args.trackId) body.append("track_id", args.trackId);
    body.append("soc_max", String(args.socMax ?? 4.0));
    return jsonFetch<Session>("/api/sessions", {
      method: "POST",
      body,
      signal: opts?.signal,
    });
  },

  async getSession(sessionId: string, opts?: ApiOpts): Promise<Session> {
    if (resolveFixture(opts)) {
      return fixtureSession(resolveFixtureName(opts, sessionId));
    }
    return jsonFetch<Session>(`/api/sessions/${encodeURIComponent(sessionId)}`, {
      signal: opts?.signal,
    });
  },

  async getRaceReport(sessionId: string, opts?: ApiOpts): Promise<RaceReport> {
    if (resolveFixture(opts)) {
      return _synthesizeFixtureRaceReport(sessionId, opts);
    }
    return jsonFetch<RaceReport>(`/api/sessions/${encodeURIComponent(sessionId)}/report`, {
      signal: opts?.signal,
    });
  },

  async getLapAnalysis(sessionId: string, lapNumber: number, opts?: ApiOpts): Promise<LapAnalysis> {
    if (resolveFixture(opts)) {
      return _synthesizeFixtureLapAnalysis(sessionId, lapNumber, opts);
    }
    return jsonFetch<LapAnalysis>(
      `/api/sessions/${encodeURIComponent(sessionId)}/laps/${encodeURIComponent(String(lapNumber))}`,
      { signal: opts?.signal },
    );
  },

  async askCopilot(
    sessionId: string,
    question: string,
    recentTurns: CopilotMessage[] = [],
    opts?: ApiOpts,
  ): Promise<CopilotAnswer> {
    if (resolveFixture(opts)) {
      return _synthesizeFixtureCopilotAnswer(sessionId, question, recentTurns, opts);
    }
    return jsonFetch<CopilotAnswer>(`/api/sessions/${encodeURIComponent(sessionId)}/copilot`, {
      method: "POST",
      body: JSON.stringify({ question, recent_turns: recentTurns }),
      headers: { "Content-Type": "application/json" },
      signal: opts?.signal,
    });
  },

  async listSessions(
    params: SessionListParams = {},
    opts?: ApiOpts,
  ): Promise<SessionListResponse> {
    // Phase 1 — drives the Session History page at /sessions. No
    // fixture-mode synthesis: fixtures are deep-link targets, not list
    // entries. When the backend is unreachable in fixture mode the
    // page renders an empty state gracefully.
    if (resolveFixture(opts)) {
      return { sessions: [], total: 0, limit: params.limit ?? 50, offset: params.offset ?? 0 };
    }
    const qs = new URLSearchParams();
    if (params.limit != null) qs.set("limit", String(params.limit));
    if (params.offset != null) qs.set("offset", String(params.offset));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return jsonFetch<SessionListResponse>(`/api/sessions${suffix}`, {
      signal: opts?.signal,
    });
  },

  /**
   * Phase 3 — open an EventSource against the session's SSE stream.
   *
   * Returns a tear-down function the caller invokes on unmount. The
   * underlying EventSource handles reconnection automatically per the
   * HTML5 spec (browser retries after ~3 s by default; the backend's
   * stale-connection cleanup is independent).
   *
   * Caller passes a single `onEvent` callback because the event types
   * (connected / lap / no_telemetry / race_ended) are a discriminated
   * union — the consumer switches on `event.event`. This is simpler
   * than four separate optional callbacks and matches how the
   * SessionPage live panel consumes the stream.
   *
   * Fixture mode: replays a short mock live stream so the cockpit insight
   * surfaces can be developed and demoed without a live backend.
   */
  streamSession(
    sessionId: string,
    onEvent: (e: LiveStreamEvent) => void,
    opts?: { fixture?: boolean; onError?: (e: Event) => void },
  ): () => void {
    if (resolveFixture(opts)) {
      const timers = fixtureLiveStreamEvents(sessionId).map(({ delayMs, event }) =>
        window.setTimeout(() => onEvent(event), delayMs),
      );
      return () => timers.forEach((timer) => window.clearTimeout(timer));
    }
    const url = `/api/sessions/${encodeURIComponent(sessionId)}/stream`;
    const es = new EventSource(url);
    es.onmessage = (msg) => {
      try {
        const parsed = JSON.parse(msg.data) as LiveStreamEvent;
        onEvent(parsed);
        if (parsed.event === "race_ended" || parsed.event === "no_telemetry") {
          es.close();
        }
      } catch {
        // Swallow malformed payloads — backend guarantees JSON shape.
      }
    };
    if (opts?.onError) {
      es.onerror = opts.onError;
    }
    return () => es.close();
  },

  async getZone(
    sessionId: string,
    zoneId: string,
    mode: ZoneMode = "engineer",
    opts?: ApiOpts,
  ): Promise<Recommendation> {
    if (resolveFixture(opts)) {
      // Simulate a small in-flight delay so the Fan-Mode loading skeleton
      // gets a chance to render — the live watsonx call takes ~1.5-2.5s
      // (see fan_mode_demo capture log), this is a sub-second proxy.
      if (mode === "fan" || mode === "both") {
        await new Promise((r) => setTimeout(r, 350));
      }
      const s = fixtureSession(resolveFixtureName(opts, sessionId));
      const r = s.recommendations.find((rec) => rec.zone.zone_id === zoneId)
        ?? s.recommendations[0];
      if (!r) {
        throw new OverrideApiError(404, {
          error_code: "NOT_FOUND",
          message: `Zone ${zoneId} not found in fixture session.`,
          detail: null,
          request_id: "fixture",
        });
      }
      // Strip fan field for engineer-only mode; keep it (already populated)
      // for fan/both. The fan_mode_demo fixture ships with .fan filled in
      // for every recommendation; the layered_defense fixture has fan=null,
      // and we surface a small fallback rather than fabricating prose.
      if (mode === "engineer") {
        return { ...r, fan: null };
      }
      return r;
    }
    const url = `/api/sessions/${encodeURIComponent(sessionId)}/zones/${encodeURIComponent(zoneId)}?mode=${mode}`;
    return jsonFetch<Recommendation>(url, { signal: opts?.signal });
  },

  /**
   * FR-8 what-if perturbations. Hits POST /api/sessions/{id}/what-if in
   * live mode; in fixture mode, synthesizes a plausible WhatIfResult from
   * the current session's recommendations so the diff renderer has data
   * to render without a live backend. Synthesis is intentionally crude —
   * it preserves the "Before / After" pair shape and surfaces a note so
   * the UI's edge-case banner gets exercised during offline dev.
   */
  async runWhatIf(
    sessionId: string,
    request: WhatIfRequest,
    opts?: ApiOpts,
  ): Promise<WhatIfResult> {
    if (resolveFixture(opts)) {
      // Sub-second proxy for the live ~5-8s pipeline run
      await new Promise((r) => setTimeout(r, 400));
      return _synthesizeFixtureWhatIf(sessionId, request, opts);
    }
    return jsonFetch<WhatIfResult>(
      `/api/sessions/${encodeURIComponent(sessionId)}/what-if`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
        signal: opts?.signal,
      },
    );
  },

  /**
   * Live TORCS-volume status (v6 plan task 3.2). Polled by /upload's
   * banner; returns `{available: false, runs: []}` when the torcs profile
   * isn't running (which is the common case — no 404 noise in the UI).
   * Fixture mode short-circuits to "unavailable" to keep offline dev
   * predictable.
   */
  async torcsStatus(
    params: { limit?: number; offset?: number } = {},
    opts?: ApiOpts,
  ): Promise<TorcsStatusResponse> {
    if (resolveFixture(opts)) {
      return { available: false, runs: [], total: 0, limit: 50, offset: 0 };
    }
    const qs = new URLSearchParams();
    if (params.limit !== undefined) qs.set("limit", String(params.limit));
    if (params.offset !== undefined) qs.set("offset", String(params.offset));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return jsonFetch<TorcsStatusResponse>(`/api/torcs-status${suffix}`, {
      signal: opts?.signal,
    });
  },

  /**
   * Live TORCS-volume ingest (v6 plan task 3.2, hard floor). POSTs the
   * run_id to the live-ingest endpoint, which reads
   * /app/data/telemetry/<run_id>.jsonl from the shared torcs-telemetry
   * volume, runs the full pipeline, returns the Session.
   *
   * Fixture mode synthesizes via the same path as createSession so
   * offline UI dev can exercise the "ingest live run" affordance
   * without a backend.
   */
  async runTorcsLive(runId: string, opts?: ApiOpts): Promise<Session> {
    if (resolveFixture(opts)) {
      await new Promise((r) => setTimeout(r, 250));
      return fixtureSession(resolveFixtureName(opts));
    }
    return jsonFetch<Session>("/api/sessions/torcs-live", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: runId }),
      signal: opts?.signal,
    });
  },

  // Phase 2 — TORCS control plane (Start/Stop race over override-net daemon)
  async torcsControlStatus(opts?: ApiOpts): Promise<TorcsControlStatus> {
    // Always returns 200 from the backend (enabled/reachable booleans
    // carry the state). Fixture mode short-circuits to "disabled" so the
    // hosted demo and fixture flows behave identically.
    if (resolveFixture(opts)) {
      return {
        enabled: false, reachable: false, starting: false, active: false, state: null,
        session_id: null, last_error: null, last_exit_code: null, track: null, laps: null, launch_mode: null, detail: null,
      };
    }
    return jsonFetch<TorcsControlStatus>("/api/torcs/control-status", { signal: opts?.signal });
  },

  async torcsTracks(opts?: ApiOpts): Promise<TorcsTracksResponse> {
    if (resolveFixture(opts)) return { tracks: [] };
    return jsonFetch<TorcsTracksResponse>("/api/torcs/tracks", { signal: opts?.signal });
  },

  async listTorcsDriverProfiles(opts?: ApiOpts): Promise<TorcsDriverProfilesResponse> {
    if (resolveFixture(opts)) {
      return { profiles: [] };
    }
    return jsonFetch<TorcsDriverProfilesResponse>("/api/torcs/driver-profiles", {
      signal: opts?.signal,
    });
  },

  async getTorcsDriverProfile(profileId: string, opts?: ApiOpts): Promise<TorcsDriverProfile> {
    if (resolveFixture(opts)) {
      throw new Error("Driver profiles are unavailable in fixture mode.");
    }
    return jsonFetch<TorcsDriverProfile>(
      `/api/torcs/driver-profiles/${encodeURIComponent(profileId)}`,
      { signal: opts?.signal },
    );
  },

  async validateTorcsDriverConfig(
    config: TorcsDriverConfigWire,
    opts?: ApiOpts,
  ): Promise<TorcsDriverConfigValidateResponse> {
    if (resolveFixture(opts)) {
      return { valid: true, config };
    }
    return jsonFetch<TorcsDriverConfigValidateResponse>("/api/torcs/driver-profiles/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config }),
      signal: opts?.signal,
    });
  },

  async createTorcsDriverProfile(
    payload: { name: string; description?: string | null; config: TorcsDriverConfigWire },
    opts?: ApiOpts,
  ): Promise<TorcsDriverProfile> {
    if (resolveFixture(opts)) {
      throw new Error("Driver profiles are unavailable in fixture mode.");
    }
    return jsonFetch<TorcsDriverProfile>("/api/torcs/driver-profiles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: opts?.signal,
    });
  },

  async updateTorcsDriverProfile(
    profileId: string,
    payload: { name?: string; description?: string | null; config?: TorcsDriverConfigWire },
    opts?: ApiOpts,
  ): Promise<TorcsDriverProfile> {
    if (resolveFixture(opts)) {
      throw new Error("Driver profiles are unavailable in fixture mode.");
    }
    return jsonFetch<TorcsDriverProfile>(
      `/api/torcs/driver-profiles/${encodeURIComponent(profileId)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: opts?.signal,
      },
    );
  },

  async duplicateTorcsDriverProfile(
    profileId: string,
    payload: { name?: string; description?: string | null } = {},
    opts?: ApiOpts,
  ): Promise<TorcsDriverProfile> {
    if (resolveFixture(opts)) {
      throw new Error("Driver profiles are unavailable in fixture mode.");
    }
    return jsonFetch<TorcsDriverProfile>(
      `/api/torcs/driver-profiles/${encodeURIComponent(profileId)}/duplicate`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: opts?.signal,
      },
    );
  },

  async deleteTorcsDriverProfile(profileId: string, opts?: ApiOpts): Promise<void> {
    if (resolveFixture(opts)) {
      throw new Error("Driver profiles are unavailable in fixture mode.");
    }
    const res = await fetch(`/api/torcs/driver-profiles/${encodeURIComponent(profileId)}`, {
      method: "DELETE",
      signal: opts?.signal,
    });
    if (!res.ok && res.status !== 204) {
      let payload: ApiError;
      try {
        payload = (await res.json()) as ApiError;
      } catch {
        payload = {
          error_code: "INTERNAL_ERROR",
          message: `HTTP ${res.status}`,
          detail: null,
          request_id: "unknown",
        };
      }
      throw new OverrideApiError(res.status, payload);
    }
  },

  async startTorcsRace(
    params: TorcsStartRaceParams = {},
    opts?: ApiOpts,
  ): Promise<TorcsStartRaceResponse> {
    if (resolveFixture(opts)) {
      throw new Error("Cannot start a TORCS race in fixture mode — drop a fixture instead.");
    }
    return jsonFetch<TorcsStartRaceResponse>("/api/torcs/start-race", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        track: params.track ?? "aalborg",
        laps: params.laps ?? 75,
        track_name: params.track_name ?? null,
        notes: params.notes ?? null,
        driver_profile_id: params.driver_profile_id ?? "baseline",
        launch_mode:
          params.launch_mode
          ?? (params.auto_launch_torcs ? "headless_quickrace" : "cockpit_practice"),
        auto_launch_torcs: params.auto_launch_torcs ?? false,
      }),
      signal: opts?.signal,
    });
  },

  async stopTorcsRace(opts?: ApiOpts): Promise<TorcsStopRaceResponse> {
    if (resolveFixture(opts)) {
      return { status: "no_active_race", session_id: null, exit_code: null };
    }
    return jsonFetch<TorcsStopRaceResponse>("/api/torcs/stop-race", {
      method: "POST",
      signal: opts?.signal,
    });
  },

  async recoverTorcs(opts?: ApiOpts): Promise<TorcsRecoverResponse> {
    if (resolveFixture(opts)) {
      return { status: "recovered", session_id: null, state: "idle" };
    }
    return jsonFetch<TorcsRecoverResponse>("/api/torcs/recover", {
      method: "POST",
      signal: opts?.signal,
    });
  },

  /**
   * Delete a single session. Phase 4: ``removeTelemetry`` (default false)
   * opts into also unlinking the source JSONL from the shared
   * torcs-telemetry volume. Default keeps the JSONL so the session
   * can be re-ingested after a delete (matches the persisted "source
   * of truth" model — JSONL is the raw capture, Session is derived).
   */
  async deleteSession(
    sessionId: string,
    params: { removeTelemetry?: boolean } = {},
    opts?: ApiOpts,
  ): Promise<void> {
    if (resolveFixture(opts)) return;
    const qs = params.removeTelemetry ? "?remove_telemetry=true" : "";
    const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}${qs}`, {
      method: "DELETE",
      signal: opts?.signal,
    });
    if (!res.ok && res.status !== 204) {
      let payload: ApiError;
      try {
        payload = (await res.json()) as ApiError;
      } catch {
        payload = {
          error_code: "INTERNAL_ERROR",
          message: `HTTP ${res.status}`,
          detail: null,
          request_id: "unknown",
        };
      }
      throw new OverrideApiError(res.status, payload);
    }
  },

  /**
   * Bulk-delete N sessions in one request. Returns the count of sessions
   * actually unlinked (missing IDs are silently skipped — idempotent)
   * plus the count of JSONL captures removed (only non-zero when
   * ``removeTelemetry`` is true).
   */
  async bulkDeleteSessions(
    sessionIds: string[],
    params: { removeTelemetry?: boolean } = {},
    opts?: ApiOpts,
  ): Promise<BulkDeleteSessionsResponse> {
    if (resolveFixture(opts)) {
      return { deleted: 0, telemetry_removed: 0 };
    }
    return jsonFetch<BulkDeleteSessionsResponse>("/api/sessions/bulk-delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_ids: sessionIds,
        remove_telemetry: params.removeTelemetry ?? false,
      }),
      signal: opts?.signal,
    });
  },

  /**
   * Unlink a raw JSONL capture from the shared torcs-telemetry volume.
   * Idempotent: returns success whether or not the file existed. Does
   * NOT touch any Session that was previously ingested from this run.
   */
  async deleteTorcsRun(runId: string, opts?: ApiOpts): Promise<void> {
    if (resolveFixture(opts)) return;
    const res = await fetch(`/api/torcs/runs/${encodeURIComponent(runId)}`, {
      method: "DELETE",
      signal: opts?.signal,
    });
    if (!res.ok && res.status !== 204) {
      let payload: ApiError;
      try {
        payload = (await res.json()) as ApiError;
      } catch {
        payload = {
          error_code: "INTERNAL_ERROR",
          message: `HTTP ${res.status}`,
          detail: null,
          request_id: "unknown",
        };
      }
      throw new OverrideApiError(res.status, payload);
    }
  },
};
