import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { useRaceEngineer } from "@/context/RaceEngineerContext";

export function RaceEngineerWidget() {
  const {
    open,
    activeContext,
    activeThread,
    isThinking,
    unreadCount,
    error,
    live,
    openWidget,
    closeWidget,
    clearError,
    submitQuestion,
  } = useRaceEngineer();
  const [question, setQuestion] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  const contextLabel = useMemo(() => {
    if (!activeContext?.sessionId) return "Open a session or live cockpit";
    if (activeContext.kind === "live_race") {
      return activeContext.title ? `Live race · ${activeContext.title}` : "Live race";
    }
    if (activeContext.kind === "lap") {
      return activeContext.lapNumber != null ? `Lap ${activeContext.lapNumber} detail` : "Lap detail";
    }
    return activeContext.title ? `Session · ${activeContext.title}` : "Session debrief";
  }, [activeContext]);

  const suggestedQuestions = useMemo(() => {
    if (!activeContext?.sessionId) return [];
    if (activeContext.kind === "live_race") {
      const latestLap = live.latestLap?.lap ?? activeContext.latestLapNumber ?? 1;
      return [
        "Are we under battery pressure now?",
        "What changed this lap?",
        `Compare lap ${Math.max(1, latestLap - 1)} and lap ${latestLap}`,
        "Why did OVERRIDE surface the latest insight?",
      ];
    }
    const latestLap = activeContext.latestLapNumber ?? activeContext.lapNumber ?? 1;
    const compareLap = Math.max(1, latestLap - 1);
    if (activeContext.kind === "lap" && activeContext.lapNumber != null) {
      return [
        `Why was lap ${activeContext.lapNumber} inefficient?`,
        `Compare lap ${compareLap} and lap ${activeContext.lapNumber}`,
        "What happened in sector 3?",
        "Summarize the battery trend",
      ];
    }
    return [
      "Why did OVERRIDE recommend the current strategy?",
      `Compare lap ${compareLap} and lap ${latestLap}`,
      "What happened in sector 3?",
      "Summarize the battery trend",
    ];
  }, [activeContext, live.latestLap?.lap]);

  const latestAssistant = useMemo(
    () => activeThread?.messages.slice().reverse().find((message) => message.role === "assistant") ?? null,
    [activeThread?.messages],
  );
  const contextBadges = useMemo(() => {
    if (!activeContext?.sessionId) return [];
    const badges = [
      activeContext.kind === "live_race"
        ? "Live race"
        : activeContext.kind === "lap"
          ? `Lap ${activeContext.lapNumber ?? "?"}`
          : "Session",
    ];
    if (activeContext.kind === "live_race") {
      badges.push(live.streamState.kind === "connected" ? "Live stream" : live.streamState.kind.replace(/_/g, " "));
      if (activeContext.raceState) badges.push(activeContext.raceState.replace(/_/g, " "));
    } else if (activeContext.title) {
      badges.push(activeContext.title);
    }
    return badges;
  }, [activeContext, live.streamState.kind]);

  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  }, [activeThread?.messages, isThinking, open]);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed) return;
    void submitQuestion(trimmed);
    setQuestion("");
  };

  const disabled = !activeContext?.sessionId || isThinking;

  return (
    <>
      <button
        type="button"
        onClick={open ? closeWidget : openWidget}
        className="fixed bottom-4 right-4 z-40 flex items-center gap-2 rounded-pill border border-accent/40 bg-surface px-4 py-3 text-sm font-medium text-text shadow-card-hover transition-colors hover:border-accent"
      >
        <span className="inline-flex h-2 w-2 rounded-full bg-accent" aria-hidden="true" />
        AI race engineer
        {unreadCount > 0 && (
          <span className="inline-flex min-w-5 items-center justify-center rounded-pill bg-accent px-1.5 py-0.5 text-[11px] font-semibold text-bg">
            {unreadCount}
          </span>
        )}
      </button>

      {open && (
        <aside className="fixed bottom-20 right-4 z-40 flex h-[min(42rem,calc(100vh-7rem))] w-[min(24rem,calc(100vw-2rem))] flex-col rounded-card border border-border bg-surface shadow-card-hover">
          <header className="border-b border-border px-4 py-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted">
                  AI race engineer
                </div>
                <h2 className="mt-1 text-sm font-semibold text-text">{contextLabel}</h2>
                <p className="mt-1 text-xs text-muted">
                  {activeContext?.kind === "live_race"
                    ? "Grounded in live telemetry, recent closed laps, and deterministic live insights."
                    : "Grounded in the current session, lap context, recommendations, and cached report artifacts."}
                </p>
                {contextBadges.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {contextBadges.map((badge) => (
                      <span
                        key={badge}
                        className="rounded-pill border border-border px-2.5 py-1 text-[11px] uppercase tracking-wider text-muted"
                      >
                        {badge}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <button
                type="button"
                onClick={closeWidget}
                className="rounded-pill border border-border px-2.5 py-1 text-xs text-muted transition-colors hover:text-text"
              >
                Close
              </button>
            </div>
          </header>

          <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
            {!activeContext?.sessionId && (
              <div className="rounded-card border border-border/70 bg-surface-2/30 p-3 text-sm text-muted">
                Open a completed session, lap detail, or the live cockpit to start a grounded race-engineer chat.
              </div>
            )}

            {activeThread?.messages.map((message) => (
              <div
                key={message.id}
                className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[85%] rounded-card px-3 py-2 text-sm ${
                    message.role === "user"
                      ? "bg-accent/10 text-text"
                      : "border border-border/70 bg-surface-2/30 text-text"
                  }`}
                >
                  {message.role === "assistant" && (
                    <div className="mb-1 text-[11px] uppercase tracking-wider text-muted">
                      {message.engine == null
                        ? "Composing"
                        : message.engine === "granite"
                          ? "Granite-backed"
                          : "Deterministic fallback"}
                      {message.confidence ? ` · ${message.confidence}` : ""}
                    </div>
                  )}
                  <p>{message.content || "…"}</p>

                  {message.supportingLaps && message.supportingLaps.length > 0 && activeContext?.sessionId && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {message.supportingLaps.map((lapNumber) => (
                        <Link
                          key={`${message.id}-${lapNumber}`}
                          to={`/session/${encodeURIComponent(activeContext.sessionId!)}/laps/${lapNumber}${activeContext.fixture ? "?fixture=1" : ""}`}
                          className="rounded-pill border border-border px-2.5 py-1 text-[11px] text-accent transition-colors hover:text-text"
                        >
                          Lap {lapNumber}
                        </Link>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {isThinking && (
              <div className="flex justify-start">
                <div className="max-w-[85%] rounded-card border border-border/70 bg-surface-2/30 px-3 py-2 text-sm text-muted">
                  <div className="mb-1 text-[11px] uppercase tracking-wider">Granite</div>
                  Consulting the race context…
                </div>
              </div>
            )}

            {!isThinking && activeThread?.messages.length === 0 && activeContext?.sessionId && (
              <div className="rounded-card border border-border/70 bg-surface-2/30 p-3 text-sm text-muted">
                Ask why OVERRIDE surfaced a strategy, compare laps, or diagnose the live race state without leaving this page.
              </div>
            )}

            {error && (
              <div className="rounded-card border border-danger/40 bg-danger/5 p-3 text-sm text-danger">
                <div className="flex items-start justify-between gap-3">
                  <span>{error}</span>
                  <button
                    type="button"
                    onClick={clearError}
                    className="text-xs text-danger/80 transition-colors hover:text-danger"
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="border-t border-border px-4 py-3">
            <div className="mb-3 flex flex-wrap gap-2">
              {(latestAssistant?.suggestions ?? suggestedQuestions).slice(0, 4).map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => void submitQuestion(item)}
                  disabled={disabled}
                  className="rounded-pill border border-border px-3 py-1.5 text-[11px] text-accent transition-colors hover:text-text disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {item}
                </button>
              ))}
            </div>

            <form onSubmit={onSubmit} className="space-y-3">
              <textarea
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                disabled={!activeContext?.sessionId}
                placeholder={
                  activeContext?.kind === "live_race"
                    ? "Why did OVERRIDE surface that live insight?"
                    : "Why did OVERRIDE recommend conservative deployment?"
                }
                className="min-h-24 w-full rounded-card border border-border bg-surface-2/30 px-3 py-2 text-sm text-text outline-none transition-colors focus:border-accent disabled:cursor-not-allowed disabled:opacity-60"
              />
              <div className="flex items-center justify-between gap-3">
                <div className="text-xs text-muted">
                  {activeContext?.kind === "live_race"
                    ? "Live answers stay grounded in the current stream and recent closed laps."
                    : "Session answers stay grounded in laps, recommendations, and report evidence."}
                </div>
                <button
                  type="submit"
                  disabled={disabled || question.trim().length === 0}
                  className="rounded-pill border border-accent px-4 py-2 text-sm text-accent transition-colors hover:bg-accent/10 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {isThinking ? "Consulting Granite…" : "Send"}
                </button>
              </div>
            </form>
          </div>
        </aside>
      )}
    </>
  );
}
