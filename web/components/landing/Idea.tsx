"use client";

import { useState } from "react";
import { useDohaPlan, useTheme } from "@/lib/hooks";
import { fmt } from "@/lib/format";
import { DayChart } from "@/components/artifact/DayChart";
import { Reveal } from "./Reveal";
import type { PlanResponse } from "@/lib/types";

const STEPS: { n: 1 | 2 | 3 | 4; title: string; body: string }[] = [
  {
    n: 1,
    title: "The forecast, hour by hour",
    body: "WBGT for a working day in Doha. WBGT reads the heat in degrees off temperature, humidity, sun and wind, not air temperature alone. The shaded band is the range of plausible forecasts at this lead time.",
  },
  {
    n: 2,
    title: "The regulatory stop-work line",
    body: "Qatar Ministerial Decision 17/2021 sets outdoor work protection at 32.1 on this index. Harara treats that as a hard constraint, so the scheduler never plans work above it.",
  },
  {
    n: 3,
    title: "The fixed-window baseline",
    body: "The standard midday rest window holds the crew from 10:00 to 15:30. It is simple and enforceable, and Harara uses it as the comparison point.",
  },
  {
    n: 4,
    title: "What the forecast-driven plan does",
    body: "Same total hours, and the crew is on site no longer than the fixed rule keeps them, in no more pieces. Within that window it works the cool hours and eases through the forecast peak. Holding the day short is the constraint; the retained-heat effect then depends on how hot the day is.",
  },
];

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
            Same hours of work, stronger protection across the whole day.
          </h2>
          <p className="mt-3 max-w-prose text-lg text-ink-secondary">
            One working day in Doha, built up in four steps, from the forecast to the regulation to the plan.
          </p>
        </Reveal>

        {!plan ? (
          <Reveal className="mt-10 rounded-xl border border-border bg-surface p-6 text-ink-secondary">
            The live example needs the planner API running. Start it and reload, or open the planner directly.
          </Reveal>
        ) : (
          <div className="mt-10 flex flex-col gap-5">
            {STEPS.map((s) => (
              <Reveal
                key={s.n}
                className="grid gap-4 rounded-xl border border-border-strong bg-bg-raised p-4 shadow-1 lg:grid-cols-[minmax(0,20rem)_1fr] lg:gap-8 lg:p-6"
              >
                <div className="lg:pt-2">
                  <p className="mono text-micro uppercase tracking-wide text-ink-muted">Step {s.n} of 4</p>
                  <h3 className="mt-1 text-h4 text-ink">{s.title}</h3>
                  <p className="mt-2 text-base text-ink-secondary">{s.body}</p>
                  {s.n === 4 && (
                    <p className="mt-3 text-sm text-ink-secondary">
                      On{" "}
                      {new Date(plan.meta.date + "T00:00:00Z").toLocaleDateString("en-GB", {
                        day: "numeric",
                        month: "long",
                        timeZone: "UTC",
                      })}{" "}
                      the crew is on site{" "}
                      <strong className="mono text-ink">{fmt(plan.summary.span_hours_plan, 0)} h</strong> against{" "}
                      <strong className="mono text-ink">{fmt(plan.summary.span_hours_calendar, 0)} h</strong> under the
                      fixed rule, for the same{" "}
                      <strong className="mono text-ink">{fmt(plan.summary.work_hours_delivered_plan, 1)}</strong> hours
                      worked. The worst retained heat load is{" "}
                      <strong className="mono text-ink">
                        {fmt(Math.abs(plan.summary.pct_peak_reduction), 1)}%{" "}
                        {plan.summary.pct_peak_reduction >= 0 ? "below" : "above"}
                      </strong>{" "}
                      the fixed rule.
                    </p>
                  )}
                </div>
                <div>
                  <DayChart
                    hours={plan.hours}
                    meta={plan.meta}
                    theme={theme}
                    focusedHour={s.n === 4 ? hour : null}
                    onFocusHour={s.n === 4 ? setHour : () => {}}
                    stage={s.n}
                  />
                  {s.n === 4 && (
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
                  )}
                </div>
              </Reveal>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
