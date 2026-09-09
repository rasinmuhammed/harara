import { Reveal } from "./Reveal";

export function Evidence() {
  return (
    <section className="border-t border-border py-20" aria-labelledby="ev-h">
      <div className="mx-auto max-w-content px-5">
        <Reveal>
          <p className="eyebrow">Honesty</p>
          <h2 id="ev-h" className="mt-2 text-h2 text-ink">What we can show, and what we cannot yet.</h2>
        </Reveal>
        <div className="mt-10 grid gap-5 md:grid-cols-3">
          <Reveal className="rounded-lg border border-border bg-surface p-5">
            <p className="eyebrow text-state-work">Proven, in simulation</p>
            <p className="mt-2 text-ink-secondary">
              Over 236 held-out days of real past weather, the scheduler lowered the mean peak heat load by 14 percent and the p90 tail by 16 to 20 percent, with no drop in hours worked.
            </p>
          </Reveal>
          <Reveal delay={80} className="rounded-lg border border-border bg-surface p-5">
            <p className="eyebrow text-state-work">Proven, and current</p>
            <p className="mt-2 text-ink-secondary">
              In a forecast check for Doha, ECMWF's models place the 32.1 C stop-work hours well. NOAA's GFS runs about 0.7 C cold on WBGT and misses roughly 40 percent of those hours at every lead.
            </p>
          </Reveal>
          <Reveal delay={160} className="rounded-lg border border-border bg-surface p-5">
            <p className="eyebrow text-state-reduced">Not proven</p>
            <p className="mt-2 text-ink-secondary">
              The individual-worker sensing work runs on synthetic physiology and has not been tested on people. It is not part of this product.
            </p>
          </Reveal>
        </div>
        <Reveal className="mt-6">
          <p className="text-sm text-ink-muted">
            Full method in the{" "}
            <a className="underline hover:text-ink" href="https://github.com/rasinmuhammed/harara/blob/main/docs/technical_report.md" target="_blank" rel="noreferrer">technical report</a>
            {" "}and the{" "}
            <a className="underline hover:text-ink" href="https://github.com/rasinmuhammed/harara/blob/main/docs/results_ledger.md" target="_blank" rel="noreferrer">results ledger</a>.
          </p>
        </Reveal>
      </div>
    </section>
  );
}
