/**
 * RaceControlCard — Phase 2 + 2.5 Start/Stop race form.
 *
 * Phase B split from the previous monolithic TorcsControlPanel: this card
 * owns the *form* (status, track dropdown, lap input, headless toggle,
 * manual-setup disclosure, Start/Stop), and emits a disclosure link to
 * /cockpit for the noVNC view (which now lives on its own surface — see
 * CockpitPage). Per audit §20 don't #5, the noVNC iframe wrapper-clip
 * hack moved verbatim to CockpitPage; this file does not touch the
 * iframe at all.
 *
 * Surface contract (unchanged from TorcsControlPanel):
 * 1. Hosted demo (Cloudflare Tunnel → override.patrickndille.com): the
 *    `isLocalHost` check returns false, the whole card doesn't render.
 * 2. Local dev WITHOUT --profile torcs: server-side `enabled` flag from
 *    /api/torcs/control-status reports the daemon URL/secret aren't
 *    configured; render a small "control plane disabled" hint.
 * 3. Local dev WITH --profile torcs but daemon not yet reachable:
 *    "Starting…" badge + detail string surfaces while torcs container
 *    boots (~90s on first run).
 * 4. Daemon reachable, race not active: form enabled.
 * 5. Race in progress: state-aware badge + Stop enabled + View live link.
 *
 * Defense-in-depth: even if a savvy operator forces the card to render
 * via dev tools, the API proxy STILL refuses with 503 CONTROL_DISABLED
 * when TORCS_CONTROL_SECRET is unset. The hostname check is UX
 * scaffolding, not a security boundary.
 */

import { useCallback, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import {
  isTorcsActiveState,
  labelForTorcsState,
  useTorcsControl,
} from "@/hooks/useTorcsControl";
import { hasTorcsSurface } from "@/lib/env";

export function RaceControlCard() {
  const navigate = useNavigate();
  const {
    status,
    groupedTracks: grouped,
    track,
    setTrack,
    laps,
    setLaps,
    busy,
    error,
    startRace,
    stopRace,
  } = useTorcsControl();
  const [message, setMessage] = useState<string | null>(null);
  // Phase 2.6 correction: default is manual-launch (3D visible in noVNC).
  // Headless is opt-in for operators who want batch/CI-shape races.
  const [autoLaunch, setAutoLaunch] = useState<boolean>(false);
  const trackName = track.charAt(0).toUpperCase() + track.slice(1);

  const onStart = useCallback(async () => {
    try {
      const resp = await startRace({ autoLaunchTorcs: autoLaunch });
      setMessage(
        autoLaunch
          ? `Headless race launching on ${trackName} (${laps} laps). ` +
            `torcs pid=${resp.torcs_pid ?? "?"} + scr-client pid=${resp.pid}. ` +
            `NOTE: torcs -r is text-mode by design — no 3D in noVNC. ` +
            `Live telemetry will stream in the panel above; click "View live →".`
          : `SCR client connected (pid=${resp.pid}) to your manually-launched TORCS. ` +
            `If you see "Server has stopped the race" in TORCS GUI, the race ` +
            `wasn't running yet — set up scr_server driver in Quick Race and ` +
            `click New Race in TORCS GUI before pressing Start race again.`,
      );
    } catch (_error) {
      setMessage(null);
    }
  }, [autoLaunch, laps, startRace, trackName]);

  const onStop = useCallback(async () => {
    try {
      const resp = await stopRace();
      setMessage(
        resp.status === "stopped"
          ? `Race stopped (scr exit ${resp.scr_exit_code ?? "-"}, torcs exit ${resp.torcs_exit_code ?? "-"}).`
          : "No active race.",
      );
    } catch (_error) {
      setMessage(null);
    }
  }, [stopRace]);

  if (!hasTorcsSurface()) return null;

  if (status === null) {
    return (
      <section
        className="rounded-card border border-border bg-surface p-4"
        aria-label="TORCS race control"
      >
        <p className="text-xs text-muted">Probing TORCS control plane…</p>
      </section>
    );
  }

  const badge = labelForTorcsState(status.state ?? (status.active ? "active" : "idle"));
  const startDisabled = busy || (status.state !== null && status.state !== "idle");
  const stopEnabled = !busy && isTorcsActiveState(status.state ?? null);

  return (
    <section
      className="rounded-card border border-border bg-surface p-4"
      aria-label="TORCS race control"
    >
      <header className="flex items-center justify-between mb-3">
        <span className="text-[11px] uppercase tracking-wider text-muted font-mono">
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
          {status.starting
            ? "Control daemon is warming up — TORCS container is still booting (noVNC + uvicorn handshake takes ~90 s on first run)."
            : `Control daemon is unreachable. ${status.detail ?? "Check that the torcs container is still running."}`}
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

          {/* Phase 2.6 correction: TORCS's `-r` flag is documented as
              "command line mode" — headless by design. Operator must
              manually launch TORCS in noVNC for 3D rendering. UI defaults
              to the manual flow with this checkbox opt-in for headless. */}
          <label className="flex items-center gap-2 mb-3 text-xs text-muted cursor-pointer">
            <input
              type="checkbox"
              checked={autoLaunch}
              onChange={(e) => setAutoLaunch(e.target.checked)}
              disabled={startDisabled}
              className="cursor-pointer"
            />
            <span>
              Headless mode <span className="text-text/60">— skip 3D rendering; faster, ideal for batch capture or CI</span>
            </span>
          </label>

          {!autoLaunch && (
            <details className="mb-3 text-xs text-muted">
              <summary className="cursor-pointer hover:text-text">
                Manual TORCS setup — first time only (~30 s)
              </summary>
              <ol className="ml-5 mt-2 space-y-1 list-decimal">
                <li>Open TORCS in the cockpit view (or in a terminal: <code className="font-mono">torcs &amp;</code>)</li>
                <li>Race → Quick Race → Configure Race</li>
                <li>Drivers: add <code className="font-mono">scr_server 1</code> and remove the default robot</li>
                <li>Accept → Accept → <strong>New Race</strong>. The 3D race opens, cars wait at the grid for the SCR client.</li>
                <li>Click <strong>Start race</strong> here — the SCR client connects, the AI starts driving, telemetry streams.</li>
              </ol>
            </details>
          )}

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

          {/* Brief B3: disclosure link to the dedicated cockpit surface.
              Same-tab navigation; the page itself is full-bleed noVNC. */}
          <Link
            to="/cockpit"
            className="mt-3 inline-block text-xs text-muted hover:text-accent transition-colors"
          >
            Open cockpit view ↗
          </Link>
        </>
      )}

      {(error || message) && (
        <p className="mt-3 text-xs text-muted whitespace-pre-line">{error ?? message}</p>
      )}
    </section>
  );
}

function ControlBadge({ labelText, tone }: { labelText: string; tone: string }) {
  return <span className={`text-xs ${tone}`}>{labelText}</span>;
}
