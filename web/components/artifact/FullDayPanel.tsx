"use client";

import { useId, useMemo } from "react";
import { scaleLinear } from "d3-scale";
import { line, area, curveMonotoneX } from "d3-shape";
import { fmt, fmtHour } from "@/lib/format";
import { THRESHOLD_C, rampGradientStops } from "@/lib/ramp";
import { usePrefersReducedMotion } from "@/lib/hooks";
import type { DayCurve } from "@/lib/types";

const W = 760;
const H = 250;
const M = { t: 34, r: 22, b: 52, l: 40 };
const PLOT_B = H - M.b;
const DAY_LO = 5;
const DAY_HI = 18;

export function FullDayPanel({
  curve,
  theme,
}: {
  curve: DayCurve;
  theme: "light" | "dark";
}) {
  const reduced = usePrefersReducedMotion();
  const gid = useId().replace(/:/g, "");
  const pts = curve.points;

  const yLo = Math.min(24, Math.floor(Math.min(...pts.map((p) => p.wbgt_c)) - 1));
  const yHi = Math.max(35, Math.ceil(Math.max(...pts.map((p) => p.wbgt_c)) + 1));

  const x = useMemo(
    () => scaleLinear().domain([-0.5, 23.5]).range([M.l, W - M.r]),
    [],
  );
  const y = useMemo(
    () => scaleLinear().domain([yLo, yHi]).range([PLOT_B, M.t]),
    [yLo, yHi],
  );

  const curveLine = line<typeof pts[number]>()
    .x((d) => x(d.hour))
    .y((d) => y(d.wbgt_c))
    .curve(curveMonotoneX)(pts) as string;
  const curveArea = area<typeof pts[number]>()
    .x((d) => x(d.hour))
    .y0(PLOT_B)
    .y1((d) => y(d.wbgt_c))
    .curve(curveMonotoneX)(pts) as string;

  const grad = rampGradientStops(yLo, yHi, theme);
  const yThr = y(THRESHOLD_C);

  const over = pts.filter((p) => p.over_threshold).map((p) => p.hour);
  const overRange =
    over.length > 0
      ? `${fmtHour(Math.min(...over))} to ${fmtHour(Math.max(...over) + 1)}`
      : null;

  const cw = curve.coolest_window;
  const cwLo = cw ? Number(cw.start.slice(0, 2)) : null;
  const cwHi = cw ? Number(cw.end.slice(0, 2)) : null;

  const caption =
    `Forecast WBGT for the full local day. It runs from ${fmt(pts[0].wbgt_c, 1)} C at 00:00 to a peak near ` +
    `${fmt(Math.max(...pts.map((p) => p.wbgt_c)), 1)} C. The band from 05:00 to 18:00 is the plan's working window. ` +
    (overRange ? `WBGT is above 32.1 C from ${overRange}. ` : `WBGT stays below 32.1 C all day. `) +
    (cw ? `The coolest working stretch is ${cw.start} to ${cw.end}. ` : "") +
    (curve.stays_hot_overnight
      ? `WBGT stays above 30 C overnight, low near ${fmt(curve.overnight_min_wbgt, 1)} C. `
      : "") +
    "Night hours carry no solar load.";

  return (
    <figure className="flex flex-col gap-3">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full select-none"
        style={{ height: "auto" }}
        role="img"
        aria-label={caption}
      >
        <defs>
          <linearGradient id={`${gid}-r`} x1="0" y1="0" x2="0" y2="1">
            {grad.map((s, i) => (
              <stop key={i} offset={s.offset} stopColor={s.color} />
            ))}
          </linearGradient>
          <clipPath id={`${gid}-c`}>
            <path d={curveArea} />
          </clipPath>
          <pattern id={`${gid}-h`} width="5" height="5" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
            <line x1="0" y1="0" x2="0" y2="5" stroke="var(--state-stop)" strokeWidth="1" opacity="0.5" />
          </pattern>
        </defs>

        {/* night wash, 00 to 05 and 18 to 24 */}
        <rect x={x(-0.5)} y={M.t} width={x(DAY_LO - 0.5) - x(-0.5)} height={PLOT_B - M.t} fill="var(--text)" opacity={theme === "dark" ? 0.06 : 0.045} />
        <rect x={x(DAY_HI + 0.5)} y={M.t} width={x(23.5) - x(DAY_HI + 0.5)} height={PLOT_B - M.t} fill="var(--text)" opacity={theme === "dark" ? 0.06 : 0.045} />

        {/* working window band */}
        <rect x={x(DAY_LO - 0.5)} y={M.t} width={x(DAY_HI + 0.5) - x(DAY_LO - 0.5)} height={PLOT_B - M.t} fill="var(--accent-weak)" opacity="0.45" />
        <text x={(x(DAY_LO - 0.5) + x(DAY_HI + 0.5)) / 2} y={PLOT_B + 30} textAnchor="middle" className="mono" fontSize="9.5" fill="var(--text-muted)">
          working window, 05:00 to 18:00
        </text>

        {y.ticks(5).map((t) => (
          <g key={t}>
            <line x1={M.l} x2={W - M.r} y1={y(t)} y2={y(t)} stroke="var(--border)" />
            <text x={M.l - 8} y={y(t)} dy="0.32em" textAnchor="end" className="mono" fontSize="10" fill="var(--text-muted)">
              {t}
            </text>
          </g>
        ))}

        {/* WBGT ramp fill + curve */}
        <g clipPath={`url(#${gid}-c)`}>
          <rect x={M.l} y={M.t} width={W - M.r - M.l} height={PLOT_B - M.t} fill={`url(#${gid}-r)`} opacity={theme === "dark" ? 0.6 : 0.68} />
        </g>
        <path
          d={curveLine}
          fill="none"
          stroke="var(--text)"
          strokeWidth="2"
          strokeLinejoin="round"
          className={reduced ? undefined : "draw-on"}
          style={{ ["--len" as string]: 1600 } as React.CSSProperties}
        />

        {/* 32.1 line + over-threshold strip */}
        <line x1={M.l} x2={W - M.r} y1={yThr} y2={yThr} stroke="var(--text)" strokeWidth="1.4" strokeDasharray="2 3" />
        <text x={W - M.r} y={yThr - 5} textAnchor="end" className="mono" fontSize="10" fontWeight="600" fill="var(--text)">
          32.1 C stop-work
        </text>
        {over.length > 0 && (
          <>
            <rect x={x(Math.min(...over) - 0.5)} y={M.t} width={x(Math.max(...over) + 0.5) - x(Math.min(...over) - 0.5)} height={7} fill={`url(#${gid}-h)`} />
            <text x={x((Math.min(...over) + Math.max(...over)) / 2)} y={M.t - 6} textAnchor="middle" className="mono" fontSize="9.5" fill="var(--state-stop)">
              above 32.1 C, {overRange}
            </text>
          </>
        )}

        {/* coolest working window bracket */}
        {cw && cwLo != null && cwHi != null && (
          <g>
            <line x1={x(cwLo - 0.4)} x2={x(cwHi - 0.6)} y1={PLOT_B + 8} y2={PLOT_B + 8} stroke="var(--accent)" strokeWidth="1.5" />
            <line x1={x(cwLo - 0.4)} x2={x(cwLo - 0.4)} y1={PLOT_B + 5} y2={PLOT_B + 11} stroke="var(--accent)" strokeWidth="1.5" />
            <line x1={x(cwHi - 0.6)} x2={x(cwHi - 0.6)} y1={PLOT_B + 5} y2={PLOT_B + 11} stroke="var(--accent)" strokeWidth="1.5" />
            <text x={x((cwLo + cwHi - 1) / 2)} y={PLOT_B + 30} textAnchor="middle" className="mono" fontSize="9.5" fill="var(--accent)">
              coolest working hours
            </text>
          </g>
        )}

        {/* overnight note */}
        {curve.stays_hot_overnight && (
          <text x={x(1.5)} y={M.t + 12} className="mono" fontSize="9.5" fill="var(--text-secondary)">
            WBGT stays above 30 C overnight (low {fmt(curve.overnight_min_wbgt, 1)})
          </text>
        )}

        {/* hour axis, every 3 h; night labels dimmed */}
        {pts
          .filter((p) => p.hour % 3 === 0 || p.hour === 23)
          .map((p) => (
            <text
              key={p.hour}
              x={x(p.hour)}
              y={PLOT_B + 15}
              textAnchor="middle"
              className="mono"
              fontSize="10"
              opacity={p.is_daylight ? 1 : 0.4}
              fill="var(--text-muted)"
            >
              {String(p.hour).padStart(2, "0")}
            </text>
          ))}
      </svg>

      <p className="text-sm text-ink-secondary">
        This is context, not a plan. Night carries no solar load, and overnight WBGT
        staying high is why a night shift is not automatically safe in Gulf summer.
      </p>
      <figcaption className="sr-only">{caption}</figcaption>
    </figure>
  );
}
