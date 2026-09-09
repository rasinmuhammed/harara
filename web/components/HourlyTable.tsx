"use client";

import { useMemo, useState } from "react";
import { fmt, fmtHour } from "@/lib/format";
import { STATE_GLYPH, STATE_LABEL, wbgtColor } from "@/lib/ramp";
import type { HourRow } from "@/lib/types";

type Col = "hour" | "wbgt_c" | "plan_work_fraction" | "calendar_work_fraction" | "retained_load_plan";
const COLS: { key: Col; label: string; num: boolean }[] = [
  { key: "hour", label: "Local", num: true },
  { key: "wbgt_c", label: "WBGT °C", num: true },
  { key: "plan_work_fraction", label: "Plan", num: true },
  { key: "calendar_work_fraction", label: "Calendar", num: true },
  { key: "retained_load_plan", label: "Retained load", num: true },
];

export function HourlyTable({
  hours,
  theme,
  focusedHour,
  onFocusHour,
}: {
  hours: HourRow[];
  theme: "light" | "dark";
  focusedHour: number | null;
  onFocusHour: (h: number | null) => void;
}) {
  const [sort, setSort] = useState<{ col: Col; dir: 1 | -1 }>({
    col: "hour",
    dir: 1,
  });

  const rows = useMemo(() => {
    const r = [...hours];
    r.sort((a, b) => ((a[sort.col] as number) - (b[sort.col] as number)) * sort.dir);
    return r;
  }, [hours, sort]);

  const toggle = (col: Col) =>
    setSort((s) => (s.col === col ? { col, dir: (s.dir * -1) as 1 | -1 } : { col, dir: 1 }));

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full min-w-[560px] border-collapse text-sm">
        <caption className="sr-only">
          Hour-by-hour forecast WBGT, the optimiser plan work fraction, the
          calendar-ban work fraction, and the plan&rsquo;s retained heat load.
        </caption>
        <thead>
          <tr className="border-b border-border bg-surface-sunken text-left">
            {COLS.map((c) => (
              <th
                key={c.key}
                scope="col"
                className="px-3 py-2 font-medium text-ink-secondary"
              >
                <button
                  type="button"
                  onClick={() => toggle(c.key)}
                  className="inline-flex items-center gap-1 hover:text-ink"
                  aria-label={`Sort by ${c.label}`}
                >
                  {c.label}
                  <span aria-hidden className="text-ink-muted">
                    {sort.col === c.key ? (sort.dir === 1 ? "▲" : "▼") : ""}
                  </span>
                </button>
              </th>
            ))}
            <th scope="col" className="px-3 py-2 font-medium text-ink-secondary">
              State
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((h) => (
            <tr
              key={h.hour}
              onMouseEnter={() => onFocusHour(h.hour)}
              onMouseLeave={() => onFocusHour(null)}
              className={`border-b border-border last:border-0 ${
                focusedHour === h.hour ? "bg-accent-weak" : ""
              }`}
            >
              <td className="tnum px-3 py-2 text-ink">{fmtHour(h.hour)}</td>
              <td className="tnum px-3 py-2">
                <span className="inline-flex items-center gap-2">
                  <span
                    aria-hidden
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ background: wbgtColor(h.wbgt_c, theme) }}
                  />
                  <span
                    className={h.over_threshold ? "font-semibold text-state-stop" : "text-ink"}
                  >
                    {fmt(h.wbgt_c, 1)}
                  </span>
                </span>
              </td>
              <td className="tnum px-3 py-2 text-ink">
                {fmt(h.plan_work_fraction, 2)}
              </td>
              <td className="tnum px-3 py-2 text-ink-muted">
                {fmt(h.calendar_work_fraction, 2)}
              </td>
              <td className="tnum px-3 py-2 text-ink">
                {fmt(h.retained_load_plan, 2)}
              </td>
              <td className="px-3 py-2">
                <span
                  className="inline-flex items-center gap-1.5 rounded-sm px-2 py-0.5 text-caption uppercase"
                  style={{
                    color: `var(--state-${h.plan_state})`,
                    background: "var(--surface-sunken)",
                  }}
                >
                  <span aria-hidden>{STATE_GLYPH[h.plan_state]}</span>
                  {STATE_LABEL[h.plan_state]}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
