"use client";

import { forwardRef } from "react";
import { cn } from "@/lib/cn";

/**
 * The control-bar chip: a small label plus the current value, e.g.
 * "Location · Doha". As a button it opens a popover; `active` marks it open.
 * `flash` briefly highlights it when its value changes.
 */
export interface ChipProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  label: string;
  value: string;
  active?: boolean;
  flash?: boolean;
  as?: "button" | "span";
}

export const Chip = forwardRef<HTMLButtonElement, ChipProps>(function Chip(
  { label, value, active, flash, as = "button", className, ...rest },
  ref,
) {
  const cls = cn(
    "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm transition-colors duration-150 ease-out",
    active
      ? "border-accent bg-accent-weak text-ink"
      : "border-border text-ink-secondary hover:border-border-strong hover:text-ink",
    flash && "border-accent [transition:none]",
    as === "button" &&
      "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus)]",
    className,
  );
  const inner = (
    <>
      <span className="mono text-micro uppercase tracking-wide text-ink-muted">{label}</span>
      <span className="font-medium text-ink">{value}</span>
    </>
  );
  if (as === "span") {
    return (
      <span className={cls} {...(rest as any)}>
        {inner}
      </span>
    );
  }
  return (
    <button ref={ref} type="button" className={cls} aria-expanded={active} {...rest}>
      {inner}
      <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden className="text-ink-muted">
        <path d="M3 4.5 6 7.5 9 4.5" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  );
});
