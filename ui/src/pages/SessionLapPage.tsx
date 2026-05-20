import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { OverrideApiError, api } from "@/api/client";
import type { LapAnalysis, Session } from "@/api/types";
import { ErrorBanner, LoadingSkeleton } from "@/components/EmptyStates";
import { useRaceEngineerPageContext } from "@/context/RaceEngineerContext";

export function SessionLapPage() {
  const { lapNumber = "", sessionId = "" } = useParams<{ sessionId: string; lapNumber: string }>();
  const [searchParams] = useSearchParams();
  const fixtureParam = searchParams.get("fixture");
  const fixture: boolean | undefined =
    fixtureParam === "1" ? true : fixtureParam === "0" ? false : undefined;
  const parsedLapNumber = Number(lapNumber);

  const [analysis, setAnalysis] = useState<LapAnalysis | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setAnalysis(null);
    setSession(null);
    setError(null);
    Promise.all([
      api.getSession(sessionId, { fixture }),
      api.getLapAnalysis(sessionId, parsedLapNumber, { fixture }),
    ]).then(
      ([loadedSession, loadedAnalysis]) => {
        if (cancelled) return;
        setSession(loadedSession);
        setAnalysis(loadedAnalysis);
      },
      (err) => {
        if (cancelled) return;
        setError(
          err instanceof OverrideApiError
            ? err.payload.message
            : err instanceof Error
            ? err.message
            : "Lap detail unavailable.",
        );
      },
    );
    return () => {
      cancelled = true;
    };
  }, [fixture, parsedLapNumber, sessionId]);

  const raceEngineerContext = useMemo(
    () =>
      session
        ? {
            kind: "lap" as const,
            sessionId,
            fixture: fixture === true,
            lapNumber: parsedLapNumber,
            title: session.summary.track_name ?? session.summary.track_id ?? "session",
            latestLapNumber: session.laps[session.laps.length - 1]?.lap_number ?? null,
            raceState: null,
          }
        : null,
    [fixture, parsedLapNumber, session, sessionId],
  );
  useRaceEngineerPageContext(raceEngineerContext);

  const lap = useMemo(
    () => session?.laps.find((item) => item.lap_number === parsedLapNumber) ?? null,
    [parsedLapNumber, session],
  );

  if (error) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-6">
        <ErrorBanner title="Lap detail unavailable" detail={error} />
      </div>
    );
  }

  if (!analysis || !session || !lap) {
    return (
      <div className="max-w-4xl mx-auto space-y-3 px-6 py-6">
        <LoadingSkeleton lines={2} />
        <LoadingSkeleton lines={5} />
      </div>
    );
  }
  const relatedRecommendations = session.recommendations.filter((rec) => rec.zone.lap_number === parsedLapNumber);

  return (
    <div className="max-w-4xl mx-auto px-6 py-6 space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link
            to={`/session/${encodeURIComponent(sessionId)}${fixture ? "?fixture=1" : ""}`}
            className="text-sm text-accent hover:underline"
          >
            ← Back to session debrief
          </Link>
          <h1 className="mt-2 text-2xl font-semibold text-text">Lap {analysis.lap_number} detail</h1>
          <p className="mt-1 text-sm text-muted">{analysis.summary}</p>
        </div>
        <div className="rounded-pill border border-border px-3 py-1.5 text-xs text-muted">
          Track: {session.summary.track_name ?? session.summary.track_id ?? "session"}
        </div>
      </div>

      <section className="rounded-card border border-border bg-surface p-4">
        <div className="text-[11px] uppercase tracking-wider text-muted">Lap analysis</div>
        <h2 className="mt-2 text-lg font-medium text-text">{analysis.headline}</h2>
        <div className="mt-4 grid gap-3 md:grid-cols-4">
          <MetricTile label="Lap time" value={`${lap.lap_time.toFixed(2)}s`} />
          <MetricTile label="SoC" value={`${Math.round(lap.soc_end * 100)}%`} />
          <MetricTile label="Harvest" value={`${lap.harvest_mj.toFixed(2)} MJ`} />
          <MetricTile label="Deploy" value={`${lap.deploy_mj.toFixed(2)} MJ`} />
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2">
        <div className="rounded-card border border-border bg-surface p-4">
          <div className="text-[11px] uppercase tracking-wider text-muted">Sector callouts</div>
          <div className="mt-3 space-y-2 text-sm text-muted">
            {analysis.sector_callouts.map((item) => (
              <p key={item}>{item}</p>
            ))}
          </div>
        </div>
        <div className="rounded-card border border-border bg-surface p-4">
          <div className="text-[11px] uppercase tracking-wider text-muted">Evidence</div>
          <ul className="mt-3 space-y-2 text-sm text-muted">
            {analysis.evidence.map((item) => (
              <li key={item}>- {item}</li>
            ))}
          </ul>
        </div>
      </section>

      <section className="rounded-card border border-border bg-surface p-4">
        <div className="text-[11px] uppercase tracking-wider text-muted">Matching recommendations</div>
        {relatedRecommendations.length === 0 ? (
          <p className="mt-3 text-sm text-muted">No zone recommendation was generated on this lap.</p>
        ) : (
          <div className="mt-3 space-y-3">
            {relatedRecommendations.map((rec) => (
              <div key={rec.zone.zone_id} className="rounded-card border border-border/70 bg-surface-2/30 p-3">
                <div className="text-sm font-medium text-text">{rec.reasoning.recommendation}</div>
                <p className="mt-1 text-sm text-muted">{rec.reasoning.cause}</p>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-card border border-border/70 bg-surface-2/30 p-3">
      <div className="text-[11px] uppercase tracking-wider text-muted">{label}</div>
      <div className="mt-2 text-lg font-medium text-text">{value}</div>
    </div>
  );
}
