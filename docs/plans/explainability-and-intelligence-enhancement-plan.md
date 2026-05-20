   Explainability and intelligence enhancement plan

  ## Problem

  OVERRIDE already runs the race-operation stack end-to-end. The next step is
  to
  turn that working system into a stronger product by making the intelligence
  legible, memorable, and collaborative: live explainability in the cockpit,
  richer post-race analysis, lap-level drill-downs, and a grounded race
  copilot.

  ## Current state

  • Live telemetry exists already.  GET /api/sessions/{session_id}/stream
  emits  connected ,  snapshot ,  lap ,  no_telemetry , and  race_ended
  events; the cockpit consumes those via  useLiveTelemetry .
  • Live explainability is still deterministic and shallow.
  ui/src/lib/cockpitTelemetry.ts  and  LiveStrategyInsight.tsx  derive simple
  pressure labels from the latest lap or in-progress snapshot, but there is no
  structured live intelligence event, evidence payload, or predictive
  explanation layer.
  • Real-time lap drill-down is not supported yet. The active-session flow
  intentionally hides post-race analysis until ingest completes, and the
  current live lap payload is too coarse for a rich lap-details surface during
  the race.
  • Post-race intelligence is already strong at the zone/recommendation layer.
  core/pipeline.py  orchestrates zone detection, optional forecast, regulation
  retrieval, Granite reasoning, deterministic validation, Guardian scoring,
  and recommendation assembly.
  • The session debrief surface is real and extensible.  SessionPage.tsx
  already renders KPI strip, energy curve, zone heatmap, recommendation cards,
  Fan Mode, and what-if comparisons.
  • Persistence is session-first, not report-first.  api/storage.py  persists
  summary ,  laps ,  forecast ,  recommendations ,  regulation_source , and
  driver_config_snapshot ; there is no stored report artifact, lap-analysis
  artifact, or copilot transcript/result cache yet.
  • No report engine or copilot exists yet. There is currently no  /report ,
  /laps/{lap} , or  /copilot  API surface and no dedicated UI for lap-level
  analysis, post-race reports, or conversational Q&A.

  ## Recommended direction

  1. Prioritize judge-visible intelligence over more automation. The platform
  already proves race operations. The highest-value work now is making
  reasoning understandable and compelling.
  2. Build on the existing session model instead of creating parallel
  subsystems. Live insights, lap details, race reports, and copilot answers
  should all reuse persisted session data and the current schema/API/UI
  patterns.
  3. Keep the live path deterministic first. Do not call Granite on every
  snapshot. Use heuristics and trend detection during the race, then let model-
  backed reasoning happen on completed laps, report generation, and user
  questions.
  4. Split domain contracts from transport contracts cleanly. Persisted/shared
  intelligence objects belong in  ingest/schema.py ; SSE envelopes and API-
  local live payloads stay in  api/main.py  and their TypeScript mirrors.
  5. Create shared structured intelligence objects before polishing the
  presentation. A stable backend shape should feed cockpit cards, session
  debriefs, future PDF export, and copilot answers.
  6. Use visible evidence trails, not faux chain-of-thought. If the UI shows
  "AI thinking," it should be an evidence/decision trace sourced from
  telemetry and recommendation artifacts rather than hidden reasoning
  simulation.

  ## Proposed phases

  ### Phase 0 — Contract skeleton

  Goal: lock the shared contracts before feature work fans out across backend,
  frontend, storage, and docs.

  • Add  LiveInsight ,  RaceReport , and  LapAnalysis  skeletons plus
  TypeScript mirrors.
  • Add empty or shape-only API contract tests for the new report/lap/live-
  insight surfaces.
  • Add schema/API/UI doc stubs so later phases fill in agreed contracts
  instead of inventing them.

  Acceptance

  • Phase 0 is done when backend, frontend, and docs all share the same
  placeholder contracts for live insights, report artifacts, and lap artifacts.

  ### Phase 1 — Live intelligence layer (recommended first)

  Goal: upgrade the cockpit from deterministic pressure labels to structured
  live insights that explain what is happening, why it matters, and what
  action is recommended.

  Locked scope

  • Phase 1 live intelligence is deterministic only. No per-snapshot Granite
  calls and no lap-close Granite phrasing in this milestone.
  • Lap drill-down pages are post-race only in this sprint. Real-time lap
  pages stay out of scope until lap-close artifacts exist.

  Backend

  • Extend  ingest/schema.py  with shared live-intelligence domain objects
  only where they are reused beyond transport boundaries; keep SSE event
  wrappers and live stream payloads in  api/main.py .
  • Add  analysis/live_intelligence.py  to derive deterministic live insights
  from snapshots plus completed laps.
  • Integrate the live intelligence engine into  GET /api/sessions/{id}/stream ,
  emitting deduplicated  insight  SSE events alongside  snapshot  and  lap .
  • Keep emission rate bounded and evidence grounded in telemetry values
  already present in the stream.

  Frontend

  • Extend  ui/src/api/types.ts  and  useLiveTelemetry.ts  to ingest and
  retain recent live insights.
  • Upgrade  LiveStrategyInsight.tsx  to render the latest structured insight,
  evidence bullets, and recommended action while preserving the current
  Engineer/Fan split.
  • Preserve the current deterministic fallback from  cockpitTelemetry.ts  /
  LiveStrategyInsight.tsx ; if live AI insight generation fails, the cockpit
  must keep rendering the existing deterministic path rather than degrading to
  a blank state.
  • Optionally add a compact "decision trace" or live insight log to the
  cockpit rather than a fake thought dump.
  • Add a fixture/demo story for cockpit-intelligence development so fixture
  mode can replay a mock live-insight stream instead of returning a no-op
  stream.

  Locked live wire contract

  • SSE event envelope:  {"event":"insight","insight":{...}}
  •  LiveInsight  fields:
    •  insight_id: str  — stable dedupe key for the stream/UI
    •  rule_id: str | null  — deterministic rule identifier such as
    energy_pressure_v1
    •  kind: "strategy_recommendation" | "anomaly" | "prediction" |
    "explanation"
    •  severity: "low" | "medium" | "high"
    •  headline: str
    •  message: str
    •  recommended_action: str | null
    •  confidence: "low" | "medium" | "high"
    •  evidence: list[str]
    •  lap: int | null
    •  sector: 1 | 2 | 3 | null
  • No  source  field in Phase 1; all live insights are deterministic by
  contract in this milestone.
  •  insight_id  generation rule:  li_{rule_id}_l{lap or 0}_s{sector or 0} .
  • Backend dedupe rule: do not emit consecutive duplicate insights for a
  connection when  insight_id ,  severity , and  message  are unchanged.
  • Frontend retention rule: keep the latest 5 unique insights, upserting by
  insight_id .

  Initial rule set

  • Energy pressure / deploy-over-harvest trend
  • Battery depletion prediction from recent SoC slope
  • Sudden pace drop or instability signal
  • Strategy mode recommendation ( recover ,  balanced ,  conserve ,  push )
  with confidence/evidence

  Acceptance

  • Phase 1 is done when the cockpit renders real deterministic  insight  SSE
  events, preserves the existing deterministic fallback on failure, and
  fixture mode can replay a mock live-insight stream for UI development/demo
  work.

  ### Phase 2 — Post-race intelligence and lap drill-down

  Goal: turn the existing session debrief into an engineer-grade post-race
  intelligence surface.

  Backend

  • Add report-oriented schema(s) such as  RaceReport ,  LapAnalysis , and
  small supporting structs in  ingest/schema.py .
  • Create  analysis/post_race_report.py  and a lap-analysis module that
  compute key moments, scoring, pace/energy deltas, and lap-by-lap
  intelligence from persisted session data.
  • Add session-scoped endpoints for report retrieval and lap detail retrieval
  before attempting PDF export.
  • Cache report and lap intelligence lazily from day one using the existing
  session-artifact storage pattern rather than recomputing on every request.
  • Reuse existing recommendations, what-if results, and regulation-grounded
  evidence instead of duplicating logic.

  Frontend

  • Add a post-race report panel to  SessionPage.tsx .
  • Add a dedicated lap route at  /session/:sessionId/laps/:lapNumber  linked
  from lap tiles/charts so users can inspect one lap at a time.
  • Surface AI race summary, key moments, driver/battery efficiency scoring,
  and lap comparisons in the debrief.

  Recommendation

  • Ship JSON/UI first. Generate PDF only after the report object and layout
  are stable.

  Acceptance

  • Phase 2 is done when a completed session can load a cached  report.json ,
  open  /session/:sessionId/laps/:lapNumber , and render report plus lap-
  detail UI from cached session artifacts.

  ### Phase 3 — Session copilot

  Goal: add a collaborative Q&A layer over a completed session so users can
  ask why, compare, and diagnose.

  Backend

  • Introduce a session-scoped copilot subsystem ( copilot/ ) with retrieval,
  intent routing, prompt assembly, and response schema.
  • Add focused tools for lap comparison, strategy explanation, sector
  diagnosis, battery analysis, and forecast interpretation.
  • Add  /api/sessions/{id}/copilot  using retrieved session context rather
  than dumping whole sessions into prompts.
  • Keep copilot stateless on the server for this milestone: the client
  supplies recent turns, and the backend does not persist transcripts or long-
  term memory.

  Frontend

  • Add a  RaceCopilotPanel  with suggested prompts, answer cards, and
  lap/zone jump links.
  • Ensure answers cite laps, metrics, recommendations, and regulations when
  available.

  Recommendation

  • Keep the copilot session-scoped first. Only add cross-session
  memory/comparison after the single-session experience is strong.

  Acceptance

  • Phase 3 is done when a completed session can answer grounded questions
  through the stateless copilot endpoint and UI, with answers citing
  laps/metrics/recommendations and linking back into the debrief.

  ### Phase 4 — Presentation polish and export

  Goal: make the intelligence layer demo-ready and memorable without
  undermining explainability.

  Candidate work

  • richer loading/transition states
  • race state machine visuals
  • predictive overlays on existing charts
  • decision-trace panel for live intelligence
  • downloadable PDF report generated from the same  RaceReport  object

  Guardrail

  • Presentation polish should sit on top of real structured intelligence
  outputs, not precede them.

  ## Cross-cutting implementation notes

  • Reuse the current file-based session storage first; add lazy-cached
  report/lap intelligence artifacts from the start and extend  api/storage.py
  with targeted helpers rather than introducing a database.
  • Reserve the artifact layout now:
    •  data/sessions/{session_id}/report.json
    •  data/sessions/{session_id}/laps/{lap_number}.json
    • no server-side copilot transcript artifact in this milestone
  • Keep all user-facing language within the existing decision-support
  guardrails: "supports", "explains", "highlights", "recommends" — never
  "decides", "autonomously", or "optimal".
  • Never hardcode FIA article numbers; continue using  RegulationSource  at
  runtime only.
  • Update  docs/03-architecture.md ,  docs/04-schema.md ,  docs/04-api.md ,
  and  docs/04-ui-ux-design.md  as part of implementation because the feature
  set adds new surfaces and contracts.
  • Validate implementation with the existing repo commands:  .venv/bin/pytest ,
  cd ui && npm run typecheck , and  cd ui && npm run build .
  • Keep  SessionComparePage  lightweight; deeper "compare lap 4 vs lap 8"
  value should land in the dedicated lap route and copilot rather than by
  expanding the compare screen early.

  ## Recommended delivery order

  0. Contract skeleton
  1. Live intelligence layer
  2. Post-race report + lap detail
  3. Session copilot
  4. PDF/export + cinematic polish

  This order gives the fastest judge-visible improvement while reusing the
  code
  that already exists.

  ## Confirmed priority

  • First implementation target confirmed: Phase 1 — Live intelligence layer.

  ## Competition sprint framing

  • Must ship: Phase 0 + Phase 1
  • Partial target: Phase 2 (report panel + cached report/lap artifacts +
  dedicated lap route)
  • Thin follow-on if time remains: Phase 3