import { Reveal } from "./Reveal";

const REPORT = "https://github.com/rasinmuhammed/harara/blob/main/docs/technical_report.md";
const LEDGER = "https://github.com/rasinmuhammed/harara/blob/main/docs/results_ledger.md";

const FINDINGS: { claim: string; result: string; href: string; cite: string }[] = [
  {
    claim: "The fixed midday window is a floor, not a ceiling.",
    result:
      "It covers about a quarter of daylight warm-season hours. Roughly 60 percent of the hours that are physiologically unsafe for heavy unacclimatised work fall outside it, in the mornings, evenings and shoulder months.",
    href: `${REPORT}#7-operational-gap-analysis`,
    cite: "Technical report, section 7",
  },
  {
    claim: "Modern public forecasts already predict Doha WBGT well.",
    result:
      "Raw 24 to 72 hour WBGT forecasts run 1.0 to 1.1 C mean error at a 12 to 14 percent miss rate. A learned bias-correction, trained walk-forward, lowers the mean error but more than doubles the miss rate: it regresses toward climatology and under-predicts the hot tail, which is the one failure mode that matters for a stop-work call.",
    href: `${REPORT}#51-bias-correcting-nwp-wbgt`,
    cite: "Technical report, section 5.1",
  },
  {
    claim: "AI weather models are not the risk here. NOAA GFS is.",
    result:
      "On identical hours, ECMWF IFS and AIFS place the 32.1 C stop-work hours within 12 to 18 percent. NOAA GFS runs 0.3 to 0.8 C cold on WBGT and misses 40 to 45 percent of those hours at every lead, and the bias worsens in the days before a heat wave.",
    href: `${LEDGER}`,
    cite: "Results ledger, rows 23 and 26",
  },
  {
    claim: "A daily schedule does not beat the fixed rule once worker time is counted.",
    result:
      "Held to the same hours on site, the forecast-driven optimiser runs hotter than the calendar rule on peak retained heat load: the earlier advantage came from spreading work across a longer on-site day. A plain earlier start is better on heat but cannot deliver full output on about half of peak-season days.",
    href: `${LEDGER}`,
    cite: "Results ledger, row 14a",
  },
  {
    claim: "A physics filter beats heart rate alone on real bodies, but is not field-ready.",
    result:
      "With a skin-temperature channel it estimates core temperature at 0.41 C RMSE against a rectal reference, below the heart-rate-only baseline, with the bias removed. Its stated uncertainty is not calibrated out of domain and it has not been tested on Gulf outdoor workers.",
    href: `${REPORT}#91-external-validation-on-real-physiology`,
    cite: "Technical report, section 9.1",
  },
  {
    claim: "The rising-heat trend was understated, not overstated, by our own weather archive.",
    result:
      "Cross-checking the working forecast archive against a second reanalysis and the measured airport station found a second, previously undocumented defect: its Doha humidity quietly drifted dry from 2018 onward. Correcting it with measured data turns a reported flat trend into a clearly rising one, confirmed by both independent sources. We are publishing the defect we found in our own primary dataset, not just the ones we found in others'.",
    href: `${REPORT}#58-a-second-archive-defect-a-persistent-humidity-drift-and-its-size`,
    cite: "Technical report, section 5.8",
  },
];

export function Findings() {
  return (
    <section id="findings" className="scroll-mt-20 border-t border-border py-20" aria-labelledby="findings-h">
      <div className="mx-auto max-w-content px-5">
        <Reveal>
          <p className="eyebrow">What the data shows</p>
          <h2 id="findings-h" className="mt-2 max-w-prose text-h2 text-ink">
            Six findings, including one about our own instruments.
          </h2>
          <p className="mt-3 max-w-prose text-lg text-ink-secondary">
            Qatar&apos;s Ministerial Decision 17/2021 is the enforceable baseline every
            result is measured against. Some of the strongest findings are that a
            proposed improvement did not hold up.
          </p>
        </Reveal>

        <ol className="mt-10 flex flex-col gap-4">
          {FINDINGS.map((f, i) => (
            <Reveal
              key={f.claim}
              delay={i * 60}
              as="li"
              className="grid gap-3 rounded-xl border border-border bg-surface p-5 sm:grid-cols-[minmax(0,22rem)_1fr] sm:gap-6 sm:p-6"
            >
              <div>
                <span className="mono text-micro text-ink-muted">{String(i + 1).padStart(2, "0")}</span>
                <h3 className="mt-1 text-h4 text-ink">{f.claim}</h3>
              </div>
              <div>
                <p className="text-ink-secondary">{f.result}</p>
                <a
                  href={f.href}
                  target="_blank"
                  rel="noreferrer"
                  className="mono mt-2 inline-block text-sm text-ink-muted underline hover:text-ink"
                >
                  {f.cite}
                </a>
              </div>
            </Reveal>
          ))}
        </ol>

        <Reveal className="mt-6">
          <p className="text-sm text-ink-muted">
            Full method and every intermediate result in the{" "}
            <a className="underline hover:text-ink" href={REPORT} target="_blank" rel="noreferrer">
              technical report
            </a>{" "}
            and the{" "}
            <a className="underline hover:text-ink" href={LEDGER} target="_blank" rel="noreferrer">
              results ledger
            </a>
            .
          </p>
        </Reveal>
      </div>
    </section>
  );
}
