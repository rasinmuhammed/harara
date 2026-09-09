const FIELD_LABEL: Record<string, string> = {
  target_local_date: "the date",
  required_work_hours: "the work-hours",
  workload: "the workload class",
  acclimatised: "acclimatisation",
  location: "the location",
};

export function ClarificationState({
  question,
  missing,
  onDismiss,
}: {
  question: string;
  missing: string[];
  onDismiss: () => void;
}) {
  return (
    <div className="rounded-lg border border-accent bg-accent-weak/40 p-4">
      <div className="flex items-start gap-3">
        <span
          aria-hidden
          className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full border border-accent text-accent"
        >
          ?
        </span>
        <div className="flex flex-col gap-2">
          <h3 className="text-base font-semibold text-ink">One more thing</h3>
          <p className="text-base text-ink-secondary">{question}</p>
          {missing.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {missing.map((f) => (
                <span
                  key={f}
                  className="rounded-sm border border-accent/50 bg-surface px-2 py-1 text-caption uppercase text-ink-secondary"
                >
                  {FIELD_LABEL[f] ?? f}
                </span>
              ))}
            </div>
          )}
          <p className="pt-1 text-sm text-ink-muted">
            The planner won&rsquo;t assume a safety-relevant value. Fill the form
            on the left instead, or add the missing detail and re-send.
          </p>
          <button
            type="button"
            onClick={onDismiss}
            className="mt-1 inline-flex min-h-[28px] items-center self-start text-sm font-medium text-accent underline decoration-accent/40"
          >
            Use the form
          </button>
        </div>
      </div>
    </div>
  );
}
