import { Link } from "react-router-dom";

import type { TorcsControlStatus } from "@/api/types";
import { truncateSessionId } from "@/lib/cockpitTelemetry";
import { isTorcsActiveState, labelForTorcsState } from "@/hooks/useTorcsControl";

interface Props {
  status: TorcsControlStatus | null;
  sessionId: string | null;
  currentLap: number;
  onStopRace: () => void;
  onRecover: () => void;
  onFullscreen: () => void;
  busy: boolean;
}

export function CockpitCommandStrip({
  status,
  sessionId,
  currentLap,
  onStopRace,
  onRecover,
  onFullscreen,
  busy,
}: Props) {
  const badge = labelForTorcsState(status?.state ?? (status?.active ? "active" : "idle"));
  const stopEnabled = !busy && isTorcsActiveState(status?.state ?? null);
  const recoverEnabled = !busy && Boolean(status?.enabled && status?.reachable);
  const targetLaps = status?.laps ?? 75;
  const lapLabel =
    currentLap > 0 ? `L${currentLap} closed / ${targetLaps}` : `0 closed / ${targetLaps}`;
  const modeLabel =
    status?.launch_mode === "headless_quickrace" ? "Headless quickrace" : "Cockpit practice";

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
        <MetaPill label="Closed lap" value={lapLabel} />
        <MetaPill label="Track" value={status?.track ?? "aalborg"} />
        <MetaPill label="Mode" value={modeLabel} />
        <button
          type="button"
          onClick={onFullscreen}
          className="ml-auto inline-flex items-center rounded-pill border border-border px-3 py-1 text-xs text-muted transition-colors hover:text-accent"
        >
          Fullscreen
        </button>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={onStopRace}
          disabled={!stopEnabled}
          className="rounded-pill border border-border bg-surface-2 px-4 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-40"
        >
          Stop race
        </button>
        <button
          type="button"
          onClick={onRecover}
          disabled={!recoverEnabled}
          className="rounded-pill border border-border bg-surface px-4 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-40"
        >
          Reset simulator
        </button>
        <Link
          to="/upload"
          className="rounded-pill border border-border bg-surface px-4 py-2 text-sm text-muted transition-colors hover:text-text"
        >
          Configure next run
        </Link>
      </div>
    </section>
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
      className="inline-flex items-center gap-1 rounded-pill border border-border px-2.5 py-1 font-mono text-[11px] uppercase tracking-[0.18em] text-muted"
    >
      <span>{label}</span>
      <span className="text-text normal-case tracking-normal font-sans text-sm">{value}</span>
    </span>
  );
}

function StatePill({ label, tone }: { label: string; tone: string }) {
  return (
    <span className={`inline-flex rounded-pill border border-border px-2.5 py-1 text-xs ${tone}`}>
      {label}
    </span>
  );
}
