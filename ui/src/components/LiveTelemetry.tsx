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

import type { LiveLapStats } from "@/api/types";
import { useLiveTelemetry, type LiveStreamState } from "@/hooks/useLiveTelemetry";

interface Props {
  sessionId: string;
  onRaceEnded?: () => void;
}

export function LiveTelemetry({ sessionId, onRaceEnded }: Props) {
  const { laps, streamState: state } = useLiveTelemetry(sessionId, { onRaceEnded });

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

      {state.kind === "no_telemetry" && (
        <p className="text-sm text-muted">{state.message}</p>
      )}

      {state.kind === "error" && (
        <p className="text-sm text-warning">
          Stream interrupted — reconnecting…
        </p>
      )}

      {laps.length === 0 && state.kind === "connecting" && (
        <p className="text-sm text-muted">Waiting for the first lap to complete…</p>
      )}

      {laps.length > 0 && <LiveLapTable laps={laps} />}
    </section>
  );
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
