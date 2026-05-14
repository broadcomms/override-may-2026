import type { Config } from "tailwindcss";

// Design tokens mirror docs/04-ui-ux-design.md §3 verbatim.
// CSS variables live in src/styles/tokens.css; Tailwind references them
// so the actual color values stay in one place.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // bg / surface / border / text don't use the `/N` opacity modifier
        // anywhere — keep them as raw hex var refs.
        bg: "var(--color-bg)",
        surface: "var(--color-surface)",
        "surface-2": "var(--color-surface-2)",
        "surface-3": "var(--color-surface-3)",
        border: "var(--color-border)",
        text: "var(--color-text)",
        // The colours below are used with Tailwind's alpha-modifier syntax
        // (e.g. `bg-warning/30`, `border-danger/40`). That requires the
        // rgb(R G B / <alpha-value>) form so Tailwind can inject alpha.
        // The RGB-triplet vars are defined alongside the hex vars in
        // src/styles/tokens.css.
        muted: "rgb(var(--color-text-muted-rgb) / <alpha-value>)",
        accent: "rgb(var(--color-accent-rgb) / <alpha-value>)",
        success: "rgb(var(--color-success-rgb) / <alpha-value>)",
        warning: "rgb(var(--color-warning-rgb) / <alpha-value>)",
        danger: "rgb(var(--color-danger-rgb) / <alpha-value>)",
        granite: "rgb(var(--color-granite-blue-rgb) / <alpha-value>)",
      },
      fontFamily: {
        sans: ['"Inter"', '"system-ui"', "sans-serif"],
        mono: ['"JetBrains Mono"', '"ui-monospace"', "monospace"],
      },
      spacing: {
        // Inter scale per §3
      },
      borderRadius: {
        card: "12px",
        pill: "999px",
      },
      boxShadow: {
        card: "var(--shadow-card)",
        "card-hover": "var(--shadow-card-hover)",
      },
      transitionTimingFunction: {
        "snap-out": "cubic-bezier(0.32, 0.72, 0, 1)",
      },
      keyframes: {
        shimmer: {
          "0%": { backgroundPosition: "200% 0" },
          "100%": { backgroundPosition: "-200% 0" },
        },
      },
      animation: {
        shimmer: "shimmer 1.2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
} satisfies Config;
