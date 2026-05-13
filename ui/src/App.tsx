import { Link, Navigate, NavLink as RouterNavLink, Route, Routes, useLocation } from "react-router-dom";
import { useEffect } from "react";

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
          <Route path="/sessions" element={<SessionsPage />} />
          <Route path="/sessions/compare" element={<SessionComparePage />} />
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
  return (
    <header className="px-6 py-3 border-b border-border flex items-center justify-between">
      <Link
        to="/"
        className="flex items-center gap-2 font-semibold tracking-tight"
        aria-label="OVERRIDE — home"
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
      <nav className="flex gap-1 text-sm" aria-label="Primary">
        <NavLink to="/upload" label="Upload" />
        <NavLink to="/sessions" label="Sessions" />
      </nav>
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

function SiteFooter() {
  return (
    <footer className="px-6 py-4 border-t border-border text-xs text-muted flex flex-wrap items-center gap-x-3 gap-y-1">
      <span>Decision support, never replacement.</span>
      <span aria-hidden="true">·</span>
      <span>
        Built on <span className="text-text">IBM watsonx.ai</span>
      </span>
      <span aria-hidden="true">·</span>
      <a
        href="https://github.com/anthropics/overdrive-may-2026"
        target="_blank"
        rel="noreferrer"
        className="hover:text-text transition-colors"
      >
        Repo ↗
      </a>
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
    };
    if (location.pathname.startsWith("/session/")) {
      document.title = "Session debrief — OVERRIDE";
      return;
    }
    document.title = map[location.pathname] ?? "OVERRIDE";
  }, [location.pathname]);
  return null;
}
