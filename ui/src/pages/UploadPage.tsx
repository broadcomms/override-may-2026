/**
 * Upload page — drop zone + sample replays per docs/04-ui-ux-design.md §4.1.
 * Posts to FastAPI /api/sessions, navigates to the session detail page.
 */

import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

import { OverrideApiError, api } from "@/api/client";
import { FileUpload } from "@/components/FileUpload";

export function UploadPage() {
  const navigate = useNavigate();
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onFile = useCallback(
    async (file: File) => {
      setIsUploading(true);
      setError(null);
      try {
        const session = await api.createSession({
          file,
          source: file.name.endsWith(".parquet") ? "fastf1" : "torx",
          socMax: 4.0,
        });
        navigate(`/session/${session.summary.session_id}`);
      } catch (e) {
        const msg =
          e instanceof OverrideApiError
            ? `${e.payload.message}${e.payload.detail ? ` — ${e.payload.detail}` : ""}`
            : e instanceof Error
            ? e.message
            : "Upload failed.";
        setError(msg);
      } finally {
        setIsUploading(false);
      }
    },
    [navigate],
  );

  const useSample = useCallback(async () => {
    // The fixture path returns a valid Session synthesized from
    // tests/fixtures/layered_defense_demo.json — see api/client.ts.
    setIsUploading(true);
    setError(null);
    try {
      const session = await api.createSession(
        {
          file: new File([], "sample.json", { type: "application/json" }),
          source: "fastf1",
          socMax: 4.0,
        },
        { fixture: true },
      );
      navigate(`/session/${session.summary.session_id}?fixture=1`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load sample.");
    } finally {
      setIsUploading(false);
    }
  }, [navigate]);

  return (
    <div className="flex flex-col items-center pt-16 px-6">
      <h1 className="text-3xl font-semibold mb-2">Drop a session replay to begin</h1>
      <p className="text-muted text-sm mb-8">
        OVERRIDE will detect inefficient zones, reason over them, and ground every recommendation in the 2026 F1 regulations.
      </p>
      <FileUpload
        onFile={onFile}
        isUploading={isUploading}
        error={error}
        sampleReplays={[
          { label: "Layered-defense demo (cached)", onClick: useSample },
        ]}
      />
    </div>
  );
}
