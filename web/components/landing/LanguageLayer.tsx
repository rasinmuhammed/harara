import { Reveal } from "./Reveal";

export function LanguageLayer() {
  return (
    <section className="border-t border-border py-20" aria-labelledby="lang-h">
      <div className="mx-auto max-w-content px-5">
        <Reveal>
          <p className="eyebrow">The language layer</p>
          <h2 id="lang-h" className="mt-2 max-w-prose text-h2 text-ink">
            Where the language model sits, and where it does not.
          </h2>
        </Reveal>

        <Reveal className="mt-8 grid gap-6 md:grid-cols-3">
          <div className="rounded-lg border border-border bg-surface p-5">
            <p className="eyebrow text-ink-muted">Reads rules</p>
            <p className="mt-2 text-ink-secondary">
              It turns outdoor-work regulations from their text into machine
              constraints, with a character-offset citation for every value,
              checked against the source before anything uses it.
            </p>
          </div>
          <div className="rounded-lg border border-border bg-surface p-5">
            <p className="eyebrow text-ink-muted">Talks plainly</p>
            <p className="mt-2 text-ink-secondary">
              It gives a plain-language interface. Describe a shift, or ask a
              heat, WBGT, forecast or rules question for the Gulf, and it routes
              to a deterministic tool and shows the source.
            </p>
          </div>
          <div className="rounded-lg border border-border bg-surface p-5">
            <p className="eyebrow text-ink-muted">Never counts</p>
            <p className="mt-2 text-ink-secondary">
              It never computes or estimates a number. Every figure comes from
              the physics, the forecast, or a cited rule. It runs on K2-Horizon
              from IFM at MBZUAI.
            </p>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
