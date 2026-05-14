/**
 * Zone heatmap — 40px-tall ribbon per docs/04-ui-ux-design.md §6 and the
 * Phase C C3 audit ruling (OQ-D2: ribbon, not rescale).
 *
 * Three sector rows (S1/S2/S3 top-to-bottom), full-width. Each cell is
 * severity-tinted when a zone hits that (lap, sector); otherwise it shows a
 * subtle surface tone so the grid remains legible at any lap count.
 *
 * Click a filled cell → onZoneClick(zone_id) for deep-linking into the
 * recommendation card. A11y: aria-label per cell, single-symbol fallback
 * for color-blind users (cell carries the severity initial).
 */

import { useMemo } from "react";

import type { Recommendation, Severity } from "@/api/types";

interface Props {
  totalLaps: number;
  recommendations: Recommendation[];
  onZoneClick?: (zoneId: string) => void;
}

type CellMap = Map<string, Recommendation>;
const cellKey = (lap: number, sector: 1 | 2 | 3) => `${lap}:${sector}`;

const SEVERITY_RANK: Record<Severity, number> = { low: 0, medium: 1, high: 2 };

// Filled cells use solid-tone tints layered on the dark surface. No border
// — the saturated fill carries the read.
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

  const lapNumbers = Array.from({ length: totalLaps }, (_, i) => i + 1);
  // Tick stride scales with density so labels stay readable from 5 laps to
  // 120 laps without overlap. Always anchor first + last.
  const tickStride =
    totalLaps <= 15 ? 1 : totalLaps <= 40 ? 5 : totalLaps <= 80 ? 10 : 20;
  const showLapLabel = (lap: number) =>
    lap === 1 || lap === totalLaps || lap % tickStride === 0;

  return (
    <div className="rounded-card border border-border bg-surface p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium">Zone heatmap</h3>
        <Legend />
      </div>

      {/* The ribbon: three sector rows × N lap columns. 1fr columns
          distribute evenly across the container width; row height fixed at
          12px each, gap 2px → 40px total. Each row's leading sector label
          is rendered inside the cell via CSS so the SVG-ribbon arithmetic
          stays out of the markup. */}
      <div className="flex gap-2">
        <div className="flex flex-col gap-[2px] pt-[1px] text-[10px] font-mono text-text/80 tabular-nums">
          {([1, 2, 3] as const).map((sector) => (
            <div key={sector} className="h-3 flex items-center">
              S{sector}
            </div>
          ))}
        </div>
        <div className="flex-1 min-w-0">
          <div
            role="grid"
            aria-label="Zone severity ribbon by lap and sector"
            className="grid gap-[2px]"
            style={{
              gridTemplateColumns: `repeat(${totalLaps}, minmax(0, 1fr))`,
              gridTemplateRows: "repeat(3, 12px)",
            }}
          >
            {([1, 2, 3] as const).flatMap((sector) =>
              lapNumbers.map((lap) => {
                const r = cells.get(cellKey(lap, sector));
                if (!r) {
                  return (
                    <div
                      key={cellKey(lap, sector)}
                      className="bg-surface-3 rounded-[2px]"
                      aria-label={`Sector ${sector}, lap ${lap}, no zone`}
                      title={`S${sector} L${lap}`}
                      role="gridcell"
                    />
                  );
                }
                return (
                  <button
                    key={cellKey(lap, sector)}
                    type="button"
                    onClick={() => onZoneClick?.(r.zone.zone_id)}
                    className={`${SEVERITY_BG[r.zone.severity]} rounded-[2px] cursor-pointer transition-colors hover:ring-1 hover:ring-accent/70 focus:outline-none focus:ring-1 focus:ring-accent`}
                    aria-label={`Sector ${sector}, lap ${lap}, ${r.zone.zone_type}, ${r.zone.severity} severity — click to open recommendation`}
                    title={`L${lap} S${sector} · ${r.zone.zone_type} · ${r.zone.severity}`}
                    role="gridcell"
                  >
                    <span className="sr-only">{SEVERITY_INITIAL[r.zone.severity]}</span>
                  </button>
                );
              }),
            )}
          </div>

          {/* Lap-number ticks under the ribbon. Same grid template so the
              ticks line up under their respective cell columns. */}
          <div
            className="grid mt-1.5"
            style={{ gridTemplateColumns: `repeat(${totalLaps}, minmax(0, 1fr))` }}
            aria-hidden="true"
          >
            {lapNumbers.map((lap) => (
              <span
                key={lap}
                className="text-[10px] font-mono text-muted text-center tabular-nums"
              >
                {showLapLabel(lap) ? lap : ""}
              </span>
            ))}
          </div>
        </div>
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
