/**
 * Sample replay picker for the Upload page.
 *
 * Entry-page sample replay list from the shipped upload-page redesign:
 * row-style list with metadata, top row marked ◆ Recommended. Top sample is
 * the rubric-positive happy-path TORCS demo per architect M2 (the entry-page
 * preview should show the optimistic case; layered-defense is still offered
 * as a Pass-2-rejection learning option but doesn't get the ◆).
 */

import type { FixtureName } from "@/api/client";

interface Sample {
  name: FixtureName;
  title: string;
  laps: number;
  zones: number;
  badge: "cached" | "sample";
}

const SAMPLES: Sample[] = [
  { name: "torcs_engineer", title: "TORCS engineer demo", laps: 12, zones: 1, badge: "sample" },
  { name: "layered_defense", title: "Layered-defense demo", laps: 47, zones: 3, badge: "cached" },
  { name: "engineer_happy", title: "Engineer happy-path demo", laps: 18, zones: 2, badge: "sample" },
];

interface Props {
  onSample: (name: FixtureName) => void;
  isUploading: boolean;
  /** Which sample carries the ◆ Recommended mark. Defaults to torcs_engineer per architect M2. */
  recommended?: FixtureName;
}

export function SampleReplayList({
  onSample,
  isUploading,
  recommended = "torcs_engineer",
}: Props) {
  return (
    <ul className="divide-y divide-border rounded-card border border-border bg-surface overflow-hidden">
      {SAMPLES.map((s) => {
        const isRecommended = s.name === recommended;
        return (
          <li key={s.name}>
            <button
              type="button"
              onClick={() => onSample(s.name)}
              disabled={isUploading}
              className="w-full text-left px-4 py-3 flex items-center gap-3 transition-colors hover:bg-surface-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <span className="flex-1 min-w-0">
                <span className="flex items-center gap-2">
                  <span className="text-text font-medium">▸ {s.title}</span>
                  {isRecommended && (
                    <span
                      className="text-[10px] uppercase tracking-wider font-mono text-accent"
                      aria-label="Recommended"
                    >
                      ◆ Recommended
                    </span>
                  )}
                </span>
                <span className="block text-xs text-muted mt-0.5 font-mono">
                  {s.laps} laps · {s.zones} zone{s.zones === 1 ? "" : "s"} · {s.badge}
                </span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
