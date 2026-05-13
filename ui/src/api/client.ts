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
import layeredDefenseFixtureRaw from "@fixtures/layered_defense_demo.json";
import torcsEngineerFixtureRaw from "@fixtures/torcs_engineer_demo.json";
import type {
  ApiError,
  HealthResponse,
  LiveStreamEvent,
  Recommendation,
  RegulationSource,
  Session,
  SessionListParams,
  SessionListResponse,
  SessionSummary,
  TorcsControlStatus,
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

export type FixtureName = "fan_mode" | "engineer_happy" | "layered_defense" | "torcs_engineer";

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
  };
  const reg = recommendation.reasoning.regulation_citation;
  return {
    summary,
    laps: [],
    forecast: null,
    recommendations: [recommendation],
    regulation_source: reg ? reg.source : null,
  };
}

export function fixtureSession(name: FixtureName = "fan_mode"): Session {
  switch (name) {
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
  if (sessionId.includes("torcs_engineer")) return "torcs_engineer";
  if (sessionId.includes("layered_defense")) return "layered_defense";
  if (sessionId.includes("engineer_happy")) return "engineer_happy";
  return "fan_mode";
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
   * Fixture mode: returns a no-op teardown immediately; fixtures are
   * deep-link demo assets, not live sessions, so there's nothing
   * meaningful to stream.
   */
  streamSession(
    sessionId: string,
    onEvent: (e: LiveStreamEvent) => void,
    opts?: { fixture?: boolean; onError?: (e: Event) => void },
  ): () => void {
    if (opts?.fixture) {
      return () => {};
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
  async torcsStatus(opts?: ApiOpts): Promise<TorcsStatusResponse> {
    if (resolveFixture(opts)) {
      return { available: false, runs: [] };
    }
    return jsonFetch<TorcsStatusResponse>("/api/torcs-status", {
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
        enabled: false, reachable: false, active: false, state: null,
        session_id: null, last_error: null, last_exit_code: null, detail: null,
      };
    }
    return jsonFetch<TorcsControlStatus>("/api/torcs/control-status", { signal: opts?.signal });
  },

  async torcsTracks(opts?: ApiOpts): Promise<TorcsTracksResponse> {
    if (resolveFixture(opts)) return { tracks: [] };
    return jsonFetch<TorcsTracksResponse>("/api/torcs/tracks", { signal: opts?.signal });
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
        laps: params.laps ?? 5,
        track_name: params.track_name ?? null,
        notes: params.notes ?? null,
        auto_launch_torcs: params.auto_launch_torcs ?? true,
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

  async deleteSession(sessionId: string, opts?: ApiOpts): Promise<void> {
    if (resolveFixture(opts)) return;
    const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`, {
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
