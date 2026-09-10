import Link from "next/link";
import { Reveal } from "./Reveal";

export function Close() {
  return (
    <section className="py-24" aria-labelledby="close-h">
      <div className="mx-auto max-w-content px-5">
        <Reveal>
          <h2 id="close-h" className="text-h2 text-ink">Open the assistant.</h2>
          <p className="mt-3 max-w-prose text-lg text-ink-secondary">
            Describe a shift the way you would to a colleague, or ask a heat, WBGT, forecast or rules question for the Gulf. Or read the full method first.
          </p>
          <div className="mt-6 flex flex-wrap items-center gap-3">
            <Link href="/app" className="rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-accent-ink hover:bg-accent-hover">
              Open the assistant
            </Link>
            <a href="/#findings" className="rounded-lg border border-border px-4 py-2.5 text-sm text-ink-secondary hover:border-border-strong hover:text-ink">
              Read the findings
            </a>
            <a href="https://github.com/rasinmuhammed/harara" target="_blank" rel="noreferrer" className="rounded-lg border border-border px-4 py-2.5 text-sm text-ink-secondary hover:border-border-strong hover:text-ink">
              Source
            </a>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
