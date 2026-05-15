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
}

export function useLiveTelemetry(
  sessionId: string | null | undefined,
  { onRaceEnded }: UseLiveTelemetryOptions = {},
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
          break;
        case "race_ended":
          setRaceEnded(true);
          setStreamState({ kind: "ended", reason: ev.reason ?? "completed" });
          onRaceEnded?.();
          break;
      }
    };

    const teardown = api.streamSession(sessionId, handle, {
      onError: () => setStreamState({ kind: "error" }),
    });

    return teardown;
  }, [onRaceEnded, sessionId]);

  return {
    laps,
    streamState,
    latestLap: laps.length > 0 ? laps[laps.length - 1] : null,
    raceEnded,
  };
}
