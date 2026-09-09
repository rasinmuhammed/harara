"use client";

import { useTheme } from "@/lib/hooks";

export function ThemeToggle() {
  const [theme, toggle] = useTheme();
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
      className="grid h-9 w-9 place-items-center rounded border border-border text-ink-secondary transition-colors duration-[var(--dur-1)] hover:border-border-strong hover:text-ink"
    >
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden>
        {theme === "dark" ? (
          <>
            <circle cx="12" cy="12" r="4.2" fill="currentColor" />
            <path
              d="M12 2.5v2.6M12 18.9v2.6M4.4 4.4l1.9 1.9M17.7 17.7l1.9 1.9M2.5 12h2.6M18.9 12h2.6M4.4 19.6l1.9-1.9M17.7 6.3l1.9-1.9"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
            />
          </>
        ) : (
          <path
            d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5Z"
            fill="currentColor"
          />
        )}
      </svg>
    </button>
  );
}
