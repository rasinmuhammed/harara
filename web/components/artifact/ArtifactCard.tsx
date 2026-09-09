"use client";

import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useTheme } from "@/lib/hooks";
import { prettyDate } from "@/lib/format";
import type { PlanResponse } from "@/lib/types";
import { DayChart } from "./DayChart";
import { ComparisonStrip } from "./ComparisonStrip";
import { RawTable } from "./RawTable";

export function ArtifactCard({ plan }: { plan: PlanResponse }) {
  const [theme] = useTheme();
  const [focused, setFocused] = useState<number | null>(null);
  const [open, setOpen] = useState(false);
  const loc = plan.meta.location;

  const inner = (compact: boolean) => (
    <div className="flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-h4 text-ink">
            {prettyDate(plan.meta.date)}
          </h3>
          <p className="mono text-sm text-ink-muted">
            {loc.lat.toFixed(2)}, {loc.lon.toFixed(2)} · {plan.meta.forecast_source} · {plan.summary.solver_status}
          </p>
        </div>
        {!compact && (
          <Dialog.Trigger asChild>
            <button
              type="button"
              className="shrink-0 rounded border border-border px-2.5 py-1.5 text-sm text-ink-secondary transition-colors hover:border-border-strong hover:text-ink"
            >
              Expand
            </button>
          </Dialog.Trigger>
        )}
      </div>
      <DayChart hours={plan.hours} meta={plan.meta} theme={theme} focusedHour={focused} onFocusHour={setFocused} />
      <ComparisonStrip s={plan.summary} />
      {plan.summary.work_shortfall_plan > 0 && (
        <p className="rounded border border-state-reduced/40 bg-surface-2 p-2.5 text-sm text-ink-secondary">
          Only {plan.summary.work_hours_delivered_plan.toFixed(1)} of the requested work-hours fit the working window today. The shortfall is {plan.summary.work_shortfall_plan.toFixed(1)} h.
        </p>
      )}
      <details className="rounded-lg border border-border">
        <summary className="cursor-pointer px-3 py-2 text-sm text-ink-secondary hover:text-ink">
          Raw hourly data
        </summary>
        <div className="p-3 pt-0">
          <RawTable hours={plan.hours} theme={theme} />
        </div>
      </details>
      <p className="mono text-micro text-ink-muted">
        {plan.meta.lead_time_note} {plan.meta.attribution}.
      </p>
    </div>
  );

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <div className="reveal rounded-xl border border-border-strong bg-bg-raised p-4 shadow-1">
        {inner(false)}
      </div>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
        <Dialog.Content
          className="fixed inset-0 z-50 overflow-y-auto"
          aria-label="Plan, full screen"
        >
          <div className="mx-auto min-h-full max-w-content px-4 py-8">
            <div className="rounded-xl border border-border-strong bg-bg-raised p-5 shadow-1">
              <div className="mb-3 flex justify-end">
                <Dialog.Close asChild>
                  <button
                    type="button"
                    className="rounded border border-border px-2.5 py-1.5 text-sm text-ink-secondary hover:border-border-strong hover:text-ink"
                  >
                    Close
                  </button>
                </Dialog.Close>
              </div>
              {inner(false)}
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
