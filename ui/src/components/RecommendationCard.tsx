/**
 * Engineer-Mode recommendation card (Phase C C4).
 *
 * Structural changes from P3.3 (per docs/plans/ui-design-audit-2026-05-14.md §9.4):
 *   - Headline-led: `reasoning.recommendation` is the h3 at top; metadata
 *     becomes the sub-line below.
 *   - Citation in a 30%-width right rail at `md` and up (CSS grid); stacks
 *     below on narrow.
 *   - Sticky footer for validator/guardian/confidence badges — they stay
 *     visible while the card is in view, even when the reasoning chain or
 *     WhatIfRail are expanded.
 *
 * Two failure modes get explicit visual treatment (unchanged):
 *   - Validator failed terminally → §7 row 4 ValidatorFailedPanel replaces
 *     the headline + grid (the recommendation was rejected; promoting it as
 *     a headline would mis-state confidence).
 *   - Pass-2 Guardian shipped with `final_confidence='low'` → small banner
 *     ("Treat as exploratory") per §7 row 3.
 *
 * WhatIfRail is preserved verbatim per docs/plans/seg3-recording-handoff.md —
 * disclosure → radios → Run ▶ click choreography unchanged. Visual position
 * sits above the sticky footer so its expansion doesn't get overlaid.
 *
 * Fan card variant lives in the same file — `mode='fan'` with a fan output.
 */

import { useId, useState } from "react";

import type { FanOutput, Recommendation } from "@/api/types";
import { BadgeChip, confidenceTone, severityTone } from "./BadgeChip";

interface Props {
  recommendation: Recommendation;
  fan?: FanOutput | null;
  mode?: "engineer" | "fan";
  /** When true and `mode==="fan"` and `fan` is null, render the Fan skeleton. */
  fanLoading?: boolean;
  /** When set and `mode==="fan"` and `fan` is null and we're not loading,
   *  render this as the fallback message inside the Engineer card.
   *  Per FR-7: if Fan translation fails, stay on Engineer view. */
  fanError?: string | null;
  onWhatIf?: (parameter: WhatIfParameter) => void;
}

export type WhatIfParameter =
  | "delay_first_deploy"
  | "skip_harvest_zone"
  | "extend_override";

export function RecommendationCard({
  recommendation,
  fan,
  mode = "engineer",
  fanLoading,
  fanError,
  onWhatIf,
}: Props) {
  const showFan = mode === "fan" && fan;
  const showFanSkeleton = mode === "fan" && !fan && fanLoading;
  return (
    <div
      className="transition-opacity duration-[var(--motion-mode)] ease-out"
      data-mode={mode}
    >
      {showFan ? (
        <FanCard rec={recommendation} fan={fan} />
      ) : showFanSkeleton ? (
        <FanCardSkeleton />
      ) : (
        <EngineerCard
          rec={recommendation}
          onWhatIf={onWhatIf}
          fanError={mode === "fan" ? fanError : null}
        />
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// Engineer card
// ──────────────────────────────────────────────────────────────────────────────

function EngineerCard({
  rec,
  onWhatIf,
  fanError,
}: {
  rec: Recommendation;
  onWhatIf?: (parameter: WhatIfParameter) => void;
  fanError?: string | null;
}) {
  const { zone, reasoning, validator, guardian } = rec;

  const validatorFailedTerminally =
    !validator.passed && validator.retry_count >= 2;
  const guardianShippedLowConfidence =
    !guardian.passed && guardian.final_confidence === "low";

  const ringClass = validatorFailedTerminally
    ? "ring-1 ring-danger/40"
    : guardianShippedLowConfidence
    ? "ring-1 ring-warning/40"
    : "";

  return (
    <article
      data-zone-id={zone.zone_id}
      className={`group relative rounded-card bg-surface border border-border shadow-card scroll-mt-20 transition-[transform,box-shadow,border-color] duration-[var(--motion-card)] ease-snap-out hover:-translate-y-0.5 hover:shadow-card-hover hover:border-border/70 focus-within:border-accent/50 ${ringClass}`}
    >
      <div className="p-5 pb-3">
        {fanError && (
          <div
            role="alert"
            className="mb-4 p-2 rounded-md border border-warning/40 bg-warning/10 text-xs text-text"
          >
            <span className="font-medium text-warning">Fan translation unavailable</span> — showing Engineer view. {fanError}
          </div>
        )}

        {validatorFailedTerminally ? (
          <>
            <header className="flex items-center justify-between gap-3 mb-4">
              <div className="flex items-baseline gap-2 flex-wrap">
                <span className="font-mono text-sm text-muted">L{zone.lap_number}</span>
                <span className="text-muted">·</span>
                <span className="font-mono text-sm text-muted">S{zone.sector}</span>
                <span className="text-muted">·</span>
                <code className="text-xs px-1.5 py-0.5 rounded bg-surface-2 text-text">{zone.zone_type}</code>
              </div>
              <BadgeChip tone={severityTone(zone.severity)}>{zone.severity} severity</BadgeChip>
            </header>
            <ValidatorFailedPanel rec={rec} />
          </>
        ) : (
          <>
            {/* Headline-led: the Granite single-sentence recommendation is
                promoted to h3. Metadata moves to the sub-line. */}
            <h3 className="text-base font-semibold text-text leading-snug mb-2">
              {reasoning.recommendation}
            </h3>
            <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
              <div className="flex items-baseline gap-2 flex-wrap text-xs">
                <span className="font-mono text-muted">L{zone.lap_number}</span>
                <span className="text-muted">·</span>
                <span className="font-mono text-muted">S{zone.sector}</span>
                <span className="text-muted">·</span>
                <code className="px-1.5 py-0.5 rounded bg-surface-2 text-text">{zone.zone_type}</code>
              </div>
              <BadgeChip tone={severityTone(zone.severity)}>{zone.severity} severity</BadgeChip>
            </div>

            {/* Two-column grid at md+ — cause/consequence/chain on the left,
                citation in the right rail. Stacks below on narrow. */}
            <div className="md:grid md:grid-cols-[1fr_minmax(0,30%)] md:gap-5">
              <div className="space-y-3 mb-4 md:mb-0">
                <Field label="Cause">{reasoning.cause}</Field>
                <Field label="Consequence">{reasoning.consequence}</Field>
                <CollapsibleReasoningChain steps={reasoning.reasoning_chain} />
              </div>
              <div>
                <Citation rec={rec} />
              </div>
            </div>

            {guardianShippedLowConfidence && (
              <LowConfidenceBanner rec={rec} />
            )}
          </>
        )}

        <WhatIfRail
          zoneId={zone.zone_id}
          onRun={onWhatIf}
          disabled={!onWhatIf}
        />
      </div>

      {/* Sticky footer — badges remain visible while the card is in view.
          Negative-mx + matching padding keeps the bar full-width inside the
          rounded card. mt-auto isn't needed because the article isn't a
          flex column; the bar simply renders at the bottom of normal flow,
          then sticks to viewport bottom while the card is in view. */}
      <footer className="sticky bottom-0 px-5 py-3 bg-surface border-t border-border rounded-b-card flex flex-wrap items-center gap-2 z-[1]">
        <ValidatorBadge validator={validator} />
        <GuardianBadge guardian={guardian} />
        <BadgeChip tone={confidenceTone(guardian.final_confidence)}>
          Confidence: {guardian.final_confidence}
        </BadgeChip>
      </footer>
    </article>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// Sub-components
// ──────────────────────────────────────────────────────────────────────────────

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-muted mb-1.5">{label}</div>
      <div className="text-sm leading-[1.55] text-text/95">{children}</div>
    </div>
  );
}

function CollapsibleReasoningChain({ steps }: { steps: string[] }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div className="border-t border-border/60 pt-3 mt-3">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={id}
        className="text-sm text-muted hover:text-text transition-colors flex items-center gap-1"
      >
        <span className={`transition-transform ${open ? "rotate-90" : ""}`}>▸</span>
        Reasoning chain ({steps.length} steps)
      </button>
      <div
        id={id}
        className={`grid transition-all duration-200 ease-out ${
          open ? "grid-rows-[1fr] opacity-100 mt-2" : "grid-rows-[0fr] opacity-0"
        }`}
      >
        <ol
          className="overflow-hidden ml-5 list-decimal space-y-1 text-sm text-muted [&>li]:marker:text-text/50"
        >
          {steps.map((step, i) => (
            <li key={i}>{step}</li>
          ))}
        </ol>
      </div>
    </div>
  );
}

/**
 * §6 hard rule lives here in code form. Section is rendered from
 * `regulation_citation.source.section`, never as a literal string.
 */
function Citation({ rec }: { rec: Recommendation }) {
  const cit = rec.reasoning.regulation_citation;
  if (!cit) {
    return (
      <div className="p-3 rounded-md border border-dashed border-border text-xs text-muted h-full">
        No regulation citation for this zone — confidence is low and reasoning is from observed data alone.
      </div>
    );
  }
  return (
    <div className="pl-3 pr-3 py-3 rounded-md border border-granite/40 bg-granite/10 border-l-[3px] border-l-granite h-full">
      <div className="text-[11px] uppercase tracking-wider text-muted mb-1.5 flex items-center gap-1.5">
        <span aria-hidden="true">¶</span>
        <span>Citation — verbatim</span>
      </div>
      <blockquote className="text-sm italic text-text mb-2 leading-[1.55]">
        &ldquo;{cit.passage}&rdquo;
      </blockquote>
      <div className="text-xs font-mono text-muted flex flex-wrap items-center gap-1.5">
        <span>{cit.source.document_title}</span>
        <span aria-hidden="true">·</span>
        <span>{cit.source.issue}</span>
        <span aria-hidden="true">·</span>
        <span className="text-text font-medium">§ {cit.source.section}</span>
        <a
          href={cit.source.public_url}
          target="_blank"
          rel="noreferrer"
          className="ml-auto text-accent hover:underline transition-colors"
          title="Open the FIA regulation source"
        >
          open ↗
        </a>
      </div>
    </div>
  );
}

function ValidatorBadge({ validator }: { validator: Recommendation["validator"] }) {
  if (validator.passed) {
    return (
      <BadgeChip tone="success" title="All Pass-1 rules cleared">
        ✓ Validation
      </BadgeChip>
    );
  }
  return (
    <BadgeChip
      tone="danger"
      title={`Pass-1 failed rules:\n${validator.failed_rules.map((r) => `• ${r}`).join("\n")}`}
    >
      ✗ Validation: {validator.failed_rules.length} rule
      {validator.failed_rules.length === 1 ? "" : "s"}
    </BadgeChip>
  );
}

function GuardianBadge({ guardian }: { guardian: Recommendation["guardian"] }) {
  const scores = Object.values(guardian.scores);
  const lo = scores.length ? Math.min(...scores) : 0;
  const tone = guardian.passed ? "granite" : "danger";
  const title = Object.entries(guardian.scores)
    .map(([k, v]) => `${k}: ${v.toFixed(2)} — ${guardian.rationales[k] ?? ""}`)
    .join("\n\n");
  return (
    <BadgeChip tone={tone} title={title}>
      AI Safety Review: {lo.toFixed(2)} / 1.00
    </BadgeChip>
  );
}

// §7 row 3 — Pass-2 retries exhausted, shipped with final_confidence='low'
function LowConfidenceBanner({ rec }: { rec: Recommendation }) {
  const sorted = Object.entries(rec.guardian.scores).sort((a, b) => a[1] - b[1]);
  const [lowestKey, lowestScore] = sorted[0] ?? ["unknown", 0];
  const rationale = rec.guardian.rationales[lowestKey];
  return (
    <div className="mt-4 p-3 rounded-md border border-warning/40 bg-warning/10 text-xs">
      <div className="font-medium text-warning mb-1">Treat as exploratory</div>
      <div className="text-text">
        This recommendation passed Pass-1 validation but did not meet the AI safety threshold after retries.
        Lowest score:{" "}
        <span className="font-mono">
          {lowestKey} = {lowestScore.toFixed(2)}
        </span>
        {rationale && <> — <span className="italic">{rationale}</span></>}
      </div>
    </div>
  );
}

// §7 row 4 — Pass-1 retries exhausted, validator hit-and-stuck
function ValidatorFailedPanel({ rec }: { rec: Recommendation }) {
  return (
    <div className="rounded-md border border-danger/40 bg-danger/10 p-3 mb-3">
      <div className="text-[11px] uppercase tracking-wider text-danger mb-2">
        Validator did not pass after {rec.validator.retry_count} retries
      </div>
      <div className="text-sm mb-2">
        The reasoning is suppressed for this zone — the system caught itself before
        shipping a malformed recommendation.
      </div>
      <ul className="text-xs font-mono text-muted space-y-0.5">
        {rec.validator.failed_rules.map((rule) => (
          <li key={rule}>
            <span className="text-danger">✗</span> {rule}
            {(() => {
              const note = rec.validator.notes.find((n) => n.startsWith(`${rule}:`));
              if (!note) return null;
              return <span className="ml-2 text-muted/80">{note.slice(rule.length + 1).trim()}</span>;
            })()}
          </li>
        ))}
      </ul>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// What-if rail (FR-8.3: Engineer-mode only; disabled in Fan mode)
// Per docs/plans/seg3-recording-handoff.md, the disclosure → radio → Run ▶
// click choreography is video-recording load-bearing. Preserve the
// functional path verbatim — visual placement may change with the card but
// the affordances stay.
// ──────────────────────────────────────────────────────────────────────────────

function WhatIfRail({
  zoneId,
  onRun,
  disabled,
}: {
  zoneId: string;
  onRun?: (parameter: WhatIfParameter) => void;
  disabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [param, setParam] = useState<WhatIfParameter>("delay_first_deploy");
  const titleAttr = disabled
    ? "What-if is available in Engineer mode"
    : "Run a what-if perturbation against this zone";

  return (
    <div className="mt-4 border-t border-border/60 pt-3">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="text-sm text-muted hover:text-text transition-colors flex items-center gap-1"
      >
        <span className={`transition-transform ${open ? "rotate-90" : ""}`}>▸</span>
        What if…
        {disabled && (
          <span className="ml-2 text-[10px] uppercase tracking-wider text-muted">
            Engineer mode only
          </span>
        )}
      </button>
      {open && (
        <fieldset
          disabled={disabled}
          title={titleAttr}
          className="mt-2 space-y-1 text-sm disabled:opacity-50"
        >
          {(["delay_first_deploy", "skip_harvest_zone", "extend_override"] as const).map((p) => (
            <label key={p} className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name={`whatif-${zoneId}`}
                value={p}
                checked={param === p}
                onChange={() => setParam(p)}
                className="accent-accent"
              />
              <span className="font-mono text-xs">{p.replace(/_/g, " ")}</span>
            </label>
          ))}
          <div className="pt-1">
            <button
              type="button"
              onClick={() => onRun?.(param)}
              disabled={disabled}
              className="px-3 py-1 rounded-pill bg-accent text-bg text-xs font-medium disabled:cursor-not-allowed"
            >
              Run ▶
            </button>
          </div>
        </fieldset>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────────
// Fan card variant
// ──────────────────────────────────────────────────────────────────────────────

function FanCard({ rec, fan }: { rec: Recommendation; fan: FanOutput }) {
  return (
    <article
      data-zone-id={rec.zone.zone_id}
      className="rounded-card bg-surface border border-border p-5 shadow-card scroll-mt-20 transition-[transform,box-shadow,border-color] duration-[var(--motion-card)] ease-snap-out hover:-translate-y-0.5 hover:shadow-card-hover hover:border-border/70"
    >
      <header className="mb-3 flex items-baseline justify-between">
        <span className="font-mono text-sm text-muted">Lap {rec.zone.lap_number}</span>
      </header>
      <h3 className="text-lg font-semibold mb-3 text-text leading-snug">{fan.headline}</h3>
      <div className="space-y-3">
        <Field label="What happened">{fan.what_happened}</Field>
        <Field label="Why it mattered">{fan.why_it_mattered}</Field>
        {fan.the_rule && <Field label="The rule">{fan.the_rule}</Field>}
      </div>
    </article>
  );
}

/** Skeleton matching the FanCard silhouette — shown while Fan Mode
 *  translation is in flight. Layout mirrors FanCard so the cross-fade
 *  doesn't reflow the page. */
function FanCardSkeleton() {
  return (
    <article
      role="status"
      aria-label="Translating to Fan Mode"
      className="rounded-card bg-surface border border-border p-5 shadow-sm"
    >
      <div className="mb-3 h-3 w-16 rounded bg-surface-2 animate-shimmer bg-gradient-to-r from-surface-2 via-border to-surface-2 bg-[length:200%_100%]" />
      <div className="mb-4 h-5 w-3/4 rounded bg-surface-2 animate-shimmer bg-gradient-to-r from-surface-2 via-border to-surface-2 bg-[length:200%_100%]" />
      <div className="space-y-3">
        {[88, 72, 64].map((w) => (
          <div key={w}>
            <div className="mb-1 h-2 w-20 rounded bg-surface-2" />
            <div
              className="h-3 rounded bg-surface-2 animate-shimmer bg-gradient-to-r from-surface-2 via-border to-surface-2 bg-[length:200%_100%]"
              style={{ width: `${w}%` }}
            />
          </div>
        ))}
      </div>
      <span className="sr-only">Translating to Fan Mode…</span>
    </article>
  );
}
