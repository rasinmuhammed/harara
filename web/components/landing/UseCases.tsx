import Link from "next/link";
import { Reveal } from "./Reveal";

const CASES = [
  {
    h: "Plan a shift.",
    p: "Give a site, a day, the work type, the hours and whether the crew is used to the heat. Get an hour-by-hour work and rest plan inside Decision 17/2021, with the time on site, the heat dose and the peak load of every choice shown next to each other.",
  },
  {
    h: "Answer heat questions for the Gulf.",
    p: "WBGT and how it is computed, heat illness and first response, acclimatisation, the forecast for a site, whether it is safe to work outside right now, and the outdoor-work rules for Qatar, the UAE and Saudi Arabia. Every answer cites its source, and it does nothing outside that scope.",
  },
  {
    h: "Model rule coverage for a regulator.",
    p: "Feed in a draft rule or an existing one and see which physiologically unsafe hours it covers and which it leaves out, against the 16-year record, by workload class and acclimatisation state.",
  },
];

export function UseCases() {
  return (
    <section className="border-t border-border py-20" aria-labelledby="uses-h">
      <div className="mx-auto max-w-content px-5">
        <Reveal>
          <p className="eyebrow">What it is used for</p>
          <h2 id="uses-h" className="mt-2 max-w-prose text-h2 text-ink">
            Three applications, honestly scoped.
          </h2>
        </Reveal>

        <div className="mt-10 grid gap-6 md:grid-cols-3">
          {CASES.map((c, i) => (
            <Reveal key={c.h} delay={i * 70} className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-5">
              <h3 className="text-h4 text-ink">{c.h}</h3>
              <p className="text-ink-secondary">{c.p}</p>
            </Reveal>
          ))}
        </div>

        <Reveal className="mt-8">
          <Link
            href="/app"
            className="rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink transition-colors hover:bg-accent-hover"
          >
            Open the assistant
          </Link>
        </Reveal>
      </div>
    </section>
  );
}
