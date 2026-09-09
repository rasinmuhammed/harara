import { Reveal } from "./Reveal";

const STEPS = [
  ["Read the forecast.", "Hourly temperature, humidity, wind, and sun for your grid cell, from the Open-Meteo API."],
  ["Convert it to heat stress.", "The Liljegren method turns those into WBGT, the wet-bulb globe temperature, one number for how hard it is for the body to cool itself."],
  ["Plan the day.", "A solver chooses the hour-by-hour work rate that delivers the required hours at the lowest peak retained heat load."],
  ["Explain it.", "The assistant writes the plan in plain language. Every number in it comes from the solver, not the model."],
];

export function HowItWorks() {
  return (
    <section className="border-t border-border py-20" aria-labelledby="how-h">
      <div className="mx-auto max-w-content px-5">
        <Reveal>
          <p className="eyebrow">How it works</p>
          <h2 id="how-h" className="mt-2 text-h2 text-ink">Four steps, all on public data.</h2>
        </Reveal>
        <ol className="mt-10 grid gap-6 sm:grid-cols-2">
          {STEPS.map(([h, p], i) => (
            <Reveal key={h} delay={i * 60} as="li" className="flex gap-4 rounded-lg border border-border bg-surface p-5">
              <span className="mono text-sm text-ink-muted">{String(i + 1).padStart(2, "0")}</span>
              <div>
                <h3 className="text-h4 text-ink">{h}</h3>
                <p className="mt-1 text-ink-secondary">{p}</p>
              </div>
            </Reveal>
          ))}
        </ol>
      </div>
    </section>
  );
}
