"use client";

import { useId, useMemo, useRef, useState } from "react";
import { scaleLinear } from "d3-scale";
import { line, area, curveMonotoneX } from "d3-shape";
import { fmt, fmtHour, prettyDate } from "@/lib/format";
import {
  STATE_GLYPH,
  STATE_LABEL,
  THRESHOLD_C,
  rampGradientStops,
} from "@/lib/ramp";
import { usePrefersReducedMotion } from "@/lib/hooks";
import type { HourRow, PlanMeta } from "@/lib/types";

const W = 720;
const H = 440;
const M = { t: 24, r: 20, b: 148, l: 44 };
const PLOT_B = H - M.b;
const WORK_H = 58;
const WORK_T = PLOT_B + 26;
const STRIP_T = WORK_T + WORK_H + 14;

export function DayChart({
  hours,
  meta,
  theme,
  focusedHour,
  onFocusHour,
  compact = false,
}: {
  hours: HourRow[];
  meta: PlanMeta;
  theme: "light" | "dark";
  focusedHour: number | null;
  onFocusHour: (h: number | null) => void;
  compact?: boolean;
}) {
  const reduced = usePrefersReducedMotion();
  const gid = useId().replace(/:/g, "");
  const svgRef = useRef<SVGSVGElement>(null);
  const [kbd, setKbd] = useState(false);

  const nums = hours.map((h) => h.hour);
  const wMin = Math.min(...nums);
  const wMax = Math.max(...nums);
  const yLo = Math.min(24, Math.floor(Math.min(...hours.map((h) => h.wbgt_c)) - 1));
  const yHi = Math.max(35, Math.ceil(Math.max(...hours.map((h) => h.wbgt_c)) + 1));

  const x = useMemo(
    () => scaleLinear().domain([wMin - 0.5, wMax + 0.5]).range([M.l, W - M.r]),
    [wMin, wMax],
  );
  const y = useMemo(
    () => scaleLinear().domain([yLo, yHi]).range([PLOT_B, M.t]),
    [yLo, yHi],
  );

  const wbgtLine = line<HourRow>().x((d) => x(d.hour)).y((d) => y(d.wbgt_c)).curve(curveMonotoneX)(hours) as string;
  const wbgtArea = area<HourRow>().x((d) => x(d.hour)).y0(PLOT_B).y1((d) => y(d.wbgt_c)).curve(curveMonotoneX)(hours) as string;
  const grad = rampGradientStops(yLo, yHi, theme);
  const cellW = (x(wMax) - x(wMin)) / (hours.length - 1);
  const yThr = y(THRESHOLD_C);
  const focused = hours.find((h) => h.hour === focusedHour) ?? null;

  function pointerHour(clientX: number) {
    const el = svgRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const hv = x.invert(((clientX - r.left) / r.width) * W);
    onFocusHour(hours.reduce((a, b) => (Math.abs(b.hour - hv) < Math.abs(a.hour - hv) ? b : a)).hour);
  }
  function onKey(e: React.KeyboardEvent) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    setKbd(true);
    let i = nums.indexOf(focusedHour ?? nums[0]);
    if (e.key === "ArrowLeft") i = Math.max(0, i - 1);
    if (e.key === "ArrowRight") i = Math.min(hours.length - 1, i + 1);
    if (e.key === "Home") i = 0;
    if (e.key === "End") i = hours.length - 1;
    onFocusHour(nums[i]);
  }

  const peak = Math.max(...hours.map((h) => h.wbgt_c));
  const over = hours.filter((h) => h.over_threshold).length;
  const rest = hours.filter((h) => h.plan_state === "stop").length;
  const caption =
    `Forecast WBGT for ${prettyDate(meta.date)} runs from ${fmt(hours[0].wbgt_c, 1)} C at ${fmtHour(hours[0].hour)} ` +
    `to a peak of ${fmt(peak, 1)} C, over the 32.1 C stop-work line for ${over} of ${hours.length} hours. ` +
    `The plan works the cool early hours at full rate, eases through the peak with ${rest} hours at rest, and resumes late. ` +
    `The calendar ban instead works full rate outside 10:00 to 15:30 regardless of the forecast. Both deliver the same work-hours. ` +
    `Colour is WBGT, cool blue to hot red with a hard break at 32.1 C; plan state is also shown as ${STATE_GLYPH.work} work, ${STATE_GLYPH.reduced} reduced, ${STATE_GLYPH.stop} stop.`;

  return (
    <figure
      role="group"
      aria-label={`WBGT forecast and work plan for ${prettyDate(meta.date)}`}
      className="flex flex-col gap-3"
    >
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full select-none"
        style={{ height: "auto" }}
        role="application"
        tabIndex={0}
        aria-describedby={`${gid}-d`}
        onKeyDown={onKey}
        onFocus={() => {
          setKbd(true);
          if (focusedHour == null) onFocusHour(hours[0].hour);
        }}
        onBlur={() => setKbd(false)}
        onPointerMove={(e) => pointerHour(e.clientX)}
        onPointerLeave={() => onFocusHour(null)}
      >
        <desc id={`${gid}-d`}>{caption}</desc>
        <defs>
          <linearGradient id={`${gid}-r`} x1="0" y1="0" x2="0" y2="1">
            {grad.map((s, i) => (
              <stop key={i} offset={s.offset} stopColor={s.color} />
            ))}
          </linearGradient>
          <clipPath id={`${gid}-c`}>
            <path d={wbgtArea} />
          </clipPath>
          <pattern id={`${gid}-h`} width="5" height="5" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
            <line x1="0" y1="0" x2="0" y2="5" stroke="var(--compare)" strokeWidth="1.3" />
          </pattern>
        </defs>

        {y.ticks(5).map((t) => (
          <g key={t}>
            <line x1={M.l} x2={W - M.r} y1={y(t)} y2={y(t)} stroke="var(--border)" />
            <text x={M.l - 8} y={y(t)} dy="0.32em" textAnchor="end" className="mono" fontSize="10.5" fill="var(--text-muted)">
              {t}
            </text>
          </g>
        ))}

        <g clipPath={`url(#${gid}-c)`}>
          <rect x={M.l} y={M.t} width={W - M.r - M.l} height={PLOT_B - M.t} fill={`url(#${gid}-r)`} opacity={theme === "dark" ? 0.66 : 0.72} />
        </g>
        <path
          d={wbgtLine}
          fill="none"
          stroke="var(--text)"
          strokeWidth="2"
          strokeLinejoin="round"
          className={reduced ? undefined : "draw-on"}
          style={{ ["--len" as string]: 1400 } as React.CSSProperties}
        />

        <line x1={M.l} x2={W - M.r} y1={yThr} y2={yThr} stroke="var(--text)" strokeWidth="1.4" strokeDasharray="2 3" />
        <text x={W - M.r} y={yThr - 5} textAnchor="end" className="mono" fontSize="10" fontWeight="600" fill="var(--text)">
          32.1 C stop-work
        </text>

        <text x={M.l} y={WORK_T - 8} className="mono" fontSize="10" letterSpacing="0.06em" fill="var(--text-muted)">
          WORK RATE BY HOUR, SAME TOTAL
        </text>
        {hours.map((h) => {
          const cx = x(h.hour);
          const bw = Math.max(6, cellW * 0.6);
          const calH = h.calendar_work_fraction * WORK_H;
          const planH = h.plan_work_fraction * WORK_H;
          return (
            <g key={`w${h.hour}`}>
              <rect x={cx - bw / 2} y={WORK_T + WORK_H - calH} width={bw} height={calH} fill={`url(#${gid}-h)`} stroke="var(--compare)" strokeWidth="1" opacity="0.85" />
              <rect x={cx - bw / 2} y={WORK_T + WORK_H - planH} width={bw} height={planH} rx="1.5" fill="var(--accent)" opacity={h.over_threshold ? 0.55 : 0.92} />
              {h.over_threshold && planH > 3 && (
                <rect x={cx - bw / 2} y={WORK_T + WORK_H - planH} width={bw} height={planH} rx="1.5" fill="none" stroke="var(--state-stop)" strokeWidth="1.2" strokeDasharray="2 2" />
              )}
            </g>
          );
        })}
        <line x1={M.l} x2={W - M.r} y1={WORK_T + WORK_H} y2={WORK_T + WORK_H} stroke="var(--border-strong)" />

        {hours.map((h) => {
          const cx = x(h.hour);
          return (
            <g key={`s${h.hour}`}>
              <rect x={cx - cellW / 2 + 1} y={STRIP_T} width={cellW - 2} height="9" rx="2" fill={`var(--state-${h.plan_state})`} opacity="0.9" />
              <text x={cx} y={STRIP_T + 28} textAnchor="middle" className="mono" fontSize="10" fill={focusedHour === h.hour ? "var(--text)" : "var(--text-muted)"} fontWeight={focusedHour === h.hour ? 700 : 400}>
                {h.hour}
              </text>
            </g>
          );
        })}

        {focused && (
          <g pointerEvents="none">
            <line x1={x(focused.hour)} x2={x(focused.hour)} y1={M.t} y2={STRIP_T + 11} stroke="var(--text)" strokeDasharray="1 3" />
            <circle cx={x(focused.hour)} cy={y(focused.wbgt_c)} r="4.5" fill="var(--surface)" stroke="var(--text)" strokeWidth="2" />
            {kbd && <rect x={x(focused.hour) - cellW / 2} y={M.t} width={cellW} height={STRIP_T + 11 - M.t} fill="var(--accent-weak)" />}
          </g>
        )}
      </svg>

      {!compact && (
        <div aria-live="polite" className="flex flex-wrap items-center gap-x-5 gap-y-1 rounded border border-border bg-surface-2 px-3 py-2 text-sm">
          {focused ? (
            <>
              <span className="mono font-semibold text-ink">{fmtHour(focused.hour)}</span>
              <span className="mono">
                WBGT{" "}
                <strong className={focused.over_threshold ? "text-state-stop" : "text-ink"}>{fmt(focused.wbgt_c, 1)} C</strong>
              </span>
              <span className="mono text-ink-secondary">
                plan <strong className="text-ink">{fmt(focused.plan_work_fraction * 100, 0)}%</strong> · ban{" "}
                <strong className="text-ink">{fmt(focused.calendar_work_fraction * 100, 0)}%</strong>
              </span>
              <span className="mono text-ink-secondary">
                retained load <strong className="text-ink">{fmt(focused.retained_load_plan, 2)}</strong> vs{" "}
                <strong className="text-ink">{fmt(focused.retained_load_calendar, 2)}</strong>
              </span>
              <span className="mono text-micro uppercase" style={{ color: `var(--state-${focused.plan_state})` }}>
                {STATE_GLYPH[focused.plan_state]} {STATE_LABEL[focused.plan_state]}
              </span>
            </>
          ) : (
            <span className="text-ink-muted">Point at the chart, or focus it and use the arrow keys, for an hour by hour readout.</span>
          )}
        </div>
      )}
      <Legend />
      <figcaption className="sr-only">{caption}</figcaption>
    </figure>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm text-ink-secondary">
      <span className="inline-flex items-center gap-2">
        <span className="h-2.5 w-4 rounded-sm bg-accent" /> optimiser plan
      </span>
      <span className="inline-flex items-center gap-2">
        <span className="h-2.5 w-4 rounded-sm border" style={{ borderColor: "var(--compare)" }} /> calendar ban
      </span>
      {(["work", "reduced", "stop"] as const).map((s) => (
        <span key={s} className="inline-flex items-center gap-1.5">
          <span style={{ color: `var(--state-${s})` }}>{STATE_GLYPH[s]}</span>
          {STATE_LABEL[s]}
        </span>
      ))}
    </div>
  );
}
