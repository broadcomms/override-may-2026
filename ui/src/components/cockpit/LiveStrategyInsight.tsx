import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
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
            Instant telemetry guardrails stay deterministic. OVERRIDE now auto-requests a Granite readout on closed laps, and you can refresh either live explainer on demand mid-race.
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
          sessionId={sessionId}
          latestSnapshot={latestSnapshot}
          recentLaps={recentLaps}
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
    question: AUTO_ENGINEER_EXPLAINER_QUESTION,
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
        <GraniteLiveExplainer
          state={graniteLive.state}
          canRefresh={graniteLive.canRefresh}
          onRefresh={graniteLive.refresh}
          sessionId={sessionId}
          streamState={streamState}
          flavor="engineer"
        />
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
        <GraniteLiveExplainer
          state={graniteLive.state}
          canRefresh={graniteLive.canRefresh}
          onRefresh={graniteLive.refresh}
          sessionId={sessionId}
          streamState={streamState}
          flavor="engineer"
        />
        <div className="text-[11px] uppercase tracking-wider text-accent">
          Live signal: {latestSnapshot.balance_label}
        </div>
        <p className="text-lg text-text">
          {snapshotEngineerDetail(latestSnapshot)}
        </p>
        <p className="text-sm text-muted">
          Instant telemetry signal only. You can refresh Granite immediately for a live readout, and completed laps still trigger automatic refreshes.
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
      <GraniteLiveExplainer
        state={graniteLive.state}
        canRefresh={graniteLive.canRefresh}
        onRefresh={graniteLive.refresh}
        sessionId={sessionId}
        streamState={streamState}
        flavor="engineer"
      />
      <div className="text-[11px] uppercase tracking-wider text-accent">
        Live signal: {signal.pressureLabel}
      </div>
      <p className="text-lg text-text">{signal.pressureDetail}</p>
      <p className="text-sm text-muted">{signal.suggestedAction}</p>
      <p className="text-sm text-muted">
        Review: deterministic live signal. Granite can be refreshed on demand here, and completed laps still trigger automatic explanation refreshes.
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

const AUTO_ENGINEER_EXPLAINER_QUESTION =
  "Explain the latest live race state using the newest completed lap, the current telemetry snapshot, and the recent live insights. Keep it concise, grounded, and recommend the next energy move.";

const AUTO_FAN_EXPLAINER_QUESTION =
  "Call the current race moment like a live motorsport commentator for a fan. Use plain language, stay grounded in the latest telemetry and completed lap context, highlight the energy story, and say what to watch next.";

type GraniteLiveState =
  | { kind: "idle" | "loading" }
  | { kind: "ready"; answer: CopilotAnswer }
  | { kind: "fallback"; answer: CopilotAnswer }
  | { kind: "error"; message: string };

type LiveExplainerFlavor = "engineer" | "fan";

function useLiveGraniteExplanation({
  sessionId,
  latestSnapshot,
  recentLaps,
  insights,
  streamState,
  question,
}: {
  sessionId: string | null;
  latestSnapshot: LiveLapSnapshot | null;
  recentLaps: LiveLapStats[];
  insights: LiveInsight[];
  streamState: LiveStreamState;
  question: string;
}): {
  state: GraniteLiveState;
  canRefresh: boolean;
  refresh: () => void;
} {
  const [state, setState] = useState<GraniteLiveState>({ kind: "idle" });
  const [refreshNonce, setRefreshNonce] = useState(0);
  const latestClosedLap = recentLaps[recentLaps.length - 1] ?? null;
  const canRefresh = Boolean(
    sessionId
      && (latestSnapshot != null
        || latestClosedLap != null
        || insights.length > 0
        || streamState.kind === "ended"),
  );
  const requestContext = useMemo<CopilotRequestContext | null>(() => {
    if (!canRefresh || !sessionId) return null;
    return {
      mode: "live_race",
        lap_number: latestSnapshot?.lap ?? latestClosedLap?.lap ?? null,
      live: {
        latest_snapshot: latestSnapshot,
        completed_laps: recentLaps.slice(-5),
        insights: insights.slice(0, 5),
        race_state: streamState.kind === "ended" ? "idle" : null,
      },
    };
  }, [canRefresh, insights, latestClosedLap, latestSnapshot, recentLaps, sessionId, streamState.kind]);

  const autoRequestKey = useMemo(() => {
    if (!sessionId || !latestClosedLap) return null;
    return `${sessionId}:${latestClosedLap.lap}`;
  }, [latestClosedLap, sessionId]);

  const refresh = useCallback(() => {
    if (!canRefresh) return;
    setRefreshNonce((current) => current + 1);
  }, [canRefresh]);

  useEffect(() => {
    if (!sessionId || !requestContext || (autoRequestKey == null && refreshNonce === 0)) {
      setState({ kind: "idle" });
      return;
    }

    let cancelled = false;
    const controller = new AbortController();
    setState({ kind: "loading" });

    api.askCopilot(sessionId, question, [], requestContext, {
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
  }, [autoRequestKey, question, refreshNonce, sessionId]);

  return { state, canRefresh, refresh };
}

function GraniteLiveExplainer({
  state,
  canRefresh,
  onRefresh,
  sessionId,
  streamState,
  flavor,
}: {
  state: GraniteLiveState;
  canRefresh: boolean;
  onRefresh: () => void;
  sessionId: string | null;
  streamState: LiveStreamState;
  flavor: LiveExplainerFlavor;
}) {
  const config = flavor === "fan"
    ? {
        title: "Granite live commentary",
        loading: "Calling the current race moment in fan-friendly language.",
        idle: "Refresh to hear a fresh live call of the race without reloading the cockpit.",
        fallbackTitle: "Live commentary fallback",
        fallbackBody:
          "The live copilot returned a deterministic fallback instead of a Granite commentary pass, so the live signal below remains the primary view.",
      }
    : {
        title: "Granite live explainer",
        loading: "Analyzing the newest race context with Granite.",
        idle: "Refresh to pull a fresh Granite explanation of the current race moment without reloading the page.",
        fallbackTitle: "Live explanation fallback",
        fallbackBody:
          "The live copilot returned a deterministic fallback instead of a Granite answer, so the instant telemetry guardrail below remains the primary signal.",
      };

  if (state.kind === "idle") {
    if (!canRefresh) return null;
    return (
      <LiveExplainerShell
        tone="neutral"
        title={config.title}
        actionLabel="Refresh now"
        actionDisabled={false}
        onRefresh={onRefresh}
      >
        <p className="text-sm text-muted">{config.idle}</p>
      </LiveExplainerShell>
    );
  }

  if (state.kind === "loading") {
    return (
      <LiveExplainerShell
        tone="accent"
        title={config.title}
        actionLabel="Refreshing..."
        actionDisabled
        onRefresh={onRefresh}
      >
        <p className="text-sm text-muted">{config.loading}</p>
      </LiveExplainerShell>
    );
  }

  if (state.kind === "error") {
    return (
      <LiveExplainerShell
        tone="warning"
        title={`${config.title} unavailable`}
        actionLabel="Retry"
        actionDisabled={!canRefresh}
        onRefresh={onRefresh}
      >
        <p className="text-sm text-muted">{state.message}</p>
      </LiveExplainerShell>
    );
  }

  if (state.kind === "fallback") {
    return (
      <LiveExplainerShell
        tone="neutral"
        title={config.fallbackTitle}
        actionLabel="Refresh now"
        actionDisabled={!canRefresh}
        onRefresh={onRefresh}
      >
        <p className="text-sm text-muted">{config.fallbackBody}</p>
        {sessionId && streamState.kind === "ended" && (
          <Link
            to={`/session/${encodeURIComponent(sessionId)}`}
            className="inline-flex rounded-pill border border-border px-3 py-1.5 text-sm text-accent transition-colors hover:text-text"
          >
            Open session debrief
          </Link>
        )}
      </LiveExplainerShell>
    );
  }

  if (state.kind !== "ready") return null;

  const { answer } = state;
  return (
    <LiveExplainerShell
      tone="accent"
      title={config.title}
      actionLabel="Refresh now"
      actionDisabled={!canRefresh}
      onRefresh={onRefresh}
    >
      <div className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-wider text-accent">
        <span className="text-muted">confidence {answer.confidence}</span>
      </div>
      <p className="text-sm text-text">{answer.answer}</p>
      {answer.supporting_laps.length > 0 && (
        <p className="text-xs text-muted">
          Supporting laps: {answer.supporting_laps.join(", ")}
        </p>
      )}
    </LiveExplainerShell>
  );
}

function FanBody({
  insights,
  latestInsight,
  sessionId,
  latestSnapshot,
  recentLaps,
  signal,
  streamState,
}: {
  insights: LiveInsight[];
  latestInsight: LiveInsight | null;
  sessionId: string | null;
  latestSnapshot: LiveLapSnapshot | null;
  recentLaps: LiveLapStats[];
  signal: ReturnType<typeof deriveLiveSignal>;
  streamState: LiveStreamState;
}) {
  const graniteLive = useLiveGraniteExplanation({
    sessionId,
    latestSnapshot,
    recentLaps,
    insights,
    streamState,
    question: AUTO_FAN_EXPLAINER_QUESTION,
  });

  if (latestInsight) {
    return (
      <div className="space-y-3">
        <GraniteLiveExplainer
          state={graniteLive.state}
          canRefresh={graniteLive.canRefresh}
          onRefresh={graniteLive.refresh}
          sessionId={sessionId}
          streamState={streamState}
          flavor="fan"
        />
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
        <GraniteLiveExplainer
          state={graniteLive.state}
          canRefresh={graniteLive.canRefresh}
          onRefresh={graniteLive.refresh}
          sessionId={sessionId}
          streamState={streamState}
          flavor="fan"
        />
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
      <div className="space-y-3">
        <GraniteLiveExplainer
          state={graniteLive.state}
          canRefresh={graniteLive.canRefresh}
          onRefresh={graniteLive.refresh}
          sessionId={sessionId}
          streamState={streamState}
          flavor="fan"
        />
        <p className="text-sm text-muted">
          {streamState.kind === "no_telemetry"
            ? streamState.message
            : "Waiting for the first completed lap before the cockpit explains the battery story in plain language."}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <GraniteLiveExplainer
        state={graniteLive.state}
        canRefresh={graniteLive.canRefresh}
        onRefresh={graniteLive.refresh}
        sessionId={sessionId}
        streamState={streamState}
        flavor="fan"
      />
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

function LiveExplainerShell({
  tone,
  title,
  actionLabel,
  actionDisabled,
  onRefresh,
  children,
}: {
  tone: "neutral" | "accent" | "warning";
  title: string;
  actionLabel: string;
  actionDisabled: boolean;
  onRefresh: () => void;
  children: ReactNode;
}) {
  const toneClasses = tone === "accent"
    ? "border-accent/30 bg-accent/8"
    : tone === "warning"
      ? "border-warning/35 bg-warning/8"
      : "border-border bg-surface-2/60";
  const eyebrowColor = tone === "warning" ? "text-warning" : "text-accent";
  return (
    <div className={`space-y-2 rounded-md border px-3 py-3 ${toneClasses}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className={`text-[11px] uppercase tracking-wider ${eyebrowColor}`}>{title}</div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={actionDisabled}
          className="inline-flex rounded-pill border border-border px-3 py-1 text-xs text-accent transition-colors hover:text-text disabled:cursor-not-allowed disabled:opacity-50"
        >
          {actionLabel}
        </button>
      </div>
      {children}
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
