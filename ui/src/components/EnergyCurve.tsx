/**
 * Energy curve — Recharts SoC line per docs/04-ui-ux-design.md §5.
 *
 * Layout:
 *   - X axis: lap_number (1-indexed)
 *   - Y axis: SoC × 100 (%)
 *   - solid line: observed soc_end
 *   - dotted continuation: 5-lap forecast.point with shaded interval (lower/upper)
 *   - red triangles below x-axis at zone lap numbers — onClick selects the zone
 *   - empty state when forecast is null (per FR-3.2)
 */

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { Forecast, LapFeatures, Recommendation } from "@/api/types";

interface Props {
  laps: LapFeatures[];
  forecast: Forecast | null;
  recommendations?: Recommendation[];
  onZoneClick?: (zoneId: string) => void;
}

interface Datum {
  lap: number;
  observed: number | null;
  forecast: number | null;
  forecastBand: [number, number] | null;
}

export function EnergyCurve({ laps, forecast, recommendations = [], onZoneClick }: Props) {
  if (laps.length === 0) {
    return (
      <div className="rounded-card border border-dashed border-border p-6 text-center text-sm text-muted">
        No lap data to chart.
      </div>
    );
  }

  // Build the unified series. Each row carries either an observed SoC, a forecast
  // SoC + interval band, or both at the boundary (so the line connects).
  const data: Datum[] = laps.map((L) => ({
    lap: L.lap_number,
    observed: round1(L.soc_end * 100),
    forecast: null,
    forecastBand: null,
  }));

  if (forecast) {
    const lastObservedLap = laps[laps.length - 1].lap_number;
    const lastObservedSoc = laps[laps.length - 1].soc_end * 100;
    // Insert a boundary row so the dotted line starts at the last observed point
    data[data.length - 1] = {
      ...data[data.length - 1],
      forecast: round1(lastObservedSoc),
      forecastBand: [round1(lastObservedSoc), round1(lastObservedSoc)],
    };
    forecast.point.forEach((p, i) => {
      data.push({
        lap: lastObservedLap + 1 + i,
        observed: null,
        forecast: round1(p * 100),
        forecastBand: [round1(forecast.lower[i] * 100), round1(forecast.upper[i] * 100)],
      });
    });
  }

  return (
    <div className="rounded-card border border-border bg-surface p-3">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-medium">Energy Curve</h3>
        {!forecast && (
          <span
            className="text-xs text-muted italic"
            title="TTM-R2 requires ≥30 laps and a confident prediction interval — see docs/04-api.md §4.7."
          >
            Forecast unavailable for this session.
          </span>
        )}
      </div>
      <div style={{ width: "100%", height: 220 }}>
        <ResponsiveContainer>
          <ComposedChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 18 }}>
            <CartesianGrid stroke="var(--color-border)" strokeDasharray="2 2" />
            <XAxis
              dataKey="lap"
              type="number"
              domain={["dataMin", "dataMax"]}
              tick={{ fill: "var(--color-text-muted)", fontSize: 11, fontFamily: "JetBrains Mono" }}
              tickLine={{ stroke: "var(--color-border)" }}
              label={{
                value: "lap",
                position: "insideBottom",
                offset: -8,
                fill: "var(--color-text-muted)",
                fontSize: 11,
              }}
            />
            <YAxis
              type="number"
              domain={[0, 100]}
              ticks={[0, 25, 50, 75, 100]}
              tick={{ fill: "var(--color-text-muted)", fontSize: 11, fontFamily: "JetBrains Mono" }}
              tickLine={{ stroke: "var(--color-border)" }}
              label={{
                value: "SoC %",
                angle: -90,
                position: "insideLeft",
                offset: 14,
                fill: "var(--color-text-muted)",
                fontSize: 11,
              }}
            />
            <Tooltip content={<CurveTooltip />} />
            {forecast && (
              <Area
                type="monotone"
                dataKey="forecastBand"
                stroke="none"
                fill="var(--color-accent)"
                fillOpacity={0.12}
                isAnimationActive={false}
                connectNulls
              />
            )}
            <Line
              type="monotone"
              dataKey="observed"
              stroke="var(--color-accent)"
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
            {forecast && (
              <Line
                type="monotone"
                dataKey="forecast"
                stroke="var(--color-accent)"
                strokeWidth={2}
                strokeDasharray="4 4"
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
            )}
            {/* Zone markers — red triangles below the X axis */}
            {recommendations.map((r) => (
              <ReferenceDot
                key={r.zone.zone_id}
                x={r.zone.lap_number}
                y={2}
                r={5}
                fill="var(--color-danger)"
                stroke="none"
                shape={(p: { cx?: number; cy?: number }) => (
                  <ZoneTriangle
                    cx={p.cx}
                    cy={p.cy}
                    severity={r.zone.severity}
                    onClick={() => onZoneClick?.(r.zone.zone_id)}
                  />
                )}
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function CurveTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ dataKey: string; value: number | null }>;
  label?: number;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const observed = payload.find((p) => p.dataKey === "observed")?.value;
  const fc = payload.find((p) => p.dataKey === "forecast")?.value;
  return (
    <div className="rounded-md border border-border bg-surface-2 px-3 py-2 text-xs font-mono">
      <div className="text-muted mb-1">lap {label}</div>
      {observed != null && <div>SoC {observed.toFixed(1)}%</div>}
      {fc != null && <div className="text-accent">forecast {fc.toFixed(1)}%</div>}
    </div>
  );
}

function ZoneTriangle({
  cx,
  cy,
  severity,
  onClick,
}: {
  cx?: number;
  cy?: number;
  severity: "low" | "medium" | "high";
  onClick?: () => void;
}) {
  if (cx == null || cy == null) return null;
  const fill =
    severity === "high"
      ? "var(--color-danger)"
      : severity === "medium"
      ? "var(--color-warning)"
      : "var(--color-text-muted)";
  // Triangle pointing UP, anchored just below the x axis row
  const yBase = cy + 14;
  const points = `${cx - 5},${yBase + 8} ${cx + 5},${yBase + 8} ${cx},${yBase}`;
  return (
    <g onClick={onClick} style={{ cursor: onClick ? "pointer" : "default" }}>
      <polygon points={points} fill={fill} stroke="var(--color-bg)" strokeWidth="1" />
    </g>
  );
}

function round1(n: number): number {
  return Math.round(n * 10) / 10;
}
