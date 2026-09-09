"use client";
const LABEL: Record<string, string> = {
  target_local_date: "date",
  required_work_hours: "work-hours",
  workload: "workload class",
  acclimatised: "acclimatisation",
  location: "location",
};
export function ClarificationCard({
  question,
  missing,
  onChip,
}: {
  question: string;
  missing: string[];
  onChip: (text: string) => void;
}) {
  return (
    <div className="rounded-lg border border-accent/50 bg-accent-weak/40 p-3">
      <p className="text-base text-ink">{question}</p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {missing.map((f) => (
          <span key={f} className="mono rounded-sm border border-accent/40 bg-surface px-2 py-0.5 text-micro uppercase text-ink-secondary">
            {LABEL[f] ?? f}
          </span>
        ))}
      </div>
      <p className="mt-2 text-sm text-ink-muted">
        The planner will not assume a safety-relevant value. Add the missing detail and send again.
      </p>
    </div>
  );
}
