import Link from "next/link";

export function Footer() {
  return (
    <footer className="border-t border-border">
      <div className="mx-auto flex max-w-content flex-col gap-3 px-5 py-8 text-sm text-ink-muted sm:flex-row sm:items-center sm:justify-between">
        <p>
          Weather data by{" "}
          <a href="https://open-meteo.com" target="_blank" rel="noreferrer" className="underline hover:text-ink-secondary">
            Open-Meteo.com
          </a>{" "}
          under CC BY 4.0. Decision support and screening, not medical advice.
          The backend runs on Render&rsquo;s free tier, so the first request
          after a quiet spell can take up to a minute to wake.
        </p>
        <p className="flex flex-wrap gap-x-4 gap-y-1">
          <a href="https://github.com/rasinmuhammed/harara/blob/main/docs/technical_report.md" target="_blank" rel="noreferrer" className="underline hover:text-ink-secondary">Technical report</a>
          <a href="https://github.com/rasinmuhammed/harara/blob/main/docs/results_ledger.md" target="_blank" rel="noreferrer" className="underline hover:text-ink-secondary">Results ledger</a>
          <a href="https://github.com/rasinmuhammed/harara/blob/main/docs/PROJECT_EXPLAINER.md" target="_blank" rel="noreferrer" className="underline hover:text-ink-secondary">Project explainer</a>
          <a href="https://github.com/rasinmuhammed/harara" target="_blank" rel="noreferrer" className="underline hover:text-ink-secondary">Source</a>
          <span>MIT licence</span>
        </p>
      </div>
    </footer>
  );
}
