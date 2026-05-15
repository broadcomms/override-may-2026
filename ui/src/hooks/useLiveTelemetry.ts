import { useEffect, useState } from "react";

import { api } from "@/api/client";
import type { LiveLapStats, LiveStreamEvent } from "@/api/types";

export type LiveStreamState =
  | { kind: "idle" }
  | { kind: "connecting" }
  | { kind: "connected"; status: string }
  | { kind: "no_telemetry"; message: string }
  | { kind: "error" }
  | { kind: "ended"; reason: string };

interface UseLiveTelemetryOptions {
  onRaceEnded?: () => void;
  /**
   * Cockpit starts the stream immediately after Start race. The stub Session is
   * written before the JSONL may exist on disk, so the API can briefly emit
   * no_telemetry and close. Retry in that mode instead of requiring a page
   * refresh to attach after the writer creates the file.
   */
  retryNoTelemetry?: boolean;
  retryDelayMs?: number;
}

export function useLiveTelemetry(
  sessionId: string | null | undefined,
  {
    onRaceEnded,
    retryNoTelemetry = false,
    retryDelayMs = 1500,
  }: UseLiveTelemetryOptions = {},
) {
  const [laps, setLaps] = useState<LiveLapStats[]>([]);
  const [streamState, setStreamState] = useState<LiveStreamState>({ kind: "idle" });
  const [raceEnded, setRaceEnded] = useState(false);

  useEffect(() => {
    if (!sessionId) {
      setLaps([]);
      setStreamState({ kind: "idle" });
      setRaceEnded(false);
      return;
    }

    setLaps([]);
    setStreamState({ kind: "connecting" });
    setRaceEnded(false);

    let retryTimer: number | null = null;
    let teardown: (() => void) | null = null;
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      teardown?.();
      teardown = api.streamSession(sessionId, handle, {
        onError: () => setStreamState({ kind: "error" }),
      });
    };

    const scheduleRetry = () => {
      if (!retryNoTelemetry || cancelled) return;
      if (retryTimer !== null) window.clearTimeout(retryTimer);
      retryTimer = window.setTimeout(() => {
        retryTimer = null;
        if (!cancelled) {
          setStreamState({ kind: "connecting" });
          connect();
        }
      }, retryDelayMs);
    };

    const handle = (ev: LiveStreamEvent) => {
      switch (ev.event) {
        case "connected":
          setStreamState({ kind: "connected", status: ev.status });
          break;
        case "lap":
          setLaps((prev) => {
            const existing = prev.findIndex((lap) => lap.lap === ev.lap);
            const stats: LiveLapStats = {
              lap: ev.lap,
              lap_time_s: ev.lap_time_s,
              avg_speed_kmh: ev.avg_speed_kmh,
              max_speed_kmh: ev.max_speed_kmh,
              harvest_mj: ev.harvest_mj,
              deploy_mj: ev.deploy_mj,
              soc_end: ev.soc_end,
              fuel_used_kg: ev.fuel_used_kg,
            };
            if (existing >= 0) {
              const next = prev.slice();
              next[existing] = stats;
              return next;
            }
            return [...prev, stats];
          });
          break;
        case "no_telemetry":
          setStreamState({ kind: "no_telemetry", message: ev.message });
          scheduleRetry();
          break;
        case "race_ended":
          setRaceEnded(true);
          setStreamState({ kind: "ended", reason: ev.reason ?? "completed" });
          onRaceEnded?.();
          break;
      }
    };

    connect();

    return () => {
      cancelled = true;
      if (retryTimer !== null) window.clearTimeout(retryTimer);
      teardown?.();
    };
  }, [onRaceEnded, retryDelayMs, retryNoTelemetry, sessionId]);

  return {
    laps,
    streamState,
    latestLap: laps.length > 0 ? laps[laps.length - 1] : null,
    raceEnded,
  };
}
