import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { OverrideApiError, api } from "@/api/client";
import type { RaceReport, Session } from "@/api/types";
import { LoadingSkeleton } from "@/components/EmptyStates";

interface Props {
  fixture?: boolean;
  session: Session;
  sessionId: string;
}

export function PostRaceReportPanel({ fixture, session, sessionId }: Props) {
  const [report, setReport] = useState<RaceReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setReport(null);
    setError(null);
    api.getRaceReport(sessionId, { fixture }).then(
      (value) => {
        if (!cancelled) setReport(value);
      },
      (err) => {
        if (cancelled) return;
        setError(
          err instanceof OverrideApiError
            ? err.payload.message
            : err instanceof Error
            ? err.message
            : "Race report unavailable.",
        );
      },
    );
    return () => {
      cancelled = true;
    };
  }, [fixture, sessionId]);

  if (error) {
    return (
      <section className="rounded-card border border-danger/40 bg-danger/5 p-4">
        <div className="text-[11px] uppercase tracking-wider text-danger">Race report unavailable</div>
        <p className="mt-2 text-sm text-danger">{error}</p>
      </section>
    );
  }

  if (!report) {
    return (
      <section className="rounded-card border border-border bg-surface p-4">
        <LoadingSkeleton lines={4} />
      </section>
    );
  }

  const lapLinks = session.laps;

  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted">Post-race intelligence</div>
          <h2 className="mt-2 text-xl font-semibold text-text">{report.title}</h2>
          <p className="mt-2 text-sm text-muted">{report.executive_summary}</p>
        </div>
        <button
          type="button"
          onClick={() => window.print()}
          className="rounded-pill border border-border px-3 py-1.5 text-xs text-accent transition-colors hover:text-text"
        >
          Save as PDF
        </button>
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        <ScoreTile label="Driver" value={report.driver_score} />
        <ScoreTile label="Battery" value={report.battery_efficiency_score} />
        <ScoreTile label="Consistency" value={report.consistency_score} />
        <ScoreTile label="Risk" value={report.risk_score} inverse />
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-[1.3fr_1fr]">
        <div className="space-y-3">
          <div className="text-[11px] uppercase tracking-wider text-muted">Key moments</div>
          {report.key_moments.map((moment) => (
            <div key={moment.insight_id} className="rounded-card border border-border/70 bg-surface-2/40 p-3">
              <div className="text-sm font-medium text-text">{moment.headline}</div>
              <p className="mt-1 text-sm text-muted">{moment.message}</p>
              {moment.recommended_action && (
                <p className="mt-2 text-xs text-muted">{moment.recommended_action}</p>
              )}
              {(moment.lap != null || moment.sector != null) && (
                <div className="mt-2 text-[11px] uppercase tracking-wider text-accent">
                  {moment.lap != null ? `Lap ${moment.lap}` : "Session"}
                  {moment.sector != null ? ` · Sector ${moment.sector}` : ""}
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="space-y-4">
          <div>
            <div className="text-[11px] uppercase tracking-wider text-muted">AI commentary</div>
            <div className="mt-3 space-y-2 text-sm text-muted">
              {report.ai_commentary.map((item) => (
                <p key={item}>{item}</p>
              ))}
            </div>
          </div>

          <div>
            <div className="text-[11px] uppercase tracking-wider text-muted">Lap drill-down</div>
            <div className="mt-1 text-xs text-muted">
              Open any lap from this run for a lap-specific debrief.
            </div>
            <div className="mt-3 flex max-h-40 flex-wrap gap-2 overflow-y-auto pr-1">
              {lapLinks.map((lap) => (
                <Link
                  key={lap.lap_number}
                  to={`/session/${encodeURIComponent(sessionId)}/laps/${lap.lap_number}${fixture ? "?fixture=1" : ""}`}
                  className="rounded-pill border border-border px-3 py-1.5 text-xs text-accent transition-colors hover:text-text"
                >
                  Lap {lap.lap_number}
                </Link>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function ScoreTile({
  inverse = false,
  label,
  value,
}: {
  inverse?: boolean;
  label: string;
  value: number;
}) {
  const display = `${Math.round(value)}/100`;
  return (
    <div className="rounded-card border border-border/70 bg-surface-2/30 p-3">
      <div className="text-[11px] uppercase tracking-wider text-muted">{label}</div>
      <div className={`mt-2 text-2xl font-semibold ${inverse ? "text-warning" : "text-text"}`}>{display}</div>
    </div>
  );
}
