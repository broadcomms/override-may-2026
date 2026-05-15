/**
 * Energy curve — Recharts ComposedChart per docs/04-ui-ux-design.md §5.
 *
 * Phase C energy-curve enrichments:
 *   - Harvest + deploy stacked areas beneath the SoC line, on a secondary
 *     right Y axis (0-10 MJ range). Same data, more information per pixel.
 *   - Sector tinting via ReferenceArea — vertical bands at each
 *     recommendation lap, severity-tinted at ~0.06 alpha.
 *   - Brush for sessions > 60 laps.
 *
 * Layout:
 *   - X axis: lap_number (1-indexed)
 *   - Y axis (left): SoC × 100 (%)
 *   - Y axis (right): energy MJ (harvest + deploy)
 *   - SoC: solid line (observed), dotted continuation (forecast.point),
 *     accent-tinted band around forecast (lower/upper)
 *   - Harvest: success-tinted Area, stacked above Deploy
 *   - Deploy: warning-tinted Area, stacked at 0
 *   - Sector tints: severity-tinted ReferenceArea at each zone lap
 *   - Brush: shown when laps.length > 60
 *   - Red triangles below x-axis at zone lap numbers — onClick selects the zone
 */

import {
  Area,
  Brush,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { Forecast, LapFeatures, Recommendation, Severity } from "@/api/types";

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
  harvest: number;
  deploy: number;
}

const SEVERITY_TINT: Record<Severity, string> = {
  low: "var(--color-text-muted)",
  medium: "var(--color-warning)",
  high: "var(--color-danger)",
};

export function EnergyCurve({ laps, forecast, recommendations = [], onZoneClick }: Props) {
  if (laps.length === 0) {
    return (
      <div className="rounded-card border border-dashed border-border p-6 text-center text-sm text-muted">
        No lap data to chart.
      </div>
    );
  }

  // Build the unified series. Each row carries observed SoC, optional forecast
  // SoC + interval band, plus harvest/deploy on the secondary axis.
  const data: Datum[] = laps.map((L) => ({
    lap: L.lap_number,
    observed: round1(L.soc_end * 100),
    forecast: null,
    forecastBand: null,
    harvest: round2(L.harvest_mj),
    deploy: round2(L.deploy_mj),
  }));

  if (forecast) {
    const lastObservedLap = laps[laps.length - 1].lap_number;
    const lastObservedSoc = laps[laps.length - 1].soc_end * 100;
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
        harvest: 0,
        deploy: 0,
      });
    });
  }

  const showBrush = laps.length > 60;

  return (
    <div className="rounded-card border border-border bg-surface p-3">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-medium">Energy Curve</h3>
        {!forecast && (
          <span
            className="text-xs text-muted italic"
            title="TTM-R2 5-lap SoC forecasting (FR-3) is deferred to v1.1 per the graceful-degradation guardrail. The pipeline runs end-to-end without forecasting."
          >
            Forecast unavailable — TTM-R2 deferred to v1.1.
          </span>
        )}
      </div>
      <div style={{ width: "100%", height: showBrush ? 270 : 232 }}>
        <ResponsiveContainer>
          <ComposedChart data={data} margin={{ top: 8, right: 36, left: 0, bottom: 36 }}>
            <CartesianGrid stroke="var(--color-border)" strokeDasharray="2 2" />
            <XAxis
              dataKey="lap"
              type="number"
              domain={["dataMin", "dataMax"]}
              tick={{ fill: "var(--color-text-muted)", fontSize: 11, fontFamily: "JetBrains Mono" }}
              tickLine={{ stroke: "var(--color-border)" }}
              tickMargin={8}
            />
            <YAxis
              yAxisId="soc"
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
            <YAxis
              yAxisId="mj"
              orientation="right"
              type="number"
              domain={[0, 10]}
              ticks={[0, 2, 4, 6, 8, 10]}
              tick={{ fill: "var(--color-text-muted)", fontSize: 11, fontFamily: "JetBrains Mono" }}
              tickLine={{ stroke: "var(--color-border)" }}
              label={{
                value: "MJ",
                angle: 90,
                position: "insideRight",
                offset: 14,
                fill: "var(--color-text-muted)",
                fontSize: 11,
              }}
            />
            <Tooltip content={<CurveTooltip />} />

            {/* Sector tinting — vertical band at each zone lap, severity-tinted
                at ~0.06 alpha. Visual cue that ties the curve to the
                recommendation cards below; the band carries no x-axis tick. */}
            {recommendations.map((r) => (
              <ReferenceArea
                key={`band-${r.zone.zone_id}`}
                yAxisId="soc"
                x1={r.zone.lap_number - 0.4}
                x2={r.zone.lap_number + 0.4}
                strokeOpacity={0}
                fill={SEVERITY_TINT[r.zone.severity]}
                fillOpacity={0.06}
              />
            ))}

            {/* Harvest + deploy stacked areas on the secondary MJ axis.
                Rendered first so the SoC line draws on top. */}
            <Area
              yAxisId="mj"
              type="monotone"
              dataKey="deploy"
              stackId="energy"
              stroke="none"
              fill="var(--color-warning)"
              fillOpacity={0.15}
              isAnimationActive={false}
            />
            <Area
              yAxisId="mj"
              type="monotone"
              dataKey="harvest"
              stackId="energy"
              stroke="none"
              fill="var(--color-success)"
              fillOpacity={0.15}
              isAnimationActive={false}
            />

            {forecast && (
              <Area
                yAxisId="soc"
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
              yAxisId="soc"
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
                yAxisId="soc"
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

            {recommendations.map((r) => (
              <ReferenceDot
                key={r.zone.zone_id}
                yAxisId="soc"
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

            {showBrush && (
              <Brush
                dataKey="lap"
                height={20}
                stroke="var(--color-border)"
                fill="var(--color-surface-2)"
                travellerWidth={8}
              />
            )}
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
  const harvest = payload.find((p) => p.dataKey === "harvest")?.value;
  const deploy = payload.find((p) => p.dataKey === "deploy")?.value;
  return (
    <div className="rounded-md border border-border bg-surface-2 px-3 py-2 text-xs font-mono space-y-0.5">
      <div className="text-muted">lap {label}</div>
      {observed != null && <div>SoC {observed.toFixed(1)}%</div>}
      {fc != null && <div className="text-accent">forecast {fc.toFixed(1)}%</div>}
      {harvest != null && harvest > 0 && (
        <div className="text-success">↑ harvest {harvest.toFixed(2)} MJ</div>
      )}
      {deploy != null && deploy > 0 && (
        <div className="text-warning">↓ deploy {deploy.toFixed(2)} MJ</div>
      )}
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
  const tipY = cy + 30;
  const baseY = tipY + 7;
  const points = `${cx - 4},${baseY} ${cx + 4},${baseY} ${cx},${tipY}`;
  return (
    <g onClick={onClick} style={{ cursor: onClick ? "pointer" : "default" }}>
      <polygon
        points={points}
        fill={fill}
        stroke="var(--color-bg)"
        strokeWidth="1"
        strokeLinejoin="round"
      />
    </g>
  );
}

function round1(n: number): number {
  return Math.round(n * 10) / 10;
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}
