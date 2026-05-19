import type { LiveLapSnapshot, LiveLapStats, TorcsControlStatus } from "@/api/types";
import type { LiveStreamState } from "@/hooks/useLiveTelemetry";
import { deriveLiveSignal } from "@/lib/cockpitTelemetry";

interface Props {
  status: TorcsControlStatus | null;
  latestSnapshot: LiveLapSnapshot | null;
  latestLap: LiveLapStats | null;
  previousLap: LiveLapStats | null;
  streamState: LiveStreamState;
  preRunIdle: boolean;
}

export function HybridEnergyRail({ status, latestSnapshot, latestLap, previousLap, streamState, preRunIdle }: Props) {
  const signal = deriveLiveSignal(latestLap, previousLap);
  const raceBadge = getRaceBadge(status, streamState, preRunIdle);

  // Snapshot values take priority during an open lap.
  const isLive = latestSnapshot != null;
  const socPercent = isLive
    ? latestSnapshot.soc_estimate * 100
    : (signal?.socPercent ?? 0);
  const harvest = isLive ? latestSnapshot.harvest_mj : latestLap?.harvest_mj ?? null;
  const deploy = isLive ? latestSnapshot.deploy_mj : latestLap?.deploy_mj ?? null;
  const net = harvest != null && deploy != null ? harvest - deploy : null;
  const balanceLabel = isLive ? latestSnapshot.balance_label : (signal?.balanceLabel ?? null);

  const gaugeTone =
    signal?.pressureTone === "warning"
      ? "bg-warning"
      : signal?.pressureTone === "success"
      ? "bg-success"
      : "bg-accent";

  const statusLine = streamStatusLine(streamState, preRunIdle);

  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <header className="mb-4 flex items-center justify-between font-mono text-[11px] uppercase tracking-[0.24em] text-muted">
        <span>Hybrid</span>
        {isLive && (
          <span className="rounded bg-accent/10 px-1.5 py-0.5 font-mono text-[10px] text-accent">
            live
          </span>
        )}
      </header>

      <div className="mb-4 rounded-md border border-border bg-surface-2 p-3">
        <div className="flex items-end justify-between gap-3">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted">
              SOC
            </div>
            <div className="mt-1 font-mono text-3xl tabular-nums text-text">
              {(isLive || latestLap) ? `${socPercent.toFixed(0)}%` : "—"}
            </div>
          </div>
          <div className="text-right text-xs text-muted">
            {balanceLabel ?? "waiting"}
          </div>
        </div>
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-bg">
          <div
            className={`h-full rounded-full ${gaugeTone} transition-all duration-200`}
            style={{ width: `${(isLive || latestLap) ? Math.min(100, Math.max(4, socPercent)) : 0}%` }}
          />
        </div>
      </div>

      <div className="space-y-3">
        <Metric label={isLive ? "HARVEST (lap)" : "HARVEST"} value={harvest != null ? `${harvest.toFixed(2)} MJ` : "—"} />
        <Metric label={isLive ? "DEPLOY (lap)" : "DEPLOY"} value={deploy != null ? `${deploy.toFixed(2)} MJ` : "—"} />
        <Metric label="NET" value={net != null ? `${net.toFixed(2)} MJ` : "—"} />
        <Metric label="BALANCE" value={balanceLabel ?? "waiting"} />
        {raceBadge && (
          <div className="flex justify-end pt-1">
            <span className={`rounded-md border px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.2em] ${raceBadge.tone}`}>
              {raceBadge.label}
            </span>
          </div>
        )}
        {!isLive && <Metric label="PRESSURE" value={signal ? signal.pressureLabel : "review pending"} />}
        {statusLine && (
          <div className="pt-1">
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted">
              Status
            </div>
            <div className="mt-0.5 text-xs text-muted leading-snug">{statusLine}</div>
          </div>
        )}
      </div>
    </section>
  );
}

/** One-line stream status shown at the bottom of the rail, replacing the frame overlay. */
function streamStatusLine(state: LiveStreamState, preRunIdle: boolean): string | null {
  if (preRunIdle) {
    return null;
  }

  switch (state.kind) {
    case "idle":
      return "Ready. Start a race to stream live data.";
    case "connecting":
      return "Connecting to telemetry stream…";
    case "connected":
      return "Telemetry stream live.";
    case "no_telemetry":
      return state.message;
    case "error":
      return "Stream interrupted. Reconnecting…";
    case "ended":
      return "Race ended. Post-lap analysis available in the session debrief.";
  }
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-b border-border/60 pb-2 last:border-b-0 last:pb-0">
      <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted">
        {label}
      </div>
      <div className="mt-1 font-mono text-sm tabular-nums text-text">{value}</div>
    </div>
  );
}

function getRaceBadge(
  status: TorcsControlStatus | null,
  streamState: LiveStreamState,
  preRunIdle: boolean,
): { label: string; tone: string } | null {
  if (preRunIdle) {
    return null;
  }

  if (streamState.kind === "ended") {
    return {
      label: "Debrief ready",
      tone: "border-accent/40 bg-accent/10 text-accent",
    };
  }

  if (status?.last_error || streamState.kind === "error") {
    return {
      label: "Needs review",
      tone: "border-warning/40 bg-warning/10 text-warning",
    };
  }

  if (status?.starting || status?.state === "launching" || status?.state === "waiting_scr") {
    return {
      label: "Staging run",
      tone: "border-border/80 bg-bg/70 text-muted",
    };
  }

  if (status?.state === "stopping" || status?.state === "cleanup") {
    return {
      label: "Closing run",
      tone: "border-border/80 bg-bg/70 text-muted",
    };
  }

  if (streamState.kind === "connected" || status?.state === "active") {
    return {
      label: status?.launch_mode === "headless_quickrace" ? "Headless live" : "Live race",
      tone: "border-accent/40 bg-accent/10 text-accent",
    };
  }

  if (status?.state === "idle") {
    return {
      label: "Standby",
      tone: "border-border/80 bg-bg/70 text-muted",
    };
  }

  return null;
}
