/**
 * Engineer ↔ Fan mode toggle in the page header.
 * Per docs/04-ui-ux-design.md §4.5: pill, accent fill on active side,
 * keyboard shortcut (E/F).
 */

import { useEffect } from "react";

export type Mode = "engineer" | "fan";

interface Props {
  mode: Mode;
  onChange: (m: Mode) => void;
}

export function ModeToggle({ mode, onChange }: Props) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      // Don't intercept while typing in an input
      if (e.target instanceof HTMLElement &&
          (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA")) {
        return;
      }
      if (e.key === "e" || e.key === "E") onChange("engineer");
      if (e.key === "f" || e.key === "F") onChange("fan");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onChange]);

  return (
    <div
      className="inline-flex p-0.5 rounded-pill border border-border bg-surface text-sm"
      role="radiogroup"
      aria-label="Display mode"
    >
      <ModeButton active={mode === "engineer"} onClick={() => onChange("engineer")} label="Engineer" hotkey="E" />
      <ModeButton active={mode === "fan"} onClick={() => onChange("fan")} label="Fan" hotkey="F" />
    </div>
  );
}

function ModeButton({
  active, onClick, label, hotkey,
}: { active: boolean; onClick: () => void; label: string; hotkey: string }) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={active}
      onClick={onClick}
      className={`px-3 py-1 rounded-pill transition-colors ${
        active ? "bg-accent text-bg font-medium" : "text-muted hover:text-text"
      }`}
    >
      {label}
      <span className="ml-1 text-[10px] opacity-60 font-mono">{hotkey}</span>
    </button>
  );
}
