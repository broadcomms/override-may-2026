import { FormEvent, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { OverrideApiError, api } from "@/api/client";
import type { CopilotAnswer, CopilotMessage, Session } from "@/api/types";

interface Props {
  fixture?: boolean;
  session: Session;
  sessionId: string;
}

const MAX_TURNS = 6;

export function RaceCopilotPanel({ fixture, session, sessionId }: Props) {
  const [question, setQuestion] = useState("");
  const [recentTurns, setRecentTurns] = useState<CopilotMessage[]>([]);
  const [answer, setAnswer] = useState<CopilotAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const suggestions = useMemo(() => {
    const latestLap = session.laps[session.laps.length - 1]?.lap_number ?? 1;
    const compareLap = Math.max(1, latestLap - 1);
    return [
      `Why did the AI recommend the current strategy?`,
      `Compare lap ${compareLap} and lap ${latestLap}`,
      "What happened in sector 3?",
      "Summarize the battery trend",
    ];
  }, [session.laps]);

  const submitQuestion = async (rawQuestion: string) => {
    const trimmed = rawQuestion.trim();
    if (!trimmed || loading) return;
    const userTurn: CopilotMessage = {
      role: "user",
      content: trimmed,
      timestamp: new Date().toISOString(),
    };
    const payloadTurns = [...recentTurns, userTurn].slice(-MAX_TURNS);
    setLoading(true);
    setError(null);
    setQuestion("");
    try {
        const nextAnswer = await api.askCopilot(sessionId, trimmed, payloadTurns, null, { fixture });
      const assistantTurn: CopilotMessage = {
        role: "assistant",
        content: nextAnswer.answer,
        timestamp: new Date().toISOString(),
      };
      setRecentTurns([...payloadTurns, assistantTurn].slice(-MAX_TURNS));
      setAnswer(nextAnswer);
    } catch (err) {
      setError(
        err instanceof OverrideApiError
          ? err.payload.message
          : err instanceof Error
            ? err.message
            : "Copilot response unavailable.",
      );
    } finally {
      setLoading(false);
    }
  };

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void submitQuestion(question);
  };

  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-mono text-[11px] uppercase tracking-[0.24em] text-muted">Race copilot</div>
          <h2 className="mt-2 text-xl font-semibold text-text">Ask the session why</h2>
          <p className="mt-2 text-sm text-muted">
            Granite-backed answers stay grounded in the current session&apos;s laps, recommendations, and energy trend.
          </p>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {suggestions.map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => void submitQuestion(item)}
            className="rounded-pill border border-border px-3 py-1.5 text-xs text-accent transition-colors hover:text-text"
            disabled={loading}
          >
            {item}
          </button>
        ))}
      </div>

      <form onSubmit={onSubmit} className="mt-4 flex flex-col gap-3">
        <textarea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Why did the AI recommend conservative deployment mode?"
          className="min-h-24 rounded-card border border-border bg-surface-2/30 px-3 py-2 text-sm text-text outline-none transition-colors focus:border-accent"
        />
        <div className="flex items-center justify-between gap-3">
          <div className="text-xs text-muted">
            Granite answers cite session evidence first; deterministic fallback stays available if model output cannot be structured.
          </div>
          <button
            type="submit"
            disabled={loading || question.trim().length === 0}
            className="rounded-pill border border-accent px-4 py-2 text-sm text-accent transition-colors hover:bg-accent/10 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Consulting Granite…" : "Ask copilot"}
          </button>
        </div>
      </form>

      {error && (
        <div className="mt-4 rounded-card border border-danger/40 bg-danger/5 p-3 text-sm text-danger">
          {error}
        </div>
      )}

      {answer && (
        <div className="mt-4 rounded-card border border-border/70 bg-surface-2/30 p-4">
          <div className="text-[11px] uppercase tracking-wider text-muted">
            Engine · <span className="text-text">{answer.engine === "granite" ? "Granite-backed" : "Deterministic fallback"}</span>
            <span className="mx-2">·</span>
            Confidence · <span className="text-text">{answer.confidence}</span>
          </div>
          <p className="mt-2 text-sm text-text">{answer.answer}</p>

          {answer.supporting_laps.length > 0 && (
            <div className="mt-4">
              <div className="text-[11px] uppercase tracking-wider text-muted">Supporting laps</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {answer.supporting_laps.map((lapNumber) => (
                  <Link
                    key={lapNumber}
                    to={`/session/${encodeURIComponent(sessionId)}/laps/${lapNumber}${fixture ? "?fixture=1" : ""}`}
                    className="rounded-pill border border-border px-3 py-1.5 text-xs text-accent transition-colors hover:text-text"
                  >
                    Lap {lapNumber}
                  </Link>
                ))}
              </div>
            </div>
          )}

          {answer.suggestions.length > 0 && (
            <div className="mt-4">
              <div className="text-[11px] uppercase tracking-wider text-muted">Suggested follow-ups</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {answer.suggestions.map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => void submitQuestion(item)}
                    className="rounded-pill border border-border px-3 py-1.5 text-xs text-accent transition-colors hover:text-text"
                    disabled={loading}
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
