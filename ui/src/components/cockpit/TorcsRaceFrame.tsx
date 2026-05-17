import { useEffect, useMemo, useRef, useState } from "react";

import type { LiveLapSnapshot, TorcsControlStatus } from "@/api/types";
import type { LiveStreamState } from "@/hooks/useLiveTelemetry";
import { torcsNoVncUrl } from "@/lib/env";

type ViewMode = "cockpit" | "headless";

interface Props {
  viewMode: ViewMode;
  status: TorcsControlStatus | null;
  streamState: LiveStreamState;
  latestSnapshot: LiveLapSnapshot | null;
}

export function TorcsRaceFrame({
  viewMode,
  status,
  streamState,
  latestSnapshot,
}: Props) {
  const baseFrameUrl = torcsNoVncUrl();
  const [frameEpoch, setFrameEpoch] = useState(0);
  const prevReachableRef = useRef<boolean | null>(null);
  const prevStartingRef = useRef<boolean | null>(null);
  const prevStateRef = useRef<TorcsControlStatus["state"]>(null);

  useEffect(() => {
    const reachable = status?.reachable ?? false;
    const starting = status?.starting ?? false;
    const state = status?.state ?? null;

    const wasReachable = prevReachableRef.current;
    const wasStarting = prevStartingRef.current;
    const wasState = prevStateRef.current;

    const recoveredFromRestart =
      (wasReachable === false && reachable === true) ||
      (wasStarting === true && starting === false && reachable) ||
      ((wasState === "cleanup" || wasState === "stopping") && state === "idle" && reachable);

    if (recoveredFromRestart) {
      setFrameEpoch((value) => value + 1);
    }

    prevReachableRef.current = reachable;
    prevStartingRef.current = starting;
    prevStateRef.current = state;
  }, [status?.reachable, status?.starting, status?.state]);

  const frameUrl = useMemo(() => {
    if (!baseFrameUrl) return null;
    return `${baseFrameUrl}&reload=${frameEpoch}`;
  }, [baseFrameUrl, frameEpoch]);
  const surfaceBadge = getSurfaceBadge(viewMode, status, streamState);

  if (viewMode === "headless") {
    const active = status?.state === "active" || status?.state === "connecting";
    return (
      <section className="relative rounded-card border border-border bg-black">
        <div className="aspect-[8/5] w-full px-6 py-8 text-center">
          <div className="flex h-full flex-col items-center justify-center gap-3">
            <span className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted">
              Headless capture
            </span>
            <div className="text-2xl font-semibold text-text">
              {active ? "Headless telemetry capture active" : "Headless capture armed"}
            </div>
            <p className="max-w-xl text-sm text-muted">
              {active
                ? "TORCS visual display is disabled for this run. Live timing and hybrid energy data will continue streaming below."
                : "TORCS visual display is disabled in this mode. Start race when you want telemetry without the 3D cockpit frame."}
            </p>
          </div>
        </div>
      </section>
    );
  }

  if (!frameUrl) {
    return (
      <section className="relative rounded-card border border-border bg-black">
        <div className="aspect-[8/5] w-full px-6 py-8 text-center">
          <div className="flex h-full flex-col items-center justify-center gap-3">
            <span className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted">
              3D cockpit unavailable
            </span>
            <p className="max-w-xl text-sm text-muted">
              The TORCS display origin is not configured for this host. Use Headless Capture or open the app from a deployment that exposes the TORCS noVNC surface.
            </p>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="relative rounded-card border border-border bg-black shadow-card">
      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-start justify-between gap-3 p-3">
        <div
          className={`ml-auto rounded-md border px-3 py-1.5 font-mono text-[11px] uppercase tracking-[0.2em] backdrop-blur-sm ${
            surfaceBadge.tone === "accent"
              ? "border-accent/40 bg-accent/12 text-accent"
              : surfaceBadge.tone === "warning"
                ? "border-warning/40 bg-warning/12 text-warning"
                : "border-border/80 bg-bg/82 text-muted"
          }`}
        >
          {surfaceBadge.label}
        </div>
      </div>

      {/* Phase 2.7 v7 — wrapper-clip pattern.
          vnc_lite.html hardcodes a status bar at the top of <body> that we
          cannot hide via URL params (different origin → SOP). We clip it by
          giving the outer wrapper `aspect-[8/5]` (matches Xvfb 16:10) and
          `overflow-hidden`, then overscanning the iframe with a slightly
          top-heavy crop. That hides the noVNC status bar and the TORCS/XFCE
          top seam without reintroducing the lower grey strip. */}
      <div className="relative w-full aspect-[8/5] overflow-hidden bg-black">
        {/* SCR-wait overlay: noVNC is black while TORCS X11 is still initialising.
            Sits above the iframe (z-20) so it covers the blank frame during the
            launching → waiting_scr window. Clears automatically once the state
            advances to connecting/active/stopping/cleanup/idle. */}
        {(status?.state === "launching" || status?.state === "waiting_scr") && (
          <div className="pointer-events-none absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 bg-black/90">
            <span className="font-mono text-[10px] uppercase tracking-[0.28em] text-muted">
              {status.state === "launching" ? "Launching simulator" : "Waiting for SCR port"}
            </span>
            <div className="h-px w-16 animate-pulse bg-accent/50" />
            <p className="max-w-xs text-center text-xs text-muted/70">
              {status.state === "launching"
                ? "TORCS is starting. The display will appear once the simulator initialises."
                : "TORCS is running. Waiting for the SCR race server port to open before connecting the AI driver."}
            </p>
          </div>
        )}
        <iframe
          key={frameUrl}
          id="torcs-iframe"
          title="TORCS in noVNC"
          src={frameUrl}
          className="absolute inset-x-0 w-full border-0"
          style={{ top: "-60px", height: "calc(100% + 96px)" }}
        />
      </div>

      {/* Live-sector overlay — only shown during an open lap so it never
          competes with the TORCS on-screen menus at race end. */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 flex justify-start p-3">
        {latestSnapshot && streamState.kind !== "ended" && (
          <div className="max-w-sm rounded-md border border-border/80 bg-bg/85 px-3 py-2 text-xs text-muted backdrop-blur-sm">
            {`Live telemetry — Sector ${latestSnapshot.sector ?? "—"}, Lap ${latestSnapshot.lap}, ${latestSnapshot.lap_progress_pct.toFixed(0)}% complete.`}
          </div>
        )}
      </div>
    </section>
  );
}

function getSurfaceBadge(
  viewMode: ViewMode,
  status: TorcsControlStatus | null,
  streamState: LiveStreamState,
): {
  label: string;
  tone: "neutral" | "accent" | "warning";
} {
  if (viewMode === "headless") {
    return {
      label: status?.state === "active" ? "Headless live" : "Headless standby",
      tone: status?.state === "active" ? "accent" : "neutral",
    };
  }

  if (streamState.kind === "ended") {
    return { label: "Debrief ready", tone: "accent" };
  }

  if (streamState.kind === "connected" || status?.state === "active") {
    return { label: "Live race", tone: "accent" };
  }

  if (status?.last_error || streamState.kind === "error") {
    return { label: "Needs review", tone: "warning" };
  }

  if (status?.starting || status?.state === "launching" || status?.state === "waiting_scr") {
    return { label: "Staging run", tone: "neutral" };
  }

  if (status?.state === "stopping" || status?.state === "cleanup") {
    return { label: "Resetting", tone: "neutral" };
  }

  return { label: "Standby", tone: "neutral" };
}
