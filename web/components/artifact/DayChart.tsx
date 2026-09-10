"use client";

import { useId, useMemo, useRef, useState } from "react";
import { scaleLinear } from "d3-scale";
import { line, area, curveMonotoneX } from "d3-shape";
import { fmt, fmtHour, prettyDate } from "@/lib/format";
import { STATE_GLYPH, STATE_LABEL, THRESHOLD_C, rampGradientStops } from "@/lib/ramp";
import { usePrefersReducedMotion } from "@/lib/hooks";
import type { HourRow, PlanMeta } from "@/lib/types";

const W = 760;
const H = 470;
const M = { t: 40, r: 22, b: 150, l: 44 };
const PLOT_B = H - M.b;
const WORK_H = 56;
const WORK_T = PLOT_B + 30;
const STRIP_T = WORK_T + WORK_H + 14;

export interface Policies {
  calendar: boolean;
  reactive: boolean;
  earlier: boolean;
}

function nowLocalHour(tz: string): number | null {
  try {
    const s = new Intl.DateTimeFormat("en-GB", {
      timeZone: tz, hour: "2-digit", minute: "2-digit", hour12: false,
    }).format(new Date());
    const [h, m] = s.split(":").map(Number);
    return h + m / 60;
  } catch {
    return null;
  }
}

export function DayChart({
  hours,
  meta,
  theme,
  focusedHour,
  onFocusHour,
  policies = { calendar: true, reactive: false, earlier: false },
  showBand = true,
  stage = 4,
}: {
  hours: HourRow[];
  meta: PlanMeta;
  theme: "light" | "dark";
  focusedHour: number | null;
  onFocusHour: (h: number | null) => void;
  policies?: Policies;
  showBand?: boolean;
  /** progressive build for the landing page: 1 forecast, 2 +stop line, 3 +fixed rule, 4 +plan */
  stage?: 1 | 2 | 3 | 4;
}) {
  const showThr = stage >= 2;
  const showFixed = stage >= 3 && policies.calendar;
  const showPlan = stage >= 4;
  const showEarlier = stage >= 4 && policies.earlier;
  const svgH = stage >= 3 ? H : PLOT_B + 40;
  const reduced = usePrefersReducedMotion();
  const gid = useId().replace(/:/g, "");
  const svgRef = useRef<SVGSVGElement>(null);
  const [kbd, setKbd] = useState(false);

  const nums = hours.map((h) => h.hour);
  const wMin = Math.min(...nums);
  const wMax = Math.max(...nums);
  const yLo = Math.min(24, Math.floor(Math.min(...hours.map((h) => h.wbgt_lo)) - 1));
  const yHi = Math.max(35, Math.ceil(Math.max(...hours.map((h) => h.wbgt_hi)) + 1));

  const x = useMemo(() => scaleLinear().domain([wMin - 0.5, wMax + 0.5]).range([M.l, W - M.r]), [wMin, wMax]);
  const y = useMemo(() => scaleLinear().domain([yLo, yHi]).range([PLOT_B, M.t]), [yLo, yHi]);

  const wbgtLine = line<HourRow>().x((d) => x(d.hour)).y((d) => y(d.wbgt_c)).curve(curveMonotoneX)(hours) as string;
  const wbgtArea = area<HourRow>().x((d) => x(d.hour)).y0(PLOT_B).y1((d) => y(d.wbgt_c)).curve(curveMonotoneX)(hours) as string;
  const bandArea = area<HourRow>().x((d) => x(d.hour)).y0((d) => y(d.wbgt_lo)).y1((d) => y(d.wbgt_hi)).curve(curveMonotoneX)(hours) as string;
  const grad = rampGradientStops(yLo, yHi, theme);
  const cellW = (x(wMax) - x(wMin)) / (hours.length - 1);
  const yThr = y(THRESHOLD_C);
  const focused = hours.find((h) => h.hour === focusedHour) ?? null;

  const today = new Date().toISOString().slice(0, 10) === meta.date;
  const nowH = today ? nowLocalHour(meta.request?.tz || "Asia/Qatar") : null;

  const peakHour = hours.reduce((a, b) => (b.wbgt_c > a.wbgt_c ? b : a));
  const restHours = hours.filter((h) => h.plan_state === "stop");
  const restMid = restHours.length ? restHours[Math.floor(restHours.length / 2)] : null;
  const banEnd = hours.find((h) => h.hour === 16) ?? null;

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

  const onSiteHours = hours.filter((h) => h.on_site);
  const onFirst = onSiteHours.length ? onSiteHours[0].hour : null;
  const onLast = onSiteHours.length ? onSiteHours[onSiteHours.length - 1].hour : null;

  const bars = (which: "plan" | "calendar" | "reactive" | "earlier", fill: string, hatch: boolean) =>
    hours.map((h) => {
      const frac =
        which === "plan" ? h.plan_work_fraction
        : which === "calendar" ? h.calendar_work_fraction
        : which === "earlier" ? h.earlier_start_work_fraction
        : h.reactive_work_fraction;
      const bh = frac * WORK_H;
      const bw = Math.max(5, cellW * (which === "plan" ? 0.56 : 0.7));
      const cx = x(h.hour);
      return hatch ? (
        <rect key={`${which}${h.hour}`} x={cx - bw / 2} y={WORK_T + WORK_H - bh} width={bw} height={bh}
          fill="none" stroke={fill} strokeWidth="1" strokeDasharray="2 2" opacity="0.85" />
      ) : (
        <rect key={`${which}${h.hour}`} x={cx - bw / 2} y={WORK_T + WORK_H - bh} width={bw} height={bh} rx="1.5"
          fill={fill} opacity={h.over_threshold && which === "plan" ? 0.5 : 0.92} />
      );
    });

  const caption =
    `Forecast WBGT for ${prettyDate(meta.date)} runs from ${fmt(hours[0].wbgt_c, 1)} C at ${fmtHour(hours[0].hour)} ` +
    `to a peak near ${fmt(peakHour.wbgt_c, 1)} C about ${fmtHour(peakHour.hour)}. The shaded band is the range of plausible forecasts. ` +
    (showThr ? `The dashed line at 32.1 C is the stop-work threshold. ` : ``) +
    (showFixed ? `The fixed calendar ban works full rate outside 10:00 to 15:30 whatever the forecast. ` : ``) +
    (showPlan
      ? `The plan works the cool early hours, rests ${restHours.length} hours through the peak, and resumes late. `
      : ``) +
    (showPlan && onFirst != null && onLast != null
      ? `The shaded band under the work bars is the on-site window, ${fmtHour(onFirst)} to ${fmtHour(onLast)}, held no wider than the fixed rule keeps the crew. `
      : ``) +
    `Colour is WBGT, cool blue to hot red with a hard break at 32.1 C.`;

  return (
    <figure role="group" aria-label={`WBGT forecast and work plan for ${prettyDate(meta.date)}`} className="flex flex-col gap-3">
      <svg ref={svgRef} viewBox={`0 0 ${W} ${svgH}`} className="w-full select-none" style={{ height: "auto" }}
        role="application" tabIndex={0} aria-describedby={`${gid}-d`} onKeyDown={onKey}
        onFocus={() => { setKbd(true); if (focusedHour == null) onFocusHour(hours[0].hour); }}
        onBlur={() => setKbd(false)} onPointerMove={(e) => pointerHour(e.clientX)} onPointerLeave={() => onFocusHour(null)}>
        <desc id={`${gid}-d`}>{caption}</desc>
        <defs>
          <linearGradient id={`${gid}-r`} x1="0" y1="0" x2="0" y2="1">
            {grad.map((s, i) => <stop key={i} offset={s.offset} stopColor={s.color} />)}
          </linearGradient>
          <clipPath id={`${gid}-c`}><path d={wbgtArea} /></clipPath>
        </defs>

        {y.ticks(5).map((t) => (
          <g key={t}>
            <line x1={M.l} x2={W - M.r} y1={y(t)} y2={y(t)} stroke="var(--border)" />
            <text x={M.l - 8} y={y(t)} dy="0.32em" textAnchor="end" className="mono" fontSize="10.5" fill="var(--text-muted)">{t}</text>
          </g>
        ))}

        {showBand && <path d={bandArea} fill="var(--text)" opacity={theme === "dark" ? 0.1 : 0.08} />}
        <g clipPath={`url(#${gid}-c)`}>
          <rect x={M.l} y={M.t} width={W - M.r - M.l} height={PLOT_B - M.t} fill={`url(#${gid}-r)`} opacity={theme === "dark" ? 0.6 : 0.68} />
        </g>
        <path d={wbgtLine} fill="none" stroke="var(--text)" strokeWidth="2" strokeLinejoin="round"
          className={reduced ? undefined : "draw-on"} style={{ ["--len" as string]: 1400 } as React.CSSProperties} />

        {showThr && (
          <>
            <line x1={M.l} x2={W - M.r} y1={yThr} y2={yThr} stroke="var(--text)" strokeWidth="1.4" strokeDasharray="2 3" />
            <text x={W - M.r} y={yThr - 5} textAnchor="end" className="mono" fontSize="10" fontWeight="600" fill="var(--text)">32.1 C stop-work</text>
          </>
        )}

        {/* direct annotations */}
        <g className="mono" fontSize="10" fill="var(--text-secondary)">
          <text x={x(peakHour.hour)} y={y(peakHour.wbgt_c) - 10} textAnchor="middle">
            Forecast peak, about {fmtHour(peakHour.hour)}
          </text>
          {showPlan && restMid && (
            <text x={x(restMid.hour)} y={M.t - 10} textAnchor="middle" fill="var(--state-stop)">
              Plan rests through the hottest hours
            </text>
          )}
          {showFixed && banEnd && (
            <text x={x(16)} y={PLOT_B + 16} textAnchor="middle" fill="var(--compare)">
              Fixed rule works the crew until here
            </text>
          )}
        </g>

        {showPlan && nowH != null && nowH >= wMin && nowH <= wMax && (
          <g>
            <line x1={x(nowH)} x2={x(nowH)} y1={M.t} y2={STRIP_T + 11} stroke="var(--accent)" strokeWidth="1.5" />
            <text x={x(nowH)} y={M.t - 26} textAnchor="middle" className="mono" fontSize="9.5" fill="var(--accent)">now</text>
          </g>
        )}

        {stage >= 3 && (
          <text x={M.l} y={WORK_T - 8} className="mono" fontSize="10" letterSpacing="0.06em" fill="var(--text-muted)">WORK RATE BY HOUR, SAME TOTAL</text>
        )}
        {showPlan && onFirst != null && onLast != null && (
          <g>
            <rect x={x(onFirst) - cellW / 2} y={WORK_T - 4} width={x(onLast) - x(onFirst) + cellW}
              height={WORK_H + 8} fill="var(--accent-weak)" opacity="0.5" />
            <text x={x(onFirst) - cellW / 2 + 3} y={WORK_T + WORK_H + 2} className="mono" fontSize="9"
              fill="var(--text-muted)">on site {fmtHour(onFirst)} to {fmtHour(onLast)}</text>
          </g>
        )}
        {showFixed && bars("calendar", "var(--compare)", true)}
        {showEarlier && bars("earlier", "var(--state-work)", true)}
        {showPlan && policies.reactive && bars("reactive", "var(--state-reduced)", true)}
        {showPlan && bars("plan", "var(--accent)", false)}
        {stage >= 3 && (
          <line x1={M.l} x2={W - M.r} y1={WORK_T + WORK_H} y2={WORK_T + WORK_H} stroke="var(--border-strong)" />
        )}

        {hours.map((h) => {
          const cx = x(h.hour);
          return (
            <g key={`s${h.hour}`}>
              {showPlan && <rect x={cx - cellW / 2 + 1} y={STRIP_T} width={cellW - 2} height="9" rx="2" fill={`var(--state-${h.plan_state})`} opacity="0.9" />}
              {showPlan && h.uncertain && <circle cx={cx} cy={STRIP_T + 4.5} r="1.6" fill="var(--bg)" />}
              <text x={cx} y={STRIP_T + 28} textAnchor="middle" className="mono" fontSize="10"
                opacity={showPlan && !h.on_site ? 0.4 : 1}
                fill={focusedHour === h.hour ? "var(--text)" : "var(--text-muted)"} fontWeight={focusedHour === h.hour ? 700 : 400}>{h.hour}</text>
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

      {showPlan && (
      <div aria-live="polite" className="flex flex-wrap items-center gap-x-5 gap-y-1 rounded border border-border bg-surface-2 px-3 py-2 text-sm">
        {focused ? (
          <>
            <span className="mono font-semibold text-ink">{fmtHour(focused.hour)}</span>
            <span className="mono">WBGT <strong className={focused.over_threshold ? "text-state-stop" : "text-ink"}>{fmt(focused.wbgt_c, 1)} C</strong>
              <span className="text-ink-muted"> ({fmt(focused.wbgt_lo, 1)} to {fmt(focused.wbgt_hi, 1)})</span></span>
            <span className="text-ink-secondary">{focused.cycle}</span>
            <span className="mono text-micro uppercase" style={{ color: `var(--state-${focused.plan_state})` }}>{STATE_GLYPH[focused.plan_state]} {STATE_LABEL[focused.plan_state]}</span>
          </>
        ) : (
          <span className="text-ink-muted">Point at the chart, or focus it and use the arrow keys, for an hour by hour readout.</span>
        )}
      </div>
      )}
      {(showPlan || showFixed) && <Legend policies={policies} showFixed={showFixed} showPlan={showPlan} />}
      <figcaption className="sr-only">{caption}</figcaption>
    </figure>
  );
}

function Legend({ policies, showFixed, showPlan }: { policies: Policies; showFixed: boolean; showPlan: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm text-ink-secondary">
      {showPlan && <span className="inline-flex items-center gap-2"><span className="h-2.5 w-4 rounded-sm bg-accent" /> plan</span>}
      {showPlan && <span className="inline-flex items-center gap-2"><span className="h-2.5 w-4 rounded-sm bg-accent-weak" /> on-site window</span>}
      {showFixed && <span className="inline-flex items-center gap-2"><span className="h-2.5 w-4 rounded-sm border" style={{ borderColor: "var(--compare)" }} /> fixed rule</span>}
      {showPlan && policies.earlier && <span className="inline-flex items-center gap-2"><span className="h-2.5 w-4 rounded-sm border" style={{ borderColor: "var(--state-work)" }} /> earlier start</span>}
      {showPlan && policies.reactive && <span className="inline-flex items-center gap-2"><span className="h-2.5 w-4 rounded-sm border" style={{ borderColor: "var(--state-reduced)" }} /> stop when hot</span>}
      {showPlan && (["work", "reduced", "stop"] as const).map((s) => (
        <span key={s} className="inline-flex items-center gap-1.5"><span style={{ color: `var(--state-${s})` }}>{STATE_GLYPH[s]}</span>{STATE_LABEL[s]}</span>
      ))}
      {showPlan && <span className="text-ink-muted">dot = forecast uncertain here</span>}
    </div>
  );
}
