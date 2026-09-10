"use client";

import { useEffect, useState } from "react";
import { fmt } from "@/lib/format";
import { Reveal } from "./Reveal";

type Day = {
  date: string;
  hours: number[];
  wbgt_c: number[];
  plan_fraction: number[];
  calendar_fraction: number[];
  plan_peak: number;
  calendar_peak: number;
  reactive_peak: number;
  daily_max_wbgt: number;
};
type Week = {
  slug: string;
  title: string;
  subtitle: string;
  note: string;
  threshold_c: number;
  required_work_hours: number;
  pct_peak_reduction: number;
  days: Day[];
};

const THR = 32.1;

function DayCard({ d }: { d: Day }) {
  const w = 132;
  const h = 66;
  const lo = 24;
  const hi = Math.max(40, Math.ceil(Math.max(...d.wbgt_c) + 1));
  const x = (i: number) => (i / (d.hours.length - 1)) * w;
  const y = (v: number) => h - ((v - lo) / (hi - lo)) * h;
  const linePts = d.wbgt_c.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const yThr = y(THR);
  const label = new Date(d.date + "T00:00:00Z").toLocaleDateString("en-GB", {
    weekday: "short", timeZone: "UTC",
  });
  return (
    <li className="flex flex-col gap-1.5 rounded-lg border border-border bg-surface p-2.5">
      <div className="flex items-baseline justify-between">
        <span className="mono text-micro uppercase text-ink-muted">{label}</span>
        <span className="mono text-sm text-ink">{fmt(d.daily_max_wbgt, 1)}</span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full" style={{ height: "auto" }} aria-hidden>
        <line x1="0" x2={w} y1={yThr} y2={yThr} stroke="var(--text)" strokeWidth="1" strokeDasharray="2 3" opacity="0.7" />
        {d.hours.map((_, i) => {
          const bw = w / d.hours.length - 1.5;
          const px = x(i) - bw / 2 + 0.75;
          return (
            <g key={i}>
              <rect x={px} y={h - d.calendar_fraction[i] * 14} width={bw} height={d.calendar_fraction[i] * 14}
                fill="none" stroke="var(--compare)" strokeWidth="0.8" opacity="0.8" />
              <rect x={px} y={h - d.plan_fraction[i] * 14} width={bw} height={d.plan_fraction[i] * 14}
                rx="0.5" fill="var(--accent)" opacity="0.9" />
            </g>
          );
        })}
        <path d={linePts} fill="none" stroke="var(--text)" strokeWidth="1.5" strokeLinejoin="round" />
      </svg>
      <div className="mono flex items-center justify-between text-micro">
        <span className="text-ink-muted">worst load</span>
        <span>
          <span className="text-accent">{fmt(d.plan_peak, 1)}</span>
          <span className="text-ink-muted"> vs {fmt(d.calendar_peak, 1)}</span>
        </span>
      </div>
    </li>
  );
}

export function Replay() {
  const [week, setWeek] = useState<Week | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "empty" | "error">("loading");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const idx = await fetch("/api/replay", { cache: "no-store" }).then((r) => r.json());
        const first = idx?.weeks?.[0];
        if (!first) {
          if (!cancelled) setState("empty");
          return;
        }
        const wk = await fetch(`/api/replay/${first.slug}`, { cache: "no-store" }).then((r) => r.json());
        if (cancelled) return;
        if (!wk?.days?.length) {
          setState("empty");
          return;
        }
        setWeek(wk);
        setState("ready");
      } catch {
        if (!cancelled) setState("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="py-20" aria-labelledby="replay-h">
      <div className="mx-auto max-w-content px-5">
        <Reveal>
          <p className="eyebrow">Worked example</p>
          <h2 id="replay-h" className="mt-2 max-w-prose text-h2 text-ink">
            A real past week, hour by hour.
          </h2>
        </Reveal>

        {state === "loading" && (
          <div className="mt-8 grid grid-cols-2 gap-2.5 sm:grid-cols-4 lg:grid-cols-7">
            {Array.from({ length: 7 }).map((_, i) => (
              <div key={i} className="skeleton h-32 rounded-lg" />
            ))}
          </div>
        )}

        {state === "error" && (
          <p className="mt-8 rounded-lg border border-border bg-surface p-4 text-ink-secondary">
            The replay data needs the API running. Start it and reload.
          </p>
        )}
        {state === "empty" && (
          <p className="mt-8 rounded-lg border border-border bg-surface p-4 text-ink-secondary">
            No replay weeks are built yet. Run <span className="mono">scripts/build_replay_weeks.py</span>.
          </p>
        )}

        {state === "ready" && week && (
          <Reveal className="mt-8">
            <p className="text-lg text-ink-secondary">
              <strong className="text-ink">{week.title.replace(/^Doha, /, "")}</strong> in Doha: the plan&apos;s
              work rate against the fixed 10:00 to 15:30 rule, and the day&apos;s WBGT curve, for each
              day, at the same{" "}
              <strong className="mono text-ink">{fmt(week.required_work_hours, 0)}</strong> hours worked.
            </p>
            <p className="mono mt-1 text-sm text-ink-muted">{week.subtitle}</p>

            <ol className="mt-5 grid grid-cols-2 gap-2.5 sm:grid-cols-4 lg:grid-cols-7">
              {week.days.map((d) => (
                <DayCard key={d.date} d={d} />
              ))}
            </ol>

            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-secondary">
              <span className="inline-flex items-center gap-2"><span className="h-2.5 w-4 rounded-sm bg-accent" /> plan work rate</span>
              <span className="inline-flex items-center gap-2"><span className="h-2.5 w-4 rounded-sm border" style={{ borderColor: "var(--compare)" }} /> fixed rule</span>
              <span className="inline-flex items-center gap-2"><span className="h-0 w-4 border-t border-dashed border-[var(--text)]" /> 32.1 stop-work line</span>
            </div>

            <p className="mt-3 max-w-prose text-sm text-ink-muted">{week.note}</p>
          </Reveal>
        )}
      </div>
    </section>
  );
}
