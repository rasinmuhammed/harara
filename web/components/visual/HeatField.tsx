"use client";

/**
 * The heat-field motif as a Canvas-2D layer. One renderer for every ambient
 * surface: the landing hero backdrop, the /app empty and loading states, and
 * (via the `divider` variant) the section rules.
 *
 * Rules held here: it never competes with text (low per-band alpha + a
 * vignette to the background), it pauses when offscreen, it becomes a single
 * static paint under prefers-reduced-motion or Save-Data, and device pixel
 * ratio is capped at 1.5.
 */

import { useEffect, useRef } from "react";
import { usePrefersReducedMotion, useSaveData } from "@/lib/hooks";
import {
  DEFAULT_CURVE, THRESHOLD_NORM, VARIANTS, bandColor, curveAt, sampleCurve,
} from "@/lib/heatField";

type Variant = keyof typeof VARIANTS;

export function HeatField({
  wbgt,
  theme,
  variant = "panel",
  className,
  animate = true,
}: {
  /** WBGT values in deg C; falls back to a calm default arc */
  wbgt?: number[];
  theme: "light" | "dark";
  variant?: Variant;
  className?: string;
  animate?: boolean;
}) {
  const ref = useRef<HTMLCanvasElement>(null);
  const reduced = usePrefersReducedMotion();
  const save = useSaveData();
  const still = reduced || save || !animate;

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const V = VARIANTS[variant];
    const curve = wbgt && wbgt.length ? sampleCurve(wbgt, 24) : DEFAULT_CURVE;
    const dpr = Math.min(1.5, window.devicePixelRatio || 1);

    let w = 0;
    let h = 0;
    const fit = () => {
      const r = canvas.getBoundingClientRect();
      w = Math.max(1, Math.round(r.width));
      h = Math.max(1, Math.round(r.height));
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    fit();

    const bg = getComputedStyle(document.documentElement)
      .getPropertyValue("--bg")
      .trim() || (theme === "dark" ? "#0b0b0c" : "#fbfaf8");

    const paint = (phase: number) => {
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, w, h);

      const base = 0.12; // push the whole field down a touch from the top
      const steps = 64;

      for (let b = 0; b < V.bands; b++) {
        const level = b / (V.bands - 1); // 0 = top (hot), 1 = bottom (cool)
        const drift = still ? 0 : 0.045 * Math.sin(phase + level * 6.2831);
        const isRidge = Math.abs(level - (1 - THRESHOLD_NORM)) < 0.5 / V.bands;

        const yAt = (i: number) => {
          const u = i / steps;
          const cy = curveAt(curve, u); // 0..1, higher = hotter
          const y = base + level * (1 - base) + drift - cy * V.amplitude * (1 - level) * 0.5;
          return Math.max(-0.1, Math.min(1.1, y)) * h;
        };

        // soft fill between this band and the next
        ctx.beginPath();
        ctx.moveTo(0, yAt(0));
        for (let i = 1; i <= steps; i++) ctx.lineTo((i / steps) * w, yAt(i));
        ctx.lineTo(w, h);
        ctx.lineTo(0, h);
        ctx.closePath();
        ctx.fillStyle = bandColor(1 - level, theme);
        ctx.globalAlpha = V.alpha * (0.05 + 0.03 * (1 - level));
        ctx.fill();

        // the contour line itself
        ctx.beginPath();
        ctx.moveTo(0, yAt(0));
        for (let i = 1; i <= steps; i++) ctx.lineTo((i / steps) * w, yAt(i));
        ctx.strokeStyle = bandColor(1 - level, theme);
        ctx.globalAlpha = V.alpha * (isRidge ? 0.62 : 0.22);
        ctx.lineWidth = isRidge ? 1.5 : 1;
        ctx.stroke();
      }

      // vignette to background so edges never hard-edge against content
      ctx.globalAlpha = 1;
      const g = ctx.createRadialGradient(w * 0.5, h * 0.42, 0, w * 0.5, h * 0.5, Math.max(w, h) * 0.75);
      g.addColorStop(0, "rgba(0,0,0,0)");
      g.addColorStop(1, bg);
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, w, h);
    };

    let raf = 0;
    let t0 = performance.now();
    let visible = true;

    const loop = (now: number) => {
      paint(((now - t0) / 1000) * VARIANTS[variant].drift);
      raf = requestAnimationFrame(loop);
    };

    const start = () => {
      if (still || !visible || raf) return;
      raf = requestAnimationFrame(loop);
    };
    const stop = () => {
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
    };

    const io = new IntersectionObserver(
      ([e]) => {
        visible = e.isIntersecting;
        if (visible) start();
        else stop();
      },
      { threshold: 0.01 },
    );
    io.observe(canvas);

    const ro = new ResizeObserver(() => {
      fit();
      paint(still ? 0 : ((performance.now() - t0) / 1000) * VARIANTS[variant].drift);
    });
    ro.observe(canvas);

    paint(0);
    if (!still) start();

    return () => {
      stop();
      io.disconnect();
      ro.disconnect();
    };
  }, [wbgt, theme, variant, still]);

  return (
    <canvas
      ref={ref}
      aria-hidden="true"
      className={className}
      style={{ display: "block", width: "100%", height: "100%" }}
    />
  );
}
