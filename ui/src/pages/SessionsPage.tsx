/**
 * Sessions history page — Phase 1 ship.
 *
 * Backed by GET /api/sessions (the v6 plan Tier-2 endpoint, now wired in
 * Phase 1). Renders one row per saved session with a checkbox for
 * picking exactly two to compare via /sessions/compare. Click a row
 * (not the checkbox) to drill into /session/{id}.
 *
 * Empty state is intentional — a fresh clone has no sessions on disk;
 * the CTA points back at /upload (or the new "Live TORCS" path) so the
 * first-touch flow is obvious.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, OverrideApiError } from "@/api/client";
import type { SessionSummary } from "@/api/types";
import { EmptyState } from "@/components/EmptyStates";

const PAGE_SIZE = 50;

function formatUploaded(iso: string): string {
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

function formatDuration(startedAt: string | null, completedAt: string | null): string | null {
  if (!startedAt || !completedAt) return null;
  const s = new Date(startedAt).getTime();
  const e = new Date(completedAt).getTime();
  if (Number.isNaN(s) || Number.isNaN(e) || e <= s) return null;
  const secs = Math.round((e - s) / 1000);
  if (secs < 60) return `${secs}s`;
  const m = Math.floor(secs / 60);
  const r = secs % 60;
  return r === 0 ? `${m}m` : `${m}m ${r}s`;
}

export function SessionsPage() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const load = useCallback(async (newOffset: number) => {
    setLoading(true);
    setError(null);
    try {
      const r = await api.listSessions({ limit: PAGE_SIZE, offset: newOffset });
      setSessions(r.sessions);
      setTotal(r.total);
      setOffset(r.offset);
    } catch (e) {
      const msg =
        e instanceof OverrideApiError
          ? e.payload.message
          : e instanceof Error
          ? e.message
          : "Failed to load sessions.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(0);
  }, [load]);

  const toggleSelected = useCallback((sid: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(sid)) {
        next.delete(sid);
      } else {
        if (next.size >= 2) {
          // Drop oldest, keep newest two
          const first = next.values().next().value as string;
          next.delete(first);
        }
        next.add(sid);
      }
      return next;
    });
  }, []);

  const compareReady = selected.size === 2;
  const compareUrl = useMemo(() => {
    if (!compareReady) return null;
    const [a, b] = Array.from(selected);
    const qs = new URLSearchParams({ a, b });
    return `/sessions/compare?${qs.toString()}`;
  }, [selected, compareReady]);

  const handleCompare = useCallback(() => {
    if (compareUrl) navigate(compareUrl);
  }, [compareUrl, navigate]);

  const hasMore = offset + sessions.length < total;
  const hasPrev = offset > 0;

  return (
    <div className="px-6 py-12 max-w-5xl mx-auto">
      <header className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold">Sessions</h1>
        <div className="flex items-center gap-3">
          {selected.size > 0 && (
            <span className="text-sm text-muted">
              {selected.size === 1 ? "1 selected — pick a second to compare" : "2 selected"}
            </span>
          )}
          <button
            type="button"
            onClick={handleCompare}
            disabled={!compareReady}
            className="px-3 py-1.5 rounded-pill border border-border bg-surface text-sm hover:bg-surface-2 disabled:opacity-40 disabled:cursor-not-allowed"
            title={
              compareReady
                ? "Compare the two selected sessions side-by-side"
                : "Select two sessions to compare"
            }
          >
            Compare
          </button>
        </div>
      </header>

      {loading && <div className="text-sm text-muted">Loading…</div>}

      {error && (
        <div
          role="alert"
          className="rounded-card border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger mb-4"
        >
          {error}
        </div>
      )}

      {!loading && !error && sessions.length === 0 && (
        <EmptyState
          icon="↻"
          title="No sessions yet"
          body="Drop a session replay on /upload (or click one of the sample-replay pills) to land on the debrief view. Each session you process here will show up in this history."
          cta={
            <Link
              to="/upload"
              className="inline-block px-3 py-1.5 rounded-pill bg-accent text-bg text-sm font-medium hover:opacity-90"
            >
              Go to /upload
            </Link>
          }
        />
      )}

      {!loading && !error && sessions.length > 0 && (
        <>
          <ul className="divide-y divide-border/60 rounded-card border border-border bg-surface/40">
            {sessions.map((s) => {
              const isSelected = selected.has(s.session_id);
              const duration = formatDuration(s.started_at, s.completed_at);
              const trackLabel = s.track_name ?? s.track_id ?? "—";
              return (
                <li key={s.session_id} className="flex items-center gap-3 px-4 py-3">
                  <input
                    type="checkbox"
                    aria-label={`Select ${s.session_id} for comparison`}
                    checked={isSelected}
                    onChange={(e) => {
                      e.stopPropagation();
                      toggleSelected(s.session_id);
                    }}
                    className="cursor-pointer"
                  />
                  <Link
                    to={`/session/${encodeURIComponent(s.session_id)}`}
                    className="flex-1 grid grid-cols-12 gap-3 items-baseline hover:text-text"
                  >
                    <span className="col-span-3 text-sm font-mono truncate" title={s.session_id}>
                      {s.session_id}
                    </span>
                    <span className="col-span-2 text-xs text-muted">
                      {s.source}
                      {s.session_source === "torcs_live" && (
                        <span className="ml-1 px-1.5 py-0.5 rounded-pill bg-accent/15 text-accent text-[10px] uppercase tracking-wider">
                          live
                        </span>
                      )}
                    </span>
                    <span className="col-span-2 text-xs text-muted truncate" title={trackLabel}>
                      {trackLabel}
                    </span>
                    <span className="col-span-1 text-xs text-muted">
                      {s.lap_count} lap{s.lap_count === 1 ? "" : "s"}
                    </span>
                    <span className="col-span-1 text-xs text-muted">
                      {s.zone_count} zone{s.zone_count === 1 ? "" : "s"}
                    </span>
                    <span className="col-span-1 text-xs text-muted">{duration ?? ""}</span>
                    <span className="col-span-2 text-xs text-muted text-right">
                      {formatUploaded(s.uploaded_at)}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>

          {(hasPrev || hasMore) && (
            <nav className="flex items-center justify-between mt-4 text-sm">
              <button
                type="button"
                onClick={() => load(Math.max(0, offset - PAGE_SIZE))}
                disabled={!hasPrev}
                className="px-3 py-1.5 rounded-pill border border-border bg-surface hover:bg-surface-2 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                ← Newer
              </button>
              <span className="text-muted text-xs">
                {offset + 1}–{offset + sessions.length} of {total}
              </span>
              <button
                type="button"
                onClick={() => load(offset + PAGE_SIZE)}
                disabled={!hasMore}
                className="px-3 py-1.5 rounded-pill border border-border bg-surface hover:bg-surface-2 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Older →
              </button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}
