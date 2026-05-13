/**
 * TorcsControlPanel — Phase 2 Start/Stop race buttons.
 *
 * Surface contract:
 * 1. Hosted demo (Cloudflare Tunnel → override.patrickndille.com): the
 *    browser-side `window.location.hostname` check returns false, the
 *    whole panel doesn't render. Per ADR-004 §security, the control
 *    plane is intentionally NOT exposed publicly.
 * 2. Local dev WITHOUT --profile torcs: the server-side `enabled`
 *    flag from /api/torcs/control-status reports the daemon URL/secret
 *    aren't configured; we render a small "control plane disabled"
 *    hint pointing at the right podman compose command.
 * 3. Local dev WITH --profile torcs but daemon not yet reachable
 *    (still booting): `enabled=true, reachable=false` → "Starting…"
 *    status, buttons disabled.
 * 4. Local dev, daemon up, no active race: "Start Race" enabled.
 * 5. Local dev, daemon up, active race: "Stop Race" enabled +
 *    active session_id surfaced as a deep link.
 *
 * Defense-in-depth: even if a savvy operator forces the UI to render
 * by spoofing localhost, the API proxy STILL refuses with 503
 * CONTROL_DISABLED when TORCS_CONTROL_SECRET is unset. The hostname
 * check is UX scaffolding, not a security boundary.
 */

import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { OverrideApiError, api } from "@/api/client";
import type { TorcsControlStatus } from "@/api/types";

const POLL_INTERVAL_MS = 5000;

function isLocalHost(): boolean {
  if (typeof window === "undefined") return false;
  const h = window.location.hostname;
  return h === "localhost" || h === "127.0.0.1" || h === "::1";
}

export function TorcsControlPanel() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<TorcsControlStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const s = await api.torcsControlStatus();
      setStatus(s);
    } catch (_e) {
      // Endpoint always returns 200 in normal operation; a thrown error
      // means the backend is down — silently keep last-known state.
    }
  }, []);

  useEffect(() => {
    if (!isLocalHost()) return;
    refresh();
    const id = window.setInterval(refresh, POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [refresh]);

  const onStart = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      // Pass a human-readable track_name so the Sessions list shows
      // "Aalborg" rather than the verbose torcs-live/s_torcs_live_... slug.
      // v1.1 will surface a track-picker in the UI; for v1.0 default to Aalborg
      // (the most-tested track in the IBM SkillsBuild lab).
      const resp = await api.startTorcsRace({
        track: "aalborg",
        laps: 10,
        track_name: "Aalborg",
      });
      // The session row doesn't exist on disk yet — gym_torcs needs to
      // run, telemetry needs to land, then the user (or a future
      // automation step) POSTs torcs-live. For v1.0 the user manually
      // ingests via the existing banner once the JSONL appears; we
      // don't auto-navigate here to avoid landing on a 404.
      await refresh();
      setError(
        `Driver client started — pid ${resp.pid}, session_id ${resp.session_id}.\n\n` +
          `Next steps (the IBM SkillsBuild lab requires TORCS itself to be launched ` +
          `manually in noVNC before the driver client can connect):\n` +
          `1. Open http://localhost:6080/vnc.html → Applications → Games → TORCS.\n` +
          `2. In TORCS: Race → Quick Race → Configure → set scr_server as a driver.\n` +
          `3. Click "New Race" — TORCS launches; the AI driver connects via UDP :3001.\n` +
          `4. Once a lap completes, click "Ingest →" on the Live TORCS banner below ` +
          `to land the session for analysis.\n\n` +
          `Or skip steps 1-3 if TORCS is already running in noVNC — the driver is ` +
          `already trying to connect.`,
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
  }, [refresh]);

  const onStop = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const resp = await api.stopTorcsRace();
      await refresh();
      setError(
        resp.status === "stopped"
          ? `Race stopped (exit ${resp.exit_code ?? "-"}).`
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

  // Hosted demo: completely hide the panel. Judges who want this clone
  // the repo and run `podman compose --profile torcs up` locally —
  // documented in README.
  if (!isLocalHost()) return null;

  // Loading initial status
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

  return (
    <section
      className="mt-8 w-full max-w-xl rounded-card border border-accent/30 bg-surface/60 p-4"
      aria-label="TORCS race control"
    >
      <header className="flex items-center justify-between mb-3">
        <span className="text-[11px] uppercase tracking-wider text-accent font-mono">
          Race control
        </span>
        <ControlBadge status={status} />
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
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onStart}
            disabled={busy || status.active}
            className="px-3 py-1.5 rounded-pill bg-accent text-bg text-sm font-medium hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Start race
          </button>
          <button
            type="button"
            onClick={onStop}
            disabled={busy || !status.active}
            className="px-3 py-1.5 rounded-pill border border-border bg-surface text-sm hover:bg-surface-2 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Stop race
          </button>
          {status.active && status.session_id && (
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
      )}

      {error && (
        <p className="mt-3 text-xs text-muted whitespace-pre-line">{error}</p>
      )}
    </section>
  );
}

function ControlBadge({ status }: { status: TorcsControlStatus }) {
  let label: string;
  let tone: string;
  if (!status.enabled) {
    label = "Disabled";
    tone = "text-muted";
  } else if (!status.reachable) {
    label = "Starting…";
    tone = "text-warning";
  } else if (status.active) {
    label = "Live";
    tone = "text-accent";
  } else {
    label = "Idle";
    tone = "text-muted";
  }
  return <span className={`text-xs ${tone}`}>{label}</span>;
}
