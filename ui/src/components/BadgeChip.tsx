/**
 * Generic chip badge — used for severity, validator/Guardian status, confidence.
 * Per docs/04-ui-ux-design.md §3 (radius pill, color tokens) and §7 (failed-rules
 * lists shown as small chips).
 */

import type { ReactNode } from "react";

type Tone = "neutral" | "success" | "warning" | "danger" | "accent" | "granite";

const TONE_CLASS: Record<Tone, string> = {
  neutral: "bg-surface-2 text-muted border-border",
  success: "bg-success/15 text-success border-success/40",
  warning: "bg-warning/15 text-warning border-warning/40",
  danger:  "bg-danger/15 text-danger border-danger/40",
  accent:  "bg-accent/15 text-accent border-accent/40",
  granite: "bg-granite/15 text-text border-granite/40",
};

interface Props {
  tone?: Tone;
  children: ReactNode;
  title?: string;
}

export function BadgeChip({ tone = "neutral", children, title }: Props) {
  const hoverAffordance = title
    ? "cursor-help transition-colors hover:brightness-110"
    : "";
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium border rounded-pill ${TONE_CLASS[tone]} ${hoverAffordance}`}
    >
      {children}
    </span>
  );
}

export function severityTone(severity: "low" | "medium" | "high"): Tone {
  return severity === "high" ? "danger" : severity === "medium" ? "warning" : "neutral";
}

export function confidenceTone(c: "low" | "medium" | "high"): Tone {
  return c === "high" ? "success" : c === "medium" ? "warning" : "neutral";
}
