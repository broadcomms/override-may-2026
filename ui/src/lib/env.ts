/**
 * Environment / deployment detection helpers.
 *
 * The OVERRIDE app can drive TORCS in two deployment shapes:
 *
 * - local dev: noVNC lives at http://localhost:6080
 * - tunneled demo: OVERRIDE is on one hostname and noVNC is exposed on a
 *   sibling TORCS hostname (for example override.* -> torcs-run.*)
 *
 * These helpers decide whether the frontend should render the live TORCS
 * surfaces and, when it does, where the noVNC iframe should point.
 */

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "::1"]);

function currentHostname(): string | null {
  if (typeof window === "undefined") return null;
  return window.location.hostname;
}

export function isLocalHost(): boolean {
  const hostname = currentHostname();
  return hostname !== null && LOCAL_HOSTS.has(hostname);
}

function configuredTorcsRunOrigin(): string | null {
  const raw = import.meta.env.VITE_TORCS_RUN_ORIGIN?.trim();
  if (!raw) return null;
  return raw.replace(/\/+$/, "");
}

function derivedTorcsRunHostname(hostname: string): string | null {
  if (hostname.startsWith("override.")) {
    return `torcs-run.${hostname.slice("override.".length)}`;
  }
  if (hostname.startsWith("override-")) {
    return hostname.replace(/^override-/, "torcs-run-");
  }
  return null;
}

export function torcsRunOrigin(): string | null {
  const configured = configuredTorcsRunOrigin();
  if (configured) return configured;

  if (typeof window === "undefined") return null;
  if (isLocalHost()) return "http://localhost:6080";

  const derivedHost = derivedTorcsRunHostname(window.location.hostname);
  if (!derivedHost) return null;

  return `${window.location.protocol}//${derivedHost}`;
}

export function hasTorcsSurface(): boolean {
  return torcsRunOrigin() !== null;
}

export function torcsNoVncUrl(): string | null {
  const origin = torcsRunOrigin();
  if (!origin) return null;
  return `${origin}/vnc_lite.html?autoconnect=1&password=&reconnect=1&scale=true`;
}
