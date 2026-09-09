/**
 * The heat-field motif, shared by every surface that shows it.
 *
 * A scalar field f(x, y) = y - curve(x), where curve(x) is the day's WBGT
 * profile normalised to 0..1 over 24..40 C. Iso-lines of f are the isotherm
 * bands: where the curve is high (hot midday) the bands crowd toward the top.
 * Each band is coloured from the shared WBGT ramp at the temperature it marks,
 * and a brighter ridge sits where the field crosses the 32.1 C stop-work level.
 *
 * Pure module: no React, no canvas. `HeatField.tsx` draws it to a canvas;
 * `HeatFieldSVG.tsx` draws the same motif as SVG for the OG image and favicon.
 */

import { wbgtColor } from "./ramp";

export const FIELD_LO_C = 24;
export const FIELD_HI_C = 40;
export const THRESHOLD_C = 32.1;
export const THRESHOLD_NORM = (THRESHOLD_C - FIELD_LO_C) / (FIELD_HI_C - FIELD_LO_C);

/** A calm default curve for surfaces with no live data yet: a Doha-summer arc. */
export const DEFAULT_CURVE = [
  0.30, 0.34, 0.42, 0.53, 0.63, 0.72, 0.79, 0.83,
  0.84, 0.82, 0.77, 0.68, 0.57, 0.44, 0.36, 0.31,
];

/** Resample WBGT values (deg C) to `n` points normalised to 0..1 over the field range. */
export function sampleCurve(valuesC: number[], n = 16): number[] {
  if (!valuesC.length) return DEFAULT_CURVE.slice(0, n);
  const norm = valuesC.map((v) =>
    Math.max(0, Math.min(1, (v - FIELD_LO_C) / (FIELD_HI_C - FIELD_LO_C))),
  );
  if (norm.length === n) return norm;
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const f = (i / (n - 1)) * (norm.length - 1);
    const a = Math.floor(f);
    const b = Math.min(a + 1, norm.length - 1);
    out.push(norm[a] + (norm[b] - norm[a]) * (f - a));
  }
  return out;
}

/** Catmull-Rom sample of a 0..1 curve at fractional index position u in [0,1]. */
export function curveAt(curve: number[], u: number): number {
  const n = curve.length;
  const x = Math.max(0, Math.min(1, u)) * (n - 1);
  const i = Math.floor(x);
  const t = x - i;
  const p0 = curve[Math.max(0, i - 1)];
  const p1 = curve[i];
  const p2 = curve[Math.min(n - 1, i + 1)];
  const p3 = curve[Math.min(n - 1, i + 2)];
  return (
    0.5 *
    (2 * p1 +
      (-p0 + p2) * t +
      (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t +
      (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t)
  );
}

/** Colour for a normalised band level, from the shared WBGT ramp. */
export function bandColor(level: number, theme: "light" | "dark"): string {
  return wbgtColor(FIELD_LO_C + level * (FIELD_HI_C - FIELD_LO_C), theme);
}

export interface FieldVariant {
  /** number of isotherm bands across the field height */
  bands: number;
  /** overall opacity ceiling (kept low so the motif never competes with text) */
  alpha: number;
  /** vertical amplitude the curve pushes the bands, in field units 0..1 */
  amplitude: number;
  /** drift speed (radians/sec) when animated */
  drift: number;
}

export const VARIANTS: Record<"hero" | "divider" | "panel", FieldVariant> = {
  hero: { bands: 15, alpha: 0.72, amplitude: 0.6, drift: 0.11 },
  divider: { bands: 3, alpha: 0.85, amplitude: 0.3, drift: 0.09 },
  panel: { bands: 11, alpha: 0.6, amplitude: 0.5, drift: 0.14 },
};
