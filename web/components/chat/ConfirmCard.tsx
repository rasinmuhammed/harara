"use client";

import { useState } from "react";
import { WORKLOADS } from "@/lib/worktypes";
import type { WorkloadClass } from "@/lib/types";
import { prettyDate } from "@/lib/format";

export interface Intent {
  target_local_date: string;
  required_work_hours: number | null;
  crew: { workload: WorkloadClass | null; acclimatised: boolean | null; crew_size: number };
  location: { name: string; lat: number; lon: number };
  timezone: string;
}

const src = (s: string) => (
  <span className="mono ml-2 rounded-sm border border-border px-1.5 py-0.5 text-[10px] uppercase text-ink-muted">
    {s}
  </span>
);

export function ConfirmCard({
  intent,
  locationSource,
  onConfirm,
  onCancel,
}: {
  intent: Intent;
  locationSource: "map pin" | "your message";
  onConfirm: (i: Intent) => void;
  onCancel: () => void;
}) {
  const [v, setV] = useState<Intent>(intent);
  const missing: string[] = [];
  if (v.required_work_hours == null) missing.push("work-hours");
  if (!v.crew.workload) missing.push("workload");
  if (v.crew.acclimatised == null) missing.push("whether the crew is used to the heat");

  const row = "flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-b border-border py-2 last:border-0";
  const ctl = "rounded border border-border bg-surface px-2 py-1 text-sm text-ink outline-none focus:border-accent";

  return (
    <div className="rounded-lg border border-border-strong bg-bg-raised p-4">
      <p className="text-sm font-medium text-ink">Here is what I have. Correct anything, then plan.</p>
      <div className="mt-2 text-sm">
        <div className={row}>
          <span className="text-ink-secondary">Location {src(locationSource)}</span>
          <span className="mono text-ink">
            {v.location.name && v.location.name !== "custom" ? v.location.name : `${v.location.lat.toFixed(3)}, ${v.location.lon.toFixed(3)}`}
          </span>
        </div>
        <div className={row}>
          <span className="text-ink-secondary">Day {src("your message")}</span>
          <input type="date" className={`${ctl} mono`} value={v.target_local_date}
            onChange={(e) => setV({ ...v, target_local_date: e.target.value })} />
        </div>
        <div className={row}>
          <label className="text-ink-secondary" htmlFor="cc-h">Work-hours {src("your message")}</label>
          <input id="cc-h" type="number" min={1} max={14} step={1} placeholder="?"
            className={`${ctl} mono w-16 ${v.required_work_hours == null ? "border-accent" : ""}`}
            value={v.required_work_hours ?? ""}
            onChange={(e) => setV({ ...v, required_work_hours: e.target.value ? +e.target.value : null })} />
        </div>
        <div className={row}>
          <span className="text-ink-secondary">Work type {src("your message")}</span>
          <select className={`${ctl} ${!v.crew.workload ? "border-accent" : ""}`}
            value={v.crew.workload ?? ""}
            onChange={(e) => setV({ ...v, crew: { ...v.crew, workload: (e.target.value || null) as any } })}>
            <option value="">choose</option>
            {WORKLOADS.map((w) => <option key={w.value} value={w.value}>{w.label}</option>)}
          </select>
        </div>
        <div className={row}>
          <span className="text-ink-secondary">Used to the heat {src("your message")}</span>
          <select className={`${ctl} ${v.crew.acclimatised == null ? "border-accent" : ""}`}
            value={v.crew.acclimatised == null ? "" : v.crew.acclimatised ? "yes" : "no"}
            onChange={(e) => setV({ ...v, crew: { ...v.crew, acclimatised: e.target.value === "" ? null : e.target.value === "yes" } })}>
            <option value="">choose</option>
            <option value="yes">Yes, more than two weeks</option>
            <option value="no">No, arrived recently</option>
          </select>
        </div>
      </div>
      {v.crew.workload && (
        <p className="mt-2 text-sm text-ink-muted">
          {WORKLOADS.find((w) => w.value === v.crew.workload)?.hint}
        </p>
      )}
      <div className="mt-3 flex items-center gap-2">
        <button
          type="button"
          disabled={missing.length > 0}
          onClick={() => onConfirm(v)}
          className="rounded bg-accent px-3.5 py-2 text-sm font-semibold text-accent-ink hover:bg-accent-hover disabled:opacity-50"
        >
          Plan the day
        </button>
        <button type="button" onClick={onCancel} className="text-sm text-ink-muted hover:text-ink">
          Cancel
        </button>
        {missing.length > 0 && (
          <span className="text-sm text-ink-muted">still need: {missing.join(", ")}</span>
        )}
      </div>
    </div>
  );
}
