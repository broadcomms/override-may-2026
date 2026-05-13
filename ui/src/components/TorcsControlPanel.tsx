/**
 * TorcsControlPanel — Phase 2 + 2.5 Start/Stop race UI.
 *
 * Surface contract:
 * 1. Hosted demo (Cloudflare Tunnel → override.patrickndille.com): the
 *    `window.location.hostname` check returns false, the whole panel
 *    doesn't render. Per ADR-004 §security, the control plane is
 *    intentionally NOT exposed publicly.
 * 2. Local dev WITHOUT --profile torcs: the server-side `enabled` flag
 *    from /api/torcs/control-status reports the daemon URL/secret aren't
 *    configured; we render a small "control plane disabled" hint.
 * 3. Local dev WITH --profile torcs but daemon not yet reachable: the
 *    "Starting…" badge + detail string surfaces while torcs container
 *    boots (~90s on first run).
 * 4. Daemon reachable, race not active: track dropdown + lap count input
 *    + "Start race" enabled.
 * 5. Race in progress: state-aware badge ("Launching…" / "Waiting for
 *    simulator…" / "Connecting client…" / "Live") + "Stop race" enabled
 *    + "View live →" link to the session detail page.
 *
 * Defense-in-depth: even if a savvy operator forces the panel to render
 * via dev tools, the API proxy STILL refuses with 503 CONTROL_DISABLED
 * when TORCS_CONTROL_SECRET is unset. The hostname check is UX
 * scaffolding, not a security boundary.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { OverrideApiError, api } from "@/api/client";
import type { TorcsControlStatus, TorcsRaceState, TorcsTrack } from "@/api/types";

const POLL_INTERVAL_MS = 3000;

// Architect-recommended: bubble the 6 most-tested road tracks to the top
// of the dropdown so judges land on safe defaults. Below the divider,
// the full TORCS library appears alphabetically grouped by category.
const RECOMMENDED_TRACKS = ["aalborg", "alpine-1", "e-track-3", "forza", "ruudskogen", "wheel-1"];

// Fallback hardcoded list when the daemon's /control/tracks endpoint
// isn't reachable (e.g. fixture-mode or backend down). Subset of road
// tracks; ensures the UI still shows something usable.
const FALLBACK_TRACKS: TorcsTrack[] = RECOMMENDED_TRACKS.map((name) => ({
  name,
  category: "road",
}));

function isLocalHost(): boolean {
  if (typeof window === "undefined") return false;
  const h = window.location.hostname;
  return h === "localhost" || h === "127.0.0.1" || h === "::1";
}

function labelForState(state: TorcsRaceState | null): { label: string; tone: string } {
  switch (state) {
    case "launching":
      return { label: "Launching…", tone: "text-warning" };
    case "waiting_scr":
      return { label: "Waiting for simulator…", tone: "text-warning" };
    case "connecting":
      return { label: "Connecting client…", tone: "text-warning" };
    case "active":
      return { label: "Live", tone: "text-accent" };
    case "stopping":
      return { label: "Stopping…", tone: "text-muted" };
    case "cleanup":
      return { label: "Cleaning up…", tone: "text-muted" };
    case "idle":
    case null:
      return { label: "Idle", tone: "text-muted" };
  }
}

function sortedTracks(tracks: TorcsTrack[]): TorcsTrack[] {
  // Bubble RECOMMENDED_TRACKS to top (preserving recommended order),
  // then alphabetical by category then name.
  const recSet = new Set(RECOMMENDED_TRACKS);
  const rec = RECOMMENDED_TRACKS
    .map((name) => tracks.find((t) => t.name === name))
    .filter((t): t is TorcsTrack => t !== undefined);
  const rest = tracks
    .filter((t) => !recSet.has(t.name))
    .sort((a, b) => {
      if (a.category !== b.category) return a.category.localeCompare(b.category);
      return a.name.localeCompare(b.name);
    });
  return [...rec, ...rest];
}

export function TorcsControlPanel() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<TorcsControlStatus | null>(null);
  const [tracks, setTracks] = useState<TorcsTrack[]>(FALLBACK_TRACKS);
  const [track, setTrack] = useState<string>("aalborg");
  const [laps, setLaps] = useState<number>(5);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const s = await api.torcsControlStatus();
      setStatus(s);
    } catch (_e) {
      // 200-always endpoint; a thrown error means backend down — keep last state
    }
  }, []);

  useEffect(() => {
    if (!isLocalHost()) return;
    refresh();
    const id = window.setInterval(refresh, POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [refresh]);

  // Load the track list once the daemon is reachable.
  useEffect(() => {
    if (!isLocalHost()) return;
    if (!status?.enabled || !status?.reachable) return;
    let cancelled = false;
    api.torcsTracks()
      .then((r) => {
        if (cancelled) return;
        if (r.tracks.length > 0) setTracks(sortedTracks(r.tracks));
      })
      .catch(() => { /* keep fallback list */ });
    return () => { cancelled = true; };
  }, [status?.enabled, status?.reachable]);

  const onStart = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      // Humanize the operator-supplied track slug into a display label
      // (capitalize first letter, hyphens preserved). aalborg → "Aalborg".
      const track_name = track.charAt(0).toUpperCase() + track.slice(1);
      const resp = await api.startTorcsRace({ track, laps, track_name });
      await refresh();
      setError(
        `Race launching on ${track_name} (${laps} laps). ` +
          `Daemon spawned torcs pid=${resp.torcs_pid ?? "?"} + scr-client pid=${resp.pid}. ` +
          `Watch the race in noVNC at http://localhost:6080/vnc.html; ` +
          `click "View live →" above to follow the per-lap telemetry stream.`,
      );
    } catch (e) {
      const msg =
        e instanceof OverrideApiError
          ? `${e.payload.message}${e.payload.detail ? ` — ${e.payload.detail}` : ""}`
          : e instanceof Error
          ? e.message
          : "Failed to start race.";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }, [refresh, track, laps]);

  const onStop = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const resp = await api.stopTorcsRace();
      await refresh();
      setError(
        resp.status === "stopped"
          ? `Race stopped (scr exit ${resp.scr_exit_code ?? "-"}, torcs exit ${resp.torcs_exit_code ?? "-"}).`
          : "No active race.",
      );
    } catch (e) {
      const msg =
        e instanceof OverrideApiError
          ? `${e.payload.message}${e.payload.detail ? ` — ${e.payload.detail}` : ""}`
          : e instanceof Error
          ? e.message
          : "Failed to stop race.";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }, [refresh]);

  // Hosted demo: completely hide the panel
  if (!isLocalHost()) return null;

  if (status === null) {
    return (
      <section
        className="mt-8 w-full max-w-xl rounded-card border border-border bg-surface/40 p-4"
        aria-label="TORCS race control"
      >
        <p className="text-xs text-muted">Probing TORCS control plane…</p>
      </section>
    );
  }

  const badge = labelForState(status.state ?? (status.active ? "active" : "idle"));
  // Start disabled in any non-idle state (busy guard + state machine)
  const startDisabled = busy || (status.state !== null && status.state !== "idle");
  // Stop enabled in any state that's "running enough" to have something to stop
  const stopEnabled =
    !busy &&
    (status.state === "active" ||
      status.state === "launching" ||
      status.state === "waiting_scr" ||
      status.state === "connecting");

  // Group tracks for the <optgroup> rendering
  const grouped = useMemo(() => {
    const recSet = new Set(RECOMMENDED_TRACKS);
    const recommended = tracks.filter((t) => recSet.has(t.name));
    const others: Record<string, TorcsTrack[]> = {};
    tracks
      .filter((t) => !recSet.has(t.name))
      .forEach((t) => {
        (others[t.category] ||= []).push(t);
      });
    return { recommended, others };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tracks]);

  return (
    <section
      className="mt-8 w-full max-w-xl rounded-card border border-accent/30 bg-surface/60 p-4"
      aria-label="TORCS race control"
    >
      <header className="flex items-center justify-between mb-3">
        <span className="text-[11px] uppercase tracking-wider text-accent font-mono">
          Race control
        </span>
        <ControlBadge labelText={badge.label} tone={badge.tone} />
      </header>

      {!status.enabled && (
        <p className="text-xs text-muted">
          Control plane disabled — set <code className="font-mono text-text">TORCS_CONTROL_SECRET</code> in
          .env and run <code className="font-mono text-text">podman compose --profile torcs up</code> to
          enable Start/Stop race controls.
        </p>
      )}

      {status.enabled && !status.reachable && (
        <p className="text-xs text-muted">
          Daemon not reachable yet — torcs container is still booting (noVNC + uvicorn handshake
          takes ~90 s on first run). {status.detail}
        </p>
      )}

      {status.enabled && status.reachable && (
        <>
          <div className="grid grid-cols-[1fr_auto] gap-2 mb-3">
            <label className="flex flex-col gap-1">
              <span className="text-[11px] uppercase tracking-wider text-muted">Track</span>
              <select
                value={track}
                onChange={(e) => setTrack(e.target.value)}
                disabled={startDisabled}
                className="px-2 py-1.5 rounded-md border border-border bg-surface text-sm font-mono disabled:opacity-50"
              >
                {grouped.recommended.length > 0 && (
                  <optgroup label="Recommended">
                    {grouped.recommended.map((t) => (
                      <option key={t.name} value={t.name}>{t.name}</option>
                    ))}
                  </optgroup>
                )}
                {Object.entries(grouped.others).map(([cat, ts]) => (
                  <optgroup key={cat} label={cat}>
                    {ts.map((t) => (
                      <option key={t.name} value={t.name}>{t.name}</option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-[11px] uppercase tracking-wider text-muted">Laps</span>
              <input
                type="number"
                min={1}
                max={200}
                value={laps}
                onChange={(e) => setLaps(Math.max(1, Math.min(200, parseInt(e.target.value, 10) || 1)))}
                disabled={startDisabled}
                className="w-20 px-2 py-1.5 rounded-md border border-border bg-surface text-sm font-mono disabled:opacity-50"
              />
            </label>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={onStart}
              disabled={startDisabled}
              className="px-3 py-1.5 rounded-pill bg-accent text-bg text-sm font-medium hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Start race
            </button>
            <button
              type="button"
              onClick={onStop}
              disabled={!stopEnabled}
              className="px-3 py-1.5 rounded-pill border border-border bg-surface text-sm hover:bg-surface-2 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Stop race
            </button>
            {status.session_id && (status.active || status.state === "launching" || status.state === "waiting_scr" || status.state === "connecting") && (
              <button
                type="button"
                onClick={() =>
                  status.session_id && navigate(`/session/${encodeURIComponent(status.session_id)}`)
                }
                className="ml-auto text-xs text-accent hover:underline"
                title="Open the active session's live-telemetry view"
              >
                View live → {status.session_id}
              </button>
            )}
          </div>
        </>
      )}

      {error && (
        <p className="mt-3 text-xs text-muted whitespace-pre-line">{error}</p>
      )}
    </section>
  );
}

function ControlBadge({ labelText, tone }: { labelText: string; tone: string }) {
  return <span className={`text-xs ${tone}`}>{labelText}</span>;
}
