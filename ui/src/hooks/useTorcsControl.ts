import { useCallback, useEffect, useMemo, useState } from "react";

import { OverrideApiError, api } from "@/api/client";
import type {
  TorcsControlStatus,
  TorcsDriverProfileSummary,
  TorcsLaunchMode,
  TorcsRaceState,
  TorcsRecoverResponse,
  TorcsStartRaceResponse,
  TorcsStopRaceResponse,
  TorcsTrack,
} from "@/api/types";
import { hasTorcsSurface } from "@/lib/env";

const POLL_INTERVAL_MS = 3000;

export const RECOMMENDED_TRACKS = [
  "aalborg",
  "alpine-1",
  "e-track-3",
  "forza",
  "ruudskogen",
  "wheel-1",
];

export const FALLBACK_TRACKS: TorcsTrack[] = RECOMMENDED_TRACKS.map((name) => ({
  name,
  category: "road",
  display_name: name.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
}));

export function labelForTorcsState(
  state: TorcsRaceState | null,
): { label: string; tone: string } {
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

export function isTorcsActiveState(state: TorcsRaceState | null): boolean {
  return (
    state === "active" ||
    state === "launching" ||
    state === "waiting_scr" ||
    state === "connecting"
  );
}

function sortedTracks(tracks: TorcsTrack[]): TorcsTrack[] {
  const recSet = new Set(RECOMMENDED_TRACKS);
  const rec = RECOMMENDED_TRACKS.map((name) => tracks.find((t) => t.name === name)).filter(
    (t): t is TorcsTrack => t !== undefined,
  );
  const rest = tracks
    .filter((t) => !recSet.has(t.name))
    .sort((a, b) => {
      if (a.category !== b.category) return a.category.localeCompare(b.category);
      return a.name.localeCompare(b.name);
    });
  return [...rec, ...rest];
}

export function groupTorcsTracks(tracks: TorcsTrack[]) {
  const recSet = new Set(RECOMMENDED_TRACKS);
  const recommended = tracks.filter((t) => recSet.has(t.name));
  const others: Record<string, TorcsTrack[]> = {};
  tracks
    .filter((t) => !recSet.has(t.name))
    .forEach((t) => {
      (others[t.category] ||= []).push(t);
    });
  return { recommended, others };
}

function describeApiError(error: unknown, fallback: string): string {
  if (error instanceof OverrideApiError) {
    return `${error.payload.message}${error.payload.detail ? ` — ${error.payload.detail}` : ""}`;
  }
  if (error instanceof Error) return error.message;
  return fallback;
}

interface UseTorcsControlOptions {
  defaultTrack?: string;
  defaultLaps?: number;
}

export function useTorcsControl({
  defaultTrack = "aalborg",
  defaultLaps = 75,
}: UseTorcsControlOptions = {}) {
  const [status, setStatus] = useState<TorcsControlStatus | null>(null);
  const [driverProfiles, setDriverProfiles] = useState<TorcsDriverProfileSummary[]>([]);
  const [driverProfileId, setDriverProfileId] = useState<string>("baseline");
  const [tracks, setTracks] = useState<TorcsTrack[]>(FALLBACK_TRACKS);
  const [track, setTrack] = useState<string>(defaultTrack);
  const [laps, setLaps] = useState<number>(defaultLaps);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await api.torcsControlStatus();
      setStatus(next);
      const nextState = next.state ?? (next.active ? "active" : null);
      const recoveredState =
        next.enabled &&
        next.reachable &&
        (isTorcsActiveState(nextState) || (nextState === "idle" && !next.last_error));
      if (recoveredState) {
        setError(null);
      }
    } catch (_error) {
      // 200-always endpoint; thrown error means backend down — keep last state.
    }
  }, []);

  useEffect(() => {
    if (!hasTorcsSurface()) return;
    refresh();
    const id = window.setInterval(refresh, POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    if (!hasTorcsSurface()) return;
    if (!status?.enabled || !status?.reachable) return;
    let cancelled = false;
    api.torcsTracks()
      .then((response) => {
        if (cancelled) return;
        if (response.tracks.length > 0) {
          setTracks(sortedTracks(response.tracks));
        }
      })
      .catch(() => {
        /* keep fallback tracks */
      });
    return () => {
      cancelled = true;
    };
  }, [status?.enabled, status?.reachable]);

  useEffect(() => {
    if (!hasTorcsSurface()) return;
    let cancelled = false;
    api.listTorcsDriverProfiles()
      .then((response) => {
        if (cancelled) return;
        setDriverProfiles(response.profiles);
        if (!response.profiles.some((profile) => profile.profile_id === driverProfileId)) {
          setDriverProfileId(response.profiles[0]?.profile_id ?? "baseline");
        }
      })
      .catch(() => {
        /* leave baseline fallback */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const groupedTracks = useMemo(() => groupTorcsTracks(tracks), [tracks]);

  const startRace = useCallback(
    async ({
      launchMode = "cockpit_practice",
      track: trackOverride,
      laps: lapsOverride,
      driverProfileId: driverProfileIdOverride,
    }: {
      launchMode?: TorcsLaunchMode;
      track?: string;
      laps?: number;
      driverProfileId?: string;
    } = {}): Promise<TorcsStartRaceResponse> => {
      setBusy(true);
      setError(null);
      try {
        const selectedTrack = trackOverride ?? track;
        const selectedLaps = lapsOverride ?? laps;
        const selectedDriverProfileId = driverProfileIdOverride ?? driverProfileId;
        const trackName = selectedTrack.charAt(0).toUpperCase() + selectedTrack.slice(1);
        const response = await api.startTorcsRace({
          track: selectedTrack,
          laps: selectedLaps,
          track_name: trackName,
          driver_profile_id: selectedDriverProfileId,
          launch_mode: launchMode,
          auto_launch_torcs: launchMode === "headless_quickrace",
        });
        await refresh();
        return response;
      } catch (error) {
        const message = describeApiError(error, "Failed to start race.");
        setError(message);
        throw new Error(message);
      } finally {
        setBusy(false);
      }
    },
    [driverProfileId, laps, refresh, track],
  );

  const stopRace = useCallback(async (): Promise<TorcsStopRaceResponse> => {
    setBusy(true);
    setError(null);
    try {
      const response = await api.stopTorcsRace();
      await refresh();
      return response;
    } catch (error) {
      const message = describeApiError(error, "Failed to stop race.");
      setError(message);
      throw new Error(message);
    } finally {
      setBusy(false);
    }
  }, [refresh]);

  const recover = useCallback(async (): Promise<TorcsRecoverResponse> => {
    setBusy(true);
    setError(null);
    try {
      const response = await api.recoverTorcs();
      await refresh();
      return response;
    } catch (error) {
      const message = describeApiError(error, "Failed to reset the simulator.");
      setError(message);
      throw new Error(message);
    } finally {
      setBusy(false);
    }
  }, [refresh]);

  return {
    status,
    driverProfiles,
    driverProfileId,
    setDriverProfileId,
    tracks,
    groupedTracks,
    track,
    setTrack,
    laps,
    setLaps,
    busy,
    error,
    setError,
    refresh,
    startRace,
    stopRace,
    recover,
  };
}
