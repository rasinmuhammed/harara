export function AssumptionsPanel() {
  return (
    <section
      aria-label="Assumptions and limitations"
      className="rounded-lg border border-border bg-surface-sunken p-4 text-sm leading-relaxed text-ink-secondary"
    >
      <h2 className="text-caption uppercase text-ink-muted">
        Assumptions &amp; limitations
      </h2>
      <ul className="mt-3 flex list-disc flex-col gap-2 pl-4">
        <li>
          <strong className="font-semibold text-ink">Screening tool.</strong>{" "}
          Work/rest fractions come from the ACGIH TLV tables (ACGIH 2017 / ISO
          7243), which protect a population, not an individual. This is
          decision-support, not medical advice, and not a substitute for on-site
          physiological monitoring.
        </li>
        <li>
          <strong className="font-semibold text-ink">Single-point forecast.</strong>{" "}
          One Open-Meteo grid cell (~25 km), hourly, for the chosen day. WBGT is
          computed with the Liljegren energy-balance method (via ECMWF{" "}
          <code>thermofeel</code>).
        </li>
        <li>
          <strong className="font-semibold text-ink">
            The 32.1&nbsp;°C stop-work line is drawn, not enforced.
          </strong>{" "}
          The optimiser minimises retained heat load at equal output; hours where
          it still schedules work above 32.1&nbsp;°C are flagged. Decision
          17/2021&rsquo;s hard stop is applied on top by the operator.
        </li>
        <li>
          <strong className="font-semibold text-ink">Retained-load model.</strong>{" "}
          A one-state passive integrator (load ={" "}
          <code>max(0, WBGT − ref)</code>, hourly retention 0.8). &ldquo;Peak&rdquo; is
          the highest retained load reached; &ldquo;tail&rdquo; is its 90th
          percentile over the day.
        </li>
        <li>
          <strong className="font-semibold text-ink">Evidence.</strong> The
          walk-forward study over 236 held-out days (
          <a
            className="underline decoration-border-strong hover:text-ink"
            href="https://github.com/rasinmuhammed/harara/blob/main/docs/technical_report.md#8-scheduling"
            target="_blank"
            rel="noreferrer"
          >
            technical report §8
          </a>
          ) finds a mean 14% peak / 16–20% tail reduction at equal output. A
          single day&rsquo;s figure will vary.
        </li>
      </ul>
    </section>
  );
}
