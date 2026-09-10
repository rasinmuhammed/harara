import { Reveal } from "./Reveal";

function DryVsHumid() {
  return (
    <svg viewBox="0 0 120 80" className="w-full text-ink-muted" aria-hidden>
      <path d="M10 66h44M66 66h44" stroke="currentColor" strokeWidth="1.2" />
      <path d="M22 40c0 7-5 12-10 12S2 47 2 40 12 22 12 22s10 11 10 18Z" transform="translate(20 6)" fill="none" stroke="var(--state-work)" strokeWidth="1.6" />
      <path d="M22 40c0 7-5 12-10 12S2 47 2 40 12 22 12 22s10 11 10 18Z" transform="translate(76 6)" fill="var(--state-stop)" opacity="0.28" stroke="var(--state-stop)" strokeWidth="1.6" />
    </svg>
  );
}
function FixedClock() {
  return (
    <svg viewBox="0 0 120 80" className="w-full text-ink-muted" aria-hidden>
      <rect x="42" y="8" width="30" height="64" fill="var(--compare)" opacity="0.22" />
      <path d="M8 52c14-4 22-26 36-26s20 20 34 16 24-22 34-24" fill="none" stroke="var(--accent)" strokeWidth="1.6" />
      <path d="M8 40c14-2 22-16 36-16s20 12 34 10 24-14 34-16" fill="none" stroke="var(--accent)" strokeWidth="1.2" opacity="0.45" />
    </svg>
  );
}
function MovingHours() {
  const bars = [0, 1, 0, 0, 2, 2, 1, 2, 2, 2, 2, 1, 0, 2, 2, 0];
  return (
    <svg viewBox="0 0 128 80" className="w-full text-ink-muted" aria-hidden>
      <rect x="42" y="6" width="44" height="58" fill="var(--compare)" opacity="0.16" />
      {bars.map((b, i) => (
        <rect key={i} x={6 + i * 7.5} y={b === 2 ? 20 : b === 1 ? 38 : 62} width="5" height={b === 2 ? 42 : b === 1 ? 24 : 2} rx="1" fill={b === 2 ? "var(--state-stop)" : b === 1 ? "var(--state-reduced)" : "var(--border-strong)"} />
      ))}
    </svg>
  );
}

const BEATS = [
  {
    h: "Humid heat is harder on the body than the number suggests.",
    p: "The body cools by sweating, and sweat only helps when it evaporates. In humid Gulf air it barely does, so the real physiological load is far higher than air temperature alone implies. WBGT is the index that captures this, and it is what the regulation is written against.",
    D: DryVsHumid,
  },
  {
    h: "Qatar's fixed window is a strong baseline.",
    p: "Ministerial Decision 17/2021 was the first GCC regulation to adopt WBGT as its legal standard, with a WBGT stop-work line and a fixed midday rest window. It is simple and enforceable, and it is the baseline this research measures against.",
    D: FixedClock,
  },
  {
    h: "The question is what a daily forecast adds.",
    p: "Heat risk shifts day to day with the weather. This project tests, on 16 years of data, where a forecast-driven layer genuinely helps and where it does not.",
    D: MovingHours,
  },
];

export function Problem() {
  return (
    <section className="py-20" aria-labelledby="problem-h">
      <div className="mx-auto max-w-content px-5">
        <Reveal>
          <p className="eyebrow">Background</p>
          <h2 id="problem-h" className="mt-2 max-w-prose text-h2 text-ink">
            Why humid heat needs its own instruments.
          </h2>
        </Reveal>
        <div className="mt-12 grid gap-8 md:grid-cols-3">
          {BEATS.map((b, i) => (
            <Reveal key={b.h} delay={i * 80} className="flex flex-col gap-3">
              <div className="rounded-lg border border-border bg-surface p-4">
                <b.D />
              </div>
              <h3 className="text-h4 text-ink">{b.h}</h3>
              <p className="text-ink-secondary">{b.p}</p>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
