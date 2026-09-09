"use client";
import { fmt, fmtHour } from "@/lib/format";
import { STATE_GLYPH, STATE_LABEL, wbgtColor } from "@/lib/ramp";
import type { HourRow } from "@/lib/types";

export function RawTable({ hours, theme }: { hours: HourRow[]; theme: "light" | "dark" }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full min-w-[520px] border-collapse text-sm">
        <caption className="sr-only">
          Hour by hour forecast WBGT, the plan work fraction, the calendar ban work fraction, and the plan retained heat load.
        </caption>
        <thead>
          <tr className="border-b border-border bg-surface-2 text-left text-ink-secondary">
            {["Local", "WBGT C", "Plan", "Ban", "Retained", "State"].map((h) => (
              <th key={h} scope="col" className="px-3 py-2 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="mono">
          {hours.map((h) => (
            <tr key={h.hour} className="border-b border-border last:border-0">
              <td className="px-3 py-1.5 text-ink">{fmtHour(h.hour)}</td>
              <td className="px-3 py-1.5">
                <span className="inline-flex items-center gap-2">
                  <span aria-hidden className="h-2.5 w-2.5 rounded-full" style={{ background: wbgtColor(h.wbgt_c, theme) }} />
                  <span className={h.over_threshold ? "font-semibold text-state-stop" : "text-ink"}>{fmt(h.wbgt_c, 1)}</span>
                </span>
              </td>
              <td className="px-3 py-1.5 text-ink">{fmt(h.plan_work_fraction, 2)}</td>
              <td className="px-3 py-1.5 text-ink-muted">{fmt(h.calendar_work_fraction, 2)}</td>
              <td className="px-3 py-1.5 text-ink">{fmt(h.retained_load_plan, 2)}</td>
              <td className="px-3 py-1.5">
                <span className="inline-flex items-center gap-1.5 text-micro uppercase" style={{ color: `var(--state-${h.plan_state})` }}>
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
