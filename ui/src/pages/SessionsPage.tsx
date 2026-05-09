/**
 * Session list page — minimal stub for P3.2.
 * The list endpoint is Tier-2 (deferred per the API review), so for P3.2
 * this page just shows the empty state and points the user back to /upload.
 */

import { Link } from "react-router-dom";

import { EmptyState } from "@/components/EmptyStates";

export function SessionsPage() {
  return (
    <div className="px-6 py-12">
      <h1 className="text-2xl font-semibold mb-6">Sessions</h1>
      <EmptyState
        icon="↻"
        title="Session history view coming soon"
        body="The list endpoint ships in API Tier 2. For now, drop a replay on the upload page to start a fresh debrief."
        cta={
          <Link
            to="/upload"
            className="inline-block px-3 py-1.5 rounded-pill bg-accent text-bg text-sm font-medium hover:opacity-90"
          >
            Go to upload
          </Link>
        }
      />
    </div>
  );
}
