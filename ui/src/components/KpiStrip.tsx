/**
 * KPI strip — above-the-fold scorecard for the Session debrief.
 *
 * Phase C KPI strip. Eight
 * tiles, mono numerals, no chrome ornament. The trust narrative reads in
 * one row: total harvest, total deploy, laps, zones, AI safety floor,
 * final SoC, regulation citation (clickable), validator pass-rate.
 *
 * SAFETY FLOOR — architect M1 ruling, option (b):
 * The math is the **global minimum across all (recommendation × Guardian
 * criterion) pairs** in the session — "the lowest score the AI gave
 * anything in this session." A single, unambiguous number; no aggregation
 * to dilute a bad score. Tone band per §9.1: ≥0.85 success, 0.70–0.84
 * warning, <0.70 danger.
 *
 * Active sessions hide HARVEST / DEPLOY / FINAL SOC tiles — pre-ingest
 * stubs don't have lap data yet (F2: SessionSummary.status === "active",
 * per ingest/schema.py:320-330 — confirmed by architect 2026-05-14).
 */

import type { Recommendation, RegulationSource, Session } from "@/api/types";

interface Props {
  session: Session;
}

export function KpiStrip({ session }: Props) {
  const isActive = session.summary.status === "active";

  // Per-lap aggregates — only meaningful for COMPLETED sessions.
  const totals = isActive ? null : computeLapTotals(session);

  // Zone breakdown
  const zoneCount = session.recommendations.length;
  const highSeverityCount = session.recommendations.filter(
    (r) => r.zone.severity === "high",
  ).length;

  // Safety floor — global min across all (rec × criterion) pairs.
  const safetyFloor = computeSafetyFloor(session.recommendations);

  // Validator pass-rate
  const validatorPassed = session.recommendations.filter((r) => r.validator.passed).length;

  return (
    <section
      aria-label="Session scorecard"
      className="rounded-card border border-border bg-surface-3 px-4 py-3 grid grid-cols-2 sm:grid-cols-4 md:grid-cols-8 gap-x-4 gap-y-3"
    >
      {totals && (
        <Tile
          label="Harvest"
          value={
            <>
              <span className="text-success" aria-hidden="true">↑</span>{" "}
              {totals.harvest.toFixed(1)} <Unit>MJ</Unit>
            </>
          }
        />
      )}
      {totals && (
        <Tile
          label="Deploy"
          value={
            <>
              <span className="text-warning" aria-hidden="true">↓</span>{" "}
              {totals.deploy.toFixed(1)} <Unit>MJ</Unit>
            </>
          }
        />
      )}
      <Tile label="Laps" value={<>{session.summary.lap_count}</>} />
      <Tile
        label="Zones"
        value={
          <>
            {zoneCount}
            {highSeverityCount > 0 && (
              <span className="text-danger ml-1.5 text-sm" aria-label={`${highSeverityCount} high severity`}>
                ({highSeverityCount}H)
              </span>
            )}
          </>
        }
      />
      <Tile
        label="Safety floor"
        value={
          safetyFloor === null ? (
            <span className="text-muted">—</span>
          ) : (
            <span className={safetyTone(safetyFloor)}>{safetyFloor.toFixed(2)}</span>
          )
        }
      />
      {totals && (
        <Tile
          label="Final SoC"
          value={
            <>
              {Math.round(totals.finalSoc * 100)}<Unit>%</Unit>
            </>
          }
        />
      )}
      <CitationTile source={session.regulation_source} />
      <Tile
        label="Validator"
        value={
          zoneCount === 0 ? (
            <span className="text-muted">—</span>
          ) : (
            <span className={validatorPassed === zoneCount ? "text-success" : "text-warning"}>
              {validatorPassed}/{zoneCount}
            </span>
          )
        }
      />
    </section>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// Tile sub-components
// ──────────────────────────────────────────────────────────────────────────────

function Tile({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] uppercase tracking-wider text-muted truncate">{label}</div>
      <div className="text-lg font-num text-text leading-tight">{value}</div>
    </div>
  );
}

function Unit({ children }: { children: React.ReactNode }) {
  return <span className="text-xs text-muted ml-0.5">{children}</span>;
}

function CitationTile({ source }: { source: RegulationSource | null }) {
  if (!source) {
    return (
      <div className="min-w-0">
        <div className="text-[10px] uppercase tracking-wider text-muted truncate">Citation</div>
        <div className="text-lg font-num text-muted leading-tight">—</div>
      </div>
    );
  }
  return (
    <a
      href={source.public_url}
      target="_blank"
      rel="noreferrer"
      title={`${source.document_title} · ${source.issue} · § ${source.section} — open in new tab`}
      className="min-w-0 group focus:outline-none rounded"
    >
      <div className="text-[10px] uppercase tracking-wider text-muted truncate flex items-center gap-1">
        Citation
        <span className="text-muted/60 group-hover:text-accent transition-colors" aria-hidden="true">↗</span>
      </div>
      <div className="text-lg font-num text-text leading-tight group-hover:text-accent transition-colors truncate">
        § {source.section}
      </div>
    </a>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// Math helpers
// ──────────────────────────────────────────────────────────────────────────────

function computeLapTotals(session: Session): { harvest: number; deploy: number; finalSoc: number } | null {
  if (session.laps.length === 0) return null;
  let harvest = 0;
  let deploy = 0;
  for (const L of session.laps) {
    harvest += L.harvest_mj;
    deploy += L.deploy_mj;
  }
  return {
    harvest,
    deploy,
    finalSoc: session.laps[session.laps.length - 1].soc_end,
  };
}

/**
 * Global minimum across all (recommendation × Guardian criterion) pairs.
 * Returns null when no recommendations exist (so the tile renders "—").
 */
function computeSafetyFloor(recommendations: Recommendation[]): number | null {
  let floor = Infinity;
  for (const r of recommendations) {
    for (const v of Object.values(r.guardian.scores)) {
      if (v < floor) floor = v;
    }
  }
  return Number.isFinite(floor) ? floor : null;
}

function safetyTone(score: number): string {
  if (score >= 0.85) return "text-success";
  if (score >= 0.7) return "text-warning";
  return "text-danger";
}
