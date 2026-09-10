const STEPS = [
  ["forecasting", "Getting the forecast", "hourly weather for that grid cell"],
  ["planning", "Planning the day", "work and rest that holds heat load down"],
  ["writing", "Writing it up", "plain language, every number from the solver"],
] as const;

const ORDER: Record<string, number> = { forecasting: 0, planning: 1, writing: 2 };

/** A plain "thinking" pulse for a conversational reply; the three-step pipeline
 *  only once a plan is actually being built. */
export function ThinkingIndicator({ state }: { state?: string }) {
  const at = ORDER[state ?? ""];

  if (at === undefined) {
    return (
      <span className="inline-flex items-center gap-2 text-sm text-ink-muted" aria-label="Thinking">
        <span className="flex gap-1" aria-hidden>
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ink-muted" />
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ink-muted [animation-delay:150ms]" />
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ink-muted [animation-delay:300ms]" />
        </span>
        Thinking
      </span>
    );
  }

  return (
    <ol className="flex flex-col gap-1.5" aria-label="Progress">
      {STEPS.map(([key, label, detail], i) => {
        const done = i < at;
        const now = i === at;
        return (
          <li key={key} className="flex items-start gap-2 text-sm">
            <span
              aria-hidden
              className={`mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full border text-[10px] ${
                done
                  ? "border-accent bg-accent text-accent-ink"
                  : now
                    ? "border-accent text-accent"
                    : "border-border text-ink-muted"
              }`}
            >
              {done ? "✓" : now ? <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" /> : i + 1}
            </span>
            <span className={now ? "text-ink" : done ? "text-ink-secondary" : "text-ink-muted"}>
              {label}
              <span className="text-ink-muted">, {detail}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}
