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
import { useNavigate } from "react-router-dom";

import { OverrideApiError, api, type FixtureName } from "@/api/client";
import type { TorcsRunSummary } from "@/api/types";
import { FileUpload } from "@/components/FileUpload";

export function UploadPage() {
  const navigate = useNavigate();
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [torcsRuns, setTorcsRuns] = useState<TorcsRunSummary[]>([]);

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

  // Poll TORCS-volume status once on mount. No automatic refresh — the
  // user would typically navigate away if they're using the live path.
  // The banner stays hidden when the torcs compose profile isn't running.
  useEffect(() => {
    let cancelled = false;
    api
      .torcsStatus()
      .then((res) => {
        if (cancelled) return;
        setTorcsRuns(res.available ? res.runs : []);
      })
      .catch(() => {
        // Silent failure — endpoint always returns 200 in normal operation,
        // so a thrown error usually means the backend isn't up. Don't pollute
        // the upload page with that.
      });
    return () => { cancelled = true; };
  }, []);

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

      {/* Live TORCS banner — only renders when the torcs compose profile is
          running AND has emitted at least one JSONL capture. Progressive
          enhancement; invisible otherwise. */}
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
              {torcsRuns.length} run{torcsRuns.length === 1 ? "" : "s"} available
            </span>
          </div>
          <ul className="space-y-2">
            {torcsRuns.map((r) => (
              <li
                key={r.run_id}
                className="flex items-center justify-between gap-3 rounded-md border border-border bg-surface p-2"
              >
                <div className="flex flex-col">
                  <span className="font-mono text-sm text-text">{r.run_id}</span>
                  <span className="text-xs text-muted">
                    {(r.size_bytes / 1024).toFixed(0)} KB · ≈{r.lap_count_estimate} lap{r.lap_count_estimate === 1 ? "" : "s"}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => onIngestRun(r.run_id)}
                  disabled={isUploading}
                  className="px-3 py-1.5 rounded-pill bg-accent text-bg text-xs font-medium hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition-opacity"
                >
                  Ingest →
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
