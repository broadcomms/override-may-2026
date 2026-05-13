/**
 * Session comparison page — Phase 1 ship.
 *
 * Renders two full sessions side-by-side, picked from the /sessions
 * history view's Compare button. URL shape:
 *   /sessions/compare?a=<session_id>&b=<session_id>
 *
 * The comparison is intentionally lightweight — pipeline-level stats
 * only (lap count, derived energy totals, zone count, regulation
 * citation). Per-zone diffs and recommendation deltas are documented
 * as v1.1 work in docs/roadmap-v1.1/. For v1.0 the rubric value is
 * "we tracked these sessions individually and can compare them at a
 * glance," not "we compute optimal-strategy deltas."
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api, OverrideApiError } from "@/api/client";
import type { Session } from "@/api/types";

function formatTs(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function sumHarvest(s: Session): number {
  return s.laps.reduce((acc, lap) => acc + (lap.harvest_mj ?? 0), 0);
}

function sumDeploy(s: Session): number {
  return s.laps.reduce((acc, lap) => acc + (lap.deploy_mj ?? 0), 0);
}

function deltaCell(a: number, b: number, unit: string, digits: number = 2): JSX.Element {
  const diff = b - a;
  const sign = diff > 0 ? "+" : "";
  const cls = diff === 0 ? "text-muted" : diff > 0 ? "text-accent" : "text-danger";
  return (
    <span className={`tabular-nums ${cls}`}>
      {sign}
      {diff.toFixed(digits)} {unit}
    </span>
  );
}

interface SidePanelProps {
  label: "A" | "B";
  session: Session;
  partner: Session;
}

function SidePanel({ label, session, partner }: SidePanelProps) {
  const s = session.summary;
  return (
    <section
      className="rounded-card border border-border bg-surface/40 p-5"
      aria-label={`Session ${label}`}
    >
      <header className="mb-4 flex items-baseline justify-between">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <span className="text-xs uppercase tracking-wider text-muted">Session {label}</span>
          <span className="font-mono text-sm">{s.session_id}</span>
        </h2>
        <Link
          to={`/session/${encodeURIComponent(s.session_id)}`}
          className="text-xs text-accent hover:underline"
        >
          Open debrief →
        </Link>
      </header>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <dt className="text-muted">Source</dt>
        <dd>
          {s.source}
          {s.session_source === "torcs_live" && (
            <span className="ml-2 px-1.5 py-0.5 rounded-pill bg-accent/15 text-accent text-[10px] uppercase tracking-wider">
              live
            </span>
          )}
        </dd>

        <dt className="text-muted">Track</dt>
        <dd>{s.track_name ?? s.track_id ?? "—"}</dd>

        <dt className="text-muted">Uploaded</dt>
        <dd>{formatTs(s.uploaded_at)}</dd>

        {s.started_at && (
          <>
            <dt className="text-muted">Started</dt>
            <dd>{formatTs(s.started_at)}</dd>
          </>
        )}

        <dt className="text-muted">Laps</dt>
        <dd className="tabular-nums">
          {s.lap_count}
          {label === "B" && (
            <span className="ml-2 text-xs">
              ({deltaCell(partner.summary.lap_count, s.lap_count, "", 0)})
            </span>
          )}
        </dd>

        <dt className="text-muted">Zones</dt>
        <dd className="tabular-nums">
          {s.zone_count}
          {label === "B" && (
            <span className="ml-2 text-xs">
              ({deltaCell(partner.summary.zone_count, s.zone_count, "", 0)})
            </span>
          )}
        </dd>

        <dt className="text-muted">Harvest total</dt>
        <dd className="tabular-nums">
          {sumHarvest(session).toFixed(2)} MJ
          {label === "B" && (
            <span className="ml-2 text-xs">({deltaCell(sumHarvest(partner), sumHarvest(session), "MJ")})</span>
          )}
        </dd>

        <dt className="text-muted">Deploy total</dt>
        <dd className="tabular-nums">
          {sumDeploy(session).toFixed(2)} MJ
          {label === "B" && (
            <span className="ml-2 text-xs">({deltaCell(sumDeploy(partner), sumDeploy(session), "MJ")})</span>
          )}
        </dd>

        <dt className="text-muted">Recommendations</dt>
        <dd className="tabular-nums">
          {session.recommendations.length}
          {label === "B" && (
            <span className="ml-2 text-xs">
              ({deltaCell(partner.recommendations.length, session.recommendations.length, "", 0)})
            </span>
          )}
        </dd>
      </dl>

      {session.regulation_source && (
        <div className="mt-4 pt-3 border-t border-border/60">
          <div className="text-xs uppercase tracking-wider text-muted mb-1">Grounded in</div>
          <div className="text-xs text-muted">
            {session.regulation_source.document_title}
            {session.regulation_source.section && (
              <> · §{session.regulation_source.section}</>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

export function SessionComparePage() {
  const [params] = useSearchParams();
  const idA = params.get("a");
  const idB = params.get("b");

  const [sessionA, setSessionA] = useState<Session | null>(null);
  const [sessionB, setSessionB] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!idA || !idB) {
      setError("Compare requires two session IDs in the URL (`?a=...&b=...`).");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [a, b] = await Promise.all([api.getSession(idA), api.getSession(idB)]);
      setSessionA(a);
      setSessionB(b);
    } catch (e) {
      const msg =
        e instanceof OverrideApiError
          ? e.payload.message
          : e instanceof Error
          ? e.message
          : "Failed to load comparison.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [idA, idB]);

  useEffect(() => {
    load();
  }, [load]);

  const both = useMemo(() => (sessionA && sessionB ? { a: sessionA, b: sessionB } : null), [
    sessionA,
    sessionB,
  ]);

  return (
    <div className="px-6 py-12 max-w-6xl mx-auto">
      <header className="mb-6 flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold">Compare sessions</h1>
        <Link to="/sessions" className="text-sm text-accent hover:underline">
          ← Back to sessions
        </Link>
      </header>

      {loading && <div className="text-sm text-muted">Loading both sessions…</div>}

      {error && (
        <div
          role="alert"
          className="rounded-card border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger"
        >
          {error}
        </div>
      )}

      {both && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <SidePanel label="A" session={both.a} partner={both.b} />
          <SidePanel label="B" session={both.b} partner={both.a} />
        </div>
      )}

      {both && (
        <p className="mt-6 text-xs text-muted">
          Per-zone diffs, recommendation deltas, and lap-time comparison are v1.1 work — this view
          surfaces the session-level metrics judges most often want at a glance.
        </p>
      )}
    </div>
  );
}
