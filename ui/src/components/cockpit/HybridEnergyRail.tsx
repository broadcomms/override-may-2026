import type { LiveLapSnapshot, LiveLapStats } from "@/api/types";
import { deriveLiveSignal } from "@/lib/cockpitTelemetry";

interface Props {
  latestSnapshot: LiveLapSnapshot | null;
  latestLap: LiveLapStats | null;
  previousLap: LiveLapStats | null;
}

export function HybridEnergyRail({ latestSnapshot, latestLap, previousLap }: Props) {
  const signal = deriveLiveSignal(latestLap, previousLap);

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
        {!isLive && <Metric label="PRESSURE" value={signal ? signal.pressureLabel : "review pending"} />}
      </div>
    </section>
  );
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
