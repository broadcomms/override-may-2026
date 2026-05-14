/**
 * ConfirmDialog — minimal accessible modal for destructive actions.
 *
 * Phase 4 ship for session management (delete single / bulk / live run).
 * Kept intentionally small: no portal, no animation, no focus-trap lib —
 * just an absolutely-positioned overlay with role="dialog", inert backdrop
 * dismissal, Escape-to-cancel, and an optional checkbox for the "also
 * delete source JSONL" opt-in case.
 *
 * Why not window.confirm:
 * - We need a checkbox (remove-telemetry opt-in) — confirm() can't do
 *   structured content.
 * - confirm() is blocked by some browser settings.
 * - Styling matches the rest of the app instead of OS-native chrome.
 */

import { useEffect, useRef } from "react";

interface ConfirmOption {
  /** Stable key for the option (used in onChange). */
  key: string;
  /** Visible label. */
  label: string;
  /** Optional helper text rendered below the label. */
  description?: string;
  /** Controlled value of the checkbox. */
  checked: boolean;
  /** Callback when toggled. */
  onChange: (next: boolean) => void;
}

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  /** Body content. Use a string for one line, ReactNode for richer copy. */
  body: React.ReactNode;
  /** Optional opt-in checkboxes shown above the buttons. */
  options?: ConfirmOption[];
  confirmLabel?: string;
  cancelLabel?: string;
  /** Style of confirm button. "danger" colors it red (destructive). */
  confirmVariant?: "default" | "danger";
  /** Disables both buttons (used while the action is in flight). */
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  body,
  options,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  confirmVariant = "default",
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDivElement | null>(null);

  // Escape-to-cancel + autofocus the dialog when it opens.
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onCancel();
    };
    window.addEventListener("keydown", handler);
    dialogRef.current?.focus();
    return () => window.removeEventListener("keydown", handler);
  }, [open, busy, onCancel]);

  if (!open) return null;

  const confirmClass =
    confirmVariant === "danger"
      ? "bg-danger text-white hover:bg-danger/90"
      : "bg-accent text-bg hover:opacity-90";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={busy ? undefined : onCancel}
      role="presentation"
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        tabIndex={-1}
        className="w-full max-w-md mx-4 rounded-card border border-border bg-surface p-5 shadow-xl outline-none"
        onClick={(e) => e.stopPropagation()}
      >
        <h2
          id="confirm-dialog-title"
          className="text-lg font-semibold mb-2"
        >
          {title}
        </h2>
        <div className="text-sm text-muted mb-4">{body}</div>

        {options && options.length > 0 && (
          <div className="space-y-2 mb-5">
            {options.map((opt) => (
              <label
                key={opt.key}
                className="flex items-start gap-2 cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={opt.checked}
                  disabled={busy}
                  onChange={(e) => opt.onChange(e.target.checked)}
                  className="mt-0.5 cursor-pointer"
                />
                <span className="text-sm">
                  <span className="text-text">{opt.label}</span>
                  {opt.description && (
                    <span className="block text-xs text-muted">
                      {opt.description}
                    </span>
                  )}
                </span>
              </label>
            ))}
          </div>
        )}

        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="px-3 py-1.5 rounded-pill border border-border bg-surface-2 text-sm hover:bg-surface disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={`px-3 py-1.5 rounded-pill text-sm font-medium disabled:opacity-50 ${confirmClass}`}
          >
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
