import type { LiveLapStats, TorcsControlStatus } from "@/api/types";
import type { LiveStreamState } from "@/hooks/useLiveTelemetry";

type ViewMode = "cockpit" | "headless";

interface Props {
  viewMode: ViewMode;
  status: TorcsControlStatus | null;
  streamState: LiveStreamState;
  latestLap: LiveLapStats | null;
}

export function TorcsRaceFrame({
  viewMode,
  status,
  streamState,
  latestLap,
}: Props) {
  if (viewMode === "headless") {
    const active = status?.state === "active" || status?.state === "connecting";
    return (
      <section className="relative rounded-card border border-border bg-black">
        <div className="aspect-video w-full px-6 py-8 text-center">
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

  const overlay = frameOverlay(streamState, latestLap);

  return (
    <section className="relative rounded-card border border-border bg-black shadow-card">
      {/* Phase 2.7 v4 — wrapper-clip pattern. Preserved verbatim from the
          previous TorcsControlPanel (audit §20 don't #5). Two problems v3
          left open:
            1. vnc_lite.html hardcodes a "Connected (unencrypted) to <host>"
               status bar + Send CtrlAltDel button at the top of <body>.
               No URL param hides it — that's the entire UI surface of
               vnc_lite. The iframe is :6080 and the parent is :8000 →
               different origin → SOP blocks us from injecting CSS into
               the iframe contentDocument.
            2. ?scale=true preserves the Xvfb 16:9 aspect ratio. With a
               fixed-height iframe at a narrow layout column, the canvas
               fits-to-width and ends up letterboxed top+bot by ~210px each.
          Both fixed by clipping at the outer wrapper:
            - aspect-video on the wrapper = 16:9 box that matches Xvfb,
              so no letterboxing math goes wrong.
            - overflow-hidden hides anything outside.
            - iframe is absolutely positioned, pulled up 36px and grown
              taller by the same amount; the status bar slides off the
              top of the clip region. Bottom is unchanged.
          Fullscreen button still works (requestFullscreen on the iframe
          element fills the screen; the negative top offset becomes
          irrelevant and the bar reappears, which is fine — fullscreen is
          a "read the HUD now" escape hatch, not the primary display). */}
      <div className="relative w-full aspect-video overflow-hidden bg-black">
        <iframe
          id="torcs-iframe"
          title="TORCS in noVNC"
          src="http://localhost:6080/vnc_lite.html?autoconnect=1&password=&reconnect=1&scale=true"
          className="absolute inset-x-0 w-full border-0"
          style={{ top: "-36px", height: "calc(100% + 36px)" }}
        />
      </div>

      <div className="pointer-events-none absolute inset-x-0 bottom-0 flex justify-start p-3">
        <div className="max-w-sm rounded-md border border-border/80 bg-bg/85 px-3 py-2 text-xs text-muted backdrop-blur-sm">
          {overlay}
        </div>
      </div>
    </section>
  );
}

function frameOverlay(streamState: LiveStreamState, latestLap: LiveLapStats | null): string {
  switch (streamState.kind) {
    case "idle":
      return "Race frame ready. Start a 3D cockpit run to attach live timing and energy signals.";
    case "connecting":
      return latestLap
        ? `Waiting for the next lap event. Last completed lap: L${latestLap.lap}.`
        : "Connected to the cockpit session. Waiting for the first completed lap.";
    case "connected":
      return latestLap
        ? `Live telemetry attached. Latest completed lap: L${latestLap.lap}.`
        : "Telemetry stream connected. Lap-level data will appear after the first completed lap.";
    case "no_telemetry":
      return streamState.message;
    case "error":
      return "Telemetry stream interrupted. The cockpit will keep polling control status while the stream reconnects.";
    case "ended":
      return "Race ended. Post-lap analysis is available in the session debrief.";
  }
}
