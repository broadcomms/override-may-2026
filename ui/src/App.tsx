import { Link, Navigate, NavLink as RouterNavLink, Route, Routes, useLocation } from "react-router-dom";
import { useEffect, useRef, useState } from "react";

import { api } from "@/api/client";
import type { VersionResponse } from "@/api/types";
import { hasTorcsSurface } from "@/lib/env";
import { CockpitPage } from "@/pages/CockpitPage";
import { DriverLabPage } from "@/pages/DriverLabPage";
import { SessionLapPage } from "@/pages/SessionLapPage";
import { SessionComparePage } from "@/pages/SessionComparePage";
import { SessionPage } from "@/pages/SessionPage";
import { SessionsPage } from "@/pages/SessionsPage";
import { UploadPage } from "@/pages/UploadPage";

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <SkipToContent />
      <SiteHeader />
      <main id="main-content" tabIndex={-1} className="flex-1 focus:outline-none">
        <Routes>
          <Route path="/" element={<Navigate to="/upload" replace />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/driver-lab" element={<DriverLabPage />} />
          <Route path="/sessions" element={<SessionsPage />} />
          <Route path="/sessions/compare" element={<SessionComparePage />} />
          <Route path="/cockpit" element={<CockpitPage />} />
          <Route path="/session/:sessionId/laps/:lapNumber" element={<SessionLapPage />} />
          <Route path="/session/:sessionId" element={<SessionPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </main>
      <SiteFooter />
      <PageTitleManager />
    </div>
  );
}

/**
 * WCAG 2.4.1 — Skip-to-content link, hidden until focused.
 * First Tab press lands here so keyboard users can bypass the header.
 */
function SkipToContent() {
  return (
    <a
      href="#main-content"
      className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:px-3 focus:py-2 focus:rounded-md focus:bg-accent focus:text-bg focus:font-medium"
    >
      Skip to content
    </a>
  );
}

function SiteHeader() {
  const showTorcsNav = hasTorcsSurface();

  return (
    <header>
      <div className="px-6 py-3 flex items-center justify-between">
        <Link
          to="/"
          className="flex items-center gap-2 font-semibold tracking-tight"
          aria-label="OVERRIDE - home"
        >
          {/* Logo slot — auto-renders the icon when the designer ships it.
              Falls back to wordmark-only on broken/missing image. */}
          <img
            src="/logo-icon.png"
            alt=""
            width={24}
            height={24}
            className="rounded-sm"
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = "none";
            }}
          />
          <span>OVERRIDE</span>
        </Link>
        <div className="flex items-center gap-3">
          <nav className="flex gap-1 text-sm" aria-label="Primary">
            <NavLink to="/upload" label="Upload" />
            {showTorcsNav && <NavLink to="/driver-lab" label="Driver Lab" />}
            <NavLink to="/sessions" label="Sessions" />
          </nav>
          <VersionChip />
        </div>
      </div>
      <div className="px-6 py-2 border-b border-border">
        <p className="text-xs text-[var(--color-chrome-subhead)]">
          Explainable AI race-strategy copilot · grounded in FIA · IBM watsonx.ai
        </p>
      </div>
    </header>
  );
}

function NavLink({ to, label }: { to: string; label: string }) {
  return (
    <RouterNavLink
      to={to}
      className={({ isActive }) =>
        `px-2 py-1 rounded-md transition-colors ${
          isActive ? "text-text bg-surface-2" : "text-muted hover:text-text"
        }`
      }
    >
      {label}
    </RouterNavLink>
  );
}

/**
 * Build / version chip in the header.
 *
 * M3 gate: the popover renders an explicit allowlist of fields from
 * VersionResponse — app version, build SHA, Granite model IDs. Never
 * spread the whole response, never render WATSONX_PROJECT_ID or any
 * auth-adjacent field that may land in the response later. If a new
 * non-allowlist field appears in VersionResponse, it must NOT auto-render
 * here.
 */
function VersionChip() {
  const [open, setOpen] = useState(false);
  const [info, setInfo] = useState<VersionResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open || info || err) return;
    let aborted = false;
    api.version().then(
      (v) => {
        if (!aborted) setInfo(v);
      },
      (e) => {
        if (!aborted) setErr(e instanceof Error ? e.message : "unavailable");
      },
    );
    return () => {
      aborted = true;
    };
  }, [open, info, err]);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const shortSha = info?.git_sha ? info.git_sha.slice(0, 7) : null;
  const label = info ? `${info.build}${shortSha ? ` · ${shortSha}` : ""}` : "build";

  return (
    <div ref={wrapRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label="Build and model versions"
        className="text-[12px] font-mono text-muted hover:text-text transition-colors px-2 py-1 rounded-md"
      >
        {label}
      </button>
      {open && (
        <div
          role="dialog"
          aria-label="Build and model versions"
          className="absolute right-0 top-full mt-1 z-20 min-w-[300px] rounded-card border border-border bg-surface p-3 text-xs shadow-card-hover"
        >
          {err ? (
            <div className="text-muted">Version info unavailable: {err}</div>
          ) : info ? (
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 font-mono">
              {/* M3 allowlist: app_version + build_sha + model IDs. Explicit
                  field-by-field. Do NOT switch to Object.entries(info). */}
              <dt className="text-muted">app</dt>
              <dd className="text-text">{info.build}</dd>
              <dt className="text-muted">build</dt>
              <dd className="text-text break-all">{info.git_sha ?? "(local dev)"}</dd>
              <dt className="text-muted">instruct</dt>
              <dd className="text-text break-all">{info.granite_instruct}</dd>
              <dt className="text-muted">guardian</dt>
              <dd className="text-text break-all">{info.granite_guardian}</dd>
              <dt className="text-muted">embed</dt>
              <dd className="text-text break-all">{info.granite_embedding}</dd>
              <dt className="text-muted">ttm-r2</dt>
              <dd className="text-text break-all">{info.granite_ttm_r2}</dd>
            </dl>
          ) : (
            <div className="text-muted">Loading…</div>
          )}
        </div>
      )}
    </div>
  );
}

function SiteFooter() {
  return (
    <footer className="px-6 py-4 border-t border-border text-xs text-muted flex flex-wrap items-center gap-x-3 gap-y-1">
      <span>© OVERRIDE</span>
      <span aria-hidden="true">·</span>
      <span>Apache 2.0</span>
      <span aria-hidden="true">·</span>
      <span>IBM SkillsBuild May 2026</span>
      <span aria-hidden="true">·</span>
      <a
        href="https://github.com/anthropics/overdrive-may-2026"
        target="_blank"
        rel="noreferrer"
        className="hover:text-text transition-colors"
      >
        Repo ↗
      </a>
      <span aria-hidden="true">·</span>
      <span>Decision support, never replacement.</span>
    </footer>
  );
}

function NotFoundPage() {
  return (
    <div className="px-6 py-16 max-w-lg mx-auto text-center">
      <div className="text-5xl mb-3 text-muted" aria-hidden="true">
        404
      </div>
      <h1 className="text-lg font-semibold mb-2">Page not found</h1>
      <p className="text-sm text-muted mb-6">
        That route doesn’t exist. Drop a replay on the upload page or browse your sessions.
      </p>
      <div className="flex justify-center gap-2">
        <Link
          to="/upload"
          className="px-3 py-1.5 rounded-pill bg-accent text-bg text-sm font-medium hover:opacity-90 transition-opacity"
        >
          Go to upload
        </Link>
        <Link
          to="/sessions"
          className="px-3 py-1.5 rounded-pill border border-border text-sm hover:bg-surface-2 transition-colors"
        >
          Sessions
        </Link>
      </div>
    </div>
  );
}

/**
 * Updates document.title from the active route. Lightweight — no Helmet
 * dep needed for a 3-route app. Respects the project's "OVERRIDE — …"
 * naming convention used in README + submission docs.
 */
function PageTitleManager() {
  const location = useLocation();
  useEffect(() => {
    const map: Record<string, string> = {
      "/upload": "Upload — OVERRIDE",
      "/sessions": "Sessions — OVERRIDE",
      "/sessions/compare": "Compare sessions — OVERRIDE",
      "/cockpit": "Cockpit — OVERRIDE",
    };
    if (location.pathname.startsWith("/session/")) {
      document.title = "Session debrief — OVERRIDE";
      return;
    }
    document.title = map[location.pathname] ?? "OVERRIDE";
  }, [location.pathname]);
  return null;
}
