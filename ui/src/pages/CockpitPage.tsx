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
import { Link, Navigate } from "react-router-dom";

import { CockpitCommandStrip } from "@/components/cockpit/CockpitCommandStrip";
import { CockpitTimingRail } from "@/components/cockpit/CockpitTimingRail";
import { HybridEnergyRail } from "@/components/cockpit/HybridEnergyRail";
import { LapEnergyTimeline } from "@/components/cockpit/LapEnergyTimeline";
import { LiveStrategyInsight } from "@/components/cockpit/LiveStrategyInsight";
import { TorcsRaceFrame } from "@/components/cockpit/TorcsRaceFrame";
import { useLiveTelemetry } from "@/hooks/useLiveTelemetry";
import { useTorcsControl } from "@/hooks/useTorcsControl";
import { hasTorcsSurface } from "@/lib/env";

export function CockpitPage() {
  const torcsSurface = hasTorcsSurface();
  const {
    status,
    busy,
    error,
    stopRace,
  } = useTorcsControl();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (status?.session_id) setSessionId(status.session_id);
  }, [status?.session_id]);

  const { laps: liveLaps, latestLap, latestSnapshot, streamState } = useLiveTelemetry(sessionId, {
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

  const onStopRace = useCallback(async () => {
    try {
      const response = await stopRace();
      setNotice(
        response.status === "stopped"
          ? "Race stopped. OVERRIDE closed the simulator. Configure the next run from Upload or review the finished session debrief."
          : "No active race was running.",
      );
    } catch (_error) {
      setNotice(null);
    }
  }, [stopRace]);

  const viewMode = useMemo<"cockpit" | "headless">(() => {
    if (
      status?.launch_mode === "headless_quickrace" &&
      (status.state === "active" || status.state === "connecting" || status.state === "waiting_scr")
    ) {
      return "headless";
    }
    return "cockpit";
  }, [status?.launch_mode, status?.state]);

  const surfaceNotice = useMemo(
    () =>
      getSurfaceNotice({
        error,
        notice,
        status,
        sessionId,
        streamState: streamState.kind,
      }),
    [error, notice, status, sessionId, streamState.kind],
  );

  if (!torcsSurface) {
    return <Navigate to="/upload" replace />;
  }

  return (
    <div className="min-h-[calc(100vh-8rem)] space-y-4 px-4 pt-6 pb-6">
      <CockpitCommandStrip
        status={status}
        sessionId={sessionId}
        currentLap={latestLap?.lap ?? 0}
        onStopRace={onStopRace}
        onFullscreen={onFullscreen}
        busy={busy}
      />

      {surfaceNotice && (
        <section
          className={`rounded-card border px-4 py-4 ${
            surfaceNotice.tone === "warning"
              ? "border-warning/40 bg-warning/10"
              : surfaceNotice.tone === "accent"
                ? "border-accent/30 bg-accent/10"
                : "border-border bg-surface"
          }`}
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-1.5">
              <div className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted">
                {surfaceNotice.eyebrow}
              </div>
              <h2 className="text-base font-semibold text-text">{surfaceNotice.title}</h2>
              <p className="max-w-3xl text-sm text-muted">{surfaceNotice.body}</p>
            </div>
            {surfaceNotice.sessionLink && (
              <Link
                to={`/session/${encodeURIComponent(surfaceNotice.sessionLink)}`}
                className="inline-flex rounded-pill border border-border px-3 py-1.5 text-sm text-accent transition-colors hover:text-text"
              >
                Open session debrief
              </Link>
            )}
          </div>
        </section>
      )}

      <div className="grid gap-4 xl:grid-cols-[210px_minmax(0,1fr)_240px]">
        <div className="order-2 xl:order-1">
          <CockpitTimingRail
            latestSnapshot={latestSnapshot}
            latestLap={latestLap}
            streamState={streamState}
            targetLaps={status?.laps ?? 75}
            raceState={status?.state ?? null}
          />
        </div>

        <div className="order-1 xl:order-2">
          <TorcsRaceFrame
            viewMode={viewMode}
            status={status}
            streamState={streamState}
            latestSnapshot={latestSnapshot}
          />
        </div>

        <div className="order-3 xl:order-3">
          <HybridEnergyRail latestSnapshot={latestSnapshot} latestLap={latestLap} previousLap={previousLap} streamState={streamState} />
        </div>
      </div>

      <LapEnergyTimeline laps={liveLaps} />
      <LiveStrategyInsight
        sessionId={sessionId}
        latestSnapshot={latestSnapshot}
        latestLap={latestLap}
        previousLap={previousLap}
        streamState={streamState}
      />
    </div>
  );
}

interface SurfaceNoticeModel {
  eyebrow: string;
  title: string;
  body: string;
  tone: "neutral" | "accent" | "warning";
  sessionLink: string | null;
}

function getSurfaceNotice({
  error,
  notice,
  status,
  sessionId,
  streamState,
}: {
  error: string | null;
  notice: string | null;
  status: ReturnType<typeof useTorcsControl>["status"];
  sessionId: string | null;
  streamState: "idle" | "connecting" | "connected" | "no_telemetry" | "error" | "ended";
}): SurfaceNoticeModel | null {
  if (error) {
    return {
      eyebrow: "OVERRIDE attention",
      title: "The cockpit needs a quick operator check.",
      body: error,
      tone: "warning",
      sessionLink: null,
    };
  }

  if (notice) {
    return {
      eyebrow: "OVERRIDE update",
      title:
        streamState === "ended"
          ? "Race complete. The finished run is ready for review."
          : "The cockpit state changed successfully.",
      body: notice,
      tone: streamState === "ended" ? "accent" : "neutral",
      sessionLink: streamState === "ended" ? sessionId : null,
    };
  }

  if (status?.last_error) {
    return {
      eyebrow: "OVERRIDE attention",
      title: "TORCS reported an error on the last run.",
      body: status.last_error,
      tone: "warning",
      sessionLink: sessionId,
    };
  }

  if (status?.starting) {
    return {
      eyebrow: "OVERRIDE cockpit",
      title: "The branded simulator surface is warming up.",
      body: "Control services are still attaching. The TORCS display may already be visible below while OVERRIDE finishes bringing telemetry and race controls online.",
      tone: "neutral",
      sessionLink: null,
    };
  }

  if (status?.detail && !status.reachable) {
    return {
      eyebrow: "OVERRIDE attention",
      title: "TORCS is not reachable from the control plane yet.",
      body: status.detail,
      tone: "warning",
      sessionLink: null,
    };
  }

  if (streamState === "ended") {
    return {
      eyebrow: "OVERRIDE debrief ready",
      title: "Race complete. OVERRIDE closed the simulator for review.",
      body: "Use the finished session debrief for the full engineer readout, then configure the next run from Upload when you want a fresh comparison.",
      tone: "accent",
      sessionLink: sessionId,
    };
  }

  if (status?.state === "cleanup" || status?.state === "stopping") {
    return {
      eyebrow: "OVERRIDE reset",
      title: "OVERRIDE is closing the simulator.",
      body: "The stop sequence is finishing. TORCS will stay unavailable until the next run is launched from Upload.",
      tone: "neutral",
      sessionLink: sessionId,
    };
  }

  if (status?.state === "active" || status?.state === "connecting" || status?.state === "waiting_scr") {
    const headless = status.launch_mode === "headless_quickrace";
    return {
      eyebrow: headless ? "OVERRIDE live capture" : "OVERRIDE live cockpit",
      title:
        streamState === "connected"
          ? "Race live. OVERRIDE is tracking the run in real time."
          : "Race live. Waiting for the first closed lap to unlock richer guidance.",
      body:
        headless
          ? "The simulator is running without the 3D cockpit frame, but telemetry, timing, and hybrid energy tracking remain live below."
          : "Keep the TORCS Practice surface in view while OVERRIDE watches for the first closed lap, then upgrades the cockpit with stronger energy signals and debrief-ready context.",
      tone: "accent",
      sessionLink: null,
    };
  }

  if (status?.enabled && status?.reachable && status.state === "idle") {
    return {
      eyebrow: "OVERRIDE cockpit ready",
      title: "The simulator is closed and waiting for the next Upload-configured run.",
      body:
        sessionId != null
          ? "The previous session is still available for review. Configure the next run from Upload, or open the finished debrief to compare outcomes."
          : "Configure track, laps, and launch mode from Upload. OVERRIDE will return here automatically once the next run starts.",
      tone: "accent",
      sessionLink: sessionId,
    };
  }

  return null;
}
