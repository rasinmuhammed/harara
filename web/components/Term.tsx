"use client";
import * as Popover from "@radix-ui/react-popover";
import { GLOSSARY } from "@/lib/glossary";

export function Term({ k, children }: { k: string; children: React.ReactNode }) {
  const text = GLOSSARY[k];
  if (!text) return <>{children}</>;
  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          type="button"
          className="border-b border-dotted border-ink-muted text-inherit underline-offset-2 hover:border-accent hover:text-ink focus-visible:border-accent"
          aria-label={`What ${k} means`}
        >
          {children}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="top"
          sideOffset={6}
          collisionPadding={12}
          className="z-50 max-w-[280px] rounded-lg border border-border-strong bg-bg-raised p-3 text-sm leading-relaxed text-ink-secondary shadow-1"
        >
          <span className="mono mb-1 block text-micro uppercase tracking-wide text-ink-muted">
            {k}
          </span>
          {text}
          <Popover.Arrow className="fill-[var(--border-strong)]" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
