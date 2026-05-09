import type { Config } from "tailwindcss";

// Design tokens mirror docs/04-ui-ux-design.md §3 verbatim.
// CSS variables live in src/styles/tokens.css; Tailwind references them
// so the actual color values stay in one place.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--color-bg)",
        surface: "var(--color-surface)",
        "surface-2": "var(--color-surface-2)",
        border: "var(--color-border)",
        text: "var(--color-text)",
        muted: "var(--color-text-muted)",
        accent: "var(--color-accent)",
        success: "var(--color-success)",
        warning: "var(--color-warning)",
        danger: "var(--color-danger)",
        granite: "var(--color-granite-blue)",
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
