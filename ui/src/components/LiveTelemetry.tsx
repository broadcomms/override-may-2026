/**
 * LiveTelemetry — Phase 3 live race overlay.
 *
 * Renders above the recommendation cards on SessionPage when the session
 * is ACTIVE. Opens a Server-Sent Events stream against
 * `GET /api/sessions/{id}/stream`, accumulates per-lap stats as they
 * arrive, surfaces a small connection-status pill so the user knows the
 * stream is alive (not silently stalled).
 *
 * Race-end semantics: when the backend emits `race_ended`, the
 * `onRaceEnded` callback fires — SessionPage uses that to refetch the
 * (now-COMPLETED) Session and swap in the normal post-race UI. Until
 * then the panel keeps the latest lap stats visible.
 */

import type { LiveLapSnapshot, LiveLapStats } from "@/api/types";
import type { LiveStreamState } from "@/hooks/useLiveTelemetry";
import type { Mode } from "@/components/ModeToggle";

interface Props {
  laps: LiveLapStats[];
  latestLap: LiveLapStats | null;
  latestSnapshot: LiveLapSnapshot | null;
  streamState: LiveStreamState;
  mode: Mode;
  expectedLapCount?: number;
}

export function LiveTelemetry({
  laps,
  latestLap,
  latestSnapshot,
  streamState: state,
  mode,
  expectedLapCount = 0,
}: Props) {
  return (
    <section
      className="rounded-card border border-accent/40 bg-surface/60 p-4 mb-6"
      aria-label="Live race telemetry"
    >
      <header className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span
              className={`absolute inline-flex h-full w-full rounded-full opacity-75 ${
                state.kind === "connected"
                  ? "animate-ping bg-accent"
                  : state.kind === "ended"
                  ? "bg-muted"
                  : "bg-warning"
              }`}
              aria-hidden="true"
            />
            <span
              className={`relative inline-flex rounded-full h-2 w-2 ${
                state.kind === "connected"
                  ? "bg-accent"
                  : state.kind === "ended"
                  ? "bg-muted"
                  : "bg-warning"
              }`}
              aria-hidden="true"
            />
          </span>
          <h2 className="text-sm font-semibold uppercase tracking-wider">
            Live race telemetry
          </h2>
        </div>
        <StatusBadge state={state} />
      </header>

      {mode === "fan" && (
        <FanLiveStory
          latestLap={latestLap}
          latestSnapshot={latestSnapshot}
          expectedLapCount={expectedLapCount}
          state={state}
        />
      )}

      {state.kind === "no_telemetry" && (
        <p className="text-sm text-muted">{state.message}</p>
      )}

      {state.kind === "error" && (
        <p className="text-sm text-warning">
          Stream interrupted — reconnecting…
        </p>
      )}

      {laps.length === 0 && (state.kind === "connecting" || state.kind === "connected") && (
        <p className="text-sm text-muted">
          {expectedLapCount > 0 && state.kind === "connected"
            ? `Syncing ${expectedLapCount} captured lap${expectedLapCount === 1 ? "" : "s"} from the live run…`
            : "Waiting for the first lap to complete…"}
        </p>
      )}

      {laps.length > 0 && <LiveLapTable laps={laps} />}
    </section>
  );
}

function FanLiveStory({
  latestLap,
  latestSnapshot,
  expectedLapCount,
  state,
}: {
  latestLap: LiveLapStats | null;
  latestSnapshot: LiveLapSnapshot | null;
  expectedLapCount: number;
  state: LiveStreamState;
}) {
  return (
    <div className="mb-4 space-y-2 border-b border-border/50 pb-3">
      <div className="text-[11px] uppercase tracking-wider text-accent">Live race story</div>
      <p className="text-sm text-text">
        {fanStoryText({ latestLap, latestSnapshot, expectedLapCount, state })}
      </p>
    </div>
  );
}

function fanStoryText({
  latestLap,
  latestSnapshot,
  expectedLapCount,
  state,
}: {
  latestLap: LiveLapStats | null;
  latestSnapshot: LiveLapSnapshot | null;
  expectedLapCount: number;
  state: LiveStreamState;
}) {
  if (latestLap) {
    const pace = latestLap.lap_time_s.toFixed(2);
    const soc = Math.round(latestLap.soc_end * 100);
    const net = latestLap.harvest_mj - latestLap.deploy_mj;
    if (net < -0.08) {
      return `Lap ${latestLap.lap} closed in ${pace}s with the battery down to ${soc}%. The car is spending more energy than it wins back right now, so the next lap is the one to watch for a recovery move.`;
    }
    if (net > 0.08) {
      return `Lap ${latestLap.lap} closed in ${pace}s and the battery recovered to ${soc}%. OVERRIDE is rebuilding energy here, which could set up a stronger push on the next straight.`;
    }
    return `Lap ${latestLap.lap} closed in ${pace}s with the battery holding around ${soc}%. The hybrid balance is steady, so the race is in a controlled holding pattern right now.`;
  }
  if (latestSnapshot) {
    const soc = Math.round(latestSnapshot.soc_estimate * 100);
    return `The car is live on lap ${latestSnapshot.lap}, sector ${latestSnapshot.sector ?? "?"}, with battery reserve around ${soc}%. The race story is still forming while OVERRIDE waits for the next clean lap to close.`;
  }
  if (expectedLapCount > 0 && state.kind === "connected") {
    return `OVERRIDE has already captured about ${expectedLapCount} lap${expectedLapCount === 1 ? "" : "s"} from this run and is syncing the live race story now.`;
  }
  return "The live race story appears here once OVERRIDE has enough telemetry to explain what the car is building toward.";
}

function StatusBadge({ state }: { state: LiveStreamState }) {
  const map: Record<LiveStreamState["kind"], { label: string; tone: string }> = {
    idle: { label: "Idle", tone: "text-muted" },
    connecting: { label: "Connecting", tone: "text-muted" },
    connected: { label: "Live", tone: "text-accent" },
    no_telemetry: { label: "No telemetry", tone: "text-muted" },
    error: { label: "Disconnected", tone: "text-warning" },
    ended: { label: "Race ended", tone: "text-muted" },
  };
  const { label, tone } = map[state.kind];
  return <span className={`text-xs ${tone}`}>{label}</span>;
}

function LiveLapTable({ laps }: { laps: LiveLapStats[] }) {
  // Newest lap at the top — gives the live demo beat a "ticking" feel.
  const ordered = laps.slice().reverse();
  return (
    <table className="w-full text-sm tabular-nums">
      <thead>
        <tr className="text-xs uppercase tracking-wider text-muted">
          <th className="text-left font-normal py-1">Lap</th>
          <th className="text-right font-normal py-1">Time</th>
          <th className="text-right font-normal py-1">Avg / Max km/h</th>
          <th className="text-right font-normal py-1">Harvest</th>
          <th className="text-right font-normal py-1">Deploy</th>
          <th className="text-right font-normal py-1">SoC</th>
        </tr>
      </thead>
      <tbody>
        {ordered.map((l) => (
          <tr key={l.lap} className="border-t border-border/40">
            <td className="py-1.5 font-mono">L{l.lap}</td>
            <td className="py-1.5 text-right">{l.lap_time_s.toFixed(2)}s</td>
            <td className="py-1.5 text-right text-muted">
              {l.avg_speed_kmh.toFixed(0)} / {l.max_speed_kmh.toFixed(0)}
            </td>
            <td className="py-1.5 text-right text-accent">
              {l.harvest_mj.toFixed(2)} MJ
            </td>
            <td className="py-1.5 text-right text-warning">
              {l.deploy_mj.toFixed(2)} MJ
            </td>
            <td className="py-1.5 text-right">
              {(l.soc_end * 100).toFixed(0)}%
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
