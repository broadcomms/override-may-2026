import { useEffect, useMemo, useRef, useState } from "react";

import type { LiveLapSnapshot, TorcsControlStatus } from "@/api/types";
import type { LiveStreamState } from "@/hooks/useLiveTelemetry";
import { torcsNoVncUrl } from "@/lib/env";

type ViewMode = "cockpit" | "headless";

interface Props {
  viewMode: ViewMode;
  preRunIdle: boolean;
  status: TorcsControlStatus | null;
  streamState: LiveStreamState;
  latestSnapshot: LiveLapSnapshot | null;
}

export function TorcsRaceFrame({
  viewMode,
  preRunIdle,
  status,
  streamState,
  latestSnapshot,
}: Props) {
  const baseFrameUrl = torcsNoVncUrl();
  const [frameEpoch, setFrameEpoch] = useState(0);
  const prevReachableRef = useRef<boolean | null>(null);
  const prevStartingRef = useRef<boolean | null>(null);
  const prevStateRef = useRef<TorcsControlStatus["state"]>(null);
  const prevSessionIdRef = useRef<string | null>(null);

  useEffect(() => {
    const reachable = status?.reachable ?? false;
    const starting = status?.starting ?? false;
    const state = status?.state ?? null;
    const sessionId = status?.session_id ?? null;

    const wasReachable = prevReachableRef.current;
    const wasStarting = prevStartingRef.current;
    const wasState = prevStateRef.current;
    const wasSessionId = prevSessionIdRef.current;

    const recoveredFromRestart =
      (wasReachable === false && reachable === true) ||
      (wasStarting === true && starting === false && reachable) ||
      ((wasState === "cleanup" || wasState === "stopping") && state === "idle" && reachable);
    const switchedSessions =
      sessionId !== null &&
      wasSessionId !== null &&
      sessionId !== wasSessionId;
    const armedNewRun =
      wasState === "idle" &&
      (state === "launching" || state === "waiting_scr" || state === "connecting");

    if (recoveredFromRestart || switchedSessions || armedNewRun) {
      setFrameEpoch((value) => value + 1);
    }

    prevReachableRef.current = reachable;
    prevStartingRef.current = starting;
    prevStateRef.current = state;
    prevSessionIdRef.current = sessionId;
  }, [status?.reachable, status?.session_id, status?.starting, status?.state]);

  const frameUrl = useMemo(() => {
    if (!baseFrameUrl) return null;
    return `${baseFrameUrl}&reload=${frameEpoch}`;
  }, [baseFrameUrl, frameEpoch]);

  if (viewMode === "headless") {
    const active = status?.state === "active" || status?.state === "connecting";
    return (
      <section className="relative bg-black">
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
      <section className="relative bg-black">
        <div className="aspect-[8/5] w-full px-6 py-8 text-center">
          <div className="flex h-full flex-col items-center justify-center gap-3">
            <span className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted">
              TORCS surface unavailable
            </span>
            <p className="max-w-xl text-sm text-muted">
              The TORCS GUI surface is not configured for this host. Use Headless Capture or open the app from a deployment that exposes the TORCS noVNC surface.
            </p>
          </div>
        </div>
      </section>
    );
  }

  if (preRunIdle) {
    return (
      <section className="relative bg-black shadow-card">
        <div className="aspect-[8/5] w-full bg-black" />
      </section>
    );
  }

  return (
    <section className="relative  bg-black shadow-card">
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
        {/* Live telemetry overlay — keep this as the only in-frame badge so it
            stays away from TORCS-native HUD elements like the FPS/minimap in
            the top-right corner. */}
        {latestSnapshot && streamState.kind !== "ended" && (
          <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex justify-center p-3">
            <div className="max-w-md rounded-md border border-border/80 bg-bg/85 px-3 py-2 text-center text-xs text-muted backdrop-blur-sm">
              {`Live telemetry - Sector ${latestSnapshot.sector ?? "—"}, Lap ${latestSnapshot.lap}, ${latestSnapshot.lap_progress_pct.toFixed(0)}% complete.`}
            </div>
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
    </section>
  );
}
