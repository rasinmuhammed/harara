"use client";
import { useRef } from "react";
export function Composer({
  onSend,
  busy,
  onStop,
}: {
  onSend: (t: string) => void;
  busy: boolean;
  onStop: () => void;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  function submit() {
    const v = ref.current?.value.trim();
    if (!v || busy) return;
    onSend(v);
    if (ref.current) ref.current.value = "";
  }
  return (
    <div className="flex items-end gap-2 border-t border-border bg-bg px-3 py-3">
      <textarea
        ref={ref}
        rows={1}
        placeholder="Describe a shift the way you would to a colleague"
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
  );
}
