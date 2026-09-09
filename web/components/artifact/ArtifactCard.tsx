"use client";

import { useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useTheme } from "@/lib/hooks";
import { fmt, prettyDate, isoToday, isoPlusDays } from "@/lib/format";
import { fetchPlan } from "@/lib/api";
import { encodeShare } from "@/lib/share";
import type { PlanResponse } from "@/lib/types";
import { DayChart, type Policies } from "./DayChart";
import { ComparisonStrip } from "./ComparisonStrip";
import { RawTable } from "./RawTable";

const chip = "rounded-full border px-2.5 py-1 text-sm transition-colors";
const on = "border-accent bg-accent-weak text-ink";
const off = "border-border text-ink-secondary hover:border-border-strong hover:text-ink";

export function ArtifactCard({
  plan: initial,
  embedded = false,
}: {
  plan: PlanResponse;
  /** inside the /app frame the control bar owns day and work type, so the
   *  card hides its own day and what-if rows to avoid two ways to set one thing */
  embedded?: boolean;
}) {
  const [theme] = useTheme();
  const [plan, setPlan] = useState(initial);
  const [focused, setFocused] = useState<number | null>(null);
  const [policies, setPolicies] = useState<Policies>({ calendar: true, reactive: false });
  const [pending, setPending] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const req = plan.meta.request;
  const s = plan.summary;
  const canReplan = !!req && !!req.date;

  async function replan(patch: Partial<typeof req>) {
    setPending(true);
    setErr(null);
    try {
      const next = await fetchPlan({
        lat: req.lat, lon: req.lon, date: req.date,
        required_work_hours: req.required_work_hours,
        workload_class: req.workload_class, acclimatised: req.acclimatised,
        tz: req.tz, ...patch,
      } as any);
      setPlan(next);
      setFocused(null);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setPending(false);
    }
  }

  const lighter: Record<string, string> = { very_heavy: "heavy", heavy: "moderate", moderate: "light", light: "light" };
  const leadOf = (iso: string) => Math.max(0, Math.round((+new Date(iso) - +new Date(isoToday())) / 86400000));
  const curLead = leadOf(req.date);

  const headline =
    `Worst point of the day: heat load ${fmt(s.peak_plan, 1)}, down from ${fmt(s.peak_calendar, 1)} ` +
    `under the fixed rule, same ${fmt(s.work_hours_delivered_plan, 0)} hours worked.`;

  const body = (
    <div className={`flex flex-col gap-4 ${pending ? "opacity-50" : ""}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-h4 leading-snug text-ink">{headline}</p>
          <p className="mono mt-1 text-sm text-ink-muted">
            {prettyDate(plan.meta.date)} · {plan.meta.location.lat.toFixed(2)}, {plan.meta.location.lon.toFixed(2)} · {plan.meta.forecast_source}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5 print:hidden">
          {canReplan && (
            <>
              <button
                type="button"
                onClick={() => {
                  const url = `${window.location.origin}/app?q=${encodeShare(req)}`;
                  navigator.clipboard?.writeText(url).then(() => {
                    setCopied(true);
                    setTimeout(() => setCopied(false), 1800);
                  });
                }}
                className="rounded border border-border px-2.5 py-1.5 text-sm text-ink-secondary hover:border-border-strong hover:text-ink"
              >
                {copied ? "Link copied" : "Copy link"}
              </button>
              <button type="button" onClick={() => window.print()} className="rounded border border-border px-2.5 py-1.5 text-sm text-ink-secondary hover:border-border-strong hover:text-ink">Print</button>
            </>
          )}
          <Dialog.Trigger asChild>
            <button type="button" className="rounded border border-border px-2.5 py-1.5 text-sm text-ink-secondary hover:border-border-strong hover:text-ink">Expand</button>
          </Dialog.Trigger>
        </div>
      </div>

      {(plan.meta.dry_hot_day || plan.meta.wide_band) && (
        <p className="rounded border border-border bg-surface-2 p-2.5 text-sm text-ink-secondary">
          {plan.meta.dry_hot_day && plan.meta.dry_hot_note}{" "}
          {plan.meta.wide_band && "This is several days out, so the forecast is less certain. Check again the morning before."}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5">
          <span className="mono text-micro uppercase text-ink-muted">show</span>
          <button type="button" aria-pressed={policies.calendar} className={`${chip} ${policies.calendar ? on : off}`} onClick={() => setPolicies((p) => ({ ...p, calendar: !p.calendar }))}>fixed rule</button>
          <button type="button" aria-pressed={policies.reactive} className={`${chip} ${policies.reactive ? on : off}`} onClick={() => setPolicies((p) => ({ ...p, reactive: !p.reactive }))}>stop when hot</button>
        </div>
        {canReplan && !embedded && (
          <>
            <div className="flex items-center gap-1.5">
              <span className="mono text-micro uppercase text-ink-muted">day</span>
              {([["today", 0], ["tomorrow", 1], ["in 3 days", 3]] as const).map(([label, d]) => (
                <button key={label} type="button" disabled={pending}
                  aria-pressed={curLead === d}
                  className={`${chip} ${curLead === d ? on : off}`}
                  onClick={() => replan({ date: d === 0 ? isoToday() : isoPlusDays(d) })}>
                  {label}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-1.5">
              <span className="mono text-micro uppercase text-ink-muted">what if</span>
              <button type="button" disabled={pending || req.workload_class === "light"}
                className={`${chip} ${off}`}
                onClick={() => replan({ workload_class: lighter[req.workload_class] as typeof req.workload_class })}>lighter work</button>
              <button type="button" disabled={pending} aria-pressed={req.acclimatised}
                className={`${chip} ${req.acclimatised ? on : off}`}
                onClick={() => replan({ acclimatised: !req.acclimatised })}>used to the heat</button>
            </div>
          </>
        )}
      </div>
      {canReplan && !embedded && curLead >= 3 && !plan.meta.wide_band && (
        <p className="mono text-sm text-ink-muted">This far out the forecast is less certain. Check again the morning before.</p>
      )}
      {err && <p className="text-sm text-state-stop">Could not re-plan: {err}</p>}

      {s.work_shortfall_plan > 0 && (
        <p className="rounded border border-border bg-surface-2 p-2.5 text-sm text-ink-secondary">
          Only {fmt(s.work_hours_delivered_plan, 1)} of the requested work-hours fit the working window. The shortfall is {fmt(s.work_shortfall_plan, 1)} hours.
        </p>
      )}

      <DayChart hours={plan.hours} meta={plan.meta} theme={theme} focusedHour={focused} onFocusHour={setFocused} policies={policies} />
      <ComparisonStrip s={s} showReactive={policies.reactive} />

      <details className="rounded-lg border border-border">
        <summary className="cursor-pointer px-3 py-2 text-sm text-ink-secondary hover:text-ink">Per-hour instructions</summary>
        <ul className="mono flex flex-col gap-0.5 p-3 pt-1 text-sm text-ink-secondary">
          {plan.hours.map((h) => (
            <li key={h.hour}><span className="text-ink">{String(h.hour).padStart(2, "0")}:00</span> {h.cycle}</li>
          ))}
        </ul>
      </details>

      <details className="rounded-lg border border-border">
        <summary className="cursor-pointer px-3 py-2 text-sm text-ink-secondary hover:text-ink">What produced these numbers</summary>
        <ul className="flex flex-col gap-1.5 p-3 pt-1 text-sm text-ink-secondary">
          <li>Forecast: {plan.meta.forecast_source}, {plan.meta.forecast_run}, lead {plan.meta.lead_days} day{plan.meta.lead_days === 1 ? "" : "s"}.</li>
          <li>Grid cell: {plan.meta.location.lat.toFixed(2)}, {plan.meta.location.lon.toFixed(2)}. {plan.meta.location.grid_note}.</li>
          <li>Heat index: Liljegren WBGT through ECMWF thermofeel. Work and rest from the ACGIH TLV tables (ACGIH 2017, ISO 7243).</li>
          <li>Plan: CVaR work/rest linear program on the point forecast. {plan.meta.uncertainty_note}</li>
          <li>{plan.meta.lead_time_note}</li>
          <li>Generated {new Date(plan.meta.generated_at).toUTCString()}. {plan.meta.attribution}.</li>
        </ul>
      </details>

      <details className="rounded-lg border border-border">
        <summary className="cursor-pointer px-3 py-2 text-sm text-ink-secondary hover:text-ink">Raw hourly data</summary>
        <div className="p-3 pt-0"><RawTable hours={plan.hours} theme={theme} /></div>
      </details>
    </div>
  );

  return (
    <Dialog.Root>
      <div className="reveal rounded-xl border border-border-strong bg-bg-raised p-4 shadow-1">{body}</div>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
        <Dialog.Content className="fixed inset-0 z-50 overflow-y-auto" aria-label="Plan, full screen">
          <div className="mx-auto min-h-full max-w-content px-4 py-8">
            <div className="rounded-xl border border-border-strong bg-bg-raised p-5 shadow-1">
              <div className="mb-3 flex justify-end">
                <Dialog.Close asChild>
                  <button type="button" className="rounded border border-border px-2.5 py-1.5 text-sm text-ink-secondary hover:border-border-strong hover:text-ink">Close</button>
                </Dialog.Close>
              </div>
              {body}
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
