"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useDohaPlan, usePrefersReducedMotion, useSaveData, useTheme } from "@/lib/hooks";
import { fmt } from "@/lib/format";
import type { PlanResponse } from "@/lib/types";

const HeroCanvas = dynamic(() => import("./HeroCanvas"), { ssr: false });

function Poster({ plan, theme }: { plan: PlanResponse | null; theme: "light" | "dark" }) {
  // a crisp static representation: the day's WBGT curve on a warm-to-cool wash
  const pts = (plan?.hours ?? []).map((h, i, a) => {
    const x = (i / Math.max(1, a.length - 1)) * 100;
    const yv = Math.max(0, Math.min(1, (h.wbgt_c - 24) / 16));
    return `${i ? "L" : "M"}${x.toFixed(1)},${(100 - yv * 78).toFixed(1)}`;
  });
  return (
    <div
      aria-hidden
      className="absolute inset-0 overflow-hidden"
      style={{
        background:
          theme === "dark"
            ? "radial-gradient(120% 80% at 80% 20%, rgba(233,150,62,0.10), transparent 60%), radial-gradient(90% 70% at 10% 90%, rgba(60,110,142,0.14), transparent 55%)"
            : "radial-gradient(120% 80% at 80% 20%, rgba(180,101,14,0.10), transparent 60%), radial-gradient(90% 70% at 10% 90%, rgba(34,80,110,0.10), transparent 55%)",
      }}
    >
      {pts.length > 0 && (
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="h-full w-full opacity-70">
          <line x1="0" y1="38" x2="100" y2="38" stroke="var(--border-strong)" strokeWidth="0.4" strokeDasharray="1 1.5" />
          <path d={pts.join(" ") + " L100,100 L0,100 Z"} fill="var(--accent-weak)" />
          <path d={pts.join(" ")} fill="none" stroke="var(--text)" strokeWidth="0.7" opacity="0.5" />
        </svg>
      )}
    </div>
  );
}

export function Hero({ plan: initial }: { plan: PlanResponse | null }) {
  const [theme] = useTheme();
  const plan = useDohaPlan(initial);
  const reduced = usePrefersReducedMotion();
  const save = useSaveData();
  const [hydrated, setHydrated] = useState(false);
  const [active, setActive] = useState(true);
  const boxRef = useRef<HTMLDivElement>(null);

  const wantCanvas = !reduced && !save;

  useEffect(() => {
    if (!wantCanvas) return;
    const start = () => setHydrated(true);
    const idle = (window as any).requestIdleCallback || ((f: any) => setTimeout(f, 400));
    if (document.readyState === "complete") idle(start);
    else window.addEventListener("load", () => idle(start), { once: true });
  }, [wantCanvas]);

  useEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setActive(e.isIntersecting), {
      threshold: 0.05,
    });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const peak = plan ? Math.max(...plan.hours.map((h) => h.wbgt_c)) : null;

  return (
    <section className="relative overflow-hidden border-b border-border">
      <div ref={boxRef} className="pointer-events-none absolute inset-0">
        <Poster plan={plan} theme={theme} />
        {hydrated && (
          <div className="fade-in absolute inset-0">
            <HeroCanvas plan={plan} theme={theme} active={active} />
          </div>
        )}
      </div>

      <div className="relative mx-auto max-w-content px-5 py-24 sm:py-32">
        <p className="eyebrow">Forecast-driven heat safety</p>
        <h1 className="mt-3 max-w-[16ch] text-h1 font-semibold text-ink">
          Decide when to work by the forecast, not the clock.
        </h1>
        <p className="mt-5 max-w-prose text-lg text-ink-secondary">
          Harara reads the weather forecast for your site, works out how hard the heat will be on the body hour by hour, and tells you when the crew should work, ease off, or stop.
        </p>
        <div className="mt-7 flex flex-wrap items-center gap-3">
          <Link href="/app" className="rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink hover:bg-accent-hover">
            Open the planner
          </Link>
          <a
            href="https://github.com/rasinmuhammed/harara/blob/main/docs/technical_report.md"
            target="_blank"
            rel="noreferrer"
            className="rounded-lg border border-border px-4 py-2.5 text-sm text-ink-secondary hover:border-border-strong hover:text-ink"
          >
            Read the method
          </a>
        </div>
        {peak != null && (
          <p className="mono mt-8 text-sm text-ink-muted">
            Doha today: forecast WBGT peaks near {fmt(peak, 1)} C.
          </p>
        )}
      </div>
    </section>
  );
}
