"use client";

/**
 * A section rule drawn as one contour line from the heat-field motif. It draws
 * itself in once when it scrolls into view, then holds. Under reduced motion it
 * is simply present. Decorative: aria-hidden, and it keeps the same visual
 * weight as the plain border it replaces.
 */

import { useInView } from "@/lib/hooks";
import { curveAt } from "@/lib/heatField";

const CURVE = [0.5, 0.42, 0.3, 0.22, 0.26, 0.4, 0.58, 0.7, 0.74, 0.66, 0.5, 0.36, 0.3, 0.4, 0.52, 0.5];

export function ContourDivider({ className = "" }: { className?: string }) {
  const [ref, inView] = useInView<HTMLDivElement>({ rootMargin: "0px 0px -20% 0px" });
  const W = 1200;
  const H = 40;
  const steps = 80;
  let d = "";
  for (let i = 0; i <= steps; i++) {
    const u = i / steps;
    const y = (0.5 + (curveAt(CURVE, u) - 0.5) * 0.7) * H;
    d += `${i === 0 ? "M" : "L"}${((u * W)).toFixed(1)},${y.toFixed(1)}`;
  }

  return (
    <div ref={ref} aria-hidden className={`w-full overflow-hidden ${className}`}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="h-6 w-full">
        <path
          d={d}
          fill="none"
          stroke="var(--border-strong)"
          strokeWidth="1"
          className={inView ? "draw-on" : undefined}
          style={{ ["--len" as string]: 1600 } as React.CSSProperties}
          strokeDasharray={inView ? undefined : "1600"}
          strokeDashoffset={inView ? undefined : "0"}
        />
      </svg>
    </div>
  );
}
