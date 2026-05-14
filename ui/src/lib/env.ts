/**
 * Environment / deployment detection helpers.
 *
 * `isLocalHost` is the UX-side guard for surfaces that only make sense
 * during local development — TORCS Race Control + the /cockpit noVNC
 * iframe, per ADR-004 §security ("the control plane is intentionally
 * NOT exposed publicly"). It is **not** a security boundary — the
 * server-side API still refuses with 503 CONTROL_DISABLED when
 * TORCS_CONTROL_SECRET is unset.
 */

export function isLocalHost(): boolean {
  if (typeof window === "undefined") return false;
  const h = window.location.hostname;
  return h === "localhost" || h === "127.0.0.1" || h === "::1";
}
