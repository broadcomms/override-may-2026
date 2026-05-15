import type { LiveLapStats } from "@/api/types";
import { deriveLiveSignal } from "@/lib/cockpitTelemetry";

interface Props {
  latestLap: LiveLapStats | null;
  previousLap: LiveLapStats | null;
}

export function HybridEnergyRail({ latestLap, previousLap }: Props) {
  const signal = deriveLiveSignal(latestLap, previousLap);
  const socPercent = signal?.socPercent ?? 0;
  const gaugeTone =
    signal?.pressureTone === "warning"
      ? "bg-warning"
      : signal?.pressureTone === "success"
      ? "bg-success"
      : "bg-accent";

  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <header className="mb-4 font-mono text-[11px] uppercase tracking-[0.24em] text-muted">
        Hybrid
      </header>

      <div className="mb-4 rounded-md border border-border bg-surface-2 p-3">
        <div className="flex items-end justify-between gap-3">
          <div>
            <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted">
              SOC
            </div>
            <div className="mt-1 font-mono text-3xl tabular-nums text-text">
              {latestLap ? `${socPercent.toFixed(0)}%` : "—"}
            </div>
          </div>
          <div className="text-right text-xs text-muted">
            {signal ? signal.balanceLabel : "waiting"}
          </div>
        </div>
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-bg">
          <div
            className={`h-full rounded-full ${gaugeTone}`}
            style={{ width: `${latestLap ? Math.min(100, Math.max(4, socPercent)) : 0}%` }}
          />
        </div>
      </div>

      <div className="space-y-3">
        <Metric label="HARVEST" value={latestLap ? `${latestLap.harvest_mj.toFixed(2)} MJ` : "—"} />
        <Metric label="DEPLOY" value={latestLap ? `${latestLap.deploy_mj.toFixed(2)} MJ` : "—"} />
        <Metric label="NET" value={signal ? `${signal.netEnergyMj.toFixed(2)} MJ` : "—"} />
        <Metric label="BALANCE" value={signal ? signal.balanceLabel : "waiting"} />
        <Metric label="PRESSURE" value={signal ? signal.pressureLabel : "review pending"} />
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
