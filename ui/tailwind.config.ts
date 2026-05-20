import type { Config } from "tailwindcss";

// Design tokens mirror docs/04-ui-ux-design.md §3 verbatim.
// CSS variables live in src/styles/tokens.css; Tailwind references them
// so the actual color values stay in one place.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // All palette tokens use the rgb(R G B / <alpha-value>) form so
        // dark-theme utilities like `bg-surface-2/30` and `border-border/70`
        // render correctly on native controls as well as regular divs.
        bg: "rgb(var(--color-bg-rgb) / <alpha-value>)",
        surface: "rgb(var(--color-surface-rgb) / <alpha-value>)",
        "surface-2": "rgb(var(--color-surface-2-rgb) / <alpha-value>)",
        "surface-3": "rgb(var(--color-surface-3-rgb) / <alpha-value>)",
        border: "rgb(var(--color-border-rgb) / <alpha-value>)",
        text: "rgb(var(--color-text-rgb) / <alpha-value>)",
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
