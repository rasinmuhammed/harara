"use client";
import { useTheme } from "@/lib/hooks";

export function ThemeToggle() {
  const [theme, toggle] = useTheme();
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
      className="grid h-9 w-9 place-items-center rounded border border-border text-ink-secondary transition-colors hover:border-border-strong hover:text-ink"
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
        {theme === "dark" ? (
          <>
            <circle cx="12" cy="12" r="4" fill="currentColor" />
            <path d="M12 2.5v2.4M12 19.1v2.4M4.5 4.5l1.7 1.7M17.8 17.8l1.7 1.7M2.5 12h2.4M19.1 12h2.4M4.5 19.5l1.7-1.7M17.8 6.2l1.7-1.7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </>
        ) : (
          <path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5Z" fill="currentColor" />
        )}
      </svg>
    </button>
  );
}
