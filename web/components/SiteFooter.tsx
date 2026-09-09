export function SiteFooter() {
  return (
    <footer className="mt-8 border-t border-border">
      <div className="mx-auto flex max-w-[1180px] flex-col gap-2 px-5 py-6 text-sm text-ink-muted sm:flex-row sm:items-center sm:justify-between">
        <p>
          Weather data by{" "}
          <a
            href="https://open-meteo.com"
            target="_blank"
            rel="noreferrer"
            className="underline decoration-border-strong hover:text-ink-secondary"
          >
            Open-Meteo.com
          </a>{" "}
          · CC BY 4.0. Screening decision-support, not medical advice.
        </p>
        <p className="flex flex-wrap gap-x-4 gap-y-1">
          <a
            href="https://github.com/rasinmuhammed/harara/blob/main/docs/technical_report.md"
            target="_blank"
            rel="noreferrer"
            className="underline decoration-border-strong hover:text-ink-secondary"
          >
            Technical report
          </a>
          <a
            href="https://github.com/rasinmuhammed/harara/blob/main/docs/results_ledger.md"
            target="_blank"
            rel="noreferrer"
            className="underline decoration-border-strong hover:text-ink-secondary"
          >
            Results ledger
          </a>
          <span>MIT licence</span>
        </p>
      </div>
    </footer>
  );
}
