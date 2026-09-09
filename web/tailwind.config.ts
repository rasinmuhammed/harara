import type { Config } from "tailwindcss";

/**
 * Tailwind is a utility layer over the CSS custom properties defined in
 * app/globals.css. Every colour/space/radius token has a single source of
 * truth there (light and dark); this file only exposes them to utilities.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        "surface-sunken": "var(--surface-sunken)",
        border: "var(--border)",
        "border-strong": "var(--border-strong)",
        ink: "var(--text)",
        "ink-secondary": "var(--text-secondary)",
        "ink-muted": "var(--text-muted)",
        accent: "var(--accent)",
        "accent-hover": "var(--accent-hover)",
        "accent-weak": "var(--accent-weak)",
        compare: "var(--compare)",
        "state-work": "var(--state-work)",
        "state-reduced": "var(--state-reduced)",
        "state-stop": "var(--state-stop)",
      },
      fontFamily: {
        display: ["var(--font-fraunces)", "Georgia", "serif"],
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
      fontSize: {
        caption: ["0.75rem", { lineHeight: "1.4", letterSpacing: "0.06em" }],
        sm: ["0.875rem", { lineHeight: "1.45" }],
        base: ["1rem", { lineHeight: "1.55" }],
        lead: ["1.125rem", { lineHeight: "1.5" }],
        stat: ["1.5rem", { lineHeight: "1.2" }],
        h3: ["1.5rem", { lineHeight: "1.15" }],
        h2: ["2rem", { lineHeight: "1.1" }],
        title: ["2.75rem", { lineHeight: "1.05" }],
        hero: ["3.75rem", { lineHeight: "1.0" }],
      },
      borderRadius: {
        sm: "var(--r-sm)",
        DEFAULT: "var(--r)",
        lg: "var(--r-lg)",
      },
      boxShadow: {
        card: "var(--shadow-card)",
      },
      transitionTimingFunction: {
        out: "cubic-bezier(.16,1,.3,1)",
      },
    },
  },
  plugins: [],
};

export default config;
