/**
 * WhatIfDiff — Before/After side-by-side renderer for FR-8 results.
 *
 * Per docs/04-ui-ux-design.md §4.3 (UI doc) and docs/plans/whatif-semantics.md
 * §"What the UI diff renders":
 *   - Two Recommendation cards side-by-side (Before = original, After = perturbed)
 *   - Highlighted deltas on key metrics (harvest_mj / deploy_mj / soc_end)
 *   - Validator + Guardian + Confidence badges for both sides — the
 *     perturbation may flip pass→fail or vice versa, which IS the
 *     explainability beat
 *   - Banner: "Perturbed by: <kind>(<params>)"
 *   - Footnote when the WhatIfResult.note is non-null (edge-case messages
 *     like "extension truncated: battery exhausted on lap 4")
 *   - NO animation between states. Clear "Before / After" labels beat motion.
 */

import type {
  PerturbationKind,
  Recommendation,
  WhatIfRequest,
  WhatIfResult,
} from "@/api/types";
import { BadgeChip, confidenceTone, severityTone } from "./BadgeChip";

interface Props {
  result: WhatIfResult;
  onDismiss?: () => void;
}

const PERTURBATION_LABEL: Record<PerturbationKind, string> = {
  delay_first_deploy: "Delay first deploy",
  skip_harvest_zone: "Skip harvest zone",
  extend_override: "Extend Override Mode",
};

export function WhatIfDiff({ result, onDismiss }: Props) {
  const { request, original, perturbed, note } = result;

  // Pair original & perturbed by zone_id. The endpoint guarantees the same
  // zones appear in both lists (perturbations don't add or drop zones), so
  // we can zip them via a map. If a zone surfaces only in the perturbed
  // list (theoretical — re-detection after perturbation), the renderer
  // labels it "newly detected" rather than "before/after."
  const byZoneOriginal = new Map(original.map((r) => [r.zone.zone_id, r]));
  const pairs: Array<{
    zoneId: string;
    before: Recommendation | null;
    after: Recommendation;
  }> = perturbed.map((after) => ({
    zoneId: after.zone.zone_id,
    before: byZoneOriginal.get(after.zone.zone_id) ?? null,
    after,
  }));

  return (
    <section
      className="rounded-card border border-accent/30 bg-surface/60 p-4 shadow-card"
      data-testid="whatif-diff"
    >
      <header className="flex items-center justify-between mb-4">
        <div className="flex items-baseline gap-2 flex-wrap">
          <span className="text-[11px] uppercase tracking-wider text-accent font-mono">
            What-if scenario
          </span>
          <h3 className="text-sm font-semibold text-text">
            {PERTURBATION_LABEL[request.perturbation]}
          </h3>
          <span className="text-xs text-muted font-mono">
            {_describeRequest(request)}
          </span>
        </div>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            className="text-xs text-muted hover:text-text px-2 py-1 rounded-md hover:bg-surface-2 transition-colors"
            aria-label="Close what-if comparison"
          >
            ✕ close
          </button>
        )}
      </header>

      {note && (
        <div className="mb-4 text-xs text-warning italic px-3 py-2 rounded-md bg-warning/5 border border-warning/20">
          {note}
        </div>
      )}

      <div className="space-y-4">
        {pairs.map(({ zoneId, before, after }) => (
          <DiffPair key={zoneId} before={before} after={after} />
        ))}
      </div>
    </section>
  );
}


// ──────────────────────────────────────────────────────────────────────────────
// One Before/After pair — two compact mini-cards side-by-side
// ──────────────────────────────────────────────────────────────────────────────

function DiffPair({
  before,
  after,
}: {
  before: Recommendation | null;
  after: Recommendation;
}) {
  if (!before) {
    return (
      <div className="rounded-md border border-accent/30 bg-surface p-3 text-xs">
        <div className="text-[10px] uppercase tracking-wider text-accent mb-1">
          Newly detected
        </div>
        <MiniCard rec={after} dimmed={false} />
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      <div className="rounded-md border border-border bg-surface p-3">
        <div className="text-[10px] uppercase tracking-wider text-muted mb-2 flex items-center gap-2">
          <span>Before</span>
          <span aria-hidden="true">·</span>
          <span className="font-mono">{before.zone.zone_id}</span>
        </div>
        <MiniCard rec={before} dimmed />
      </div>
      <div className="rounded-md border border-accent/40 bg-surface p-3">
        <div className="text-[10px] uppercase tracking-wider text-accent mb-2 flex items-center gap-2">
          <span>After</span>
          <span aria-hidden="true">·</span>
          <span className="font-mono">{after.zone.zone_id}</span>
        </div>
        <MiniCard rec={after} dimmed={false} highlightVs={before} />
      </div>
    </div>
  );
}


// ──────────────────────────────────────────────────────────────────────────────
// MiniCard — compact recommendation summary with metric deltas highlighted
// ──────────────────────────────────────────────────────────────────────────────

function MiniCard({
  rec,
  dimmed,
  highlightVs,
}: {
  rec: Recommendation;
  dimmed: boolean;
  highlightVs?: Recommendation;
}) {
  const metrics = rec.zone.metrics;
  const compare = highlightVs?.zone.metrics ?? {};

  return (
    <div className={dimmed ? "opacity-70" : ""}>
      <header className="flex items-center justify-between gap-2 mb-2 flex-wrap">
        <span className="font-mono text-xs text-muted">
          L{rec.zone.lap_number} · S{rec.zone.sector}
        </span>
        <div className="flex gap-1">
          <BadgeChip tone={severityTone(rec.zone.severity)}>
            {rec.zone.severity}
          </BadgeChip>
          <BadgeChip tone={confidenceTone(rec.reasoning.confidence)}>
            {rec.reasoning.confidence}
          </BadgeChip>
        </div>
      </header>

      <div className="text-xs text-text mb-2 leading-snug">
        {rec.zone.description}
      </div>

      <dl className="grid grid-cols-3 gap-2 mb-2 font-mono text-xs">
        <MetricDelta
          label="harvest"
          value={metrics.harvest_mj}
          baseline={compare.harvest_mj}
          unit="MJ"
        />
        <MetricDelta
          label="deploy"
          value={metrics.deploy_mj}
          baseline={compare.deploy_mj}
          unit="MJ"
        />
        <MetricDelta
          label="ROI"
          value={metrics.roi_mj_per_s}
          baseline={compare.roi_mj_per_s}
          unit=""
        />
      </dl>

      <div className="flex gap-1 flex-wrap text-[10px]">
        <BadgeChip tone={rec.validator?.passed ? "success" : "danger"}>
          P1 {rec.validator?.passed ? "✓" : "✗"}
        </BadgeChip>
        <BadgeChip tone={rec.guardian?.passed ? "success" : "danger"}>
          P2 {rec.guardian?.passed ? "✓" : "✗"}
        </BadgeChip>
      </div>
    </div>
  );
}


function MetricDelta({
  label,
  value,
  baseline,
  unit,
}: {
  label: string;
  value: number | undefined;
  baseline: number | undefined;
  unit: string;
}) {
  if (value === undefined) {
    return (
      <div>
        <div className="text-[10px] text-muted">{label}</div>
        <div className="text-muted">—</div>
      </div>
    );
  }
  let toneClass = "text-text";
  let arrow: string | null = null;
  if (baseline !== undefined && Math.abs(value - baseline) > 0.005) {
    if (value > baseline) {
      toneClass = "text-danger";
      arrow = "↑";
    } else {
      toneClass = "text-success";
      arrow = "↓";
    }
  }
  return (
    <div>
      <div className="text-[10px] text-muted">{label}</div>
      <div className={`${toneClass} flex items-baseline gap-1`}>
        <span>{value.toFixed(2)}</span>
        {unit && <span className="text-[10px] text-muted">{unit}</span>}
        {arrow && <span className="text-[10px]">{arrow}</span>}
      </div>
    </div>
  );
}


function _describeRequest(req: WhatIfRequest): string {
  switch (req.perturbation) {
    case "delay_first_deploy":
      return `n=${req.n ?? 1}`;
    case "skip_harvest_zone":
      return req.zone_id ?? "";
    case "extend_override":
      return `${req.zone_id ?? ""} · +${req.extra_laps ?? 1} lap${(req.extra_laps ?? 1) > 1 ? "s" : ""}`;
  }
}
