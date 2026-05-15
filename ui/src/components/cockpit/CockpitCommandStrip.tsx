import { Link } from "react-router-dom";

import type { TorcsControlStatus } from "@/api/types";
import { truncateSessionId } from "@/lib/cockpitTelemetry";
import {
  groupTorcsTracks,
  isTorcsActiveState,
  labelForTorcsState,
} from "@/hooks/useTorcsControl";

type ViewMode = "cockpit" | "headless";

interface Props {
  status: TorcsControlStatus | null;
  sessionId: string | null;
  currentLap: number;
  targetLaps: number;
  track: string;
  onTrackChange: (value: string) => void;
  laps: number;
  onLapsChange: (value: number) => void;
  tracks: Array<{ name: string; category: "road" | "oval" | "dirt" }>;
  viewMode: ViewMode;
  onViewModeChange: (value: ViewMode) => void;
  onStartRace: () => void;
  onStopRace: () => void;
  onFullscreen: () => void;
  busy: boolean;
}

export function CockpitCommandStrip({
  status,
  sessionId,
  currentLap,
  targetLaps,
  track,
  onTrackChange,
  laps,
  onLapsChange,
  tracks,
  viewMode,
  onViewModeChange,
  onStartRace,
  onStopRace,
  onFullscreen,
  busy,
}: Props) {
  const badge = labelForTorcsState(status?.state ?? (status?.active ? "active" : "idle"));
  const startDisabled = busy || (status?.state !== null && status?.state !== "idle");
  const stopEnabled = !busy && isTorcsActiveState(status?.state ?? null);
  const groupedTracks = groupTorcsTracks(tracks);
  const lapLabel = currentLap > 0 ? `Lap ${currentLap}/${targetLaps}` : `Lap 0/${targetLaps}`;

  return (
    <section className="rounded-card border border-border bg-surface px-4 py-3">
      <div className="flex flex-wrap items-center gap-2 text-xs md:text-sm">
        <Link
          to="/upload"
          className="inline-flex items-center rounded-pill border border-border px-2.5 py-1 text-muted transition-colors hover:text-accent"
        >
          Back
        </Link>
        <span className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted">
          Cockpit
        </span>
        <StatePill label={badge.label} tone={badge.tone} />
        <MetaPill
          label="Session"
          value={sessionId ? truncateSessionId(sessionId) : "standby"}
          title={sessionId ?? "No active session yet"}
        />
        <MetaPill label="Lap" value={lapLabel} />
        <MetaPill label="Mode" value="2026 Hybrid Energy" />
        <button
          type="button"
          onClick={onFullscreen}
          className="ml-auto inline-flex items-center rounded-pill border border-border px-3 py-1 text-xs text-muted transition-colors hover:text-accent"
        >
          Fullscreen
        </button>
      </div>

      <div className="mt-3 hidden grid-cols-1 gap-3 lg:grid lg:grid-cols-[minmax(0,1fr)_auto_auto] lg:items-end">
        <DesktopSetup
          track={track}
          onTrackChange={onTrackChange}
          laps={laps}
          onLapsChange={onLapsChange}
          groupedTracks={groupedTracks}
          viewMode={viewMode}
          onViewModeChange={onViewModeChange}
          startDisabled={startDisabled}
        />
        <button
          type="button"
          onClick={onStartRace}
          disabled={startDisabled}
          className="h-10 rounded-pill bg-accent px-4 text-sm font-medium text-bg disabled:cursor-not-allowed disabled:opacity-40"
        >
          Start race
        </button>
        <button
          type="button"
          onClick={onStopRace}
          disabled={!stopEnabled}
          className="h-10 rounded-pill border border-border bg-surface-2 px-4 text-sm disabled:cursor-not-allowed disabled:opacity-40"
        >
          Stop race
        </button>
      </div>

      <details className="mt-3 lg:hidden">
        <summary className="cursor-pointer list-none rounded-md border border-border bg-surface-2 px-3 py-2 text-xs uppercase tracking-wider text-muted">
          Race setup
        </summary>
        <div className="mt-3 space-y-3">
          <DesktopSetup
            track={track}
            onTrackChange={onTrackChange}
            laps={laps}
            onLapsChange={onLapsChange}
            groupedTracks={groupedTracks}
            viewMode={viewMode}
            onViewModeChange={onViewModeChange}
            startDisabled={startDisabled}
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onStartRace}
              disabled={startDisabled}
              className="flex-1 rounded-pill bg-accent px-4 py-2 text-sm font-medium text-bg disabled:cursor-not-allowed disabled:opacity-40"
            >
              Start race
            </button>
            <button
              type="button"
              onClick={onStopRace}
              disabled={!stopEnabled}
              className="flex-1 rounded-pill border border-border bg-surface-2 px-4 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-40"
            >
              Stop race
            </button>
          </div>
        </div>
      </details>
    </section>
  );
}

function DesktopSetup({
  track,
  onTrackChange,
  laps,
  onLapsChange,
  groupedTracks,
  viewMode,
  onViewModeChange,
  startDisabled,
}: {
  track: string;
  onTrackChange: (value: string) => void;
  laps: number;
  onLapsChange: (value: number) => void;
  groupedTracks: ReturnType<typeof groupTorcsTracks>;
  viewMode: ViewMode;
  onViewModeChange: (value: ViewMode) => void;
  startDisabled: boolean;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      <label className="flex flex-col gap-1">
        <span className="text-[10px] font-mono uppercase tracking-wider text-muted">
          Track
        </span>
        <select
          value={track}
          onChange={(e) => onTrackChange(e.target.value)}
          disabled={startDisabled}
          className="h-10 rounded-md border border-border bg-surface px-3 font-mono text-sm disabled:opacity-50"
        >
          {groupedTracks.recommended.length > 0 && (
            <optgroup label="Recommended">
              {groupedTracks.recommended.map((item) => (
                <option key={item.name} value={item.name}>
                  {item.name}
                </option>
              ))}
            </optgroup>
          )}
          {Object.entries(groupedTracks.others).map(([category, items]) => (
            <optgroup key={category} label={category}>
              {items.map((item) => (
                <option key={item.name} value={item.name}>
                  {item.name}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1">
        <span className="text-[10px] font-mono uppercase tracking-wider text-muted">
          Target laps
        </span>
        <input
          type="number"
          min={1}
          max={200}
          value={laps}
          onChange={(e) =>
            onLapsChange(Math.max(1, Math.min(200, parseInt(e.target.value, 10) || 1)))
          }
          disabled={startDisabled}
          className="h-10 rounded-md border border-border bg-surface px-3 font-mono text-sm disabled:opacity-50"
        />
      </label>

      <div className="flex flex-col gap-1">
        <span className="text-[10px] font-mono uppercase tracking-wider text-muted">
          View mode
        </span>
        <div className="inline-flex h-10 rounded-pill border border-border bg-surface p-0.5 text-sm">
          <ViewModeButton
            active={viewMode === "cockpit"}
            label="3D Cockpit"
            onClick={() => onViewModeChange("cockpit")}
            disabled={startDisabled}
          />
          <ViewModeButton
            active={viewMode === "headless"}
            label="Headless Capture"
            onClick={() => onViewModeChange("headless")}
            disabled={startDisabled}
          />
        </div>
      </div>
    </div>
  );
}

function ViewModeButton({
  active,
  label,
  onClick,
  disabled,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
  disabled: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`flex-1 rounded-pill px-3 transition-colors disabled:opacity-50 ${
        active ? "bg-accent text-bg" : "text-muted hover:text-text"
      }`}
    >
      {label}
    </button>
  );
}

function StatePill({ label, tone }: { label: string; tone: string }) {
  return (
    <span className={`inline-flex items-center rounded-pill border border-border px-2 py-1 text-xs ${tone}`}>
      {label}
    </span>
  );
}

function MetaPill({
  label,
  value,
  title,
}: {
  label: string;
  value: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className="inline-flex items-center gap-1 rounded-pill border border-border px-2 py-1 font-mono text-[11px] uppercase tracking-wide text-muted"
    >
      <span className="text-text/60">{label}</span>
      <span className="normal-case tracking-normal text-text">{value}</span>
    </span>
  );
}
