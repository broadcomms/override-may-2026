/**
 * Single-purpose drop+browse affordance for the Upload page.
 *
 * Entry-page upload affordance after the Phase A UI refresh.
 * this component is deliberately *secondary*: the hero on /upload is the
 * sample-replay list. Hierarchy here is solid 1px border, no glyph, single
 * line — the dropzone reads as "bring your own", not "upload to begin".
 *
 * Sample-replay rendering previously lived here. It now lives in
 * SampleReplayList so each surface owns one job.
 */

import { useCallback, useRef, useState } from "react";

interface Props {
  onFile: (file: File) => void;
  isUploading: boolean;
  error?: string | null;
}

export function FileUpload({ onFile, isUploading, error }: Props) {
  const [hovering, setHovering] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(
    (file: File | undefined) => {
      if (!file) return;
      onFile(file);
    },
    [onFile],
  );

  return (
    <div className="w-full">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setHovering(true);
        }}
        onDragLeave={() => setHovering(false)}
        onDrop={(e) => {
          e.preventDefault();
          setHovering(false);
          handleFile(e.dataTransfer.files?.[0]);
        }}
        onClick={() => inputRef.current?.click()}
        className={`rounded-card border p-6 text-center cursor-pointer transition-colors ${
          hovering
            ? "border-accent/60 bg-accent/[0.03]"
            : "border-border bg-surface hover:bg-surface-2"
        }`}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
      >
        {isUploading ? (
          <div className="space-y-2">
            <div className="text-text">Parsing session…</div>
            <div className="h-1 w-full bg-surface-2 overflow-hidden rounded-full">
              <div className="h-full w-1/3 bg-accent animate-pulse" />
            </div>
            <div className="text-xs text-muted">
              Reasoning over zones · running safety review · this can take ~30 s
            </div>
          </div>
        ) : (
          <div className="text-sm text-text">
            Drop in a replay session, or click to browse<br></br> <span className="font-mono text-muted">Supports TORCS .json</span>{" "}
            <span className="text-muted">/</span>{" "}
            <span className="font-mono text-muted">FastF1 .parquet</span><br></br>
            <span className="text-muted"> Upload to 25 MB</span>
          </div>
        )}
        <input
          ref={inputRef}
          type="file"
          accept=".json,.parquet"
          className="hidden"
          onChange={(e) => handleFile(e.target.files?.[0] ?? undefined)}
        />
      </div>

      {error && (
        <div
          role="alert"
          className="mt-3 px-3 py-2 rounded-md bg-danger/15 border border-danger/40 text-sm text-danger"
        >
          {error}
        </div>
      )}
    </div>
  );
}
