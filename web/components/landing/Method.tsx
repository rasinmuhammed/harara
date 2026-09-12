import { Reveal } from "./Reveal";

const REPORT = "https://github.com/rasinmuhammed/harara/blob/main/docs/technical_report.md";
const LEDGER = "https://github.com/rasinmuhammed/harara/blob/main/docs/results_ledger.md";

const POINTS = [
  [
    "Sixteen years of Doha weather.",
    "Hourly temperature, humidity, wind and radiation for 2010 to 2026, from the Open-Meteo archive, with a measured-wind patch from November 2024 where the archive drifted.",
  ],
  [
    "WBGT by the Liljegren energy-balance method.",
    "The physical model through ECMWF thermofeel, not an algebraic approximation. An early approximation biased the index 1 to 2 C low and was replaced.",
  ],
  [
    "Walk-forward validation.",
    "Every model is scored only on days after the ones it was fitted on. Hand-picked case days that seemed to support a hypothesis turned out to be selection bias, so the whole record is used.",
  ],
  [
    "The miss rate is the metric.",
    "The share of true stop-work hours a forecast places below 32.1 C, not average error. A model can cut mean error and still miss more dangerous hours.",
  ],
  [
    "Negative results are reported.",
    "Four forecasting hypotheses were tested and all four rejected. The scheduler result was revised down when worker time was counted honestly. Those are in the ledger with the rest.",
  ],
];

export function Method() {
  return (
    <section id="method" className="scroll-mt-20 border-t border-border py-20" aria-labelledby="method-h">
      <div className="mx-auto max-w-content px-5">
        <Reveal>
          <p className="eyebrow">Method</p>
          <h2 id="method-h" className="mt-2 max-w-prose text-h2 text-ink">
            How the research was done.
          </h2>
          <p className="mt-3 max-w-prose text-lg text-ink-secondary">
            All of it on public data, reproducible from the repository.
          </p>
        </Reveal>

        <ol className="mt-10 grid gap-6 sm:grid-cols-2">
          {POINTS.map(([h, p], i) => (
            <Reveal key={h} delay={i * 60} as="li" className="flex gap-4 rounded-lg border border-border bg-surface p-5">
              <span className="mono text-sm text-ink-muted">{String(i + 1).padStart(2, "0")}</span>
              <div>
                <h3 className="text-h4 text-ink">{h}</h3>
                <p className="mt-1 text-ink-secondary">{p}</p>
              </div>
            </Reveal>
          ))}
        </ol>

        <Reveal className="mt-6">
          <p className="text-sm text-ink-muted">
            The{" "}
            <a className="underline hover:text-ink" href={REPORT} target="_blank" rel="noreferrer">
              technical report
            </a>{" "}
            has the full method, and the{" "}
            <a className="underline hover:text-ink" href={LEDGER} target="_blank" rel="noreferrer">
              results ledger
            </a>{" "}
            has every question tested, including the rejected ones.
          </p>
        </Reveal>
      </div>
    </section>
  );
}
