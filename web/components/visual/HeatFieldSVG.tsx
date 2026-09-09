/**
 * The heat-field motif as static SVG, for surfaces that render outside the
 * browser (the OpenGraph image and the favicon, both drawn by next/og). Same
 * scalar field as `HeatField.tsx`, no animation, colours straight from the
 * shared WBGT ramp.
 */

import { DEFAULT_CURVE, THRESHOLD_NORM, bandColor, curveAt, sampleCurve } from "@/lib/heatField";

export function HeatFieldSVG({
  wbgt,
  theme,
  width,
  height,
  bands = 12,
  className,
}: {
  wbgt?: number[];
  theme: "light" | "dark";
  width: number;
  height: number;
  bands?: number;
  className?: string;
}) {
  const curve = wbgt && wbgt.length ? sampleCurve(wbgt, 24) : DEFAULT_CURVE;
  const steps = 48;
  const base = 0.12;
  const amp = 0.55;

  const lines = [];
  for (let b = 0; b < bands; b++) {
    const level = b / (bands - 1);
    const isRidge = Math.abs(level - (1 - THRESHOLD_NORM)) < 0.5 / bands;
    let d = "";
    for (let i = 0; i <= steps; i++) {
      const u = i / steps;
      const cy = curveAt(curve, u);
      const y = (base + level * (1 - base) - cy * amp * (1 - level) * 0.5) * height;
      d += `${i === 0 ? "M" : "L"}${(u * width).toFixed(1)},${y.toFixed(1)}`;
    }
    const color = bandColor(1 - level, theme);
    lines.push(
      <path
        key={b}
        d={`${d} L${width},${height} L0,${height} Z`}
        fill={color}
        fillOpacity={0.06 + 0.03 * (1 - level)}
      />,
      <path
        key={`l${b}`}
        d={d}
        fill="none"
        stroke={color}
        strokeOpacity={isRidge ? 0.55 : 0.18}
        strokeWidth={isRidge ? 2 : 1}
      />,
    );
  }

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      style={{ display: "flex" }}
    >
      {lines}
    </svg>
  );
}
