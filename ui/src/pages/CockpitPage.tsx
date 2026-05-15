/**
 * CockpitPage — live race-intelligence surface around the noVNC TORCS view.
 *
 * The cockpit stays self-contained: race start/stop, lap telemetry, live
 * hybrid-energy signals, and the AI guidance slot all live here so operators
 * don't have to bounce back to /upload mid-demo.
 *
 * The iframe wrapper-clip hack is preserved verbatim inside TorcsRaceFrame.
 * isLocalHost guard still redirects hosted-demo traffic away from localhost noVNC.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Navigate } from "react-router-dom";

import { CockpitCommandStrip } from "@/components/cockpit/CockpitCommandStrip";
import { CockpitTimingRail } from "@/components/cockpit/CockpitTimingRail";
import { HybridEnergyRail } from "@/components/cockpit/HybridEnergyRail";
import { LapEnergyTimeline } from "@/components/cockpit/LapEnergyTimeline";
import { LiveStrategyInsight } from "@/components/cockpit/LiveStrategyInsight";
import { TorcsRaceFrame } from "@/components/cockpit/TorcsRaceFrame";
import { useLiveTelemetry } from "@/hooks/useLiveTelemetry";
import { useTorcsControl } from "@/hooks/useTorcsControl";
import { isLocalHost } from "@/lib/env";

export function CockpitPage() {
  const localHost = isLocalHost();
  const {
    status,
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
  const [viewMode, setViewMode] = useState<"cockpit" | "headless">("cockpit");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (status?.session_id) setSessionId(status.session_id);
  }, [status?.session_id]);

  const { laps: liveLaps, latestLap, streamState } = useLiveTelemetry(sessionId, {
    retryNoTelemetry: true,
  });
  const previousLap = useMemo(
    () => (liveLaps.length > 1 ? liveLaps[liveLaps.length - 2] : null),
    [liveLaps],
  );

  const onFullscreen = () => {
    const el = document.getElementById("torcs-iframe");
    if (el && el.requestFullscreen) el.requestFullscreen();
  };

  const onStartRace = useCallback(async () => {
    try {
      const response = await startRace({ autoLaunchTorcs: viewMode === "headless" });
      setSessionId(response.session_id);
      setNotice(
        viewMode === "headless"
          ? `Headless capture started on ${response.track} for ${response.laps} laps. Live timing and hybrid energy data will stream as laps complete.`
          : `3D cockpit capture started on ${response.track} for ${response.laps} laps. Live timing will attach as soon as the first lap closes.`,
      );
    } catch (_error) {
      setNotice(null);
    }
  }, [startRace, viewMode]);

  const onStopRace = useCallback(async () => {
    try {
      const response = await stopRace();
      setNotice(
        response.status === "stopped"
          ? "Race stopped. The completed session remains available for post-lap analysis."
          : "No active race was running.",
      );
    } catch (_error) {
      setNotice(null);
    }
  }, [stopRace]);

  const operationalNote =
    error ??
    notice ??
    status?.last_error ??
    status?.detail ??
    (viewMode === "cockpit" &&
    status?.enabled &&
    status?.reachable &&
    status.state === "idle"
      ? "3D Cockpit mode expects the local TORCS visual stack to be open. Use Headless Capture when you want telemetry without the noVNC race display."
      : null);

  // Hosted demo: noVNC isn't reachable off-host; redirect home.
  if (!localHost) {
    return <Navigate to="/upload" replace />;
  }

  return (
    <div className="min-h-[calc(100vh-8rem)] space-y-4 px-4 pb-6">
      <CockpitCommandStrip
        status={status}
        sessionId={sessionId}
        currentLap={latestLap?.lap ?? 0}
        targetLaps={laps}
        track={track}
        onTrackChange={setTrack}
        laps={laps}
        onLapsChange={setLaps}
        tracks={tracks}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        onStartRace={onStartRace}
        onStopRace={onStopRace}
        onFullscreen={onFullscreen}
        busy={busy}
      />

      {operationalNote && (
        <div className="rounded-card border border-border bg-surface px-4 py-3 text-sm text-muted">
          {operationalNote}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[210px_minmax(0,1fr)_240px]">
        <div className="order-2 xl:order-1">
          <CockpitTimingRail
            latestLap={latestLap}
            streamState={streamState}
            targetLaps={laps}
            raceState={status?.state ?? null}
          />
        </div>

        <div className="order-1 xl:order-2">
          <TorcsRaceFrame
            viewMode={viewMode}
            status={status}
            streamState={streamState}
            latestLap={latestLap}
          />
        </div>

        <div className="order-3 xl:order-3">
          <HybridEnergyRail latestLap={latestLap} previousLap={previousLap} />
        </div>
      </div>

      <LapEnergyTimeline laps={liveLaps} />
      <LiveStrategyInsight
        sessionId={sessionId}
        latestLap={latestLap}
        previousLap={previousLap}
        streamState={streamState}
      />
    </div>
  );
}
