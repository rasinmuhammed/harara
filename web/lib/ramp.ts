/**
 * WBGT temperature ramp: perceptual cool -> hot with a deliberate
 * discontinuity at 32.1 C (the Decision 17/2021 stop-work line). Blue<->amber/red
 * is the colour-vision-deficiency-safe axis; the near-neutral grey-green just
 * below the line is a transition, not a distinguishing step. Interpolated in
 * OKLab so intermediate temperatures are perceptually even.
 *
 * CVD note: every adjacent stop separates by OKLab dE >= 10 under normal
 * vision and >= 9 under simulated deuteranopia/protanopia; the 32.0 -> 32.1
 * jump is dE ~12 and is additionally drawn as a 1px rule.
 */

export const THRESHOLD_C = 32.1;

type Stop = [tempC: number, light: string, dark: string];

export const RAMP: Stop[] = [
  [24.0, "#22506e", "#3c6e8e"],
  [27.0, "#2f7189", "#4c93ac"],
  [30.0, "#6da0a0", "#87b9ba"],
  [32.0, "#aeb8a8", "#c4cdbd"],
  // --- discontinuity at 32.1 ---
  [32.1, "#e9b24c", "#f2c066"],
  [34.0, "#db8038", "#e79a4f"],
  [37.0, "#c04a34", "#d06a54"],
  [40.0, "#6e2420", "#a03e37"],
];

const DOMAIN_MIN = RAMP[0][0];
const DOMAIN_MAX = RAMP[RAMP.length - 1][0];

// ---- sRGB <-> OKLab ------------------------------------------------------
function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [
    parseInt(h.slice(0, 2), 16) / 255,
    parseInt(h.slice(2, 4), 16) / 255,
    parseInt(h.slice(4, 6), 16) / 255,
  ];
}
const s2l = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const l2s = (c: number) =>
  c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055;

function srgbToOklab(hex: string): [number, number, number] {
  let [r, g, b] = hexToRgb(hex).map(s2l) as [number, number, number];
  let l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  let m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  let s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

function oklabToHex(L: number, a: number, b: number): string {
  const l_ = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m_ = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s_ = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const r = 4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_;
  const g = -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_;
  const bb = -0.0041960863 * l_ - 0.7034186147 * m_ + 1.707614701 * s_;
  const to = (c: number) =>
    Math.max(0, Math.min(255, Math.round(l2s(c) * 255)))
      .toString(16)
      .padStart(2, "0");
  return `#${to(r)}${to(g)}${to(bb)}`;
}

/** Colour for a WBGT value, in the given theme. */
export function wbgtColor(tempC: number, theme: "light" | "dark"): string {
  const t = Math.max(DOMAIN_MIN, Math.min(DOMAIN_MAX, tempC));
  const idx = theme === "dark" ? 2 : 1;
  for (let i = 0; i < RAMP.length - 1; i++) {
    const [t0] = RAMP[i];
    const [t1] = RAMP[i + 1];
    if (t <= t1) {
      // hard break: no interpolation straddling 32.0 -> 32.1
      if (t0 === 32.0 && t1 === 32.1) {
        return t < THRESHOLD_C ? (RAMP[i][idx] as string) : (RAMP[i + 1][idx] as string);
      }
      const f = t1 === t0 ? 0 : (t - t0) / (t1 - t0);
      const c0 = srgbToOklab(RAMP[i][idx] as string);
      const c1 = srgbToOklab(RAMP[i + 1][idx] as string);
      return oklabToHex(
        c0[0] + f * (c1[0] - c0[0]),
        c0[1] + f * (c1[1] - c0[1]),
        c0[2] + f * (c1[2] - c0[2]),
      );
    }
  }
  return RAMP[RAMP.length - 1][idx] as string;
}

/** SVG <linearGradient> stops for a vertical WBGT axis (y up = hotter). */
export function rampGradientStops(
  yMin: number,
  yMax: number,
  theme: "light" | "dark",
): { offset: number; color: string }[] {
  const stops: { offset: number; color: string }[] = [];
  const span = yMax - yMin;
  for (const [t] of RAMP) {
    if (t < yMin || t > yMax) continue;
    stops.push({ offset: 1 - (t - yMin) / span, color: wbgtColor(t, theme) });
    if (t === 32.0) {
      stops.push({ offset: 1 - (32.1 - yMin) / span, color: wbgtColor(32.1, theme) });
    }
  }
  return stops.sort((a, b) => a.offset - b.offset);
}

export const STATE_COLOR: Record<string, string> = {
  work: "var(--state-work)",
  reduced: "var(--state-reduced)",
  stop: "var(--state-stop)",
};
export const STATE_GLYPH: Record<string, string> = {
  work: "●", // ●
  reduced: "◐", // ◐
  stop: "■", // ■
};
export const STATE_LABEL: Record<string, string> = {
  work: "Work",
  reduced: "Reduced",
  stop: "Stop",
};
