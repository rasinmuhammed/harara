"use client";
import { useRef } from "react";

const HINTS = [
  "What is WBGT?",
  "How does tomorrow compare to the week?",
  "Is it safe to work outside in Doha right now?",
  "Has heat been increasing here?",
  "What's the rule in Qatar?",
];

export function Composer({
  onSend,
  busy,
  onStop,
  showHints = false,
}: {
  onSend: (t: string) => void;
  busy: boolean;
  onStop: () => void;
  showHints?: boolean;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  function submit() {
    const v = ref.current?.value.trim();
    if (!v || busy) return;
    onSend(v);
    if (ref.current) ref.current.value = "";
  }
  return (
    <div data-print-hide className="border-t border-border bg-bg px-3 py-3">
      {showHints && !busy && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {HINTS.map((h) => (
            <button
              key={h}
              type="button"
              onClick={() => onSend(h)}
              className="rounded-full border border-border px-2.5 py-1 text-sm text-ink-secondary transition-colors hover:border-border-strong hover:text-ink"
            >
              {h}
            </button>
          ))}
        </div>
      )}
      <div className="flex items-end gap-2">
      <textarea
        ref={ref}
        rows={1}
        placeholder="Ask about heat, the forecast or the rules, or describe a shift"
        aria-label="Message"
        onInput={(e) => {
          const el = e.currentTarget;
          el.style.height = "auto";
          el.style.height = Math.min(el.scrollHeight, 160) + "px";
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        className="max-h-40 flex-1 resize-none rounded-lg border border-border bg-surface px-3 py-2.5 text-base text-ink outline-none transition-colors focus:border-accent"
      />
      {busy ? (
        <button type="button" onClick={onStop} className="rounded-lg border border-border px-3.5 py-2.5 text-sm text-ink-secondary hover:border-border-strong hover:text-ink">
          Stop
        </button>
      ) : (
        <button type="button" onClick={submit} className="rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink hover:bg-accent-hover">
          Send
        </button>
      )}
      </div>
    </div>
  );
}
