const LABEL: Record<string, string> = {
  parsing: "Reading the request",
  forecasting: "Getting the forecast",
  planning: "Planning the day",
  writing: "Writing it up",
};
export function ThinkingIndicator({ state }: { state?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-ink-muted">
      <span className="flex gap-1" aria-hidden>
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ink-muted" />
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ink-muted [animation-delay:150ms]" />
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-ink-muted [animation-delay:300ms]" />
      </span>
      {LABEL[state ?? "parsing"] ?? "Working"}
    </div>
  );
}
