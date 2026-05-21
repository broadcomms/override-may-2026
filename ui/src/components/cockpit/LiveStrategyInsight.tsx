import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { OverrideApiError, api } from "@/api/client";
import type {
  CopilotAnswer,
  CopilotRequestContext,
  LiveInsight,
  LiveLapSnapshot,
  LiveLapStats,
  Recommendation,
} from "@/api/types";
import { ModeToggle, type Mode } from "@/components/ModeToggle";
import type { LiveStreamState } from "@/hooks/useLiveTelemetry";
import { deriveLiveSignal } from "@/lib/cockpitTelemetry";

interface Props {
  insights: LiveInsight[];
  sessionId: string | null;
  latestSnapshot: LiveLapSnapshot | null;
  latestLap: LiveLapStats | null;
  previousLap: LiveLapStats | null;
  recentLaps: LiveLapStats[];
  streamState: LiveStreamState;
  recommendation?: Recommendation | null;
}

export function LiveStrategyInsight({
  insights,
  sessionId,
  latestSnapshot,
  latestLap,
  previousLap,
  recentLaps,
  streamState,
  recommendation,
}: Props) {
  const [mode, setMode] = useState<Mode>("engineer");
  const signal = deriveLiveSignal(latestLap, previousLap);
  const latestInsight = insights[0] ?? null;

  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted">
            AI race engineer
          </div>
          <div className="mt-1 text-sm text-muted">
            Instant telemetry guardrails stay deterministic, and each completed lap now requests a Granite-backed live explanation.
          </div>
        </div>
        <ModeToggle mode={mode} onChange={setMode} />
      </header>

      {mode === "engineer" ? (
        <EngineerBody
          insights={insights}
          latestInsight={latestInsight}
          sessionId={sessionId}
          latestSnapshot={latestSnapshot}
          recentLaps={recentLaps}
          streamState={streamState}
          signal={signal}
          recommendation={recommendation ?? null}
        />
      ) : (
        <FanBody
          insights={insights}
          latestInsight={latestInsight}
          latestSnapshot={latestSnapshot}
          signal={signal}
          streamState={streamState}
        />
      )}
    </section>
  );
}

function EngineerBody({
  insights,
  latestInsight,
  sessionId,
  latestSnapshot,
  recentLaps,
  streamState,
  signal,
  recommendation,
}: {
  insights: LiveInsight[];
  latestInsight: LiveInsight | null;
  sessionId: string | null;
  latestSnapshot: LiveLapSnapshot | null;
  recentLaps: LiveLapStats[];
  streamState: LiveStreamState;
  signal: ReturnType<typeof deriveLiveSignal>;
  recommendation: Recommendation | null;
}) {
  const graniteLive = useLiveGraniteExplanation({
    sessionId,
    latestSnapshot,
    recentLaps,
    insights,
    streamState,
  });

  if (recommendation) {
    return (
      <div className="space-y-3">
        <div className="text-[11px] uppercase tracking-wider text-accent">
          Post-lap analysis available
        </div>
        <p className="text-lg text-text">{recommendation.reasoning.recommendation}</p>
        <p className="text-sm text-muted">
          Validation and Guardian review are attached to the completed recommendation.
        </p>
      </div>
      );
  }

  if (latestInsight) {
    return (
      <div className="space-y-3">
        <GraniteLiveExplainer state={graniteLive} sessionId={sessionId} streamState={streamState} />
        <div className="text-[11px] uppercase tracking-wider text-accent">
          Instant telemetry guardrail: {kindLabel(latestInsight)} · {latestInsight.severity}
        </div>
        <h3 className="text-lg text-text">{latestInsight.headline}</h3>
        <p className="text-sm text-text">{latestInsight.message}</p>
        {latestInsight.recommended_action && (
          <p className="text-sm text-muted">{latestInsight.recommended_action}</p>
        )}
        {latestInsight.evidence.length > 0 && (
          <ul className="space-y-1 text-sm text-muted">
            {latestInsight.evidence.slice(0, 3).map((item) => (
              <li key={item}>- {item}</li>
            ))}
          </ul>
        )}
        <p className="text-sm text-muted">
          Instant race-state guardrail from live telemetry. Completed laps now trigger a Granite-backed explanation above when the copilot runtime responds successfully.
        </p>
        <RecentInsightList insights={insights} />
        {sessionId && streamState.kind === "ended" && (
          <Link
            to={`/session/${encodeURIComponent(sessionId)}`}
            className="inline-flex rounded-pill border border-border px-3 py-1.5 text-sm text-accent transition-colors hover:text-text"
          >
            Open session debrief
          </Link>
        )}
      </div>
    );
  }

  // Snapshot-based live signal: deterministic balance label, clearly labelled.
  if (latestSnapshot) {
    return (
      <div className="space-y-3">
        <GraniteLiveExplainer state={graniteLive} sessionId={sessionId} streamState={streamState} />
        <div className="text-[11px] uppercase tracking-wider text-accent">
          Live signal: {latestSnapshot.balance_label}
        </div>
        <p className="text-lg text-text">
          {snapshotEngineerDetail(latestSnapshot)}
        </p>
        <p className="text-sm text-muted">
          Instant telemetry signal only. Granite-backed live explanation starts after the first completed lap closes.
        </p>
        {sessionId && streamState.kind === "ended" && (
          <Link
            to={`/session/${encodeURIComponent(sessionId)}`}
            className="inline-flex rounded-pill border border-border px-3 py-1.5 text-sm text-accent transition-colors hover:text-text"
          >
            Open session debrief
          </Link>
        )}
      </div>
    );
  }

  if (!signal) {
    return (
      <WaitingBody sessionId={sessionId} streamState={streamState} />
    );
  }

  return (
    <div className="space-y-3">
      <GraniteLiveExplainer state={graniteLive} sessionId={sessionId} streamState={streamState} />
      <div className="text-[11px] uppercase tracking-wider text-accent">
        Live signal: {signal.pressureLabel}
      </div>
      <p className="text-lg text-text">{signal.pressureDetail}</p>
      <p className="text-sm text-muted">{signal.suggestedAction}</p>
      <p className="text-sm text-muted">
        Review: deterministic live signal. Granite-backed lap-close explanation appears above once completed-lap context is available.
      </p>
      {sessionId && streamState.kind === "ended" && (
        <Link
          to={`/session/${encodeURIComponent(sessionId)}`}
          className="inline-flex rounded-pill border border-border px-3 py-1.5 text-sm text-accent transition-colors hover:text-text"
        >
          Open session debrief
        </Link>
      )}
    </div>
  );
}

const AUTO_LIVE_EXPLAINER_QUESTION =
  "Explain the latest live race state using the newest completed lap, the current telemetry snapshot, and the recent live insights. Keep it concise and recommend the next energy move.";

type GraniteLiveState =
  | { kind: "idle" | "loading" }
  | { kind: "ready"; answer: CopilotAnswer }
  | { kind: "fallback"; answer: CopilotAnswer }
  | { kind: "error"; message: string };

function useLiveGraniteExplanation({
  sessionId,
  latestSnapshot,
  recentLaps,
  insights,
  streamState,
}: {
  sessionId: string | null;
  latestSnapshot: LiveLapSnapshot | null;
  recentLaps: LiveLapStats[];
  insights: LiveInsight[];
  streamState: LiveStreamState;
}): GraniteLiveState {
  const [state, setState] = useState<GraniteLiveState>({ kind: "idle" });
  const latestClosedLap = recentLaps[recentLaps.length - 1] ?? null;
  const requestContext = useMemo<CopilotRequestContext | null>(() => {
    if (!sessionId || !latestClosedLap) return null;
    return {
      mode: "live_race",
      lap_number: latestSnapshot?.lap ?? latestClosedLap.lap ?? null,
      live: {
        latest_snapshot: latestSnapshot,
        completed_laps: recentLaps.slice(-5),
        insights: insights.slice(0, 5),
        race_state: streamState.kind === "ended" ? "idle" : null,
      },
    };
  }, [insights, latestClosedLap, latestSnapshot, recentLaps, sessionId, streamState.kind]);

  const requestKey = useMemo(() => {
    if (!sessionId || !latestClosedLap) return null;
    return `${sessionId}:${latestClosedLap.lap}`;
  }, [latestClosedLap, sessionId]);

  useEffect(() => {
    if (!sessionId || !requestContext || !requestKey) {
      setState({ kind: "idle" });
      return;
    }

    let cancelled = false;
    const controller = new AbortController();
    setState({ kind: "loading" });

    api.askCopilot(sessionId, AUTO_LIVE_EXPLAINER_QUESTION, [], requestContext, {
      signal: controller.signal,
    }).then(
      (answer) => {
        if (cancelled) return;
        if (answer.engine === "granite") {
          setState({ kind: "ready", answer });
          return;
        }
        setState({ kind: "fallback", answer });
      },
      (error) => {
        if (cancelled) return;
        setState({
          kind: "error",
          message:
            error instanceof OverrideApiError
              ? error.payload.message
              : error instanceof Error
                ? error.message
                : "Granite live explanation unavailable.",
        });
      },
    );

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [requestKey, sessionId]);

  return state;
}

function GraniteLiveExplainer({
  state,
  sessionId,
  streamState,
}: {
  state: GraniteLiveState;
  sessionId: string | null;
  streamState: LiveStreamState;
}) {
  if (state.kind === "idle") return null;

  if (state.kind === "loading") {
    return (
      <div className="space-y-1 rounded-md border border-accent/25 bg-accent/8 px-3 py-3">
        <div className="text-[11px] uppercase tracking-wider text-accent">
          Granite live explainer
        </div>
        <p className="text-sm text-muted">
          Analyzing the newest completed lap with the live race context.
        </p>
      </div>
    );
  }

  if (state.kind === "error") {
    return (
      <div className="space-y-1 rounded-md border border-border bg-surface-2/60 px-3 py-3">
        <div className="text-[11px] uppercase tracking-wider text-warning">
          Granite live explainer unavailable
        </div>
        <p className="text-sm text-muted">{state.message}</p>
      </div>
    );
  }

  if (state.kind === "fallback") {
    return (
      <div className="space-y-1 rounded-md border border-border bg-surface-2/60 px-3 py-3">
        <div className="text-[11px] uppercase tracking-wider text-warning">
          Live explanation fallback
        </div>
        <p className="text-sm text-muted">
          The live copilot returned a deterministic fallback instead of a Granite answer, so the instant telemetry guardrail below remains the primary signal.
        </p>
        {sessionId && streamState.kind === "ended" && (
          <Link
            to={`/session/${encodeURIComponent(sessionId)}`}
            className="inline-flex rounded-pill border border-border px-3 py-1.5 text-sm text-accent transition-colors hover:text-text"
          >
            Open session debrief
          </Link>
        )}
      </div>
    );
  }

  if (state.kind !== "ready") return null;

  const { answer } = state;
  return (
    <div className="space-y-2 rounded-md border border-accent/30 bg-accent/8 px-3 py-3">
      <div className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-wider text-accent">
        <span>Granite live explainer</span>
        <span className="text-muted">· {answer.confidence}</span>
      </div>
      <p className="text-sm text-text">{answer.answer}</p>
      {answer.supporting_laps.length > 0 && (
        <p className="text-xs text-muted">
          Supporting laps: {answer.supporting_laps.join(", ")}
        </p>
      )}
    </div>
  );
}

function FanBody({
  insights,
  latestInsight,
  latestSnapshot,
  signal,
  streamState,
}: {
  insights: LiveInsight[];
  latestInsight: LiveInsight | null;
  latestSnapshot: LiveLapSnapshot | null;
  signal: ReturnType<typeof deriveLiveSignal>;
  streamState: LiveStreamState;
}) {
  if (latestInsight) {
    return (
      <div className="space-y-3">
        <div className="text-[11px] uppercase tracking-wider text-accent">
          Live insight
        </div>
        <p className="text-lg text-text">{latestInsight.headline}</p>
        <p className="text-sm text-muted">{fanFriendlyInsight(latestInsight)}</p>
        {latestInsight.recommended_action && (
          <p className="text-sm text-muted">{latestInsight.recommended_action}</p>
        )}
        <RecentInsightList insights={insights} />
      </div>
    );
  }

  if (latestSnapshot) {
    return (
      <div className="space-y-3">
        <div className="text-[11px] uppercase tracking-wider text-accent">
          Live signal
        </div>
        <p className="text-lg text-text">{snapshotFanSummary(latestSnapshot)}</p>
        <p className="text-sm text-muted">
          Post-lap analysis can upgrade this with a grounded engineer recommendation after the review completes.
        </p>
      </div>
    );
  }

  if (!signal) {
    return (
      <p className="text-sm text-muted">
        {streamState.kind === "no_telemetry"
          ? streamState.message
          : "Waiting for the first completed lap before the cockpit explains the battery story in plain language."}
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="text-[11px] uppercase tracking-wider text-accent">
        Live signal
      </div>
      <p className="text-lg text-text">{signal.fanSummary}</p>
      <p className="text-sm text-muted">
        Post-lap analysis can upgrade this with a grounded engineer recommendation after the review completes.
      </p>
    </div>
  );
}

function RecentInsightList({ insights }: { insights: LiveInsight[] }) {
  if (insights.length <= 1) return null;
  return (
    <div className="space-y-2 border-t border-border/70 pt-3">
      <div className="text-[11px] uppercase tracking-wider text-muted">Recent insight trace</div>
      <div className="space-y-1 text-xs text-muted">
        {insights.slice(1).map((insight) => (
          <div key={insight.insight_id}>
            {insight.headline}
            {insight.lap != null ? ` · lap ${insight.lap}` : ""}
            {insight.sector != null ? ` · sector ${insight.sector}` : ""}
          </div>
        ))}
      </div>
    </div>
  );
}

function WaitingBody({
  sessionId,
  streamState,
}: {
  sessionId: string | null;
  streamState: LiveStreamState;
}) {
  let message =
    "Waiting for the first completed lap. OVERRIDE will highlight live energy pressure as soon as telemetry closes a lap.";
  if (streamState.kind === "no_telemetry") message = streamState.message;
  if (streamState.kind === "ended") {
    message = "Race ended before a strong live energy signal formed. Use the completed session debrief for the full review.";
  }

  return (
    <div className="space-y-3">
      <div className="text-[11px] uppercase tracking-wider text-muted">
        Review pending
      </div>
      <p className="text-sm text-muted">{message}</p>
      {sessionId && streamState.kind === "ended" && (
        <Link
          to={`/session/${encodeURIComponent(sessionId)}`}
          className="inline-flex rounded-pill border border-border px-3 py-1.5 text-sm text-accent transition-colors hover:text-text"
        >
          Open session debrief
        </Link>
      )}
    </div>
  );
}

/** Deterministic engineer detail for an in-progress lap snapshot. */
function snapshotEngineerDetail(snap: LiveLapSnapshot): string {
  const soc = Math.round(snap.soc_estimate * 100);
  const net = (snap.harvest_mj - snap.deploy_mj).toFixed(2);
  switch (snap.balance_label) {
    case "spending":
      return `Battery at ${soc}%. Net energy this lap: ${net} MJ. Deploy rate exceeds harvest — energy balance trending negative.`;
    case "recovering":
      return `Battery at ${soc}%. Net energy this lap: +${net} MJ. Harvest exceeds deploy — energy balance trending positive.`;
    case "balanced":
      return `Battery at ${soc}%. Net energy this lap: ${net} MJ. Harvest and deploy are closely matched — energy balance stable.`;
  }
}

/** Deterministic fan summary for an in-progress lap snapshot. */
function snapshotFanSummary(snap: LiveLapSnapshot): string {
  const soc = Math.round(snap.soc_estimate * 100);
  switch (snap.balance_label) {
    case "spending":
      return `Battery is at ${soc}% and the car is using more energy than it's recovering. The hybrid system is working hard this lap.`;
    case "recovering":
      return `Battery is at ${soc}% and climbing. The car is harvesting more energy than it's using — a good sign heading into the next stint.`;
    case "balanced":
      return `Battery is at ${soc}% and holding steady. Energy in and out are evenly matched right now.`;
  }
}

function kindLabel(insight: LiveInsight): string {
  switch (insight.kind) {
    case "strategy_recommendation":
      return "strategy";
    case "anomaly":
      return "anomaly";
    case "prediction":
      return "prediction";
    case "explanation":
      return "explanation";
  }
}

function fanFriendlyInsight(insight: LiveInsight): string {
  if (insight.lap == null) return insight.message;
  const sector = insight.sector != null ? `, sector ${insight.sector}` : "";
  return `${insight.message} This trend is centered on lap ${insight.lap}${sector}.`;
}
