import Link from "next/link";
import { ThemeToggle } from "@/components/ThemeToggle";

export function Nav() {
  return (
    <header className="sticky top-0 z-40 border-b border-border/70 bg-bg/80 backdrop-blur">
      <div className="mx-auto flex max-w-content items-center justify-between px-5 py-3.5">
        <Link href="/" className="text-lg font-semibold tracking-tight text-ink">
          Harara
        </Link>
        <nav className="flex items-center gap-1 sm:gap-2">
          <a href="/#findings" className="hidden rounded px-3 py-2 text-sm text-ink-secondary hover:text-ink sm:block">
            Findings
          </a>
          <a href="/#method" className="hidden rounded px-3 py-2 text-sm text-ink-secondary hover:text-ink sm:block">
            Method
          </a>
          <ThemeToggle />
          <Link
            href="/app"
            className="rounded-lg bg-accent px-3.5 py-2 text-sm font-semibold text-accent-ink hover:bg-accent-hover"
          >
            Open the assistant
          </Link>
        </nav>
      </div>
    </header>
  );
}
