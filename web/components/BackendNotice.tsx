"use client";

import { useEffect, useState } from "react";

const KEY = "harara-backend-notice-dismissed";

// A quiet, dismissible one-liner explaining the free-tier backend, so a slow
// first request reads as expected rather than broken.
export function BackendNotice() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    try {
      setShow(localStorage.getItem(KEY) !== "1");
    } catch {
      setShow(true);
    }
  }, []);

  if (!show) return null;

  return (
    <div className="flex items-center gap-3 border-b border-border bg-surface px-4 py-1.5 text-micro text-ink-muted">
      <span className="flex-1">
        The demo backend runs on Render&rsquo;s free tier. The first request after
        a quiet spell can take up to a minute to wake, then it is fast.
      </span>
      <button
        type="button"
        onClick={() => {
          try {
            localStorage.setItem(KEY, "1");
          } catch {}
          setShow(false);
        }}
        className="shrink-0 rounded px-1.5 py-0.5 text-ink-muted hover:bg-surface-2 hover:text-ink"
        aria-label="Dismiss"
      >
        Got it
      </button>
    </div>
  );
}
