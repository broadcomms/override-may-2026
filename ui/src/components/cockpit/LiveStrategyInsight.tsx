import { Link } from "react-router-dom";
import { useState } from "react";

import type { LiveLapSnapshot, LiveLapStats, Recommendation } from "@/api/types";
import { ModeToggle, type Mode } from "@/components/ModeToggle";
import type { LiveStreamState } from "@/hooks/useLiveTelemetry";
import { deriveLiveSignal } from "@/lib/cockpitTelemetry";

interface Props {
  sessionId: string | null;
  latestSnapshot: LiveLapSnapshot | null;
  latestLap: LiveLapStats | null;
  previousLap: LiveLapStats | null;
  streamState: LiveStreamState;
  recommendation?: Recommendation | null;
}

export function LiveStrategyInsight({
  sessionId,
  latestSnapshot,
  latestLap,
  previousLap,
  streamState,
  recommendation,
}: Props) {
  const [mode, setMode] = useState<Mode>("engineer");
  const signal = deriveLiveSignal(latestLap, previousLap);

  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted">
            AI race engineer
          </div>
          <div className="mt-1 text-sm text-muted">
            Live guidance stays deterministic until completed-lap analysis is available.
          </div>
        </div>
        <ModeToggle mode={mode} onChange={setMode} />
      </header>

      {mode === "engineer" ? (
        <EngineerBody
          sessionId={sessionId}
          latestSnapshot={latestSnapshot}
          streamState={streamState}
          signal={signal}
          recommendation={recommendation ?? null}
        />
      ) : (
        <FanBody latestSnapshot={latestSnapshot} signal={signal} streamState={streamState} />
      )}
    </section>
  );
}

function EngineerBody({
  sessionId,
  latestSnapshot,
  streamState,
  signal,
  recommendation,
}: {
  sessionId: string | null;
  latestSnapshot: LiveLapSnapshot | null;
  streamState: LiveStreamState;
  signal: ReturnType<typeof deriveLiveSignal>;
  recommendation: Recommendation | null;
}) {
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

  // Snapshot-based live signal: deterministic balance label, clearly labelled.
  if (latestSnapshot) {
    return (
      <div className="space-y-3">
        <div className="text-[11px] uppercase tracking-wider text-accent">
          Live signal: {latestSnapshot.balance_label}
        </div>
        <p className="text-lg text-text">
          {snapshotEngineerDetail(latestSnapshot)}
        </p>
        <p className="text-sm text-muted">
          Deterministic live signal — Guardian review pending. Full Granite safety review appears after analysis completes.
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
      <div className="text-[11px] uppercase tracking-wider text-accent">
        Live signal: {signal.pressureLabel}
      </div>
      <p className="text-lg text-text">{signal.pressureDetail}</p>
      <p className="text-sm text-muted">{signal.suggestedAction}</p>
      <p className="text-sm text-muted">
        Review: deterministic live signal; Guardian review pending. Full Granite safety review appears after analysis completes.
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

function FanBody({
  latestSnapshot,
  signal,
  streamState,
}: {
  latestSnapshot: LiveLapSnapshot | null;
  signal: ReturnType<typeof deriveLiveSignal>;
  streamState: LiveStreamState;
}) {
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
