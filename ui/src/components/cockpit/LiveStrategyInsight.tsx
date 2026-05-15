import { Link } from "react-router-dom";
import { useState } from "react";

import type { LiveLapStats, Recommendation } from "@/api/types";
import { ModeToggle, type Mode } from "@/components/ModeToggle";
import type { LiveStreamState } from "@/hooks/useLiveTelemetry";
import { deriveLiveSignal } from "@/lib/cockpitTelemetry";

interface Props {
  sessionId: string | null;
  latestLap: LiveLapStats | null;
  previousLap: LiveLapStats | null;
  streamState: LiveStreamState;
  recommendation?: Recommendation | null;
}

export function LiveStrategyInsight({
  sessionId,
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
          streamState={streamState}
          signal={signal}
          recommendation={recommendation ?? null}
        />
      ) : (
        <FanBody signal={signal} streamState={streamState} />
      )}
    </section>
  );
}

function EngineerBody({
  sessionId,
  streamState,
  signal,
  recommendation,
}: {
  sessionId: string | null;
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
  signal,
  streamState,
}: {
  signal: ReturnType<typeof deriveLiveSignal>;
  streamState: LiveStreamState;
}) {
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
