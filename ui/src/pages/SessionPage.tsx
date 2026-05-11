/**
 * Session detail page (P3.3 polish).
 * Per docs/04-ui-ux-design.md §4.2.
 *
 * Adds vs P3.2:
 *  - ZoneHeatmap below the energy curve
 *  - Curve-triangle and heatmap-cell clicks scroll the matching
 *    recommendation card into view (deep-link-friendly via ?zone=…)
 *  - Lazy Fan-Mode fetching with per-zone cache (kept from P3.2)
 *  - Validator-failed-permanently and low-confidence cards render their
 *    failure-mode treatment per §7
 *  - Footer cites RegulationSource (document_title, issue, § section)
 *    from the struct — never a hardcoded string
 */

import { useCallback, useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import { OverrideApiError, api } from "@/api/client";
import type { FanOutput, Session } from "@/api/types";
import { EnergyCurve } from "@/components/EnergyCurve";
import {
  EmptyState,
  ErrorBanner,
  GroundingPendingBanner,
  LoadingSkeleton,
} from "@/components/EmptyStates";
import { ModeToggle, type Mode } from "@/components/ModeToggle";
import { RecommendationCard } from "@/components/RecommendationCard";
import { ZoneHeatmap } from "@/components/ZoneHeatmap";

export function SessionPage() {
  const { sessionId = "" } = useParams<{ sessionId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  // `?fixture=1` / `?fixture=0` force the mode for this tab; absent → let the
  // env default (VITE_USE_FIXTURE) decide. Passing `undefined` keeps the `??`
  // fallback inside api.client intact — passing an explicit `false` would
  // override the env default and route through the live API.
  const fixtureParam = searchParams.get("fixture");
  const fixture: boolean | undefined =
    fixtureParam === "1" ? true : fixtureParam === "0" ? false : undefined;

  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("engineer");
  const [fanCache, setFanCache] = useState<Record<string, FanOutput>>({});
  /** Per-zone error message when /api/zones/.../?mode=fan fails. The zone
   *  card stays on Engineer with a small banner, per FR-7 + the §7
   *  "Fan translation unavailable" UX. */
  const [fanErrors, setFanErrors] = useState<Record<string, string>>({});
  /** Per-zone in-flight flag — true between request start and resolution. */
  const [fanInflight, setFanInflight] = useState<Record<string, boolean>>({});

  // Load the session
  useEffect(() => {
    let cancelled = false;
    setSession(null);
    setError(null);
    api
      .getSession(sessionId, { fixture })
      .then((s) => !cancelled && setSession(s))
      .catch((e) => {
        if (cancelled) return;
        const msg =
          e instanceof OverrideApiError
            ? `${e.payload.message}${e.payload.detail ? ` — ${e.payload.detail}` : ""}`
            : e instanceof Error
            ? e.message
            : "Failed to load session.";
        setError(msg);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, fixture]);

  // Lazy Fan-Mode hydration when toggling to Fan.
  // Per FR-7.4: only fetch zones we don't have cached + don't have a
  // recorded error for. Per the §7 fallback: if a fan fetch fails, that
  // zone card stays on Engineer with a small banner; we don't block the
  // whole page on one failure.
  useEffect(() => {
    if (mode !== "fan" || !session) return;
    const missing = session.recommendations.filter(
      (r) => !fanCache[r.zone.zone_id] && !fanErrors[r.zone.zone_id],
    );
    if (missing.length === 0) return;
    let cancelled = false;
    setFanInflight((prev) => {
      const next = { ...prev };
      for (const r of missing) next[r.zone.zone_id] = true;
      return next;
    });

    Promise.all(
      missing.map((r) =>
        api
          .getZone(sessionId, r.zone.zone_id, "fan", { fixture })
          .then((rec) => ({ zid: r.zone.zone_id, fan: rec.fan, error: null as string | null }))
          .catch((e) => ({
            zid: r.zone.zone_id,
            fan: null,
            error:
              e instanceof OverrideApiError
                ? e.payload.message
                : e instanceof Error
                ? e.message
                : "Fan translation request failed.",
          })),
      ),
    ).then((entries) => {
      if (cancelled) return;
      setFanCache((prev) => {
        const next = { ...prev };
        for (const e of entries) {
          if (e.fan) next[e.zid] = e.fan;
        }
        return next;
      });
      setFanErrors((prev) => {
        const next = { ...prev };
        for (const e of entries) {
          if (e.error) next[e.zid] = e.error;
        }
        return next;
      });
      setFanInflight((prev) => {
        const next = { ...prev };
        for (const e of entries) delete next[e.zid];
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, session]);

  // Scroll a recommendation card into view + record selection in URL
  const onZoneClick = useCallback(
    (zoneId: string) => {
      const next = new URLSearchParams(searchParams);
      next.set("zone", zoneId);
      setSearchParams(next, { replace: true });
      const el = document.querySelector<HTMLElement>(`[data-zone-id="${zoneId}"]`);
      el?.scrollIntoView({ behavior: "smooth", block: "start" });
      el?.focus({ preventScroll: true });
    },
    [searchParams, setSearchParams],
  );

  // Auto-scroll on initial load if ?zone=… is present
  useEffect(() => {
    if (!session) return;
    const zid = searchParams.get("zone");
    if (!zid) return;
    const el = document.querySelector<HTMLElement>(`[data-zone-id="${zid}"]`);
    el?.scrollIntoView({ block: "start" });
  }, [session, searchParams]);

  if (error) {
    return (
      <div className="px-6 py-8 max-w-5xl mx-auto">
        <ErrorBanner title="Session unavailable" detail={error} />
      </div>
    );
  }
  if (!session) {
    return (
      <div className="px-6 py-8 space-y-3 max-w-5xl mx-auto">
        <LoadingSkeleton lines={2} />
        <LoadingSkeleton lines={4} />
        <LoadingSkeleton lines={4} />
      </div>
    );
  }

  const groundingPending = session.regulation_source === null;

  return (
    <div className="max-w-5xl mx-auto px-6 py-6">
      {/* Header */}
      <header className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div className="flex items-baseline gap-3 flex-wrap">
          <span className="font-semibold text-lg">OVERRIDE</span>
          <span className="text-muted">·</span>
          <span className="text-sm text-muted">
            {session.summary.track_id ?? "—"} · {session.summary.lap_count} laps · uploaded{" "}
            <time dateTime={session.summary.uploaded_at}>
              {new Date(session.summary.uploaded_at).toLocaleString()}
            </time>
          </span>
        </div>
        <ModeToggle mode={mode} onChange={setMode} />
      </header>

      {session.summary.note && (
        <div className="mb-3 text-xs text-muted italic">{session.summary.note}</div>
      )}
      {groundingPending && (
        <div className="mb-4">
          <GroundingPendingBanner />
        </div>
      )}

      {/* Energy curve + zone heatmap */}
      <section className="mb-6 space-y-3">
        <EnergyCurve
          laps={session.laps}
          forecast={session.forecast}
          recommendations={session.recommendations}
          onZoneClick={onZoneClick}
        />
        <ZoneHeatmap
          totalLaps={session.summary.lap_count}
          recommendations={session.recommendations}
          onZoneClick={onZoneClick}
        />
      </section>

      {/* Recommendations */}
      <section className="space-y-4">
        <h2 className="text-sm uppercase tracking-wider text-muted mb-1">
          Recommendations ({session.recommendations.length})
        </h2>
        {session.recommendations.length === 0 ? (
          <EmptyState
            icon="✓"
            title="No inefficient zones detected"
            body="The session was clean — every lap stayed inside the energy envelope."
          />
        ) : (
          session.recommendations.map((r) => (
            <RecommendationCard
              key={r.zone.zone_id}
              recommendation={r}
              fan={fanCache[r.zone.zone_id]}
              fanLoading={!!fanInflight[r.zone.zone_id]}
              fanError={fanErrors[r.zone.zone_id] ?? null}
              mode={mode}
            />
          ))
        )}
      </section>

      {/* Footer — regulation source rendered from the struct, never hardcoded */}
      {session.regulation_source && (
        <footer className="mt-8 pt-4 border-t border-border text-xs text-muted">
          Grounded in <span className="text-text">{session.regulation_source.document_title}</span>,{" "}
          {session.regulation_source.issue} ·{" "}
          <span className="text-text font-medium">§ {session.regulation_source.section}</span>
          {" · "}
          <a
            href={session.regulation_source.public_url}
            target="_blank"
            rel="noreferrer"
            className="text-accent hover:underline"
          >
            FIA source ↗
          </a>
        </footer>
      )}
    </div>
  );
}
