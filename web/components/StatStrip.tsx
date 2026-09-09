"use client";

import { useCountUp } from "@/lib/hooks";
import { fmt } from "@/lib/format";
import type { PlanSummary } from "@/lib/types";

function Stat({
  label,
  value,
  digits = 2,
  compare,
  delta,
  suffix,
}: {
  label: string;
  value: number;
  digits?: number;
  compare?: string;
  delta?: string;
  suffix?: string;
}) {
  const v = useCountUp(value);
  return (
    <div className="flex flex-col gap-1.5 rounded-lg border border-border bg-surface p-4">
      <span className="text-caption uppercase text-ink-muted">{label}</span>
      <span className="tnum text-stat font-semibold leading-none text-ink">
        {fmt(v, digits)}
        {suffix ? <span className="text-lead text-ink-muted"> {suffix}</span> : null}
      </span>
      {compare && (
        <span className="tnum whitespace-nowrap text-sm text-ink-muted">
          ban {compare}
        </span>
      )}
      {delta && (
        <span className="tnum whitespace-nowrap text-sm font-medium text-state-work">
          {delta}
        </span>
      )}
    </div>
  );
}

export function StatStrip({ s }: { s: PlanSummary }) {
  const delta = (pct: number) =>
    pct > 0 ? `−${fmt(pct, 1)}% vs ban` : `+${fmt(-pct, 1)}% vs ban`;

  return (
    <div
      className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5"
      role="group"
      aria-label="Plan versus calendar ban, summary"
    >
      <Stat
        label="Peak load"
        value={s.peak_plan}
        compare={fmt(s.peak_calendar)}
        delta={delta(s.pct_peak_reduction)}
      />
      <Stat
        label="Tail load · p90"
        value={s.tail_plan}
        compare={fmt(s.tail_calendar)}
        delta={delta(s.pct_tail_reduction)}
      />
      <Stat
        label="Delivered"
        value={s.work_hours_delivered_plan}
        digits={1}
        compare={`${fmt(s.work_hours_delivered_calendar, 1)} h`}
        suffix="h"
      />
      <Stat
        label="Stop hours · plan"
        value={s.stop_hours_plan}
        digits={0}
        compare={`${s.stop_hours_calendar} banned`}
      />
      <Stat label="WBGT ref" value={s.wbgt_ref_c} digits={1} suffix="°C" />
    </div>
  );
}
