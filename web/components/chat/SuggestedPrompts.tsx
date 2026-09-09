"use client";
import { SUGGESTED_PROMPTS } from "@/lib/types";
export function SuggestedPrompts({ onPick }: { onPick: (t: string) => void }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="eyebrow">Try</p>
      <div className="flex flex-col gap-2">
        {SUGGESTED_PROMPTS.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => onPick(p)}
            className="reveal rounded-lg border border-border bg-surface px-3.5 py-3 text-left text-sm text-ink-secondary transition-colors hover:border-border-strong hover:text-ink"
          >
            {p}
          </button>
        ))}
      </div>
    </div>
  );
}
