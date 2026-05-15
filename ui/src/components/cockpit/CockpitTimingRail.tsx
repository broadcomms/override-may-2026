import type { LiveLapSnapshot, LiveLapStats, TorcsRaceState } from "@/api/types";
import type { LiveStreamState } from "@/hooks/useLiveTelemetry";
import { formatTorcsStateShort } from "@/lib/cockpitTelemetry";

interface Props {
  latestSnapshot: LiveLapSnapshot | null;
  latestLap: LiveLapStats | null;
  streamState: LiveStreamState;
  targetLaps: number;
  raceState: TorcsRaceState | null;
}

export function CockpitTimingRail({
  latestSnapshot,
  latestLap,
  streamState,
  targetLaps,
  raceState,
}: Props) {
  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <header className="mb-4 font-mono text-[11px] uppercase tracking-[0.24em] text-muted">
        Timing
      </header>
      <div className="space-y-3">
        <Metric
          label="CURRENT LAP"
          value={
            latestSnapshot
              ? `${latestSnapshot.lap}/${targetLaps}`
              : latestLap
              ? `${latestLap.lap + 1}/${targetLaps}`
              : `1/${targetLaps}`
          }
          prominent
        />
        <Metric
          label="CURRENT TIME"
          value={latestSnapshot ? `${latestSnapshot.lap_time_s.toFixed(2)}s` : "waiting"}
        />
        <Metric
          label="LIVE SPEED"
          value={latestSnapshot ? `${latestSnapshot.speed_kmh.toFixed(0)} km/h` : "—"}
        />
        <Metric
          label="LIVE AVG"
          value={latestSnapshot ? `${latestSnapshot.avg_speed_kmh.toFixed(0)} km/h` : "—"}
        />
        <Metric
          label="FUEL"
          value={
            latestSnapshot?.fuel_kg != null
              ? `${latestSnapshot.fuel_kg.toFixed(1)} kg`
              : latestLap?.fuel_used_kg != null
              ? `${latestLap.fuel_used_kg.toFixed(2)} kg used`
              : "n/a"
          }
        />
        <Metric label="STATE" value={stateValue(streamState, raceState)} />
        {latestLap && (
          <div className="pt-1 border-t border-border/40">
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted/70">
              Closed lap
            </div>
            <div className="mt-0.5 font-mono text-xs tabular-nums text-muted">
              L{latestLap.lap} · {latestLap.lap_time_s.toFixed(3)}s · {latestLap.avg_speed_kmh.toFixed(0)} km/h avg
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function stateValue(
  streamState: LiveStreamState,
  raceState: TorcsRaceState | null,
): string {
  switch (streamState.kind) {
    case "connected":
      return "live";
    case "connecting":
      return "arming";
    case "no_telemetry":
      return "no telemetry";
    case "error":
      return "stream retry";
    case "ended":
      return "race ended";
    case "idle":
      return formatTorcsStateShort(raceState);
  }
}

function Metric({
  label,
  value,
  prominent = false,
}: {
  label: string;
  value: string;
  prominent?: boolean;
}) {
  return (
    <div className="border-b border-border/60 pb-2 last:border-b-0 last:pb-0">
      <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted">
        {label}
      </div>
      <div className={`${prominent ? "text-2xl" : "text-base"} mt-1 font-mono tabular-nums text-text`}>
        {value}
      </div>
    </div>
  );
}
