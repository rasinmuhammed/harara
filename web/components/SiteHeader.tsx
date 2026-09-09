import { ThemeToggle } from "./ThemeToggle";

export function SiteHeader() {
  return (
    <header className="border-b border-border">
      <div className="mx-auto flex max-w-[1180px] items-center justify-between gap-4 px-5 py-4">
        <div className="flex items-baseline gap-3">
          <span className="font-display text-[1.35rem] leading-none text-ink">
            Harara
          </span>
          <span className="hidden text-sm text-ink-muted sm:inline">
            forecast-driven heat-safe scheduling
          </span>
        </div>
        <div className="flex items-center gap-2">
          <a
            href="https://github.com/rasinmuhammed/harara"
            target="_blank"
            rel="noreferrer"
            className="hidden rounded border border-border px-3 py-2 text-sm text-ink-secondary transition-colors duration-[var(--dur-1)] hover:border-border-strong hover:text-ink sm:inline-block"
          >
            Source & method
          </a>
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
