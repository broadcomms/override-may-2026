import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/api/client";
import type { LiveInsight, LiveLapSnapshot, LiveLapStats, LiveStreamEvent } from "@/api/types";

export type LiveStreamState =
  | { kind: "idle" }
  | { kind: "connecting" }
  | { kind: "connected"; status: string }
  | { kind: "no_telemetry"; message: string }
  | { kind: "error" }
  | { kind: "ended"; reason: string };

interface UseLiveTelemetryOptions {
  onRaceEnded?: () => void;
  retryNoTelemetry?: boolean;
  retryDelayMs?: number;
}

interface LiveTelemetrySnapshot {
  laps: LiveLapStats[];
  insights: LiveInsight[];
  latestSnapshot: LiveLapSnapshot | null;
  streamState: LiveStreamState;
  raceEnded: boolean;
}

interface StoreSubscriber {
  onState: (snapshot: LiveTelemetrySnapshot) => void;
  onRaceEnded?: () => void;
}

interface LiveTelemetryStore {
  sessionId: string;
  state: LiveTelemetrySnapshot;
  subscribers: Set<StoreSubscriber>;
  teardown: (() => void) | null;
  retryTimer: number | null;
  retryNoTelemetry: boolean;
  retryDelayMs: number;
}

const DEFAULT_RETRY_DELAY_MS = 1500;
const stores = new Map<string, LiveTelemetryStore>();

function initialSnapshot(): LiveTelemetrySnapshot {
  return {
    laps: [],
    insights: [],
    latestSnapshot: null,
    streamState: { kind: "idle" },
    raceEnded: false,
  };
}

function notify(store: LiveTelemetryStore) {
  for (const subscriber of store.subscribers) {
    subscriber.onState(store.state);
  }
}

function updateStore(store: LiveTelemetryStore, updater: (current: LiveTelemetrySnapshot) => LiveTelemetrySnapshot) {
  store.state = updater(store.state);
  notify(store);
}

function clearRetryTimer(store: LiveTelemetryStore) {
  if (store.retryTimer !== null) {
    window.clearTimeout(store.retryTimer);
    store.retryTimer = null;
  }
}

function disconnectStore(store: LiveTelemetryStore) {
  clearRetryTimer(store);
  store.teardown?.();
  store.teardown = null;
}

function handleEvent(store: LiveTelemetryStore, ev: LiveStreamEvent) {
  switch (ev.event) {
    case "connected":
      updateStore(store, (current) => ({
        ...current,
        streamState: { kind: "connected", status: ev.status },
      }));
      return;
    case "snapshot":
      updateStore(store, (current) => ({
        ...current,
        latestSnapshot: ev.snapshot,
      }));
      return;
    case "insight":
      updateStore(store, (current) => {
        const withoutCurrent = current.insights.filter((insight) => insight.insight_id !== ev.insight.insight_id);
        return {
          ...current,
          insights: [ev.insight, ...withoutCurrent].slice(0, 5),
        };
      });
      return;
    case "lap":
      updateStore(store, (current) => {
        const existing = current.laps.findIndex((lap) => lap.lap === ev.lap);
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
          const next = current.laps.slice();
          next[existing] = stats;
          return { ...current, laps: next };
        }
        return { ...current, laps: [...current.laps, stats] };
      });
      return;
    case "no_telemetry":
      updateStore(store, (current) => ({
        ...current,
        streamState: { kind: "no_telemetry", message: ev.message },
      }));
      if (store.retryNoTelemetry) {
        clearRetryTimer(store);
        store.retryTimer = window.setTimeout(() => {
          store.retryTimer = null;
          if (store.subscribers.size === 0) return;
          connectStore(store);
        }, store.retryDelayMs);
      }
      return;
    case "race_ended":
      updateStore(store, (current) => ({
        ...current,
        raceEnded: true,
        latestSnapshot: null,
        streamState: { kind: "ended", reason: ev.reason ?? "completed" },
      }));
      for (const subscriber of store.subscribers) {
        subscriber.onRaceEnded?.();
      }
      return;
  }
}

function connectStore(store: LiveTelemetryStore) {
  disconnectStore(store);
  updateStore(store, (current) => ({
    ...current,
    streamState: { kind: "connecting" },
  }));
  store.teardown = api.streamSession(store.sessionId, (event) => handleEvent(store, event), {
    onError: () => {
      updateStore(store, (current) => ({
        ...current,
        streamState: { kind: "error" },
      }));
    },
  });
}

function getOrCreateStore(sessionId: string): LiveTelemetryStore {
  const existing = stores.get(sessionId);
  if (existing) return existing;
  const store: LiveTelemetryStore = {
    sessionId,
    state: {
      ...initialSnapshot(),
      streamState: { kind: "connecting" },
    },
    subscribers: new Set(),
    teardown: null,
    retryTimer: null,
    retryNoTelemetry: false,
    retryDelayMs: DEFAULT_RETRY_DELAY_MS,
  };
  stores.set(sessionId, store);
  return store;
}

export function useLiveTelemetry(
  sessionId: string | null | undefined,
  {
    onRaceEnded,
    retryNoTelemetry = false,
    retryDelayMs = DEFAULT_RETRY_DELAY_MS,
  }: UseLiveTelemetryOptions = {},
) {
  const [snapshot, setSnapshot] = useState<LiveTelemetrySnapshot>(() => initialSnapshot());
  const onRaceEndedRef = useRef(onRaceEnded);

  useEffect(() => {
    onRaceEndedRef.current = onRaceEnded;
  }, [onRaceEnded]);

  useEffect(() => {
    if (!sessionId) {
      setSnapshot(initialSnapshot());
      return;
    }

    const store = getOrCreateStore(sessionId);
    store.retryNoTelemetry = store.retryNoTelemetry || retryNoTelemetry;
    store.retryDelayMs = Math.min(store.retryDelayMs, retryDelayMs);

    const subscriber: StoreSubscriber = {
      onState: setSnapshot,
      onRaceEnded: () => onRaceEndedRef.current?.(),
    };
    store.subscribers.add(subscriber);
    setSnapshot(store.state);
    if (store.teardown == null) {
      connectStore(store);
    }

    return () => {
      store.subscribers.delete(subscriber);
      if (store.subscribers.size === 0) {
        disconnectStore(store);
        stores.delete(sessionId);
      }
    };
  }, [retryDelayMs, retryNoTelemetry, sessionId]);

  return useMemo(
    () => ({
      laps: snapshot.laps,
      insights: snapshot.insights,
      streamState: snapshot.streamState,
      latestLap: snapshot.laps.length > 0 ? snapshot.laps[snapshot.laps.length - 1] : null,
      latestSnapshot: snapshot.latestSnapshot,
      raceEnded: snapshot.raceEnded,
    }),
    [snapshot],
  );
}
