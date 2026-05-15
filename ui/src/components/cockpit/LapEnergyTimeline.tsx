import type { LiveLapStats } from "@/api/types";
import { deriveLiveSignal, describeLapBalance } from "@/lib/cockpitTelemetry";

interface Props {
  laps: LiveLapStats[];
}

export function LapEnergyTimeline({ laps }: Props) {
  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <header className="mb-3 flex items-center justify-between gap-3">
        <span className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted">
          Lap timeline
        </span>
        <span className="text-xs text-muted">
          {laps.length > 0 ? `${laps.length} laps received` : "awaiting first lap"}
        </span>
      </header>

      {laps.length === 0 ? (
        <p className="text-sm text-muted">
          Waiting for completed laps. Timeline tiles will flag candidate energy pressure as telemetry arrives.
        </p>
      ) : (
        <div className="flex gap-3 overflow-x-auto pb-1">
          {laps.map((lap, index) => {
            const signal = deriveLiveSignal(lap, index > 0 ? laps[index - 1] : null);
            const balance = describeLapBalance(lap);
            const borderTone = signal?.warning ? "border-warning/50" : "border-border";
            return (
              <article
                key={lap.lap}
                className={`min-w-[168px] rounded-md border ${borderTone} bg-surface-2 p-3`}
              >
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="font-mono text-sm text-text">L{lap.lap}</span>
                  <span className="text-[10px] uppercase tracking-wider text-muted">
                    {balance}
                  </span>
                </div>
                <dl className="space-y-1 font-mono text-xs text-muted">
                  <div className="flex items-center justify-between gap-3">
                    <dt>Time</dt>
                    <dd className="text-text">{lap.lap_time_s.toFixed(2)}s</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <dt>SoC</dt>
                    <dd className="text-text">{(lap.soc_end * 100).toFixed(0)}%</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <dt>Harvest</dt>
                    <dd className="text-success">{lap.harvest_mj.toFixed(2)}</dd>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <dt>Deploy</dt>
                    <dd className="text-warning">{lap.deploy_mj.toFixed(2)}</dd>
                  </div>
                </dl>
                <div className="mt-2 text-[10px] uppercase tracking-wide text-muted">
                  {signal?.warning ? signal.pressureLabel : "Review pending"}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
