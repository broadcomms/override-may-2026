/**
 * PreviewStrip — entry-page peek at the destination (Phase D D1).
 *
 * Phase D preview-strip implementation. Renders the EnergyCurve + first
 * RecommendationCard from the architect-selected cached
 * `torcs_engineer_demo` fixture below the two-pane Begin/Live grid
 * on /upload. M2 wins over the audit's original layered_defense suggestion
 * — entry-page preview shows the optimistic case; layered-defense stays
 * available in the SampleReplayList as a Pass-2-rejection learning option.
 *
 * Progressive enhancement: silent on fixture-fetch failure. The fixture
 * path is in-process and synchronous (no network), so the fetch never
 * realistically fails — but the silent fallback keeps the entry page from
 * blocking on a UI dev-time regression.
 */

import { useEffect, useState } from "react";

import { api } from "@/api/client";
import type { Session } from "@/api/types";
import { EnergyCurve } from "./EnergyCurve";
import { RecommendationCard } from "./RecommendationCard";

export function PreviewStrip() {
  const [session, setSession] = useState<Session | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getSession("s_torcs_engineer_demo", {
        fixture: true,
        fixtureName: "torcs_engineer",
      })
      .then((s) => {
        if (!cancelled) setSession(s);
      })
      .catch(() => {
        /* silent — progressive enhancement */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!session) return null;
  const firstRec = session.recommendations[0];
  if (!firstRec) return null;

  return (
    <section
      aria-labelledby="preview-heading"
      className="mt-10 pt-6 border-t border-border"
    >
      <h2
        id="preview-heading"
        className="text-[11px] uppercase tracking-wider text-muted font-mono mb-2"
      >
        What you'll see
      </h2>
      <p className="text-sm text-muted mb-5">
        A real debrief from the cached TORCS engineer fixture, citation grounded, validated, and ready to explore.
      </p>
      <div className="grid items-start lg:grid-cols-2 gap-6">
        <EnergyCurve
          laps={session.laps}
          forecast={session.forecast}
          recommendations={session.recommendations}
        />
        <RecommendationCard
          recommendation={firstRec}
          mode="engineer"
          hideWhatIf
        />
      </div>
    </section>
  );
}
