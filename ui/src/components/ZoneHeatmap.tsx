/**
 * Zone heatmap — sectors (S1/S2/S3) × laps grid per docs/04-ui-ux-design.md §6.
 *
 * Cell color encodes severity. A11y: aria-label per cell, single-symbol
 * fallback for color-blind users (cell carries the severity initial).
 * Click → onZoneClick(zone_id) for deep-linking into the recommendation card.
 */

import { useMemo } from "react";

import type { Recommendation, Severity } from "@/api/types";

interface Props {
  totalLaps: number;
  recommendations: Recommendation[];
  onZoneClick?: (zoneId: string) => void;
}

// Map (lap_number, sector) → highest-severity zone hitting that cell.
type CellMap = Map<string, Recommendation>;
const cellKey = (lap: number, sector: 1 | 2 | 3) => `${lap}:${sector}`;

const SEVERITY_RANK: Record<Severity, number> = { low: 0, medium: 1, high: 2 };

// Filled cells use solid-tone tints (low/medium/high) layered on the dark
// surface. No border on filled cells — the saturated fill carries the read.
const SEVERITY_BG: Record<Severity, string> = {
  low: "bg-muted/25",
  medium: "bg-warning/40",
  high: "bg-danger/55",
};
const SEVERITY_INITIAL: Record<Severity, string> = { low: "l", medium: "m", high: "h" };

export function ZoneHeatmap({ totalLaps, recommendations, onZoneClick }: Props) {
  const cells = useMemo<CellMap>(() => {
    const m: CellMap = new Map();
    for (const r of recommendations) {
      const key = cellKey(r.zone.lap_number, r.zone.sector);
      const existing = m.get(key);
      if (!existing || SEVERITY_RANK[r.zone.severity] > SEVERITY_RANK[existing.zone.severity]) {
        m.set(key, r);
      }
    }
    return m;
  }, [recommendations]);

  if (totalLaps === 0) {
    return (
      <div className="rounded-card border border-dashed border-border p-4 text-center text-xs text-muted">
        No laps to chart.
      </div>
    );
  }

  // Lap numbers from 1..totalLaps. For sessions > 60 laps we'd switch to
  // a 2-lap aggregation per the §6 open item — flagged for P3.5.
  const lapNumbers = Array.from({ length: totalLaps }, (_, i) => i + 1);
  // Show every lap when the session is short enough to fit comfortably,
  // otherwise stride the labels (first, last, every 5th).
  const showLapLabel = (lap: number) =>
    totalLaps <= 12 || lap === 1 || lap === totalLaps || lap % 5 === 0;

  return (
    <div className="rounded-card border border-border bg-surface p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium">Zone heatmap</h3>
        <Legend />
      </div>
      <div className="overflow-x-auto">
        <table className="border-separate" style={{ borderSpacing: "3px" }}>
          <tbody>
            {([1, 2, 3] as const).map((sector) => (
              <tr key={sector}>
                <th
                  className="pr-3 text-xs font-mono font-medium text-text/80 text-right tabular-nums"
                  scope="row"
                >
                  S{sector}
                </th>
                {lapNumbers.map((lap) => {
                  const r = cells.get(cellKey(lap, sector));
                  if (!r) {
                    return (
                      <td
                        key={lap}
                        className="w-6 h-7 rounded-[3px] bg-surface-2/50"
                        aria-label={`Sector ${sector}, lap ${lap}, no zone`}
                        title={`S${sector} L${lap}`}
                      />
                    );
                  }
                  return (
                    <td
                      key={lap}
                      className={`w-6 h-7 rounded-[3px] cursor-pointer transition-colors ${SEVERITY_BG[r.zone.severity]} hover:ring-1 hover:ring-accent/70 focus:outline-none focus:ring-1 focus:ring-accent`}
                      onClick={() => onZoneClick?.(r.zone.zone_id)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) =>
                        (e.key === "Enter" || e.key === " ") && onZoneClick?.(r.zone.zone_id)
                      }
                      aria-label={`Sector ${sector}, lap ${lap}, ${r.zone.zone_type}, ${r.zone.severity} severity`}
                      title={`L${lap} S${sector} · ${r.zone.zone_type} · ${r.zone.severity}`}
                    >
                      <span className="sr-only">{SEVERITY_INITIAL[r.zone.severity]}</span>
                    </td>
                  );
                })}
              </tr>
            ))}
            <tr aria-hidden="true">
              <th />
              {lapNumbers.map((lap) => (
                <td
                  key={lap}
                  className="w-6 pt-1.5 text-[10px] font-mono text-muted text-center tabular-nums"
                >
                  {showLapLabel(lap) ? lap : ""}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Legend() {
  return (
    <div className="flex items-center gap-3 text-[10px] font-mono uppercase tracking-wide text-muted">
      <LegendSwatch tone="low" label="low" />
      <LegendSwatch tone="medium" label="medium" />
      <LegendSwatch tone="high" label="high" />
    </div>
  );
}

function LegendSwatch({ tone, label }: { tone: Severity; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`inline-block w-3 h-3 rounded-[2px] ${SEVERITY_BG[tone]}`} />
      <span>{label}</span>
    </span>
  );
}
