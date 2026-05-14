/**
 * CockpitPage — full-bleed noVNC surface (Phase B brief B1).
 *
 * Single-purpose: page-title chrome + status pill + Back link +
 * Fullscreen button + the 16:9 noVNC iframe. No other content per
 * audit spec.
 *
 * The wrapper-clip hack at the iframe block is verbatim from the
 * previous TorcsControlPanel.tsx — audit §20 don't #5 explicitly
 * preserves it. Don't rewrite that block; the negative top offset +
 * grown height + overflow-hidden combination is what hides the
 * vnc_lite.html status bar across the SOP boundary.
 *
 * isLocalHost guard: anyone hitting /cockpit on the hosted demo is
 * redirected to /upload — the noVNC URL is `localhost:6080`, which
 * doesn't make sense off-host.
 */

import { useCallback, useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";

import { api } from "@/api/client";
import type { TorcsControlStatus, TorcsRaceState } from "@/api/types";
import { isLocalHost } from "@/lib/env";

const POLL_INTERVAL_MS = 3000;

function labelForState(state: TorcsRaceState | null): { label: string; tone: string } {
  switch (state) {
    case "launching":
      return { label: "Launching…", tone: "text-warning" };
    case "waiting_scr":
      return { label: "Waiting for simulator…", tone: "text-warning" };
    case "connecting":
      return { label: "Connecting client…", tone: "text-warning" };
    case "active":
      return { label: "Live", tone: "text-accent" };
    case "stopping":
      return { label: "Stopping…", tone: "text-muted" };
    case "cleanup":
      return { label: "Cleaning up…", tone: "text-muted" };
    case "idle":
    case null:
      return { label: "Idle", tone: "text-muted" };
  }
}

export function CockpitPage() {
  const [status, setStatus] = useState<TorcsControlStatus | null>(null);

  const refresh = useCallback(async () => {
    try {
      const s = await api.torcsControlStatus();
      setStatus(s);
    } catch (_e) {
      // 200-always endpoint; thrown error means backend down — keep last state
    }
  }, []);

  useEffect(() => {
    if (!isLocalHost()) return;
    refresh();
    const id = window.setInterval(refresh, POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [refresh]);

  // Hosted demo: noVNC isn't reachable off-host; redirect home.
  if (!isLocalHost()) {
    return <Navigate to="/upload" replace />;
  }

  const onFullscreen = () => {
    const el = document.getElementById("torcs-iframe");
    if (el && el.requestFullscreen) el.requestFullscreen();
  };

  const badge = labelForState(status?.state ?? (status?.active ? "active" : "idle"));

  return (
    <div className="min-h-[calc(100vh-8rem)] flex flex-col">
      {/* Page-title chrome + status pill + actions */}
      <div className="px-4 py-2 border-b border-border flex items-center gap-3 text-sm">
        <Link
          to="/upload"
          className="text-muted hover:text-accent transition-colors"
        >
          ← Back to OVERRIDE
        </Link>
        <span className="text-[11px] uppercase tracking-wider font-mono text-muted">
          Cockpit
        </span>
        <span className={`text-xs ${badge.tone}`}>● {badge.label}</span>
        <button
          type="button"
          onClick={onFullscreen}
          className="ml-auto text-[11px] text-muted hover:text-accent transition-colors"
          title="Open the noVNC iframe in browser fullscreen for readable HUD text"
        >
          Fullscreen ⤢
        </button>
      </div>

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
    </div>
  );
}
