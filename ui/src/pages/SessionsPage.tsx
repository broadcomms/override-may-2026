/**
 * Session list page — v1.1 framing.
 *
 * The list endpoint (`GET /api/sessions`) is explicitly deferred to v1.1 per
 * `docs/04-api.md` §"Tier 2" (the `list_sessions` helper exists in
 * `api/storage.py` but is intentionally not wired to an HTTP route in v1.0).
 * Same v1.1 framing pattern used by:
 *   - TTM-R2 deferral banner in `EnergyCurve.tsx`
 *   - v1.1 row in `docs/02-ai-and-technical-approach.md` §"Five IBM technologies"
 *   - FR-3 deferral note in `docs/03-prd.md`
 *
 * The page is reachable from the main nav; rather than "Coming soon"
 * (which reads as polish slipping), the v1.1 framing makes the deferral
 * intentional + names the migration target.
 */

import { Link } from "react-router-dom";

import { EmptyState } from "@/components/EmptyStates";

export function SessionsPage() {
  return (
    <div className="px-6 py-12">
      <h1 className="text-2xl font-semibold mb-6">Sessions</h1>
      <EmptyState
        icon="↻"
        title="Session history view — v1.1"
        body={
          "v1.0 ships single-session-at-a-time: drop a replay on /upload, get a debrief, deep-link the session URL. The list endpoint and history view are in the v1.1 roadmap. The storage layer already keeps every session under data/sessions/{id}/ — v1.1 wires the GET /api/sessions index endpoint, paginated, and a real list view here."
        }
        cta={
          <Link
            to="/upload"
            className="inline-block px-3 py-1.5 rounded-pill bg-accent text-bg text-sm font-medium hover:opacity-90"
          >
            Drop a replay on /upload
          </Link>
        }
      />
    </div>
  );
}
