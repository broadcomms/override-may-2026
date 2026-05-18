import { useCallback, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import type { TorcsLaunchMode, TorcsTrack } from "@/api/types";
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
    driverProfiles,
    driverProfileId,
    setDriverProfileId,
    groupedTracks: grouped,
    tracks,
    track,
    setTrack,
    laps,
    setLaps,
    busy,
    error,
    startRace,
    stopRace,
  } = useTorcsControl();
  const [launchMode, setLaunchMode] = useState<TorcsLaunchMode>("cockpit_practice");
  const [message, setMessage] = useState<string | null>(null);

  const selectedTrack = useMemo(
    () => tracks.find((item) => item.name === track) ?? tracks[0] ?? null,
    [track, tracks],
  );
  const selectedProfile = useMemo(
    () => driverProfiles.find((item) => item.profile_id === driverProfileId) ?? null,
    [driverProfileId, driverProfiles],
  );

  const trackName = selectedTrack?.display_name ?? track;

  const onStart = useCallback(async () => {
    try {
      const resp = await startRace({ launchMode, driverProfileId });
      setMessage(
        launchMode === "headless_quickrace"
          ? `Headless quickrace started on ${trackName} for ${resp.laps} laps with ${resp.driver_profile_name_hint ?? selectedProfile?.name ?? "the selected driver profile"}. OVERRIDE is capturing telemetry without the 3D cockpit surface.`
          : `Visible Practice launch started on ${trackName} for ${resp.laps} laps with ${resp.driver_profile_name_hint ?? selectedProfile?.name ?? "the selected driver profile"}. OVERRIDE is launching TORCS through the cockpit surface plus live telemetry.`,
      );
      navigate("/cockpit");
    } catch (_error) {
      setMessage(null);
    }
  }, [driverProfileId, launchMode, navigate, selectedProfile?.name, startRace, trackName]);

  const onStop = useCallback(async () => {
    try {
      const resp = await stopRace();
      setMessage(
        resp.status === "stopped"
          ? "Race stopped. OVERRIDE closed the simulator and kept the next run under Upload control."
          : "No active race was running.",
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
  const needsAttention = Boolean(status.last_error) || status.state === "cleanup";

  return (
    <section
      className="rounded-card border border-border bg-surface p-4"
      aria-label="TORCS race control"
    >
      <header className="flex items-center justify-between gap-3 mb-3">
        <span className="text-[11px] uppercase tracking-wider text-muted font-mono">
          Race control
        </span>
        <ControlBadge labelText={badge.label} tone={badge.tone} />
      </header>

      {!status.enabled && (
        <p className="text-xs text-muted">
          Control plane disabled. Set <code className="font-mono text-text">TORCS_CONTROL_SECRET</code> in
          <code className="ml-1 font-mono text-text">.env</code> and run
          <code className="mx-1 font-mono text-text">podman-compose up override torcs</code>
          to enable OVERRIDE-owned live capture.
        </p>
      )}

      {status.enabled && !status.reachable && (
        <p className="text-xs text-muted">
          {status.starting
            ? "Control daemon is warming up. The torcs container is still booting its kiosk surface and telemetry services."
            : `Control daemon is unreachable. ${status.detail ?? "Check that the torcs container is still running."}`}
        </p>
      )}

      {status.enabled && status.reachable && (
        <>
          {(needsAttention || status.state === "stopping") && (
            <div className="mb-4 rounded-md border border-warning/35 bg-warning/10 px-3 py-2">
              <div className="text-[11px] font-mono uppercase tracking-[0.22em] text-warning">
                Simulator status
              </div>
              <p className="mt-1 text-xs text-muted">
                {status.last_error
                  ? status.last_error
                  : "OVERRIDE is finishing the previous shutdown. Start will re-enable once the simulator is fully closed."}
              </p>
            </div>
          )}

          <div className="grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
            <div className="space-y-3">
              <div className="grid grid-cols-[1fr_auto] gap-2 padding-2">
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
                        {grouped.recommended.map((item) => (
                          <option key={item.name} value={item.name}>
                            {item.display_name}
                          </option>
                        ))}
                      </optgroup>
                    )}
                    {Object.entries(grouped.others).map(([category, items]) => (
                      <optgroup key={category} label={category}>
                        {items.map((item) => (
                          <option key={item.name} value={item.name}>
                            {item.display_name}
                          </option>
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
                    onChange={(e) =>
                      setLaps(Math.max(1, Math.min(200, parseInt(e.target.value, 10) || 1)))
                    }
                    disabled={startDisabled}
                    className="w-24 px-2 py-1.5 rounded-md border border-border bg-surface text-sm font-mono disabled:opacity-50"
                  />
                </label>
              </div>

              <div className="space-y-1">
                <span className="text-[11px] uppercase tracking-wider text-muted">Launch mode</span>
                <div className="inline-flex w-full rounded-pill border border-border bg-surface p-0.5 text-sm">
                  <ModeButton
                    active={launchMode === "cockpit_practice"}
                    label="Visible Practice"
                    description="3D TORCS race display"
                    onClick={() => setLaunchMode("cockpit_practice")}
                    disabled={startDisabled}
                  />
                  <ModeButton
                    active={launchMode === "headless_quickrace"}
                    label="Headless Capture"
                    description="Fast race without 3D"
                    onClick={() => setLaunchMode("headless_quickrace")}
                    disabled={startDisabled}
                  />
                </div>
              </div>

              <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
                <label className="flex flex-col gap-1">
                  <span className="text-[11px] uppercase tracking-wider text-muted">Driver profile</span>
                  <select
                    value={driverProfileId}
                    onChange={(e) => setDriverProfileId(e.target.value)}
                    disabled={startDisabled || driverProfiles.length === 0}
                    className="px-2 py-1.5 rounded-md border border-border bg-surface text-sm disabled:opacity-50"
                  >
                    {driverProfiles.map((profile) => (
                      <option key={profile.profile_id} value={profile.profile_id}>
                        {profile.name}
                      </option>
                    ))}
                    {driverProfiles.length === 0 && <option value="baseline">Baseline Demo Driver</option>}
                  </select>
                </label>
                <Link
                  to="/driver-lab"
                  className="inline-flex items-center justify-center rounded-pill border border-border px-3 py-1.5 text-sm text-muted transition-colors hover:text-text"
                >
                  Driver Lab ↗
                </Link>
              </div>

              {selectedProfile && (
                <p className="text-xs text-muted">
                  {selectedProfile.description ?? "No profile notes yet."} {selectedProfile.read_only ? "Shipped default profile." : "Saved in local Driver Lab storage."}
                </p>
              )}

              <p className="text-xs text-muted">
                {launchMode === "cockpit_practice"
                  ? "OVERRIDE owns the supported visible Practice path here: configured track/laps, scr_server 1, then TORCS launches the New Race from the cockpit surface."
                  : "Headless mode keeps the legacy quickrace-style capture path for faster batch runs and smoke checks."}
              </p>

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
                <Link
                  to="/cockpit"
                  className="ml-auto text-xs text-accent transition-colors hover:text-text"
                >
                  Open cockpit view ↗
                </Link>
              </div>
            </div>

            <TrackPreview track={selectedTrack} />
          </div>
        </>
      )}

      {(error || message) && (
        <p className="mt-3 text-xs text-muted whitespace-pre-line">{error ?? message}</p>
      )}
    </section>
  );
}

function TrackPreview({ track }: { track: TorcsTrack | null }) {
  return (
    <aside className="rounded-md border border-border bg-surface-2 p-3">
      <div className="text-[11px] font-mono uppercase tracking-[0.22em] text-muted">
        Track preview
      </div>
      {track?.preview_url ? (
        <img
          src={track.preview_url}
          alt={`${track.display_name} preview`}
          className="mt-3 aspect-[8/5] w-full rounded-md border border-border object-cover"
        />
      ) : track?.map_url ? (
        <img
          src={track.map_url}
          alt={`${track.display_name} map`}
          className="mt-3 aspect-[8/5] w-full rounded-md border border-border object-contain bg-black/30 p-4"
        />
      ) : (
        <div className="mt-3 flex aspect-[8/5] w-full items-center justify-center rounded-md border border-dashed border-border bg-bg/40 px-4 text-center text-xs text-muted">
          Track preview will appear here when TORCS exposes background or map assets for this circuit.
        </div>
      )}

      <div className="mt-3 space-y-2 text-sm">
        <div className="font-semibold text-text">{track?.display_name ?? "Standby"}</div>
        <p className="text-xs text-muted">
          {track?.description ?? "OVERRIDE uses TORCS track metadata and assets directly so operators can configure races here instead of inside the simulator menus."}
        </p>
        <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-xs text-muted">
          <MetaItem label="Category" value={track?.category ?? "road"} />
          <MetaItem label="Author" value={track?.author ?? "—"} />
          <MetaItem label="Length" value={formatMeasure(track?.length_m, "m")} />
          <MetaItem label="Width" value={formatMeasure(track?.width_m, "m")} />
          <MetaItem label="Pits" value={track?.pits != null ? String(track.pits) : "—"} />
          <MetaItem label="Map asset" value={track?.map_url ? "available" : "—"} />
        </dl>
      </div>
    </aside>
  );
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="font-mono uppercase tracking-wider">{label}</dt>
      <dd className="text-text">{value}</dd>
    </>
  );
}

function formatMeasure(value: number | null | undefined, unit: string): string {
  if (value == null) return "—";
  if (Number.isInteger(value)) return `${value} ${unit}`;
  return `${value.toFixed(1)} ${unit}`;
}

function ModeButton({
  active,
  label,
  description,
  onClick,
  disabled,
}: {
  active: boolean;
  label: string;
  description: string;
  onClick: () => void;
  disabled: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`flex-1 rounded-pill px-3 py-2 text-left transition-colors disabled:opacity-40 ${
        active ? "bg-accent text-bg" : "text-muted hover:text-text"
      }`}
    >
      <div className="text-sm font-medium">{label}</div>
      <div className={`text-[11px] ${active ? "text-bg/80" : "text-muted"}`}>{description}</div>
    </button>
  );
}

function ControlBadge({ labelText, tone }: { labelText: string; tone: string }) {
  return <span className={`text-xs ${tone}`}>{labelText}</span>;
}
