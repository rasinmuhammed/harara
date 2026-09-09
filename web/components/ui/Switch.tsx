"use client";

import { useId } from "react";
import * as RS from "@radix-ui/react-switch";
import { cn } from "@/lib/cn";

/** Labelled switch with an optional one-line explanation under it. */
export function Switch({
  checked,
  onCheckedChange,
  label,
  hint,
  disabled,
}: {
  checked: boolean;
  onCheckedChange: (v: boolean) => void;
  label: string;
  hint?: string;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <div className={cn("flex flex-col gap-1", disabled && "opacity-45")}>
      <div className="flex items-center justify-between gap-4">
        <label htmlFor={id} className="text-sm text-ink">
          {label}
        </label>
        <RS.Root
          id={id}
          checked={checked}
          onCheckedChange={onCheckedChange}
          disabled={disabled}
          className={cn(
            "relative h-6 w-11 shrink-0 rounded-full border transition-colors duration-150 ease-out",
            "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus)]",
            checked ? "border-accent bg-accent" : "border-border-strong bg-surface-2",
          )}
        >
          <RS.Thumb
            className={cn(
              "block h-4 w-4 rounded-full bg-bg-raised shadow transition-transform duration-150 ease-out",
              "translate-x-1 data-[state=checked]:translate-x-6",
            )}
          />
        </RS.Root>
      </div>
      {hint && <p className="max-w-[46ch] text-sm text-ink-muted">{hint}</p>}
    </div>
  );
}
