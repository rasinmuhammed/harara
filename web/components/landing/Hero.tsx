"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { useDeferredMount, useDohaPlan, useTheme } from "@/lib/hooks";
import { fmt } from "@/lib/format";
import type { PlanResponse } from "@/lib/types";

const HeatField = dynamic(
  () => import("@/components/visual/HeatField").then((m) => m.HeatField),
  { ssr: false },
);

export function Hero({ plan: initial }: { plan: PlanResponse | null }) {
  const [theme] = useTheme();
  const plan = useDohaPlan(initial);
  const showField = useDeferredMount();
  const peak = plan ? Math.max(...plan.hours.map((h) => h.wbgt_c)) : null;
  const wbgt = plan?.hours.map((h) => h.wbgt_c);

  return (
    <section className="relative overflow-hidden border-b border-border">
      {/* motif backdrop: a CSS wash paints first, the field layers over it */}
      <div
        aria-hidden
        className="absolute inset-0"
        style={{
          background:
            theme === "dark"
              ? "radial-gradient(120% 80% at 82% 12%, rgba(233,150,62,0.08), transparent 60%)"
              : "radial-gradient(120% 80% at 82% 12%, rgba(180,101,14,0.07), transparent 60%)",
        }}
      />
      {showField && (
        <div aria-hidden className="fade-in absolute inset-0">
          <HeatField wbgt={wbgt} theme={theme} variant="hero" />
        </div>
      )}

      <div className="relative mx-auto max-w-content px-5 py-24 sm:py-32">
        <p className="eyebrow">Gulf humid-heat research</p>
        <h1 className="mt-3 max-w-[22ch] text-h1 font-semibold text-ink">
          Research on forecast-driven heat safety for outdoor work in the Gulf.
        </h1>
        <p className="mt-5 max-w-prose text-lg text-ink-secondary">
          Qatar&apos;s Ministerial Decision 17/2021 is the enforceable baseline: a
          WBGT standard and a fixed midday rest window. This project studies what
          a daily weather forecast adds on top of it, and reports what it does
          not. Harara is the assistant built from that work.
        </p>
        <div className="mt-7 flex flex-wrap items-center gap-3">
          <a
            href="/#findings"
            className="rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink transition-colors hover:bg-accent-hover"
          >
            See the findings
          </a>
          <Link
            href="/app"
            className="rounded-lg border border-border px-4 py-2.5 text-sm text-ink-secondary transition-colors hover:border-border-strong hover:text-ink"
          >
            Open the assistant
          </Link>
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
