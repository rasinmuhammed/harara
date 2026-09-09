import type { Config } from "tailwindcss";

// Tailwind is a thin utility layer over the CSS custom properties in
// app/globals.css. Colours/radii have one source of truth there (both themes).
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        "bg-raised": "var(--bg-raised)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        border: "var(--border)",
        "border-strong": "var(--border-strong)",
        ink: "var(--text)",
        "ink-secondary": "var(--text-secondary)",
        "ink-muted": "var(--text-muted)",
        accent: "var(--accent)",
        "accent-hover": "var(--accent-hover)",
        "accent-ink": "var(--accent-ink)",
        "accent-weak": "var(--accent-weak)",
        compare: "var(--compare)",
        "state-work": "var(--state-work)",
        "state-reduced": "var(--state-reduced)",
        "state-stop": "var(--state-stop)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        micro: ["0.75rem", { lineHeight: "1.4" }],
        sm: ["0.8125rem", { lineHeight: "1.45" }],
        base: ["0.9375rem", { lineHeight: "1.55" }],
        lg: ["1.0625rem", { lineHeight: "1.55" }],
        h4: ["1.25rem", { lineHeight: "1.2" }],
        h3: ["1.5rem", { lineHeight: "1.15" }],
        h2: ["2rem", { lineHeight: "1.1" }],
        h1: ["clamp(2.25rem, 6vw, 3.75rem)", { lineHeight: "1.05" }],
        stat: ["1.75rem", { lineHeight: "1.1" }],
      },
      borderRadius: {
        sm: "var(--r-sm)",
        DEFAULT: "var(--r)",
        lg: "var(--r-lg)",
        xl: "var(--r-xl)",
      },
      boxShadow: { "1": "var(--shadow-1)" },
      maxWidth: { content: "1120px", prose: "680px" },
      transitionTimingFunction: { out: "cubic-bezier(0.22,1,0.36,1)" },
    },
  },
  plugins: [],
};

export default config;
