/**
 * Drag-drop upload zone per docs/04-ui-ux-design.md §4.1.
 * States: idle / hovering / uploading / error.
 */

import { useCallback, useRef, useState } from "react";

interface Props {
  onFile: (file: File) => void;
  isUploading: boolean;
  error?: string | null;
  /** When true, surfaces a "use sample replay" affordance per §4.1. */
  sampleReplays?: { label: string; onClick: () => void }[];
}

export function FileUpload({ onFile, isUploading, error, sampleReplays }: Props) {
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
    <div className="w-full max-w-xl">
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
        className={`rounded-card border-2 border-dashed p-12 text-center cursor-pointer transition-colors ${
          hovering ? "border-accent bg-accent/5" : "border-border bg-surface hover:bg-surface-2"
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
          <>
            <div className="text-2xl mb-2">⤓</div>
            <div className="text-text mb-1">
              Drop a <span className="font-mono">.json</span> or <span className="font-mono">.parquet</span> file, or click to browse
            </div>
            <div className="text-xs text-muted">
              Supported: TORCS, FastF1 — max 25 MB, up to 120 laps
            </div>
          </>
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

      {sampleReplays && sampleReplays.length > 0 && (
        <div className="mt-4">
          <div className="text-xs uppercase tracking-wider text-muted mb-2">Or try a sample replay</div>
          <div className="flex flex-wrap gap-2">
            {sampleReplays.map((s) => (
              <button
                key={s.label}
                type="button"
                onClick={s.onClick}
                disabled={isUploading}
                className="px-3 py-1.5 rounded-pill border border-border bg-surface text-sm hover:bg-surface-2 disabled:opacity-50"
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
