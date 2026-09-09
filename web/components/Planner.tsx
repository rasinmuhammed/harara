"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchPlan } from "@/lib/api";
import { useTheme } from "@/lib/hooks";
import { prettyDate } from "@/lib/format";
import {
  LOCATION_PRESETS,
  type PlanResponse,
  type WorkloadClass,
} from "@/lib/types";
import { DEFAULT_FORM, InputPanel, type FormState } from "./InputPanel";
import { NLBox } from "./NLBox";
import { AssumptionsPanel } from "./AssumptionsPanel";
import { HeroChart } from "./HeroChart";
import { StatStrip } from "./StatStrip";
import { HourlyTable } from "./HourlyTable";
import { EmptyState } from "./states/EmptyState";
import { ResultsSkeleton } from "./states/ResultsSkeleton";
import { ErrorState } from "./states/ErrorState";
import { ClarificationState } from "./states/ClarificationState";

type View =
  | { k: "empty" }
  | { k: "loading" }
  | { k: "ready"; data: PlanResponse }
  | { k: "error"; message: string }
  | { k: "clarify"; question: string; missing: string[] };

export function Planner() {
  const [theme] = useTheme();
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [view, setView] = useState<View>({ k: "empty" });
  const [focusedHour, setFocusedHour] = useState<number | null>(null);
  const lastReq = useRef<FormState | null>(null);
  const didAuto = useRef(false);

  const run = useCallback(async (f: FormState) => {
    lastReq.current = f;
    setView({ k: "loading" });
    setFocusedHour(null);
    try {
      const data = await fetchPlan({
        lat: f.lat,
        lon: f.lon,
        date: f.date,
        required_work_hours: f.workHours,
        workload_class: f.workload,
        acclimatised: f.acclimatised,
      });
      setView({ k: "ready", data });
    } catch (e) {
      setView({ k: "error", message: (e as Error).message });
    }
  }, []);

  useEffect(() => {
    if (didAuto.current) return;
    didAuto.current = true;
    if (typeof window !== "undefined" &&
        new URLSearchParams(window.location.search).has("demo")) {
      run(DEFAULT_FORM);
    }
  }, [run]);

  function applyIntent(intent: Record<string, unknown>) {
    const crew = (intent.crew ?? {}) as Record<string, unknown>;
    const loc = (intent.location ?? {}) as Record<string, unknown>;
    const name =
      typeof loc.name === "string"
        ? loc.name.replace(/\b\w/g, (c) => c.toUpperCase())
        : form.locationName;
    const preset = LOCATION_PRESETS.find(
      (p) => p.name.toLowerCase() === String(name).toLowerCase(),
    );
    const next: FormState = {
      ...form,
      locationName: preset?.name ?? name,
      lat: preset?.lat ?? (typeof loc.lat === "number" ? loc.lat : form.lat),
      lon: preset?.lon ?? (typeof loc.lon === "number" ? loc.lon : form.lon),
      date:
        typeof intent.target_local_date === "string"
          ? intent.target_local_date
          : form.date,
      workHours:
        typeof intent.required_work_hours === "number"
          ? Math.round(intent.required_work_hours)
          : form.workHours,
      workload: (crew.workload as WorkloadClass) ?? form.workload,
      acclimatised:
        typeof crew.acclimatised === "boolean"
          ? crew.acclimatised
          : form.acclimatised,
    };
    setForm(next);
    run(next);
  }

  const readyDate =
    view.k === "ready" ? view.data.meta.date : form.date;

  return (
    <div className="mx-auto max-w-[1180px] px-5 py-6">
      <div className="mb-6 flex flex-col gap-1">
        <h1 className="text-title text-ink">
          Plan the day around the forecast
        </h1>
        <p className="max-w-2xl text-lead text-ink-secondary">
          The same work-hours, shaped to the hour-by-hour WBGT forecast — set
          against Qatar&rsquo;s fixed 10:00&ndash;15:30 calendar ban.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[340px_1fr]">
        <aside className="flex flex-col gap-5">
          <div className="rounded-lg border border-border bg-surface p-4">
            <InputPanel
              value={form}
              onChange={setForm}
              onSubmit={() => run(form)}
              busy={view.k === "loading"}
            />
          </div>
          <NLBox
            onParsed={applyIntent}
            onClarify={(question, missing) =>
              setView({ k: "clarify", question, missing })
            }
          />
          <div className="hidden lg:block">
            <AssumptionsPanel />
          </div>
        </aside>

        <section id="results" aria-live="polite" className="min-w-0">
          {view.k === "empty" && <EmptyState />}
          {view.k === "loading" && <ResultsSkeleton />}
          {view.k === "error" && (
            <ErrorState
              message={view.message}
              onRetry={() => lastReq.current && run(lastReq.current)}
            />
          )}
          {view.k === "clarify" && (
            <div className="flex flex-col gap-5">
              <ClarificationState
                question={view.question}
                missing={view.missing}
                onDismiss={() => setView({ k: "empty" })}
              />
              <EmptyState />
            </div>
          )}
          {view.k === "ready" && (
            <div className="flex animate-rise flex-col gap-5">
              <p className="text-sm text-ink-muted">
                {prettyDate(view.data.meta.date)} · {view.data.meta.forecast_source} ·{" "}
                {view.data.summary.solver_status}
              </p>
              <HeroChart
                hours={view.data.hours}
                meta={view.data.meta}
                theme={theme}
                focusedHour={focusedHour}
                onFocusHour={setFocusedHour}
              />
              <StatStrip s={view.data.summary} />
              <HourlyTable
                hours={view.data.hours}
                theme={theme}
                focusedHour={focusedHour}
                onFocusHour={setFocusedHour}
              />
              {view.data.summary.work_shortfall_plan > 0 && (
                <p className="rounded border border-state-reduced/40 bg-surface-sunken p-3 text-sm text-ink-secondary">
                  On this day only{" "}
                  {view.data.summary.work_hours_delivered_plan.toFixed(1)} of the{" "}
                  {form.workHours} requested work-hours fit the working window;
                  the shortfall is {view.data.summary.work_shortfall_plan.toFixed(1)} h.
                </p>
              )}
            </div>
          )}
        </section>

        <div className="lg:hidden">
          <AssumptionsPanel />
        </div>
      </div>
    </div>
  );
}
