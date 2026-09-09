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
  wbgtColor,
} from "@/lib/ramp";
import { usePrefersReducedMotion } from "@/lib/hooks";
import type { HourRow, PlanMeta } from "@/lib/types";

const W = 760;
const H = 452;
const M = { t: 26, r: 22, b: 150, l: 48 };
const PLOT_B = H - M.b; // bottom of the WBGT plot
const WORK_H = 62; // height of the work-fraction band
const WORK_T = PLOT_B + 26;
const STRIP_T = WORK_T + WORK_H + 14;

export function HeroChart({
  hours,
  meta,
  theme,
  focusedHour,
  onFocusHour,
}: {
  hours: HourRow[];
  meta: PlanMeta;
  theme: "light" | "dark";
  focusedHour: number | null;
  onFocusHour: (h: number | null) => void;
}) {
  const reduced = usePrefersReducedMotion();
  const gradId = useId().replace(/:/g, "");
  const svgRef = useRef<SVGSVGElement>(null);
  const [kbdActive, setKbdActive] = useState(false);

  const hourNums = hours.map((h) => h.hour);
  const wMin = Math.min(...hourNums);
  const wMax = Math.max(...hourNums);

  const yDomainLo = Math.min(24, Math.floor(Math.min(...hours.map((h) => h.wbgt_c)) - 1));
  const yDomainHi = Math.max(35, Math.ceil(Math.max(...hours.map((h) => h.wbgt_c)) + 1));

  const x = useMemo(
    () => scaleLinear().domain([wMin - 0.5, wMax + 0.5]).range([M.l, W - M.r]),
    [wMin, wMax],
  );
  const y = useMemo(
    () => scaleLinear().domain([yDomainLo, yDomainHi]).range([PLOT_B, M.t]),
    [yDomainLo, yDomainHi],
  );

  const wbgtLine = line<HourRow>()
    .x((d) => x(d.hour))
    .y((d) => y(d.wbgt_c))
    .curve(curveMonotoneX)(hours) as string;

  const wbgtArea = area<HourRow>()
    .x((d) => x(d.hour))
    .y0(PLOT_B)
    .y1((d) => y(d.wbgt_c))
    .curve(curveMonotoneX)(hours) as string;

  const gradStops = rampGradientStops(yDomainLo, yDomainHi, theme);
  const cellW = (x(wMax) - x(wMin)) / (hours.length - 1);
  const yThresh = y(THRESHOLD_C);

  const focused = hours.find((h) => h.hour === focusedHour) ?? null;

  function pointerHour(clientX: number) {
    const svg = svgRef.current;
    if (!svg) return;
    const r = svg.getBoundingClientRect();
    const px = ((clientX - r.left) / r.width) * W;
    const hv = x.invert(px);
    const nearest = hours.reduce((a, b) =>
      Math.abs(b.hour - hv) < Math.abs(a.hour - hv) ? b : a,
    );
    onFocusHour(nearest.hour);
  }

  function onKey(e: React.KeyboardEvent) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
    e.preventDefault();
    setKbdActive(true);
    const cur = focusedHour ?? hours[0].hour;
    let idx = hourNums.indexOf(cur);
    if (e.key === "ArrowLeft") idx = Math.max(0, idx - 1);
    if (e.key === "ArrowRight") idx = Math.min(hours.length - 1, idx + 1);
    if (e.key === "Home") idx = 0;
    if (e.key === "End") idx = hours.length - 1;
    onFocusHour(hourNums[idx]);
  }

  const lineLen = 1400; // generous upper bound for stroke-dashoffset draw-on

  const caption = useMemo(() => {
    const over = hours.filter((h) => h.over_threshold).length;
    const stops = hours.filter((h) => h.plan_state === "stop").length;
    return `Forecast WBGT for ${prettyDate(meta.date)} rises from ${fmt(
      hours[0].wbgt_c,
      1,
    )} °C at ${fmtHour(hours[0].hour)} to a peak of ${fmt(
      Math.max(...hours.map((h) => h.wbgt_c)),
      1,
    )} °C, crossing the 32.1 °C stop-work line for ${over} of ${
      hours.length
    } hours. The optimiser plan works the cool early hours at full rate, tapers through the heat of the day (${stops} hours at rest), and resumes late; the calendar ban instead works full-rate outside 10:00–15:30 regardless of the forecast. Both deliver the same work-hours. Colour encodes WBGT (cool blue to hot red, hard break at 32.1 °C); the plan's per-hour state is also shown as ${STATE_GLYPH.work} work, ${STATE_GLYPH.reduced} reduced, ${STATE_GLYPH.stop} stop.`;
  }, [hours, meta.date]);

  return (
    <figure
      role="group"
      aria-label={`WBGT forecast and work plan for ${meta.location.lat.toFixed(
        2,
      )}, ${meta.location.lon.toFixed(2)} on ${prettyDate(meta.date)}`}
      className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4"
    >
      <div className="relative">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          className="w-full select-none"
          style={{ height: "auto" }}
          role="application"
          tabIndex={0}
          aria-describedby={`${gradId}-desc`}
          onKeyDown={onKey}
          onFocus={() => {
            setKbdActive(true);
            if (focusedHour == null) onFocusHour(hours[0].hour);
          }}
          onBlur={() => setKbdActive(false)}
          onPointerMove={(e) => pointerHour(e.clientX)}
          onPointerLeave={() => onFocusHour(null)}
        >
          <desc id={`${gradId}-desc`}>{caption}</desc>
          <defs>
            <linearGradient id={`${gradId}-ramp`} x1="0" y1="0" x2="0" y2="1">
              {gradStops.map((s, i) => (
                <stop key={i} offset={s.offset} stopColor={s.color} />
              ))}
            </linearGradient>
            <clipPath id={`${gradId}-clip`}>
              <path d={wbgtArea} />
            </clipPath>
            <pattern
              id={`${gradId}-hatch`}
              width="5"
              height="5"
              patternTransform="rotate(45)"
              patternUnits="userSpaceOnUse"
            >
              <line x1="0" y1="0" x2="0" y2="5" stroke="var(--compare)" strokeWidth="1.4" />
            </pattern>
          </defs>

          {/* y grid + ticks */}
          {y.ticks(5).map((t) => (
            <g key={t}>
              <line
                x1={M.l}
                x2={W - M.r}
                y1={y(t)}
                y2={y(t)}
                stroke="var(--border)"
                strokeWidth="1"
              />
              <text
                x={M.l - 8}
                y={y(t)}
                dy="0.32em"
                textAnchor="end"
                className="tnum"
                fontSize="11"
                fill="var(--text-muted)"
              >
                {t}
              </text>
            </g>
          ))}

          {/* WBGT area filled with the ramp, plus a crisp curve */}
          <g clipPath={`url(#${gradId}-clip)`}>
            <rect
              x={M.l}
              y={M.t}
              width={W - M.r - M.l}
              height={PLOT_B - M.t}
              fill={`url(#${gradId}-ramp)`}
              opacity={theme === "dark" ? 0.62 : 0.72}
            />
          </g>
          <path
            d={wbgtLine}
            fill="none"
            stroke="var(--text)"
            strokeWidth="2"
            strokeLinejoin="round"
            className={reduced ? undefined : "draw-on"}
            style={{ ["--len" as string]: lineLen } as React.CSSProperties}
          />

          {/* 32.1 C stop-work rule */}
          <line
            x1={M.l}
            x2={W - M.r}
            y1={yThresh}
            y2={yThresh}
            stroke="var(--text)"
            strokeWidth="1.5"
            strokeDasharray="2 3"
          />
          <text
            x={W - M.r}
            y={yThresh - 6}
            textAnchor="end"
            fontSize="10.5"
            fontWeight="600"
            fill="var(--text)"
          >
            32.1 °C — stop-work (Decision 17/2021)
          </text>

          {/* work-fraction band: calendar (ghost) behind, plan (solid) in front */}
          <text
            x={M.l}
            y={WORK_T - 8}
            fontSize="10.5"
            letterSpacing="0.06em"
            fill="var(--text-muted)"
          >
            WORK RATE BY HOUR — SAME TOTAL, DIFFERENT SHAPE
          </text>
          {hours.map((h) => {
            const cx = x(h.hour);
            const bw = Math.max(6, cellW * 0.62);
            const calH = h.calendar_work_fraction * WORK_H;
            const planH = h.plan_work_fraction * WORK_H;
            return (
              <g key={`w-${h.hour}`}>
                <rect
                  x={cx - bw / 2}
                  y={WORK_T + WORK_H - calH}
                  width={bw}
                  height={calH}
                  fill={`url(#${gradId}-hatch)`}
                  stroke="var(--compare)"
                  strokeWidth="1"
                  opacity="0.9"
                />
                <rect
                  x={cx - bw / 2}
                  y={WORK_T + WORK_H - planH}
                  width={bw}
                  height={planH}
                  rx="1.5"
                  fill="var(--accent)"
                  opacity={h.over_threshold ? 0.55 : 0.92}
                />
                {h.over_threshold && planH > 3 && (
                  <rect
                    x={cx - bw / 2}
                    y={WORK_T + WORK_H - planH}
                    width={bw}
                    height={planH}
                    rx="1.5"
                    fill="none"
                    stroke="var(--state-stop)"
                    strokeWidth="1.2"
                    strokeDasharray="2 2"
                  />
                )}
              </g>
            );
          })}
          <line
            x1={M.l}
            x2={W - M.r}
            y1={WORK_T + WORK_H}
            y2={WORK_T + WORK_H}
            stroke="var(--border-strong)"
          />

          {/* plan state strip + x labels */}
          {hours.map((h) => {
            const cx = x(h.hour);
            return (
              <g key={`s-${h.hour}`}>
                <rect
                  x={cx - cellW / 2 + 1}
                  y={STRIP_T}
                  width={cellW - 2}
                  height="10"
                  rx="2"
                  fill={`var(--state-${h.plan_state})`}
                  opacity="0.9"
                />
                <text
                  x={cx}
                  y={STRIP_T + 30}
                  textAnchor="middle"
                  className="tnum"
                  fontSize="10.5"
                  fill={
                    focusedHour === h.hour ? "var(--text)" : "var(--text-muted)"
                  }
                  fontWeight={focusedHour === h.hour ? 700 : 400}
                >
                  {h.hour}
                </text>
              </g>
            );
          })}

          {/* crosshair */}
          {focused && (
            <g pointerEvents="none">
              <line
                x1={x(focused.hour)}
                x2={x(focused.hour)}
                y1={M.t}
                y2={STRIP_T + 12}
                stroke="var(--text)"
                strokeWidth="1"
                strokeDasharray="1 3"
              />
              <circle
                cx={x(focused.hour)}
                cy={y(focused.wbgt_c)}
                r="4.5"
                fill="var(--surface)"
                stroke="var(--text)"
                strokeWidth="2"
              />
              {kbdActive && (
                <rect
                  x={x(focused.hour) - cellW / 2}
                  y={M.t}
                  width={cellW}
                  height={STRIP_T + 12 - M.t}
                  fill="var(--accent-weak)"
                />
              )}
            </g>
          )}

        </svg>
      </div>

      {/* precise readout */}
      <div
        aria-live="polite"
        className="flex flex-wrap items-center gap-x-6 gap-y-1 rounded border border-border bg-surface-sunken px-4 py-3 text-sm"
      >
        {focused ? (
          <>
            <span className="tnum font-semibold text-ink">
              {fmtHour(focused.hour)}
            </span>
            <span className="tnum">
              WBGT{" "}
              <strong
                className={
                  focused.over_threshold
                    ? "font-semibold text-state-stop"
                    : "text-ink"
                }
              >
                {fmt(focused.wbgt_c, 1)} °C
              </strong>
            </span>
            <span className="tnum text-ink-secondary">
              plan{" "}
              <strong className="text-ink">
                {fmt(focused.plan_work_fraction * 100, 0)}%
              </strong>{" "}
              · calendar{" "}
              <strong className="text-ink">
                {fmt(focused.calendar_work_fraction * 100, 0)}%
              </strong>
            </span>
            <span className="tnum text-ink-secondary">
              retained load{" "}
              <strong className="text-ink">
                {fmt(focused.retained_load_plan, 2)}
              </strong>{" "}
              vs{" "}
              <strong className="text-ink">
                {fmt(focused.retained_load_calendar, 2)}
              </strong>
            </span>
            <span
              className="inline-flex items-center gap-1.5 text-caption uppercase"
              style={{ color: `var(--state-${focused.plan_state})` }}
            >
              {STATE_GLYPH[focused.plan_state]} {STATE_LABEL[focused.plan_state]}
            </span>
          </>
        ) : (
          <span className="text-ink-muted">
            Hover the chart, or focus it and use ← → , for an hour-by-hour
            readout.
          </span>
        )}
      </div>

      <Legend />
      <p className="text-sm text-ink-muted sm:hidden">
        Narrow screen — rotate for detail, or read the hourly table below.
      </p>
      <figcaption className="sr-only">{caption}</figcaption>
    </figure>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-ink-secondary">
      <span className="inline-flex items-center gap-2">
        <span className="h-2.5 w-4 rounded-sm bg-accent" /> optimiser plan
      </span>
      <span className="inline-flex items-center gap-2">
        <span
          className="h-2.5 w-4 rounded-sm border"
          style={{ borderColor: "var(--compare)", background: "transparent" }}
        />
        calendar ban
      </span>
      <span className="text-ink-muted">·</span>
      {(["work", "reduced", "stop"] as const).map((s) => (
        <span key={s} className="inline-flex items-center gap-1.5">
          <span style={{ color: `var(--state-${s})` }}>{STATE_GLYPH[s]}</span>
          {STATE_LABEL[s]}
        </span>
      ))}
      <span className="text-ink-muted">
        · dashed outline = plan works above 32.1 °C
      </span>
    </div>
  );
}
