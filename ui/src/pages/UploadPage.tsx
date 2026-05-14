/**
 * Upload page — drop zone + sample replays per docs/04-ui-ux-design.md §4.1.
 * Posts to FastAPI /api/sessions, navigates to the session detail page.
 *
 * v6 plan task 3.2 addition: when `GET /api/torcs-status` reports the
 * torcs-telemetry volume has JSONL runs available (i.e., the user is
 * running `podman compose --profile torcs up` AND has driven at least
 * one capture via gym_torcs's torcs_jm_par.py with OVERRIDE_LOG_TELEMETRY
 * set), surface a banner with per-run "Ingest" buttons. Progressive
 * enhancement — invisible when the torcs profile isn't running.
 */

import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { OverrideApiError, api, type FixtureName } from "@/api/client";
import type { TorcsRunSummary } from "@/api/types";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { FileUpload } from "@/components/FileUpload";
import { TorcsControlPanel } from "@/components/TorcsControlPanel";

// Phase 4: page the Live TORCS banner so 19+ runs don't push the rest of
// the page off-screen. Small page so the banner stays compact in the
// overall upload layout.
const RUN_PAGE_SIZE = 10;

export function UploadPage() {
  const navigate = useNavigate();
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [torcsRuns, setTorcsRuns] = useState<TorcsRunSummary[]>([]);
  const [runsTotal, setRunsTotal] = useState(0);
  const [runsOffset, setRunsOffset] = useState(0);
  const [runDelete, setRunDelete] = useState<string | null>(null);
  const [runDeleting, setRunDeleting] = useState(false);

  const onFile = useCallback(
    async (file: File) => {
      setIsUploading(true);
      setError(null);
      try {
        const session = await api.createSession({
          file,
          source: file.name.endsWith(".parquet") ? "fastf1" : "torcs",
          socMax: 4.0,
        });
        navigate(`/session/${session.summary.session_id}`);
      } catch (e) {
        const msg =
          e instanceof OverrideApiError
            ? `${e.payload.message}${e.payload.detail ? ` — ${e.payload.detail}` : ""}`
            : e instanceof Error
            ? e.message
            : "Upload failed.";
        setError(msg);
      } finally {
        setIsUploading(false);
      }
    },
    [navigate],
  );

  // Load a page of TORCS-volume runs. Re-callable so delete + pagination
  // can refresh without a route remount. Silent on error — the endpoint
  // always returns 200 in normal operation; a thrown error usually means
  // the backend itself is down, which surfaces in other ways.
  const loadRuns = useCallback(async (offset: number) => {
    try {
      const res = await api.torcsStatus({ limit: RUN_PAGE_SIZE, offset });
      if (res.available) {
        setTorcsRuns(res.runs);
        setRunsTotal(res.total ?? res.runs.length);
        setRunsOffset(res.offset ?? offset);
      } else {
        setTorcsRuns([]);
        setRunsTotal(0);
        setRunsOffset(0);
      }
    } catch {
      // ignore — see comment above
    }
  }, []);

  useEffect(() => {
    void loadRuns(0);
  }, [loadRuns]);

  const onIngestRun = useCallback(async (runId: string) => {
    setIsUploading(true);
    setError(null);
    try {
      const session = await api.runTorcsLive(runId);
      navigate(`/session/${session.summary.session_id}`);
    } catch (e) {
      const msg =
        e instanceof OverrideApiError
          ? `${e.payload.message}${e.payload.detail ? ` — ${e.payload.detail}` : ""}`
          : e instanceof Error
          ? e.message
          : "Live ingest failed.";
      setError(msg);
    } finally {
      setIsUploading(false);
    }
  }, [navigate]);

  const confirmRunDelete = useCallback(async () => {
    if (!runDelete) return;
    setRunDeleting(true);
    try {
      await api.deleteTorcsRun(runDelete);
      setRunDelete(null);
      // Refresh — if the deletion empties the current page, step back one.
      const newTotal = Math.max(0, runsTotal - 1);
      const newOffset =
        runsOffset > 0 && newTotal <= runsOffset ? Math.max(0, runsOffset - RUN_PAGE_SIZE) : runsOffset;
      await loadRuns(newOffset);
    } catch (e) {
      const msg =
        e instanceof OverrideApiError
          ? e.payload.message
          : e instanceof Error
          ? e.message
          : "Delete failed.";
      setError(msg);
      setRunDelete(null);
    } finally {
      setRunDeleting(false);
    }
  }, [runDelete, runsTotal, runsOffset, loadRuns]);

  const useSample = useCallback(
    async (fixtureName: FixtureName) => {
      // The fixture path returns a valid Session synthesized from the
      // corresponding tests/fixtures/*.json — see api/client.ts.
      setIsUploading(true);
      setError(null);
      try {
        const session = await api.createSession(
          {
            file: new File([], "sample.json", { type: "application/json" }),
            source: fixtureName === "torcs_engineer" ? "torcs" : "fastf1",
            socMax: 4.0,
          },
          { fixture: true, fixtureName },
        );
        navigate(`/session/${session.summary.session_id}?fixture=1`);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load sample.");
      } finally {
        setIsUploading(false);
      }
    },
    [navigate],
  );

  return (
    <div className="flex flex-col items-center pt-16 px-6">
      <h1 className="text-3xl font-semibold mb-2">Drop a session replay to begin</h1>
      <p className="text-muted text-sm mb-8">
        OVERRIDE will detect inefficient zones, reason over them, and ground every recommendation in the 2026 F1 regulations.
      </p>
      <FileUpload
        onFile={onFile}
        isUploading={isUploading}
        error={error}
        sampleReplays={[
          { label: "TORCS engineer demo", onClick: () => useSample("torcs_engineer") },
          { label: "Engineer happy-path demo", onClick: () => useSample("engineer_happy") },
          { label: "Layered-defense demo (cached)", onClick: () => useSample("layered_defense") },
        ]}
      />

      {/* Phase 2 — Start/Stop race controls. Hidden on the hosted demo
          (window.location.hostname guard) AND hidden when the override
          API reports the control plane isn't configured (server-side
          ENABLED flag). Defense in depth — see ADR-004 §security. */}
      <TorcsControlPanel />

      {/* Live TORCS banner — only renders when the torcs compose profile is
          running AND has emitted at least one JSONL capture. Progressive
          enhancement; invisible otherwise.
          Phase 4: paginates at RUN_PAGE_SIZE; runs that have already been
          ingested show an "Open session →" link instead of an Ingest button
          (which would 409 since /api/sessions/torcs-live adopts the same
          session_id); per-row × button deletes the JSONL after confirmation. */}
      {torcsRuns.length > 0 && (
        <section
          className="mt-8 w-full max-w-xl rounded-card border border-accent/40 bg-surface/60 p-4"
          aria-label="Live TORCS captures available"
        >
          <div className="flex items-baseline gap-2 mb-3">
            <span className="text-[11px] uppercase tracking-wider text-accent font-mono">
              Live TORCS detected
            </span>
            <span className="text-xs text-muted">
              {runsTotal} run{runsTotal === 1 ? "" : "s"} available
            </span>
          </div>
          <ul className="space-y-2">
            {torcsRuns.map((r) => {
              const ingested = r.ingested_session_id ?? null;
              return (
                <li
                  key={r.run_id}
                  className="flex items-center justify-between gap-3 rounded-md border border-border bg-surface p-2"
                >
                  <div className="flex flex-col min-w-0 flex-1">
                    <span className="font-mono text-sm text-text truncate" title={r.run_id}>
                      {r.run_id}
                    </span>
                    <span className="text-xs text-muted">
                      {(r.size_bytes / 1024).toFixed(0)} KB · ≈{r.lap_count_estimate} lap
                      {r.lap_count_estimate === 1 ? "" : "s"}
                      {ingested && (
                        <span className="ml-2 text-[10px] uppercase tracking-wider text-accent">
                          ingested
                        </span>
                      )}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    {ingested ? (
                      <Link
                        to={`/session/${encodeURIComponent(ingested)}`}
                        className="px-3 py-1.5 rounded-pill border border-border bg-surface-2 text-xs hover:bg-surface transition-colors"
                      >
                        Open session →
                      </Link>
                    ) : (
                      <button
                        type="button"
                        onClick={() => onIngestRun(r.run_id)}
                        disabled={isUploading}
                        className="px-3 py-1.5 rounded-pill bg-accent text-bg text-xs font-medium hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
                      >
                        Ingest →
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => setRunDelete(r.run_id)}
                      title="Delete this telemetry capture"
                      aria-label={`Delete ${r.run_id}`}
                      className="px-2 py-1 rounded text-muted hover:text-danger hover:bg-danger/10 text-sm leading-none transition-colors"
                    >
                      ×
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>

          {runsTotal > RUN_PAGE_SIZE && (
            <nav className="flex items-center justify-between mt-3 text-xs">
              <button
                type="button"
                onClick={() => loadRuns(Math.max(0, runsOffset - RUN_PAGE_SIZE))}
                disabled={runsOffset === 0}
                className="px-2 py-1 rounded-pill border border-border bg-surface hover:bg-surface-2 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                ← Newer
              </button>
              <span className="text-muted">
                {runsOffset + 1}–{runsOffset + torcsRuns.length} of {runsTotal}
              </span>
              <button
                type="button"
                onClick={() => loadRuns(runsOffset + RUN_PAGE_SIZE)}
                disabled={runsOffset + torcsRuns.length >= runsTotal}
                className="px-2 py-1 rounded-pill border border-border bg-surface hover:bg-surface-2 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Older →
              </button>
            </nav>
          )}
        </section>
      )}

      <ConfirmDialog
        open={runDelete !== null}
        title="Delete TORCS capture?"
        body={
          <p>
            This permanently removes the JSONL file{" "}
            <span className="font-mono text-text">{runDelete}.jsonl</span> from
            the shared torcs-telemetry volume. Any session previously ingested
            from this run is kept; only the raw capture is unlinked.
          </p>
        }
        confirmLabel="Delete capture"
        confirmVariant="danger"
        busy={runDeleting}
        onConfirm={confirmRunDelete}
        onCancel={() => { if (!runDeleting) setRunDelete(null); }}
      />
    </div>
  );
}
