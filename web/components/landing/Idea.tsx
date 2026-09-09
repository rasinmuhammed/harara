"use client";

import { useState } from "react";
import { useDohaPlan, useTheme } from "@/lib/hooks";
import { fmt } from "@/lib/format";
import { DayChart } from "@/components/artifact/DayChart";
import { Reveal } from "./Reveal";
import type { PlanResponse } from "@/lib/types";

export function Idea({ plan: initial }: { plan: PlanResponse | null }) {
  const [theme] = useTheme();
  const plan = useDohaPlan(initial);
  const [hour, setHour] = useState<number | null>(null);

  return (
    <section className="border-t border-border py-20" aria-labelledby="idea-h">
      <div className="mx-auto max-w-content px-5">
        <Reveal>
          <p className="eyebrow">The idea</p>
          <h2 id="idea-h" className="mt-2 max-w-prose text-h2 text-ink">
            Same hours of work, less of the worst heat.
          </h2>
          <p className="mt-3 max-w-prose text-lg text-ink-secondary">
            Drag across the day to see a working shift for Doha, where the plan works the cool morning at full rate, eases through the forecast peak, and picks the work back up as it drops, while still hitting the target hours.
          </p>
        </Reveal>

        {plan ? (
          <Reveal className="mt-10 rounded-xl border border-border-strong bg-bg-raised p-4 shadow-1">
            <DayChart
              hours={plan.hours}
              meta={plan.meta}
              theme={theme}
              focusedHour={hour}
              onFocusHour={setHour}
            />
            <label className="mt-2 flex items-center gap-3">
              <span className="mono text-sm text-ink-muted">scrub</span>
              <input
                type="range"
                min={plan.hours[0].hour}
                max={plan.hours[plan.hours.length - 1].hour}
                value={hour ?? plan.hours[0].hour}
                onChange={(e) => setHour(Number(e.target.value))}
                aria-label="Scrub the working day by hour"
                className="h-1 flex-1 accent-[var(--accent)]"
              />
            </label>
            <p className="mt-4 text-ink-secondary">
              For Doha on{" "}
              {new Date(plan.meta.date + "T00:00:00Z").toLocaleDateString("en-GB", {
                day: "numeric",
                month: "long",
                timeZone: "UTC",
              })}{" "}
              the plan lowers the worst retained heat load by{" "}
              <strong className="mono text-ink">{fmt(plan.summary.pct_peak_reduction, 1)}%</strong> and the p90 tail by{" "}
              <strong className="mono text-ink">{fmt(plan.summary.pct_tail_reduction, 1)}%</strong>, with the same{" "}
              <strong className="mono text-ink">{fmt(plan.summary.work_hours_delivered_plan, 1)}</strong> hours worked as the calendar ban.
            </p>
          </Reveal>
        ) : (
          <Reveal className="mt-10 rounded-xl border border-border bg-surface p-6 text-ink-secondary">
            The live example needs the planner API running. Start it and reload, or open the planner directly.
          </Reveal>
        )}
      </div>
    </section>
  );
}
