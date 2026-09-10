"use client";
import { useCountUp } from "@/lib/hooks";
import { fmt } from "@/lib/format";
import type { PlanSummary } from "@/lib/types";

function Cell({ label, value, digits = 2, unit, sub, delta, good }: {
  label: string; value: number; digits?: number; unit?: string; sub?: string;
  delta?: string; good?: boolean;
}) {
  const v = useCountUp(value);
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-border bg-surface p-3">
      <span className="mono text-micro uppercase tracking-wide text-ink-muted">{label}</span>
      <span className="mono text-stat font-semibold leading-none text-ink">
        {fmt(v, digits)}{unit ? <span className="text-lg text-ink-muted"> {unit}</span> : null}
      </span>
      {sub && <span className="mono text-sm text-ink-muted">{sub}</span>}
      {delta && (
        <span className={`mono text-sm font-medium ${good === false ? "text-state-stop" : "text-state-work"}`}>
          {delta}
        </span>
      )}
    </div>
  );
}

export function ComparisonStrip({ s, showReactive }: { s: PlanSummary; showReactive?: boolean }) {
  const spanSaved = s.span_hours_calendar - s.span_hours_plan;
  const doseUp = s.cumulative_exposure_plan > s.cumulative_exposure_calendar + 1e-6;
  return (
    <div role="group" aria-label="Plan versus the calendar rule" className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
      <Cell label="Retained load, peak" value={s.peak_plan}
        sub={`fixed rule ${fmt(s.peak_calendar)}${showReactive ? ` · hot-stop ${fmt(s.peak_reactive)}` : ""}`}
        delta={`${s.pct_peak_reduction >= 0 ? "−" : "+"}${fmt(Math.abs(s.pct_peak_reduction), 1)}% vs fixed rule`}
        good={s.pct_peak_reduction >= 0} />
      <Cell label="Tail, p90" value={s.tail_plan} sub={`fixed rule ${fmt(s.tail_calendar)}`}
        delta={`${s.pct_tail_reduction >= 0 ? "−" : "+"}${fmt(Math.abs(s.pct_tail_reduction), 1)}% vs fixed rule`}
        good={s.pct_tail_reduction >= 0} />
      <Cell label="Time on site" value={s.span_hours_plan} digits={1} unit="h"
        sub={`fixed rule ${fmt(s.span_hours_calendar, 1)} h`}
        delta={spanSaved >= 0.05 ? `${fmt(spanSaved, 1)} h shorter` : "same as fixed rule"} />
      <Cell label="Heat dose, total" value={s.cumulative_exposure_plan} digits={1}
        sub={`fixed rule ${fmt(s.cumulative_exposure_calendar, 1)}`}
        delta={doseUp ? `${fmt(s.cumulative_exposure_plan - s.cumulative_exposure_calendar, 1)} higher` : `${fmt(s.cumulative_exposure_calendar - s.cumulative_exposure_plan, 1)} lower`}
        good={!doseUp} />
      <Cell label="Hours delivered" value={s.work_hours_delivered_plan} digits={1} unit="h"
        sub={`fixed rule ${fmt(s.work_hours_delivered_calendar, 1)} h`} />
      <Cell label="Work blocks" value={s.work_blocks_plan} digits={0}
        sub={`fixed rule ${s.work_blocks_calendar}`} />
    </div>
  );
}
