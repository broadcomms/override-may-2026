import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { OverrideApiError, api } from "@/api/client";
import type {
  CopilotAnswer,
  CopilotMessage,
  CopilotRequestContext,
  TorcsRaceState,
} from "@/api/types";
import { useLiveTelemetry } from "@/hooks/useLiveTelemetry";

type RaceEngineerContextKind = "session" | "lap" | "live_race";
type RaceEngineerMessageRole = "user" | "assistant";
type SetPageContextValue =
  | RaceEngineerPageContext
  | null
  | ((current: RaceEngineerPageContext | null) => RaceEngineerPageContext | null);

export interface RaceEngineerPageContext {
  kind: RaceEngineerContextKind;
  sessionId: string | null;
  fixture?: boolean;
  lapNumber?: number | null;
  title?: string | null;
  latestLapNumber?: number | null;
  raceState?: TorcsRaceState | null;
}

export interface RaceEngineerMessage {
  id: string;
  role: RaceEngineerMessageRole;
  content: string;
  timestamp: string;
  engine?: CopilotAnswer["engine"];
  confidence?: CopilotAnswer["confidence"];
  supportingLaps?: number[];
  suggestions?: string[];
}

interface RaceEngineerThread {
  threadKey: string;
  sessionId: string;
  fixture: boolean;
  messages: RaceEngineerMessage[];
}

interface PersistedRaceEngineerState {
  open: boolean;
  unreadCount: number;
  threads: Record<string, RaceEngineerThread>;
}

interface RaceEngineerContextValue {
  open: boolean;
  activeContext: RaceEngineerPageContext | null;
  activeThread: RaceEngineerThread | null;
  isThinking: boolean;
  unreadCount: number;
  error: string | null;
  live: ReturnType<typeof useLiveTelemetry>;
  setPageContext: (value: SetPageContextValue) => void;
  openWidget: () => void;
  closeWidget: () => void;
  toggleWidget: () => void;
  clearError: () => void;
  submitQuestion: (question: string) => Promise<void>;
}

const STORAGE_KEY = "override-race-engineer";
const MAX_THREAD_MESSAGES = 30;
const MAX_RECENT_TURNS = 6;

const RaceEngineerContext = createContext<RaceEngineerContextValue | null>(null);

function emptyPersistedState(): PersistedRaceEngineerState {
  return { open: false, unreadCount: 0, threads: {} };
}

function readPersistedState(): PersistedRaceEngineerState {
  if (typeof window === "undefined") return emptyPersistedState();
  const raw = window.sessionStorage.getItem(STORAGE_KEY);
  if (!raw) return emptyPersistedState();
  try {
    const parsed = JSON.parse(raw) as PersistedRaceEngineerState;
    if (!parsed || typeof parsed !== "object") return emptyPersistedState();
    return {
      open: parsed.open === true,
      unreadCount: typeof parsed.unreadCount === "number" ? parsed.unreadCount : 0,
      threads: typeof parsed.threads === "object" && parsed.threads != null ? parsed.threads : {},
    };
  } catch {
    return emptyPersistedState();
  }
}

function writePersistedState(state: PersistedRaceEngineerState) {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function createMessageId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `re_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function makeThreadKey(context: RaceEngineerPageContext | null): string | null {
  if (!context?.sessionId) return null;
  return `${context.fixture === true ? "fixture" : "live"}:${context.sessionId}`;
}

function trimMessages(messages: RaceEngineerMessage[]) {
  return messages.slice(-MAX_THREAD_MESSAGES);
}

function messageToTurn(message: RaceEngineerMessage): CopilotMessage {
  return {
    role: message.role,
    content: message.content,
    timestamp: message.timestamp,
  };
}

function buildCopilotContext(
  context: RaceEngineerPageContext,
  live: RaceEngineerContextValue["live"],
): CopilotRequestContext {
  if (context.kind !== "live_race") {
    return {
      mode: context.kind,
      lap_number: context.lapNumber ?? null,
      live: null,
    };
  }
  return {
    mode: "live_race",
    lap_number: context.lapNumber ?? live.latestSnapshot?.lap ?? live.latestLap?.lap ?? null,
    live: {
      latest_snapshot: live.latestSnapshot,
      completed_laps: live.laps.slice(-5),
      insights: live.insights.slice(0, 5),
      race_state: context.raceState ?? null,
    },
  };
}

function buildThread(context: RaceEngineerPageContext, threadKey: string, messages: RaceEngineerMessage[]): RaceEngineerThread {
  return {
    threadKey,
    sessionId: context.sessionId ?? "",
    fixture: context.fixture === true,
    messages: trimMessages(messages),
  };
}

export function RaceEngineerProvider({ children }: { children: ReactNode }) {
  const persisted = useMemo(() => readPersistedState(), []);
  const [open, setOpen] = useState(persisted.open);
  const [unreadCount, setUnreadCount] = useState(persisted.unreadCount);
  const [threads, setThreads] = useState<Record<string, RaceEngineerThread>>(persisted.threads);
  const [activeContext, setActiveContext] = useState<RaceEngineerPageContext | null>(null);
  const [isThinking, setIsThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const openRef = useRef(open);
  const live = useLiveTelemetry(activeContext?.kind === "live_race" ? activeContext.sessionId : null, {
    retryNoTelemetry: true,
  });

  useEffect(() => {
    writePersistedState({ open, unreadCount, threads });
  }, [open, unreadCount, threads]);

  useEffect(() => {
    openRef.current = open;
  }, [open]);

  const activeThreadKey = makeThreadKey(activeContext);
  const activeThread = useMemo(() => {
    if (!activeThreadKey || !activeContext?.sessionId) return null;
    return threads[activeThreadKey] ?? buildThread(activeContext, activeThreadKey, []);
  }, [activeContext, activeThreadKey, threads]);

  const setPageContext = useCallback((value: SetPageContextValue) => {
    setActiveContext((current) => (typeof value === "function" ? value(current) : value));
  }, []);

  const submitQuestion = useCallback(async (question: string) => {
    const context = activeContext;
    const threadKey = activeThreadKey;
    const thread = activeThread;
    const trimmed = question.trim();
    if (!context?.sessionId || !threadKey || !trimmed || isThinking) return;

    setOpen(true);
    setUnreadCount(0);
    setError(null);
    setIsThinking(true);

    const userMessage: RaceEngineerMessage = {
      id: createMessageId(),
      role: "user",
      content: trimmed,
      timestamp: new Date().toISOString(),
    };
    const nextMessages = trimMessages([...(thread?.messages ?? []), userMessage]);
    const assistantMessageId = createMessageId();
    setThreads((current) => ({
      ...current,
      [threadKey]: buildThread(context, threadKey, nextMessages),
    }));

    try {
      setThreads((current) => {
        const baseThread = current[threadKey] ?? buildThread(context, threadKey, nextMessages);
        return {
          ...current,
          [threadKey]: buildThread(context, threadKey, [
            ...baseThread.messages,
            {
              id: assistantMessageId,
              role: "assistant",
              content: "",
              timestamp: new Date().toISOString(),
            },
          ]),
        };
      });

      await api.streamCopilot(
        context.sessionId,
        trimmed,
        nextMessages.map(messageToTurn).slice(-MAX_RECENT_TURNS),
        buildCopilotContext(context, live),
        {
          onEvent: (event) => {
            if (event.event === "delta") {
              setThreads((current) => {
                const baseThread = current[threadKey];
                if (!baseThread) return current;
                return {
                  ...current,
                  [threadKey]: buildThread(
                    context,
                    threadKey,
                    baseThread.messages.map((message) =>
                      message.id === assistantMessageId
                        ? { ...message, content: `${message.content}${event.delta}` }
                        : message,
                    ),
                  ),
                };
              });
              return;
            }
            if (event.event === "complete") {
              setThreads((current) => {
                const baseThread = current[threadKey];
                if (!baseThread) return current;
                return {
                  ...current,
                  [threadKey]: buildThread(
                    context,
                    threadKey,
                    baseThread.messages.map((message) =>
                      message.id === assistantMessageId
                        ? {
                            ...message,
                            content: event.answer.answer,
                            engine: event.answer.engine,
                            confidence: event.answer.confidence,
                            supportingLaps: event.answer.supporting_laps,
                            suggestions: event.answer.suggestions,
                          }
                        : message,
                    ),
                  ),
                };
              });
              if (!openRef.current) {
                setUnreadCount((current) => current + 1);
              }
              return;
            }
            if (event.event === "error") {
              setError(event.message);
            }
          },
        },
        context.fixture === true ? { fixture: true } : undefined,
      );
    } catch (err) {
      setThreads((current) => {
        const baseThread = current[threadKey];
        if (!baseThread) return current;
        return {
          ...current,
          [threadKey]: buildThread(
            context,
            threadKey,
            baseThread.messages.filter((message) => !(message.id === assistantMessageId && message.content.length === 0)),
          ),
        };
      });
      setError(
        err instanceof OverrideApiError
          ? err.payload.message
          : err instanceof Error
            ? err.message
            : "Race engineer response unavailable.",
      );
    } finally {
      setIsThinking(false);
    }
  }, [activeContext, activeThread, activeThreadKey, isThinking, live]);

  const openWidget = useCallback(() => {
    setUnreadCount(0);
    setOpen(true);
  }, []);

  const closeWidget = useCallback(() => {
    setOpen(false);
  }, []);

  const toggleWidget = useCallback(() => {
    setOpen((current) => {
      const next = !current;
      if (next) setUnreadCount(0);
      return next;
    });
  }, []);

  const value = useMemo<RaceEngineerContextValue>(() => ({
    open,
    activeContext,
    activeThread,
    isThinking,
    unreadCount,
    error,
    live,
    setPageContext,
    openWidget,
    closeWidget,
    toggleWidget,
    clearError: () => setError(null),
    submitQuestion,
  }), [activeContext, activeThread, closeWidget, error, isThinking, live, open, openWidget, setPageContext, submitQuestion, toggleWidget, unreadCount]);

  return (
    <RaceEngineerContext.Provider value={value}>
      {children}
    </RaceEngineerContext.Provider>
  );
}

export function useRaceEngineer() {
  const context = useContext(RaceEngineerContext);
  if (context == null) {
    throw new Error("useRaceEngineer must be used within RaceEngineerProvider");
  }
  return context;
}

export function useRaceEngineerPageContext(context: RaceEngineerPageContext | null) {
  const { setPageContext } = useRaceEngineer();
  const contextKey = makeThreadKey(context);

  useEffect(() => {
    setPageContext(context);
    return () => {
      setPageContext((current) => {
        if (makeThreadKey(current) === contextKey && current?.kind === context?.kind) {
          return null;
        }
        return current;
      });
    };
  }, [context, contextKey, setPageContext]);
}
