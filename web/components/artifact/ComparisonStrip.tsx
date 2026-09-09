"use client";
import { useCountUp } from "@/lib/hooks";
import { fmt } from "@/lib/format";
import type { PlanSummary } from "@/lib/types";

function Cell({
  label,
  value,
  digits = 2,
  unit,
  sub,
  delta,
}: {
  label: React.ReactNode;
  value: number;
  digits?: number;
  unit?: string;
  sub?: string;
  delta?: string;
}) {
  const v = useCountUp(value);
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-border bg-surface p-3">
      <span className="mono text-micro uppercase tracking-wide text-ink-muted">
        {label}
      </span>
      <span className="mono text-stat font-semibold leading-none text-ink">
        {fmt(v, digits)}
        {unit ? <span className="text-lg text-ink-muted"> {unit}</span> : null}
      </span>
      {sub && <span className="mono text-sm text-ink-muted">{sub}</span>}
      {delta && <span className="mono text-sm font-medium text-state-work">{delta}</span>}
    </div>
  );
}

export function ComparisonStrip({ s }: { s: PlanSummary }) {
  const d = (p: number) => (p > 0 ? `−${fmt(p, 1)}% vs ban` : `+${fmt(-p, 1)}% vs ban`);
  return (
    <div role="group" aria-label="Plan versus calendar ban" className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
      <Cell label="Retained load, peak" value={s.peak_plan} sub={`ban ${fmt(s.peak_calendar)}`} delta={d(s.pct_peak_reduction)} />
      <Cell label="Tail, p90" value={s.tail_plan} sub={`ban ${fmt(s.tail_calendar)}`} delta={d(s.pct_tail_reduction)} />
      <Cell label="Hours delivered" value={s.work_hours_delivered_plan} digits={1} unit="h" sub={`ban ${fmt(s.work_hours_delivered_calendar, 1)} h`} />
      <Cell label="Stop hours, plan" value={s.stop_hours_plan} digits={0} sub={`${s.stop_hours_calendar} banned`} />
    </div>
  );
}
