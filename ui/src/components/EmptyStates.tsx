/**
 * Empty / loading / error skeletons per docs/04-ui-ux-design.md §7.
 * P3.3 polish: low-confidence banner + better skeleton shimmer.
 */

import type { ReactNode } from "react";

export function EmptyState({
  icon = "—",
  title,
  body,
  cta,
}: {
  icon?: string;
  title: string;
  body?: ReactNode;
  cta?: ReactNode;
}) {
  return (
    <div className="rounded-card border border-dashed border-border p-8 text-center">
      <div className="text-3xl mb-2 text-muted" aria-hidden="true">
        {icon}
      </div>
      <div className="text-text font-medium mb-1">{title}</div>
      {body && <div className="text-sm text-muted">{body}</div>}
      {cta && <div className="mt-4">{cta}</div>}
    </div>
  );
}

export function LoadingSkeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div
      className="rounded-card bg-surface border border-border p-5"
      role="status"
      aria-label="Loading"
    >
      <div className="space-y-2">
        {Array.from({ length: lines }).map((_, i) => (
          <div
            key={i}
            className="h-3 rounded bg-gradient-to-r from-surface-2 via-border to-surface-2 bg-[length:200%_100%] animate-[shimmer_1.2s_ease-in-out_infinite]"
            style={{ width: `${100 - i * 12}%` }}
          />
        ))}
      </div>
      <span className="sr-only">Loading…</span>
    </div>
  );
}

export function ErrorBanner({
  title = "Something went wrong",
  detail,
  onRetry,
}: {
  title?: string;
  detail?: string;
  onRetry?: () => void;
}) {
  return (
    <div role="alert" className="rounded-md bg-danger/15 border border-danger/40 p-4">
      <div className="font-medium text-danger">{title}</div>
      {detail && <div className="text-sm text-muted mt-1">{detail}</div>}
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 px-3 py-1 rounded-pill border border-danger/40 text-sm text-danger hover:bg-danger/10"
        >
          Retry
        </button>
      )}
    </div>
  );
}

export function GroundingPendingBanner() {
  return (
    <div className="rounded-md bg-warning/15 border border-warning/40 p-3 text-sm text-text">
      <span className="font-medium">Regulation grounding unavailable —</span>{" "}
      citations will be generic until verification completes.
    </div>
  );
}

export function LowConfidenceBanner({ message }: { message?: string }) {
  return (
    <div className="rounded-md bg-warning/15 border border-warning/40 p-3 text-xs">
      <div className="font-medium text-warning mb-0.5">Treat as exploratory</div>
      <div className="text-text">
        {message ??
          "This recommendation passed Pass-1 validation but did not meet the AI safety threshold after retries."}
      </div>
    </div>
  );
}
