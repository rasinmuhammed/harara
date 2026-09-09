"use client";

/** Numeric stepper with a tabular value and hold-safe buttons. */
export function Stepper({
  value,
  onChange,
  min = 1,
  max = 12,
  step = 1,
  unit,
  label,
}: {
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
  label: string;
}) {
  const clamp = (v: number) => Math.min(max, Math.max(min, Math.round(v / step) * step));
  const btn =
    "grid h-9 w-9 place-items-center rounded-lg border border-border text-ink-secondary transition-colors hover:border-border-strong hover:text-ink disabled:pointer-events-none disabled:opacity-40 active:translate-y-px";
  return (
    <div className="flex items-center gap-3" role="group" aria-label={label}>
      <button type="button" className={btn} onClick={() => onChange(clamp(value - step))} disabled={value <= min} aria-label={`Decrease ${label}`}>
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden><path d="M3 7h8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
      </button>
      <div className="min-w-[5ch] text-center">
        <span className="mono text-stat font-semibold leading-none text-ink">{value}</span>
        {unit && <span className="mono ml-1 text-sm text-ink-muted">{unit}</span>}
      </div>
      <button type="button" className={btn} onClick={() => onChange(clamp(value + step))} disabled={value >= max} aria-label={`Increase ${label}`}>
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden><path d="M7 3v8M3 7h8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
      </button>
    </div>
  );
}
